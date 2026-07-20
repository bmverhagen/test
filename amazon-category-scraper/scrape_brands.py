#!/usr/bin/env python3
"""Convenience entrypoint: python scrape_brands.py <CATEGORY_URL> [options]."""

import sys

from amazon_category_scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())
