"""Build Weave Evaluation datasets from human profiler annotations."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from discovery_forge.tools.feedback import (
    annotation_target_prompt,
    enrich_feedback_with_queue_name,
    load_profile_runs,
)

PROFILER_DATASET_FILENAME = "eval_profiler_quality_weave.jsonl"
REVIEW_QUEUE_FILENAME = "eval_annotation_review_queue.jsonl"
DATASET_REFS_FILENAME = "eval_dataset_refs.json"
PROFILER_DATASET_NAME = "discovery-forge-profiler-quality-eval"
SUPPORTED_VERDICTS = {"good", "bad"}
MINIMAL_PROFILER_EVAL_FIELDS = (
    "input_tool_name",
    "input_candidate_url",
    "input_candidate_description",
    "expected_scope_status",
    "expected_issue_category",
)


def export_profiler_eval_dataset(
    *,
    day_dir: Path,
    client: Any,
    min_annotators: int = 2,
    manual_cases_path: Path | None = None,
    publish_weave_dataset: bool = False,
) -> dict[str, Any]:
    """Export profiler annotation rows for Weave Evaluation."""
    day = _day_from_dir(day_dir)
    profile_runs = load_profile_runs(day_dir)
    candidates = _read_jsonl(day_dir / "_candidates.jsonl")
    manual_cases = _read_jsonl(manual_cases_path) if manual_cases_path else []

    rows, review_queue = build_profiler_eval_rows(
        day=day,
        feedback_items=list(getattr(client, "get_feedback")()),
        profile_runs=profile_runs,
        candidates=candidates,
        min_annotators=min_annotators,
        client=client,
        manual_cases=manual_cases,
    )
    rows = dedupe_profiler_eval_rows(rows)

    dataset_path = day_dir / PROFILER_DATASET_FILENAME
    review_path = day_dir / REVIEW_QUEUE_FILENAME
    _write_jsonl(dataset_path, rows)
    _write_jsonl(review_path, review_queue)

    refs: dict[str, str] = {}
    if publish_weave_dataset:
        refs[PROFILER_DATASET_NAME] = publish_profiler_dataset(rows)
        (day_dir / DATASET_REFS_FILENAME).write_text(json.dumps(refs, indent=2) + "\n")

    return {
        "dataset_path": str(dataset_path),
        "review_queue_path": str(review_path),
        "dataset_rows": rows,
        "review_queue": review_queue,
        "dataset_refs": refs,
    }


def build_profiler_eval_rows(
    *,
    day: str,
    feedback_items: list[Any],
    profile_runs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    min_annotators: int = 2,
    client: Any | None = None,
    manual_cases: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return profiler eval rows and excluded annotation review rows."""
    rows: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    run_by_call_id = {
        run.get("weave_call_id"): run
        for run in profile_runs
        if isinstance(run.get("weave_call_id"), str)
    }
    candidate_by_key = _candidate_lookup(candidates)
    queue_name_cache: dict[str, str | None] = {}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_feedback in feedback_items:
        feedback = feedback_to_dict(raw_feedback)
        if client is not None:
            feedback = enrich_feedback_with_queue_name(
                client,
                feedback,
                queue_name_cache=queue_name_cache,
            )
        call_id = feedback.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            if _is_annotation_feedback(feedback):
                review_queue.append(_review_row("missing_call_id", feedback=feedback))
            continue
        if call_id not in run_by_call_id:
            if _is_annotation_feedback(feedback):
                review_queue.append(_review_row("missing_profile_run_metadata", feedback=feedback))
            continue
        if not _is_profiler_annotation(feedback, day=day, profiler_call_ids=set(run_by_call_id)):
            continue
        grouped[call_id].append(feedback)

    for call_id, feedback_group in sorted(grouped.items()):
        row = _row_from_feedback_group(
            day=day,
            call_id=call_id,
            feedback_group=feedback_group,
            profile_run=run_by_call_id[call_id],
            candidate_by_key=candidate_by_key,
            min_annotators=min_annotators,
        )
        if row["kind"] == "dataset":
            rows.append(row["row"])
        else:
            review_queue.append(row["row"])

    for index, manual_case in enumerate(manual_cases or [], start=1):
        row = _manual_case_to_row(day=day, manual_case=manual_case, index=index)
        if row["kind"] == "dataset":
            rows.append(row["row"])
        else:
            review_queue.append(row["row"])

    return rows, review_queue


def publish_profiler_dataset(rows: list[dict[str, Any]]) -> str:
    """Publish rows as a versioned Weave dataset and return its ref URI."""
    import weave

    dataset = weave.Dataset(name=PROFILER_DATASET_NAME, rows=rows)
    ref = weave.publish(dataset)
    uri = getattr(ref, "uri", None)
    return uri() if callable(uri) else str(ref)


def dedupe_profiler_eval_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated profiler examples for the same normalized candidate URL."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for row in rows:
        key = normalized_candidate_url(row.get("input_candidate_url"))
        if key is None:
            passthrough.append(row)
            continue
        grouped[key].append(row)

    deduped = passthrough
    for key, group in sorted(grouped.items()):
        best = max(group, key=_row_quality_score)
        merged = json.loads(json.dumps(best, default=str))
        merged["dedupe_key"] = key
        metadata = dict(merged.get("metadata") or {})
        metadata["duplicate_count"] = len(group)
        metadata["merged_example_ids"] = _unique(
            example_id
            for row in group
            if (example_id := row.get("example_id"))
        )
        metadata["merged_source_call_ids"] = _unique(
            call_id
            for row in group
            if (call_id := row.get("source_call_id"))
        )
        metadata["label_feedback_ids"] = _unique(
            feedback_id
            for row in group
            for feedback_id in (row.get("metadata") or {}).get("label_feedback_ids", [])
        ) or metadata.get("label_feedback_ids", [])
        metadata["review_feedback_ids"] = _unique(
            feedback_id
            for row in group
            for feedback_id in (row.get("metadata") or {}).get("review_feedback_ids", [])
        ) or metadata.get("review_feedback_ids", [])
        metadata["review_notes"] = _unique(
            note
            for row in group
            for note in (row.get("metadata") or {}).get("review_notes", [])
        ) or metadata.get("review_notes", [])
        metadata["label_count"] = sum(
            int((row.get("metadata") or {}).get("label_count") or 0)
            for row in group
        ) or metadata.get("label_count")
        metadata["annotator_count"] = max(
            int((row.get("metadata") or {}).get("annotator_count") or 0)
            for row in group
        )
        merged["metadata"] = metadata
        deduped.append(merged)
    return sorted(deduped, key=lambda row: str(row.get("example_id", "")))


def minimal_profiler_eval_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return only fields needed by the profiler Weave Evaluation."""
    return {field: row.get(field) for field in MINIMAL_PROFILER_EVAL_FIELDS}


def split_profiler_eval_rows_for_weave(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split verbose profiler rows into minimal eval rows and audit sidecar rows."""
    minimal_rows = [minimal_profiler_eval_row(row) for row in rows]
    audit_rows = []
    for row in rows:
        minimal = minimal_profiler_eval_row(row)
        audit = {
            "example_id": row.get("example_id"),
            "source_call_id": row.get("source_call_id"),
            "removed_fields": {
                key: value
                for key, value in row.items()
                if key not in minimal or minimal.get(key) != value
            },
        }
        audit_rows.append(audit)
    return minimal_rows, audit_rows


def normalized_candidate_url(value: Any) -> str | None:
    """Normalize a candidate URL for exact-tool dedupe."""
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip().lower().rstrip("/")
    path = parsed.path.rstrip("/")
    if parsed.netloc.lower() == "github.com" and path.endswith(".git"):
        path = path[:-4]
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.query,
        "",
    )).lower()


def feedback_to_dict(item: Any) -> dict[str, Any]:
    """Convert a Weave feedback object or dict into JSON-serializable data."""
    if isinstance(item, dict):
        return item
    data: dict[str, Any] = {}
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
    if not data.get("call_id"):
        data["call_id"] = _call_id_from_ref(data.get("weave_ref"))
    return data


def extract_annotation_verdict(feedback: dict[str, Any]) -> str | None:
    """Return explicit good/bad annotation verdicts."""
    payload = feedback.get("payload")
    if not isinstance(payload, dict):
        return None
    for key in ("value", "verdict", "quality", "label", "rating"):
        verdict = _normalize_verdict(payload.get(key))
        if verdict is not None:
            return verdict
    return None


def _row_from_feedback_group(
    *,
    day: str,
    call_id: str,
    feedback_group: list[dict[str, Any]],
    profile_run: dict[str, Any],
    candidate_by_key: dict[tuple[str, str], dict[str, Any]],
    min_annotators: int,
) -> dict[str, Any]:
    valid_annotations = []
    unsupported = []
    for feedback in feedback_group:
        annotator = feedback.get("wb_user_id")
        verdict = extract_annotation_verdict(feedback)
        if not isinstance(annotator, str) or not annotator:
            return {
                "kind": "review",
                "row": _review_row("missing_annotator", feedback=feedback, call_id=call_id),
            }
        if verdict is None:
            unsupported.append(feedback)
            continue
        valid_annotations.append((annotator, verdict, feedback))

    if unsupported and not valid_annotations:
        return {
            "kind": "review",
            "row": _review_row("unsupported_verdict", feedback=unsupported[0], call_id=call_id),
        }

    annotators = {annotator for annotator, _, _ in valid_annotations}
    if len(annotators) < min_annotators:
        return {
            "kind": "review",
            "row": _review_row(
                "not_enough_annotators",
                feedback=valid_annotations[0][2] if valid_annotations else feedback_group[0],
                call_id=call_id,
                details={"annotator_count": len(annotators), "min_annotators": min_annotators},
            ),
        }

    verdict_counts = Counter(verdict for _, verdict, _ in valid_annotations)
    if len(verdict_counts) != 1:
        return {
            "kind": "review",
            "row": _review_row(
                "verdict_disagreement",
                feedback=valid_annotations[0][2],
                call_id=call_id,
                details={"verdict_counts": dict(verdict_counts)},
            ),
        }

    verdict = next(iter(verdict_counts))
    name = profile_run.get("name")
    url = profile_run.get("url")
    if not isinstance(name, str) or not name or not isinstance(url, str) or not url:
        return {
            "kind": "review",
            "row": _review_row("missing_profile_run_metadata", feedback=valid_annotations[0][2], call_id=call_id),
        }
    candidate = _lookup_candidate(candidate_by_key, name=name, url=url)
    description = candidate.get("description") if candidate else None
    if not isinstance(description, str) or not description:
        return {
            "kind": "review",
            "row": _review_row("missing_candidate_description", feedback=valid_annotations[0][2], call_id=call_id),
        }

    feedback_ids = [str(feedback.get("id")) for _, _, feedback in valid_annotations if feedback.get("id")]
    issue_category = _issue_category([feedback for _, _, feedback in valid_annotations])
    return {
        "kind": "dataset",
        "row": {
            "example_id": f"profiler-quality:{day}:{call_id}",
            "input_day": day,
            "input_tool_name": name,
            "input_candidate_url": url,
            "input_candidate_description": description,
            "expected_human_quality": verdict,
            "expected_scope_status": _expected_scope_status(
                verdict,
                issue_category,
                original_status=profile_run.get("status"),
            ),
            "expected_issue_category": issue_category,
            "source_call_id": call_id,
            "source_workflow_name": profile_run.get("workflow_name"),
            "metadata": {
                "stage": "profiler",
                "source_stage": "profiler_annotation",
                "slug": profile_run.get("slug"),
                "original_profiler_status": profile_run.get("status"),
                "original_rejection_reason": profile_run.get("rejection_reason"),
                "annotator_count": len(annotators),
                "feedback_ids": feedback_ids,
            },
        },
    }


def _manual_case_to_row(*, day: str, manual_case: dict[str, Any], index: int) -> dict[str, Any]:
    required = (
        "input_tool_name",
        "input_candidate_url",
        "input_candidate_description",
        "expected_human_quality",
        "expected_scope_status",
    )
    missing = [key for key in required if not isinstance(manual_case.get(key), str) or not manual_case.get(key)]
    if missing:
        return {
            "kind": "review",
            "row": {
                "reason": "invalid_manual_case",
                "details": {"missing": missing, "manual_case": manual_case},
            },
        }
    verdict = _normalize_verdict(manual_case["expected_human_quality"])
    if verdict is None:
        return {
            "kind": "review",
            "row": {
                "reason": "unsupported_verdict",
                "details": {"manual_case": manual_case},
            },
        }
    example_id = manual_case.get("example_id") or f"profiler-quality:{day}:manual-{index}"
    return {
        "kind": "dataset",
        "row": {
            "example_id": example_id,
            "input_day": manual_case.get("input_day") or day,
            "input_tool_name": manual_case["input_tool_name"],
            "input_candidate_url": manual_case["input_candidate_url"],
            "input_candidate_description": manual_case["input_candidate_description"],
            "expected_human_quality": verdict,
            "expected_scope_status": manual_case["expected_scope_status"],
            "expected_issue_category": manual_case.get("expected_issue_category"),
            "source_call_id": manual_case.get("source_call_id"),
            "source_workflow_name": manual_case.get("source_workflow_name"),
            "metadata": {
                "stage": "profiler",
                "source_stage": "manual_profiler_case",
                "reason": manual_case.get("reason"),
            },
        },
    }


def _is_profiler_annotation(feedback: dict[str, Any], *, day: str, profiler_call_ids: set[str]) -> bool:
    if annotation_target_prompt(feedback, day) == "profiler":
        return True
    call_id = feedback.get("call_id")
    return isinstance(call_id, str) and call_id in profiler_call_ids and _is_annotation_feedback(feedback)


def _is_annotation_feedback(feedback: dict[str, Any]) -> bool:
    feedback_type = feedback.get("feedback_type")
    return isinstance(feedback_type, str) and feedback_type.startswith("wandb.annotation.")


def _normalize_verdict(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z]+", " ", value.strip().lower()).strip()
    return normalized if normalized in SUPPORTED_VERDICTS else None


def _call_id_from_ref(value: Any) -> str | None:
    if not isinstance(value, str) or "/call/" not in value:
        return None
    call_id = value.rsplit("/call/", 1)[-1].strip()
    return call_id or None


def _issue_category(feedback_group: list[dict[str, Any]]) -> str | None:
    for feedback in feedback_group:
        payload = feedback.get("payload")
        if not isinstance(payload, dict):
            continue
        for key in ("issue_category", "expected_issue_category", "prompt_issue_type"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _expected_scope_status(
    verdict: str,
    issue_category: str | None,
    *,
    original_status: Any = None,
) -> str:
    if verdict == "good":
        return original_status if original_status in {"accepted", "rejected"} else "accepted"
    if issue_category == "out_of_scope":
        return "rejected"
    return "accepted"


def _candidate_lookup(candidates: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup = {}
    for candidate in candidates:
        name = candidate.get("name")
        url = candidate.get("url")
        if isinstance(name, str) and isinstance(url, str):
            lookup[(_norm(name), _norm(url))] = candidate
    return lookup


def _lookup_candidate(
    candidate_by_key: dict[tuple[str, str], dict[str, Any]],
    *,
    name: str,
    url: str,
) -> dict[str, Any] | None:
    return candidate_by_key.get((_norm(name), _norm(url)))


def _norm(value: str) -> str:
    return value.strip().lower()


def _row_quality_score(row: dict[str, Any]) -> tuple[int, int, int, str]:
    metadata = row.get("metadata") or {}
    label_count = int(metadata.get("label_count") or len(metadata.get("feedback_ids", [])) or 0)
    annotator_count = int(metadata.get("annotator_count") or 0)
    review_count = len(metadata.get("review_notes", []))
    return (label_count, annotator_count, review_count, str(row.get("source_call_id") or ""))


def _unique(values) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _review_row(
    reason: str,
    *,
    feedback: dict[str, Any],
    call_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "reason": reason,
        "call_id": call_id or feedback.get("call_id"),
        "feedback_id": feedback.get("id"),
        "feedback_type": feedback.get("feedback_type"),
        "payload": feedback.get("payload"),
    }
    if details:
        row["details"] = details
    return row


def _day_from_dir(day_dir: Path) -> str:
    return day_dir.name


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
