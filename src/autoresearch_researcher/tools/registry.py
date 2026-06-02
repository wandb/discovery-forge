"""ToolRegistry: global tool accumulator across daily runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from autoresearch_researcher.schemas.registry import RegistryEntry
from autoresearch_researcher.schemas.tool_profile import ToolProfile
from autoresearch_researcher.tools.persistence import save_tool_profile


def _normalize_url(url: str) -> str:
    """Normalize URL for dedup: lowercase, strip trailing slash."""
    return url.strip().rstrip("/").lower()


class ToolRegistry:
    """
    Global registry of all known tools across daily runs.

    Persistence layout:
        {registry_dir}/
        ├── tools.jsonl        # one RegistryEntry per line
        ├── profiles/{slug}.md # canonical ToolProfile per tool
        └── sources.jsonl      # cumulative sources (managed externally)
    """

    def __init__(self, registry_dir: Path) -> None:
        self.registry_dir = registry_dir
        self.tools_file = registry_dir / "tools.jsonl"
        self.profiles_dir = registry_dir / "profiles"
        self._entries: list[RegistryEntry] = []
        self._url_index: dict[str, int] = {}  # normalized_url → index in _entries

    @classmethod
    def load(cls, registry_dir: Path) -> "ToolRegistry":
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "profiles").mkdir(parents=True, exist_ok=True)

        reg = cls(registry_dir)
        if reg.tools_file.exists():
            for line in reg.tools_file.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = RegistryEntry(**json.loads(line))
                reg._entries.append(entry)
                reg._url_index[_normalize_url(entry.url)] = len(reg._entries) - 1
        return reg

    def contains(self, url: str) -> bool:
        return _normalize_url(url) in self._url_index

    def add(self, profile: ToolProfile, day: str) -> bool:
        """
        Add a tool to the registry. If it already exists, update last_updated_day.
        Returns True if newly added, False if already existed.
        """
        url = profile.github_url or profile.project_url or profile.paper_url or ""
        norm = _normalize_url(url)
        now = datetime.now(timezone.utc)

        if norm in self._url_index:
            idx = self._url_index[norm]
            entry = self._entries[idx]
            entry.last_updated_day = day
            entry.last_profiled_at = now
            if profile.stars is not None:
                entry.stars = profile.stars
            if profile.last_commit is not None:
                entry.last_commit = profile.last_commit
            self._rewrite_tools_jsonl()
            # Overwrite the canonical profile (newer info wins)
            save_tool_profile(profile, self.profiles_dir)
            return False

        entry = RegistryEntry(
            slug=profile.slug,
            name=profile.name,
            url=url,
            first_seen_day=day,
            last_updated_day=day,
            last_profiled_at=now,
            stars=profile.stars,
            last_commit=profile.last_commit,
        )
        self._entries.append(entry)
        self._url_index[norm] = len(self._entries) - 1

        with self.tools_file.open("a") as f:
            f.write(entry.model_dump_json() + "\n")
        save_tool_profile(profile, self.profiles_dir)
        return True

    def update_metadata(
        self, slug: str, stars: int | None, last_commit: str | None, day: str
    ) -> bool:
        """
        Update an entry's stars/last_commit only. Returns True if anything changed.
        """
        for entry in self._entries:
            if entry.slug == slug:
                changed = False
                if stars is not None and entry.stars != stars:
                    entry.stars = stars
                    changed = True
                if last_commit is not None and entry.last_commit != last_commit:
                    entry.last_commit = last_commit
                    changed = True
                if changed:
                    entry.last_updated_day = day
                    entry.last_profiled_at = datetime.now(timezone.utc)
                    self._rewrite_tools_jsonl()
                return changed
        return False

    def get_all_entries(self) -> list[RegistryEntry]:
        return list(self._entries)

    def get_all_profiles(self) -> list[dict]:
        """Return all profile front-matter dicts from profiles/*.md."""
        from autoresearch_researcher.tools.profiles import load_tool_profiles_from_dir
        return load_tool_profiles_from_dir(self.profiles_dir)

    def _rewrite_tools_jsonl(self) -> None:
        with self.tools_file.open("w") as f:
            for entry in self._entries:
                f.write(entry.model_dump_json() + "\n")
