#!/usr/bin/env python3
"""Parse GitHub Trending HTML and output filtered JSON array.

Reads HTML from stdin, extracts repo info, filters by AI-related topics
(ai/llm/agent/ml), and writes a JSON array to stdout.
Returns empty array on any error.

Requires: beautifulsoup4
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FILTER_KEYWORDS = frozenset({"ai", "llm", "agent", "ml"})
_STAR_SUFFIXES = {"k": 1_000, "m": 1_000_000}


def _parse_stars(text: str) -> int:
    """Parse a star count string (e.g. '15,234', '1.2k', '3k') to int."""
    text = text.strip().lower().replace(",", "")
    if not text:
        return 0
    for suffix, multiplier in _STAR_SUFFIXES.items():
        if text.endswith(suffix):
            try:
                return int(float(text[:-1]) * multiplier)
            except ValueError:
                return 0
    try:
        return int(text)
    except ValueError:
        return 0


def _match_topics(topics: list[str]) -> bool:
    """Return True if any topic contains an AI-related keyword (case-insensitive)."""
    return any(
        kw in topic.lower() for topic in topics for kw in FILTER_KEYWORDS
    )


def parse_trending(html: str) -> tuple[list[dict[str, object]], int]:
    """Parse GitHub Trending HTML and return (filtered_repos, total_parsed)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write("ERROR: beautifulsoup4 not installed\n")
        return [], 0

    soup = BeautifulSoup(html, "html.parser")
    repos: list[dict[str, object]] = []
    articles = soup.find_all("article", class_="Box-row")
    total_parsed = len(articles)

    for article in articles:
        try:
            h2 = article.find("h2", class_="h3")
            if not h2:
                continue
            link = h2.find("a", class_="Link")
            if not link:
                continue
            href = (link.get("href") or "").strip()
            name = href.strip("/")
            url = f"https://github.com{href}" if href.startswith("/") else href

            desc_p = article.find("p", class_="col-9")
            description = desc_p.get_text(strip=True) if desc_p else ""

            topics: list[str] = []
            topics_container = article.find("div", class_="topics-row-container")
            if topics_container:
                topics = [
                    t.get_text(strip=True)
                    for t in topics_container.find_all("a", class_="topic-tag")
                ]

            if not _match_topics(topics):
                continue

            stars = 0
            star_link = article.find("a", href=re.compile(r"/stargazers"))
            if star_link:
                stars = _parse_stars(star_link.get_text(strip=True))

            repos.append({
                "name": name,
                "url": url,
                "stars": stars,
                "topics": topics,
                "description": description,
            })

        except Exception:
            continue

    return repos, total_parsed


def _find_schema() -> Path | None:
    """Locate trending_output.schema.json by walking up from __file__."""
    current = Path(__file__).resolve().parent
    for _ in range(8):
        candidate = current / "schemas" / "trending_output.schema.json"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _validate_output(repos: list[dict[str, object]]) -> None:
    """Validate repos against trending_output JSON Schema. Logs warning on failure."""
    try:
        from jsonschema import validate as jsonschema_validate  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write("WARNING: jsonschema not installed, skipping schema validation\n")
        return

    schema_path = _find_schema()
    if schema_path is None:
        sys.stderr.write("WARNING: trending_output.schema.json not found\n")
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema_validate(instance=repos, schema=schema)
    except (json.JSONDecodeError, OSError, Exception) as exc:
        sys.stderr.write(f"WARNING: schema validation failed: {exc}\n")


def main() -> None:
    try:
        html = sys.stdin.read()
        if not html.strip():
            print("[]")
            return
        repos, total_parsed = parse_trending(html)
        if total_parsed == 0:
            sys.stderr.write(
                "WARNING: parsed 0 repos from HTML, "
                "GitHub trending page structure may have changed\n"
            )
        _validate_output(repos)
        sys.stdout.reconfigure(encoding="utf-8")
        json.dump(repos, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.flush()
    except Exception:
        print("[]")


if __name__ == "__main__":
    main()
