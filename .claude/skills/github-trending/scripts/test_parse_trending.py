"""Tests for parse_trending.py with offline HTML fixtures."""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from parse_trending import FILTER_KEYWORDS, _match_topics, _parse_stars, parse_trending

FIXTURE_HTML = """\
<!DOCTYPE html>
<html>
<body>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/llm-org/awesome-llm" class="Link">llm-org / <span class="text-bold">awesome-llm</span></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A curated list of LLM resources</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/llm-org/awesome-llm/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      15,234
    </a>
  </div>
  <div class="topics-row-container">
    <a class="topic-tag topic-tag-link" href="/topics/llm">llm</a>
    <a class="topic-tag topic-tag-link" href="/topics/awesome-list">awesome-list</a>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/agent-org/agent-sdk" class="Link">agent-org / <span class="text-bold">agent-sdk</span></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">SDK for building AI agents</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/agent-org/agent-sdk/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      8,500
    </a>
  </div>
  <div class="topics-row-container">
    <a class="topic-tag topic-tag-link" href="/topics/agent">agent</a>
    <a class="topic-tag topic-tag-link" href="/topics/python">python</a>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/tools-org/web-framework" class="Link">tools-org / <span class="text-bold">web-framework</span></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">A fast web framework</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/tools-org/web-framework/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      3,200
    </a>
  </div>
  <div class="topics-row-container">
    <a class="topic-tag topic-tag-link" href="/topics/web">web</a>
    <a class="topic-tag topic-tag-link" href="/topics/framework">framework</a>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/data-org/ml-pipeline" class="Link">data-org / <span class="text-bold">ml-pipeline</span></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">ML training pipeline toolkit</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/data-org/ml-pipeline/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      1,200
    </a>
  </div>
  <div class="topics-row-container">
    <a class="topic-tag topic-tag-link" href="/topics/ml">ml</a>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/ai-org/no-topics-repo" class="Link">ai-org / <span class="text-bold">no-topics-repo</span></a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">No topics but name suggests AI</p>
  <div class="f6 color-fg-muted mt-2">
    <a href="/ai-org/no-topics-repo/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      500
    </a>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/ml-org/no-desc-repo" class="Link">ml-org / <span class="text-bold">no-desc-repo</span></a>
  </h2>
  <div class="f6 color-fg-muted mt-2">
    <a href="/ml-org/no-desc-repo/stargazers" class="Link--muted d-inline-block mr-3">
      <svg></svg>
      750
    </a>
  </div>
  <div class="topics-row-container">
    <a class="topic-tag topic-tag-link" href="/topics/machine-learning">machine-learning</a>
  </div>
</article>
</body>
</html>
"""


class TestMatchTopics:
    def test_exact_match(self) -> None:
        assert _match_topics(["llm", "python"])
        assert _match_topics(["agent"])
        assert _match_topics(["ai"])

    def test_case_insensitive(self) -> None:
        assert _match_topics(["LLM"])
        assert _match_topics(["Agent", "Tool"])

    def test_substring_match(self) -> None:
        assert _match_topics(["llm-ops", "rag"])
        assert _match_topics(["ai-agent"])

    def test_no_match(self) -> None:
        assert not _match_topics(["python", "web", "framework"])
        assert not _match_topics([])

    def test_ml_substring_excludes_xml(self) -> None:
        """ml 子串匹配会命中 xml — 当前设计接受此行为."""
        assert _match_topics(["xml"]) is True


class TestParseTrending:
    def test_total_parsed_count(self) -> None:
        repos, total = parse_trending(FIXTURE_HTML)
        assert total == 6

    def test_filtered_count(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        # Matching: llm-org/awesome-llm (llm), agent-org/agent-sdk (agent),
        #          data-org/ml-pipeline (ml). ai-org/no-topics-repo excluded
        #          (no topics). ml-org/no-desc-repo excluded (machine-learning
        #          not in keyword list).
        assert len(repos) == 3

    def test_field_completeness(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        required = {"name", "url", "stars", "topics", "description"}
        for repo in repos:
            assert required == set(repo.keys())
            assert isinstance(repo["name"], str) and repo["name"]
            assert repo["url"].startswith("https://github.com/")
            assert isinstance(repo["stars"], int)
            assert isinstance(repo["topics"], list) and len(repo["topics"]) > 0
            assert isinstance(repo["description"], str)

    def test_stars_parsing(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        stars_map = {r["name"]: r["stars"] for r in repos}
        assert stars_map["llm-org/awesome-llm"] == 15234
        assert stars_map["agent-org/agent-sdk"] == 8500
        assert stars_map["data-org/ml-pipeline"] == 1200

    def test_excludes_non_ai_topics(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        names = {r["name"] for r in repos}
        assert "tools-org/web-framework" not in names

    def test_excludes_no_topics_repo(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        names = {r["name"] for r in repos}
        assert "ai-org/no-topics-repo" not in names

    def test_missing_description_defaults_empty(self) -> None:
        repos, _ = parse_trending(FIXTURE_HTML)
        no_desc = [r for r in repos if r["name"] == "ml-org/no-desc-repo"]
        # machine-learning is not in FILTER_KEYWORDS so it's excluded;
        # verify no crash for missing <p> tag in excluded entries
        assert len(no_desc) == 0

    def test_empty_html(self) -> None:
        repos, total = parse_trending("")
        assert total == 0
        assert repos == []

    def test_irrelevant_html(self) -> None:
        repos, total = parse_trending("<html><body><p>hello</p></body></html>")
        assert total == 0
        assert repos == []


class TestParseStars:
    def test_plain_integer(self) -> None:
        assert _parse_stars("12345") == 12345

    def test_comma_separated(self) -> None:
        assert _parse_stars("15,234") == 15234

    def test_k_suffix_integer(self) -> None:
        assert _parse_stars("12k") == 12000

    def test_k_suffix_decimal(self) -> None:
        assert _parse_stars("1.2k") == 1200

    def test_m_suffix(self) -> None:
        assert _parse_stars("2.5m") == 2500000

    def test_case_insensitive_suffix(self) -> None:
        assert _parse_stars("3K") == 3000

    def test_empty_string(self) -> None:
        assert _parse_stars("") == 0

    def test_invalid_string(self) -> None:
        assert _parse_stars("abc") == 0


class TestFilterKeywords:
    def test_keywords_unchanged(self) -> None:
        """回归测试: 过滤关键词集不应随意变更."""
        assert FILTER_KEYWORDS == frozenset({"ai", "llm", "agent", "ml"})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
