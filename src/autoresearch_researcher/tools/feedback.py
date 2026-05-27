"""Feedback ingestion from Weave calls into local daily artifacts."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TARGET_ANNOTATION_RE = re.compile(r"(?:^|\.)(D(\d{8})_(Discovery|Profiler))$")


def load_profile_runs(day_dir: Path) -> list[dict[str, Any]]:
    """Load per-tool profile trace records for a day."""
    path = day_dir / "_profile_runs.jsonl"
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


def annotation_target_prompt(feedback: dict[str, Any], day: str) -> str | None:
    """Return the prompt file targeted by a day-scoped annotation name."""
    day_token = _day_annotation_token(day)
    if day_token is None:
        return None

    for value in _annotation_name_candidates(feedback):
        match = TARGET_ANNOTATION_RE.search(value)
        if match is None:
            continue
        annotation_day = match.group(2)
        if annotation_day != day_token:
            continue
        agent_name = match.group(3).lower()
        return "discovery" if agent_name == "discovery" else "profiler"
    return None


def _annotation_name_candidates(feedback: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("feedback_type", "annotation_ref", "annotation_queue_name"):
        value = feedback.get(key)
        if isinstance(value, str):
            values.append(value)
    payload = feedback.get("payload", {})
    if isinstance(payload, dict):
        for key in ("annotation_name", "name", "scorer_name"):
            value = payload.get(key)
            if isinstance(value, str):
                values.append(value)
    return values


def ingest_feedback(day_dir: Path, client: Any) -> list[dict[str, Any]]:
    """Write feedback_events.jsonl and prompt_improvement_notes.md for a day."""
    profile_runs = load_profile_runs(day_dir)
    day = _feedback_day_id(day_dir, profile_runs)
    events: list[dict[str, Any]] = []
    run_by_call_id = {
        run.get("weave_call_id"): run
        for run in profile_runs
        if run.get("weave_call_id")
    }
    seen_keys: set[str] = set()
    queue_name_cache: dict[str, str | None] = {}

    def add_event(feedback: dict[str, Any], run: dict[str, Any] | None = None) -> None:
        feedback = enrich_feedback_with_queue_name(
            client,
            feedback,
            queue_name_cache=queue_name_cache,
        )
        event_key = _feedback_event_key(feedback)
        if event_key in seen_keys:
            return
        seen_keys.add(event_key)

        target_prompt = annotation_target_prompt(feedback, day)
        event = {
            "day": (run or {}).get("day") or day,
            "run_id": (run or {}).get("run_id"),
            "slug": (run or {}).get("slug"),
            "name": (run or {}).get("name"),
            "url": (run or {}).get("url"),
            "weave_call_id": feedback.get("call_id") or (run or {}).get("weave_call_id"),
            "target_prompt": target_prompt,
            "feedback": feedback,
        }
        events.append(event)

    for run in profile_runs:
        call_id = run.get("weave_call_id")
        if not call_id:
            continue
        for feedback in collect_call_feedback(client, call_id):
            add_event(feedback, run)

    for item in getattr(client, "get_feedback")():
        feedback = _feedback_to_dict(item)
        feedback = enrich_feedback_with_queue_name(
            client,
            feedback,
            queue_name_cache=queue_name_cache,
        )
        if annotation_target_prompt(feedback, day) is None:
            continue
        call_id = feedback.get("call_id")
        run = run_by_call_id.get(call_id)
        add_event(feedback, run)

    events_path = day_dir / "feedback_events.jsonl"
    with events_path.open("w") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")

    notes_path = day_dir / "prompt_improvement_notes.md"
    notes_path.write_text(render_prompt_improvement_notes(events))
    return events


def enrich_feedback_with_queue_name(
    client: Any,
    feedback: dict[str, Any],
    *,
    queue_name_cache: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Attach the annotation queue name when Weave only returns the queue ID."""
    queue_id = feedback.get("queue_id")
    if not isinstance(queue_id, str) or feedback.get("annotation_queue_name"):
        return feedback

    if queue_name_cache is None:
        queue_name_cache = {}
    if queue_id not in queue_name_cache:
        queue_name_cache[queue_id] = resolve_annotation_queue_name(client, queue_id)

    queue_name = queue_name_cache[queue_id]
    if queue_name is None:
        return feedback

    enriched = dict(feedback)
    enriched["annotation_queue_name"] = queue_name
    return enriched


def resolve_annotation_queue_name(client: Any, queue_id: str) -> str | None:
    """Resolve a Weave annotation queue ID to its display name."""
    server = getattr(client, "server", None)
    project_id = _client_project_id(client)
    if server is None or project_id is None:
        return None

    try:
        from weave.trace_server.trace_server_interface import AnnotationQueueReadReq

        response = server.annotation_queue_read(
            AnnotationQueueReadReq(project_id=project_id, queue_id=queue_id)
        )
    except Exception:
        return None

    queue = getattr(response, "queue", None)
    name = getattr(queue, "name", None)
    return name if isinstance(name, str) else None


def _client_project_id(client: Any) -> str | None:
    value = getattr(client, "project_id", None)
    if isinstance(value, str):
        return value

    project_id_fn = getattr(client, "_project_id", None)
    if callable(project_id_fn):
        try:
            value = project_id_fn()
        except Exception:
            return None
        return value if isinstance(value, str) else None
    return None


def _feedback_event_key(feedback: dict[str, Any]) -> str:
    if feedback.get("id") is not None:
        return f"id:{feedback['id']}"
    payload = json.dumps(feedback.get("payload", {}), sort_keys=True, default=str)
    return f"{feedback.get('call_id')}|{feedback.get('feedback_type')}|{payload}"


def _feedback_day_id(day_dir: Path, profile_runs: list[dict[str, Any]]) -> str:
    for run in profile_runs:
        day = run.get("day")
        if isinstance(day, str) and _day_annotation_token(day) is not None:
            return day
    return day_dir.name


def _day_annotation_token(day: str) -> str | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", day)
    if match is None:
        return None
    return "".join(match.groups())


def render_prompt_improvement_notes(events: list[dict[str, Any]]) -> str:
    """Summarize feedback into a maintainer-readable prompt improvement note."""
    lines = ["# Prompt Improvement Notes", ""]
    if not events:
        lines.append("No Weave feedback found for profiled tool traces.")
        lines.append("")
        return "\n".join(lines)

    issue_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    by_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        target_prompt = event.get("target_prompt")
        if target_prompt:
            target_counts[str(target_prompt)] += 1
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

    lines.append("## Target Prompt Summary")
    lines.append("")
    if target_counts:
        for target_prompt, count in target_counts.most_common():
            lines.append(f"- `{target_prompt}.md`: {count}")
    else:
        lines.append("- No day-scoped `D{YYYYMMDD}_Discovery` or `D{YYYYMMDD}_Profiler` annotations found.")
    lines.append("")

    lines.append("## Tool Feedback")
    lines.append("")
    for slug, tool_events in sorted(by_tool.items()):
        lines.append(f"### {slug}")
        for event in tool_events:
            feedback = event.get("feedback", {})
            feedback_type = feedback.get("feedback_type", "unknown")
            payload = feedback.get("payload", {})
            target_prompt = event.get("target_prompt")
            target_text = f" -> `{target_prompt}.md`" if target_prompt else ""
            lines.append(
                f"- `{feedback_type}`{target_text}: "
                f"{json.dumps(payload, ensure_ascii=False, default=str)}"
            )
        lines.append("")

    lines.append("## Suggested Prompt Review")
    lines.append("")
    lines.append("- Review ProfilerAgent instructions for repeated `scope_filter`, `search_query`, `source_selection`, or `metadata_extraction` issues.")
    lines.append("- Apply prompt edits manually after checking the referenced Weave calls.")
    lines.append("")
    return "\n".join(lines)
