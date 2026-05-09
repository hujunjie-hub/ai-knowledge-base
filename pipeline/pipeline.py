#!/usr/bin/env python3
"""Four-step knowledge base automation pipeline: Collect -> Analyze -> Organize -> Save."""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import logging
import os
import re
import sys
import time as _time
import uuid as _uuid
from pathlib import Path
from typing import Any

import httpx
import yaml

# Make model_client importable from the same directory as requested.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_client import LLMProvider, chat_with_retry, create_provider  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
RSS_SOURCES_PATH = Path(__file__).resolve().parent / "rss_sources.yaml"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_TAGS = frozenset({"LLM", "Agent", "Infra", "Tool", "Paper"})
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_SEARCH_QUERY = "AI OR LLM OR agent OR ML OR machine learning"
MIN_RELEVANCE_SCORE = 0.7
TZ_SHANGHAI = _dt.timezone(_dt.timedelta(hours=8))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class _JSONFormatter(logging.Formatter):
    """Simple JSON-line formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return json.dumps(
            {"ts": ts, "level": record.levelname, "agent": "pipeline", "msg": record.getMessage()},
            ensure_ascii=False,
        )


logger = logging.getLogger("pipeline")


def setup_logging(verbose: bool = False) -> None:
    """Configure pipeline-wide logging.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JSONFormatter())
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False


# ---------------------------------------------------------------------------
# UUID v7 (timestamp-ordered)
# ---------------------------------------------------------------------------


def uuid7() -> str:
    """Generate a UUID v7 string from the current timestamp and random bits.

    Layout (RFC 9562): 48-bit Unix ms timestamp | 4-bit version=7 |
    12-bit rand_a | 2-bit variant=2 | 62-bit rand_b.
    """
    ms = int(_time.time() * 1000)
    rand_bytes = os.urandom(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    # 12-bit rand_a from top of random, 62-bit rand_b from bottom
    rand_a = (rand_int >> 68) & 0xFFF
    rand_b = rand_int & 0x3FFFFFFFFFFFFFFF
    return str(_uuid.UUID(fields=(
        (ms >> 16) & 0xFFFFFFFF,
        ms & 0xFFFF,
        0x7000 | rand_a,
        0x80 | ((rand_b >> 56) & 0x3F),
        (rand_b >> 48) & 0xFF,
        rand_b & 0xFFFFFFFFFFFF,
    )))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC+8 time as ISO 8601 string."""
    return _dt.datetime.now(TZ_SHANGHAI).isoformat(timespec="seconds")


def _today_str() -> str:
    """Return today's date string in UTC+8, e.g. '2026-05-09'."""
    return _dt.datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d")


def _make_slug(source_type: str, title_en: str, source_url: str) -> str:
    """Derive a safe filename slug from source metadata.

    Args:
        source_type: The source type of the item.
        title_en: English title or repo name.
        source_url: Source URL used as fallback.

    Returns:
        A lowercased, hyphen-separated slug string.
    """
    if source_type == "github_trending":
        # Extract owner/repo from URL and replace / with -
        m = re.search(r"github\.com/([^/]+/[^/]+)", source_url)
        if m:
            return m.group(1).replace("/", "-").lower()
    # For RSS / other: use title, cleaning it up
    slug = title_en.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] if len(slug) > 80 else slug


def _load_rss_sources() -> list[dict[str, Any]]:
    """Load enabled RSS sources from config YAML.

    Returns:
        List of source dicts with name, url, category keys.
    """
    if not RSS_SOURCES_PATH.exists():
        logger.warning("RSS sources config not found: %s", RSS_SOURCES_PATH)
        return []
    with open(RSS_SOURCES_PATH, encoding="utf-8") as fh:
        config: dict[str, Any] = yaml.safe_load(fh)
    sources: list[dict[str, Any]] = config.get("sources", [])
    enabled = [s for s in sources if s.get("enabled", False)]
    logger.info("loaded %d RSS sources (%d enabled)", len(sources), len(enabled))
    return enabled


# ---------------------------------------------------------------------------
# Step 1: Collect
# ---------------------------------------------------------------------------


async def _collect_github(client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
    """Collect repositories from the GitHub Search API.

    Args:
        client: Shared httpx async client.
        limit: Maximum number of results to return.

    Returns:
        List of raw repository dicts with keys: name, url, description, stars,
        topics, language, created_at.
    """
    token = os.getenv("GITHUB_TOKEN", "")
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params: dict[str, Any] = {
        "q": GITHUB_SEARCH_QUERY,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    }

    logger.info(
        "fetching GitHub search: q=%s per_page=%d", GITHUB_SEARCH_QUERY, params["per_page"]
    )
    try:
        resp = await client.get(
            GITHUB_SEARCH_URL, headers=headers, params=params, timeout=30.0
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("GitHub search API failed: %s", exc)
        return []

    items: list[dict[str, Any]] = []
    for repo in data.get("items", []):
        items.append({
            "name": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "description": repo.get("description") or "",
            "stars": repo.get("stargazers_count", 0),
            "topics": repo.get("topics", []),
            "language": repo.get("language") or "",
            "created_at": repo.get("created_at", ""),
        })
        if len(items) >= limit:
            break

    logger.info("collected %d repos from GitHub search", len(items))
    return items


async def _collect_rss_single(
    client: httpx.AsyncClient, source: dict[str, Any], limit: int
) -> list[dict[str, Any]]:
    """Collect items from a single RSS feed.

    Args:
        client: Shared httpx async client.
        source: RSS source config dict with name, url, category.
        limit: Max items from this source.

    Returns:
        List of raw item dicts with keys: title, url, description, source_name,
        source_category.
    """
    name: str = source["name"]
    url: str = source["url"]
    category: str = source.get("category", "")

    logger.info("fetching RSS: %s (%s)", name, url)
    try:
        resp = await client.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        xml_text = resp.text
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("RSS fetch failed for %s: %s", name, exc)
        return []

    # Simple regex RSS item parsing
    items: list[dict[str, Any]] = []
    item_blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    if not item_blocks:
        # Some feeds use <entry> instead (Atom)
        item_blocks = re.findall(r"<entry>(.*?)</entry>", xml_text, re.DOTALL)

    for block in item_blocks:
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
        link_m = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.DOTALL)
        if not link_m:
            link_m = re.search(r'<link[^>]*href="([^"]*)"', block)
        desc_m = re.search(
            r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", block, re.DOTALL
        )

        title = title_m.group(1).strip() if title_m else ""
        link = link_m.group(1).strip() if link_m else ""
        description = desc_m.group(1).strip() if desc_m else ""

        # Clean HTML tags from description
        description = re.sub(r"<[^>]+>", " ", description).strip()
        description = re.sub(r"\s+", " ", description)

        if not link:
            continue

        items.append({
            "title": title,
            "url": link,
            "description": description[:500] if description else "",
            "source_name": name,
            "source_category": category,
        })
        if len(items) >= limit:
            break

    logger.info("collected %d items from RSS: %s", len(items), name)
    return items


def _rss_source_type(source: dict[str, Any]) -> str:
    """Map an RSS source to its source_type.

    Args:
        source: RSS source config dict.

    Returns:
        ``hacker_news`` for HN-derived feeds, ``rss`` otherwise.
    """
    name: str = source.get("name", "").lower()
    if "hacker news" in name or "hn" in name.split():
        return "hacker_news"
    return "rss"


async def step_collect(
    client: httpx.AsyncClient,
    sources: list[str],
    limit: int,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Step 1: Collect raw items from configured sources.

    Args:
        client: Shared httpx async client.
        sources: List of source identifiers (``github``, ``rss``).
        limit: Max items per source.
        dry_run: If True, log intent but skip actual requests.

    Returns:
        Unified list of raw item dicts, each annotated with ``_source_type``.
    """
    all_items: list[dict[str, Any]] = []

    if "github" in sources:
        if dry_run:
            logger.info("DRY-RUN: would collect up to %d repos from GitHub Search", limit)
        else:
            repos = await _collect_github(client, limit)
            for repo in repos:
                repo["_source_type"] = "github_trending"
            all_items.extend(repos)

    if "rss" in sources:
        rss_sources = _load_rss_sources()
        if dry_run:
            src_names = [s["name"] for s in rss_sources]
            logger.info("DRY-RUN: would collect up to %d items each from %d RSS sources: %s",
                        limit, len(rss_sources), src_names)
        else:
            for src in rss_sources:
                items = await _collect_rss_single(client, src, limit)
                st = _rss_source_type(src)
                for item in items:
                    item["_source_type"] = st
                all_items.extend(items)

    logger.info("Step 1 Collect complete: %d total items", len(all_items))
    return all_items


# ---------------------------------------------------------------------------
# Step 2: Analyze
# ---------------------------------------------------------------------------


_ANALYSIS_SYSTEM_PROMPT = """\
You are an AI technology content analyst. Analyze the given technical item
and return a JSON object.

Required fields:
- title: Chinese title translation (concise and accurate)
- title_en: English title (preserve original if already English, or translate)
- summary: 2-3 sentence bilingual (zh/en) summary with specific technical details
- relevance_score: float 0.0-1.0 rating relevance to AI/LLM/Agent/ML topics
- tags: array of 1-5 tags chosen ONLY from: LLM, Agent, Infra, Tool, Paper

Scoring guide:
- 0.9-1.0: Core AI/LLM/Agent innovation or research
- 0.7-0.9: Directly related tooling, framework, or application
- 0.5-0.7: Tangentially related (uses AI but not about AI)
- 0.0-0.5: Not AI-relevant

Return ONLY valid JSON, no markdown fences, no extra commentary.
{"title":"AI助手","title_en":"AI Tool","summary":"A tool.","relevance_score":0.85,"tags":["Agent"]}
"""


def _build_analysis_user_prompt(item: dict[str, Any]) -> str:
    """Build a user prompt for LLM analysis from a raw item.

    Args:
        item: Raw collected item dict.

    Returns:
        A string prompt describing the item to analyze.
    """
    source_type = item.get("_source_type", "unknown")
    if source_type == "github_trending":
        return (
            f"Analyze this GitHub repository:\n"
            f"Name: {item.get('name', '')}\n"
            f"Description: {item.get('description', '')}\n"
            f"Topics: {', '.join(item.get('topics', []))}\n"
            f"Language: {item.get('language', '')}\n"
            f"Stars: {item.get('stars', 0)}\n"
            f"URL: {item.get('url', '')}"
        )
    else:
        return (
            f"Analyze this article:\n"
            f"Title: {item.get('title', '')}\n"
            f"Description: {item.get('description', '')}\n"
            f"Source: {item.get('source_name', '')}\n"
            f"URL: {item.get('url', '')}"
        )


def _parse_llm_json(raw_text: str) -> dict[str, Any] | None:
    """Extract and parse a JSON object from LLM output.

    Handles markdown code fences and trailing noise.

    Args:
        raw_text: Raw LLM response text.

    Returns:
        Parsed dict, or None if parsing fails.
    """
    text = raw_text.strip()
    # Strip markdown code fences if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Find first { ... } pair
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    end = start
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    try:
        return json.loads(text[start:end])  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return None


def _dry_run_analysis(item: dict[str, Any]) -> dict[str, Any]:
    """Generate a placeholder analysis for dry-run mode.

    Args:
        item: Raw collected item dict.

    Returns:
        Synthetic analysis result dict.
    """
    source_type = item.get("_source_type", "unknown")
    if source_type == "github_trending":
        title_en = item.get("name", "")
        title_cn = item.get("description", title_en)[:40]
        return {
            "title": title_cn or title_en,
            "title_en": title_en,
            "summary": (
                f"[DRY-RUN] GitHub repo {item.get('name')}: {item.get('description')}"
            ),
            "relevance_score": 0.80,
            "tags": ["Tool"],
        }
    else:
        title_en = item.get("title", "")
        return {
            "title": title_en,
            "title_en": title_en,
            "summary": (
                f"[DRY-RUN] Article from {item.get('source_name')}: "
                f"{item.get('description')}"
            ),
            "relevance_score": 0.75,
            "tags": ["Paper"],
        }


async def step_analyze(
    provider: LLMProvider,
    items: list[dict[str, Any]],
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Step 2: Analyze each item via LLM for summary, score, and tags.

    Single-item failures are logged and skipped; the rest continue.

    Args:
        provider: Configured LLM provider instance.
        items: Raw collected items from Step 1.
        dry_run: If True, generate placeholder results without calling LLM.

    Returns:
        List of merged dicts (raw item + analysis fields).
    """
    analyzed: list[dict[str, Any]] = []
    total = len(items)

    for idx, item in enumerate(items):
        item_desc = item.get("url") or item.get("title") or f"item #{idx}"
        logger.info("analyzing %d/%d: %s", idx + 1, total, item_desc)

        if dry_run:
            analysis = _dry_run_analysis(item)
        else:
            try:
                user_prompt = _build_analysis_user_prompt(item)
                response = await chat_with_retry(
                    provider,
                    [
                        {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                    timeout=60.0,
                )
                parsed = _parse_llm_json(response.content)
                if parsed is None:
                    logger.warning("failed to parse LLM JSON for %s: %s", item_desc,
                                   response.content[:200])
                    continue
                analysis = parsed
            except Exception as exc:
                logger.error("LLM analysis failed for %s: %s", item_desc, exc)
                continue

        # Merge raw item with analysis
        merged: dict[str, Any] = {**item, **analysis}
        analyzed.append(merged)
        # Brief pause to avoid rate limits
        if not dry_run and idx < total - 1:
            await asyncio.sleep(0.5)

    logger.info("Step 2 Analyze complete: %d/%d items analyzed", len(analyzed), total)
    return analyzed


# ---------------------------------------------------------------------------
# Step 3: Organize
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """Normalize a string for comparison: lowercased, whitespace-collapsed."""
    return re.sub(r"\s+", " ", s.lower()).strip()


def step_organize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Step 3: Deduplicate, validate, and filter analyzed items.

    Processing order:
    1. URL-based dedup (exact match)
    2. Title-based dedup (normalized match)
    3. Validate required fields and tag constraints
    4. Filter by minimum relevance score

    Args:
        items: Analyzed items from Step 2 (raw + analysis merged).

    Returns:
        List of clean, validated, deduplicated article dicts.
    """
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    organized: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for item in items:
        url = item.get("url", "")
        title_en = item.get("title_en", item.get("name", item.get("title", "")))
        title_norm = _normalize(title_en)

        # URL dedup
        if url and url in seen_urls:
            logger.debug("dedup (url): %s", url)
            continue
        # Title dedup
        if title_norm and title_norm in seen_titles:
            logger.debug("dedup (title): %s", title_en)
            continue

        # Validate tags
        tags: list[str] = item.get("tags", [])
        # Filter to allowed tags only, deduplicate
        clean_tags: list[str] = list(dict.fromkeys(t for t in tags if t in ALLOWED_TAGS))
        if not clean_tags:
            clean_tags = ["Tool"]  # default fallback
        if len(clean_tags) > 5:
            clean_tags = clean_tags[:5]
        item["tags"] = clean_tags

        # Validate relevance_score
        score = item.get("relevance_score", 0)
        if not isinstance(score, (int, float)) or score < MIN_RELEVANCE_SCORE:
            logger.info("filtered (score %.2f < %.2f): %s", score, MIN_RELEVANCE_SCORE, title_en)
            reason = f"relevance_score {score} < {MIN_RELEVANCE_SCORE}"
            rejected.append({"title": title_en, "reason": reason})
            continue

        # Clamp score to [0.0, 1.0]
        item["relevance_score"] = round(max(0.0, min(1.0, float(score))), 2)

        # Validate source_type
        source_type = item.get("_source_type", "rss")
        item["source_type"] = source_type

        if url:
            seen_urls.add(url)
        if title_norm:
            seen_titles.add(title_norm)
        organized.append(item)

    logger.info(
        "Step 3 Organize complete: %d kept, %d filtered (from %d input)",
        len(organized), len(rejected), len(items),
    )
    return organized


# ---------------------------------------------------------------------------
# Step 4: Save
# ---------------------------------------------------------------------------


def step_save(items: list[dict[str, Any]], dry_run: bool = False) -> int:
    """Step 4: Save articles as individual JSON files and a daily index.

    Args:
        items: Organized article dicts from Step 3.
        dry_run: If True, log intent but skip file writes.

    Returns:
        Number of articles saved.
    """
    today = _today_str()
    now_iso = _now_iso()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    saved = 0
    index_entries: list[dict[str, Any]] = []
    filtered_out: list[dict[str, str]] = []

    for item in items:
        source_type: str = item.get("source_type", "rss")
        title_en: str = item.get("title_en", item.get("name", item.get("title", "")))
        source_url: str = item.get("url", "")
        slug = _make_slug(source_type, title_en, source_url)
        if not slug:
            slug = uuid7()[:8]

        filename = f"{today}-{source_type}-{slug}.json"
        filepath = ARTICLES_DIR / filename

        if filepath.exists():
            logger.warning("article file already exists, skipping: %s", filename)
            continue

        article: dict[str, Any] = {
            "id": uuid7(),
            "title": item.get("title", title_en),
            "title_en": title_en,
            "source_url": source_url,
            "source_type": source_type,
            "summary": item.get("summary", ""),
            "tags": item.get("tags", []),
            "relevance_score": item.get("relevance_score", 0.0),
            "status": "draft",
            "fetched_at": now_iso,
            "analyzed_at": now_iso,
            "published_at": None,
        }

        if dry_run:
            logger.info("DRY-RUN: would save %s", filename)
        else:
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(article, fh, ensure_ascii=False, indent=2)
            logger.info("saved article: %s", filename)

        index_entries.append({
            "filename": filename,
            "id": article["id"],
            "title": article["title"],
            "title_en": article["title_en"],
            "relevance_score": article["relevance_score"],
            "tags": article["tags"],
        })
        saved += 1

    # Write daily index
    index_path = ARTICLES_DIR / f"{today}-index.json"
    index_data: dict[str, Any] = {
        "date": today,
        "source": f"pipeline-{today}",
        "generated_at": now_iso,
        "total_entries": saved,
        "filtered_out": filtered_out,
        "entries": index_entries,
    }
    if dry_run:
        logger.info("DRY-RUN: would save index to %s", index_path)
    else:
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(index_data, fh, ensure_ascii=False, indent=2)
        logger.info("saved index: %s (%d entries)", index_path.name, saved)

    return saved


# ---------------------------------------------------------------------------
# Save raw data
# ---------------------------------------------------------------------------


def _save_raw(items: list[dict[str, Any]], dry_run: bool = False) -> None:
    """Save raw collected data to knowledge/raw/ for traceability.

    Args:
        items: Raw collected items from Step 1.
        dry_run: If True, skip file write.
    """
    today = _today_str()
    now_iso = _now_iso()
    raw_path = RAW_DIR / f"pipeline-collect-{today}.json"

    raw_data: dict[str, Any] = {
        "meta": {
            "pipeline": "collect",
            "fetched_at": now_iso,
            "date": today,
            "total_items": len(items),
        },
        "items": items,
    }
    if dry_run:
        logger.info("DRY-RUN: would save raw data to %s", raw_path)
    else:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as fh:
            json.dump(raw_data, fh, ensure_ascii=False, indent=2)
        logger.info("saved raw data: %s", raw_path.name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="四步知识库自动化流水线: Collect -> Analyze -> Organize -> Save",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="采集来源，逗号分隔: github, rss (默认: github,rss)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每个来源的最大采集数量 (默认: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：跳过 LLM 调用和文件写入",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出 DEBUG 级别详细日志",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run_pipeline(
    sources: list[str],
    limit: int,
    dry_run: bool,
) -> int:
    """Execute the full four-step pipeline.

    Args:
        sources: List of source identifiers.
        limit: Max items per source.
        dry_run: Whether this is a dry run.

    Returns:
        Number of articles saved.
    """
    logger.info(
        "pipeline starting: sources=%s limit=%d dry_run=%s",
        sources, limit, dry_run,
    )

    # Step 1: Collect
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "ai-knowledge-base-pipeline/1.0"},
    ) as client:
        raw_items = await step_collect(client, sources, limit, dry_run=dry_run)

    if not raw_items:
        logger.warning("no items collected, pipeline ends")
        return 0

    # Save raw data for traceability
    _save_raw(raw_items, dry_run=dry_run)

    # Step 2: Analyze
    if dry_run:
        provider = None  # type: ignore[assignment]
    else:
        provider = create_provider()

    analyzed_items = await step_analyze(provider, raw_items, dry_run=dry_run)

    if not analyzed_items:
        logger.warning("no items analyzed, pipeline ends")
        return 0

    # Step 3: Organize
    organized_items = step_organize(analyzed_items)

    if not organized_items:
        logger.warning("no items passed organization, pipeline ends")
        return 0

    # Step 4: Save
    saved = step_save(organized_items, dry_run=dry_run)

    logger.info("pipeline complete: %d articles saved", saved)
    return saved


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid_sources = {"github", "rss"}
    sources = [s for s in sources if s in valid_sources]
    if not sources:
        logger.error("no valid sources specified (choose from: github, rss)")
        sys.exit(1)

    saved = asyncio.run(_run_pipeline(sources, args.limit, args.dry_run))
    logger.info("exit: saved=%d", saved)
    print(f"Pipeline complete. Articles saved: {saved}")


if __name__ == "__main__":
    main()
