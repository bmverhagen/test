#!/usr/bin/env python3
"""Kleine tests zonder netwerkcalls."""

from bol_voorraad import extract_offer_id, extract_product_id


def test_extract_product_id_from_digits():
    assert extract_product_id("9300000123456789") == "9300000123456789"


def test_extract_product_id_from_url():
    url = "https://www.bol.com/nl/nl/p/voorbeeld-product/9300000123456789/"
    assert extract_product_id(url) == "9300000123456789"


def test_extract_offer_id_from_query():
    url = "https://www.bol.com/nl/nl/p/x/9300000123456789/?offerId=1122334455"
    assert extract_offer_id(url, None) == 1122334455


def test_extract_offer_id_explicit_wins():
    url = "https://www.bol.com/nl/nl/p/x/9300000123456789/?offerId=1"
    assert extract_offer_id(url, 99) == 99


if __name__ == "__main__":
    test_extract_product_id_from_digits()
    test_extract_product_id_from_url()
    test_extract_offer_id_from_query()
    test_extract_offer_id_explicit_wins()
    print("OK")
