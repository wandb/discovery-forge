"""Diff infrastructure: draft vs final diff generation and feedback template."""

import difflib
import re
from typing import Optional


# Patterns for semantic diff classification
_ADD_PATTERNS = [
    re.compile(r"^\+\s*#{1,3}\s+\w"),   # new heading (tool section added)
    re.compile(r"^\+\s*\|.*\|.*\|"),     # new table row (tool added)
]
_REMOVE_PATTERNS = [
    re.compile(r"^-\s*#{1,3}\s+\w"),    # removed heading (tool removed)
    re.compile(r"^-\s*\|.*\|.*\|"),     # removed table row
]
_FIX_PATTERNS = [
    re.compile(r"^[+-].*\b\d+\s*(stars?|issues?|commits?|forks?)\b", re.I),
    re.compile(r"^[+-].*\b(MIT|Apache|GPL|BSD|Commercial|Custom)\b", re.I),
    re.compile(r"^[+-]\s*\|"),           # any changed table cell → potential fact fix
]
_BALANCE_PATTERNS = [
    re.compile(r"^[+-].*\b(limitation|weakness|caveat|risk|concern|drawback|warning)\b", re.I),
    re.compile(r"^\+.*\*\*Known", re.I),
]


def classify_diff_line(line: str) -> Optional[str]:
    """
    Classify a unified-diff line into one of: ADD, REMOVE, FIX, REWORD, BALANCE, or None.

    Returns None for context lines (no leading + or -).
    """
    if not line or line[0] not in ("+", "-"):
        return None
    if line.startswith("---") or line.startswith("+++"):
        return None  # diff header

    for pat in _ADD_PATTERNS:
        if pat.match(line):
            return "ADD"
    for pat in _REMOVE_PATTERNS:
        if pat.match(line):
            return "REMOVE"
    for pat in _BALANCE_PATTERNS:
        if pat.match(line):
            return "BALANCE"
    for pat in _FIX_PATTERNS:
        if pat.match(line):
            return "FIX"

    return "REWORD"


def generate_diff(draft: str, final: str) -> str:
    """
    Generate a semantic diff between draft and final markdown strings.

    Returns a formatted markdown string summarising the changes.
    """
    draft_lines = draft.splitlines(keepends=True)
    final_lines = final.splitlines(keepends=True)

    unified = list(difflib.unified_diff(
        draft_lines,
        final_lines,
        fromfile="draft.md",
        tofile="final.md",
        lineterm="",
    ))

    if not unified:
        return "<!-- No changes between draft.md and final.md -->"

    # Collect classified changes
    classified: dict[str, list[str]] = {
        "ADD": [], "REMOVE": [], "FIX": [], "REWORD": [], "BALANCE": [],
    }
    for line in unified:
        cat = classify_diff_line(line)
        if cat:
            classified[cat].append(line.rstrip())

    sections = ["# Diff: draft.md → final.md\n"]
    for cat, lines in classified.items():
        if lines:
            sections.append(f"\n## [{cat}]\n")
            for ln in lines[:20]:  # cap at 20 lines per category
                sections.append(f"```\n{ln}\n```\n")

    sections.append("\n## Raw Unified Diff\n\n```diff\n")
    sections.extend(ln.rstrip() + "\n" for ln in unified[:200])
    sections.append("```\n")

    return "".join(sections)


def generate_feedback_template(week: str) -> str:
    """Generate the feedback.md template for a given week."""
    return f"""# Week {week} Feedback

## 발행 결정: ✅ as-is / ⚠️ minor edits / 🔴 major rewrite / ❌ reject

## 정량 점수 (1-5)
- 정확성:
- 완전성 (누락 도구 없는가):
- 표 가독성:
- 균형성 (낙관/비관 출처):
- 최신성:

## 수정 사항 (구조화)
- [ADD]
- [FIX]
- [REMOVE]
- [REWORD]
- [BALANCE]

## 시스템 개선 제안
- DiscoveryAgent:
- ProfilerAgent:
- WriterAgent:

## 패턴 메모 (3주 이상 반복되는 이슈만)
"""
