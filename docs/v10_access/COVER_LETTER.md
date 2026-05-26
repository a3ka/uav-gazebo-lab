# Cover Letter — IEEE Access Submission

**To:** Editor-in-Chief, IEEE Access
**Subject:** Submission of original manuscript "Byzantine-Fault-Tolerant Hierarchical Navigation for GNSS-Denied UAV Swarms: Architecture, Theoretical Analysis, and Empirical Validation"

---

Dear Prof. Saif,

I am pleased to submit the attached manuscript for consideration by IEEE Access.

## Scope and contribution

The work presents a Byzantine-fault-tolerant (BFT) hierarchical navigation architecture for unmanned aerial vehicle (UAV) swarms operating in GNSS-denied environments, accompanied by a complete seven-phase empirical validation campaign and a vanilla-Raft baseline comparison that exposes the BFT-versus-crash-fault-tolerance (CFT) capability gap.

The architecture is the first published design, to our knowledge based on a systematic review of approximately ninety publications spanning 2020-2026, that integrates all six core capabilities required for adversarial-peer-resilient GNSS-denied swarm navigation within a continuous-state flight-grade factor-graph estimator: BFT consensus, dynamic anchor/follower hierarchy, reputation-weighted multi-hop position relay, automatic failover, UWB-based GNSS-spoofing detection, and capacity-aware load balancing under progressive attrition. The central primitive is a Visual Proof of Observation: cryptographically signed hashes of terrain feature descriptors verified by physical revisit, integrated into iSAM2 via asymmetric reputation-weighted noise covariances.

## Why IEEE Access

IEEE Access is the right venue for this contribution because:

1. **Technical soundness over novelty as the review axis.** The integrated architecture is the contribution rather than any one mechanism in isolation. Several constituent primitives (asymmetric reputation, Raft-style leader election, terrain-relative navigation) are documented prior art; the contribution is in their combined design and the empirical demonstration that the combination yields the headline guarantees (zero false honest exclusions, p99 < 6.3 s failover, 98.3 % spoof detection at p99 < 0.6 s, zero over-capacity intervals under attrition with admission control). IEEE Access's binary accept/reject model on technical soundness, rather than perceived breakthrough novelty, fits this profile.

2. **Full empirical validation is included.** All six pillars are validated empirically; no core claim is deferred to future work. The empirical campaign comprises 250 CEP-vs-hops trials, 1 200 failover-timing measurements across four scenarios, thirty Byzantine-exclusion trials across six (M, f) configurations, sixty GNSS-spoofing-detection trials, fifteen progressive-attrition trials with and without admission control, four single-pillar ablations, and a vanilla-Raft baseline plus single-Byzantine adversarial test. All workspace artefacts and reproducibility pins are released open-source.

3. **Open-source reproducibility lab.** The entire validation infrastructure (ROS 2 nodes, sweep configurations, analysis scripts, Docker recipes, raw production-sweep CSVs) is released under MIT licence at `github.com/a3ka/uav-gazebo-lab` with a tagged release archived on Zenodo (DOI assigned upon submission).

## Empirical headline results

- Proof-of-Observation: AUC = 0.9996 at the paper-specification verification threshold T_verify = 0.30 (FAR = 0.4 %, FRR = 3.0 %); an alternative zero-false-acceptance operating point at T_verify = 0.32 yields FAR = 0 % and FRR = 4.6 %.
- Reputation-driven Byzantine exclusion: 30 / 30 trials with zero false exclusions of honest peers (Proposition 1 validated empirically).
- Circular Error Probable at three relay hops: 23 m, more than four times inside the 100-m NATO-grade ISR threshold; the empirical per-hop multiplier delta = 0.088 is within and tighter than the conservative paper-v9 assumption delta = 0.15.
- Anchor failover: p99 = 6.24 s across 1 200 follower-switch measurements (silence-triggered), p99 = 1.94 s for reputation-triggered failover.
- GNSS-spoofing detection: 98.3 % per-victim recall with zero false positives at p99 detection time 0.60 s.
- Capacity-aware admission control: over-capacity interval = 0 s across 15 attrition trials, restoring the capacity invariant strictly at the cost of a single Pareto-honest mission failure (14 / 15 mission survival).
- Vanilla-Raft baseline: failover-time gap of approximately 1 s nominal (5.087 s for Raft vs 6.080 s for our protocol), while under a single-Byzantine leader-claimer attack Raft is compromised indefinitely (19/19 heartbeats from the Byzantine attacker, zero from any honest peer) and our protocol detects and excludes the analogous Byzantine anchor within the Phase 5 detection envelope (p99 < 0.6 s).

## Declarations

- **Funding:** none. All compute was self-funded (approximately one US dollar of vast.ai RTX rental for the GPU-bound Proof-of-Observation pipeline; remaining phases ran on the author's local workstation at zero marginal cost).
- **Competing interests:** the methods of Section IV-B through IV-G are the subject of pending patent applications filed with the German Patent and Trademark Office (DPMA) in April 2026, Aktenzeichen 10 2026 001 712.2 and a related application. This is disclosed in the title footnote and Acknowledgements.
- **AI disclosure:** all software released under the `uav-gazebo-lab` repository (ROS 2 nodes, sweep configurations, analysis scripts, Docker recipes, abstract Monte Carlo simulators) was developed with LLM-assisted code generation (Anthropic Claude). All numerical results were obtained by deterministic re-execution of the released code; reproducibility is verified by independent re-runs of every production sweep and recorded in each `workspaces/<sweep>/manifest.json` alongside the analysis output. The manuscript text was drafted by the author; LLM assistance was used to triage early framing options, summarise candidate related-work entries from a curated reading list, and check internal consistency across sections. This is disclosed in the Acknowledgements.
- **Submission compliance:** the manuscript was prepared with the IEEE Access submission template; a graphical abstract is supplied as a separate supporting document.

## Suggested reviewer competences

The work spans three subfields and a constructive review would benefit from at least two of: (1) Byzantine-fault-tolerant consensus protocols and reputation systems; (2) GNSS-denied cooperative localisation, factor-graph state estimation (iSAM2 / GTSAM), and ultra-wideband ranging; (3) hierarchical UAV swarm protocols and resilience evaluation.

## Reproducibility

The complete validation lab is released at `https://github.com/a3ka/uav-gazebo-lab` under the MIT licence. A tagged release matching the submitted manuscript is archived on Zenodo with the DOI cited in the Code and Data Availability subsection. Per-phase reproducibility pins (Docker image digest, git commit at sweep start, manifest of sweep parameters) are documented in `docs/results/phase-{1..8}.md` files of the repository.

I confirm that the manuscript has not been published in or submitted to any other journal, and that all authors (single author) have approved this submission.

Thank you for your consideration.

Yours sincerely,

**Oleksandr Kalynovskyi**
Independent Researcher
Email: kalinovsky.research@proton.me
ORCID: 0009-0009-1437-3252
