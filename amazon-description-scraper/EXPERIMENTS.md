# Speed experiments (50+)

Harness: `bench_speed.py` + follow-up validations. Marketplace: amazon.nl. No HTTP cache.

## Categories tried

1. Worker counts: 1,2,3,4,5,6,7,8,10,12,16,20,24,28,32
2. Spacing: 0.0, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.55
3. Fetch modes: soft / twister-only / dp-only / two-pass
4. Session: shared pool vs per-request
5. Timeouts: 6, 8, 10, 12, 15
6. Cache-bust query on/off (headers still no-cache)
7. Pool sizes: 5, 20, 40, 50, 80, 120
8. Retries: 0, 1, 2
9. Clients: requests vs httpx
10. Parse: BeautifulSoup full vs regex-first `fast_parse`
11. Adaptive spacing growth/decay
12. Skip urllib3 retry on twister 404 → immediate dp
13. Accept-Encoding gzip/br + keep-alive
14. Combo grids (w8/s05, w10/s04, w9/s06, w12/s05, …)

`bench_speed.py` alone ran **55 named experiments** on N=24; winners re-validated on 100/200/250/500/1000.

## Ladder

| Stage | Rate | Notes |
| --- | --- | --- |
| Sequential soft | 0.57/s | 1000/1000 in ~29min |
| Soft parallel w5/s0.12 | 3.9/s | 200/200 |
| Bench winner markers-only w20–w24 | 13–18/s | 100–250 |
| **Turbo + fast_parse (shipped)** | **18.3/s** | **1000/1000 in 54.6s, 0 captcha** |

## Shipped defaults

`bulk` → engine=`turbo`, workers=`24`, spacing=`0.02` (adaptive floor 0.015), shared pooled Session, twister→dp, regex-first parse.
