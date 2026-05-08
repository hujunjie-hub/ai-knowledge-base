# 004 — 进度追踪与可观测性

## What to build

提供管道运行时的结构化进度日志和运行后的状态查询能力，确保在任何时间点都能了解管道的执行状态。

### 结构化日志

每个 Agent 阶段必须输出以下 JSON 日志（符合 coding-standards 第 5 节）：

```json
{"ts": "...", "level": "INFO", "agent": "Collector", "phase": "start", "msg": "collector phase start", "n_items": 0}
{"ts": "...", "level": "INFO", "agent": "Collector", "phase": "end", "msg": "collector phase complete", "elapsed_ms": 2312, "n_items": 10}
```

每个 Agent 必须在阶段开始和结束时分别输出日志，包含 `agent`、`phase`（start/end）、`elapsed_ms`、`n_items`。阶段内每处理一条条目输出 DEBUG 级别日志。

### CLI 状态查询

提供 `pipeline status` 子命令：

```
$ pipeline status --date 2026-05-08
Collector   completed │ 10 items │ 2.3s
Analyzer    completed │ 10 items │ 45.2s
Organizer   completed │ 8 items  │ 1.1s
Status: partial (2 items failed, see report)
```

```
$ pipeline status --date 2026-05-08
Collector   failed   │ API rate limit exceeded
Analyzer    skipped
Organizer   skipped
Status: failed
```

状态数据来源：当日管道运行的最终报告 JSON（由 #002 生成）。

### 错误聚合

管道全部失败时，状态输出中标注 `status: failed`，并列出每个 Agent 的失败原因。当天有 WARNING 级别日志时，`pipeline status` 末尾附警告计数。

## Acceptance criteria

- [ ] 管道运行后在日志中看到 6 条 INFO 日志（3 个 Agent × start + end）
- [ ] `pipeline status --date 2026-05-08` 显示三个 Agent 各自状态、处理条目数、耗时
- [ ] 故意让 Collector 失败 → `pipeline status` 显示 `collector: failed, analyzer: skipped, organizer: skipped`
- [ ] Analyzer 部分条目失败 → status 显示 `partial`，标注失败条目数
- [ ] 日志全部为 JSON Lines 格式，可通过 `jq` 解析

## Blocked by

- #001 数据契约 + 管道骨架
