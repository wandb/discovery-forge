"""Persistence tools: save candidates, profiles, drafts."""

import json
from pathlib import Path

from autoresearch_researcher.schemas.candidate import Candidate, RejectedCandidate


def save_candidate(candidate: Candidate, output_file: Path) -> None:
    """Append a candidate to the JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a") as f:
        f.write(json.dumps(candidate.model_dump()) + "\n")


def save_rejected_candidate(candidate: RejectedCandidate, output_file: Path) -> None:
    """Append a rejected candidate (with reason) to a separate JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("a") as f:
        f.write(json.dumps(candidate.model_dump()) + "\n")


def load_candidates(candidates_file: Path) -> list[Candidate]:
    """Load all accepted candidates from a JSONL file."""
    if not candidates_file.exists():
        return []
    candidates = []
    for line in candidates_file.read_text().splitlines():
        line = line.strip()
        if line:
            candidates.append(Candidate(**json.loads(line)))
    return candidates
