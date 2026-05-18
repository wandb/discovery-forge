"""Feedback ingestion from Weave calls into local weekly artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_profile_runs(week_dir: Path) -> list[dict[str, Any]]:
    """Load per-tool profile trace records for a week."""
    path = week_dir / "_profile_runs.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _feedback_to_dict(item: Any) -> dict[str, Any]:
    """Convert a Weave feedback object or dict into JSON-serializable data."""
    if isinstance(item, dict):
        return item
    data = {}
    for key in (
        "id",
        "feedback_type",
        "payload",
        "created_at",
        "call_id",
        "weave_ref",
        "runnable_ref",
        "call_ref",
        "annotation_ref",
        "queue_id",
        "wb_user_id",
    ):
        value = getattr(item, key, None)
        if value is not None:
            data[key] = value
    return data


def _feedback_matches_call(item: dict[str, Any], call_id: str) -> bool:
    """Return True when a feedback row belongs to the requested Weave call."""
    if item.get("call_id") == call_id:
        return True
    ref = item.get("weave_ref") or item.get("runnable_ref") or item.get("call_ref")
    return isinstance(ref, str) and call_id in ref


def collect_call_feedback(client: Any, call_id: str) -> list[dict[str, Any]]:
    """Fetch feedback rows for one Weave call ID."""
    feedback_items = getattr(client, "get_feedback")()
    return [
        _feedback_to_dict(item)
        for item in feedback_items
        if _feedback_matches_call(_feedback_to_dict(item), call_id)
    ]


def ingest_feedback(week_dir: Path, client: Any) -> list[dict[str, Any]]:
    """Write feedback_events.jsonl and prompt_improvement_notes.md for a week."""
    profile_runs = load_profile_runs(week_dir)
    events: list[dict[str, Any]] = []

    for run in profile_runs:
        call_id = run.get("weave_call_id")
        if not call_id:
            continue
        for feedback in collect_call_feedback(client, call_id):
            event = {
                "week": run.get("week"),
                "run_id": run.get("run_id"),
                "slug": run.get("slug"),
                "name": run.get("name"),
                "url": run.get("url"),
                "weave_call_id": call_id,
                "feedback": feedback,
            }
            events.append(event)

    events_path = week_dir / "feedback_events.jsonl"
    with events_path.open("w") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")

    notes_path = week_dir / "prompt_improvement_notes.md"
    notes_path.write_text(render_prompt_improvement_notes(events))
    return events


def render_prompt_improvement_notes(events: list[dict[str, Any]]) -> str:
    """Summarize feedback into a maintainer-readable prompt improvement note."""
    lines = ["# Prompt Improvement Notes", ""]
    if not events:
        lines.append("No Weave feedback found for profiled tool traces.")
        lines.append("")
        return "\n".join(lines)

    issue_counts: Counter[str] = Counter()
    by_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        payload = event.get("feedback", {}).get("payload", {})
        if isinstance(payload, dict):
            issue_type = payload.get("prompt_issue_type")
            if issue_type:
                issue_counts[str(issue_type)] += 1
        by_tool[str(event.get("slug") or event.get("name") or "unknown")].append(event)

    lines.append("## Issue Summary")
    lines.append("")
    if issue_counts:
        for issue_type, count in issue_counts.most_common():
            lines.append(f"- `{issue_type}`: {count}")
    else:
        lines.append("- No structured `prompt_issue_type` feedback found.")
    lines.append("")

    lines.append("## Tool Feedback")
    lines.append("")
    for slug, tool_events in sorted(by_tool.items()):
        lines.append(f"### {slug}")
        for event in tool_events:
            feedback = event.get("feedback", {})
            feedback_type = feedback.get("feedback_type", "unknown")
            payload = feedback.get("payload", {})
            lines.append(f"- `{feedback_type}`: {json.dumps(payload, ensure_ascii=False, default=str)}")
        lines.append("")

    lines.append("## Suggested Prompt Review")
    lines.append("")
    lines.append("- Review ProfilerAgent instructions for repeated `scope_filter`, `search_query`, `source_selection`, or `metadata_extraction` issues.")
    lines.append("- Apply prompt edits manually after checking the referenced Weave calls.")
    lines.append("")
    return "\n".join(lines)
