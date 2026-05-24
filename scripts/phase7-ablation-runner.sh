#!/usr/bin/env bash
# Phase 7 task 7.2/7.3 — single-shot ablation campaign.
#
# Runs 4 ablation variants by re-spawning the existing Phase 3/4/5/6
# sweep scripts with the "disabled-pillar" parameter values. Output
# each goes to workspaces/phase7-<ABL>/.
#
# Trial count per ablation kept low (5) — sufficient to see the
# >=30% degradation signal vs the established baseline; not a full
# statistical campaign. The baseline production sweeps from
# workspaces/phase{3,4,5,6}-prod/ are what we compare against.
#
# Env vars (optional):
#   ABL_TRIALS  (default 5)
#   ABL_JOBS    (default 2)
#   RUN_ONLY    (default "1 2 3 4")  whitespace-separated list, e.g.
#                 "1 3" to skip ABL2 + ABL4
#
# Output:
#   workspaces/phase7-abl1-nospoof/{results.csv, manifest.json, analysis.json}
#   workspaces/phase7-abl2-nofailover/...
#   workspaces/phase7-abl3-noloadbal/...
#   workspaces/phase7-abl4-notrn/...

set -o pipefail

ABL_TRIALS="${ABL_TRIALS:-5}"
ABL_JOBS="${ABL_JOBS:-2}"
RUN_ONLY="${RUN_ONLY:-1 2 3 4}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
cd /workspace/uav-gazebo-lab

run_in() { for x in $RUN_ONLY; do [[ "$x" == "$1" ]] && return 0; done; return 1; }

echo "###################################################"
echo "### Phase 7 ablation campaign"
echo "### ABL_TRIALS=$ABL_TRIALS  ABL_JOBS=$ABL_JOBS  RUN_ONLY=\"$RUN_ONLY\""
echo "###################################################"
date -u

# ABL1 — No spoof detection: T_spoof=1e9 makes every residual look
# tiny, so the detector never accumulates suspicious_pairs.
if run_in 1; then
  echo ""
  echo "=== ABL1: no spoof detection (T_spoof=1e9) ==="
  rm -rf workspaces/phase7-abl1-nospoof
  python3 scripts/phase5-batch-sweep.py \
      --trials "$ABL_TRIALS" \
      --n-uavs 20 --n-spoofed 2 --region-m 200.0 \
      --t-steady-s 4 --t-observe-s 8 --window-s 3 --m-suspect 3 \
      --spoof-offset-m 120.0 \
      --t-spoof-m 1000000000.0 \
      --t-pass-budget-s 5.0 \
      --run-id phase7-abl1-nospoof --jobs "$ABL_JOBS"
  python3 scripts/phase5-analyze.py \
      --csv workspaces/phase7-abl1-nospoof/results.csv \
      --out workspaces/phase7-abl1-nospoof/analysis.json
fi

# ABL2 — No failover: t_timeout=1e4 ensures the watchdog never fires.
# Followers should remain "attached" to dead anchors -> n_pass=0.
if run_in 2; then
  echo ""
  echo "=== ABL2: no failover (t_timeout=10000) ==="
  rm -rf workspaces/phase7-abl2-nofailover
  # ABL2 scope-trim: only S1 (sudden death; S2/S3 are silence variants
  # with identical no-failover semantics) + reduced trial count. The
  # disabled-pillar signal is binary (0 switching events vs 100% in
  # baseline) so n=3 is plenty.
  # t-timeout-s=30 is bigger than t-mission (~25s) so the watchdog
  # never fires within the trial -- same "no failover" semantics as
  # 10000, but bounds the collector budget (which scales with timeout)
  # to a sane wall.
  python3 scripts/phase4-batch-sweep.py \
      --scenarios S1 \
      --trials-per-scenario 3 \
      --n-anchors 3 --n-followers 3 --victim-anchor-id 0 \
      --t-steady-s 5 --t-pass-budget-s 5 \
      --t-timeout-s 30.0 \
      --run-id phase7-abl2-nofailover --jobs 1
  python3 scripts/phase4-analyze.py \
      --csv workspaces/phase7-abl2-nofailover/results.csv \
      --out workspaces/phase7-abl2-nofailover/analysis.json
fi

# ABL3 — No load-balancing: alpha_cap=0 in follower selection. The
# bunching should be at least as bad as baseline (and arguably worse
# because no spread incentive).
if run_in 3; then
  echo ""
  echo "=== ABL3: no load balancing (alpha_cap=0) ==="
  rm -rf workspaces/phase7-abl3-noloadbal
  python3 scripts/phase6-tier-b-sweep.py \
      --trials "$ABL_TRIALS" \
      --n-uavs 50 --m-anchors 10 --region-m 300 \
      --n-victims 3 --t-first-event-s 30 --t-step-s 30 \
      --t-warmup-s 8 --t-mission-s 120 \
      --alpha-cap 0.0 \
      --run-id phase7-abl3-noloadbal --jobs "$ABL_JOBS"
fi

# ABL4 — No TRN: sigma_trn=1e9 turns the TRN prior into a no-op
# (anchor self-prior dominates). Followers at k=3 lose all absolute-
# fix information; CEP should grow significantly.
if run_in 4; then
  echo ""
  echo "=== ABL4: no TRN (sigma_trn=1e9) ==="
  rm -rf workspaces/phase7-abl4-notrn
  python3 scripts/phase3-batch-sweep.py \
      --k-list 3 \
      --trials-per-k "$ABL_TRIALS" \
      --warmup-s 20 --trial-s 30 \
      --sigma-uwb-m 0.1 --sigma-trn-m 1000000000.0 --trn-period-s 10.0 \
      --run-id phase7-abl4-notrn --jobs "$ABL_JOBS"
  python3 scripts/phase3-analyze.py \
      --csv workspaces/phase7-abl4-notrn/sweep.csv \
      --out workspaces/phase7-abl4-notrn/analysis.json
fi

echo ""
echo "###################################################"
echo "### Phase 7 ablation campaign DONE"
echo "###################################################"
date -u

# Quick summary
echo ""
for ABL in workspaces/phase7-abl*/; do
    [[ -f "$ABL/analysis.json" ]] && echo "$ABL:" && \
        python3 -c "
import json
a=json.load(open('$ABL/analysis.json'))
if 'per_scenario' in a:
    for s in a['per_scenario']:
        print(f'  {s[\"scenario\"]}: pass_rate={s[\"pass_rate\"]} med={s[\"switch_time_median\"]}')
elif 'summary' in a:
    s=a['summary']
    if 'detection_rate_per_victim' in s:
        print(f'  detection_rate={s[\"detection_rate_per_victim\"]} fp_total={s[\"total_fp\"]} median_t={s[\"t_detect_median_s\"]}')
    else:
        print(f'  trial_pass={s.get(\"trial_pass_rate\")}')
elif 'per_k' in a:
    for s in a['per_k']:
        print(f'  k={s[\"k\"]} cep50_median={s[\"cep50_median\"]} std={s[\"cep50_std\"]}')
"
done
