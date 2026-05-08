---
name: github-trending
description: 从 GitHub Trending 抓取 AI/LLM/Agent/ML 热门开源项目，输出 JSON 数组。当用户说"抓取/采集/拉取/获取/查看 GitHub trending/热门/趋势 项目"、"fetch/scrape/pull/get trending repos"、"今天 GitHub 有什么热门 AI 项目"、"what's hot on GitHub"等中英文表达时触发。
allowed-tools: Bash, WebFetch
---

# GitHub Trending 采集技能

## 概述

从 `github.com/trending` 抓取当日 Top 25 仓库，筛选 topics 含 `ai`/`llm`/`agent`/`ml` 的项目，以 JSON 数组输出到 stdout。

- **角色定位**：Collector Agent 的核心采集能力
- **下游消费者**：Analyzer Agent（接收 JSON 数组做深度分析）

## 环境准备

首次使用前安装依赖：

```bash
uv add beautifulsoup4 jsonschema
```

## 执行步骤

### 1. 抓取页面

WebFetch `https://github.com/trending`（默认 daily），获取 HTML 内容。

### 2. 解析过滤

将 HTML 通过 stdin 传入解析脚本：

```bash
python .claude/skills/github-trending/scripts/parse_trending.py
```

脚本解析仓库列表，按 topics 过滤后输出 JSON 数组。

### 3. 验证输出

脚本在 `json.dump` 前自动以 `schemas/trending_output.schema.json` 校验输出数组；校验失败时打 stderr WARNING，不阻塞输出。调用方无需额外校验步骤。若 stdout 为 `[]`，说明当日无匹配项目或页面解析失败。

## 输出格式

```json
[
  {
    "name": "owner/repo",
    "url": "https://github.com/owner/repo",
    "stars": 12345,
    "topics": ["llm", "agent", "tool"],
    "description": "A framework for building LLM applications"
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 仓库全名 (owner/repo) |
| `url` | string | 是 | GitHub 仓库完整 URL |
| `stars` | integer | 是 | Star 数量 |
| `topics` | string[] | 是 | 仓库 topics 标签，至少 1 个 |
| `description` | string | 是 | 仓库原始英文描述，可为空字符串 |

## stdout 消费者协议

stdout 输出的 JSON 数组由**调用方（caller）**负责捕获并传递给下游：

| 调用模式 | 调用方 | stdout 处理方式 |
|----------|--------|-----------------|
| LangGraph 自动调度 | Collector Agent 节点 | 节点从 stdout 捕获 JSON，写入 LangGraph state 的 `raw_items` 字段，传递给 Analyzer 节点 |
| 手动单独 invoke | 用户 / 开发者 | JSON 输出到终端；若需进管道，手动将其作为 Analyzer 的输入 |

调用方约定：
- 必须捕获 stdout，不依赖文件系统中的中间文件
- 捕获后验证 JSON 为合法数组（空数组 `[]` 为合法值）
- `total_parsed == 0` 时检查 stderr WARNING，触发运维告警

## 约束

- **不使用 GitHub API** — 直接解析 HTML 页面，避免 rate limit
- **不做去重** — 由下游 Organizer Agent 负责
- **不写文件** — 仅 stdout 输出 JSON
- **失败返回 `[]`** — 任何异常均输出空数组，不抛错
- **预期 < 10s** — WebFetch 超时由框架控制，skill 不做硬超时截断
- **过滤关键词**：`ai`, `llm`, `agent`, `ml`（大小写不敏感，子串匹配 topics）
