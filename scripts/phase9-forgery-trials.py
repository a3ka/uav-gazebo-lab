#!/usr/bin/env python3
"""Phase 9 — same-region forgery trials.

For each (tile, date_v, date_a) triple drawn from the acquisition manifest:
  - load tile-of-region at date_v (verifier acquisition)
  - load tile-of-region at date_a (adversary acquisition, date_a != date_v)
  - run SuperPoint v1 on each, extract K=20 Mode-A descriptors
  - compute V_score = matched_descriptors / K with Lowe ratio τ=0.7
  - emit one CSV row per trial

Three trial populations are run in one batch:
  honest_revisit     : verifier = perturbed(tile_v), adversary = tile_v (self;
                       acts as positive control)
  wrong_region_fab   : verifier = tile_v, adversary = tile_OTHER at any date
                       (Phase 1 weak adversary, recomputed for consistency)
  same_region_fab    : verifier = tile_v, adversary = tile_v at date_a != date_v
                       (Phase 9 strong adversary)

For same-region pairs, also record the temporal gap so the analyzer can
bin into same-season / cross-season / cross-year.

Settings locked to Phase 1 / paper Mode A:
  SuperPoint v1 (LightGlue MagicLeap weights)
  top-N = 50 keypoints, K = 20 transmitted descriptors
  matcher: brute-force NN + Lowe ratio τ = 0.7
  decision: VERIFIED iff V > T_verify (default 0.30)
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, fields
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch


# --------------------------- SuperPoint --------------------------- #

try:
    from lightglue import SuperPoint
except ImportError:
    print("FAIL: lightglue not installed. On vast.ai: pip install lightglue",
          file=sys.stderr)
    sys.exit(1)


def perturb(img: np.ndarray, sun_shift: float, blur_sigma: float,
            occl_frac: float, rng: random.Random) -> np.ndarray:
    """Identical to Phase 1 perturbation envelope (honest revisit noise)."""
    out = img.astype(np.float32)
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


def extract_topk(model: SuperPoint, img: np.ndarray, k: int,
                 device: str) -> torch.Tensor:
    """Run SuperPoint and return top-K descriptors by score, shape [K, 256]."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    t = torch.from_numpy(gray)[None, None, ...].to(device)
    with torch.no_grad():
        out = model({"image": t})
    desc = out["descriptors"][0]
    scores = out["keypoint_scores"][0]
    if desc.shape[0] == 0:
        return torch.zeros((0, 256), device=device)
    take = min(k, desc.shape[0])
    top = torch.topk(scores, take).indices
    return desc[top]


def v_score(desc_a: torch.Tensor, desc_b: torch.Tensor,
            lowe_tau: float = 0.7) -> Tuple[float, int]:
    """Brute-force NN matcher with Lowe ratio. Returns (V_score, n_matches).

    V_score = accepted_matches / K where K is the number of descriptors
    transmitted by the claimant (here, desc_a).
    """
    K = desc_a.shape[0]
    if K == 0 or desc_b.shape[0] < 2:
        return 0.0, 0

    # L2 distance matrix [K, M]
    d = torch.cdist(desc_a, desc_b)
    # Two nearest neighbours per row
    top2 = torch.topk(d, k=2, largest=False).values  # [K, 2]
    ratio = top2[:, 0] / top2[:, 1].clamp(min=1e-8)
    accepted = (ratio < lowe_tau).sum().item()
    return accepted / K, int(accepted)


# --------------------------- Trial driver --------------------------- #

@dataclass
class TrialRow:
    trial_id: int
    population: str        # honest_revisit | wrong_region_fab | same_region_fab
    tile_id_verifier: str
    tile_id_adversary: str
    date_verifier: str     # ISO yyyy-mm-dd
    date_adversary: str
    temporal_gap_days: int # signed; 0 for honest_revisit and wrong_region_fab
    sun_shift: float       # perturbations applied to verifier image (honest only)
    blur_sigma: float
    occl_frac: float
    v_score: float
    n_matches: int
    t_verify: float
    inference_ms: float


def load_image(p: Path) -> np.ndarray:
    img = cv2.imread(str(p))
    if img is None:
        raise FileNotFoundError(p)
    return img


def daydiff(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def discover_tiles(acquisition_dir: Path) -> dict:
    """Return {tile_id: [(date, path), ...]} sorted by date."""
    tiles = defaultdict(list)
    for tile_subdir in acquisition_dir.iterdir():
        if not tile_subdir.is_dir():
            continue
        tile_id = tile_subdir.name
        for png in sorted(tile_subdir.glob("dt_*.png")):
            # filename dt_YYYYMMDD.png
            stem = png.stem.replace("dt_", "")
            iso = f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}"
            tiles[tile_id].append((iso, png))
    return dict(tiles)


def run_population_trials(model: SuperPoint, device: str,
                          tiles: dict, population: str,
                          n_trials: int, t_verify: float,
                          rng: random.Random, start_id: int) -> List[TrialRow]:
    rows: List[TrialRow] = []
    tile_ids = sorted(tiles.keys())

    for i in range(n_trials):
        tid_v = rng.choice(tile_ids)
        dates = tiles[tid_v]
        if len(dates) < 2:
            continue
        d_v_iso, d_v_path = rng.choice(dates)

        # Build (verifier_img, adversary_img) per population
        if population == "honest_revisit":
            verifier_img = perturb(
                load_image(d_v_path),
                sun_shift=rng.uniform(-15, 15),
                blur_sigma=rng.choice([0.0, 0.5, 1.0]),
                occl_frac=0.0,
                rng=rng,
            )
            adversary_img = load_image(d_v_path)
            tid_a = tid_v
            d_a_iso = d_v_iso
            gap = 0
            ss, bs, of = -1, -1, -1  # not applicable; record perturb vals below
        elif population == "wrong_region_fab":
            verifier_img = load_image(d_v_path)
            other_tiles = [t for t in tile_ids if t != tid_v]
            tid_a = rng.choice(other_tiles)
            d_a_iso, d_a_path = rng.choice(tiles[tid_a])
            adversary_img = load_image(d_a_path)
            gap = daydiff(d_a_iso, d_v_iso)
            ss, bs, of = 0, 0, 0
        elif population == "same_region_fab":
            verifier_img = load_image(d_v_path)
            # Pick a *different date* of the same tile
            other_dates = [(d, p) for (d, p) in dates if d != d_v_iso]
            if not other_dates:
                continue
            d_a_iso, d_a_path = rng.choice(other_dates)
            adversary_img = load_image(d_a_path)
            tid_a = tid_v
            gap = daydiff(d_a_iso, d_v_iso)
            ss, bs, of = 0, 0, 0
        else:
            raise ValueError(population)

        t0 = time.perf_counter()
        desc_a = extract_topk(model, adversary_img, k=20, device=device)
        desc_v = extract_topk(model, verifier_img, k=50, device=device)
        v, n = v_score(desc_a, desc_v, lowe_tau=0.7)
        infer_ms = (time.perf_counter() - t0) * 1000.0

        rows.append(TrialRow(
            trial_id=start_id + i,
            population=population,
            tile_id_verifier=tid_v,
            tile_id_adversary=tid_a,
            date_verifier=d_v_iso,
            date_adversary=d_a_iso,
            temporal_gap_days=gap,
            sun_shift=float(ss),
            blur_sigma=float(bs),
            occl_frac=float(of),
            v_score=float(v),
            n_matches=int(n),
            t_verify=float(t_verify),
            inference_ms=float(infer_ms),
        ))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--acquisition", default="workspaces/phase9-acquisition",
                    help="Directory containing tile_id/dt_YYYYMMDD.png files.")
    ap.add_argument("--out", default="workspaces/phase9-sweep/forgery_trials.csv",
                    help="CSV output path.")
    ap.add_argument("--n-honest", type=int, default=500)
    ap.add_argument("--n-wrong", type=int, default=500)
    ap.add_argument("--n-same", type=int, default=500)
    ap.add_argument("--t-verify", type=float, default=0.30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default=None,
                    help="cuda / cpu / mps (auto-detect by default).")
    args = ap.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    acquisition_dir = Path(args.acquisition)
    tiles = discover_tiles(acquisition_dir)
    if not tiles:
        print(f"FAIL: no tiles in {acquisition_dir}; run phase9-acquisition.py first.",
              file=sys.stderr)
        return 1
    print(f"[tiles] {len(tiles)} tile locations, "
          f"{sum(len(v) for v in tiles.values())} (tile,date) scenes")

    rng = random.Random(args.seed)
    model = SuperPoint(max_num_keypoints=2048).eval().to(device)

    all_rows: List[TrialRow] = []
    for pop, n in [("honest_revisit", args.n_honest),
                   ("wrong_region_fab", args.n_wrong),
                   ("same_region_fab", args.n_same)]:
        print(f"[{pop}] running {n} trials ...")
        rows = run_population_trials(
            model, device, tiles, pop, n, args.t_verify, rng,
            start_id=len(all_rows),
        )
        all_rows.extend(rows)
        print(f"[{pop}] done, {len(rows)} rows")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(TrialRow)]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in all_rows:
            w.writerow(asdict(row))
    print(f"[csv] {len(all_rows)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
