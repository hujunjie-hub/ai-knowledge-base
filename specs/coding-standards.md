# Coding Standards

本文件是 AI 知识库项目的编码规范正文。所有规范变更必须通过补丁文件流程提出，不得直接修改本文件。

---

## 1. Python 版本

- **下限 3.12，上限 3.12** — 本项目以 Python 3.12 为唯一目标版本，不接受 3.13+ 语法。
- `pyproject.toml` 中 `requires-python = "==3.12.*"`。
- CI 使用 Python 3.12.x 最新补丁版本。

---

## 2. 代码风格

### 2.1 基础

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)。
- **行宽 99 字符** — 与 PEP 8 推荐的 docstring/注释宽度一致。
- 缩进 4 空格，禁止 tab。
- 文件末尾必须有且仅有一个换行符。

### 2.2 命名

| 对象 | 风格 | 示例 |
|------|------|------|
| 变量 | `snake_case` | `relevance_score` |
| 函数 | `snake_case` | `fetch_github_trending()` |
| 类 | `PascalCase` | `CollectorAgent` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| 私有成员 | 单下划线前缀 | `_validate_schema()` |
| 文件名 | `snake_case` | `github_fetcher.py` |

### 2.3 import 顺序

标准库 → 第三方库 → 本地模块，每组间空一行。本地模块使用相对导入。

```python
# 标准库
import asyncio
from datetime import datetime, timezone

# 第三方库
import httpx
from pydantic import BaseModel

# 本地模块
from .collector import collect_github
```

**强制执行**：CI 中运行 `isort --check-only --profile=black .`，不通过则构建失败。

---

## 3. 类型注解

### 3.1 规则

- 所有公共函数/方法签名必须包含类型注解。
- 使用 `mypy` 做类型检查，CI 零错误通过。
- 不允许使用 `Any` 除非有充分理由（需 PR 中注释说明）。

### 3.2 mypy 配置

以下 flag 在 `pyproject.toml` 中开启：

**必开（缺了等于没开）：**

```ini
[tool.mypy]
disallow_untyped_defs = true      # 函数缺注解直接报错
warn_return_any = true            # 返回值推断为 Any 时报 warning
warn_unused_ignores = true        # 没必要的 # type: ignore 报错
```

**建议开（收益大、噪音低）：**

```ini
disallow_incomplete_defs = true   # 部分参数有注解部分没有也报
check_untyped_defs = true         # 未注解函数内部仍做类型推断
warn_redundant_casts = true       # 不必要的 cast() 报警
```

---

## 4. Docstring

### 4.1 格式

采用 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) docstring 格式。所有公共函数/类必须有 docstring。

### 4.2 类型声明规则

**函数签名上的类型注解是权威来源**。`Args:` / `Returns:` 段仅描述语义含义，不重复声明类型。

```python
# ✅ 正确 — 类型只在签名上声明
def analyze_item(raw: RawEntry, prior_day: list[Article] | None) -> Article:
    """对一条原始采集条目执行分析。

    Args:
        raw: 来自 Collector 的原始数据。
        prior_day: 前一日 articles 列表，首日运行时为 None。

    Returns:
        填充了 category、tags、summary 字段的 Article，status 为 reviewed。
    """
```

```python
# ❌ 错误 — Args 段重复声明类型
def analyze_item(raw: RawEntry, prior_day: list[Article] | None) -> Article:
    """...

    Args:
        raw (RawEntry): 原始数据。  # 不要这样写
    """
```

### 4.3 内部函数与私有方法

仅对逻辑不明显的非公共函数加 docstring。一目了然的单行工具函数可省略。

---

## 5. 日志

### 5.1 规则

- **禁止裸 `print()`** — 使用 `ruff` 规则 `T201` 在 CI 中拦截。
- **禁止裸 `except:`** — 异常捕获必须指定异常类型。

### 5.2 日志格式

所有日志输出为 JSON Lines（每行一个 JSON 对象），使用 `python-json-logger` formatter。

固定顶层键：

| 键 | 必填 | 说明 |
|----|------|------|
| `ts` | 是 | ISO 8601 时间戳，UTC |
| `level` | 是 | INFO / WARNING / ERROR / DEBUG |
| `agent` | 是 | 产生日志的 Agent 名称 |
| `msg` | 是 | 人类可读的日志消息 |

其余字段可自由附加，但键名必须 snake_case。

```json
{"ts": "2026-05-08T01:01:23.456Z", "level": "INFO", "agent": "Collector", "msg": "fetching github trending page 1", "elapsed_ms": 312, "n_items": 25}
```

### 5.3 级别定义

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| **ERROR** | 单条目处理失败、API 超时、Schema 校验不通过 | `"hn api returned 503 after 3 retries"` |
| **WARNING** | 可恢复异常 — 单条目跳过、relevance 低于阈值被丢弃 | `"item summarization failed, skipping"` |
| **INFO** | 管道里程碑 — 阶段开始/结束、处理条目数、分发结果 | `"analyzer phase complete, 8/10 items reviewed"` |
| **DEBUG** | Agent 推理细节、prompt/response 摘要、去重判断依据 | `"comparing with prior day item openai/whisper-large-v3"` |

`LOG_LEVEL` 环境变量控制级别，默认 `INFO`。DEBUG 仅在排查时手动开启。

---

## 6. 依赖管理

### 6.1 工具

使用 `uv` 管理依赖。

- `pyproject.toml` 声明项目元数据与依赖。
- `uv.lock` 锁定所有传递依赖的精确版本，**必须进版本控制**。
- 添加依赖：`uv add <package>`。
- CI 安装：`uv sync --frozen`（严格按 lock 文件安装，不更新）。

### 6.2 依赖分类

- **生产依赖**：Agent 运行时必需（LangGraph、httpx、pydantic、python-json-logger 等）。
- **开发依赖**：测试、lint、类型检查（pytest、ruff、mypy、isort）。

---

## 7. 异步编程

### 7.1 规则

- **允许混用异步和同步代码**。
- **async 上下文中禁止同步阻塞调用**。以下调用在协程中出现即为违规：
  - `time.sleep()` — 必须使用 `await asyncio.sleep()`
  - `requests.get()` — 必须使用 `httpx.AsyncClient` 或同类异步 HTTP 库
  - 任何不带 `await` 的阻塞 I/O
- 使用 `ruff` 规则 `ASYNC` 系列辅助检测（`ASYNC100`、`ASYNC101` 等）。

---

## 8. 测试

### 8.1 框架

`pytest`。CI 中 `python -m pytest` 必须全部通过。

### 8.2 覆盖率

按代码层级分层控制，使用 `pytest-cov` 测量：

| 层 | 路径 | 覆盖率要求 | 说明 |
|-----|------|-----------|------|
| 业务逻辑 | `schemas/`、`pipeline/` 中的纯逻辑模块 | ≥90% | JSON Schema 验证、status 流转、数据转换、去重判断 |
| 工具层 | `pipeline/` 中的工具函数、配置加载 | ≥80% | API 调用封装、序列化、配置读取 |
| 边界适配 | 渠道分发适配器 | ≥50% | Telegram/飞书消息格式化、Webhook 适配 |
| LLM 调用 | `agents/*_llm.py` | 不计入 | LLM 输出本质不确定，硬凑用例产出假绿 |

- CI 中任一层低于阈值，构建直接失败。
- 覆盖率报告以 `pytest-cov` 的 branch coverage 为准。

---

## 9. 环境变量

### 9.1 命名格式

```
{SERVICE}_{FIELD}
```

- 全大写 `UPPER_SNAKE_CASE`。
- `SERVICE` 表示外部服务名（GITHUB、TELEGRAM、ANTHROPIC 等）。
- `FIELD` 限定使用以下四种后缀：

| 后缀 | 含义 | 示例 |
|------|------|------|
| `API_KEY` | API 密钥 | `ANTHROPIC_API_KEY` |
| `TOKEN` | 访问令牌（GitHub 官方命名为 Token，沿用） | `GITHUB_TOKEN` |
| `BASE_URL` | 自定义 API endpoint | `DEEPSEEK_BASE_URL` |
| `WEBHOOK_URL` | Webhook 回调地址 | `FEISHU_WEBHOOK_URL` |

### 9.2 完整清单

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `GITHUB_TOKEN` | GitHub API 访问 | `ghp_xxx` |
| `ANTHROPIC_API_KEY` | Claude API | `sk-ant-xxx` |
| `QWEN_API_KEY` | 通义千问 API | - |
| `QWEN_BASE_URL` | 通义千问 endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API | - |
| `DEEPSEEK_BASE_URL` | DeepSeek endpoint | `https://api.deepseek.com/v1` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot | `123:abc` |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook | `https://open.feishu.cn/...` |
| `LOG_LEVEL` | 日志级别（可选，默认 INFO） | `DEBUG` |

### 9.3 可发现性

项目根目录必须提供 `.env.example` 文件，列出所有必需的环境变量及其说明，按服务分区注释。任何 clone 后 `cp .env.example .env` 即可获取完整清单。

### 9.4 加载方式

Agent 代码中禁止硬编码任何密钥或 URL。统一通过 `os.getenv()` 或 `pydantic-settings` 加载。

---

## 10. 规范治理

### 10.1 变更流程

本规范的修改必须走补丁文件流程，不得直接编辑此文件：

1. **提出** — 在 `specs/` 下新建 `YYYY-MM-DD-<简短描述>.md` 补丁文件，说明：
   - 改什么（具体条款）
   - 为什么（动机与背景）
   - 影响范围（哪些文件/流程受影响）
2. **评审** — 至少一人 review 通过。
3. **落地** — 补丁内容吸纳进本文件正文相应章节。
4. **归档** — 补丁文件保留不删除，形成可追溯的决策日志。

### 10.2 补丁文件模板

临时需要时再写——本条本身是规范，不提前提供模板。

---

## 11. 工具配置汇总

CI 流水线必须执行的检查（失败则阻塞合并）：

| 检查项 | 工具 | 命令/配置 |
|--------|------|-----------|
| 类型检查 | mypy | `mypy .`（6 个 flag 全开） |
| 代码风格 | ruff | `ruff check .`（含 T201、ASYNC 规则集） |
| import 顺序 | isort | `isort --check-only --profile=black .` |
| 测试 | pytest | `python -m pytest --cov --cov-branch --cov-fail-under=... ` |

各工具的具体配置写入 `pyproject.toml`，不在本文件中重复。
