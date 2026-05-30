# vast.ai setup recipe — Phase 9 (same-region forgery)

Step-by-step recipe to reproduce the Phase 9 campaign on a fresh
vast.ai GPU instance.

**Estimated end-to-end time:** 30–60 min (most of it is acquisition
network I/O; the GPU inference for 1500 trials is ~1–2 min on RTX 3090).

**Estimated cost:** ~$1–3 (RTX 3090 spot is ~$0.20/hr).

---

## 1. Instance selection

- **Image:** `pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime` (or the
  `uav-lab:gpu` image already published at
  `ghcr.io/a3ka/uav-lab:gpu` for Phase 1 reuse).
- **GPU:** any single CUDA-capable GPU with ≥ 8 GB VRAM. RTX 3060 /
  3070 / 3080 / 3090 / 4070+ all fine. CPU torch also works but is
  ~30× slower.
- **Disk:** 30 GB scratch is plenty (Sentinel-2 TCI tiles cropped to
  256×256 px are ~50 kB each; full plan = 48 scenes ≈ 3 MB).
- **Bandwidth:** any.

Recommended search filter on vast.ai:
`gpu_name in ['RTX 3090', 'RTX 4090', 'RTX 3080'] and verified=True and reliability>0.95 and dlperf>20`

## 2. CDSE (Copernicus Data Space Ecosystem) account

Required to download Sentinel-2 L2A scenes (the data are free; the
account is for API rate-limit attribution).

1. Register: <https://dataspace.copernicus.eu/>
2. Verify email.
3. Note the username and password — you will export them as env vars
   on the vast.ai instance.

There is **no payment step** at CDSE. The data are public.

## 3. On the vast.ai instance — one-time setup

```bash
# Clone the repository (use SSH key uploaded via vast.ai console
# or git clone over HTTPS with a personal access token)
git clone https://github.com/ok-research/bft-uav-swarm-validation-lab.git
cd bft-uav-swarm-validation-lab

# Pull the Phase 9 tag (or main if running against the tip)
git checkout v1.2-phase9   # tag will exist after Phase 9 lands

# Python dependencies (most are already in the published GPU image;
# the only new one for Phase 9 is the Sentinel-2 client stack)
pip install --quiet \
    lightglue \
    pystac-client \
    odc-stac \
    rasterio \
    requests \
    Pillow \
    opencv-python-headless \
    matplotlib \
    numpy

# Verify the GPU is visible to torch
python3 -c "import torch; print('cuda:', torch.cuda.is_available(), \
torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

If the line prints `cuda: True <gpu name>`, the GPU half of the
campaign is ready.

## 4. Credentials

```bash
export CDSE_USERNAME='<your-cdse-username>'
export CDSE_PASSWORD='<your-cdse-password>'
```

(For persistent runs, write these into a `.env` and `source .env`.)

## 5. Single-command execution

```bash
./scripts/phase9-campaign.sh
```

This runs all three steps in sequence:

1. **`phase9-acquisition.py`** — fetches Sentinel-2 L2A scenes for
   the locked 8 tile locations × 6 dates = 48 scenes. Crops each
   to 256×256 px PNG. Writes
   `workspaces/phase9-acquisition/<tile_id>/dt_<YYYYMMDD>.png`.
   ~15-25 min depending on CDSE latency.
2. **`phase9-forgery-trials.py`** — runs SuperPoint v1 + Lowe matcher
   on 1500 trials (500 honest revisit, 500 wrong-region fab, 500
   same-region fab). Writes
   `workspaces/phase9-sweep/forgery_trials.csv`. ~1–2 min on GPU.
3. **`phase9-analyze.py`** — builds histograms, ROC, decision per
   the pre-registered interpretation matrix. Writes
   `docs/results/phase-9.md` (overwrites template).

## 6. Pulling results back

Three things must come off the instance before it is destroyed:

```bash
# (from your local machine, with vast.ai ssh)
scp -P <port> root@<instance-ip>:/workspace/bft-uav-swarm-validation-lab/workspaces/phase9-sweep/forgery_trials.csv ./
scp -r -P <port> root@<instance-ip>:/workspace/bft-uav-swarm-validation-lab/workspaces/phase9-sweep/figures ./
scp -P <port> root@<instance-ip>:/workspace/bft-uav-swarm-validation-lab/docs/results/phase-9.md ./
```

The acquisition tiles themselves are gitignored — they do not need
to come back (re-runnable from the manifest CSV which is committed).

## 7. Commit results to the lab repo

On your local machine, after pulling the CSV + figures:

```bash
# Replace the template results/phase-9.md with the populated one
cp /tmp/phase-9.md docs/results/phase-9.md

# Forgery trials are gitignored under workspaces/, but the
# acquisition manifest is committed:
git add workspaces/phase9-acquisition-manifest.csv
git add docs/results/phase-9.md
git commit -m "Phase 9 — same-region forgery results"
git push
```

The paper `.tex` is updated separately in the paper-authoring
workspace; after results land here, run an audit-delta on the paper
to integrate the new numbers into §IV-B (PoO unforgeability claim)
and into the Limitations section per the pre-registered
interpretation matrix.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cuda: False` | GPU not exposed to container | Restart instance with `--gpus all`; ensure `nvidia-container-toolkit` is active |
| CDSE 401 | Wrong credentials | Re-export `CDSE_USERNAME` / `CDSE_PASSWORD` |
| CDSE 429 | Rate limit | The script already sleeps 0.5 s between requests; if persistent, increase to 2 s in `phase9-acquisition.py` |
| `no scene for <tile>` for many tiles | Cloud cover > 30 % in the search window | Open `phase9-acquisition.py`, lift the `eo:cloud_cover < 30` filter to `< 60` |
| `lightglue` ImportError | Old pytorch | `pip install lightglue --upgrade` |
| Trials run but `same_region_fab` produces 0 rows | Each tile has only one date | Re-run acquisition; ensure 6 distinct dates per tile arrived |

---

## Audit and credibility

The pre-registered design and interpretation matrix is in
`docs/phase-9-spec.md` and is committed **before** the campaign is
run. Any of the three pre-registered outcomes is publishable. The
spec, the campaign script, the results doc, the figures, and the
raw CSV (via the published companion repo and Zenodo DOI) together
constitute a fully reproducible test of the paper's central PoO
unforgeability claim.
