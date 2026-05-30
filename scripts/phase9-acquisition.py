#!/usr/bin/env python3
"""Phase 9 acquisition v3 — Microsoft Planetary Computer pivot.

Why the pivot from CDSE STAC (v1/v2):
  - CDSE serves Sentinel-2 asset hrefs as s3://eodata/... which requires
    CDSE-issued S3 credentials (separate from password OAuth2) to download.
  - Microsoft Planetary Computer (MPC) mirrors the same Sentinel-2 L2A
    collection, serves assets as HTTPS Azure Blob URLs, and exposes a
    free public SAS-token signing endpoint requiring no account at all.

Outputs match v1/v2 exactly so downstream phase9-forgery-trials.py and
phase9-analyze.py are unchanged. Manifest CSV schema preserved.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import List

TILE_CENTERS = [
    ("urban_zurich",       47.3769,   8.5417),
    ("urban_munich",       48.1351,  11.5820),
    ("agric_padua",        45.4064,  11.8768),
    ("agric_lyon_rural",   45.7000,   4.5000),
    ("forest_blackforest", 47.9000,   8.2500),
    ("forest_vienna_hills",48.2500,  16.3500),
    ("mixed_geneva",       46.2044,   6.1432),
    ("mixed_innsbruck",    47.2692,  11.4041),
]

TARGET_DATES = [
    date(2024,  3, 15),
    date(2024,  6, 15),
    date(2024,  9, 15),
    date(2024, 12, 15),
    date(2025,  3, 15),
    date(2025,  9, 15),
]

TILE_SIZE_PX = 256
MPC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


@dataclass
class ScenePlanEntry:
    tile_id: str
    lat: float
    lon: float
    target_date: str
    actual_date: str
    scene_id: str
    cloud_cover_pct: float
    download_path: str


def find_scene(catalog, lat: float, lon: float, target: date,
               window_days: int = 45, max_cloud: float = 60.0):
    half = 0.012
    bbox = [lon - half, lat - half, lon + half, lat + half]
    dt_start = target - timedelta(days=window_days)
    dt_end = target + timedelta(days=window_days)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{dt_start.isoformat()}/{dt_end.isoformat()}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
        limit=50,
    )
    items = list(search.items())
    if not items:
        return None
    items.sort(key=lambda it: (
        abs((date.fromisoformat(it.properties["datetime"][:10]) - target).days),
        it.properties.get("eo:cloud_cover", 100),
    ))
    return items[0]


def download_visual_crop(item, lat: float, lon: float,
                         out_png: Path, tile_px: int) -> None:
    """Download MPC `visual` asset (TCI-equivalent RGB) and crop tile_px square."""
    import rasterio
    from rasterio.windows import Window
    from rasterio.warp import transform as rio_transform
    from PIL import Image

    visual = item.assets.get("visual")
    if visual is None:
        raise RuntimeError(f"no visual asset on {item.id}")
    href = visual.href  # already signed (modifier=pc.sign_inplace at client init)

    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")
    vsi_href = f"/vsicurl/{href}"

    with rasterio.open(vsi_href) as src:
        xs, ys = rio_transform("EPSG:4326", src.crs, [lon], [lat])
        col, row = src.index(xs[0], ys[0])
        half = tile_px // 2
        col0 = max(0, col - half)
        row0 = max(0, row - half)
        window = Window(col0, row0, tile_px, tile_px)
        rgb = src.read([1, 2, 3], window=window)

    if rgb.shape[1] < tile_px // 2 or rgb.shape[2] < tile_px // 2:
        raise RuntimeError(f"insufficient pixels for {out_png} (got {rgb.shape})")

    img = Image.fromarray(rgb.transpose(1, 2, 0))
    img.save(out_png)


def plan_acquisition() -> List[dict]:
    plan = []
    for tile_id, lat, lon in TILE_CENTERS:
        for tdate in TARGET_DATES:
            plan.append({
                "tile_id": tile_id, "lat": lat, "lon": lon,
                "target_date": tdate.isoformat(),
            })
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="workspaces/phase9-acquisition")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = plan_acquisition()
    out_dir = Path(args.out)

    if args.dry_run:
        for p in plan:
            print(f"[plan] tile={p['tile_id']} ({p['lat']:.4f},{p['lon']:.4f}) target={p['target_date']}")
        print(f"[plan] total = {len(plan)} scenes")
        return 0

    try:
        import pystac_client
        import planetary_computer as pc
        import rasterio  # noqa: F401
    except ImportError as e:
        print(f"FAIL: missing dep {e}", file=sys.stderr)
        return 1

    catalog = pystac_client.Client.open(MPC_STAC, modifier=pc.sign_inplace)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: List[ScenePlanEntry] = []

    t0 = time.time()
    for i, p in enumerate(plan):
        target = date.fromisoformat(p["target_date"])
        try:
            item = find_scene(catalog, p["lat"], p["lon"], target)
        except Exception as e:
            print(f"[search-fail {i+1}/{len(plan)}] {p['tile_id']} {p['target_date']}: {type(e).__name__}: {e}")
            continue
        if item is None:
            print(f"[skip {i+1}/{len(plan)}] no scene for {p['tile_id']} near {p['target_date']}")
            continue

        actual_date = item.properties["datetime"][:10]
        cloud = item.properties.get("eo:cloud_cover", -1)
        tile_dir = out_dir / p["tile_id"]
        tile_dir.mkdir(exist_ok=True)
        out_png = tile_dir / f"dt_{actual_date.replace('-', '')}.png"
        try:
            download_visual_crop(item, p["lat"], p["lon"], out_png, TILE_SIZE_PX)
            manifest.append(ScenePlanEntry(
                tile_id=p["tile_id"], lat=p["lat"], lon=p["lon"],
                target_date=p["target_date"], actual_date=actual_date,
                scene_id=item.id, cloud_cover_pct=float(cloud),
                download_path=str(out_png.relative_to(out_dir.parent)),
            ))
            elapsed = time.time() - t0
            print(f"[ok {i+1}/{len(plan)}] {p['tile_id']} target={p['target_date']} actual={actual_date} cloud={cloud:.1f}% t+{elapsed:.0f}s")
        except Exception as e:
            print(f"[fail {i+1}/{len(plan)}] {p['tile_id']} {p['target_date']}: {type(e).__name__}: {e}")
        time.sleep(0.3)

    if manifest:
        manifest_path = out_dir.parent / "phase9-acquisition-manifest.csv"
        with manifest_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(manifest[0]).keys()))
            writer.writeheader()
            for m in manifest:
                writer.writerow(asdict(m))
        print(f"[manifest] {len(manifest)}/{len(plan)} ok -> {manifest_path}")
    else:
        print("FAIL: 0 scenes acquired", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
