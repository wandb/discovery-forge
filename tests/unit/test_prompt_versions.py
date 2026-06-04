"""Weave prompt versioning tests for the single researcher instruction."""

from types import SimpleNamespace


def _write_instruction_files(tmp_path):
    (tmp_path / "researcher.md").write_text("Find and profile one experiment-automation tool.")


def test_load_local_instruction_prompts_returns_researcher(tmp_path):
    from discovery_forge.tools.prompts import load_local_instruction_prompts

    _write_instruction_files(tmp_path)

    versions = load_local_instruction_prompts(max_tools=7, instructions_dir=tmp_path)

    assert set(versions) == {"researcher"}
    assert versions["researcher"].formatted_content == "Find and profile one experiment-automation tool."
    assert versions["researcher"].ref_uri is None


def test_publish_instruction_prompts_uses_registered_prompt_content(tmp_path, monkeypatch):
    from discovery_forge.tools import prompts

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
        return SimpleNamespace(get=lambda: SimpleNamespace(content="Registered researcher prompt."))

    monkeypatch.setattr(prompts.weave, "publish", fake_publish)
    monkeypatch.setattr(prompts.weave, "ref", fake_ref)

    versions = prompts.publish_instruction_prompts(max_tools=3, instructions_dir=tmp_path)

    assert published_names == ["researcher_instructions"]
    assert versions["researcher"].formatted_content == "Registered researcher prompt."
    assert versions["researcher"].ref_uri == "weave:///entity/project/object/researcher_instructions:v1"


def test_prompt_metadata_helpers_return_hashes_refs_and_contents(tmp_path):
    from discovery_forge.tools.prompts import (
        load_local_instruction_prompts,
        prompt_contents,
        prompt_hashes,
        prompt_refs,
    )

    _write_instruction_files(tmp_path)
    versions = load_local_instruction_prompts(max_tools=2, instructions_dir=tmp_path)

    assert set(prompt_hashes(versions)) == {"researcher"}
    assert prompt_refs(versions) == {"researcher": None}
    assert prompt_contents(versions)["researcher"] == "Find and profile one experiment-automation tool."
