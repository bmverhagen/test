#!/usr/bin/env python3
"""Convenience entrypoint: python scrape.py [options]."""

import sys

from booking_scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())
