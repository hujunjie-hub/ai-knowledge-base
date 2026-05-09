"""MCP Server for AI Knowledge Base search over stdio (JSON-RPC 2.0).

Reads knowledge/articles/ JSON files and exposes search_articles, get_article,
and knowledge_stats tools via the Model Context Protocol.
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger("mcp_knowledge_server")
logger.setLevel(logging.INFO)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_stderr_handler)

ARTICLES_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "articles"

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------


def _write_response(id_: int | str | None, result: Any) -> None:
    """Write a JSON-RPC success response to stdout."""
    payload = {"jsonrpc": "2.0", "id": id_, "result": result}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _write_error(id_: int | str | None, code: int, message: str) -> None:
    """Write a JSON-RPC error response to stdout."""
    payload = {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Article loading
# ---------------------------------------------------------------------------


def _load_articles() -> list[dict[str, Any]]:
    """Load all article JSON files from the knowledge/articles directory.

    Skips index files (files ending in -index.json) and non-JSON files.
    """
    if not ARTICLES_DIR.is_dir():
        logger.error("articles directory not found: %s", ARTICLES_DIR)
        return []
    articles: list[dict[str, Any]] = []
    for filepath in sorted(ARTICLES_DIR.glob("*.json")):
        if filepath.name.endswith("-index.json"):
            continue
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "id" in data:
                articles.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("failed to load %s: %s", filepath.name, exc)
    logger.info("loaded %d articles", len(articles))
    return articles


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _search_articles(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search articles by keyword in title, title_en, and summary fields."""
    articles = _load_articles()
    keyword_lower = keyword.lower()
    matches: list[tuple[int, dict[str, Any]]] = []

    for article in articles:
        score = 0
        title = article.get("title", "")
        title_en = article.get("title_en", "")
        summary = article.get("summary", "")

        if keyword_lower in title.lower():
            score += 3
        if keyword_lower in title_en.lower():
            score += 2
        if keyword_lower in summary.lower():
            score += 1

        if score > 0:
            matches.append((score, article))

    matches.sort(key=lambda x: x[0], reverse=True)
    results = matches[:limit]

    return [
        {
            "id": a["id"],
            "title": a.get("title", ""),
            "title_en": a.get("title_en", ""),
            "source_type": a.get("source_type", ""),
            "summary": a.get("summary", ""),
            "tags": a.get("tags", []),
            "relevance_score": a.get("relevance_score"),
            "status": a.get("status", ""),
        }
        for _, a in results
    ]


def _get_article(article_id: str) -> dict[str, Any] | None:
    """Get full article content by ID."""
    articles = _load_articles()
    for article in articles:
        if article.get("id") == article_id:
            return article
    return None


def _knowledge_stats() -> dict[str, Any]:
    """Compute knowledge base statistics."""
    articles = _load_articles()
    total = len(articles)

    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for a in articles:
        source_counter[a.get("source_type", "unknown")] += 1
        status_counter[a.get("status", "unknown")] += 1
        for tag in a.get("tags", []):
            tag_counter[tag] += 1

    return {
        "total_articles": total,
        "by_source": dict(source_counter.most_common()),
        "by_status": dict(status_counter),
        "top_tags": dict(tag_counter.most_common(10)),
    }


# ---------------------------------------------------------------------------
# MCP protocol handlers
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_articles",
        "description": "按关键词搜索知识库文章标题、英文标题和摘要，返回匹配结果列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认 5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容，包含全部字段",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章唯一标识符 (UUID v7)",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "返回知识库统计信息：文章总数、来源分布、状态分布、热门标签",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _handle_initialize(id_: int | str | None, params: dict[str, Any]) -> None:
    protocol_version = params.get("protocolVersion", "2024-11-05")
    _write_response(id_, {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "mcp-knowledge-server",
            "version": "0.1.0",
        },
    })


def _handle_tools_list(id_: int | str | None) -> None:
    _write_response(id_, {"tools": TOOLS})


def _handle_tools_call(id_: int | str | None, params: dict[str, Any]) -> None:
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name == "search_articles":
        keyword = arguments.get("keyword", "")
        limit = arguments.get("limit", 5)
        result = _search_articles(keyword, limit)
    elif tool_name == "get_article":
        article_id = arguments.get("article_id", "")
        article = _get_article(article_id)
        if article is None:
            _write_error(id_, -32000, f"article not found: {article_id}")
            return
        result = article
    elif tool_name == "knowledge_stats":
        result = _knowledge_stats()
    else:
        _write_error(id_, -32601, f"unknown tool: {tool_name}")
        return

    _write_response(id_, {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2),
            }
        ]
    })


METHOD_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP JSON-RPC loop on stdin/stdout."""
    logger.info("mcp_knowledge_server starting, articles_dir=%s", ARTICLES_DIR)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.error("invalid JSON: %s", exc)
            continue

        req_id = request.get("id")
        method = request.get("method", "")

        if method not in METHOD_HANDLERS:
            _write_error(req_id, -32601, f"method not found: {method}")
            continue

        try:
            handler = METHOD_HANDLERS[method]
            if method == "initialize":
                handler(req_id, request.get("params", {}))
            elif method == "tools/call":
                handler(req_id, request.get("params", {}))
            else:
                handler(req_id)
        except Exception as exc:
            logger.exception("handler error for method=%s", method)
            _write_error(req_id, -32603, str(exc))


if __name__ == "__main__":
    main()
