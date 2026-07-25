from amazon_description_scraper.pipeline import AdaptivePacer, PipelineStats
from amazon_description_scraper.models import ProductDescription


def test_adaptive_pacer_grows_and_decays():
    pacer = AdaptivePacer(delay=1.0, min_delay=0.5, max_delay=5.0, growth=2.0, decay_every=2, decay_factor=0.5)
    pacer.on_block()
    assert pacer.delay == 2.0
    pacer.on_success()
    pacer.on_success()
    assert pacer.delay == 1.0  # 2.0 * 0.5


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
    assert d["success_rate"] == 1.0
