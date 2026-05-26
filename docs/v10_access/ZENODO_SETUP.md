# Zenodo DOI setup for `uav-gazebo-lab` release

Setup the GitHub↔Zenodo connection ONCE, then any future `git tag` push
auto-generates a new Zenodo deposit with its own DOI. Used to cite the
release from §X Code & Data Availability.

---

## One-time GitHub↔Zenodo link (~10 min)

1. Go to https://zenodo.org/account/settings/github/
2. Sign in with GitHub (OAuth — Zenodo asks only for public-repo read access)
3. Find `a3ka/uav-gazebo-lab` in the repository list
4. Toggle the switch to **ON**

That's it. From now on every GitHub tagged release becomes a Zenodo
deposit automatically.

---

## Tag and release for v10 submission (do after F-IP cleared, ~5 min)

```bash
cd /home/nous/research/uav-gazebo-lab

# Verify clean tree
git status                              # should show clean or only paper-edit files
git add docs/v10_access/                 # if you want paper sources tracked
git commit -m "v10 IEEE Access submission state"

# Tag
git tag -a v1.0.0 -m "IEEE Access submission v10 — Phases 1-8 empirical validation"
git push origin main
git push origin v1.0.0
```

Then on GitHub:

1. Go to https://github.com/a3ka/uav-gazebo-lab/releases
2. Click "Draft a new release" → choose tag `v1.0.0`
3. Title: `v1.0.0 — IEEE Access submission (Phases 1-8 empirical validation)`
4. Description (paste):
   ```
   Companion release for IEEE Access submission of "Byzantine-Fault-Tolerant
   Hierarchical Navigation for GNSS-Denied UAV Swarms: Architecture,
   Theoretical Analysis, and Empirical Validation" (Kalynovskyi, 2026).

   Contents:
   - ROS 2 + Gazebo + Python validation stack
   - Production sweep workspaces for Phases 1-8 (raw CSVs + analysis.json)
   - Per-phase reproducibility docs in docs/results/phase-{1..8}.md
   - Docker recipes (uav-lab:cpu, uav-lab:gpu)
   - Sweep configurations and analysis scripts

   Companion paper PDF and source available at:
   <link to arXiv or DOI of paper if posted preprint>

   Companion abstract Monte Carlo simulators (Sections VIII-X of the paper)
   are at github.com/ok-research/bft-uav-swarm-validation v1.1.

   Citation: see manuscript Section X (Code and Data Availability) for full
   citation block including this Zenodo DOI.
   ```
5. Click "Publish release"

---

## Zenodo deposit metadata (~5 min)

Zenodo auto-creates the deposit within 1-2 min. To finalize metadata:

1. Go to https://zenodo.org/account/settings/github/
2. Find the new deposit (will show "v1.0.0 — IEEE Access submission" entry)
3. Click "View" → opens the auto-created deposit
4. Click "Edit" → fill in:
   - **Title**: `bft-uav-validation-lab v1.0.0: Empirical validation testbed for BFT UAV swarm navigation`
   - **Authors**: `Kalynovskyi, Oleksandr` + ORCID `0009-0009-1437-3252`
   - **Description**: copy from GitHub release description above
   - **License**: MIT (auto-detected from repo LICENSE file)
   - **Keywords**: `UAV swarm`, `Byzantine fault tolerance`, `GNSS-denied
     navigation`, `factor graph`, `ROS2`, `Gazebo`, `reproducibility`
   - **Related identifiers**: Add entry `is supplement to` → DOI of the
     IEEE Access paper (after IEEE assigns one)
5. Click "Publish"

DOI appears as `10.5281/zenodo.NNNNNNN`. Copy it.

---

## Update paper

Replace placeholder in §X Code & Data Availability:

```bash
F=/home/nous/research/uav-gazebo-lab/docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex
sed -i 's|10\.5281/zenodo\.XXXXXXX|10.5281/zenodo.NNNNNNN|g' "$F"

# Verify
grep -n 'zenodo' "$F"
# Should show real DOI, not XXXXXXX
```

Then recompile in Docker and re-sync to audit-harness:

```bash
docker run --rm -v /home/nous/research/uav-gazebo-lab:/work \
  texlive/texlive:latest bash -c \
  'cd /work/docs/v10_access && \
   pdflatex -interaction=nonstopmode BFT_UAV_Swarm_Paper_v10_access.tex >/dev/null && \
   pdflatex -interaction=nonstopmode BFT_UAV_Swarm_Paper_v10_access.tex >/dev/null && \
   echo exit=$? && ls -la BFT_UAV_Swarm_Paper_v10_access.pdf'

cp /home/nous/research/uav-gazebo-lab/docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.{tex,pdf} \
   /home/nous/research/audit-harness/inputs/papers/
```

---

## Verification

```bash
# Resolve DOI to confirm it works (replace NNNNNNN with real)
curl -sI https://doi.org/10.5281/zenodo.NNNNNNN | head -5
# Expect: HTTP/2 302 with Location header pointing to zenodo.org/records/NNNNNNN
```

If the DOI resolves to the right deposit landing page → done.

---

## Future versions

Every subsequent `git tag` + GitHub release auto-creates a NEW Zenodo
deposit with a NEW DOI. Each version is independently citable. Zenodo
also assigns a "concept DOI" that always resolves to the latest version
(useful for general-purpose citations; we use the version-specific DOI
in the paper for reproducibility).

---

## Costs

Zenodo: free for academic deposits up to 50 GB per deposit.
GitHub: free for public repos.

---

## Backout plan

If for any reason the Zenodo auto-link fails:

1. Manual upload at https://zenodo.org/uploads/new
2. Upload a tarball of the entire `uav-gazebo-lab` repository state at tag `v1.0.0`:
   ```bash
   cd /home/nous/research
   git -C uav-gazebo-lab archive --format=tar.gz --prefix=uav-gazebo-lab-v1.0.0/ v1.0.0 > uav-gazebo-lab-v1.0.0.tar.gz
   ```
3. Fill in metadata as above; publish to obtain DOI.

End of Zenodo setup guide.
