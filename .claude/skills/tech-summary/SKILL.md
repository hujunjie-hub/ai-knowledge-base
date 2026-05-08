---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# 技术深度分析技能

## 使用场景

- 对采集 Agent 产出的原始数据进行深度分析，为知识入库做准备
- 作为知识库管道的第二环，承接 Collector 输出，供 Organizer 消费
- 用户需要对一批技术项目进行逐一评估、提炼摘要、发现趋势时使用

## 执行步骤

### 第 1 步：读取最新原始数据

使用 Glob 列出 `knowledge/raw/` 下最近日期的 JSON 文件，优先处理 `github-trending-*.json`，其次 `hacker-news-*.json`。若存在多个同日文件，按文件名排序逐一处理。

读取文件后提取 `items` 数组。若 `items` 为空或文件不存在，终止并报告。

### 第 2 步：逐条深度分析

对 `items` 中的每个项目，通过 WebFetch 访问其 `url` 阅读原文（README、项目文档、讨论帖等），然后完成以下分析：

**摘要（summary）**

在原始摘要基础上精炼为一句话中文摘要，字数 ≤ 50 字。保留项目名、核心功能和关键差异点。

**技术亮点（highlights）**

列出 2–3 个技术亮点，每个亮点用事实说话，格式为：

> **[亮点标题]**：具体事实描述，含数据或对比。

禁止泛化描述如"性能优异""设计优雅"——必须包含具体数字、技术选型理由、或与同类项目的对比。

**评分（score）**

按以下标准给出 1–10 的整数评分，并附一句话理由：

| 分数区间 | 含义 | 典型特征 |
|----------|------|----------|
| 9–10 | 改变格局 | 全新范式、解决关键瓶颈、巨头发布或顶级论文官方实现 |
| 7–8 | 直接有帮助 | 实际项目可落地、补齐已知短板、生态关键一环 |
| 5–6 | 值得了解 | 有趣但非必需、已有成熟替代品、尚处早期 |
| 1–4 | 可略过 | 实验性 Demo、已停止维护、功能过于单一 |

**硬性约束**：15 个项目中 9–10 分不超过 2 个。若候选超过 2 个，保留得分最高的 2 个，其余降为 8 分。

**标签建议（suggested_tags）**

建议 1–5 个技术标签，从以下标签集中选择或合理扩展：

`LLM` | `Agent` | `RAG` | `Prompt` | `Fine-tuning` | `Embedding` | `Vector` | `Inference` | `Infra` | `Tool` | `Paper` | `Benchmark` | `Multimodal` | `OpenSource` | `Security`

禁止使用 `Misc`、`Other` 等模糊标签。

### 第 3 步：趋势发现

通览全部已分析条目，识别跨项目的共同线索：

- **共同主题（common_themes）**：2–4 个跨项目反复出现的技术方向或问题域，每个附带涉及的项目列表。
- **新概念（emerging_concepts）**：1–2 个首次出现或突然走红的技术概念，附简短说明。

趋势发现应基于条目中的具体事实，不可凭空臆造。

### 第 4 步：输出分析结果 JSON

将分析结果写入 `knowledge/raw/tech-summary-YYYY-MM-DD.json`（与输入文件同日）。文件需为 UTF-8 编码、格式化 JSON（indent=2），一次性写入。

## 注意事项

- **必须 WebFetch 原文**：分析不得仅基于采集阶段的 `summary` 字段，必须逐条访问原文获取最新信息。
- **单条失败不阻塞**：某条目的 WebFetch 或分析失败时，在 `items[].error` 字段记录原因并继续处理剩余条目，最终报告中标注失败数。
- **评分分布自查**：输出前验证 9–10 分数量 ≤ 2、1–4 分至少占 20%（3 条以上）。
- **摘要去水**：禁止"革命性""颠覆性""重磅"等营销词汇，用技术事实说话。
- **标签一致性**：同类项目应使用一致的标签，避免同一概念分散到不同标签。
- **时区**：所有日期均使用 UTC+8。

## 输出格式

输出 JSON 文件路径：`knowledge/raw/tech-summary-YYYY-MM-DD.json`

```json
{
  "source": "github_trending",
  "skill": "tech-summary",
  "analyzed_at": "2026-05-08T10:30:00+08:00",
  "input_file": "knowledge/raw/github-trending-2026-05-08.json",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "精炼中文摘要，≤ 50 字",
      "highlights": [
        "推理速度比 vLLM 快 3 倍，首个支持 FP8 量化的开源推理引擎",
        "与 HuggingFace TGI 完全兼容，迁移成本为 0"
      ],
      "score": 8,
      "score_reason": "补齐了开源推理的性能短板，已有 3 家企业在生产环境验证",
      "suggested_tags": ["LLM", "Inference", "Infra"],
      "error": null
    }
  ],
  "trends": {
    "common_themes": [
      {
        "theme": "推理引擎性能竞赛",
        "description": "本周多个项目聚焦 LLM 推理加速，FP8 量化和 PagedAttention 变体成为主流方向",
        "related_items": ["owner/repo-a", "owner/repo-b"]
      }
    ],
    "emerging_concepts": [
      {
        "concept": "Mixture-of-Agents (MoA)",
        "description": "将 MoE 思想应用于多 Agent 协作，多个项目开始实现 Agent 路由层",
        "related_items": ["owner/repo-c"]
      }
    ]
  },
  "stats": {
    "total": 15,
    "succeeded": 14,
    "failed": 1,
    "score_distribution": {
      "9-10": 2,
      "7-8": 6,
      "5-6": 4,
      "1-4": 3
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | 继承自输入文件的 source 值 |
| `skill` | string | 固定值 `tech-summary` |
| `analyzed_at` | string | ISO 8601 分析完成时间，UTC+8 |
| `input_file` | string | 被分析的原始文件路径 |
| `items[].name` | string | 仓库全名（继承自输入） |
| `items[].url` | string | GitHub 仓库完整 URL |
| `items[].summary` | string | 精炼后的中文摘要，≤ 50 字 |
| `items[].highlights` | string[] | 2–3 个技术亮点，每个含具体事实 |
| `items[].score` | number | 1–10 整数评分 |
| `items[].score_reason` | string | 一句话评分理由 |
| `items[].suggested_tags` | string[] | 1–5 个技术标签 |
| `items[].error` | string\|null | 分析失败时记录错误原因，成功为 null |
| `trends.common_themes` | object[] | 2–4 个跨项目共同主题 |
| `trends.emerging_concepts` | object[] | 1–2 个新兴技术概念 |
| `stats.total` | number | 条目总数 |
| `stats.succeeded` | number | 分析成功数 |
| `stats.failed` | number | 分析失败数 |
| `stats.score_distribution` | object | 四档评分分布，用于自查约束是否达标 |
