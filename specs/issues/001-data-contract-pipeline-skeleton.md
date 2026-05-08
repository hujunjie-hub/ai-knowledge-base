# 001 — 数据契约 + 管道骨架

## What to build

定义 Collector → Analyzer → Organizer 三个 Agent 间的接口数据契约（Schema），并实现最小 LangGraph StateGraph 骨架将三个 stub Agent 串联起来，确保数据格式在管道各段间正确传递。

### 数据契约

Collector 输出（`knowledge/raw/YYYY-MM-DD.json`）：

```json
[
  {
    "id": "owner/repo",
    "name": "仓库名",
    "url": "https://github.com/owner/repo",
    "description": "GitHub description",
    "stars": 1234,
    "language": "Python",
    "topics": ["llm", "agent"],
    "fetched_at": "2026-05-08T00:00:00Z"
  }
]
```

Analyzer 输出（中间格式，不入库）：

```json
[
  {
    "id": "owner/repo",
    "category": "LLM",
    "innovation": "对比前一日 openai/whisper，新增了流式推理",
    "difficulty": "低",
    "analyzed_at": "2026-05-08T01:00:00Z"
  }
]
```

Organizer 输出 → 合并后写入 `knowledge/articles/{date}-{source}-{slug}.json`（Schema 见 CLAUDE.md Knowledge entry JSON schema）。

### 管道骨架

LangGraph StateGraph，三个节点顺序执行：

```
START → collector → analyzer → organizer → END
```

每个节点目前为 stub，只做 schema 校验 + 数据透传。边界处 schema 校验失败则拒绝，不向后传递。

## Acceptance criteria

- [ ] `knowledge/raw/YYYY-MM-DD.json` schema 已定义为 Pydantic model
- [ ] Analyzer 中间格式 schema 已定义为 Pydantic model
- [ ] StateGraph 三个节点串联，数据在三段间正确传递
- [ ] 边界 schema 校验：无效数据被拒绝，不会传播到下游
- [ ] 空管道端到端跑通（stub Agent 无实际逻辑，仅透传）

## Blocked by

无 — 可立即开始。
