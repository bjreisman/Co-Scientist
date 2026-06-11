# Co-Scientist

[English](README.md)

Co-Scientist 是一个仓库本地的科研 agent 工作流，用于生成、审阅、排序、演化和总结科学假设。它面向 Claude Code 和 Codex 这类 host-agent 运行时设计，同时把关键状态保存在 `runs/<run_id>/` 下的普通文件中。

本项目使用 Markdown skills 定义 agent 行为，并使用 Python contracts 支撑状态、验证、检索、embedding、排序和 dashboard。预期用户体验是：安装环境，安装项目本地 skills，从研究目标启动一次 run，然后检查生成的 artifacts 和 dashboard receipts。

英文 `README.md` 是主文档和事实来源。本中文文档与当前英文版章节和内容对齐；若两者后续出现细节不一致，请以英文版为准。

## 目录

- [预览](#预览)
- [它能做什么](#它能做什么)
- [快速开始](#快速开始)
- [环境要求](#环境要求)
- [安装](#安装)
- [启动一次 Run](#启动一次-run)
- [用户配置](#用户配置)
- [运行产物](#运行产物)
- [Dashboard](#dashboard)
- [验证](#验证)
- [可选 MCP 检索桥](#可选-mcp-检索桥)
- [仓库结构](#仓库结构)
- [开发](#开发)
- [贡献与安全](#贡献与安全)
- [引用](#引用)
- [致谢](#致谢)
- [许可证](#许可证)

## 预览

Pipeline overview 展示 host agent 如何从研究目标推进到生成、审阅、排序、演化、收敛和最终综合，同时保留可审计的运行产物。

![Co-Scientist pipeline overview](assets/readme/pipeline-overview.png)

Dashboard 为每次 run 提供研究计划、执行状态、假设排名和选中假设详情的紧凑视图。

![Co-Scientist dashboard overview](assets/readme/dashboard-overview.png)

## 它能做什么

Co-Scientist 运行一个结构化假设工作流：

1. 配置研究目标和运行策略。
2. 从文献、辩论和假设前提出发生成假设。
3. 使用 observation、simulation、summary、full-review 和 deep-verification 等 passes 审阅假设。
4. 通过 pairwise tournament artifacts 和 Elo 风格更新为假设排序。
5. 通过多种 transformation skills 演化有前景的假设。
6. 在启用 embeddings 时维护 proximity graph。
7. 在 run 达到有效完成状态后生成最终 research overview。

这个工作流是 file-first 的。Skills 必须读写 canonical artifacts，而不是依赖隐藏聊天记忆。Validators 会检查 artifact graph，因此一次 run 可以被检查、恢复或修复。

## 快速开始

下面路径可以让一个干净 checkout 完成首次 run。文献检索 API keys 和 embedding API keys 都是可选的；没有这些 key 时，工作流仍会启动，并在 provider-backed 能力不可用时记录可审计的 degraded receipts。

### 1. Clone 并安装

```powershell
git clone https://github.com/panjose/Co-Scientist.git
cd Co-Scientist
uv sync --extra dev --extra mcp
```

### 2. 安装项目本地 Skills

对于 Claude Code，安装 slash-command skill surface。

Windows：

```powershell
powershell -File tools/install/install_co_scientist.ps1
```

Unix-like shells：

```bash
bash tools/install/install_co_scientist.sh
```

对于 Codex，安装项目本地 `$skill` surface。

Windows：

```powershell
powershell -File tools/install/install_co_scientist_codex.ps1
```

Unix-like shells：

```bash
bash tools/install/install_co_scientist_codex.sh
```

### 3. 检查环境

```powershell
uv run python -m tools.host.project_cli doctor
```

### 4. 启动一次 Run

在 Claude Code 中，打开仓库根目录并使用：

```text
/co-scientist-start
```

在 Codex 中，打开仓库根目录并使用：

```text
$co-scientist-start
```

或者直接通过 CLI 启动：

```powershell
uv run python -m tools.host.project_cli start --goal "Investigate a plausible mechanism for ammonia synthesis catalyst stability." --budget low --iteration-policy capped --iteration-band 6_10
```

### 5. 打开 Dashboard

使用 start 命令输出的 run 目录：

```powershell
uv run python -m tools.host.project_cli dashboard runs/<run_id>
```

如果你希望获得更强的文献覆盖或使用 proximity-based ranking，可以在第 4 步前添加可选 provider 配置。检索桥、embedding model、timeouts 和 fallback 行为见 [用户配置](#用户配置)。

## 环境要求

- Python 3.12 或更新版本。
- Conda、`uv` 或其他 Python 环境管理器。
- 用于 dashboard 的 Node.js 和 `pnpm`。
- 用于项目本地 host-agent skill 体验的 Claude Code 或 Codex。
- 启用可选文献和 embedding providers 时需要网络访问。

## 安装

Python 依赖声明在 `pyproject.toml` 中，并锁定在 `uv.lock` 中。为了可复现的本地设置，推荐使用 `uv sync`；如果你希望自行管理 Python 解释器，也可以使用 Conda。

### 推荐 `uv` 设置

```powershell
uv sync --extra dev --extra mcp
```

使用这种设置时，通过 `uv run` 执行 Python 命令：

```powershell
uv run python -m tools.host.project_cli doctor
```

### 替代 Conda 设置

```powershell
conda create -n co-scientist python=3.12 -y
conda activate co-scientist
python -m pip install -e ".[dev,mcp]"
```

### Dashboard 依赖

```powershell
pnpm --dir apps/dashboard install
pnpm --dir apps/dashboard build
```

### 项目本地 Claude Code Skills

Windows：

```powershell
powershell -File tools/install/install_co_scientist.ps1
```

Unix-like shells：

```bash
bash tools/install/install_co_scientist.sh
```

### 项目本地 Codex Skills

Windows：

```powershell
powershell -File tools/install/install_co_scientist_codex.ps1
```

Unix-like shells：

```bash
bash tools/install/install_co_scientist_codex.sh
```

Codex installer 会把项目本地 discovery surface 写入 `.agents/skills/`，把安装状态记录到 `.co-scientist/installed-codex-skills.json`，并维护本地 `AGENTS.md` managed block。它默认不会创建项目级 `.codex/` 目录。

最后，在你将用于 Co-Scientist 的环境中运行 doctor：

```powershell
uv run python -m tools.host.project_cli doctor
```

或者，对于 Conda：

```powershell
conda activate co-scientist
python -m tools.host.project_cli doctor
```

`doctor` 会检查 Python、必需 runtime packages、dashboard tooling、dashboard install state、Claude Code 和 Codex skill 安装情况，以及 `runs/` 目录。

下面示例默认使用 `uv run` 执行 Python 命令。Conda 用户可以在 `conda activate co-scientist` 后，把 `uv run python` 替换为 `python`。

## 启动一次 Run

### Claude Code

安装项目本地 skills 后，从仓库根目录打开 Claude Code，并使用：

```text
/co-scientist-start
```

常用入口命令：

```text
/co-scientist-install
/co-scientist-doctor
/co-scientist-params
/co-scientist-start
/co-scientist-dashboard runs/<run_id>
```

### Codex

安装项目本地 Codex skills 后，从仓库根目录打开 Codex，并使用：

```text
$co-scientist-start
```

常用入口 skills：

```text
$co-scientist-doctor
$co-scientist-params
$co-scientist-start
$co-scientist-dashboard runs/<run_id>
```

### Python CLI

从仓库根目录直接启动：

```powershell
uv run python -m tools.host.project_cli start --goal "Investigate a plausible mechanism for resistance." --iteration-policy completion_driven
```

capped run：

```powershell
uv run python -m tools.host.project_cli start --goal "Investigate a plausible mechanism for resistance." --budget low --iteration-policy capped --iteration-band 6_10
```

查看可用 start 控制项：

```powershell
uv run python -m tools.host.project_cli params
uv run python -m tools.host.project_cli start --help
```

核心控制项：

| 控制项 | 选项 | 用途 |
| --- | --- | --- |
| `--exploration` | `conservative`, `balanced`, `aggressive` | 控制新颖性、多样性和广度。 |
| `--generation-bias` | `literature_heavy`, `debate_heavy`, `assumptions_heavy`, `mixed` | 调整生成策略偏向。 |
| `--review` | `light`, `standard`, `strict` | 控制审阅深度和批判严格程度。 |
| `--budget` | `low`, `medium`, `high` | 控制每轮强度。 |
| `--iteration-policy` | `completion_driven`, `capped` | 选择语义停止或用户指定迭代上限。 |
| `--iteration-band` | `6_10`, `10_14`, `15_20`, `20_30` | 设置 capped run 的近似迭代范围。 |
| `--evolution` | `exploit`, `balanced`, `diversify` | 调整后期搜索行为。 |
| `--stop-policy` | `exploratory`, `standard`, `strict` | 控制收敛时停止 run 的难易程度。 |
| `--human-checkpoint` | `auto`, `before_overview`, `before_completion`, `every_major_stage` | 控制 host 何时暂停等待确认。 |

## 用户配置

大多数用户只需要环境变量加 CLI start 控制项。不要通过编辑 skill prompts 来更改 providers、models 或 run policy。

外部 API keys 对启动和运行工作流是可选的。没有 literature provider keys 时，bridge 仍会尝试支持的公开 metadata providers，并记录可审计 provider receipts。没有 embedding API key 时，proximity updates 会记录结构化 skip receipt，ranking 会使用文档化 fallback path。

### 文献检索桥

文献检索桥会调用真实公开 provider APIs，并写入可审计 evidence artifacts。需要 literature grounding 的 skills 必须调用 canonical bridge；它们不能编造 papers、DOIs、arXiv IDs、venues、citation counts 或 abstracts。

基础使用不需要文献检索 API key。`OPENALEX_EMAIL` 是用于礼貌 provider 使用的联系地址，不是 secret。`OPENALEX_API_KEY` 和 `SEMANTIC_SCHOLAR_API_KEY` 在可用时可以提升 provider 可靠性和 rate limits，但 bridge 没有这些 key 也能运行。匿名访问可能返回较少结果、遇到 rate limits，或者生成 `partial` / `blocked` evidence bundle。

支持 providers：

- `openalex`
- `crossref`
- `europe_pmc`
- `semantic_scholar`
- `arxiv`

常用配置：

```powershell
$env:OPENALEX_EMAIL="you@example.edu"
$env:OPENALEX_API_KEY="..."                  # optional
$env:SEMANTIC_SCHOLAR_API_KEY="..."          # optional
$env:CO_SCIENTIST_LITERATURE_MAX_RESULTS="10"
$env:CO_SCIENTIST_LITERATURE_TIMEOUT_SECONDS="30"
```

Provider failures 会被保留。如果至少一个 provider 成功，bridge 可以返回 `partial` evidence bundle。如果所有 provider 都失败或被跳过，它会返回 `blocked`，下游 skills 必须保留这个状态，而不是声称已经完成 literature grounding。

Bridge 会写入：

```text
literature/queries/<query_id>/REQUEST.json
literature/queries/<query_id>/PROVIDER_RECEIPTS.json
literature/queries/<query_id>/CANDIDATE_PAPERS.json
literature/queries/<query_id>/VERIFIED_PAPERS.json
literature/queries/<query_id>/EVIDENCE_BUNDLE.json
literature/queries/<query_id>/EVIDENCE_BUNDLE.md
literature/queries/<query_id>/SEARCH_TRACE.jsonl
literature/bundles/<bundle_id>.json
```

Bridge 会检索 provider metadata 和可用 abstracts。它不保证机构 full-text access、provider uptime，也不保证某篇论文支持某个细粒度 claim。请使用 receipts、verified-paper status 和 validation commands 审计覆盖情况。

### Proximity Embedding Model

Proximity embeddings 是 run capability。启用并配置后，可行假设会获得 embeddings，`state/PROXIMITY_GRAPH.json` 会被更新，ranking 可以使用 similarity-aware context。如果 embeddings 不可用，run 应保留结构化 skip 或 failure receipt，并使用文档化 ranking fallback。

Embedding API key 是可选的。如果没有为所选 provider 配置 key，proximity bridge 会记录 `skipped_provider_unavailable`，不会写入伪造 vectors，并让 ranking 通过 receipt-gated fallback 继续。当你想有意禁用这个能力时，可以设置 `CO_SCIENTIST_PROXIMITY_ENABLED=false`。

Provider、model、dimensions、timeout 和 provider 环境变量名称会解析进每次 run 的 `state/RESOLVED_RUN_CONFIG.json`。Resume 会使用 run-local 配置，因此后续修改 shell 环境变量不会静默改变现有 run 的 embedding space。

配置面：

| 设置 | 配置方式 |
| --- | --- |
| Provider | `openai_compatible`, `gemini` |
| Model | 使用 `CO_SCIENTIST_EMBEDDING_MODEL` 设置，或使用项目默认值。 |
| Dimensions | 使用 `CO_SCIENTIST_EMBEDDING_DIMENSIONS` 设置，或使用项目默认值。 |
| Enabled | `true` |
| Base URL env var | OpenAI-compatible providers 使用 `OPENAI_BASE_URL`；Gemini 不使用。 |
| API key env var | OpenAI-compatible providers 使用 `OPENAI_API_KEY`；Gemini 使用 `GEMINI_API_KEY`。 |

OpenAI-compatible 示例：

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
$env:CO_SCIENTIST_EMBEDDING_PROVIDER="openai_compatible"
$env:CO_SCIENTIST_EMBEDDING_MODEL="<embedding-model-name>"
$env:CO_SCIENTIST_EMBEDDING_DIMENSIONS="<embedding-dimension-count>"
$env:CO_SCIENTIST_EMBEDDING_TIMEOUT_SECONDS="60"
```

Gemini 示例：

```powershell
uv sync --extra dev --extra mcp --extra gemini

$env:GEMINI_API_KEY="..."
$env:CO_SCIENTIST_EMBEDDING_PROVIDER="gemini"
$env:CO_SCIENTIST_EMBEDDING_MODEL="gemini-embedding-2"
$env:CO_SCIENTIST_EMBEDDING_DIMENSIONS="768"
$env:CO_SCIENTIST_EMBEDDING_TIMEOUT_SECONDS="60"
```

对于 Gemini，`CO_SCIENTIST_EMBEDDING_DIMENSIONS` 会作为 `output_dimensionality` 传给 provider。如果 `GEMINI_API_KEY` 或可选 `google-genai` 依赖不可用，proximity bridge 会记录 `skipped_provider_unavailable`，ranking 会通过文档化 fallback path 继续。

`CO_SCIENTIST_EMBEDDING_DIMENSIONS` 必须匹配所选 model 返回的 vector size。如果你更改 model 或 dimensions，请启动新 run 或重建 proximity graph。

高级 provider 变量间接配置：

```powershell
$env:CO_SCIENTIST_EMBEDDING_BASE_URL_ENV="MY_EMBEDDING_BASE_URL"
$env:CO_SCIENTIST_EMBEDDING_API_KEY_ENV="MY_EMBEDDING_API_KEY"
$env:MY_EMBEDDING_BASE_URL="https://your-openai-compatible-endpoint/v1"
$env:MY_EMBEDDING_API_KEY="..."
```

显式禁用 proximity embeddings：

```powershell
$env:CO_SCIENTIST_PROXIMITY_ENABLED="false"
```

不要在同一个 proximity graph 中混用 embedding dimensions 或 models。如果你改变 embedding space，请启动新 run 或重建 graph。

## 运行产物

Run 会创建在 `runs/<run_id>/` 下。Bootstrap 会写入：

```text
input.md
RUN_POLICY.yaml
state/START_REQUEST.json
state/POLICY_DECISION.json
state/RESOLVED_RUN_CONFIG.json
state/STRATEGY_PLAN.json
```

配置阶段随后会 materialize：

```text
research_plan/RESEARCH_PLAN.json
```

后续阶段会写入 generation、review、ranking、evolution、proximity、literature、dashboard 和 overview artifacts。如果一个 run 报告 `inspect_state` 或 `validation blocked`，请把它视为 artifact consistency 问题。在 resume 或生成 final overview 前，应先修复报告出的 drift。

## Dashboard

`start`、`run` 和 `resume` 会尝试在后台 bootstrap dashboard runtime。用下面命令为一次 run 解析 ready links：

```powershell
uv run python -m tools.host.project_cli dashboard runs/<run_id>
```

Dashboard receipts：

```text
runs/<run_id>/dashboard/LINKS.md
runs/<run_id>/dashboard/LINKS.json
```

`LINKS.md` 用作人类可读 receipt，`LINKS.json` 用作机器可读 receipt。

## 验证

验证一次 run：

```powershell
uv run python -m tools.validation.contract_validation runs/<run_id> --skill co-scientist-pipeline
```

验证 completion readiness：

```powershell
uv run python -m tools.validation.verify_pipeline_completion runs/<run_id> --skill co-scientist-pipeline
```

对于 literature-heavy runs，请检查：

- `PROVIDER_RECEIPTS.json` 记录了尝试过的 providers。
- `EVIDENCE_BUNDLE.json.retrieval_metadata.status` 是 `succeeded` 或 `partial`。
- `CANDIDATE_PAPERS.json` 包含 skill 使用的 papers。
- `VERIFIED_PAPERS.json` 区分 `verified`、`verify_pending` 和 `unverified` candidates。
- 下游 artifacts 中的 retrieval results 会链接回 `evidence_bundle_ids` 和 `literature_query_ids`。

## 可选 MCP 检索桥

可选 MCP server 会把同一个 canonical literature bridge 暴露给支持 MCP 的 hosts。它是一个薄 transport layer；provider calls、deduplication、verification、bundle construction 和 validation 仍保留在 Python packages 中。

安装可选依赖：

```powershell
uv sync --extra mcp
```

从仓库根目录运行 stdio server：

```powershell
uv run python mcp-servers/search-bridge/server.py
```

对于 Codex，请使用 `templates/codex/config.toml.example` 作为 MCP config snippet。把 `[mcp_servers.co_scientist_search_bridge]` block 复制或合并到用户级 `~/.codex/config.toml`，也可以通过 Codex CLI MCP configuration command 添加 server。项目 installer 默认不会创建 `.codex/`；项目本地 `.codex/` 仅用于高级 trusted-project overrides。

暴露工具：

- `search_literature(run_dir, request, verify=True)`
- `search_start(run_dir, request, verify=True)`
- `search_status(run_dir, job_id)`
- `get_evidence_bundle(run_dir, bundle_id)`
- `verify_literature_candidates(run_dir, query_id)`

Request shape 和 reliability boundary 见 `mcp-servers/search-bridge/README.md`。

## 仓库结构

```text
apps/dashboard/                 Nuxt dashboard
mcp-servers/search-bridge/      Optional MCP transport for literature search
packages/agent_contracts/       Pydantic contracts for run artifacts
packages/agent_mechanics/       Deterministic helpers for search, embeddings, ranking, and selection
packages/agent_support/         Policy resolution, routing, parsing, and shared support
packages/run_artifacts/         Artifact IO and synchronization helpers
skills/                         Agent-readable Markdown skills
templates/                      Run and input templates
tests/                          Pytest coverage
tools/                          CLI, install, dashboard, policy, and validation tools
```

## 开发

安装开发依赖：

```powershell
uv sync --extra dev --extra mcp
```

运行当前验证套件：

```powershell
uv run python -m ruff check packages tools mcp-servers tests
uv run python -m ruff format --check packages tools mcp-servers tests
uv run pytest -q
uv pip check
```

在不启动 Codex 的情况下验证 Codex install surface：

```powershell
uv run python -m tools.validation.verify_codex_integration_surface
```

编辑 dashboard-facing contracts 后重新生成 dashboard contract artifacts：

```powershell
uv run python -m packages.dashboard_contracts.export_contract_artifacts
```

代码、注释、canonical technical documentation、测试和 skill-facing technical documentation 应保持英文。允许 `README.zh-CN.md` 这类翻译文档，但英文 README 仍是 source of truth。

## 贡献与安全

开发设置、验证命令和 pull request 预期见 [CONTRIBUTING.md](CONTRIBUTING.md)。

社区行为预期见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

请私下报告疑似安全漏洞。支持的报告路径和 credential-handling guidance 见 [SECURITY.md](SECURITY.md)。

## 引用

如果你在研究中使用本仓库，请通过 [CITATION.cff](CITATION.cff) 引用本项目，并引用下方列出的上游 AI co-scientist 工作。

## 致谢

本项目建立在 Google DeepMind 公开 AI co-scientist 研究方向之上：

- [Co-Scientist: A multi-agent AI partner to accelerate research](https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/)
- [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)

感谢 [Xinhe Li](https://github.com/Xinhe-Li/) 早期 pipeline 设计和实现工作，这些工作帮助塑造了本仓库的起点。

感谢 [ARIS project](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 围绕 portable、agent-readable research automation 提供的轻量 skill-workflow ideas。

## 许可证

本仓库使用 Apache License 2.0。详见 [LICENSE](LICENSE)。
