"""Pydantic schemas for tool candidates discovered by DiscoveryAgent."""

from pydantic import BaseModel


class Candidate(BaseModel):
    name: str
    url: str
    description: str
    category: str


class RejectedCandidate(BaseModel):
    name: str
    url: str
    description: str
    category: str
    rejection_reason: str
