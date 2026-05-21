# PF-2 — Copernicus Data Space Ecosystem account

**Status:** ⏳ pending user signup
**Owner:** user (account creation requires personal email)

## Why we need this

Phase 0 needs Sentinel-2 satellite imagery to texture the Gazebo
ground plane (so the rendered camera frames have enough optical
detail for SuperPoint feature extraction). Phase 1 PoO uses
Sentinel-2 reference tiles as the "ground truth" the drones'
imagery is matched against. Phase 3 camera-driven TRN uses the same
imagery.

All Sentinel-2 data is **free** via Copernicus. The account only
exists for rate-limited API access.

## Signup steps

1. Go to https://dataspace.copernicus.eu
2. Click "Register" (top-right). Email + password. No phone /
   payment / institutional affiliation required.
3. Confirm via the verification email.
4. After confirmation, sign in at https://dataspace.copernicus.eu
   to verify the account is active.

That's it — no waiting period, no approval.

## Where to put credentials

Copy `.env.example` to `.env` (gitignored) in the project root, fill in:

```
CDSE_USERNAME=your.email@example.com
CDSE_PASSWORD=your-password-here
```

These will be picked up by Phase 0 dataset staging scripts via
python-dotenv. Do NOT commit `.env` — it's in `.gitignore`.

## API / library

We use the modern CDSE OData + STAC API via:
- `cdsetool` (Python) for catalog search + bulk download
- `pystac-client` for STAC queries
- `rasterio` for reading the downloaded GeoTIFFs

All three are already in `Dockerfile.cpu` pip install block (well,
`sentinelsat` is there but that's the legacy SciHub client — when we
implement Phase 0 dataset staging we'll swap it for `cdsetool` or just
use the OAuth + requests directly).

## Rate limits

CDSE free tier is generous but not infinite:
- ~30 GB / day download cap
- Concurrent connection cap: 4 simultaneous downloads
- Catalog API: ~50 req/min

For our region-of-interest (one ~100 km × 100 km patch, 1-2 tiles
covering it, recent cloud-free acquisitions), this is well within
limits.

## Status note (update when done)

After signup, edit this file:
- Replace "⏳ pending user signup" with "✅ done"
- Add the email used (so future agents know which account)
- Add date
