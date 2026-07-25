from amazon_description_scraper.turbo import _structural_404


def test_structural_404_detects_status_404():
    assert _structural_404(404, "x" * 9000)
    assert _structural_404(404, "<title>Pagina niet gevonden</title>")


def test_structural_404_detects_not_found_markers_on_200():
    html = "<html><title>Page Not Found</title><body>dogs of amazon</body></html>"
    assert _structural_404(200, html)


def test_structural_404_rejects_soft_5xx():
    assert not _structural_404(503, "Er is iets misgegaan")
    assert not _structural_404(500, "service niet beschikbaar")
