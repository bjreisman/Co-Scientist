import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { readModelRouting } from '../server/utils/modelRouting.ts'

test('legacy runs do not claim a policy or historical dispatches', async () => {
  const run = await mkdtemp(join(tmpdir(), 'model-routing-'))
  try {
    const data = await readModelRouting(run)
    assert.equal(data.configured, false)
    assert.deepEqual(data.dispatches, [])
  } finally { await rm(run, { recursive: true, force: true }) }
})

test('requested policy and mismatching observed model remain separate, without private fields', async () => {
  const run = await mkdtemp(join(tmpdir(), 'model-routing-'))
  try {
    await mkdir(join(run, 'state/model_dispatches'), { recursive: true })
    await writeFile(join(run, 'state/MODEL_POLICY.json'), JSON.stringify({ policy: {
      enabled: true, fallback: 'stop', roles: { reviewer: { model: 'gpt-6.1-sol', reasoning_effort: 'high' } },
      tasks: { review: 'reviewer' }, skill_overrides: { 'hypothesis-full-review': 'reviewer' }
    } }))
    await writeFile(join(run, 'state/model_dispatches/abc-123.json'), JSON.stringify({
      id: 'abc-123', skill: 'hypothesis-full-review', route: 'codex_subagent', status: 'completed',
      requested: { model: 'gpt-6.1-sol', reasoningEffort: 'high' },
      observed: [{ model: 'gpt-6-luna', reasoningEffort: 'medium' }], verification: 'mismatch',
      findingsArtifact: '/private/findings', sessionId: 'secret-id', content: 'private conversation'
    }))
    const data = await readModelRouting(run)
    assert.equal(data.tasks[0].requested.model, 'gpt-6.1-sol')
    assert.equal(data.overrides[0].skill, 'hypothesis-full-review')
    assert.equal(data.dispatches[0].observed[0].model, 'gpt-6-luna')
    assert.equal(data.dispatches[0].verification, 'mismatch')
    assert.doesNotMatch(JSON.stringify(data), /secret-id|private conversation|private\/findings/)
  } finally { await rm(run, { recursive: true, force: true }) }
})
