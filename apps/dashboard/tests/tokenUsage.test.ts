import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm, realpath, symlink } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { readTokenUsage, tokenUsageRunDir, validateCreditBudget, writeCreditBudget } from '../server/utils/tokenUsage.ts'
import { parseCreditBudgetInput } from '../app/utils/creditBudget.ts'

test('budget form supports Vue number coercion as well as empty/string inputs', () => {
  assert.equal(parseCreditBudgetInput(1000000), 1000000)
  assert.equal(parseCreditBudgetInput('1000000'), 1000000)
  assert.equal(parseCreditBudgetInput('1.5'), 1.5)
  assert.equal(parseCreditBudgetInput('  '), null)
  for (const invalid of [0, -1, NaN, 'not-a-number']) assert.throws(() => parseCreditBudgetInput(invalid))
})

test('missing usage is unknown, while budgets persist independently of collector snapshots', async () => {
  const run = await mkdtemp(join(tmpdir(), 'usage-'))
  try {
    await mkdir(join(run, 'state'))
    const missing = await readTokenUsage(run)
    assert.equal(missing.status, 'unavailable')
    assert.equal(missing.totalTokens, null)
    await writeCreditBudget(run, 500000)
    assert.equal((await readTokenUsage(run)).budgetCredits, 500000)
    await writeCreditBudget(run, null)
    assert.equal((await readTokenUsage(run)).budgetCredits, null)
  } finally { await rm(run, { recursive: true }) }
})

test('measured totals preserve cache subsets and ignore stale snapshot budgets', async () => {
  const run = await mkdtemp(join(tmpdir(), 'usage-'))
  try {
    await mkdir(join(run, 'state'))
    await writeFile(join(run, 'state/TOKEN_USAGE.json'), JSON.stringify({
      status: 'partial', inputTokens: 100, cachedInputTokens: 70, uncachedInputTokens: 30,
      outputTokens: 20, reasoningOutputTokens: 5, totalTokens: 120,
      budgetCredits: 1, sessionCount: 1, missingSessionCount: 1
    }))
    await writeCreditBudget(run, 500)
    const usage = await readTokenUsage(run)
    assert.equal(usage.status, 'partial')
    assert.equal(usage.totalTokens, 120)
    assert.equal(usage.cachedInputTokens, 70)
    assert.equal(usage.budgetCredits, 500)
    assert.equal(usage.missingSessionCount, 1)
  } finally { await rm(run, { recursive: true }) }
})

test('invalid usage cannot masquerade as measured zero or double-count cache', async () => {
  const run = await mkdtemp(join(tmpdir(), 'usage-'))
  try {
    await mkdir(join(run, 'state'))
    for (const payload of ['{"partial":', JSON.stringify({status: 'available', inputTokens: 100, cachedInputTokens: 70,
      uncachedInputTokens: 30, outputTokens: 20, totalTokens: 190})]) {
      await writeFile(join(run, 'state/TOKEN_USAGE.json'), payload)
      assert.equal((await readTokenUsage(run)).totalTokens, null)
    }
  } finally { await rm(run, { recursive: true }) }
})

test('budget accepts only positive finite numbers or explicit null', () => {
  for (const invalid of [0, -1, '500', undefined, true, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => validateCreditBudget(invalid))
  }
  assert.equal(validateCreditBudget(null), null)
  assert.equal(validateCreditBudget(500000), 500000)
})

test('usage endpoints cannot resolve directory traversal outside the run root', async () => {
  const root = await mkdtemp(join(tmpdir(), 'usage-runs-'))
  try {
    await mkdir(join(root, 'real-run'))
    assert.equal(await tokenUsageRunDir(root, 'real-run'), await realpath(join(root, 'real-run')))
    const outside = await mkdtemp(join(tmpdir(), 'usage-outside-'))
    try {
      await symlink(outside, join(root, 'escape'))
      await assert.rejects(() => tokenUsageRunDir(root, 'escape'))
    } finally { await rm(outside, { recursive: true }) }
    for (const invalid of ['../outside', '..', '.', '/tmp', 'real-run/../outside', '']) {
      await assert.rejects(() => tokenUsageRunDir(root, invalid))
    }
  } finally { await rm(root, { recursive: true }) }
})

test('credit estimate and model breakdown retain partial coverage without exposing unrelated fields', async () => {
  const run = await mkdtemp(join(tmpdir(), 'usage-'))
  try {
    await mkdir(join(run, 'state'))
    await writeFile(join(run, 'state/TOKEN_USAGE.json'), JSON.stringify({
      status: 'available', inputTokens: 500000, cachedInputTokens: 400000, uncachedInputTokens: 100000,
      outputTokens: 100000, totalTokens: 600000, estimatedCredits: 31, creditStatus: 'partial',
      unpricedTokens: 200, freeSafetyTokens: 100, modelCredits: [{model: 'gpt-6.1-sol (standard)', credits: 31}],
      secret: 'must not be exported'
    }))
    await writeCreditBudget(run, 50.5, 'fast')
    const usage = await readTokenUsage(run)
    assert.equal(usage.estimatedCredits, 31)
    assert.equal(usage.creditStatus, 'partial')
    assert.equal(usage.budgetCredits, 50.5)
    assert.equal(usage.fallbackSpeed, 'fast')
    assert.equal(usage.unpricedTokens, 200)
    assert.equal(usage.modelCredits[0].credits, 31)
    assert.equal('secret' in usage, false)
    await assert.rejects(() => writeCreditBudget(run, 50, 'unknown-speed'))
  } finally { await rm(run, {recursive: true}) }
})
