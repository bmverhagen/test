"""Allow ``python -m booking_scraper``."""

import sys

from .cli import main

sys.exit(main())
