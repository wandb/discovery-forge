"""Weave prompt versioning tests for agent instructions."""

from types import SimpleNamespace


def _write_instruction_files(tmp_path):
    instructions = {
        "discovery.md": "Find up to {max_tools} tools.",
        "profiler.md": "Profile one tool.",
        "writer.md": "Write {Tool Name} cards without formatting variables.",
    }
    for filename, content in instructions.items():
        (tmp_path / filename).write_text(content)


def test_load_local_instruction_prompts_formats_discovery_only(tmp_path):
    from autoresearch_researcher.tools.prompts import load_local_instruction_prompts

    _write_instruction_files(tmp_path)

    versions = load_local_instruction_prompts(max_tools=7, instructions_dir=tmp_path)

    assert versions["discovery"].formatted_content == "Find up to 7 tools."
    assert versions["profiler"].formatted_content == "Profile one tool."
    assert versions["writer"].formatted_content == "Write {Tool Name} cards without formatting variables."
    assert versions["discovery"].ref_uri is None


def test_publish_instruction_prompts_uses_registered_prompt_content(tmp_path, monkeypatch):
    from autoresearch_researcher.tools import prompts

    _write_instruction_files(tmp_path)
    published_names = []

    class FakeRef:
        def __init__(self, name: str) -> None:
            self._name = name

        def uri(self) -> str:
            return f"weave:///entity/project/object/{self._name}:v1"

    def fake_publish(prompt, name):
        published_names.append(name)
        return FakeRef(name)

    def fake_ref(uri):
        if "discovery" in uri:
            return SimpleNamespace(get=lambda: SimpleNamespace(content="Registered {max_tools} discovery."))
        if "profiler" in uri:
            return SimpleNamespace(get=lambda: SimpleNamespace(content="Registered profiler."))
        return SimpleNamespace(get=lambda: SimpleNamespace(content="Registered writer."))

    monkeypatch.setattr(prompts.weave, "publish", fake_publish)
    monkeypatch.setattr(prompts.weave, "ref", fake_ref)

    versions = prompts.publish_instruction_prompts(max_tools=3, instructions_dir=tmp_path)

    assert published_names == [
        "autoresearch-discovery-instructions",
        "autoresearch-profiler-instructions",
        "autoresearch-writer-instructions",
    ]
    assert versions["discovery"].formatted_content == "Registered 3 discovery."
    assert versions["profiler"].formatted_content == "Registered profiler."
    assert versions["writer"].ref_uri == "weave:///entity/project/object/autoresearch-writer-instructions:v1"


def test_prompt_metadata_helpers_return_hashes_refs_and_contents(tmp_path):
    from autoresearch_researcher.tools.prompts import (
        load_local_instruction_prompts,
        prompt_contents,
        prompt_hashes,
        prompt_refs,
    )

    _write_instruction_files(tmp_path)
    versions = load_local_instruction_prompts(max_tools=2, instructions_dir=tmp_path)

    assert set(prompt_hashes(versions)) == {"discovery", "profiler", "writer"}
    assert prompt_refs(versions) == {"discovery": None, "profiler": None, "writer": None}
    assert prompt_contents(versions)["discovery"] == "Find up to 2 tools."
