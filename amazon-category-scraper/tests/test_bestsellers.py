import unittest
from pathlib import Path

from amazon_category_scraper.parser import (
    guess_brand_from_title,
    match_known_brand,
    parse_category_page,
    resolve_product_brands,
)
from amazon_category_scraper.urls import sibling_search_listing

FIXTURES = Path(__file__).parent / "fixtures"

BSR_URL = "https://www.amazon.com/Best-Sellers-Coffee-Machines/zgbs/kitchen/289745/"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class BestSellerParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = parse_category_page(load("bestsellers_page.html"), url=BSR_URL)

    def test_detects_best_seller_layout(self):
        self.assertTrue(self.result.is_best_seller_list)
        self.assertEqual(self.result.total_cards, 4)

    def test_products_have_rank_asin_title(self):
        products = self.result.products
        self.assertEqual([p.rank for p in products], [1, 2, 3, 4])
        self.assertEqual(products[0].asin, "B0KEURIG01")
        self.assertTrue(products[0].title.startswith("Keurig K-Express"))

    def test_no_brands_before_resolution(self):
        self.assertTrue(all(p.brand is None for p in self.result.products))

    def test_next_page_link_found(self):
        self.assertIn("pg=2", self.result.next_page_url)


class BrandResolutionTests(unittest.TestCase):
    def _parsed(self):
        return parse_category_page(load("bestsellers_page.html"), url=BSR_URL)

    def test_resolution_with_vocabulary_house_brands_and_guesses(self):
        page = self._parsed()
        resolved = resolve_product_brands(page, ["Keurig"])
        self.assertEqual(resolved, 3)

        by_rank = {p.rank: p for p in page.products}
        self.assertEqual(by_rank[1].brand, "Keurig")
        self.assertEqual(by_rank[1].brand_source, "known_brand")
        # House brand matches even though it was not in the vocabulary.
        self.assertEqual(by_rank[2].brand, "Amazon Basics")
        self.assertEqual(by_rank[2].brand_source, "known_brand")
        # Unknown brand: conservative first-word guess, labeled as such.
        self.assertEqual(by_rank[3].brand, "ZULAY")
        self.assertEqual(by_rank[3].brand_source, "title_guess")
        # Title starting with a number gets no brand at all.
        self.assertIsNone(by_rank[4].brand)

        self.assertEqual(page.cards_with_brand, 3)
        self.assertEqual(page.product_brands, ["Keurig", "Amazon Basics", "ZULAY"])

    def test_resolution_without_guessing(self):
        page = self._parsed()
        resolve_product_brands(page, ["Keurig"], guess_missing=False)
        by_rank = {p.rank: p for p in page.products}
        self.assertIsNone(by_rank[3].brand)
        self.assertIsNone(by_rank[4].brand)


class TitleGuessTests(unittest.TestCase):
    def test_guesses(self):
        self.assertEqual(guess_brand_from_title("BELLA 12 Cup Programmable Coffee Maker"), "BELLA")
        # Too short after stripping punctuation: no guess (multiword brands
        # like "Mr. Coffee" must come from the vocabulary instead).
        self.assertIsNone(guess_brand_from_title("Mr. Coffee® 5-Cup Mini Brew"))
        self.assertIsNone(guess_brand_from_title("12-Cup Replacement Carafe"))
        self.assertIsNone(guess_brand_from_title(""))
        self.assertIsNone(guess_brand_from_title("A+ Charger"))

    def test_known_brand_matches_despite_trademark_sign(self):
        self.assertEqual(
            match_known_brand("Mr. Coffee® 5-Cup Mini Brew", ["Mr. Coffee"]), "Mr. Coffee"
        )
        self.assertEqual(
            match_known_brand("Mr. Coffee 5-Cup Mini Brew", ["Mr. Coffee"]), "Mr. Coffee"
        )


class SiblingListingUrlTests(unittest.TestCase):
    def test_zgbs_url_maps_to_node_search(self):
        self.assertEqual(
            sibling_search_listing(BSR_URL),
            "https://www.amazon.com/s?rh=n%3A289745&fs=true",
        )

    def test_gp_bestsellers_with_node(self):
        self.assertEqual(
            sibling_search_listing("https://www.amazon.com/gp/bestsellers/electronics/172659"),
            "https://www.amazon.com/s?rh=n%3A172659&fs=true",
        )

    def test_urls_without_node_return_none(self):
        self.assertIsNone(sibling_search_listing("https://www.amazon.com/gp/bestsellers/electronics/"))
        self.assertIsNone(sibling_search_listing("https://www.amazon.com/s?k=coffee"))


if __name__ == "__main__":
    unittest.main()
