"""Amazon product description scraper — HTML + plug-in JSON providers."""

from .models import Marketplace, ProductDescription, ProviderName
from .scraper import DescriptionScraper

__all__ = [
    "DescriptionScraper",
    "Marketplace",
    "ProductDescription",
    "ProviderName",
]

__version__ = "0.1.0"
