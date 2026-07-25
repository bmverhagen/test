from amazon_description_scraper.turbo import _structural_404


def test_structural_404_detects_nl_shell():
    html = (
        "<html><head><title>Pagina niet gevonden</title></head>"
        "<body>sorry</body></html>"
    )
    assert _structural_404(404, html)


def test_structural_404_rejects_non_404():
    assert not _structural_404(503, "Pagina niet gevonden")


def test_structural_404_rejects_large_body():
    assert not _structural_404(404, "x" * 9000)
