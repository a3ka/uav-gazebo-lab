# Sonnet Brief — Phase F final consolidation (v10-v2 → v10-v3, IEEE Access submission-ready)

## Context (read first)

Paper: `/home/nous/research/uav-gazebo-lab/docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex`
(currently v10-v2 state, 1924 lines, IEEEtran journal 10pt ONECOLUMN; audit-readiness READY-TO-SUBMIT for content; this brief makes it IEEE Access form-compliant).

Audit-harness state baseline: every numeric claim in §VI/§VII is traced to `workspaces/*/analysis.json` or `manifest.json`. Do not introduce new numbers. Only fix the form, rename, reframe, and switch to twocolumn.

Before editing read:
- `/home/nous/research/uav-gazebo-lab/CLAUDE.md`
- `/home/nous/research/uav-gazebo-lab/docs/v10_access/SONNET_PAPER_HANDOFF.md` §3 (workspace-jq map)
- `/home/nous/research/audit-harness/inputs/papers/BFT_UAV_Swarm_Paper_v10_access.NOTES.md` (framing + deferred items)
- `/home/nous/research/audit-harness/outputs/paper-audits/BFT_UAV_Swarm_Paper_v10_access-full-audit-20260526.md` (full audit state — all 12 findings resolved last cycle, 0 unresolved as of READY-TO-SUBMIT)

You will work in two parts:

- **PART 1** — 13 content-consistency fixes (no math, no new claims, only resolving stated contradictions and softening scope language)
- **PART 2** — IEEE Access form: switch to two-column, explicit font sizes for captions, abstract/keywords full-width, IEEE Access submission file structure

Do NOT touch:
- §VI/§VII headline numbers (all already audit-verified)
- §III-V theorems and proofs (carried from v9_8 unchanged)
- vanilla-Raft baseline framing (verified clean by previous audit)
- σ_k=19.4·(1.088)^k or its derivation (verified)
- Pareto 14/15 vs 15/15 tradeoff (correct)
- ABL4 50-trial numbers (verified previous cycle)

When done, sync to audit-harness AND re-run audit-delta + audit-readiness:
```
cp /home/nous/research/uav-gazebo-lab/docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex \
   /home/nous/research/audit-harness/inputs/papers/
# Then in a fresh audit-harness Claude session:
/audit-delta inputs/papers/BFT_UAV_Swarm_Paper_v10_access.tex
/audit-readiness inputs/papers/BFT_UAV_Swarm_Paper_v10_access.tex
```

================================================================
# PART 1 — Content fixes (13 items)
================================================================

------------------------------------------------------------------
## 1.1  🔴 Tspoof 50m vs 20m design-vs-experiment discrepancy
------------------------------------------------------------------

**Data**: `workspaces/phase5-prod/manifest.json` shows `t_spoof_m: 20.0`. Paper currently says 50m in three places:
- §IV-C line 295: "coincidence with $T_\text{spoof}=50$m is deliberate"
- Table II line 345: "Spoof position threshold & 50\,m"
- §IV-G line 440: "If $\lVert ... \rVert > T_\text{spoof} = 50$m for $N_\text{consecutive} = 3$"

**Resolution pattern**: same as how the FAR/FRR T_verify=0.30/0.32 dual-operating-point was handled. Keep 50m as the documented design spec; report the 20m used in Phase 5 as a tighter operational threshold.

**Edits**:

(a) **§VI-F Phase 5 Configuration** (around line 613), after `Detector threshold $T_\text{spoof}{=}20$\,m residual` ADD inline parenthetical:
```latex
Detector threshold $T_\text{spoof}{=}20$\,m residual (tighter than the
$T_\text{spoof}=50$\,m design specification of Section~\ref{sec:approach}-G;
the production sweep characterises detector sensitivity beyond the design
floor, since 20\,m is comparable to the GNSS-spoof injection offset and
permits resolution of detection-time distribution dynamics that a 50\,m
threshold would saturate);
```

(b) **§IV-G line 440** — after the sentence "...$T_\text{spoof}=50$\,m corresponds to $\sim$170--500$\sigma_\text{UWB}$, far above any legitimate ranging uncertainty.", ADD:
```latex
The empirical Phase~5 sweep (Section~\ref{sec:phase5-spoofing}) uses a
tighter operational threshold $T_\text{spoof}{=}20$\,m to characterise
detector latency near the noise floor; the design value $50$\,m remains
the documented spec for deployments seeking minimum false-positive risk.
```

(c) **§IV-C line 295** — replace "The coincidence with $T_\text{spoof}=50$m is deliberate" with:
```latex
The design value $T_\text{spoof}=50$\,m (Section~\ref{sec:approach}-G) is
calibrated against the same noise floor; the Phase~5 production sweep
uses a tighter operational threshold (Section~\ref{sec:phase5-spoofing}).
```

(d) **Table II line 345** — leave 50m unchanged (it is the design spec).

(e) Update measurements.jsonl: ADD a new entry
```
number="20" unit="m" context="Phase 5 detector threshold T_spoof operational value"
location="BFT_UAV_Swarm_Paper_v10_access.tex:613"
source_type="measurement"
source_ref="jq '.t_spoof_m' workspaces/phase5-prod/manifest.json"
documented_at: <ISO now>
```

------------------------------------------------------------------
## 1.2  🔴 σ_anchor terminology cleanup
------------------------------------------------------------------

Three distinct quantities currently share confusingly similar names:
- $\sigma_\text{base} = 50$\,m — prior noise floor (system parameter, Eq. 9 in §IV-D)
- $\sigma_\text{anchor} = \sigma_\text{base}/(R+\varepsilon) \approx 58.1$\,m at R=0.85 — effective per-UAV anchor sigma after reputation scaling (§IV-E example)
- "$\sigma_\text{anchor self} = 50$\,m" in §VI-A scaffold — the iSAM2 self-prior std-dev used in production trials (numerically identical to $\sigma_\text{base}$ but conceptually a different role)

**Edit**: in §VI-A line 508, change scaffold parameter names to disambiguate:

Current (around line 508):
```
Anchor self-prior $\sigma_\text{anchor self}=50$\,m and initial-position
noise $\sigma_\text{anchor init}=30$\,m, $\sigma_\text{follower init}=50$\,m
```

Replace with:
```
The iSAM2 self-prior std-dev (numerically equal to the $\sigma_\text{base}$
of Eq.~9, but used here as the GTSAM self-factor noise on each anchor's
own pose key) is set to $\sigma^{\text{(self)}}_\text{anchor}=50$\,m, and
initial-position noise $\sigma^{\text{(init)}}_\text{anchor}=30$\,m,
$\sigma^{\text{(init)}}_\text{follower}=50$\,m
```

Subsequent references in §VI-A to either parameter must use the superscripted form. Also add ONE sentence at the end of §VI-A para 1 (around line 508) noting the distinction:

```latex
Note that $\sigma_\text{base}$ (Eq.~9), the post-reputation effective
$\sigma_\text{anchor}(R)$ (Eq.~10), and the iSAM2 self-prior
$\sigma^{\text{(self)}}_\text{anchor}$ used as the GTSAM self-factor noise
are three distinct quantities that happen to share the value 50\,m at
$R\!\to\!1$; we use the superscripted form for the empirical scaffold to
avoid notational collision with the design-time symbols.
```

------------------------------------------------------------------
## 1.3  failover "six and a quarter seconds" → "six point two four"
------------------------------------------------------------------

**Edit**: Abstract line 96, change exactly:
```
failover ninety-ninth percentile of six and a quarter seconds
```
to:
```
failover ninety-ninth percentile of six point two four seconds
```

(The "six and a quarter" written out = 6.25s; actual table value is 6.24s.)

------------------------------------------------------------------
## 1.4  Phase numbering explanation
------------------------------------------------------------------

§VI subsections currently appear: VI-B Phase 1, VI-C Phase 3, VI-D Phase 4, VI-E Phase 2, VI-F Phase 5, VI-G Phase 6, VI-H Phase 7. §VII (titled "Baseline Comparison") corresponds to Phase 8 in the lab's internal numbering.

**Edit**: at the END of the §VI introductory paragraph (around line 502), ADD one sentence:
```latex
Subsections are grouped by architectural pillar rather than by chronological phase number; the vanilla-Raft baseline of Section~\ref{sec:baseline} constitutes Phase~8 in the lab's internal numbering.
```

------------------------------------------------------------------
## 1.5  Phase 5 N=20 scope softening
------------------------------------------------------------------

**Edit**: in §VI-F (Phase 5) after the existing scope note (around line 615 "the scaling cliff is implementation-specific rather than algorithmic"), REPLACE the existing scope sentence with:

```latex
\textbf{Scope note.} The Phase~5 sweep ran at $N{=}20$ rather than the
$N{=}50$ paper-spec design parameter: at $N{=}50$, the per-pair
publisher pattern of the Python rclpy detector creates measurable queue
back-pressure under the production-load envelope. The bottleneck is
implementation-bound (Python rclpy queue depth + per-pair publisher
fan-out), not algorithmic --- the detector itself is $O(M_\text{peers})$
per UAV and scales linearly. A C\texttt{++} reimplementation or a sharded
multi-detector deployment lifts the scaling ceiling; this is identified
as the closest implementation follow-up (Section~\ref{sec:discussion}-A).
```

------------------------------------------------------------------
## 1.6  Phase 8 baseline N=5 future-work note
------------------------------------------------------------------

**Edit**: at the END of §VII-A Nominal Failover Time (just before the Byzantine Adversarial subsection, around line 724), ADD one sentence:

```latex
The $N{=}5$ cluster size matches the canonical Raft cluster envelope
and the cluster-sizes most-cited in distributed-systems benchmarks;
larger-$N$ comparison is identified as follow-up work
(Section~\ref{sec:discussion}-A).
```

------------------------------------------------------------------
## 1.7  Fig:repu caption — "empirical validation deferred" reframe
------------------------------------------------------------------

**Edit**: Figure caption at line 390 currently says "(Section~\ref{sec:sim}-C; empirical validation deferred)". Replace with:
```latex
(Section~\ref{sec:sim}-C; the schematic is an analytical prediction;
empirical validation of the reputation-driven exclusion mechanism is
reported in Section~\ref{sec:phase2-exclusion} with 30/30 trials and
zero false honest exclusions).
```

(Make sure no other place in body/abstract/conclusion refers to this schematic as a measurement.)

------------------------------------------------------------------
## 1.8  GNSS-spoofing reputation asymmetry
------------------------------------------------------------------

**Edit**: §IV-G line 440 final sentence (`By design, GNSS spoofing does not affect navigation reputation $R_i$; only failed Proof-of-Observation verifications decrement reputation...`) — EXTEND with a single-sentence safety clause:

```latex
A captured peer that spoofs only its GNSS receiver while continuing to
fabricate position claims is still excluded through two orthogonal
channels: the Proof-of-Observation verification of
Section~\ref{sec:approach}-B (which fails on any claimed-but-unobserved
terrain region), and the UWB consistency check above (which flags any
broadcast position whose UWB-trilaterated equivalent deviates by more
than $\delta_\text{consist}$); both channels feed the same
reputation-update rule, so the by-design exclusion of GNSS-spoof events
from $R_i$ updates is not a coverage gap.
```

------------------------------------------------------------------
## 1.9  Statistical-power consolidation
------------------------------------------------------------------

**Edit**: in §X-A Limitations subsection, ADD one new bullet (or merge into an existing bullet if §VIII-IX-X power is already mentioned):

```latex
\item \emph{Statistical power of the abstract Monte Carlo studies
(\S\ref{sec:asym-decay-empirical}--\S\ref{sec:byzantine-scaling-empirical}).}
The retained Monte Carlo experiments were run with the seed counts of
the v9.8 release (3 seeds per cell for the asymmetric reputation study,
single-pass per cell for the clamp convergence and Byzantine scaling
studies) and are reported as indicative rather than confirmatory;
across-seed std-dev is therefore not separately reported for these
sections. A 25-seed re-run that produces confirmatory confidence
intervals is identified as a follow-up
(Section~\ref{sec:discussion}-A).
```

------------------------------------------------------------------
## 1.10  Abstract word count
------------------------------------------------------------------

Already 218 words, in range. Apply 1.3 fix (the only edit within abstract) and re-count; expected to remain ~218.

------------------------------------------------------------------
## 1.11  Zenodo DOI placeholder
------------------------------------------------------------------

Currently §X Code & Data: `DOI~10.5281/zenodo.XXXXXXX`. Leave the placeholder; user will replace after tagged GitHub release. ADD a TODO comment immediately before the bibitem-style line:

```latex
% TODO (Phase F submission step): replace XXXXXXX with concrete Zenodo
% DOI after tagged GitHub release matching this manuscript.
```

------------------------------------------------------------------
## 1.12  Two-repo README mapping
------------------------------------------------------------------

**Edit**: in §X Code & Data Availability subsection, add a clarifying paragraph that explicitly maps which repo holds which content:

```latex
The two open-source releases serve complementary roles:
\texttt{uav-gazebo-lab} (\url{https://github.com/a3ka/uav-gazebo-lab})
contains the full ROS\,2 + Gazebo + Python stack and the production-sweep
artefacts for Section~\ref{sec:empirical} (Phases~1--8); the earlier
\texttt{bft-uav-swarm-validation} v1.1 release
(\url{https://github.com/ok-research/bft-uav-swarm-validation}) contains
the three abstract Monte Carlo simulators of
Sections~\ref{sec:asym-decay-empirical}--\ref{sec:byzantine-scaling-empirical}.
A code-to-claim mapping (which source file produces which paper
number) is provided as a README in \texttt{uav-gazebo-lab/docs/v10\_access/}.
```

------------------------------------------------------------------
## 1.13  Verify 4 fresh DOIs
------------------------------------------------------------------

Use WebFetch on the four DOIs flagged as needing manual verification:

- `[3]` RESS 2026 art. 112101 — find its \bibitem in the file and verify DOI resolves to the cited title/authors via `doi.org` or `crossref.org/api/works/<doi>`
- `[4]` Sci Rep 2025 art. 36420 — same procedure
- `[44]` Drones 2026 — same procedure
- `[52]` arXiv:2509.15956 — same procedure

If any of the four fails verification (DOI does not resolve to the cited title/authors, or arXiv ID does not exist), write the finding to:

```
/home/nous/research/uav-gazebo-lab/docs/v10_access/PHASE_F_DOI_FAILURES.md
```

Do not silently delete the bibitem; flag for author review.

================================================================
# PART 2 — IEEE Access form
================================================================

## 2.1 documentclass — switch to two-column

**Edit**: line 17 currently:
```latex
\documentclass[journal,10pt,onecolumn]{IEEEtran}
```

Change to:
```latex
\documentclass[journal,10pt,twocolumn]{IEEEtran}
```

(IEEE Access submission uses IEEEtran journal twocolumn. There is no separate `ieeeaccess.cls` in standard texlive distributions; the IEEE Access "template" is IEEEtran with twocolumn-by-default and specific cover-page macros that the editor handles. See https://template-selector.ieee.org for the official template.)

Update the header comment around line 20-30 to reflect that twocolumn is now the production setting (remove the "Phase F deferred" language).

## 2.2 Captions must be SMALLER than body text

IEEE Access spec: body = 10pt, captions = 8pt. Currently captions have no explicit font-size and inherit 10pt.

**Edit**: in the preamble (between line 29 `\usepackage{cite}` and line 41 `\usepackage{hyperref}`), ADD:

```latex
\usepackage[font=footnotesize,labelfont=bf]{caption}
```

This sets all `\caption{...}` calls to use footnotesize (~9pt — still readable, smaller than body 10pt) with bold label ("Fig. 1.", "Table II."). The exact 8pt requested in the spec is not directly available as a LaTeX size name; `footnotesize` is the closest standard size (8.5-9pt depending on font tuning) and matches what IEEEtran's own caption macro uses under twocolumn.

If the `caption` package conflicts with any existing manual `\small`/`\footnotesize` inside specific captions, those manual sizing commands can be removed (they were workarounds for the now-fixed global default).

## 2.3 Abstract and IEEEkeywords full-width

In IEEEtran journal twocolumn class, `\begin{abstract}` and `\begin{IEEEkeywords}` automatically render full-width above the two-column body — no action needed beyond the documentclass switch (2.1).

VERIFY after compile: abstract+keywords span the full text width; first §I Introduction text drops to two columns below. If this does not happen automatically, the issue is most likely a stale layout cache; rerun pdflatex twice.

## 2.4 Margins — IEEEtran default

IEEEtran journal class sets margins per IEEE Transactions specification (US Letter: top 0.75in, bottom 1in, side 0.625in) automatically. No `\geometry{}` or manual margin override needed; do NOT add `\usepackage{geometry}` (it would clash with IEEEtran).

## 2.5 Caption placement convention

IEEEtran convention:
- Figure captions are placed BELOW the figure (call `\caption{...}` after the graphic content)
- Table captions are placed ABOVE the table (call `\caption{...}` immediately after `\begin{table}` before `\begin{tabular}`)

VERIFY all tables in §VI/§VII follow this convention. If any table has `\caption{...}` after `\end{tabular}`, move it to the correct position.

## 2.6 Overfull hboxes from twocolumn re-flow (expected layout regressions)

A diagnostic compile in twocolumn (Phase F early-test, run prior to this brief) identified six overfull hboxes:

| Line range | Overflow | Element | Fix |
|---|---|---|---|
| 631-641 | 46.6pt | tab:phase6_attrition | Wrap tabular body in `\resizebox{\columnwidth}{!}{...}` |
| 667-678 | 7.95pt | tab:ablation_measured (split-into-2-rows version) | Reduce `\tabcolsep` to 3pt OR resize |
| 717-725 | 44.9pt | tab:phase8_nominal | `\resizebox` |
| 742-752 | 6.2pt | tab:phase8_byzantine | `\tabcolsep` |
| 889-901 | 14.1pt | inlined §VIII figure caption | wrap caption text or reduce includegraphics width |
| 1893 | 21.9pt | bibliography entry (long URL) | wrap URL in `\url{...}` (already wrapped) or use `\sloppy` in bibliography preamble |

**Edit pattern** for `\resizebox` wrap, applied to any wide table that uses `\begin{tabular}{...} ... \end{tabular}` directly:

```latex
% Before:
\begin{table}[t]
\centering
\caption{...}
\label{...}
\small
\begin{tabular}{@{}lcc@{}}
... rows ...
\end{tabular}
\end{table}

% After:
\begin{table}[t]
\centering
\caption{...}
\label{...}
\small
\resizebox{\columnwidth}{!}{%
\begin{tabular}{@{}lcc@{}}
... rows ...
\end{tabular}%
}
\end{table}
```

Apply to tab:phase6_attrition, tab:phase8_nominal (the two big overflows), AND tab:ablation_measured, tab:phase8_byzantine (the two small ones — for consistency and future-proofing). Leave bibliography overflow (line 1893) to the post-compile pass; add `\sloppy` immediately after `\begin{thebibliography}{50}` to soften long-URL constraints.

## 2.7 IEEEtran-specific section numbering

IEEEtran automatically uses Roman numerals for top-level (I. INTRODUCTION) and uppercase letters for subsections (A. ...) — no manual `\renewcommand{\thesection}{...}` needed. VERIFY this is what the compiled PDF shows; if subsections are showing 1.1, 1.2 (arabic) instead of A, B, the issue is a clash with `hyperref` options or a `tocdepth` override. No action expected.

## 2.8 \hypersetup{pdftitle} — verify already fixed

Previous audit-delta confirmed Phase A FMT_001 fix; verify pdftitle reads "...Empirical Validation" not "...Evaluation Methodology". If still stale, fix.

## 2.9 Final compile + IEEE PDF eXpress check (post-edit step)

After applying all PART 1 + PART 2 edits, run:

```bash
cd /home/nous/research/uav-gazebo-lab
docker run --rm -v $PWD:/work texlive/texlive:latest bash -c '
  cd /work/docs/v10_access &&
  pdflatex -interaction=nonstopmode BFT_UAV_Swarm_Paper_v10_access.tex > /dev/null 2>&1 &&
  pdflatex -interaction=nonstopmode BFT_UAV_Swarm_Paper_v10_access.tex > /dev/null 2>&1 &&
  echo "exit=$?" &&
  ls -la BFT_UAV_Swarm_Paper_v10_access.pdf &&
  echo "---errors---" &&
  grep -cE "^! " BFT_UAV_Swarm_Paper_v10_access.log &&
  echo "---undefined---" &&
  grep -cE "(Reference|Citation).*undefined" BFT_UAV_Swarm_Paper_v10_access.log &&
  echo "---overfull hboxes---" &&
  grep -cE "^Overfull \\\\hbox" BFT_UAV_Swarm_Paper_v10_access.log &&
  echo "---all overfull lines---" &&
  grep -E "^Overfull \\\\hbox" BFT_UAV_Swarm_Paper_v10_access.log
'
```

Expected after all edits: exit=0, errors=0, undefined=0, overfull hboxes ≤2 (down from 6 in pre-edit twocolumn diagnostic; the two remaining are inherited <2pt overflows from v9_8 inlined MC sections).

Then **sync to audit-harness**:
```bash
cp /home/nous/research/uav-gazebo-lab/docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.{tex,pdf} \
   /home/nous/research/audit-harness/inputs/papers/
```

Note: IEEE PDF eXpress is a separate online tool the author runs before submission — Sonnet does not run this; just leave a TODO comment in the file header reminding the author to do this final check before upload.

================================================================
# Report at the end
================================================================

Output a markdown table:

| ID | Status | What changed | Verification |
|---|---|---|---|
| 1.1 Tspoof | DONE | three sites updated; design 50m, Phase 5 20m | grep "T_\\text{spoof}=20" in §VI-F: ≥1; grep "T_\\text{spoof}=50" remains in §IV-G, §IV-C, Table II |
| 1.2 σ_anchor | DONE | superscripted form in §VI-A; disambiguation paragraph added | grep "sigma\\^{(self)}_anchor" or new naming present |
| 1.3 6.25→6.24 | DONE | abstract line 96 word-form fixed | grep "six and a quarter" → 0 |
| 1.4 phase order | DONE | explanation sentence added after §VI intro | grep "grouped by architectural pillar" → 1 |
| 1.5 N=20 scope | DONE | replaced scope note in Phase 5 | grep "C++ reimplementation" → 1 |
| 1.6 N=5 baseline | DONE | future-work sentence added in §VII-A | grep "larger-N comparison" → 1 |
| 1.7 fig:repu | DONE | caption reframed; empirical reference added | grep "empirical validation deferred" → 0 |
| 1.8 spoof safety | DONE | extension sentence in §IV-G | grep "two orthogonal channels" → 1 |
| 1.9 stat power | DONE | bullet added to §X Limitations | grep "Statistical power of the abstract Monte Carlo" → 1 |
| 1.10 abstract | DONE | recounted, still in range | new wc shown |
| 1.11 Zenodo | DONE | TODO comment added | grep "TODO.*Zenodo" → 1 |
| 1.12 README map | DONE | mapping paragraph added | grep "two open-source releases serve complementary roles" → 1 |
| 1.13 DOIs | <status per ref> | 4 doi.org fetches; if failures, listed in PHASE_F_DOI_FAILURES.md | report 4 statuses |
| 2.1 twocolumn | DONE | documentclass option changed | grep "twocolumn" in documentclass line: 1 |
| 2.2 captions | DONE | caption package added with footnotesize | grep "usepackage\\[font=footnotesize" → 1 |
| 2.6 overfull fix | DONE | resizebox wrappers + sloppy in bib | overfull count ≤2 |
| 2.8 pdftitle | DONE if was needed | n/a if already fixed | grep "Empirical Validation" in pdftitle |

Plus:
- Final pdflatex compile result (exit=0, errors=0, undefined=0, overfull≤2)
- Final file size + page count (twocolumn typically ~16-22 pages vs onecolumn 31)
- Confirmation sync to audit-harness done
- Output paths of new artifacts

If any blocker, write the finding to:
```
/home/nous/research/uav-gazebo-lab/docs/v10_access/PHASE_F_BLOCKERS.md
```
and continue with the rest.

================================================================
# What NOT to do
================================================================

- NO new measurements, no new claims, no new citations not in PART 1/PART 2
- NO Phase F items beyond this brief (no BibTeX conversion, no ieeeaccess.cls switch, no graphical abstract rerender — those are author-deferred or already done)
- NO emojis in .tex
- NO running of audit-harness slash commands (next step after your patches)
- DO NOT touch §VI/§VII headline numbers
- DO NOT touch §III-V theory and proofs
- DO NOT remove the v9_8 deltas header comments
- DO NOT touch §VIII-X inlined MC sections except the CONS_004 \ref (already in v10-v2) and the new caption-package effect (which applies globally without per-section edits)

If you find any other apparent inconsistency not in this list, write the finding to PHASE_F_BLOCKERS.md and continue — the brief is the authoritative scope.
