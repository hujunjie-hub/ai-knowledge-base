# 003 — 幂等性与重跑

## What to build

确保同日多次运行管道不产生重复数据，支持从指定 Agent 断点重跑，以及瞬态失败自动重试。

### 幂等性

- 运行前检测当日 `knowledge/raw/` 或 `knowledge/articles/` 是否已有数据
- 已有数据时默认跳过（幂等），并发 WARNING 日志说明跳过原因
- 提供 `--force` flag 强制覆盖当日数据（仅当日，历史日期不可覆盖）

### 断点重跑

提供 `--from=<agent>` 参数，跳过前置步骤直接从指定 Agent 启动：

```
python -m pipeline run                # 全流程
python -m pipeline run --from=analyzer    # 从分析开始（前提：raw 已存在）
python -m pipeline run --from=organizer   # 从整理开始（前提：raw + 中间文件已存在）
```

如果前置数据不存在则报错退出（如 `--from=analyzer` 但 `knowledge/raw/` 为空）。

### 自动重试

- 瞬态失败（网络超时、API 503）自动重试 1 次（符合 CLAUDE.md "单次，不回退"）
- 非瞬态失败（schema 校验失败、API 401）不重试，直接记入 errors
- 重试间隔使用指数退避（1s → 2s → 4s，最多 3 次）

### 历史保护

- 历史日期（非今日）的 `knowledge/articles/` 文件不可写入、不可覆盖
- 历史日期重跑直接拒绝，输出 ERROR 并退出

## Acceptance criteria

- [ ] 连续跑两次同日管道（无 --force），第二次输出 WARNING 并跳过，articles 数量不变
- [ ] `--force` 跑当日两次，第二次成功覆盖，articles 数量 = 最新 batch
- [ ] `--from=analyzer` 且 raw 已存在 → 正常从分析启动
- [ ] `--from=analyzer` 且 raw 不存在 → 报错退出，提示先运行 collector
- [ ] 模拟 API 503 → 自动重试成功，日志记录重试次数
- [ ] 模拟 API 401 → 不重试，直接记入 errors
- [ ] 尝试 `--date=2025-01-01` 跑历史日期 → 拒绝，ERROR 退出

## Blocked by

- #001 数据契约 + 管道骨架
