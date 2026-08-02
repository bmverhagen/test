import pytest

from booking_scraper.filters import (
    FILTER_ALIASES,
    load_filter_catalog,
    resolve_alias,
    resolve_aliases,
)


def test_catalog_contains_corrected_core_filters():
    chips = {item["chip"]: item["label"] for item in load_filter_catalog()}
    assert chips["roomfacility=17"] == "Balkon"
    assert chips["roomfacility=123"] == "Terras"
    assert chips["hotelfacility=433"] == "Zwembad"
    assert chips["mealplan=1"] == "Ontbijt inbegrepen"
    assert chips["popular_activities=10"] == "Sauna"
    assert "roomfacility=32" not in chips
    assert "popular_activities=2" not in chips


def test_aliases_resolve():
    assert resolve_alias("pool") == ("hotelfacility=433",)
    assert resolve_alias("balcony") == ("roomfacility=17",)
    assert "roomfacility=123" in resolve_alias("balcony_or_terrace")
    assert resolve_aliases(["spa", "hotelfacility=2"]) == [
        "hotelfacility=54",
        "hotelfacility=2",
    ]


def test_unknown_alias_raises():
    with pytest.raises(KeyError):
        resolve_alias("niet_bestaand")


def test_alias_coverage_for_defaults():
    for name in ("breakfast", "pool", "balcony", "score_9"):
        assert name in FILTER_ALIASES
