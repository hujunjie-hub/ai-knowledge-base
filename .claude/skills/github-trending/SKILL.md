---
name: github-trending
description: 当需要采集 Github 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

- 用户需要采集 GitHub 上 AI/LLM/Agent 领域的当日热门开源项目
- 作为知识库管道的第一环，为下游分析 Agent 提供原始数据
- 定期（每日）自动抓取，也可手动触发单次采集

## 执行步骤

### 第 1 步：搜索热门仓库

调用 GitHub Search API，按 stars 降序检索近 7 天内创建或更新的 AI 相关仓库：

```
GET https://api.github.com/search/repositories
  ?q=ai+OR+llm+OR+agent+OR+machine-learning+created:>={7_days_ago}
  &sort=stars
  &order=desc
  &per_page=100
```

若无 API Token，使用 WebFetch 抓取 GitHub Trending 页面作为备选。

### 第 2 步：提取信息

从 API 响应或页面中提取每个仓库的关键字段：

- `name` — 仓库全名（owner/repo）
- `url` — GitHub 仓库链接
- `stars` — star 数量
- `language` — 主要编程语言
- `topics` — 仓库标签列表
- `description` — 原始英文描述

### 第 3 步：过滤

**纳入规则**：项目主题或描述中包含 AI、LLM、Agent、ML、NLP、Deep Learning、Transformer、RAG、Prompt、Fine-tuning、Embedding、Vector、Inference 等关键词。

**排除规则**：
- `awesome-*` 开头的 Awesome 列表类仓库
- 纯教程/课程类（如 `*-tutorial`、`*-course`、`*-guide`）
- 与 AI 领域无关的通用工具或框架

### 第 4 步：去重

以 `url` 为主键去重。若同一仓库在多次拉取中出现，仅保留第一次。注意识别 fork 与原仓库 — 优先保留原仓库，丢弃 fork。

### 第 5 步：撰写中文摘要

对每个通过过滤的仓库，按以下公式生成一句话中文摘要：

> **项目名** + 做什么 + 为什么值得关注

示例：`LangChain — 用于构建 LLM 应用链式调用的框架，本周 star 增速最快，生态集成超过 50 个模型和工具。`

摘要控制在 40–80 字，突出具体技术细节而非泛化描述。

### 第 6 步：排序取 Top 15

按 `stars` 降序排列，取前 15 条。若 star 数相同，按 `name` 字母序次级排序。确保最终输出恰好 15 条（不足 15 条时以实际数量输出，并在日志中标注）。

### 第 7 步：输出 JSON 文件

将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`（日期为采集当日）。文件需为 UTF-8 编码、格式化 JSON（indent=2），且必须是一次性写入（不可追加）。

## 注意事项

- **不进行内容评分**：采集阶段仅做过滤和排序，不做 relevance_score 计算，评分由下游 Analyzer Agent 负责。
- **API 限流**：GitHub API 未认证限速 10 次/分钟，认证后 30 次/分钟，单次请求合理设置 `per_page`。
- **失败重试**：单次请求失败时重试 1 次，间隔 3 秒；仍失败则记录错误并返回已获取的数据。
- **时区**：所有日期均使用 UTC+8，文件名中的日期与 `collected_at` 字段保持一致。
- **文件不可覆盖**：当日文件若已存在，说明已采集过，应跳过而非覆盖。

## 输出格式

输出 JSON 文件路径：`knowledge/raw/github-trending-YYYY-MM-DD.json`

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-05-08T09:00:00+08:00",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "中文一句话摘要，40–80 字",
      "stars": 12345,
      "language": "Python",
      "topics": ["llm", "agents", "rag"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | 固定值 `github_trending` |
| `skill` | string | 固定值 `github-trending` |
| `collected_at` | string | ISO 8601 采集时间，UTC+8 |
| `items[].name` | string | 仓库全名（owner/repo） |
| `items[].url` | string | GitHub 仓库完整 URL |
| `items[].summary` | string | AI 生成的中文摘要 |
| `items[].stars` | number | star 数量 |
| `items[].language` | string | 主要编程语言 |
| `items[].topics` | string[] | 仓库标签列表 |
