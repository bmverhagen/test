"""Allow running as ``python -m amazon_category_scraper``."""

import sys

from .cli import main

sys.exit(main())
