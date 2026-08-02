from pathlib import Path

from booking_scraper.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "search_results.html"


def test_cli_from_file_json(tmp_path, capsys):
    out = tmp_path / "out.json"
    code = main(
        [
            "--from-file",
            str(FIXTURE),
            "--format",
            "json",
            "-o",
            str(out),
        ]
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "La Uffheimoise" in text
    assert "price_total" in text


def test_cli_print_url(capsys):
    code = main(["--print-url"])
    assert code == 0
    url = capsys.readouterr().out.strip()
    assert "booking.com/searchresults" in url
    assert "dest_id=1477" in url
