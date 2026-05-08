# 002 — 失败传播与优雅降级

## What to build

处理上游 Agent 失败时下游 Agent 的行为，确保单点失败不导致整条管道崩溃，最终报告中明确标注所有失败条目。

### 三种失败场景

| 场景 | 下游行为 |
|---|---|
| Collector 全量失败（API 挂了/限流） | Analyzer 和 Organizer 跳过，管道输出 ERROR 级别错误报告，退出码非零 |
| Analyzer 部分条目失败（LLM 超时/返回异常） | 成功条目继续传入 Organizer，失败条目被记录（id + error reason），不阻塞其他条目 |
| Analyzer 全量失败（API key 失效等） | Organizer 跳过，管道输出错误报告，与 Collector 全量失败行为一致 |

### 实现要点

- 每个 Agent 输出结构增加 `errors: list[ItemError]` 字段（`ItemError = { id, error, ts }`）
- 单条目异常用 try/except 包裹，捕获后 `errors.append(...)` 然后 continue
- 全量失败通过 StateGraph 条件边跳过后续节点（检查 `state["errors"]` 是否包含致命错误）
- 最终报告 JSON 包含 `status: success | partial | failed`、各阶段耗时、失败条目明细

## Acceptance criteria

- [ ] 注入 Collector crash（exit 1），验证 Analyzer/Organizer 跳过，退出码非零，ERROR 日志输出
- [ ] 注入 Analyzer 单条 LLM 超时，验证该条进入 errors 列表，其余 9 条正常完成 Organizer
- [ ] 注入 Analyzer 全量失败（全部条目报错），验证 Organizer 跳过，最终报告 status=failed
- [ ] 注入 Organizer 写入磁盘失败，验证前两段数据不丢失（raw + analyzed 已持久化）
- [ ] 最终报告 JSON 包含：status、每个 Agent 的耗时、失败条目 id 列表及原因

## Blocked by

- #001 数据契约 + 管道骨架
