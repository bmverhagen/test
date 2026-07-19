import unittest
from pathlib import Path

from amazon_category_scraper.parser import clean_brand_name, parse_category_page

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ModernLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = parse_category_page(
            load("category_page_1.html"),
            url="https://www.amazon.com/s?k=televisions",
        )

    def test_counts_product_cards(self):
        self.assertEqual(self.result.total_cards, 6)
        # One card intentionally has no brand row.
        self.assertEqual(self.result.cards_with_brand, 5)

    def test_brands_from_product_cards(self):
        self.assertEqual(
            self.result.product_brands,
            ["SAMSUNG", "Sony", "SAMSUNG", "TCL", "INSIGNIA"],
        )

    def test_brands_from_refinement_sidebar(self):
        self.assertEqual(
            self.result.refinement_brands,
            ["Samsung", "Sony", "TCL", "Hisense", "LG", "Roku"],
        )

    def test_see_more_and_counts_are_filtered_out(self):
        lowered = [name.casefold() for name in self.result.refinement_brands]
        self.assertNotIn("see more", lowered)
        for name in self.result.refinement_brands:
            self.assertNotRegex(name, r"\(\d")

    def test_brands_from_structured_data(self):
        self.assertEqual(self.result.structured_data_brands, ["Hisense", "VIZIO"])

    def test_next_page_url_is_resolved_absolute(self):
        self.assertEqual(
            self.result.next_page_url,
            "https://www.amazon.com/s?k=televisions&page=2&qid=1721400000&ref=sr_pg_2",
        )

    def test_product_titles_are_not_reported_as_brands(self):
        for name in self.result.product_brands:
            self.assertNotIn("QLED", name)
            self.assertNotIn("Smart TV", name)


class LegacyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = parse_category_page(
            load("category_page_2.html"),
            url="https://www.amazon.com/s?k=televisions&page=2",
        )

    def test_brands_from_byline_and_h5_layouts(self):
        self.assertEqual(self.result.product_brands, ["LG", "Bose", "Panasonic"])

    def test_last_page_has_no_next_url(self):
        self.assertIsNone(self.result.next_page_url)


class TitleFallbackTests(unittest.TestCase):
    """Newest layout: no brand row on cards; title prefix + sidebar match."""

    HTML = """
    <div id="brandsRefinements">
      <ul aria-labelledby="p_123-title">
        <li id="p_123/1"><span class="a-label a-checkbox-label">Sony</span></li>
        <li id="p_123/2"><span class="a-label a-checkbox-label">Sony Electronics</span></li>
      </ul>
    </div>
    <div data-component-type="s-search-result">
      <div data-cy="title-recipe">
        <a href="/Sony-Electronics-Thing/dp/B000000001">
          <h2><span>Sony Electronics Wireless Speaker</span></h2>
        </a>
      </div>
    </div>
    <div data-component-type="s-search-result">
      <div data-cy="title-recipe">
        <a href="/Sonyx-Thing/dp/B000000002">
          <h2><span>Sonyx Cable 2-Pack</span></h2>
        </a>
      </div>
    </div>
    """

    def test_longest_word_bounded_prefix_wins(self):
        result = parse_category_page(self.HTML)
        # "Sony Electronics" beats "Sony"; "Sonyx" must not match "Sony".
        self.assertEqual(result.product_brands, ["Sony Electronics"])
        self.assertEqual(result.total_cards, 2)
        self.assertEqual(result.cards_with_brand, 1)


class CleanBrandNameTests(unittest.TestCase):
    def test_strips_by_prefix_and_counts(self):
        self.assertEqual(clean_brand_name("by LG"), "LG")
        self.assertEqual(clean_brand_name("Samsung (1,234)"), "Samsung")
        self.assertEqual(clean_brand_name("  Sony\n Electronics "), "Sony Electronics")


class EmptyPageTests(unittest.TestCase):
    def test_handles_page_without_results(self):
        result = parse_category_page("<html><body><p>No results.</p></body></html>")
        self.assertEqual(result.total_cards, 0)
        self.assertEqual(result.product_brands, [])
        self.assertEqual(result.refinement_brands, [])
        self.assertIsNone(result.next_page_url)


if __name__ == "__main__":
    unittest.main()
