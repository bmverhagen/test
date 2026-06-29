from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Article:
    """Normalized NU.nl article."""

    title: str
    url: str
    article_id: str | None = None
    summary: str | None = None
    category: str | None = None
    published_at: datetime | None = None
    image_url: str | None = None
    image_credit: str | None = None
    body: str | None = None
    source: str = "rss"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.published_at is not None:
            data["published_at"] = self.published_at.isoformat()
        return data
