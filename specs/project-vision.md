# AI 知识库 · 项目愿景 V1.0

## 要做什么

### 数据抓取
- 每天通过 GitHub Search API 抓取 AI 相关仓库，按 stars 排序，取前 10 条
- 搜索条件：`topic:artificial-intelligence` 或 `topic:machine-learning`，按 stars 排
- 抓取字段：仓库名、url、description、stars、主要语言、topics

### Agent 分析
- 对每条仓库分析三个维度：
  - **技术类别**：属于 AI 的哪个子领域（LLM / Agent / CV / Infra / 其他）
  - **创新点**：与前一天上榜的 10 个仓库对比，有什么新意；无历史数据时标注"首日"
  - **使用难度**：面向 PM 视角（能不能快速跑 demo），输出"低 / 中 / 高"
- 分析需加载前一日知识条目作为参照系（系统有状态）

### 输出
- JSON 格式，单文件包含当日全部 10 条条目
- Schema：

```json
{
  "id": "repo 唯一标识",
  "name": "仓库名 (owner/repo)",
  "url": "仓库链接",
  "description": "GitHub description 原文",
  "stars": 12345,
  "language": "主要语言",
  "topics": ["topic1", "topic2"],
  "fetched_at": "抓取日期 (YYYY-MM-DD)",
  "category": "技术类别",
  "innovation": "创新点描述（对比前一日上榜仓库）",
  "difficulty": "低 | 中 | 高"
}
```

- 下游 Agent 消费这些条目，进行总结分析、去重

## 不做什么

- 不做多日趋势分析（那是下游 Agent 的活）
- 不做 Trending 页面抓取
- 不做人工审核/编辑流程
- 不输出 Markdown 可读格式（JSON only）
- 不过滤非 AI 领域仓库（search API 已通过 topic 限定）

## 边界 & 验收

- 每日 10 条，允许因 API 限速或网络波动少 1-2 条，但不低于 8 条
- 创新点需引用前一日具体仓库名作为对比，不得输出通用套话
- 使用难度判定需有依据（能否 pip install、是否有 demo/colab、是否需 GPU）
- 数据存储为按日分区的 JSON 文件，便于前一日加载对比
- 抓取和分析是一次性流程，每天一次，不实时、不增量

## 怎么验证

- 连续运行 3 天，检查第 2、3 天的创新点字段是否包含对前一日仓库的具名引用
- 人工抽查 10 条难度评定，与 PM 直觉对比，偏差不超过一级（高低判定不得反转）
- 验证 JSON schema 每个字段不为空（除 innovation 首日可标注外）

