# PF-1 — SwarmRaft reference availability

**Completed:** 2026-05-21
**Status:** ✅ Reference impl exists, but with caveats

## Paper

- **Title:** SwarmRaft: Leveraging Consensus for Robust Drone Swarm Coordination in GNSS-Degraded Environments
- **Authors:** Kapel Dev, Yash Madhwal, Sofia Shevelo, Pavel Osinenko, Yury Yanovich
- **Affiliation:** Skoltech (Skolkovo Institute of Science and Technology)
- **arXiv:** [2508.00622](https://arxiv.org/abs/2508.00622), v1 July 2025, v2 Aug 2025
- **Target venue:** IEEE Internet of Things Journal (submitted)

## Approach in brief

Raft-style consensus adapted to UAV swarms for GNSS-denied / spoofed
self-localization. INS dead-reckoning + peer state exchange; Raft-
elected leader runs a voting round where honest replicas cross-check
candidates against inter-drone ranging and motion priors; outliers
rejected, affected positions reconstructed from quorum consensus.
Explicit trade: lower compute than full BFT, weaker adversary model
(crash-tolerant, not Byzantine).

## Reference implementations

Two repos, both authored by paper co-authors:

| | yashmadhwal/SwarmRaft | kapeldev/SwarmRaft |
|---|---|---|
| URL | https://github.com/yashmadhwal/SwarmRaft | https://github.com/kapeldev/SwarmRaft |
| Cited from | arXiv v1 | arXiv v2 (canonical) |
| Last commit | 2025-07-29 | 2025-09-21 |
| Size | 13 KB, 8 files | 51 KB, 10 files |
| Language | Python (Monte Carlo sim) | Python (Monte Carlo sim) |
| License | None (no LICENSE file) | None (no LICENSE file) |
| ROS2 / Gazebo | none | none |

## Implications for Phase 8

**Previous assumption:** if no open-source ref, +2 wk reimplementation
from paper.

**Actual:** ref exists but is **pure Python Monte Carlo simulator**,
not a Gazebo/ROS2 baseline. Phase 8 still needs ROS2 wrapping of the
consensus + voting logic — estimated **3-7 days**, not +2 wk.

**Revised Phase 8 budget:**
- Time: ~3-7 days ROS2 wrapping (down from +2 wk reimplementation)
- GPU cost: unchanged (~$15-50 for re-running Phase 3/6 scenarios with
  SwarmRaft node in place)
- Risk: unchanged

## Caveats requiring action

1. **No license declared** on either repo. Legally "all rights
   reserved." Before redistributing or vendoring the code into our
   repo we must contact authors:
   - yyanovich@skoltech.ru (corresponding author)
   - Or co-authors at Skoltech

   For fair-use academic comparison (running their code to compare
   against ours, reporting numbers in our paper), this is generally
   tolerated. For inclusion as a submodule or fork — explicit license
   grant needed.

2. **Two divergent code drops.** `kapeldev/SwarmRaft` (v2-aligned) is
   the more canonical reference per the latest paper version. Default
   to that one for Phase 8 unless integration issues push us to the
   modular `yashmadhwal/` version.

3. **Both repos abandoned post-submission** (single push for kapeldev;
   last activity July 2025 for yashmadhwal). Do not expect upstream
   support. Fork once and own it.

4. **Algorithmic parity at simulator level is feasible**; ROS2 wrapping
   is the additional work. The Monte Carlo simulator reproduces the
   paper's plots — we can verify our ROS2 port is faithful by running
   our port on the same scenarios and matching their published
   numbers.

## Decision

Phase 8 stays in plan with reduced time estimate. Phase 8 spec in
`VALIDATION_PLAN.md` to be updated accordingly. License contact to
Skoltech is a Phase 8 pre-step (not blocking Phase 0-7).

## Source

Research performed by general-purpose subagent, 2026-05-21. Findings
cross-checked against arXiv abstract + both GitHub repo READMEs.
