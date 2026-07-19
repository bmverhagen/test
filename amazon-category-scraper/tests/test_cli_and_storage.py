import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from amazon_category_scraper.cli import main
from amazon_category_scraper.models import BrandRecord, ScrapeReport
from amazon_category_scraper.storage import write_report

FIXTURES = Path(__file__).parent / "fixtures"


def sample_report() -> ScrapeReport:
    return ScrapeReport(
        category_urls=["https://www.amazon.com/s?k=tv"],
        pages_scraped=1,
        product_cards_seen=3,
        brands=[
            BrandRecord(name="Sony", product_mentions=2, sources=("brand_filter", "product_card")),
            BrandRecord(name="TCL", product_mentions=1, sources=("product_card",)),
        ],
        scraped_at="2026-07-19T00:00:00+00:00",
    )


class StorageTests(unittest.TestCase):
    def test_csv_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "brands.csv"
            write_report(sample_report(), out, "csv")
            rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0], ["brand", "product_mentions", "sources"])
        self.assertEqual(rows[1], ["Sony", "2", "brand_filter|product_card"])
        self.assertEqual(rows[2], ["TCL", "1", "product_card"])

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "brands.json"
            write_report(sample_report(), out, "json")
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["unique_brands"], 2)
        self.assertEqual(data["brands"][0]["name"], "Sony")
        self.assertEqual(data["brands"][0]["product_mentions"], 2)

    def test_txt_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "brands.txt"
            write_report(sample_report(), out, "txt")
            lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["Sony", "TCL"])

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            write_report(sample_report(), None, "xml")


class CliTests(unittest.TestCase):
    def test_from_file_end_to_end_json(self):
        fixture = str(FIXTURES / "category_page_1.html")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "brands.json"
            exit_code = main(["--from-file", fixture, "-o", str(out)])
            self.assertEqual(exit_code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(data["pages_scraped"], 1)
        self.assertEqual(data["product_cards_seen"], 6)
        names = {brand["name"].casefold() for brand in data["brands"]}
        self.assertLessEqual({"samsung", "sony", "tcl", "hisense", "lg", "insignia"}, names)

    def test_output_format_inferred_from_extension(self):
        fixture = str(FIXTURES / "category_page_1.html")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "brands.csv"
            self.assertEqual(main(["--from-file", fixture, "-o", str(out)]), 0)
            first_line = out.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "brand,product_mentions,sources")

    def test_product_url_exits_with_error(self):
        self.assertEqual(main(["https://www.amazon.com/dp/B0CV9WPMWQ"]), 2)


if __name__ == "__main__":
    unittest.main()
