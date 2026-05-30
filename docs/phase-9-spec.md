# Phase 9 — PoO same-region forgery resistance (spec)

**Status:** pre-registered 2026-05-29 (before execution).
**Targeted hardware:** vast.ai RTX 3090 (or any GPU with ≥ 8 GB VRAM).
**Estimated cost:** ~$1–3.
**Estimated wall time:** ~30–60 min end-to-end (acquisition + trials + analysis).

---

## Why this phase exists

Phase 1 measured PoO FAR/FRR using a *wrong-region* Byzantine model:
the adversary fabricates a `V_score` by submitting SuperPoint descriptors
extracted from a Zurich tile **different** from the location it claims.
That tests the weakest realistic adversary: a captured peer that has
not observed the claimed region and substitutes random terrain.

The paper's "unforgeable in the practical sense" claim is stronger
than that: it asserts that even an adversary who **has** seen the
region (publicly via Sentinel-2) cannot fabricate a passing
`V_score` because that would require knowing the verifier's
acquisition-time atmospheric, illumination, and seasonal state.
That stronger claim has not been tested.

Phase 9 closes the gap: same location, **different acquisition** —
adversary descriptors from a Sentinel-2 capture of the *same* tile
at a *different* date than the verifier image. The result either
strengthens the central thesis with new data, or quantifies the
acquisition gap beyond which forgery becomes practical.

---

## Design (critic-locked, 5 conditions)

1. **Same location, different acquisition.** Adversary applies
   SuperPoint to a Sentinel-2 capture of the same tile at a different
   date (not the same image the verifier sees, not a different tile).
   This models "adversary has public satellite imagery of the region
   but does not have the verifier's specific future acquisition."

2. **Single modality, no self-comparison.** Both verifier and
   adversary images are Sentinel-2 satellite captures (no UAV-camera
   vs satellite cross-modality, no comparison of an image to itself).

3. **Sweep across realism gap.** Pairs are binned by temporal gap
   between adversary and verifier acquisition:
   - **same-season** (≤ 3 month gap)
   - **cross-season** (3–9 month gap)
   - **cross-year** (≥ 12 month gap)

   Finds the boundary at which acquisition drift defeats forgery.

4. **Distributional report, not binary FAR.** Output histograms of
   `V_score` for three populations, all overlaid on `T_verify = 0.30`:
   - **honest-revisit** baseline (same image with realistic
     perturbations, as in Phase 1)
   - **wrong-region-fab** (Phase 1 Byzantine model, recomputed for
     consistency)
   - **same-region-fab** (Phase 9 new model, per condition 1)

   Reporting the distributions answers the rigorous question ("where
   does same-region fall *relative* to T_verify"), not just the
   binary pass/fail.

5. **Mode A focus.** Mode A (top-K=20 descriptors, L2 + Lowe τ=0.7,
   `T_verify = 0.30`) is the configuration the body of the paper
   uses and the one a same-region adversary could plausibly attack.
   Mode B (SHA-256 hash equality) is unforgeable by construction
   under any cross-acquisition gap (the hash changes with any pixel
   change), and the Phase 9 experiment does not test it.

---

## Pre-registered interpretation matrix

The interpretation is fixed **before** execution; results are not
re-cut to fit a desired narrative.

| Same-region median `V_score` | Interpretation | Paper action |
|---|---|---|
| < 0.20 (well below T_verify) | Acquisition drift defeats forgery: same-region fabrication is no easier than wrong-region. | Strengthen Abstract / §IV-B unforgeability claim with the new data; report "PoO resists same-region forgery at any tested acquisition gap." |
| 0.20–0.35 (overlapping T_verify) | Forgery is marginal at small acquisition gaps but defeated at large ones. | Soften "unforgeable in the practical sense" to "hard to forge beyond an acquisition gap of approximately X months"; report the boundary X explicitly. |
| > 0.35 (above T_verify) | Same-region forgery is practical at the tested gaps. | Honest reveal: Mode A is not security-sufficient against an adversary with the public-imagery prior. Recommend Mode B (hash-only) for high-trust operations; explicitly note Mode B's own brittleness to honest acquisition change (Section IV-B). |

All three outcomes are publishable. The pre-registration is what
distinguishes a credible test from cherry-picked validation.

---

## Pipeline overview

```
phase9-acquisition.py        →  workspaces/phase9-acquisition/
   (Sentinel-2 multi-temporal           tile_<lat>_<lon>/
    download via Copernicus              dt_<YYYYMMDD>.png × N dates)
    Data Space Ecosystem API)

phase9-forgery-trials.py     →  workspaces/phase9-sweep/
   (SuperPoint v1 + Lowe matcher,        forgery_trials.csv
    runs Mode A V_score per pair,        (1 row / pair)
    sweeps over honest /
    wrong-region-fab / same-region-fab)

phase9-analyze.py            →  docs/results/phase-9.md
   (V_score histograms by population,    (populated from template)
    per-bin same-region medians,         workspaces/phase9-sweep/figures/
    decision per interpretation matrix    histogram_*.png
    above)                                roc_curve.png

phase9-campaign.sh           →  orchestrates: acquisition → trials → analyze
   (single-command end-to-end on
    vast.ai instance)
```

---

## Acceptance

- Phase 9 acceptance is **the pre-registered interpretation itself**.
  Any of the three outcomes above is acceptable; the test does not
  have a "pass" criterion in the Phase 1–8 sense, because the test
  is a measurement, not a gate.
- The result is committed to `docs/results/phase-9.md` in the same
  format as `phase-1.md`, with the actual data and the interpretation
  applied per the matrix above.

---

## Data lineage

- Sentinel-2 L2A surface-reflectance scenes acquired via the
  Copernicus Data Space Ecosystem (CDSE) Open Access browser /
  STAC API. Authentication: free CDSE account (token-based).
- Tiles cropped to the same dimensions as the Phase 1 Zurich Z16
  set (256×256 px). Locations chosen to span varied terrain
  (urban / agricultural / forested) for representative SuperPoint
  behaviour.
- Raw downloaded scenes are not committed to git (gitignored under
  `workspaces/phase9-acquisition/`); the manifest of (tile, date)
  pairs **is** committed for reproducibility.

---

## What this phase does NOT do

- Does not test Mode B (hash-equality) — by construction it is not
  forgeable under any acquisition gap, and its brittleness to
  honest acquisition change is a known property of cryptographic
  hashing, not a security question.
- Does not test a "guessing adversary" that synthesises plausible
  descriptors from a generative model. That is a meaningfully
  different threat (out of scope, noted in Limitations).
- Does not test under jamming / replay-at-deployment attacks
  beyond the Phase 5 spoof detector envelope.
