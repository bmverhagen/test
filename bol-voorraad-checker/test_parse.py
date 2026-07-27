#!/usr/bin/env python3
"""Kleine tests zonder netwerkcalls."""

from bol_voorraad import extract_offer_uid, extract_product_id


def test_extract_product_id_from_digits():
    assert extract_product_id("9300000123456789") == "9300000123456789"


def test_extract_product_id_from_url():
    url = "https://www.bol.com/nl/nl/p/voorbeeld-product/9300000123456789/"
    assert extract_product_id(url) == "9300000123456789"


def test_extract_offer_uid_from_query():
    url = (
        "https://www.bol.com/nl/nl/p/x/9300000123456789/"
        "?offerUid=41925260-65c5-4e37-be1e-7a4b47ba40d1"
    )
    assert extract_offer_uid(url, None) == "41925260-65c5-4e37-be1e-7a4b47ba40d1"


def test_extract_offer_uid_explicit_wins():
    url = "https://www.bol.com/nl/nl/p/x/9300000123456789/?offerUid=abc"
    assert extract_offer_uid(url, "explicit-id") == "explicit-id"


if __name__ == "__main__":
    test_extract_product_id_from_digits()
    test_extract_product_id_from_url()
    test_extract_offer_uid_from_query()
    test_extract_offer_uid_explicit_wins()
    print("OK")
