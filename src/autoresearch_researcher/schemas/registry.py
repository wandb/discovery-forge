"""Pydantic schema for the global tool registry."""

from datetime import datetime

from pydantic import BaseModel


class RegistryEntry(BaseModel):
    """A single entry in the global tool registry. One per unique tool."""

    slug: str
    name: str
    url: str
    first_seen_week: str
    last_updated_week: str
    last_profiled_at: datetime
    stars: int | None
    last_commit: str | None
