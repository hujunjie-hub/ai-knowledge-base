# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AI 知识库助手 — 自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域技术动态，通过多 Agent 协作完成深度分析，结构化存储为 JSON 知识条目，并通过 Telegram / 飞书等渠道自动分发。

## Tech stack

| 层面 | 选型 | 说明 |
|------|------|------|
| Runtime | Python 3.13 | `.python-version` 锁定 3.13 |
| Frontend (future) | TypeScript strict mode | 引入前端代码时同步配好 tsconfig strict + CI |
| AI 编排 | OpenCode + 国产大模型 | OpenCode 负责 Agent 调度，国产模型处理摘要与翻译 |
| Agent 框架 | LangGraph | 多 Agent 协同，有状态工作流 |
| 分发框架 | OpenClaw | 统一适配 Telegram / 飞书等渠道 |
| 日志 | loguru | 结构化日志输出，遵循标准六级语义 |
| 包管理 | uv | `uv.lock` 进版本控制 |
| 测试 | pytest | 配合 mypy（类型检查）+ ruff（lint/format） |
| 安全扫描 | bandit + pip-audit | 依赖漏洞 + SAST（后续 CI 集成） |

## Commands

```bash
uv run pytest                              # run all unit tests
uv run pytest tests/test_foo.py            # run single test file
uv run pytest -k "pattern"                 # run tests matching pattern
uv run pytest --cov=. --cov-report=term    # run tests with coverage report
uv run ruff check .                        # lint
uv run ruff format --check .               # format check (CI)
uv run ruff format .                       # format (write)
uv run mypy .                              # type-check
uv run bandit -c pyproject.toml .          # SAST security scan
uv run pip-audit                           # dependency vulnerability scan
```

CI 上 "lint" 为简写，实际包含：ruff check、ruff format --check、mypy、bandit、pip-audit。

## Coding standards

- **Python 3.13** — 不兼容 3.12 及更早语法。
- **TypeScript strict mode**（前端引入后生效）— tsconfig `"strict": true`，CI 挂 `tsc --noEmit`。
- **PEP 8** — 行宽 99 字符，4 空格缩进。
- **snake_case** — 变量、函数、文件名统一使用。
- **Google 风格 docstring** — 所有无 `_` 前缀的公共函数/类必须有；`Args:` / `Returns:` 段只写语义，不重复类型注解。
- **类型注解** — 函数签名必须有；mypy 零错误。
- **禁止裸 `print()`** — 日志统一用 `loguru`（`from loguru import logger`）。日志等级遵循 loguru 标准六级语义：`debug`（开发调试）、`info`（关键节点）、`warning`（可恢复异常）、`error`（不可恢复但继续）、`critical`（进程退出）。
- **禁止裸 `except:`** — 必须指定异常类型。
- **import 顺序** — 标准库 → 第三方 → 本地，CI 强制。
- **环境变量** — `{SERVICE}_{FIELD}` 全大写格式，`.env.example` 必填，禁止硬编码密钥。
- **无魔法字符串** — 状态值（如 `"reviewed"` `"github_trending"`）、HTTP 状态码（如 `429`）及其他跨模块使用的字面量，必须定义为模块级常量或枚举。按 code review 拦截，暂无自动检查。
- **禁止 TODO 进入 main** — 通过 pre-commit hook 本地拦截 + CI `grep TODO` 二次防线。
- **错误处理** — 非关键路径允许 `logger.error` + return None；关键路径必须抛出明确的自定义异常。
- **许可证审计** — CI 自动扫描（`pip-audit`），禁止引入 GPL/AGPL 等强 copyleft 依赖。

## Testing & coverage

### 目录布局

- 单测：`tests/` 按模块镜像集中管理（`tests/pipeline/test_collector.py`）
- 集成测试：`tests/integration/` — 端到端管道验证，用真实 API
- 集成测试不挂在每次 CI push 上，单独定时触发（触发频率后续确定）

### 命名约定

- 文件名：`test_<模块名>.py`
- 函数名：`test_<函数名>` — 按被测试函数一对一对应

### Mock 策略

- 所有外部 API 调用全 mock（单测永不允许联网）
- 使用 `pytest-mock`（`mocker` fixture）

### 覆盖率

- 分层目标（人工判断层级归属，CI 强制全局阈值）：
  - 业务逻辑层 ≥ 90%
  - 工具层 ≥ 80%
  - 边界适配层 ≥ 50%
- CI 当前强制全局 80%，分层阈值在文档中声明，逐步实现分目录 CI 检查

## Project structure

```
.claude/            # claude 配置
├── agents/          # 自定义 Agent 定义（采集 / 分析 / 整理）
└── skills/          # 自定义 Skill 定义（github-trending / tech-summary）

knowledge/           # 知识数据
├── raw/             # 原始采集数据（未经分析的原始 API 响应）
└── articles/        # 分析后的结构化知识条目 + 每日索引

spec/                # 项目规范与设计文档
pipeline/            # 工具函数、API 封装、模型调用
schemas/             # JSON Schema 定义与字段验证
scripts/             # 一键运行脚本（fetch / analyze / distribute）
```

## Knowledge entry JSON schema

每条知识条目存储为单个 JSON 文件，按 `<date>-<source>-<slug>.json` 命名存放于 `knowledge/articles/`。每日另生成轻量索引文件 `<date>-index.json`。

```json
{
  "id": "<uuid7 — 时戳可排序的唯一标识>",
  "title": "<条目标题，中文翻译>",
  "title_en": "<原始英文标题>",
  "source_url": "<原文链接>",
  "source_type": "<github_trending | hacker_news>",
  "summary": "<AI 生成的 2-3 句中英文摘要>",
  "tags": ["<技术标签 — LLM | Agent | Infra | Tool | Paper>"],
  "relevance_score": "<0.0–1.0，AI 评估的相关度>",
  "status": "<draft | reviewed | published>",
  "fetched_at": "<ISO 8601 采集时间>",
  "analyzed_at": "<ISO 8601 分析完成时间>",
  "published_at": "<ISO 8601 发布时间，未发布则为 null>"
}
```

### 字段约束

- `id` 必须可时序排序（使用 UUID v7）
- `source_type` 仅允许 `github_trending` 或 `hacker_news`
- `tags` 至少 1 个，最多 5 个；标签集合由分析 Agent 维护
- `relevance_score` ≥ 0.7 才进入后续分发流程
- `status` 流转：`draft` → `reviewed` → `published`（单向，不可逆）

## Agent roles

| 角色 | 职责 | 输入 | 输出 | 关键约束 |
|------|------|------|------|----------|
| **Collector** 采集 Agent | 从 GitHub Trending / Hacker News 拉取原始数据，去重，入 raw 库 | API 响应 | `knowledge/raw/YYYY-MM-DD.json` | 不做任何内容过滤或评分 |
| **Analyzer** 分析 Agent | 逐条阅读原文，生成中文摘要和亮点，评分 (1-10)，建议标签 | Collector 输出的 JSON 数组 | 分析后 JSON 数组（summary / highlights / score / tags） | 必须逐条 WebFetch 原文；评分覆盖 ≥3 个区间；禁止 LLM 万能标签 |
| **Organizer** 整理 Agent | 去重检查、评分筛选、格式化为标准 Schema、写入 `knowledge/articles/` | Analyzer 输出的 JSON 数组 | `knowledge/articles/{date}-{source}-{slug}.json` + 当日索引 | 管道唯一写权限；三级去重（URL / 标题 / 语义）；禁止覆盖已有文件 |

### Agent 调度

- **每天 09:00 UTC+8** — Collector 启动，采集前一天 Trending 数据
- Collector 完成后 → Analyzer 自动触发
- Analyzer 完成后 → Organizer 自动触发，入库 `knowledge/articles/`
- 使用 LangGraph StateGraph 编排，支持失败重试（单次，不回退）
- 分发到 Telegram / 飞书由下游分发 Agent 在 Organizer 完成后触发

## Red lines（绝对禁止）

1. **禁止手动编辑 `knowledge/articles/` 下的任何文件** — 所有内容由 Agent 生成；若数据有误，修复上游逻辑后重新运行管道
2. **禁止在 Agent 逻辑中硬编码 API Key / Token** — 统一从环境变量或 `.env` 文件读取
3. **禁止向外部 API 发送原始用户数据** — 仅发送必要的公开 URL 和标题
4. **禁止跨日覆盖历史 articles 文件** — 每日 JSON 只写一次，不可追加或覆写历史
5. **禁止单条失败阻塞整批处理** — 单条目分析失败应记录错误并继续处理其余条目，最终报告中标注失败项
6. **禁止分发未经分析的条目** — `status` 非 `reviewed` 的条目绝对不可进入分发流程
7. **禁止爬取付费/Paywall 内容** — 仅采集公开可访问的页面
