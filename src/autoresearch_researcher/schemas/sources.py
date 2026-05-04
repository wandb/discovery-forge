"""Pydantic schema for citation sources."""

from datetime import datetime
from pydantic import BaseModel


class Source(BaseModel):
    id: int
    url: str
    title: str
    fetched_at: datetime
    used_in: list[str]  # tool slugs
