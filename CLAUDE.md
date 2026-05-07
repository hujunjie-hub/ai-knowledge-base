# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AI 知识库助手 — 自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域技术动态，通过多 Agent 协作完成深度分析，结构化存储为 JSON 知识条目，并通过 Telegram / 飞书等渠道自动分发。

---

## Tech stack

| 层面 | 选型 | 说明 |
|------|------|------|
| Runtime | Python 3.12 | 最低要求 3.12，利用新语法特性 |
| AI 模型 | Claude (Anthropic) + 国产大模型 | Claude 负责深度分析，国产模型处理摘要与翻译 |
| Agent 编排 | LangGraph | 多 Agent 协同，有状态工作流 |
| 分发框架 | OpenClaw | 统一适配 Telegram / 飞书等渠道 |

---

## Coding standards

- **[PEP 8](https://peps.python.org/pep-0008/)** — 代码风格以 PEP 8 为准，行宽 120 字符
- **snake_case** — 变量、函数、文件名统一使用 snake_case
- **Google 风格 docstring** — 所有公共函数/类必须有 docstring，格式遵循 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- **类型注解** — 函数签名必须包含类型注解；使用 `mypy` 检查
- **禁止裸 `print()`** — 日志统一使用 `logging` 模块，按需配置 logger
- **禁止裸 `except:`** — 异常捕获必须指定异常类型
- **import 顺序** — 标准库 → 第三方库 → 本地模块，每组间空一行

---

## Project structure

```
.claude/              # Claude Code 配置
├── agents/          # 自定义 Agent 定义（采集 / 分析 / 整理）
├── skills/          # 自定义 Skill 定义
└── settings.json    # 项目级权限与钩子配置

knowledge/           # 知识数据
├── raw/             # 原始采集数据（未经分析的原始 API 响应）
└── articles/        # 分析后的结构化知识条目 JSON 文件

agents/              # Agent 实现代码（LangGraph 工作流）
skills/              # Skill 实现代码
scripts/             # 一键运行脚本（fetch / analyze / distribute）
```

---

## Knowledge entry JSON schema

每条知识条目存储为单个 JSON 对象，按日期分文件存放在 `knowledge/articles/YYYY-MM-DD.json` 中。

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
- `tags` 至少包含 1 个标签，最多 5 个；标签集合由分析 Agent 维护
- `relevance_score` ≥ 0.7 才进入后续分发流程
- `status` 流转：`draft` → `reviewed` → `published`（单向，不可逆）

---

## Agent roles

| 角色 | 职责 | 输入 | 输出 | 关键约束 |
|------|------|------|------|----------|
| **Collector** 采集 Agent | 从 GitHub Trending / Hacker News 拉取原始数据，去重，入 raw 库 | API 响应 | `knowledge/raw/YYYY-MM-DD.json` | 不做任何内容过滤或评分 |
| **Analyzer** 分析 Agent | 对原始条目逐条分析：翻译标题、生成摘要、打标签、评估相关度 | `knowledge/raw/YYYY-MM-DD.json` | `knowledge/articles/YYYY-MM-DD.json` | 必须参考前一日 articles 避免重复；relevance_score < 0.7 丢弃 |
| **Curator** 整理 Agent | 审核当日 articles，决策发布顺序，生成推送文案，分发到各渠道 | `knowledge/articles/YYYY-MM-DD.json` | Telegram / 飞书消息 | 每条消息必须含来源链接；status 必须流转至 `published` |

### Agent 调度

- **每天 09:00 UTC+8** — Collector 启动，采集前一天 Trending 数据
- Collector 完成后 → Analyzer 自动触发
- Analyzer 完成后 → Curator 自动触发
- 流程使用 LangGraph StateGraph 编排，支持失败重试（单次，不回退）

---

## Red lines (绝对禁止)

1. **禁止手动编辑 knowledge/articles/ 下的任何文件** — 所有内容由 Agent 生成；若数据有误，修复上游逻辑后重新运行管道
2. **禁止在 Agent 逻辑中硬编码 API Key / Token** — 统一从环境变量或 `.env` 文件读取
3. **禁止向外部 API 发送原始用户数据** — 仅发送必要的公开 URL 和标题
4. **禁止跨日覆盖历史 articles 文件** — 每日 JSON 只写一次，不可追加或覆写历史
5. **禁止单条失败阻塞整批处理** — 单条目分析失败应记录错误并继续处理其余条目，最终报告中标注失败项
6. **禁止分发未经分析的条目** — `status` 非 `reviewed` 的条目绝对不可进入分发流程
7. **禁止爬取付费/Paywall 内容** — 仅采集公开可访问的页面

---

## Verification checklist

- [ ] 连续运行 3 天，每天产生 ≥ 8 条 `reviewed` 条目
- [ ] 抽查 10 条 `summary`，每条包含具体技术细节而非泛化描述
- [ ] 抽查 10 条 `tags`，标签与条目内容匹配（无 `LLM` 万能标签滥用）
- [ ] 验证 Telegram / 飞书推送消息包含有效链接且无格式错误
- [ ] 确认 `relevance_score < 0.7` 的条目已被正确丢弃
- [ ] 确认 `status` 流转单向不可逆（无 `published` → `draft` 回溯）
- [ ] `mypy` 类型检查零错误
- [ ] `python -m pytest` 全部通过
