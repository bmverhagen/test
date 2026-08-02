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


def test_cli_print_nflt(capsys):
    code = main(["--print-nflt"])
    assert code == 0
    nflt = capsys.readouterr().out.strip()
    assert "hotelfacility=433" in nflt
    assert "roomfacility=17" in nflt


def test_cli_list_filters(capsys):
    code = main(["--list-filters"])
    assert code == 0
    out = capsys.readouterr().out
    assert "balcony" in out
    assert "roomfacility=17" in out
    assert "Zwembad" in out
