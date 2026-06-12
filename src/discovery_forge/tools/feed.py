"""Agentforge feed export for daily discovery-forge runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discovery_forge.tools.profiles import load_tool_profiles_from_dir

RAW_ARTIFACTS = {
    "_candidates.jsonl": "candidates.jsonl",
    "_new_candidates.jsonl": "new_candidates.jsonl",
    "_updated_tools.jsonl": "updated_tools.jsonl",
    "_rejected_profiles.jsonl": "rejected_profiles.jsonl",
    "_profile_runs.jsonl": "profile_runs.jsonl",
    "run_metadata.json": "run_metadata.json",
}

ALLOWED_TAGS = {"academic", "survey", "github", "blog", "usecase", "lab"}


def build_feed_output(
    day_dir: Path,
    registry: Any | None,
    day: str,
    *,
    source_sha: str | None = None,
    previous_source_sha: str | None = None,
) -> dict[str, Any]:
    """Write Agentforge-compatible feed artifacts for one daily run."""
    day_dir.mkdir(parents=True, exist_ok=True)
    items_dir = day_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    profiles_dir = registry.profiles_dir if registry is not None else day_dir / "tools"
    profiles = load_tool_profiles_from_dir(profiles_dir)
    metadata = _read_json(day_dir / "run_metadata.json")
    generated_at = _run_timestamp(metadata)
    resolved_source_sha = source_sha if source_sha is not None else _current_source_sha()
    previous_manifest = _resolve_previous_manifest(day_dir, day=day, metadata=metadata)
    resolved_previous_source_sha = (
        previous_source_sha
        if previous_source_sha is not None
        else _manifest_source_sha(previous_manifest)
    )
    previous_items_by_key = _manifest_items_by_dedupe_key(previous_manifest)

    new_ids = _ids_from_jsonl(day_dir / "_new_candidates.jsonl")
    updated_ids = _ids_from_jsonl(day_dir / "_updated_tools.jsonl")
    daily_ids = new_ids | updated_ids
    weave_traces = _weave_traces_by_slug(day_dir / "_profile_runs.jsonl")

    manifest_items = []
    daily_profiles = _profiles_for_daily_ids(profiles, daily_ids)
    deduped_profiles = _dedupe_profiles_by_key(daily_profiles, new_ids, updated_ids)
    for profile in _sort_profiles(deduped_profiles):
        item_id = _profile_item_id(profile)
        item = _profile_to_item(
            profile,
            generated_at=generated_at,
            weave_trace=weave_traces.get(item_id),
        )
        item_path = items_dir / f"{item['id']}.json"
        _write_json(item_path, item)
        manifest_items.append({
            "id": item["id"],
            "dedupeKey": item["dedupeKey"],
            "path": f"items/{item['id']}.json",
            "contentHash": item["contentHash"],
            "changeStatus": _change_status(item, previous_items_by_key),
        })
    _remove_stale_item_files(items_dir, manifest_items)

    _write_raw_artifacts(day_dir)

    manifest_new_ids = sorted(
        item["id"] for item in manifest_items if item["changeStatus"] == "new"
    )
    manifest_updated_ids = sorted(
        item["id"] for item in manifest_items if item["changeStatus"] == "updated"
    )

    manifest = {
        "schemaVersion": 1,
        "runId": day,
        "runDate": day,
        "cadence": "daily",
        "sourceSha": resolved_source_sha,
        "previousSourceSha": resolved_previous_source_sha,
        "sourceRange": {
            "fromShaExclusive": resolved_previous_source_sha,
            "toShaInclusive": resolved_source_sha,
        },
        "generatedAt": generated_at,
        "publishedAt": generated_at,
        "updatedAt": generated_at,
        "weaveTraceId": _manifest_weave_trace_id(metadata),
        "items": manifest_items,
        "delta": {
            "newItemIds": manifest_new_ids,
            "updatedItemIds": manifest_updated_ids,
            "removedItemIds": [],
        },
    }
    manifest["manifestHash"] = stable_hash(manifest)
    _write_json(day_dir / "manifest.json", manifest)
    return manifest


def stable_hash(value: dict[str, Any]) -> str:
    """Return a SHA-256 hash of normalized JSON, excluding existing hash fields."""
    normalized = _strip_hash_fields(value)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_key_for_url(url: str | None, *, fallback_id: str) -> str:
    if url:
        normalized = _normalize_url(url)
        return f"url:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"
    return f"source:discovery-forge:{fallback_id}"


def feed_metadata_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the per-profile feed fields useful for linking Weave traces to feed items."""
    item_id = str(profile.get("slug") or _slugify(str(profile.get("name") or "unknown")))
    canonical_url = _canonical_url(profile)
    return {
        "feed_item_id": item_id,
        "feed_item_path": f"items/{item_id}.json",
        "feed_dedupe_key": dedupe_key_for_url(canonical_url, fallback_id=item_id),
        "feed_canonical_url": canonical_url,
        "feed_tags": _tags(profile),
        "feed_manifest_path": "manifest.json",
    }


def _profile_to_item(
    profile: dict[str, Any],
    *,
    generated_at: str,
    weave_trace: dict[str, str] | None,
) -> dict[str, Any]:
    item_id = _profile_item_id(profile)
    canonical_url = _canonical_url(profile)
    domains = profile.get("domains") if isinstance(profile.get("domains"), list) else []
    limitations = profile.get("key_limitations") if isinstance(profile.get("key_limitations"), list) else []
    page_title = _known_string(profile.get("page_title")) or profile.get("name") or item_id
    page_description = _known_string(profile.get("page_description")) or _summary(profile)
    page_image_url = _known_string(profile.get("page_image_url"))
    page_published_at = _known_string(profile.get("page_published_at")) or generated_at
    source_updated_at = _known_string(profile.get("source_updated_at")) or _known_string(
        profile.get("last_commit")
    )
    summary = _item_summary(profile, fallback_description=page_description)
    page_metadata = {
        "description": page_description,
        "image": page_image_url,
        "siteName": _site_name(canonical_url),
    }
    if weave_trace:
        page_metadata.update({
            "weave_call_id": weave_trace["weave_call_id"],
            "weave_agent_trace_id": weave_trace.get("agent_trace_id"),
            "weave_trace_url": weave_trace.get("trace_url"),
            "weave_workflow_name": weave_trace.get("workflow_name"),
        })

    weave_call_id = profile.get("weave_call_id") or (weave_trace or {}).get("weave_call_id")
    item = {
        "schemaVersion": 1,
        "id": item_id,
        "dedupeKey": dedupe_key_for_url(canonical_url, fallback_id=item_id),
        "canonicalUrl": canonical_url,
        "pageTitle": page_title,
        "pageMetadata": page_metadata,
        "title": profile.get("name") or item_id,
        "summary": summary,
        "tags": _tags(profile),
        "pagePublishedAt": page_published_at,
        "sourceUpdatedAt": source_updated_at,
        "weaveTraceId": weave_call_id,
        "metadata": {
            "githubStars": profile.get("stars"),
            "license": profile.get("license") or "unknown",
            "domain": domains[0] if domains else "unknown",
            "autonomyLevel": profile.get("autonomy_level") or "unknown",
            "interfaceType": profile.get("interface") or "unknown",
            "resourceRequirements": profile.get("resource_requirements") or "unknown",
            "keyLimitation": limitations[0] if limitations else "unknown",
        },
    }
    item["contentHash"] = stable_hash(item)
    return item


def _write_raw_artifacts(day_dir: Path) -> None:
    raw_dir = day_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in RAW_ARTIFACTS.items():
        source = day_dir / source_name
        if source.exists():
            shutil.copy2(source, raw_dir / target_name)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _remove_stale_item_files(items_dir: Path, manifest_items: list[dict[str, Any]]) -> None:
    expected_paths = {items_dir / f"{item['id']}.json" for item in manifest_items}
    for path in items_dir.glob("*.json"):
        if path not in expected_paths:
            path.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _resolve_previous_manifest(day_dir: Path, *, day: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    explicit_path = metadata.get("previous_manifest_path")
    if isinstance(explicit_path, str) and explicit_path:
        manifest = _read_json(Path(explicit_path))
        if manifest:
            return manifest

    previous_manifest_path = _latest_previous_manifest_path(day_dir, day=day)
    if previous_manifest_path is None:
        return None
    manifest = _read_json(previous_manifest_path)
    return manifest or None


def _latest_previous_manifest_path(day_dir: Path, *, day: str) -> Path | None:
    if not day_dir.parent.exists():
        return None
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    candidates = []
    for sibling in day_dir.parent.iterdir():
        if not sibling.is_dir() or sibling == day_dir:
            continue
        if not date_pattern.match(sibling.name) or sibling.name >= day:
            continue
        manifest_path = sibling / "manifest.json"
        if manifest_path.exists():
            candidates.append(manifest_path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.parent.name)[-1]


def _manifest_source_sha(manifest: dict[str, Any] | None) -> str | None:
    if not manifest:
        return None
    value = manifest.get("sourceSha")
    return value if isinstance(value, str) and value else None


def _manifest_items_by_dedupe_key(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}
    items = manifest.get("items")
    if not isinstance(items, list):
        return {}
    by_key = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("dedupeKey")
        if isinstance(key, str) and key:
            by_key[key] = item
    return by_key


def _manifest_weave_trace_id(metadata: dict[str, Any]) -> str | None:
    for key in ("weave_call_id", "weave_trace_id", "agent_trace_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _ids_from_jsonl(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = row.get("slug")
        if item_id:
            ids.add(str(item_id))
    return ids


def _weave_traces_by_slug(path: Path) -> dict[str, dict[str, str]]:
    """Return per-profile Weave call metadata captured during this daily run."""
    traces: dict[str, dict[str, str]] = {}
    if not path.exists():
        return traces
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        slug = row.get("slug")
        weave_call_id = row.get("weave_call_id")
        if slug and weave_call_id:
            trace = {"weave_call_id": str(weave_call_id)}
            for key in ("agent_trace_id", "trace_url", "workflow_name"):
                value = row.get(key)
                if isinstance(value, str) and value:
                    trace[key] = value
            traces[str(slug)] = trace
    return traces


def _profile_item_id(profile: dict[str, Any]) -> str:
    return str(profile.get("slug") or _slugify(str(profile.get("name") or "unknown")))


def _change_status(item: dict[str, Any], previous_items_by_key: dict[str, dict[str, Any]]) -> str:
    previous_item = previous_items_by_key.get(str(item.get("dedupeKey") or ""))
    if previous_item is None:
        return "new"
    if previous_item.get("contentHash") != item.get("contentHash"):
        return "updated"
    return "unchanged"


def _removed_item_ids(
    previous_items_by_key: dict[str, dict[str, Any]],
    manifest_items: list[dict[str, Any]],
) -> list[str]:
    current_keys = {str(item.get("dedupeKey") or "") for item in manifest_items}
    removed_ids = [
        str(item["id"])
        for key, item in previous_items_by_key.items()
        if key not in current_keys and item.get("id")
    ]
    return sorted(removed_ids)


def _sort_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(profiles, key=lambda p: str(p.get("slug") or p.get("name") or ""))


def _dedupe_profiles_by_key(
    profiles: list[dict[str, Any]],
    new_ids: set[str],
    updated_ids: set[str],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        item_id = str(profile.get("slug") or _slugify(str(profile.get("name") or "unknown")))
        key = dedupe_key_for_url(_canonical_url(profile), fallback_id=item_id)
        current = by_key.get(key)
        if current is None or _profile_priority(profile, new_ids, updated_ids) > _profile_priority(
            current, new_ids, updated_ids
        ):
            by_key[key] = profile
    return list(by_key.values())


def _profiles_for_daily_ids(profiles: list[dict[str, Any]], daily_ids: set[str]) -> list[dict[str, Any]]:
    if not daily_ids:
        return []
    return [profile for profile in profiles if _profile_item_id(profile) in daily_ids]


def _profile_priority(profile: dict[str, Any], new_ids: set[str], updated_ids: set[str]) -> tuple[int, int, str]:
    item_id = str(profile.get("slug") or "")
    if item_id in updated_ids:
        status_rank = 2
    elif item_id in new_ids:
        status_rank = 1
    else:
        status_rank = 0
    stars = profile.get("stars")
    star_rank = stars if isinstance(stars, int) else -1
    return (status_rank, star_rank, item_id)


def _run_timestamp(metadata: dict[str, Any]) -> str:
    timestamp = metadata.get("finished_at") or metadata.get("started_at")
    if isinstance(timestamp, str) and timestamp:
        return timestamp
    return datetime.now(timezone.utc).isoformat()


def _current_source_sha() -> str | None:
    if sha := os.getenv("GITHUB_SHA"):
        return sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _canonical_url(profile: dict[str, Any]) -> str | None:
    for key in ("github_url", "project_url", "paper_url"):
        value = profile.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _summary(profile: dict[str, Any]) -> str:
    body = str(profile.get("_body") or "").strip()
    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph and not paragraph.startswith("#"):
            return paragraph.replace("\n", " ")
    return str(profile.get("autonomy_rationale") or profile.get("name") or "No summary available.")


def _item_summary(profile: dict[str, Any], *, fallback_description: str) -> str:
    descriptor = _summary_descriptor(profile)
    domain = _summary_domain(profile)
    action = _summary_action(profile) or _clean_summary_text(fallback_description)
    article = "An" if descriptor[:1].lower() in {"a", "e", "i", "o", "u"} else "A"
    return f"{article} {descriptor} for {domain} that {action}."


def _summary_descriptor(profile: dict[str, Any]) -> str:
    interface = str(profile.get("interface") or "").lower()
    if any(token in interface for token in ("curated", "list", "directory", "survey")):
        return "curated reference repository"
    if "framework" in interface:
        return "framework"
    if "platform" in interface:
        return "platform"
    if "cli" in interface:
        return "CLI tool"
    if "library" in interface or "lib" in interface:
        return "library"
    if "agent" in interface:
        return "agentic system"
    if "github" in interface or "repository" in interface:
        return "open-source project"
    return "AI system"


def _summary_domain(profile: dict[str, Any]) -> str:
    domains = profile.get("domains")
    domain = domains[0] if isinstance(domains, list) and domains else "iterative AI"
    text = str(domain).strip()
    if text.lower() == "ml":
        return "ML workflows"
    if text.lower().endswith(("workflow", "workflows", "automation")):
        return text
    return f"{text} workflows"


def _summary_action(profile: dict[str, Any]) -> str | None:
    source = _known_string(profile.get("autonomy_rationale")) or _summary(profile)
    text = _clean_summary_text(source)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not sentences:
        return None
    sentence = next(
        (
            item
            for item in sentences
            if not item.lower().startswith(("this is ", "it is ", "the repository is "))
        ),
        sentences[0],
    )
    sentence = re.sub(
        r"^(it|this system|the system|the project|the repository)\s+",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    sentence = re.sub(
        r"^[A-Z][A-Za-z0-9_. -]{0,80}\s+is described as\s+",
        "provides ",
        sentence,
    )
    sentence = re.sub(
        r"^[A-Z][A-Za-z0-9_. -]{0,80}\s+is\s+(a|an|the)\s+",
        r"provides \1 ",
        sentence,
    )
    sentence = sentence.strip().rstrip(".")
    return sentence[:1].lower() + sentence[1:] if sentence else None


def _clean_summary_text(value: str) -> str:
    text = re.sub(r"^\*\*Autonomy level\*\*:.*?—\s*", "", value.strip())
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def _known_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in {"unknown", "null", "none", "n/a"}:
        return None
    return stripped


def _tags(profile: dict[str, Any]) -> list[str]:
    tags: set[str] = set()
    if profile.get("github_url"):
        tags.add("github")
    if profile.get("paper_url"):
        tags.add("academic")
    text = " ".join(
        str(value).lower()
        for value in [
            profile.get("domains"),
            profile.get("resource_requirements"),
            profile.get("interface"),
            profile.get("name"),
        ]
    )
    if any(token in text for token in ("lab", "chem", "bio", "equipment", "robot")):
        tags.add("lab")
    if any(token in text for token in ("survey", "review", "awesome", "curated")):
        tags.add("survey")
    return sorted(tags & ALLOWED_TAGS)


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _site_name(url: str | None) -> str | None:
    if not url:
        return None
    if "github.com" in url.lower():
        return "GitHub"
    if "arxiv.org" in url.lower():
        return "arXiv"
    return None


def _slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in slug.split("-") if part) or "unknown"


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in {"contentHash", "manifestHash"}
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
