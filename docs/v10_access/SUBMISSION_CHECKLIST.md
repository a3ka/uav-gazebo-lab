# IEEE Access Submission Checklist — v10

End-to-end checklist for the IEEE Author Portal upload step (after all
audit cycles are clean and Phase F items resolved). Print this and tick
each item before clicking Submit.

---

## Pre-flight blockers (must all be ✓ before opening Author Portal)

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | All audit MINORs resolved (0/0/0 from `/audit-readiness`) | Sonnet | ☐ |
| 2 | DPMA F-IP уточнение для admission control submitted | Author | ☐ (tomorrow) |
| 3 | Author photo `docs/v10_access/author_photo.eps` (or .pdf/.png) supplied | Author | ☐ (later) |
| 4 | Tagged GitHub release `uav-gazebo-lab` v10.0 pushed | Author | ☐ |
| 5 | Zenodo DOI assigned (auto from GitHub release via Zenodo↔GitHub link) | Author | ☐ |
| 6 | `\hypersetup{pdftitle}` confirmed updated to "Empirical Validation" | Sonnet (done) | ☑ |
| 7 | Zenodo DOI placeholder `XXXXXXX` replaced with real DOI in §X Code & Data | Author | ☐ |
| 8 | Final compile in `texlive/texlive:latest` Docker passes (exit=0, errors=0) | Sonnet | ☐ |
| 9 | **IEEE PDF eXpress check passed** (see Section "PDF eXpress" below) | Author | ☐ |

---

## IEEE PDF eXpress check (mandatory before IEEE accepts upload)

IEEE PDF eXpress validates the compiled PDF for:
- All fonts embedded (Type 1 / TrueType)
- PDF version compliance (typically 1.4 - 1.6)
- No font subsetting errors
- No password protection / no DRM
- Page size matches venue (US Letter for IEEE Access)

**How to use** (free, ~10 min including queue):

1. Go to https://ieee-pdf-express.org/account/login
2. Create/login. **Conference ID for IEEE Access**: use the conference/journal
   identifier provided by IEEE Access; if unknown, use general IEEE
   account.
3. Upload `BFT_UAV_Swarm_Paper_v10_access.pdf`
4. Wait for emailed validation report (typically <10 min)
5. If PASS → you get an "IEEE Xplore-compatible" PDF back, use THAT for
   submission (not your local pdflatex output)
6. If FAIL → fix the flagged issues (usually font embedding); re-upload

**Common failure modes** (fix in source):
- Missing font embedding: add `\usepackage[T1]{fontenc}` (already present)
  + ensure all `\includegraphics` files have embedded fonts themselves
  (e.g., for EPS graphics, embed fonts in EPS export)
- Type 3 fonts (bitmap) instead of Type 1: usually from `bitmap` package
  or old `psfrag`; convert sources to vector
- Form fields / annotations: remove any `\hypertarget`-based interactive
  elements (we use only `hyperref` for cross-refs, should be fine)

---

## Submission package — exact files for IEEE Author Portal

IEEE Access Author Portal accepts a **source bundle** (preferred for
LaTeX submissions) + the **compiled PDF** + supplementary files.

### Required uploads

1. **Source tarball** — single `.tar.gz` containing:
   ```
   BFT_UAV_Swarm_Paper_v10_access.tex            ← main source
   BFT_UAV_Swarm_Paper_v10_access.bbl            ← (only if using BibTeX; we use inline \bibitem so skip)
   BFT_UAV_Swarm_Paper_v9_8/code/asymmetric_decay/results/detection_latency_vs_ratio.png
   BFT_UAV_Swarm_Paper_v9_8/code/asymmetric_decay/results/round_detection_rate_N100_f020.png
   BFT_UAV_Swarm_Paper_v9_8/code/clamp_convergence/results/theory_vs_empirical_ratio.png
   BFT_UAV_Swarm_Paper_v9_8/code/byzantine_scaling/results/byzantine_resilience_curve.png
   author_photo.eps                              ← (when supplied)
   ```
   Build:
   ```bash
   cd /home/nous/research/uav-gazebo-lab/docs/v10_access
   tar czf BFT_UAV_v10_source.tar.gz \
     BFT_UAV_Swarm_Paper_v10_access.tex \
     BFT_UAV_Swarm_Paper_v9_8/code/asymmetric_decay/results/*.png \
     BFT_UAV_Swarm_Paper_v9_8/code/clamp_convergence/results/*.png \
     BFT_UAV_Swarm_Paper_v9_8/code/byzantine_scaling/results/*.png \
     author_photo.eps   # ← uncomment when photo file exists
   ```

2. **Compiled PDF (PDF eXpress validated)** — `BFT_UAV_Swarm_Paper_v10_access.pdf`
   - Upload the IEEE-eXpress-blessed version, NOT raw pdflatex output

3. **Graphical abstract** — `graphical_abstract/main.pdf` (or .png at 300dpi)
   - Mark as "Graphical Abstract" in supplementary file metadata
   - Mention in cover letter

4. **Cover letter** — copy content of `COVER_LETTER.md` into Author Portal's
   cover-letter textarea (Author Portal stores as plaintext; markdown
   formatting is OK but no need for markdown-specific renderers)

5. **(Optional)** — Demo video if available (e.g., Gazebo N=5 multi-PX4 flight)
   - Mark as "Multimedia Supplement"
   - Reference in §VI Phase 6 Tier A paragraph if uploaded

### Author Portal form fields

When asked in the Portal:

- **Article type**: Original Research Article
- **Title**: copy from \title{} macro (single line, no LaTeX)
- **Abstract**: copy from \begin{abstract}...\end{abstract} (plaintext, max
  250 words; portal will reject longer)
- **Keywords**: copy from IEEEkeywords list (comma-separated)
- **Suggested reviewers**: leave blank OR list 2-3 names from cover letter
  reviewer-competences section (no obligation; helpful if you know specific
  reviewers in BFT-swarms or UWB-localization subfields)
- **Conflicts of interest**: declare DPMA patent pending (10 2026 001 712.2)
  per cover-letter Declarations
- **Funding statement**: "This work received no external funding."
- **AI disclosure**: per Acknowledgements/AI Disclosure section of paper
- **License**: CC BY 4.0 (gold OA default for IEEE Access)
- **Copyright transfer**: complete eCF (electronic Copyright Form) when
  prompted at acceptance (NOT at submission)

### Author Portal navigation

1. https://ieee.atyponrex.com/journal/IEEE-Access (IEEE Access portal)
2. "Submit a Manuscript"
3. Walk through 7-step wizard:
   - Step 1: Article type + title
   - Step 2: Authors (single author; complete affiliation + ORCID)
   - Step 3: Abstract + keywords
   - Step 4: Cover letter (paste)
   - Step 5: File upload (source tarball + PDF + graphical abstract +
     supplementary)
   - Step 6: Suggested reviewers (optional)
   - Step 7: Review + Submit

Expected confirmation email within 1 hour with manuscript ID.

---

## After submission

- **Editor desk-review**: 1-7 days. If desk-rejected (very rare for technically
  sound submissions): receive feedback, can resubmit with revisions.
- **Peer review**: 3-6 weeks (IEEE Access target). 2-3 reviewers, binary
  accept/reject. No major-revision rounds (minor revisions only).
- **Decision**: accept-with-minor-revisions (most common positive outcome) /
  reject-with-feedback / accept-as-is (rare).
- **Acceptance**: pay APC ($2,160 flat, member discount applicable), sign
  eCF, get publication slot. Publication typically 4-6 weeks
  submission-to-published in IEEE Xplore.

---

## Post-acceptance reproducibility commitments

Once accepted, before publication:

1. Replace `XXXXXXX` Zenodo DOI placeholder (if not done at submission)
2. Confirm GitHub `uav-gazebo-lab` v10.0 tag matches manuscript content
   exactly (no in-flight changes during peer review)
3. Confirm Zenodo DOI resolves and matches GitHub tag SHA
4. Final pdftotext check — confirm no PDF-extracted text reveals
   author-only-known internal annotations

---

## Roll-back plan

If something blocks at the Author Portal stage:

| Block | Fix path |
|---|---|
| PDF eXpress font failure | Re-compile in Docker, double-check `\usepackage[T1]{fontenc}` |
| Page-size mismatch | Force `\documentclass[a4paper,journal,twocolumn]{IEEEtran}` if portal demands A4 (IEEE Access accepts both Letter and A4) |
| File upload limit (typically 25 MB total) | Compress graphical abstract PNG; remove demo video if too large |
| Source-bundle BibTeX expected | Convert inline `\bibitem` to BibTeX (deferred Phase F item; can do under pressure) |
| eCF not recognized | Re-do at IEEE eCF portal, contact IEEE Help (help@ieee.org) |

---

End of submission checklist.
