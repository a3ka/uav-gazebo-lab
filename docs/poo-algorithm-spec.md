# PoO Algorithm Spec — locked for Phase 1

**Status:** locked 2026-05-21
**Source:** `docs/reference/BFT_UAV_Swarm_Paper_v9_8.tex` §IV-B "Visual Proof
of Observation" (lines 195-213). All locked values traceable to the paper;
where the paper leaves choices open (Track 2 deferrals), this doc pins a
concrete default for Phase 1 measurement.

This is PF-5 in `VALIDATION_PLAN.md`. Phase 1 implementation must conform
to this spec. Changes require explicit user discussion + a Decision
register entry.

---

## 1. Locked choices (directly from paper)

| Item | Value | Paper anchor |
|---|---|---|
| Keypoint detector | **SuperPoint** | §IV-B p.197 cite [detone2018superpoint] |
| Descriptor dimension | 256 (L2-normalised) | §IV-B p.197 |
| Image resolution (input to SuperPoint) | 480 × 640 px | §IV-D p.249 |
| Total keypoints per frame (raw) | typical 200–500 (SuperPoint default) | §IV-B p.197 |
| Top-N selected (Mode B hash basis) | N = 50 by detector score | §IV-B p.197 |
| Mode A transmitted descriptors | K = 20 | §IV-B p.197 |
| Mode A packet size | ~5.30 kB total | §IV-B p.197 |
| Mode B base record size | 180–200 B | §IV-B p.197 |
| Hash function | SHA-256 over sorted top-50 descriptors | §IV-B eq.1 |
| Signature | Ed25519 | §IV-B eq.3 |
| Verification radius | r_verify = 500 m | §IV-B p.211 |
| Match threshold (Lowe ratio) | τ_match = 0.7 | §IV-B p.211 cite [lowe2004distinctive] |
| VERIFIED threshold | T_verify = 0.3 (V > 0.3 ⇒ VERIFIED) | §IV-B p.211 |
| Mode A scoring | V = accepted_matches / K (transmitted descriptors) | §IV-B p.211 |
| Mode B scoring | recomputed-hash equality (binary) | §IV-B p.211 |
| Expected honest inlier ratio (clean LoS) | 60-90 % | §IV-B p.211 (literature) |
| Expected honest inlier ratio (degraded) | 20-40 % | §IV-B p.211 (literature) |

## 2. Lock-ins Phase 1 specifically needs (paper open, we close)

These were left to Track 2 by the paper. We close them for Phase 1
baseline; sensitivity sweep around them is Phase 1's job.

| Item | Phase 1 default | Justification |
|---|---|---|
| SuperPoint pretrained weights | **MagicLeap official `superpoint_v1.pth`** (mirror: HuggingFace `magicleap/superpoint`) | The reference release of [detone2018superpoint]. Re-training out of scope. |
| Matcher | **Brute-force nearest-neighbour in L2 with Lowe ratio τ=0.7** | Exactly what paper §IV-B specifies. NOT LightGlue — LightGlue is more permissive and would shift FAR/FRR away from paper-as-stated. The image bakes in `lightglue` as an available library so Phase 1 sensitivity sweep can A/B it later, but baseline measurement uses paper-spec Lowe ratio. |
| Mode for Phase 1 measurement | **Mode A (compact descriptor set, K=20)** | Mode A allows direct FAR/FRR characterisation: the score V is continuous over [0, 1] so a ROC curve can be computed. Mode B is binary (hash matches or doesn't) and reduces to a different test. Mode B characterisation is its own work item, deferred. |
| Image source for satellite reference | **Sentinel-2 L2A surface reflectance tiles** (~10 m/pixel, RGB bands B04/B03/B02) | Free via CDSE (PF-2), standard in geospatial research, sufficient feature density for SuperPoint. |
| Camera model in Gazebo | **Standard `gz-sim` camera plugin** at 480×640 px, FOV ≈ 60°, mounted nadir-pointing | Matches paper's stated SuperPoint input resolution. FOV is a Gazebo-default reasonable starting point; not specified in paper. |
| Drone altitude in Phase 1 | **150 m AGL** (cruise altitude per §III paper "System Model") | Inside SuperPoint's effective range; matches paper's stated cruise envelope. |
| Sentinel-2 tile selection | **One ~100 × 100 km patch with mixed urban/rural texture; ≤10% cloud cover; recent acquisition** | Mixed texture ensures keypoint density variation across scene. Exact tile chosen during Phase 0 dataset staging. |
| Byzantine forge strategy in Phase 1 | **Replay**: byzantine UAV serves descriptors from a *different* Sentinel-2 tile (~50 km offset) as if it were observing the current location | Most realistic Byzantine threat model for PoO. Catches paper's "captured UAV without imagery DB" scenario. |
| Honest noise injection | **Sun-angle / motion-blur / partial-cloud variation in Gazebo lighting + camera plugin parameters** | Exercises Assumption (iv) inlier ranges (60-90% clean, 20-40% degraded) without leaving the paper-specified physics. |

## 3. Phase 1 algorithm — step-by-step

For each PoO trial (one verification event):

1. **Honest UAV $v_i$ captures frame at time $t_1$, position $\mathbf{p}_i$.**
   - Gazebo `camera` sensor at 480×640 px, nadir, 60° FOV.
2. **SuperPoint inference on the frame.**
   - Use `superpoint_v1.pth` weights, top-50 keypoints by score, 256-D descriptors.
3. **Build SignedObservation** $\mathrm{OBS}_i = (t_1, \mathbf{p}_i, H_i, c_i, \mathrm{ID}_i, \sigma_i)$.
   - $H_i$ = SHA-256(sorted top-50 descriptors).
   - $c_i$ = RANSAC inlier ratio from initial TRN fix (paper §IV-B).
   - $\sigma_i$ = Ed25519 signature.
   - Mode A appendix: K=20 descriptors (lowest-N by some deterministic order — paper does not specify; spec choice: **score-descending then index-ascending**).
4. **Honest UAV $v_i$ transmits to $v_j$.**
5. **At time $t_2 > t_1$, when $v_j$ flies within $r_{\text{verify}} = 500$ m of $\mathbf{p}_i$:**
   - $v_j$ captures own frame, runs SuperPoint, gets $\mathbf{f}_j$ keypoints + descriptors.
   - For each of the K=20 descriptors in OBS$_i$ (Mode A): brute-force NN search in $\mathbf{f}_j$; apply Lowe ratio test with τ=0.7.
   - Count accepted matches.
   - $V = \text{accepted\_matches} / K$.
   - **Decision:** $V > T_{\text{verify}} = 0.3$ → VERIFIED, else UNVERIFIED.

For **byzantine** trials: same flow except $v_i$ replaces own frame's
descriptors with descriptors extracted from a *different* Sentinel-2 tile
(~50 km offset). Everything downstream (hash, sign, transmit) is honest;
only the observation itself is forged.

## 4. Phase 1 measurement plan

- **Honest trials:** ≥500. Sweep environmental variation: 3 sun angles, 2
  motion-blur levels, 2 partial-cloud conditions. Cells: 3×2×2 = 12 cells,
  ~42 trials each.
- **Byzantine trials:** ≥500. Sweep distance of replay source (10 km, 50
  km, 200 km, different terrain class), 3 byzantine attempts per
  honest-conditions cell.
- **Per trial logged:** $V$ raw score, accepted/transmitted match count,
  decision (VERIFIED/UNVERIFIED), inlier ratio, lighting params, ground
  truth (honest/byzantine).
- **Metrics computed:**
  - FAR @ T_verify=0.3 (false-accept rate of byzantine)
  - FRR @ T_verify=0.3 (false-reject rate of honest)
  - ROC AUC over T_verify ∈ [0, 1]
  - Sensitivity sweep at T_verify ∈ {0.2, 0.3, 0.4} (paper-specified deferred item)
  - Per-environmental-cell honest inlier ratio distribution
    (cross-check against paper's claimed 60-90% / 20-40% literature ranges)

## 5. Pass criteria (Phase 1)

From VALIDATION_PLAN.md Phase 1:
- FAR < 5% at T_verify = 0.3
- FRR < 10% at T_verify = 0.3
- ROC AUC > 0.90

## 6. Open items — flagged here, NOT closed in this spec

These are explicitly deferred and tracked separately:

1. **SuperPoint inference timing on target embedded accelerator.** Paper
   §IV-B p.209 names "50-100 TOPS-class accelerator" as representative;
   Phase 1 will use whatever the GPU rental provides. Per-board
   characterisation is its own item, post-Phase-1.

2. **Mode B (zero-bandwidth) characterisation.** Phase 1 uses Mode A
   exclusively. Mode B reduces to a binary hash-equality test that
   requires reproducible descriptor extraction across viewing geometries;
   that's its own calibration deferred.

3. **Adversarial-PoO (strategic, not naïve byzantine).** Phase 1 byzantine
   model is "replay from different tile." A strategic adversary that
   *guesses* descriptors plausibly close to honest is out of scope —
   paper acknowledges this is unproven (Section IV "partial mitigation
   against strategic adversaries").

4. **Image format pipeline.** Sentinel-2 L2A is GeoTIFF in CRS UTM; Gazebo
   camera plugin produces sRGB BGRA8 numpy arrays. The colour-space
   conversion + radiometric normalisation pipeline between the two is a
   Phase 0 sub-task (item 9 — Gazebo camera + SuperPoint smoke test). If
   that smoke test reveals colour-space drift biasing SuperPoint, Phase
   1 must redo with corrected pipeline.

## 7. Stack pins (referenced by Dockerfile.gpu)

| Library | Pin | Purpose |
|---|---|---|
| `torch` | 2.5.1 (CUDA 12.4) | Backend for SuperPoint inference |
| `torchvision` | 0.20.1 | Image utils |
| `kornia` | latest 0.7.x | SuperPoint pretrained model loader (kornia.feature.SuperPoint) |
| `lightglue` | latest | NOT used in Phase 1 baseline (paper spec is Lowe ratio); reserved for future sensitivity comparison |
| `opencv-python-headless` | 4.x | RANSAC inlier computation (paper-referenced) |
| `rasterio` | 1.4+ | Sentinel-2 GeoTIFF read |

## 8. Decision register

- **2026-05-21** — initial lock. Matcher choice: paper-spec Lowe ratio,
  NOT LightGlue (which is in Dockerfile only as a reserved library).
  Mode A only for Phase 1; Mode B deferred. Byzantine model: replay from
  ~50 km offset tile.
