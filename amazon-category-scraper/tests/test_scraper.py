import unittest
from pathlib import Path

from amazon_category_scraper.fetcher import FetchError, looks_like_robot_check
from amazon_category_scraper.scraper import CategoryBrandScraper, merge_pages
from amazon_category_scraper.urls import NotACategoryPageError

FIXTURES = Path(__file__).parent / "fixtures"

PAGE_1_URL = "https://www.amazon.com/s?k=televisions"
PAGE_2_URL = "https://www.amazon.com/s?k=televisions&page=2&qid=1721400000&ref=sr_pg_2"
BSR_URL = "https://www.amazon.com/Best-Sellers-Coffee-Machines/zgbs/kitchen/289745/"
BSR_SIBLING_URL = "https://www.amazon.com/s?rh=n%3A289745&fs=true"

# Minimal search listing for node 289745 whose sidebar names one brand.
BSR_SIBLING_HTML = """
<div id="brandsRefinements">
  <ul aria-labelledby="p_123-title">
    <li id="p_123/1"><span class="a-label a-checkbox-label">Keurig</span></li>
  </ul>
</div>
"""


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """In-memory Fetcher replacement; records every URL requested."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.requested: list[str] = []

    def fetch(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.responses:
            raise FetchError(f"unexpected fetch: {url}")
        return self.responses[url]


class ScraperTests(unittest.TestCase):
    def _scraper(self, responses: dict[str, str], **kwargs) -> tuple[CategoryBrandScraper, FakeFetcher]:
        fetcher = FakeFetcher(responses)
        return CategoryBrandScraper(fetcher=fetcher, delay=0, **kwargs), fetcher

    def test_rejects_product_urls_without_fetching(self):
        scraper, fetcher = self._scraper({})
        with self.assertRaises(NotACategoryPageError):
            scraper.scrape(["https://www.amazon.com/dp/B0CV9WPMWQ"])
        self.assertEqual(fetcher.requested, [])

    def test_single_page_scrape_merges_all_sources(self):
        scraper, fetcher = self._scraper({PAGE_1_URL: load("category_page_1.html")})
        report = scraper.scrape([PAGE_1_URL])

        self.assertEqual(fetcher.requested, [PAGE_1_URL])
        self.assertEqual(report.pages_scraped, 1)
        self.assertEqual(report.product_cards_seen, 6)

        by_name = {record.name.casefold(): record for record in report.brands}
        # Samsung: sidebar + 2 product cards, deduplicated case-insensitively.
        samsung = by_name["samsung"]
        self.assertEqual(samsung.product_mentions, 2)
        self.assertEqual(samsung.sources, ("brand_filter", "product_card"))
        # Hisense: sidebar + structured data only, no cards.
        hisense = by_name["hisense"]
        self.assertEqual(hisense.product_mentions, 0)
        self.assertEqual(hisense.sources, ("brand_filter", "structured_data"))
        # Sorted by product mentions first.
        self.assertEqual(report.brands[0].name.casefold(), "samsung")

    def test_pagination_follows_next_link_until_last_page(self):
        scraper, fetcher = self._scraper(
            {
                PAGE_1_URL: load("category_page_1.html"),
                PAGE_2_URL: load("category_page_2.html"),
            },
            max_pages=5,
        )
        report = scraper.scrape([PAGE_1_URL])

        # Page 2's "Next" is disabled, so exactly two fetches happen.
        self.assertEqual(fetcher.requested, [PAGE_1_URL, PAGE_2_URL])
        self.assertEqual(report.pages_scraped, 2)
        names = {record.name.casefold() for record in report.brands}
        self.assertIn("lg", names)  # legacy byline on page 2
        self.assertIn("bose", names)  # h5 layout on page 2
        # Listing positions continue across pages: 6 cards, then 3 more.
        self.assertEqual([p.rank for p in report.products], list(range(1, 10)))

    def test_max_pages_limits_fetches(self):
        scraper, fetcher = self._scraper(
            {PAGE_1_URL: load("category_page_1.html")}, max_pages=1
        )
        report = scraper.scrape([PAGE_1_URL])
        self.assertEqual(fetcher.requested, [PAGE_1_URL])
        self.assertEqual(report.pages_scraped, 1)

    def test_fetch_errors_are_reported_not_raised(self):
        scraper, _ = self._scraper({})  # every fetch raises FetchError
        report = scraper.scrape([PAGE_1_URL])
        self.assertEqual(report.pages_scraped, 0)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.brands, [])

    def test_never_requests_product_pages_even_when_linked(self):
        # A page whose "next" link points at a product page: must not be followed.
        html = (
            '<div data-component-type="s-search-result">'
            '<div data-cy="title-recipe">'
            '<h2 class="a-size-mini"><span class="a-size-base-plus a-color-base">Acme</span></h2>'
            '<a href="/Acme-Widget/dp/B000000001"><h2><span>Acme Widget 3000</span></h2></a>'
            "</div></div>"
            '<a class="s-pagination-next" href="/Acme-Widget/dp/B000000001">Next</a>'
        )
        scraper, fetcher = self._scraper({PAGE_1_URL: html}, max_pages=5)
        report = scraper.scrape([PAGE_1_URL])

        self.assertEqual(fetcher.requested, [PAGE_1_URL])
        for url in fetcher.requested:
            self.assertNotIn("/dp/", url)
        self.assertEqual(report.pages_scraped, 1)
        self.assertEqual(report.brands[0].name, "Acme")


class BestSellerScrapeTests(unittest.TestCase):
    def test_bsr_scrape_learns_brands_from_sibling_listing(self):
        fetcher = FakeFetcher(
            {
                BSR_URL: load("bestsellers_page.html"),
                BSR_SIBLING_URL: BSR_SIBLING_HTML,
            }
        )
        scraper = CategoryBrandScraper(fetcher=fetcher, delay=0)
        report = scraper.scrape([BSR_URL])

        # The sibling search listing (a category page) was fetched once.
        self.assertIn(BSR_SIBLING_URL, fetcher.requested)
        # Still no product pages, ever.
        for url in fetcher.requested:
            self.assertNotIn("/dp/", url)

        by_rank = {p.rank: p for p in report.products}
        self.assertEqual(by_rank[1].brand, "Keurig")  # from sibling sidebar
        self.assertEqual(by_rank[2].brand, "Amazon Basics")  # house brand
        self.assertEqual(by_rank[3].brand, "ZULAY")  # labeled guess
        self.assertEqual(by_rank[3].brand_source, "title_guess")
        self.assertIsNone(by_rank[4].brand)

        # Aggregated view counts the resolved best-seller products.
        mentions = {r.name: r.product_mentions for r in report.brands}
        self.assertEqual(mentions["Keurig"], 1)
        self.assertEqual(mentions["Amazon Basics"], 1)


class MergePagesTests(unittest.TestCase):
    def test_merge_of_zero_pages(self):
        report = merge_pages([], ["https://www.amazon.com/s?k=tv"])
        self.assertEqual(report.pages_scraped, 0)
        self.assertEqual(report.brands, [])
        self.assertEqual(report.to_dict()["unique_brands"], 0)


class RobotCheckDetectionTests(unittest.TestCase):
    def test_detects_captcha_page(self):
        self.assertTrue(looks_like_robot_check(load("robot_check.html")))

    def test_normal_page_is_not_flagged(self):
        self.assertFalse(looks_like_robot_check(load("category_page_1.html")))


if __name__ == "__main__":
    unittest.main()
