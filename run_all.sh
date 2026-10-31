#!/usr/bin/env bash
# Run all TPG-Reg experiments; results are written to ./results
#   ./run_all.sh            all experiments (about 1.5 hours on 2 cores)
#   ./run_all.sh --fast     without the SMT studies and the PDP conformance check
#   ./run_all.sh --no-smt   everything except the SMT studies (scalability, GPMS)
#   ./run_all.sh --smt-only only the SMT studies
# The external XPA policies are fetched first (experiments/fetch_external_policies.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
R="$HERE/results"; L="$R/logs"
mkdir -p "$R" "$L"
cd "$HERE/experiments"
export PYTHONHASHSEED=0
MODE=${1:-}
step () { echo "[$(date +%H:%M:%S)] $1"; }
[ -d "$HERE/external/xpa" ] || ./fetch_external_policies.sh

if [ "$MODE" != "--smt-only" ]; then
step "single-edit evolutions";            python3 exp_single_edit_evolution.py "$R/single_edit_evolution" > "$L/exp_single_edit_evolution.log" 2>&1
step "summary of single-edit results";    python3 summarize_single_edit.py "$R/single_edit_evolution"     > "$R/single_edit_evolution/summary.txt" 2>&1
step "significance tests";                python3 significance_tests.py "$R/single_edit_evolution"        > "$R/single_edit_evolution/significance_tests.txt" 2>&1
step "detection-rate chart";              python3 plot_detection_rates.py "$R/single_edit_evolution"      > "$L/plot_detection_rates.log" 2>&1
step "external policies: single-edit";    python3 exp_single_edit_evolution.py "$R/external_single_edit" external > "$L/exp_external_single_edit.log" 2>&1
step "external policies: summary";        python3 summarize_single_edit.py "$R/external_single_edit"      > "$R/external_single_edit/summary.txt" 2>&1
step "external policies: significance";   python3 significance_tests.py "$R/external_single_edit"         > "$R/external_single_edit/significance_tests.txt" 2>&1
step "two-edit commits (intent oracle)";  python3 exp_two_edit_commits.py "$R/two_edit_commits" 40       > "$L/exp_two_edit_commits.log" 2>&1
step "external two-edit commits";         python3 exp_two_edit_commits.py "$R/external_two_edit_commits" 40 external > "$L/exp_external_two_edit_commits.log" 2>&1
step "SMT backend equivalence";           python3 check_smt_backend.py "$R/validation"                  > "$L/check_smt_backend.log" 2>&1
step "financial example";                 mkdir -p "$R/finance_example"; python3 demo_finance_example.py > "$R/finance_example/output.txt" 2>&1
step "XACML export";                      python3 export_xacml_policies.py "$R/xacml_policies"          > "$L/export_xacml_policies.log" 2>&1
step "regression suites export";          python3 export_regression_suites.py "$R/regression_suites"    > "$L/export_regression_suites.log" 2>&1
if [ "$MODE" != "--fast" ]; then
  step "PDP conformance (ndg-xacml)"
  PYTHONPATH="$HERE/third_party/ndg_xacml_py3:${PYTHONPATH:-}" python3 check_pdp_conformance.py "$R/validation" > "$L/check_pdp_conformance.log" 2>&1
fi
fi
if [ "$MODE" != "--fast" ] && [ "$MODE" != "--no-smt" ]; then
  step "scalability n=50..400 (full pipeline)"; python3 exp_scalability.py "$R/scalability" 50,100,200,400 30   > "$L/exp_scalability_full.log" 2>&1
  step "scalability n=800 (analysis only)";     python3 exp_scalability.py "$R/scalability" 800 30 analysis    > "$L/exp_scalability_n800.log" 2>&1
  step "external GPMS (Z3 backend)";            python3 exp_external_smt.py "$R/external" 100                  > "$L/exp_external_smt.log" 2>&1
fi
step "review counterexamples";        python3 ../tests/test_review_examples.py                  > "$L/test_review_examples.log" 2>&1
step "report";                            python3 build_report.py "$R"                                 > "$L/build_report.log" 2>&1
step "done: $R/REPORT.md"
