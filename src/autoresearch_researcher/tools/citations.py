"""Citation integrity verification and source registry."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from autoresearch_researcher.schemas.sources import Source


def verify_citations(report: str, sources: list[Source]) -> list[str]:
    """
    Verify citation integrity of a report against the known source list.

    Returns a list of error strings (empty = clean).
    Checks:
    1. All [^N] references in the report correspond to a source ID.
    2. All sources are cited at least once (orphan warning).
    """
    cited_ids = {int(m) for m in re.findall(r'\[\^(\d+)\]', report)}
    available_ids = {s.id for s in sources}

    errors: list[str] = []

    missing = cited_ids - available_ids
    if missing:
        errors.append(f"Missing source IDs (cited but not registered): {sorted(missing)}")

    orphans = available_ids - cited_ids
    if orphans:
        errors.append(f"Orphan sources (registered but never cited): {sorted(orphans)}")

    return errors


class SourceRegistry:
    """
    Thread-safe (single-process) registry that assigns sequential IDs to sources
    and deduplicates by URL.
    """

    def __init__(self, sources_file: Path) -> None:
        self._file = sources_file
        self._url_to_id: dict[str, int] = {}
        self._sources: list[Source] = []
        self._next_id = 1
        self._load_existing()

    def _load_existing(self) -> None:
        if not self._file.exists():
            return
        for line in self._file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            s = Source(**data)
            self._sources.append(s)
            self._url_to_id[s.url] = s.id
            self._next_id = max(self._next_id, s.id + 1)

    def register(self, url: str, title: str, used_in: str) -> int:
        """
        Register a source URL and return its ID.
        Deduplicates by URL; adds tool slug to used_in on re-registration.
        """
        if url in self._url_to_id:
            existing_id = self._url_to_id[url]
            # Update used_in to include this slug
            for s in self._sources:
                if s.id == existing_id and used_in not in s.used_in:
                    s.used_in.append(used_in)
                    self._rewrite()
            return existing_id

        source = Source(
            id=self._next_id,
            url=url,
            title=title,
            fetched_at=datetime.now(timezone.utc),
            used_in=[used_in],
        )
        self._sources.append(source)
        self._url_to_id[url] = self._next_id
        self._next_id += 1
        self._append(source)
        return source.id

    def _append(self, source: Source) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with self._file.open("a") as f:
            f.write(source.model_dump_json() + "\n")

    def _rewrite(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with self._file.open("w") as f:
            for s in self._sources:
                f.write(s.model_dump_json() + "\n")
