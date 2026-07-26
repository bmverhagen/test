from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Marketplace, ProductDescription


class Provider(ABC):
    name: str

    @abstractmethod
    def fetch(self, asin: str, marketplace: Marketplace) -> ProductDescription:
        """Return a product description for *asin* on *marketplace*."""
