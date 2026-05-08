# skill: github-trending · 需求


## 要做什么
- 抓取github.com/trending top 50
- 过滤 repo topics 含ai/llm/agent/ml的
- 输出JSON 数组 · 字段【nam, urll, starts, topics, description】

## 不做什么
- 不调用Github API(rate limit太紧) · 走HTML解析
- 不存数据库 · 只stdout
- 不做去重（只caller处理）

## 边界 & 验收
- 单次执行< 10s
- 失败时返回空数组 · 不抛异常
- 输出必须通过jsonschema验证

## 怎么验证
- 跑 ·skill-invoke github-trending·后检查输出是JSON且字段完整