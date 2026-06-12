import json
from pathlib import Path

from tests.unit.test_feed_export import _bootstrap_day_dir


def _create_autoresearch_schema(db_path: Path) -> None:
    from libsql_client import create_client_sync

    client = create_client_sync(url=f"file:{db_path}")
    try:
        client.execute(
            """
            CREATE TABLE autoresearch_reports (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL UNIQUE,
              run_date TEXT,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              manifest_hash TEXT,
              source_sha TEXT,
              published_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              generated_at TEXT,
              weave_trace_id TEXT,
              metadata TEXT DEFAULT '{}',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        client.execute(
            """
            CREATE TABLE autoresearch_items (
              id TEXT PRIMARY KEY,
              dedupe_key TEXT NOT NULL UNIQUE,
              source_type TEXT NOT NULL DEFAULT 'repository',
              source_item_id TEXT,
              canonical_url TEXT NOT NULL,
              title TEXT NOT NULL,
              page_title TEXT,
              page_metadata TEXT DEFAULT '{}',
              summary TEXT NOT NULL,
              category TEXT NOT NULL,
              tags TEXT NOT NULL DEFAULT '[]',
              page_published_at TEXT,
              source_updated_at TEXT,
              content_hash TEXT NOT NULL,
              github_stars INTEGER,
              license TEXT,
              domain TEXT,
              autonomy_level TEXT,
              interface_type TEXT,
              resource_requirements TEXT,
              key_limitation TEXT,
              raw_payload TEXT DEFAULT '{}',
              created_by_user_id INTEGER,
              favorite_count INTEGER NOT NULL DEFAULT 0,
              comment_count INTEGER NOT NULL DEFAULT 0,
              good_count INTEGER NOT NULL DEFAULT 0,
              bad_count INTEGER NOT NULL DEFAULT 0,
              weave_trace_id TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        client.execute(
            """
            CREATE TABLE autoresearch_report_items (
              id TEXT PRIMARY KEY,
              report_id TEXT NOT NULL,
              item_id TEXT NOT NULL,
              rank INTEGER NOT NULL DEFAULT 0,
              change_status TEXT NOT NULL DEFAULT 'unchanged',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(report_id, item_id)
            )
            """
        )
        client.execute(
            """
            CREATE TABLE autoresearch_sync_runs (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              source_sha TEXT,
              manifest_hash TEXT,
              status TEXT NOT NULL,
              inserted_count INTEGER NOT NULL DEFAULT 0,
              updated_count INTEGER NOT NULL DEFAULT 0,
              skipped_count INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              started_at TEXT NOT NULL,
              finished_at TEXT
            )
            """
        )
    finally:
        client.close()


def test_write_feed_to_turso_skips_without_db_url(tmp_path, monkeypatch):
    from discovery_forge.tools.feed import build_feed_output
    from discovery_forge.tools.turso_feed import write_feed_to_turso

    monkeypatch.delenv("DB_DISCOVERY_FORGE_URL", raising=False)

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    assert write_feed_to_turso(day_dir, manifest, "2026-05-28") is None


def test_write_feed_to_turso_upserts_report_items_and_sync_run(tmp_path, monkeypatch):
    from libsql_client import create_client_sync

    from discovery_forge.tools.feed import build_feed_output
    from discovery_forge.tools.turso_feed import write_feed_to_turso

    db_path = tmp_path / "autoresearch.db"
    _create_autoresearch_schema(db_path)
    monkeypatch.setenv("DB_DISCOVERY_FORGE_URL", f"file:{db_path}")

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    result = write_feed_to_turso(day_dir, manifest, "2026-05-28")
    assert result is not None
    assert result["status"] == "success"
    assert result["runId"] == "2026-05-28"
    assert result["insertedCount"] == 1
    assert result["updatedCount"] == 0
    assert result["skippedCount"] == 0

    client = create_client_sync(url=f"file:{db_path}")
    try:
        report = client.execute(
            "SELECT id, run_id, manifest_hash FROM autoresearch_reports WHERE run_id = ?",
            ["2026-05-28"],
        ).rows[0]
        assert report[0] == "repo-a-2026-05-28"
        assert report[1] == "2026-05-28"
        assert report[2] == manifest["manifestHash"]

        item = client.execute(
            "SELECT id, dedupe_key, content_hash, weave_trace_id, page_metadata FROM autoresearch_items",
        ).rows[0]
        assert item[0] == "tool-a"
        item_payload = json.loads((day_dir / "items" / "tool-a.json").read_text())
        assert item[1] == item_payload["dedupeKey"]
        assert item[2] == item_payload["contentHash"]
        assert item[3] == item_payload["weaveTraceId"]
        item_page_metadata = json.loads(item[4])
        assert item_page_metadata["weave_call_id"] == "call-tool-a"

        relation = client.execute(
            """
            SELECT report_id, item_id, rank, change_status
            FROM autoresearch_report_items
            """,
        ).rows[0]
        assert relation[0] == "repo-a-2026-05-28"
        assert relation[1] == "tool-a"
        assert relation[2] == 1
        assert relation[3] == "new"

        sync_run = client.execute(
            "SELECT status, inserted_count, updated_count, skipped_count FROM autoresearch_sync_runs",
        ).rows[0]
        assert sync_run[0] == "success"
        assert sync_run[1] == 1
        assert sync_run[2] == 0
        assert sync_run[3] == 0
    finally:
        client.close()


def test_write_feed_to_turso_skips_unchanged_item_on_rerun(tmp_path, monkeypatch):
    from libsql_client import create_client_sync

    from discovery_forge.tools.feed import build_feed_output
    from discovery_forge.tools.turso_feed import write_feed_to_turso

    db_path = tmp_path / "autoresearch.db"
    _create_autoresearch_schema(db_path)
    monkeypatch.setenv("DB_DISCOVERY_FORGE_URL", f"file:{db_path}")

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")

    write_feed_to_turso(day_dir, manifest, "2026-05-28")
    result = write_feed_to_turso(day_dir, manifest, "2026-05-28")

    assert result is not None
    assert result["insertedCount"] == 0
    assert result["updatedCount"] == 0
    assert result["skippedCount"] == 1

    client = create_client_sync(url=f"file:{db_path}")
    try:
        sync_runs = client.execute(
            "SELECT status FROM autoresearch_sync_runs ORDER BY started_at",
        ).rows
        assert len(sync_runs) == 2
        assert sync_runs[-1][0] == "success"
    finally:
        client.close()


def test_write_feed_to_turso_links_existing_dedupe_item_id(tmp_path, monkeypatch):
    from libsql_client import create_client_sync

    from discovery_forge.tools.feed import build_feed_output
    from discovery_forge.tools.turso_feed import write_feed_to_turso

    db_path = tmp_path / "autoresearch.db"
    _create_autoresearch_schema(db_path)
    monkeypatch.setenv("DB_DISCOVERY_FORGE_URL", f"file:{db_path}")

    day_dir = tmp_path / "2026-05-28"
    day_dir.mkdir()
    _bootstrap_day_dir(day_dir)
    manifest = build_feed_output(day_dir, registry=None, day="2026-05-28", source_sha="abc123")
    item_payload = json.loads((day_dir / "items" / "tool-a.json").read_text())

    client = create_client_sync(url=f"file:{db_path}")
    try:
        client.execute(
            """
            INSERT INTO autoresearch_items (
              id, dedupe_key, canonical_url, title, summary, category, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "existing-tool-a",
                item_payload["dedupeKey"],
                item_payload["canonicalUrl"],
                item_payload["title"],
                item_payload["summary"],
                "ml",
                item_payload["contentHash"],
            ],
        )
    finally:
        client.close()

    result = write_feed_to_turso(day_dir, manifest, "2026-05-28")

    assert result is not None
    assert result["skippedCount"] == 1

    client = create_client_sync(url=f"file:{db_path}")
    try:
        relation = client.execute(
            "SELECT item_id FROM autoresearch_report_items WHERE report_id = ?",
            ["repo-a-2026-05-28"],
        ).rows[0]
        assert relation[0] == "existing-tool-a"
    finally:
        client.close()
