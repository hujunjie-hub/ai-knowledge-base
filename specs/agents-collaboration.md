# AI知识库 · 三个agent协作规范 v0.1

## 总流程
每天 UTC 0:00 触发 · collector -> analyzer -> organizer · 串行。

## Agent职责
- collector:抓取gtihub treding top50 · 过滤AI相关 · 存knowledge/raw/
- analyzer: 读raw · 给每条打 3 维度标签
- organizer: 读已标注 · 整理成MD


## 协作契约（？这里粗略 · 用 to-issues 细化）
- 上游失败下游怎么办？
- 数据怎么传？文件or消息？
- 重跑策略？
- 进度追踪？