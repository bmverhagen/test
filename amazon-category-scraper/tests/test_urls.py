import unittest

from amazon_category_scraper.urls import (
    NotACategoryPageError,
    ensure_category_url,
    is_category_url,
    is_product_url,
    with_full_store,
    with_page,
)

CATEGORY_URLS = [
    "https://www.amazon.com/s?k=televisions",
    "https://www.amazon.com/s?i=electronics&rh=n%3A172282",
    "https://www.amazon.com/b?node=172282",
    "https://www.amazon.com/b/?node=16225009011",
    "https://www.amazon.com/gp/bestsellers/electronics/",
    "https://www.amazon.com/Best-Sellers-Electronics-Televisions/zgbs/electronics/172659",
    "https://www.amazon.com/gp/new-releases/electronics/",
    "https://www.amazon.com/gp/browse.html?node=283155",
    "https://www.amazon.co.uk/s?k=laptops",
    "https://www.amazon.de/-/en/s?k=fernseher",
]

PRODUCT_URLS = [
    "https://www.amazon.com/dp/B0CV9WPMWQ",
    "https://www.amazon.com/SAMSUNG-65-Inch-QLED/dp/B0CV9WPMWQ/ref=sr_1_1",
    "https://www.amazon.com/gp/product/B09XQ3JV22",
    "https://www.amazon.com/gp/aw/d/B09XQ3JV22",
    "https://www.amazon.com/exec/obidos/ASIN/B000000000",
    "https://www.amazon.com/product-reviews/B0CV9WPMWQ",
    "https://www.amazon.de/-/en/dp/B0CV9WPMWQ",
]


class UrlClassificationTests(unittest.TestCase):
    def test_category_urls_are_accepted(self):
        for url in CATEGORY_URLS:
            with self.subTest(url=url):
                self.assertTrue(is_category_url(url))
                self.assertFalse(is_product_url(url))
                self.assertEqual(ensure_category_url(url), url)

    def test_product_urls_are_rejected(self):
        for url in PRODUCT_URLS:
            with self.subTest(url=url):
                self.assertTrue(is_product_url(url))
                self.assertFalse(is_category_url(url))
                with self.assertRaises(NotACategoryPageError):
                    ensure_category_url(url)

    def test_product_page_error_message_mentions_category_pages(self):
        with self.assertRaisesRegex(NotACategoryPageError, "only scrapes category pages"):
            ensure_category_url("https://www.amazon.com/dp/B0CV9WPMWQ")

    def test_non_amazon_urls_are_rejected(self):
        for url in [
            "https://www.example.com/s?k=tv",
            "https://myamazon.evil.com/s?k=tv",
            "ftp://www.amazon.com/s?k=tv",
            "not a url",
        ]:
            with self.subTest(url=url):
                self.assertFalse(is_category_url(url))
                with self.assertRaises(NotACategoryPageError):
                    ensure_category_url(url)

    def test_with_page_sets_and_replaces_page_param(self):
        url = "https://www.amazon.com/s?k=tv"
        page2 = with_page(url, 2)
        self.assertIn("page=2", page2)
        self.assertIn("k=tv", page2)
        page3 = with_page(page2, 3)
        self.assertIn("page=3", page3)
        self.assertNotIn("page=2", page3)
        self.assertNotIn("page=", with_page(page2, 1))

    def test_with_full_store_added_to_node_only_search(self):
        url = "https://www.amazon.com/s?i=electronics&rh=n%3A172282"
        result = with_full_store(url)
        self.assertIn("fs=true", result)
        self.assertIn("rh=n%3A172282", result)

    def test_with_full_store_leaves_other_urls_unchanged(self):
        for url in [
            "https://www.amazon.com/s?k=tv",  # keyword search
            "https://www.amazon.com/s?rh=n%3A172282&fs=false",  # fs already set
            "https://www.amazon.com/s?rh=p_89%3ASony",  # no node refinement
            "https://www.amazon.com/b?node=172282",  # not /s
            "https://www.amazon.com/gp/bestsellers/electronics/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(with_full_store(url), url)


if __name__ == "__main__":
    unittest.main()
