#!/usr/bin/env python3
"""知识条目 5 维度质量评分工具。

支持单文件和通配符多文件输入，输出可视化进度条、维度得分和等级。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 标准标签列表（来自项目 Schema）
_STANDARD_TAGS = frozenset({"LLM", "Agent", "Infra", "Tool", "Paper"})

# 合法 status 值
_VALID_STATUSES = frozenset({"draft", "reviewed", "review", "published"})

# 技术关键词（摘要中出现可获奖励分）
_TECH_KEYWORDS = [
    "AI", "LLM", "Agent", "ML", "RAG", "API", "CLI", "SDK",
    "transformer", "fine-tune", "fine-tuning", "inference", "embedding",
    "open-source", "MIT", "Apache", "GPL",
    "Python", "Rust", "Go", "TypeScript", "JavaScript",
    "neural", "model", "training", "dataset", "benchmark",
    "tokenizer", "RLHF", "DPO", "LoRA", "QLoRA",
    "GPU", "CUDA", "distributed", "multi-modal",
]

# 空洞词黑名单 — 中文
_CN_BUZZWORDS = [
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑",
    "颗粒度", "对齐", "拉通", "沉淀", "强大的", "革命性的",
]

# 空洞词黑名单 — 英文
_EN_BUZZWORDS = [
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "best-in-class", "world-class", "next-generation",
]


@dataclass
class DimensionScore:
    """单个评分维度的得分与详情。"""

    name: str
    score: float
    max_score: float
    details: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """单条知识条目的完整质量报告。"""

    file_path: str
    dimensions: list[DimensionScore]
    total_score: float
    grade: str

    @property
    def max_total(self) -> float:
        return sum(d.max_score for d in self.dimensions)


def score_summary_quality(entry: dict[str, Any]) -> DimensionScore:
    """对摘要质量评分（满分 25）。

    >= 50 字满分，>= 20 字基本分，含技术关键词有奖励。
    """
    details: list[str] = []
    summary = entry.get("summary", "")
    if not isinstance(summary, str):
        return DimensionScore(name="摘要质量", score=0, max_score=25,
                              details=["summary 字段非字符串"])

    length = len(summary)
    if length >= 50:
        base = 22.0
        details.append(f"摘要 {length} 字（≥50: 满分）")
    elif length >= 20:
        base = 15.0
        details.append(f"摘要 {length} 字（≥20: 基本分）")
    else:
        base = 5.0
        details.append(f"摘要仅 {length} 字（<20: 低分）")

    # 技术关键词奖励
    lower = summary.lower()
    tech_count = sum(1 for kw in _TECH_KEYWORDS if kw.lower() in lower)
    if tech_count > 0:
        bonus = min(tech_count, 3.0)
        score = min(base + bonus, 25.0)
        details.append(f"含 {tech_count} 个技术关键词，奖励 +{bonus:.0f}")
    else:
        score = base
        details.append("未发现技术关键词")

    return DimensionScore(name="摘要质量", score=score, max_score=25, details=details)


def score_technical_depth(entry: dict[str, Any]) -> DimensionScore:
    """对技术深度评分（满分 25）。

    基于 score 字段 1-10 线性映射到 0-25。
    """
    details: list[str] = []
    raw = entry.get("score")

    if raw is None:
        return DimensionScore(name="技术深度", score=0, max_score=25,
                              details=["缺少 score 字段"])

    # 排除 bool（bool 是 int 的子类）
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return DimensionScore(name="技术深度", score=0, max_score=25,
                              details=[f"score 类型无效: {type(raw).__name__}"])

    score_val = float(raw)
    if score_val < 1 or score_val > 10:
        details.append(f"score={score_val} 超出 1-10 范围")
        score_val = max(1.0, min(10.0, score_val))

    mapped = (score_val / 10.0) * 25.0
    mapped = round(mapped, 1)
    details.append(f"score={raw}/10 → {mapped}/25")

    return DimensionScore(name="技术深度", score=mapped, max_score=25, details=details)


def _has_timestamp(entry: dict[str, Any]) -> bool:
    """检查是否存在至少一个时间戳字段。"""
    for key in ("collected_at", "fetched_at", "analyzed_at", "published_at"):
        if key in entry and isinstance(entry[key], str) and entry[key]:
            return True
    return False


def score_format_compliance(entry: dict[str, Any]) -> DimensionScore:
    """对格式规范评分（满分 20）。

    id、title、source_url、status、时间戳五项各 4 分。
    """
    details: list[str] = []
    score = 0.0

    checks = [
        ("id", "id" in entry and isinstance(entry["id"], str) and len(entry["id"]) > 0),
        ("title", "title" in entry and isinstance(entry["title"], str) and len(entry["title"]) > 0),
        ("source_url",
         "source_url" in entry and isinstance(entry["source_url"], str)
         and entry["source_url"].startswith("http")),
        ("status",
         "status" in entry and isinstance(entry["status"], str)
         and entry["status"] in _VALID_STATUSES),
        ("时间戳", _has_timestamp(entry)),
    ]

    for field, ok in checks:
        if ok:
            score += 4.0
        else:
            details.append(f"缺少或不规范: {field}")

    if score == 20.0:
        details.insert(0, "五项齐全")

    return DimensionScore(name="格式规范", score=score, max_score=20, details=details)


def score_tag_precision(entry: dict[str, Any]) -> DimensionScore:
    """对标签精度评分（满分 15）。

    1-3 个合法标签最佳；无标签零分；过多或非标准标签扣分。
    """
    details: list[str] = []
    tags = entry.get("tags", [])

    if not isinstance(tags, list):
        return DimensionScore(name="标签精度", score=0, max_score=15,
                              details=[f"tags 非数组: {type(tags).__name__}"])

    if len(tags) == 0:
        return DimensionScore(name="标签精度", score=0, max_score=15, details=["无标签"])

    score = 15.0

    # 数量检查
    if 1 <= len(tags) <= 3:
        details.append(f"标签数 {len(tags)}（最佳范围 1-3）")
    elif len(tags) > 3:
        penalty = (len(tags) - 3) * 2.0
        score -= penalty
        details.append(f"标签过多 ({len(tags)} > 3)，扣 {penalty:.0f} 分")

    # 标准标签校验（大小写不敏感）
    standard_lower = {s.lower() for s in _STANDARD_TAGS}
    valid = [t for t in tags if t.lower() in standard_lower]
    invalid = [t for t in tags if t.lower() not in standard_lower]
    if invalid:
        penalty = len(invalid) * 2.0
        score -= penalty
        details.append(f"非标准标签 {invalid}，扣 {penalty:.0f} 分")
    if valid:
        details.append(f"标准标签 {valid} ({len(valid)}/{len(tags)})")

    score = max(0.0, min(score, 15.0))
    return DimensionScore(name="标签精度", score=score, max_score=15, details=details)


def score_buzzword_free(entry: dict[str, Any]) -> DimensionScore:
    """对空洞词检测评分（满分 15）。

    在 title / summary / title_en 中检测中英文空洞词，每命中一个扣 3 分。
    """
    details: list[str] = []
    score = 15.0

    # 收集文本字段
    parts: list[str] = []
    for field in ("title", "title_en", "summary"):
        val = entry.get(field, "")
        if isinstance(val, str):
            parts.append(val)
    combined = "".join(parts)
    combined_lower = combined.lower()

    # 中文空洞词
    found_cn = [w for w in _CN_BUZZWORDS if w in combined]
    # 英文空洞词（不区分大小写）
    found_en = [w for w in _EN_BUZZWORDS if w in combined_lower]
    all_found = found_cn + found_en

    if all_found:
        deduction = len(all_found) * 3.0
        score = max(0.0, score - deduction)
        details.append(f"发现 {len(all_found)} 个空洞词 {all_found}，扣 {deduction:.0f} 分")
    else:
        details.append("未发现空洞词")

    return DimensionScore(name="空洞词检测", score=score, max_score=15, details=details)


def check_quality(entry: dict[str, Any], file_path: str) -> QualityReport:
    """对一条知识条目执行全部 5 维度评分。

    Args:
        entry: 解析后的 JSON 数据。
        file_path: 源文件路径，仅用于报告标识。

    Returns:
        包含各维度得分与总评等级的 QualityReport。
    """
    dimensions = [
        score_summary_quality(entry),
        score_technical_depth(entry),
        score_format_compliance(entry),
        score_tag_precision(entry),
        score_buzzword_free(entry),
    ]
    total = sum(d.score for d in dimensions)
    if total >= 80:
        grade = "A"
    elif total >= 60:
        grade = "B"
    else:
        grade = "C"
    return QualityReport(file_path=file_path, dimensions=dimensions, total_score=total,
                         grade=grade)


def _progress_bar(current: int, total: int, width: int = 30) -> str:
    """生成文本进度条字符串。"""
    filled = int(width * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = (current / total * 100) if total > 0 else 0
    return f"[{bar}] {current}/{total} ({pct:.0f}%)"


def _collect_files(patterns: list[str]) -> list[Path]:
    """展开输入模式，返回去重排序后的文件列表。

    Args:
        patterns: 命令行传入的文件路径或 glob 模式。

    Returns:
        去重并排序后的 Path 列表。
    """
    seen: set[str] = set()
    files: list[Path] = []
    for pattern in patterns:
        p = Path(pattern)
        # 绝对路径
        if p.is_absolute():
            parent = p.parent
            if p.is_file():
                if str(p) not in seen:
                    seen.add(str(p))
                    files.append(p)
            elif parent.is_dir():
                for match in sorted(parent.glob(p.name)):
                    if match.is_file() and str(match) not in seen:
                        seen.add(str(match))
                        files.append(match)
            continue

        # 相对路径：直接文件
        if p.is_file():
            if str(p) not in seen:
                seen.add(str(p))
                files.append(p)
            continue

        # 相对路径：目录 → 其下所有 .json
        if p.is_dir():
            for match in sorted(p.glob("*.json")):
                if str(match) not in seen:
                    seen.add(str(match))
                    files.append(match)
            continue

        # 相对路径：通配模式
        parent = p.parent
        if parent.is_dir():
            for match in sorted(parent.glob(p.name)):
                if match.is_file() and str(match) not in seen:
                    seen.add(str(match))
                    files.append(match)

    return files


def main(argv: list[str] | None = None) -> int:
    """入口函数。

    Args:
        argv: 命令行参数列表，None 表示使用 sys.argv。

    Returns:
        0 表示全部通过（无 C 级），1 表示存在 C 级条目。
    """
    parser = argparse.ArgumentParser(description="知识条目 5 维度质量评分")
    parser.add_argument(
        "inputs",
        nargs="+",
        help="JSON 文件路径或通配符模式（如 'knowledge/articles/*.json'）",
    )
    args = parser.parse_args(argv)

    files = _collect_files(args.inputs)
    if not files:
        sys.stderr.write("未匹配到任何 JSON 文件\n")
        return 1

    reports: list[QualityReport] = []
    has_c = False

    for idx, fp in enumerate(files, 1):
        # 进度条输出到 stderr（与输出分离）
        sys.stderr.write(f"\r{_progress_bar(idx, len(files))}")
        sys.stderr.flush()

        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"\n跳过无法解析的文件: {fp} — {exc}\n")
            continue
        except OSError as exc:
            sys.stderr.write(f"\n跳过无法读取的文件: {fp} — {exc}\n")
            continue

        if not isinstance(data, dict):
            sys.stderr.write(f"\n跳过非对象顶层结构: {fp}\n")
            continue

        report = check_quality(data, str(fp))
        reports.append(report)
        if report.grade == "C":
            has_c = True

    sys.stderr.write("\n")

    if not reports:
        sys.stderr.write("没有成功评分的条目\n")
        return 1

    # 输出报告
    sep = "─" * 60
    sys.stdout.write(f"\n{sep}\n")
    for report in reports:
        sys.stdout.write(f"📄 {report.file_path}\n")
        sys.stdout.write(
            f"   总分: {report.total_score:.1f}/{report.max_total:.0f}"
            f"  等级: {report.grade}\n"
        )
        for dim in report.dimensions:
            sys.stdout.write(f"   {dim.name}: {dim.score:.1f}/{dim.max_score:.0f}\n")
            for detail in dim.details:
                sys.stdout.write(f"      ↳ {detail}\n")
        sys.stdout.write(f"{sep}\n")

    # 汇总
    grade_counts = {"A": 0, "B": 0, "C": 0}
    for r in reports:
        grade_counts[r.grade] += 1
    sys.stdout.write(
        f"\n总计 {len(reports)} 条:"
        f" A={grade_counts['A']} B={grade_counts['B']} C={grade_counts['C']}\n"
    )

    if has_c:
        sys.stdout.write("结果: 存在 C 级条目，质量不达标\n")
        return 1
    else:
        sys.stdout.write("结果: 全部通过\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
