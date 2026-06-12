"""Direct Turso upsert for daily discovery-forge feed output.

The local ``daily_runs/<day>/`` artifacts stay as the Weave review and debug
source of truth. This module reads the already-built manifest plus item payloads
and upserts them into the Agentforge Turso database, so the dashboard reads
straight from Turso instead of from committed feed files.

When ``DB_DISCOVERY_FORGE_URL`` is unset, ``write_feed_to_turso`` returns ``None``
and writes nothing. That is the documented skip path, not a fallback.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_feed_to_turso(
    day_dir: Path,
    manifest: dict[str, Any],
    day: str,
) -> dict[str, Any] | None:
    """Upsert one daily feed run into the Agentforge Turso database.

    Returns a result summary, or ``None`` when ``DB_DISCOVERY_FORGE_URL`` is unset.
    """
    db_url = os.getenv("DB_DISCOVERY_FORGE_URL")
    if not db_url:
        return None

    from libsql_client import create_client_sync

    auth_token = os.getenv("DB_DISCOVERY_FORGE_AUTH_TOKEN")
    run_id = str(manifest.get("runId") or day)
    report_id = f"repo-a-{run_id}"
    started_at = _now()

    if auth_token:
        client = create_client_sync(url=_client_url(db_url), auth_token=auth_token)
    else:
        client = create_client_sync(url=_client_url(db_url))

    inserted = 0
    updated = 0
    skipped = 0
    try:
        items = _load_items(day_dir, manifest)
        _upsert_report(client, report_id=report_id, run_id=run_id, manifest=manifest, item_count=len(items))

        client.execute(
            "DELETE FROM autoresearch_report_items WHERE report_id = ?",
            [report_id],
        )
        for rank, (manifest_item, payload) in enumerate(items, start=1):
            item_id, status = _upsert_item(client, payload)
            if status == "inserted":
                inserted += 1
            elif status == "updated":
                updated += 1
            else:
                skipped += 1
            _insert_report_item(
                client,
                report_id=report_id,
                item_id=item_id,
                rank=rank,
                change_status=str(manifest_item.get("changeStatus") or "unchanged"),
            )

        _write_sync_run(
            client,
            run_id=run_id,
            manifest=manifest,
            status="success",
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            error=None,
            started_at=started_at,
            finished_at=_now(),
        )
        return {
            "status": "success",
            "runId": run_id,
            "insertedCount": inserted,
            "updatedCount": updated,
            "skippedCount": skipped,
        }
    except Exception as exc:
        _write_sync_run(
            client,
            run_id=run_id,
            manifest=manifest,
            status="error",
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            error=str(exc),
            started_at=started_at,
            finished_at=_now(),
        )
        raise
    finally:
        client.close()


def _load_items(day_dir: Path, manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in manifest.get("items") or []:
        rel_path = entry.get("path") or f"items/{entry['id']}.json"
        payload = json.loads((day_dir / rel_path).read_text())
        items.append((entry, payload))
    return items


def _client_url(db_url: str) -> str:
    """Use Turso's HTTP endpoint for Python libsql-client remote writes."""
    if db_url.startswith("libsql://"):
        return "https://" + db_url.removeprefix("libsql://")
    return db_url


def _upsert_report(
    client: Any,
    *,
    report_id: str,
    run_id: str,
    manifest: dict[str, Any],
    item_count: int,
) -> None:
    delta = manifest.get("delta") or {}
    new_count = len(delta.get("newItemIds") or [])
    updated_count = len(delta.get("updatedItemIds") or [])
    run_date = manifest.get("runDate") or run_id
    title = f"Discovery Forge {run_date}"
    summary = f"{item_count} items ({new_count} new, {updated_count} updated)"
    metadata = json.dumps(
        {
            "cadence": manifest.get("cadence"),
            "sourceRange": manifest.get("sourceRange"),
            "delta": manifest.get("delta"),
        },
        ensure_ascii=False,
    )
    published_at = manifest.get("publishedAt") or _now()
    updated_at = manifest.get("updatedAt") or _now()

    existing = client.execute(
        "SELECT id FROM autoresearch_reports WHERE run_id = ?",
        [run_id],
    ).rows
    if existing:
        client.execute(
            """
            UPDATE autoresearch_reports
            SET run_date = ?, title = ?, summary = ?, manifest_hash = ?, source_sha = ?,
                published_at = ?, updated_at = ?, generated_at = ?, weave_trace_id = ?, metadata = ?
            WHERE run_id = ?
            """,
            [
                run_date,
                title,
                summary,
                manifest.get("manifestHash"),
                manifest.get("sourceSha"),
                published_at,
                updated_at,
                manifest.get("generatedAt"),
                manifest.get("weaveTraceId"),
                metadata,
                run_id,
            ],
        )
        return

    client.execute(
        """
        INSERT INTO autoresearch_reports (
            id, run_id, run_date, title, summary, manifest_hash, source_sha,
            published_at, updated_at, generated_at, weave_trace_id, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            report_id,
            run_id,
            run_date,
            title,
            summary,
            manifest.get("manifestHash"),
            manifest.get("sourceSha"),
            published_at,
            updated_at,
            manifest.get("generatedAt"),
            manifest.get("weaveTraceId"),
            metadata,
        ],
    )


def _upsert_item(client: Any, payload: dict[str, Any]) -> tuple[str, str]:
    dedupe_key = str(payload["dedupeKey"])
    content_hash = str(payload["contentHash"])
    existing = client.execute(
        "SELECT id, content_hash FROM autoresearch_items WHERE dedupe_key = ?",
        [dedupe_key],
    ).rows
    if existing:
        item_id = str(existing[0][0])
        if str(existing[0][1]) == content_hash:
            return item_id, "skipped"
        _update_item(client, payload, dedupe_key=dedupe_key)
        return item_id, "updated"
    _insert_item(client, payload, dedupe_key=dedupe_key)
    return str(payload["id"]), "inserted"


def _insert_item(client: Any, payload: dict[str, Any], *, dedupe_key: str) -> None:
    md = payload.get("metadata") or {}
    item_id = str(payload["id"])
    client.execute(
        """
        INSERT INTO autoresearch_items (
            id, dedupe_key, source_type, source_item_id, canonical_url, title, page_title,
            page_metadata, summary, category, tags, page_published_at, source_updated_at,
            content_hash, github_stars, license, domain, autonomy_level, interface_type,
            resource_requirements, key_limitation, raw_payload, weave_trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            item_id,
            dedupe_key,
            "repository",
            item_id,
            payload.get("canonicalUrl"),
            payload.get("title"),
            payload.get("pageTitle"),
            json.dumps(payload.get("pageMetadata") or {}, ensure_ascii=False),
            payload.get("summary"),
            _category(md),
            json.dumps(payload.get("tags") or [], ensure_ascii=False),
            payload.get("pagePublishedAt"),
            payload.get("sourceUpdatedAt"),
            str(payload["contentHash"]),
            md.get("githubStars"),
            md.get("license"),
            md.get("domain"),
            md.get("autonomyLevel"),
            md.get("interfaceType"),
            md.get("resourceRequirements"),
            md.get("keyLimitation"),
            json.dumps(payload, ensure_ascii=False),
            payload.get("weaveTraceId"),
        ],
    )


def _update_item(client: Any, payload: dict[str, Any], *, dedupe_key: str) -> None:
    md = payload.get("metadata") or {}
    item_id = str(payload["id"])
    client.execute(
        """
        UPDATE autoresearch_items
        SET source_item_id = ?, canonical_url = ?, title = ?, page_title = ?, page_metadata = ?,
            summary = ?, category = ?, tags = ?, page_published_at = ?, source_updated_at = ?,
            content_hash = ?, github_stars = ?, license = ?, domain = ?, autonomy_level = ?,
            interface_type = ?, resource_requirements = ?, key_limitation = ?, raw_payload = ?,
            weave_trace_id = ?, updated_at = ?
        WHERE dedupe_key = ?
        """,
        [
            item_id,
            payload.get("canonicalUrl"),
            payload.get("title"),
            payload.get("pageTitle"),
            json.dumps(payload.get("pageMetadata") or {}, ensure_ascii=False),
            payload.get("summary"),
            _category(md),
            json.dumps(payload.get("tags") or [], ensure_ascii=False),
            payload.get("pagePublishedAt"),
            payload.get("sourceUpdatedAt"),
            str(payload["contentHash"]),
            md.get("githubStars"),
            md.get("license"),
            md.get("domain"),
            md.get("autonomyLevel"),
            md.get("interfaceType"),
            md.get("resourceRequirements"),
            md.get("keyLimitation"),
            json.dumps(payload, ensure_ascii=False),
            payload.get("weaveTraceId"),
            _now(),
            dedupe_key,
        ],
    )


def _insert_report_item(
    client: Any,
    *,
    report_id: str,
    item_id: str,
    rank: int,
    change_status: str,
) -> None:
    client.execute(
        """
        INSERT INTO autoresearch_report_items (id, report_id, item_id, rank, change_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        [f"{report_id}:{item_id}", report_id, item_id, rank, change_status],
    )


def _write_sync_run(
    client: Any,
    *,
    run_id: str,
    manifest: dict[str, Any],
    status: str,
    inserted: int,
    updated: int,
    skipped: int,
    error: str | None,
    started_at: str,
    finished_at: str,
) -> None:
    client.execute(
        """
        INSERT INTO autoresearch_sync_runs (
            id, run_id, source_sha, manifest_hash, status,
            inserted_count, updated_count, skipped_count, error, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            str(uuid.uuid4()),
            run_id,
            manifest.get("sourceSha"),
            manifest.get("manifestHash"),
            status,
            inserted,
            updated,
            skipped,
            error,
            started_at,
            finished_at,
        ],
    )


def _category(metadata: dict[str, Any]) -> str:
    domain = metadata.get("domain")
    if isinstance(domain, str):
        stripped = domain.strip()
        if stripped and stripped.lower() not in {"unknown", "null", "none", "n/a"}:
            return stripped
    return "research-tool"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
