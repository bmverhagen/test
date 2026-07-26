from amazon_description_scraper.pipeline import AdaptivePacer, PipelineStats, SpacingGate
from amazon_description_scraper.models import ProductDescription


def test_adaptive_pacer_grows_and_decays():
    pacer = AdaptivePacer(delay=1.0, min_delay=0.5, max_delay=5.0, growth=2.0, decay_every=2, decay_factor=0.5)
    pacer.on_block()
    assert pacer.delay == 2.0
    pacer.on_success()
    pacer.on_success()
    assert pacer.delay == 1.0  # 2.0 * 0.5


def test_spacing_gate_cap_and_reset():
    gate = SpacingGate(spacing=0.05, min_spacing=0.03, max_spacing=1.5)
    gate.spacing = 0.9
    gate.cap_spacing(0.20)
    assert gate.max_spacing == 0.20
    assert gate.spacing == 0.20
    gate.reset_spacing(0.08)
    assert gate.spacing == 0.08


def test_pipeline_stats_rates():
    stats = PipelineStats(total=10)
    stats.started_at = stats.started_at - 10
    product = ProductDescription(
        asin="B000000001",
        marketplace="nl",
        url="https://www.amazon.nl/dp/B000000001",
        title="x",
        provider="soft/twister",
        source_bytes=100,
    )
    stats.note_success(product)
    assert stats.ok == 1
    assert stats.rate > 0
    d = stats.to_dict()
    # success_rate is final coverage: ok / total (not ok / attempted)
    assert d["success_rate"] == 0.1
    stats.ok = 10
    assert stats.to_dict()["success_rate"] == 1.0
