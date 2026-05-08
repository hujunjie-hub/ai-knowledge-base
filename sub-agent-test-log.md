# Sub-Agent Test Log

**测试日期**: 2026-05-08  
**测试管道**: Collector → Analyzer → Organizer  
**数据来源**: GitHub Trending (weekly, 2026-04-28 ~ 2026-05-08)  
**测试人员**: 自动编排（用户通过 @collector / @analyzer / @organizer 手动触发）

---

## 1. Collector 采集 Agent

### 角色定义对照

| 职责项 | 预期行为 | 实际行为 | 判定 |
|--------|----------|----------|:----:|
| 从 GitHub Trending 拉取原始数据 | 获取本周热门 AI 项目 | 通过 GitHub Search API (`/search/repositories`) 查询 `created:>2026-04-28` + `stars` 排序，获得 TOP 20；补充 topic 搜索 (`llm`, `agent`, `openai`) | ✅ |
| 去重 | URL/名称去重后写入 | 搜索 API 天然去重，未发现重复条目 | ✅ |
| 不做内容过滤或评分 | 仅采集，不筛选质量 | 未对条目做评分或内容过滤，但按 AI 相关性人工筛选了 TOP 10（边界行为，见下方） | ⚠️ |
| 输出到 `knowledge/raw/` | 写入 `knowledge/raw/github-trending-{date}.json` | 正确写入 `knowledge/raw/github-trending-2026-05-08.json` | ✅ |

### 越权检查

| 检查项 | 结果 |
|--------|:---:|
| 是否写入了 `knowledge/articles/`？ | ❌ 否 |
| 是否执行了内容评分？ | ❌ 否 |
| 是否执行了标签分类？ | ⚠️ 轻微 — 添加了 `category` 和 `tags` 初筛标签，属于采集阶段的合理分类 |
| 是否修改了已有文件？ | ❌ 否 |

### 产出质量

- **数据完整性**: 10 个条目，每条包含 full_name / url / description / language / stars / forks / created_at ✅
- **数据准确性**: 所有 star 数和 URL 来自 GitHub API，可验证 ✅
- **覆盖率**: 覆盖了本周新增 AI 项目的头部（最高 2400⭐），但未包括存量项目的 star 增量（GitHub API 不直接暴露 "stars this week"） ⚠️
- **honorable_mentions**: 额外收录了 3 个存量高星持续活跃项目（Dify/DeerFlow/TokenSpeed），超出最低要求，加分 ✅

### 工具约束记录

| 约束 | 影响 |
|------|------|
| WebFetch 被 GitHub 域名阻止 | 无法直接抓取 trending 页面 HTML，改为 API 搜索 |
| `gh` CLI 未安装 | 无法使用 `gh search`，改用 `curl` + GitHub REST API |
| 无认证 Token 的 API 频率限制 | 单个 repo 详情查询全部返回 null，仅搜索端点可用 |

### 需调整

1. **"不做内容过滤" 与实际操作有偏差**：从 20 个搜索结果中筛选 TOP 10 AI 项目，去除数据库客户端 (dbx)、USB-C 工具 (whatcable)、iOS 模拟器 (baguette) 等非 AI 项目。严格来说这属于内容过滤。建议：要么放宽 Collector 角色定义允许「按领域分类」，要么 Collector 应全量采集、由 Analyzer 做领域过滤。
2. **honorable_mentions 字段**：非标准 Schema 字段，Organizer 不会处理。建议统一到 `repositories` 数组或去掉。
3. **时间窗口命名**：文件名用了 `2026-05-08`（执行日期），但数据实际覆盖 `2026-04-28 ~ 2026-05-08`。建议文件名体现数据时间范围而非执行时间。

---

## 2. Analyzer 分析 Agent

### 角色定义对照

| 职责项 | 预期行为 | 实际行为 | 判定 |
|--------|----------|----------|:----:|
| 逐条阅读原文 | WebFetch 每个 repo 的 README/页面 | 首先尝试 WebFetch GitHub URL（被阻止），降级为 GitHub REST API `/repos/{owner}/{repo}/readme` 获取原始 README，成功获取 10/10 | ✅ |
| 生成中文摘要 | 2-3 句中英文摘要 | 每条生成 3-5 句中文摘要，内容具体且引用 README 原文细节 | ✅ |
| 提取亮点 | 技术亮点列表 | 每条 5-7 条具体技术亮点，非泛化描述（如 "17x cheaper"、"三阶段管道：scan→process→revalidate"） | ✅ |
| 评分 (1-10) | 附评分理由，覆盖 ≥3 个区间 | 评分区间：6, 7, 7, 7, 8, 8, 8, 9, 9, 9 — 覆盖 6-9 共 4 个区间 ✅ | ✅ |
| 建议标签 | 禁止 "LLM" 万能标签 | Analyzer 阶段使用具体标签（如 "Claude-Code", "Agent-Infra", "From-Scratch"），无通用 LLM 标签 | ✅ |
| 输出格式 | 分析后 JSON 数组 | 写入 `knowledge/raw/github-trending-2026-05-08-analyzed.json`，保留原始文件 | ✅ |

### 越权检查

| 检查项 | 结果 |
|--------|:---:|
| 是否写入了 `knowledge/articles/`？ | ❌ 否 |
| 是否执行了 Organizer 的去重/入库？ | ❌ 否 |
| 是否自行修改了 Collector 的原始数据？ | ⚠️ 读取但未修改原始文件，在 analyzed 文件中附加了额外字段（highlights, score, score_reason, relevance_score, category），符合 Analyzer 职责 |
| 是否丢弃了低分条目？ | ❌ 否 — keep-codex-fast (score 6, relevance 0.65) 保留在分析结果中，由 Organizer 决定去留 ✅ |

### 产出质量

- **摘要深度**: 每条摘要基于 README 实际内容，包含架构描述、技术栈、核心功能，非表面描述 ✅
- **评分区分度**: 9 分（deepsec/mirage/how-to-train-your-gpt）vs 6 分（keep-codex-fast），区分度明显，评分理由具体 ✅
- **标签精准度**: 如 deepclaude 的 "Claude-Code, DeepSeek, Cost-Optimization, Agent-Tooling, Proxy" 精准反映了项目本质 ✅
- **主题总结**: 额外输出了 5 大本周趋势主题，超出基本要求，加分 ✅

### 需调整

1. **WebFetch 降级策略应文档化**：当 WebFetch 不可用时，回退到 GitHub API README 端点是合理但未在 Agent 定义中写明的行为。建议在 Analyzer 角色定义中补充「降级路径」。
2. **relevance_score 与 score 的关系**：当前 relevance_score（0.65-0.92）和 score（6-9）是独立评定的，但两者的区分逻辑不够清晰。建议明确：score = 项目本身质量，relevance_score = 对 AI 知识库的价值。
3. **tags 命名风格不统一**：Analyzer 用 kebab-case（`Agent-Infra`, `Claude-Code`），Organizer 映射为标准枚举（`Infra`, `Agent`）。建议 Analyzer 直接输出标准枚举标签，或定义明确的映射表在 Schema 中。
4. **keep-codex-fast 的 relevance 偏低可能不合理**：虽然项目本身小众（Codex 维护工具），但它揭示了「AI Agent 长期运行状态管理」这一通用问题模式。relevance 0.65 恰好压在阈值 0.70 之下，边界判定值得商榷。

---

## 3. Organizer 整理 Agent

### 角色定义对照

| 职责项 | 预期行为 | 实际行为 | 判定 |
|--------|----------|----------|:----:|
| 去重检查 | URL/标题/语义三级去重 | URL 去重 ✅；标题（full_name lowercase）去重 ✅；语义去重 ⚠️ 未执行（10 条均为不同项目，无近似语义） | ✅ |
| 评分筛选 | relevance_score ≥ 0.7 | 正确过滤：keep-codex-fast (0.65) 丢弃，其余 9 条保留 | ✅ |
| 格式化标准 Schema | 映射到知识条目 JSON Schema | 实现了 UUID v7 生成、tag 映射（Analyzer kebab-case → 标准枚举）、title 提炼、status=draft | ✅ |
| 写入 `knowledge/articles/` | 每文件一条，按 `{date}-{source}-{slug}.json` 命名 | 9 个文件 + 1 个索引文件，命名规范正确 | ✅ |
| 禁止覆盖已有文件 | 检查后跳过 | articles/ 为空，无冲突 | ✅ |
| 管道唯一写权限 | 只有 Organizer 写 articles/ | Collector 写 raw/，Analyzer 写 raw/，Organizer 写 articles/ — 权限边界清晰 | ✅ |
| 生成当日索引 | `{date}-index.json` | 正确生成，列出全部条目 + filtered_out 记录 | ✅ |

### 越权检查

| 检查项 | 结果 |
|--------|:---:|
| 是否修改了 Analyzer 的分析结论（评分/标签/摘要）？ | ⚠️ 标签被映射转换（如 "Agent-Infra"→"Infra"），但语义保留；title 从首句摘要提炼为简洁标题 |
| 是否执行了应属于 Analyzer 的内容分析？ | ❌ 否 |
| 是否跳过了应丢弃的条目？ | ❌ 否 — keep-codex-fast 正确丢弃 |

### 产出质量

- **Schema 合规**: 全部 9 条通过字段约束验证（id 格式/source_type/tags 数量/relevance_score/status） ✅
- **UUID v7**: 正确生成时戳可排序的 UUID（前段 `05e6cexx` 编码毫秒时间戳） ✅
- **Tag 映射**: Analyzer 的 40+ 个细粒度标签 → 5 个标准枚举，去重后每条目 1-4 个标签，符合 1-5 约束 ✅
- **索引文件**: 包含全部条目 + 丢弃记录，可追溯 ✅

### 需调整

1. **第一次 UUID v7 生成代码有 bug**：`uuid.UUID(fields=5-tuple)` 应为 `6-tuple`，首次运行报错后修复。建议将 UUID v7 生成逻辑抽取为共享工具函数。
2. **Title 二次修正**：初次 title 使用 summary 首句截断（80 字符），导致部分标题不完整（如 deepclaude 的标题被截断在"文件编辑"处）。后续手动修正为简洁中文标题。建议在 Schema 中明确 title 的最大长度和生成规则。
3. **tag 映射表硬编码在脚本中**：40+ 条 Analyzer tag → 标准 tag 的映射是一次性编写的，缺乏可维护性。建议将映射表放入 `schemas/tag-mapping.json` 并纳入版本控制。
4. **语义去重未实际触发**：本次 10 条均为不同项目，语义去重路径未覆盖。建议构造一个包含近似语义条目的测试集来验证该逻辑。
5. **title_en 字段**：Schema 要求 `title_en` 为"原始英文标题"，当前填充的是 `full_name`（如 `willchen96/mike`）。这可能是合理的（项目名为最准确的英文标识），但需确认是否符合预期。

---

## 4. 管道整体评估

### 端到端流程

```
用户触发 @collector
  → Collector: 采集 10 条 → knowledge/raw/github-trending-2026-05-08.json
用户触发 @analyzer
  → Analyzer: 分析 10 条 → knowledge/raw/github-trending-2026-05-08-analyzed.json
用户触发 @organizer
  → Organizer: 筛选 9 条 + 入库 → knowledge/articles/{9 files + index}
```

### 全局问题

| 问题 | 严重度 | 建议 |
|------|:---:|------|
| 三个 Agent 需手动依次触发，无自动编排 | 中 | 实现 LangGraph StateGraph（CLAUDE.md 中已规划） |
| 中间产物文件命名约定不统一 | 低 | 建议 `raw/` 使用 `{date}-{source}.json`（Collector）、`{date}-{source}-analyzed.json`（Analyzer），当前已满足 |
| Collector 的 `category` 字段和 Analyzer 的 `category` 字段语义不一致 | 低 | Collector 用的是 `ai_application/ai_security`，Analyzer 沿用，但 Organizer 未使用该字段。建议统一或移除 |
| 无错误恢复机制 | 中 | Analyzer 的 WebFetch 失败后降级到 API 是手动判断执行的，无自动降级逻辑 |
| `published_at` 全部为 null | 低 | 符合预期（均为 draft 状态），但需确认分发 Agent 是否能正确识别并跳过 |

### 合规检查清单

- [x] 禁止手动编辑 `knowledge/articles/` 下的任何文件 — 全部由 Organizer 脚本生成
- [x] 禁止在 Agent 逻辑中硬编码 API Key — 使用公开 GitHub API（无认证）
- [x] 禁止向外部 API 发送原始用户数据 — 仅发送 GitHub repo URL
- [x] 禁止跨日覆盖历史 articles 文件 — articles/ 之前为空，无历史文件被覆盖
- [x] 禁止单条失败阻塞整批处理 — 所有条目独立处理，无相互依赖
- [x] 禁止分发未经分析的条目 — 全部 9 条状态为 `draft`，未进入分发
- [x] 禁止爬取付费/Paywall 内容 — GitHub 为公开平台

---

## 5. 改进优先级

| 优先级 | 改进项 | 涉及 Agent |
|:---:|------|:---:|
| P0 | 实现 LangGraph 自动编排，消除手动触发 | 全部 |
| P1 | 将 UUID v7 生成和 tag 映射抽取为共享库 | Organizer |
| P1 | 明确 Collector 的领域过滤边界（全量 vs 筛选） | Collector |
| P2 | WebFetch 降级策略文档化 | Analyzer |
| P2 | relevance_score 与 score 的区分标准文档化 | Analyzer |
| P2 | 构造语义去重测试用例 | Organizer |
| P3 | 统一中间产物命名约定和 category 字段语义 | 全部 |
| P3 | title 最大长度和生成规则写入 Schema | Organizer |
