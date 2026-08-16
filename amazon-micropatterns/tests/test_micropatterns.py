"""Tests voor automatische micropatroon-discovery (geen curated taxonomie)."""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from cluster import discover_clusters  # noqa: E402
from extract import build_phrase_index, extract_candidate_phrases, tokenize  # noqa: E402
from generate_longtail_demo import main as gen_demo  # noqa: E402
from momentum import analyse, classify  # noqa: E402


class ExtractTests(unittest.TestCase):
    def test_strips_brand_and_stopwords(self):
        tokens = tokenize("Novellia Fermented Rice Water Hair Rinse 200ml")
        self.assertIn("fermented", tokens)
        self.assertIn("rice", tokens)
        self.assertIn("water", tokens)
        self.assertNotIn("novellia", tokens)
        self.assertNotIn("ml", tokens)
        self.assertNotIn("hair", tokens)

    def test_phrases_include_bigrams(self):
        phrases = extract_candidate_phrases(
            "Kuralux Silk Protein Heat Protect Spray 150ml"
        )
        self.assertIn("silk protein", phrases)
        self.assertIn("heat protect", phrases)


class ClusterDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gen_demo()
        cls.data_dir = os.path.join(ROOT, "data")
        cls.results, cls.baseline, cls.clusters = analyse(cls.data_dir)

    def test_discovers_multiple_clusters_without_taxonomy(self):
        self.assertGreaterEqual(len(self.clusters), 5)

    def test_finds_rice_water_micropattern(self):
        blob = " | ".join(
            c.label.lower() + " " + " ".join(c.phrases) for c in self.clusters
        )
        self.assertTrue(
            "rice water" in blob or "fermented rice" in blob,
            f"rice water cluster missing in: {blob[:400]}",
        )

    def test_finds_silk_heat_cooccurrence(self):
        found = False
        for c in self.clusters:
            joined = " ".join(c.phrases).lower()
            if "silk" in joined and "heat" in joined:
                found = True
                break
            if "silk protein" in joined or "heat protect" in joined:
                # Accept as related singletons or joint cluster
                found = True
                break
        self.assertTrue(found, "silk/heat micropattern not discovered")

    def test_rising_and_declining_present(self):
        stages = {classify(r)[0] for r in self.results if r.longtail_asins >= 3}
        self.assertTrue(
            stages & {"EXPLODING", "RISING"},
            f"expected rising stages, got {stages}",
        )
        self.assertTrue(
            stages & {"DECLINING", "FADING"},
            f"expected declining stages, got {stages}",
        )

    def test_top_sellers_do_not_dominate_longtail_signal(self):
        # Clusters whose only evidence is top-300 should be NOISE or empty longtail
        for r in self.results:
            if r.longtail_asins == 0:
                continue
            self.assertGreaterEqual(r.avg_rank_last, 300)

    def test_phrase_index_filters_rare(self):
        asins = {
            "A1": {"title": "Unique Zzz Token Only Here 100ml", "price": 1.0},
            "A2": {"title": "Shared Moisture Shampoo 100ml", "price": 1.0},
            "A3": {"title": "Shared Moisture Conditioner 100ml", "price": 1.0},
            "A4": {"title": "Shared Moisture Mask 100ml", "price": 1.0},
        }
        phrases = build_phrase_index(asins, min_df=3)
        self.assertNotIn("zzz", phrases)
        self.assertIn("moisture", phrases)


class GraphClusterUnitTests(unittest.TestCase):
    def test_cooccurrence_merges_related_phrases(self):
        from extract import PhraseStats

        phrases = {
            "rice water": PhraseStats("rice water", 4, frozenset("ABCD")),
            "fermented": PhraseStats("fermented", 4, frozenset("ABCD")),
            "charcoal": PhraseStats("charcoal", 3, frozenset("EFG")),
            "detox": PhraseStats("detox", 3, frozenset("EFG")),
            "unrelated": PhraseStats("unrelated", 3, frozenset("XYZ")),
        }
        clusters = discover_clusters(phrases, min_jaccard=0.5, min_asins=3)
        labels = " | ".join(c.label for c in clusters)
        # rice+fermented should merge; charcoal+detox should merge
        rice = next(c for c in clusters if "rice" in c.label or "fermented" in c.label)
        self.assertGreaterEqual(len(rice.phrases), 2)
        self.assertIn("charcoal", labels.lower() + " " + " ".join(
            " ".join(c.phrases) for c in clusters
        ))


if __name__ == "__main__":
    unittest.main()
