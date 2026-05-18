"""WriterAgent: synthesizes tool profiles into the weekly briefing draft."""

import json
from pathlib import Path

import yaml
from agents import Agent, function_tool

from autoresearch_researcher.agents.discovery import load_instructions
from autoresearch_researcher.tools.persistence import save_comparison_table, save_draft


def generate_highlights(week_dir: Path, week: str) -> str:
    """
    Build the 'This Week's Highlights' section from per-week change files.

    Reads:
      {week_dir}/_new_candidates.jsonl  → tools first profiled this week
      {week_dir}/_updated_tools.jsonl   → tools whose stars/last_commit changed
    """
    new_file = week_dir / "_new_candidates.jsonl"
    updated_file = week_dir / "_updated_tools.jsonl"

    new_entries = _read_jsonl(new_file)
    updated_entries = _read_jsonl(updated_file)

    if not new_entries and not updated_entries:
        return f"## This Week's Highlights ({week})\n\nNo new tools discovered this week and no major updates to existing tools.\n"

    lines = [f"## This Week's Highlights ({week})", ""]

    if new_entries:
        lines.append(f"**New this week ({len(new_entries)}):**")
        lines.append("")
        for e in new_entries:
            stars = e.get("stars")
            stars_str = f" ({stars} stars)" if stars else ""
            lines.append(f"- **{e['name']}**{stars_str}")
        lines.append("")

    if updated_entries:
        lines.append(f"**Updated this week ({len(updated_entries)}):**")
        lines.append("")
        for e in updated_entries:
            stars = e.get("stars")
            stars_str = f" — now {stars} stars" if stars else ""
            lines.append(f"- {e['name']}{stars_str}")
        lines.append("")

    return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_tool_profiles_from_dir(tools_dir: Path) -> list[dict]:
    """Load all tool profile .md files from tools_dir, parse YAML front-matter."""
    if not tools_dir.exists():
        return []
    profiles = []
    for md_file in sorted(tools_dir.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        content = md_file.read_text()
        profile = _parse_frontmatter(content)
        if profile:
            profiles.append(profile)
    return profiles


def _parse_frontmatter(content: str) -> dict | None:
    """Extract YAML front-matter from a --- delimited markdown file."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
        data["_body"] = parts[2].strip()
        return data
    except yaml.YAMLError:
        return None


def _cell(value) -> str:
    """Render a table cell value, replacing None/empty with 'unknown'."""
    if value is None or value == "" or value == []:
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def generate_comparison_table(profiles: list[dict]) -> str:
    """Generate a markdown comparison table from a list of tool profile dicts."""
    header = (
        "| Tool Name | License | Domain | Autonomy Level | Interface"
        " | Resource Requirements | GitHub Stars | Last Commit | Price/TCO | Key Limitation |\n"
        "|-----------|---------|--------|----------------|----------"
        "|-----------------------|-------------|-------------|-----------|----------------|\n"
    )
    rows = []
    # Sort: Scientist → Analyst → Tool → other, then alphabetically
    order = {"scientist": 0, "analyst": 1, "tool": 2}
    sorted_profiles = sorted(
        profiles,
        key=lambda p: (order.get(p.get("autonomy_level", "").lower(), 3), p.get("name", "").lower()),
    )
    for p in sorted_profiles:
        limitations = p.get("key_limitations", [])
        first_limit = limitations[0] if limitations else "unknown"
        row = (
            f"| {_cell(p.get('name'))} "
            f"| {_cell(p.get('license'))} "
            f"| {_cell(p.get('domains'))} "
            f"| {_cell(p.get('autonomy_level'))} "
            f"| {_cell(p.get('interface'))} "
            f"| {_cell(p.get('resource_requirements'))} "
            f"| {_cell(p.get('stars'))} "
            f"| {_cell(p.get('last_commit'))} "
            f"| {_cell(p.get('pricing_note'))} "
            f"| {_cell(first_limit)} |"
        )
        rows.append(row)
    return header + "\n".join(rows) + "\n"


def build_writer_agent(
    output_dir: Path,
    week: str,
    registry=None,
    instructions_override: str | None = None,
) -> "Agent":
    """Build and return the WriterAgent.

    If `registry` is provided, profiles are read from the global registry
    (`_registry/profiles/`) instead of the per-week `tools/` directory.
    """
    profiles_dir = registry.profiles_dir if registry is not None else output_dir / "tools"

    @function_tool
    def save_draft_tool(content: str) -> str:
        """Save the main weekly briefing draft as draft.md."""
        save_draft(content, output_dir)
        return f"Saved draft.md to {output_dir}"

    @function_tool
    def save_comparison_table_tool(content: str) -> str:
        """Save the comparison table as comparison_table.md."""
        save_comparison_table(content, output_dir)
        return f"Saved comparison_table.md to {output_dir}"

    @function_tool
    def read_tool_profiles_tool() -> str:
        """Read all tool profiles from the registry/tools dir and return them as JSON."""
        profiles = load_tool_profiles_from_dir(profiles_dir)
        if not profiles:
            return "No tool profiles found."
        clean = [{k: v for k, v in p.items() if k != "_body"} for p in profiles]
        return json.dumps(clean, ensure_ascii=False, indent=2)

    @function_tool
    def get_tool_body_tool(slug: str) -> str:
        """Return the body text of a specific tool profile by slug."""
        md_file = profiles_dir / f"{slug}.md"
        if not md_file.exists():
            return f"Profile not found: {slug}"
        profiles = _parse_frontmatter(md_file.read_text())
        return profiles.get("_body", "") if profiles else ""

    @function_tool
    def read_highlights_tool() -> str:
        """Read the pre-generated highlights.md for this week."""
        path = output_dir / "highlights.md"
        if not path.exists():
            return ""
        return path.read_text()

    instructions = instructions_override or load_instructions("writer")

    return Agent(
        name="WriterAgent",
        instructions=instructions,
        tools=[
            save_draft_tool,
            save_comparison_table_tool,
            read_tool_profiles_tool,
            get_tool_body_tool,
            read_highlights_tool,
        ],
        model="gpt-5.4-mini",
    )
