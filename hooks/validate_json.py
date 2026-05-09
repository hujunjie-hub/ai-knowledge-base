#!/usr/bin/env python3
"""知识条目 JSON 文件校验工具。

支持单文件和多文件（通配符 *.json）两种输入模式。
校验通过 exit 0，失败 exit 1。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 必填字段：字段名 → 期望类型
REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})
VALID_AUDIENCES = frozenset({"beginner", "intermediate", "advanced"})

_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_URL_RE = re.compile(r"^https?://")
_SUMMARY_MIN_LEN = 20
_TAGS_MIN_COUNT = 1
_SCORE_MIN, _SCORE_MAX = 1, 10


def _collect_files(patterns: list[Path]) -> list[Path]:
    """展开通配模式，返回去重、排序后的文件列表。"""
    seen: set[str] = set()
    files: list[Path] = []
    for pattern in patterns:
        # 已是具体文件则直接收入
        if pattern.is_file():
            if str(pattern) not in seen:
                seen.add(str(pattern))
                files.append(pattern)
            continue
        # 目录 → 匹配其下所有 *.json
        if pattern.is_dir():
            for matched in sorted(pattern.glob("*.json")):
                if str(matched) not in seen:
                    seen.add(str(matched))
                    files.append(matched)
            continue
        # 带通配符的模式（如 knowledge/articles/*.json）
        parent = pattern.parent
        if not parent.is_dir():
            logger.warning("路径不存在，跳过: %s", pattern)
            continue
        for matched in sorted(parent.glob(pattern.name)):
            if matched.is_file() and str(matched) not in seen:
                seen.add(str(matched))
                files.append(matched)
    return files


def validate_file(filepath: Path) -> list[str]:
    """校验单个 JSON 文件，返回错误列表（空列表表示通过）。"""
    errors: list[str] = []
    label = str(filepath)

    # 1. 解析 JSON
    try:
        raw = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{label}: 文件读取失败 — {exc}")
        return errors

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: JSON 解析失败 — {exc}")
        return errors

    if not isinstance(data, dict):
        errors.append(f"{label}: 顶层结构必须是对象，实际为 {type(data).__name__}")
        return errors

    # 2. 必填字段存在性与类型（逐字段记录是否可安全访问）
    field_ok: dict[str, bool] = {}
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"{label}: 缺少必填字段 `{field}`")
            field_ok[field] = False
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"{label}: 字段 `{field}` 类型错误，"
                f"期望 {expected_type.__name__}，"
                f"实际 {type(data[field]).__name__}"
            )
            field_ok[field] = False
        else:
            field_ok[field] = True

    # 3. ID 格式（仅当类型正确时检查）
    if field_ok.get("id") and not _ID_RE.match(data["id"]):
        errors.append(
            f"{label}: ID 格式错误，"
            f"期望 UUID v7 格式，"
            f"实际 `{data['id']}`"
        )

    # 4. URL 格式
    if field_ok.get("source_url") and not _URL_RE.match(data["source_url"]):
        errors.append(f"{label}: source_url 格式无效 `{data['source_url']}`")

    # 5. status 枚举
    if field_ok.get("status") and data["status"] not in VALID_STATUSES:
        errors.append(
            f"{label}: status 值无效 `{data['status']}`，"
            f"允许值 {sorted(VALID_STATUSES)}"
        )

    # 6. summary 最少 N 字
    if field_ok.get("summary") and len(data["summary"]) < _SUMMARY_MIN_LEN:
        errors.append(
            f"{label}: summary 过短（{len(data['summary'])} 字），"
            f"最少 {_SUMMARY_MIN_LEN} 字"
        )

    # 7. tags 至少 1 个
    if field_ok.get("tags") and len(data["tags"]) < _TAGS_MIN_COUNT:
        errors.append(f"{label}: tags 至少需要 {_TAGS_MIN_COUNT} 个标签")

    # 8. 可选字段：score 1-10
    if "score" in data:
        score = data["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            errors.append(f"{label}: score 类型错误 `{score}`")
        elif not (_SCORE_MIN <= score <= _SCORE_MAX):
            errors.append(
                f"{label}: score 值无效 {score}，范围为 {_SCORE_MIN}-{_SCORE_MAX}"
            )

    # 9. 可选字段：audience
    if "audience" in data:
        audience = data["audience"]
        if audience not in VALID_AUDIENCES:
            errors.append(
                f"{label}: audience 值无效 `{audience}`，"
                f"允许值 {sorted(VALID_AUDIENCES)}"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    """入口函数。

    Args:
        argv: 命令行参数列表，None 表示使用 sys.argv。

    Returns:
        0 表示全部通过，1 表示存在错误。
    """
    parser = argparse.ArgumentParser(description="校验知识条目 JSON 文件")
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="JSON 文件路径或通配模式（如 knowledge/articles/*.json）",
    )
    args = parser.parse_args(argv)

    filepaths = _collect_files(args.files)
    if not filepaths:
        logger.warning("未匹配到任何 JSON 文件")
        return 0

    all_errors: dict[str, list[str]] = {}
    for fp in filepaths:
        errs = validate_file(fp)
        if errs:
            all_errors[str(fp)] = errs

    total = len(filepaths)
    error_count = sum(len(v) for v in all_errors.values())
    passed = total - len(all_errors)

    # 输出错误明细
    for filepath, errs in all_errors.items():
        for err in errs:
            logger.error(err)

    # 汇总统计
    logger.info(
        "校验完成: %d/%d 文件通过，共 %d 个错误",
        passed,
        total,
        error_count,
    )

    return 1 if all_errors else 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stderr,
    )
    sys.exit(main())
