# uav-gazebo-lab

Empirical validation testbed for the BFT-Resilient UAV Swarm Navigation
paper (v9_8 on arXiv, DPMA Aktenzeichen 10 2026 002 312.2).

**Status:** Bootstrap. Phase 0 (infrastructure) pending.

## What this is

The v9_8 preprint disclosed all simulation as abstract Monte Carlo and
explicitly deferred physics-grounded validation to Track 2 (this lab).
This project carries that deferred work — empirically validating every
claim in the paper using ROS2 Jazzy + Gazebo Harmonic + PX4 SITL.

## What this is NOT

- Not a discovery lab. Hypotheses are pre-specified by the paper.
- Not a Sakana fork. No LLMs in the experimental loop.
- Not an audit harness. Audit happens in the sister project.

## Stack

- Ubuntu 24.04 + ROS2 Jazzy + Gazebo Sim Harmonic + PX4 main + GTSAM 4.2+

See `CLAUDE.md` for the rationale and lock list.

## Where to start

`docs/VALIDATION_PLAN.md` — the locked 9-phase validation plan. Read
this before any work.

## Sister projects

- `../audit-harness/` — Track 1, paper audit harness (audits anything
  produced here)
- `../sakana-lab/` — Track 2, LLM-driven research discovery
  (independent — does not feed this project)
