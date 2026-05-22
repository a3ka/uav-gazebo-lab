#!/usr/bin/env python3
"""Phase 1 -- PoO FAR/FRR measurement campaign.

Spec source: docs/poo-algorithm-spec.md ("locked 2026-05-21").
  - SuperPoint v1 pretrained, 256-D L2-normalised descriptors
  - top-N=50 keypoints per frame (Mode B basis)
  - Mode A transmits K=20 descriptors
  - matcher: brute-force NN + Lowe ratio tau=0.7
  - V = accepted_matches / K, VERIFIED iff V > T_verify (default 0.3)

For Phase 1 we use the Zurich Z16 dataset (re-used). Byzantine model:
"replay" -- byzantine claims position P but the descriptors come from
a *different* tile in the dataset (geographically separated --
typically opposite end of the 2.2 x 3.3 km grid). Verifier extracts
descriptors at the *true* position P.

Honest noise injection sweep:
  - brightness shift   (sun angle proxy)
  - gaussian blur      (motion blur proxy)
  - partial occlusion  (cloud / shadow proxy)

Output: CSV row per trial with columns:
  trial_id, label, t_verify_used, V_score, n_matches,
  sun_shift, blur_sigma, occl_frac, honest_tile, byzantine_tile,
  inference_ms

Pass criteria (per VALIDATION_PLAN.md Phase 1):
  FAR < 5%, FRR < 10% at T_verify = 0.3, ROC AUC > 0.90.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from lightglue import SuperPoint


@dataclass
class TrialResult:
    trial_id: int
    label: str  # 'honest' or 'byzantine'
    t_verify_used: float
    V_score: float
    n_matches: int
    sun_shift: float
    blur_sigma: float
    occl_frac: float
    honest_tile: str
    byzantine_tile: str
    inference_ms: float


def load_tile(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(path)
    return img


def perturb(img: np.ndarray, sun_shift: float, blur_sigma: float, occl_frac: float, rng: random.Random) -> np.ndarray:
    """Apply honest revisit perturbations: brightness, blur, occlusion."""
    out = img.astype(np.float32)
    # sun_shift in [-50, +50] -> additive on 0-255 scale
    out = np.clip(out + sun_shift, 0, 255)
    if blur_sigma > 0:
        k = max(3, int(2 * math.ceil(blur_sigma)) | 1)
        out = cv2.GaussianBlur(out, (k, k), blur_sigma)
    if occl_frac > 0:
        h, w = out.shape[:2]
        occ_h = int(h * math.sqrt(occl_frac))
        occ_w = int(w * math.sqrt(occl_frac))
        x = rng.randint(0, w - occ_w)
        y = rng.randint(0, h - occ_h)
        out[y:y + occ_h, x:x + occ_w] = 128.0
    return out.astype(np.uint8)


def extract_topn(model: SuperPoint, img: np.ndarray, n_keypoints: int, device: str) -> torch.Tensor:
    """Run SuperPoint and return top-N descriptors by score, shape [N, 256]."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    t = torch.from_numpy(gray)[None, None, ...].to(device)
    with torch.no_grad():
        # LightGlue's SuperPoint expects a dict {'image': tensor}.
        out = model({'image': t})
    kps = out['keypoints'][0]
    desc = out['descriptors'][0]  # [n_kp, 256]
    scores = out['keypoint_scores'][0]  # LightGlue key
    if kps.shape[0] == 0:
        return torch.zeros((0, 256), device=device)
    idx = torch.argsort(scores, descending=True)[:n_keypoints]
    return desc[idx]


def match_lowe(query: torch.Tensor, gallery: torch.Tensor, ratio: float) -> int:
    """Return count of query descriptors that pass the Lowe ratio test."""
    if query.shape[0] == 0 or gallery.shape[0] < 2:
        return 0
    # All pairwise L2 distances
    d = torch.cdist(query, gallery)
    top2 = torch.topk(d, k=2, largest=False, dim=1).values  # [Q, 2]
    accepted = (top2[:, 0] < ratio * top2[:, 1]).sum().item()
    return int(accepted)


def run_trial(
    model: SuperPoint,
    device: str,
    tile_paths: list[Path],
    rng: random.Random,
    label: str,
    n_top: int,
    k_modea: int,
    lowe_tau: float,
    sun_shift: float,
    blur_sigma: float,
    occl_frac: float,
) -> tuple[float, int, str, str, float]:
    """Returns (V_score, n_matches, honest_tile_name, byzantine_tile_name, inference_ms)."""
    honest_tile = rng.choice(tile_paths)
    img_observed = load_tile(honest_tile)

    if label == 'honest':
        img_revisit = perturb(img_observed, sun_shift, blur_sigma, occl_frac, rng)
        byz_name = ''
    else:
        # Byzantine: claim observed at honest_tile but use descriptors from a *different* tile
        other_tiles = [p for p in tile_paths if p != honest_tile]
        byzantine_tile = rng.choice(other_tiles)
        img_observed = load_tile(byzantine_tile)  # what byzantine actually saw
        img_revisit = perturb(load_tile(honest_tile), sun_shift, blur_sigma, occl_frac, rng)
        byz_name = byzantine_tile.name

    t0 = time.monotonic()
    obs_desc_topN = extract_topn(model, img_observed, n_top, device)
    revisit_desc_topN = extract_topn(model, img_revisit, n_top, device)
    inference_ms = (time.monotonic() - t0) * 1000

    # Mode A: take top-K of the observation as the transmitted descriptor set
    obs_modeA = obs_desc_topN[:k_modea]
    n_matches = match_lowe(obs_modeA, revisit_desc_topN, lowe_tau)
    V = n_matches / max(k_modea, 1)
    return V, n_matches, honest_tile.name, byz_name, inference_ms


def main() -> int:
    ap = argparse.ArgumentParser(description='Phase 1 PoO FAR/FRR runner')
    ap.add_argument('--dataset', default='/datasets/zurich-z16',
                    help='Directory of .png tiles')
    ap.add_argument('--out', default='/run-data/phase1-trials.csv')
    ap.add_argument('--n-honest', type=int, default=500)
    ap.add_argument('--n-byzantine', type=int, default=500)
    ap.add_argument('--n-top', type=int, default=50, help='top-N keypoints per frame')
    ap.add_argument('--k-modea', type=int, default=20, help='Mode A transmitted descriptors')
    ap.add_argument('--lowe-tau', type=float, default=0.7)
    ap.add_argument('--t-verify', type=float, default=0.3, help='VERIFIED threshold')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--sun-shifts', type=str, default='-30,0,30',
                    help='Comma-separated brightness shifts in [-255, 255]')
    ap.add_argument('--blur-sigmas', type=str, default='0,2',
                    help='Comma-separated gaussian-blur stddevs (px)')
    ap.add_argument('--occl-fracs', type=str, default='0,0.10',
                    help='Comma-separated occlusion fractions in [0, 1]')
    args = ap.parse_args()

    dataset_dir = Path(args.dataset)
    tile_paths = sorted(dataset_dir.glob('*.png'))
    if len(tile_paths) < 5:
        print(f'FAIL: need >=5 tiles, found {len(tile_paths)} in {dataset_dir}', file=sys.stderr)
        return 1
    print(f'[dataset] {len(tile_paths)} tiles in {dataset_dir}')

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'[device] {device}')

    print('[model] loading SuperPoint v1...')
    model = SuperPoint(max_num_keypoints=512).eval().to(device)

    rng = random.Random(args.seed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Sweep grid (CLI-overrideable)
    sun_grid = [float(x) for x in args.sun_shifts.split(',')]
    blur_grid = [float(x) for x in args.blur_sigmas.split(',')]
    occl_grid = [float(x) for x in args.occl_fracs.split(',')]

    print(f'[trials] honest={args.n_honest} byzantine={args.n_byzantine}')
    print(f'[sweep]  {len(sun_grid)}x{len(blur_grid)}x{len(occl_grid)} = '
          f'{len(sun_grid)*len(blur_grid)*len(occl_grid)} cells')

    results: list[TrialResult] = []
    trial_id = 0
    total = args.n_honest + args.n_byzantine
    for label, n in (('honest', args.n_honest), ('byzantine', args.n_byzantine)):
        for i in range(n):
            sun = rng.choice(sun_grid)
            blur = rng.choice(blur_grid)
            occl = rng.choice(occl_grid)
            V, n_matches, ht, bt, ms = run_trial(
                model, device, tile_paths, rng, label,
                args.n_top, args.k_modea, args.lowe_tau,
                sun, blur, occl,
            )
            results.append(TrialResult(
                trial_id=trial_id, label=label, t_verify_used=args.t_verify,
                V_score=V, n_matches=n_matches,
                sun_shift=sun, blur_sigma=blur, occl_frac=occl,
                honest_tile=ht, byzantine_tile=bt, inference_ms=ms,
            ))
            trial_id += 1
            if trial_id % 25 == 0:
                print(f'  ... {trial_id}/{total} trials, last: label={label} V={V:.3f} n_matches={n_matches} ms={ms:.0f}')

    # Write CSV
    with out_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'trial_id', 'label', 't_verify_used', 'V_score', 'n_matches',
            'sun_shift', 'blur_sigma', 'occl_frac', 'honest_tile',
            'byzantine_tile', 'inference_ms',
        ])
        for r in results:
            w.writerow([
                r.trial_id, r.label, r.t_verify_used, r.V_score, r.n_matches,
                r.sun_shift, r.blur_sigma, r.occl_frac, r.honest_tile,
                r.byzantine_tile, f'{r.inference_ms:.1f}',
            ])
    print(f'[out] {len(results)} rows -> {out_path}')

    # Quick summary at the locked T_verify
    honest_pass = sum(1 for r in results if r.label == 'honest' and r.V_score > args.t_verify)
    honest_total = sum(1 for r in results if r.label == 'honest')
    byz_pass = sum(1 for r in results if r.label == 'byzantine' and r.V_score > args.t_verify)
    byz_total = sum(1 for r in results if r.label == 'byzantine')
    frr = 1 - (honest_pass / honest_total) if honest_total else float('nan')
    far = byz_pass / byz_total if byz_total else float('nan')
    print('')
    print(f'==== Phase 1 quick summary @ T_verify={args.t_verify} ====')
    print(f'  honest:     {honest_pass}/{honest_total} VERIFIED ({(honest_pass/honest_total*100):.1f}%)')
    print(f'  byzantine:  {byz_pass}/{byz_total} (false-accept) ({(byz_pass/byz_total*100):.1f}%)')
    print(f'  FAR={far*100:.2f}%   FRR={frr*100:.2f}%')
    print(f'  pass criteria: FAR<5%, FRR<10%')
    fail = []
    if far >= 0.05:
        fail.append(f'FAR {far*100:.2f}% >= 5%')
    if frr >= 0.10:
        fail.append(f'FRR {frr*100:.2f}% >= 10%')
    if fail:
        print('  NOTE: FAIL at this T_verify -- ' + '; '.join(fail)
              + '  (this is a measurement, not a script error; see ROC sweep)')
    else:
        print('  PASS at T_verify=0.3 (ROC AUC sweep still needed for full plan compliance)')
    # Always exit 0 -- this script is a data collector; pass/fail is for
    # downstream analysis (phase1-batch-sweep.sh + ROC sweep).
    return 0


if __name__ == '__main__':
    sys.exit(main())
