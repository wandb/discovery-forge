"""
Migrate existing per-day tool profiles into the global registry.

Usage:
    uv run python scripts/migrate_to_registry.py daily_runs/2026-05-19 2026-05-19

Reads {day_dir}/tools/*.md and adds each profile to daily_runs/_registry/.
Existing day_dir is left untouched (rollback-safe).
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from autoresearch_researcher.schemas.tool_profile import ToolProfile  # noqa: E402
from autoresearch_researcher.tools.registry import ToolRegistry  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <day_dir> <day_id>")
        sys.exit(1)

    day_dir = Path(sys.argv[1])
    day_id = sys.argv[2]

    if not day_dir.exists():
        print(f"ERROR: {day_dir} does not exist")
        sys.exit(1)

    tools_dir = day_dir / "tools"
    if not tools_dir.exists():
        print(f"ERROR: {tools_dir} does not exist")
        sys.exit(1)

    registry_dir = day_dir.parent / "_registry"
    registry = ToolRegistry.load(registry_dir)
    print(f"Loaded registry at {registry_dir} ({len(registry.get_all_entries())} existing entries)")

    added = 0
    skipped = 0
    for md_file in sorted(tools_dir.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        content = md_file.read_text()
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        front = yaml.safe_load(parts[1])

        # Drop the body field added by writer agent's loader
        front.pop("_body", None)
        # Default missing fields for legacy profiles (pre-key_limitations frontmatter)
        front.setdefault("key_limitations", [])

        try:
            profile = ToolProfile(**front)
        except Exception as e:
            print(f"  SKIP {md_file.name}: invalid front-matter ({e})")
            skipped += 1
            continue

        is_new = registry.add(profile, day=day_id)
        status = "NEW" if is_new else "UPDATED"
        print(f"  {status:8} {profile.slug}")
        if is_new:
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} added, {skipped} updated/skipped")
    print(f"Registry now has {len(registry.get_all_entries())} entries.")


if __name__ == "__main__":
    main()
