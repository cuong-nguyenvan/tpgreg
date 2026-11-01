# TPG-Reg

**Change-impact-driven regression testing for evolving XACML policies, based on Typed Policy Graphs.**

This repository contains the prototype and all experiments of the paper
*From Flow Graphs to Typed Policy Graphs: Change-Impact-Driven Regression Testing for Evolving XACML Policies*.
Every number reported in the paper can be regenerated with one script (`run_all.sh`), and the pre-computed
results are included in [`results/`](results/).

## How it works

Given two versions of an XACML policy set and the declared scope of the change, TPG-Reg

1. **builds a Typed Policy Graph (TPG)** for each version: typed nodes (policy set, policy, rule, target,
   condition, combining algorithm, variable definition, attribute), syntactic edges (`contains`, `scopes`, `reads`,
   `combinedBy`) and derived edges between rules that can interact (`precedes` under first-applicable,
   `overrides` under deny-/permit-overrides) or share a variable definition (`refers`);
2. **computes the Behavioral Impact Set (BIS)**: the two graphs are matched by XACML identifiers, the changed
   elements are mapped to seed rules, and a level-monotone closure over the interaction edges adds every rule
   whose decisions the edit can change;
3. **generates a regression suite inside the BIS** from an exact decisiveness predicate `Dec_P(r, q)`:
   decisive witnesses (W1), isolation witnesses (W1u), interaction witnesses (W2) and difference witnesses (W3),
   optionally with distinguishing requests (D). Candidate requests are reduced by greedy set cover;
4. **runs the suite on both versions** and classifies each changed decision as *intended* or *regression*
   against the declared edit scope.

Three variants are evaluated:

| Variant | Obligations |
|---|---|
| `TPG-Reg` | W1, W1u, W2, W3 for the rules in the BIS |
| `TPG-Reg+D` | as `TPG-Reg`, plus one distinguishing request D per BIS rule |
| `TPG-Reg(D)` | distinguishing requests D for the BIS rules only |

Two backends compute the obligations: exhaustive enumeration over finite attribute domains (vectorised with
NumPy), and Z3 for request spaces that cannot be enumerated.

## Main results

Behaviour-changing single-edit evolutions (synthetic), seeds 1–5.
*Authored*: HACS, FMS and SIS, written for this study (363 evolutions).
*XPA*: iTrust, Pluto, Conference and Fedora from the [XPA repository](https://github.com/dianxiangxu/XPA),
which are independent of this study (998 evolutions).

| Method | EDR authored | ARE authored | Obl. authored | EDR XPA | ARE XPA | Obl. XPA |
|---|---:|---:|---:|---:|---:|---:|
| Flow-graph suite, GA-minimised (Retest-all) | 51.7 % | 36.9 % | – | 46.4 % | 38.9 % | – |
| Syntactic difference (AST-Up) | 58.9 % | 31.5 % | – | 46.5 % | 34.9 % | – |
| Direct semantic difference, 1 request (Diff-1) | 100 % | 56.7 % | 1 | 100 % | 95.2 % | 1 |
| Distinguishing query for every rule (Diff-all) | 100 % | 100 % | 25.3 | 100 % | 100 % | 34.0 |
| **TPG-Reg** (W1–W3) | 92.9 % | 67.5 % | 60.8 | 99.9 % | 99.7 % | 12.8 |
| **TPG-Reg+D** | 100 % | 100 % | 70.9 | 100 % | 100 % | 16.0 |
| **TPG-Reg(D)** | 100 % | 100 % | 10.1 | 100 % | 100 % | 3.2 |

- **EDR** (evolution detection rate): share of behaviour-changing evolutions for which the two versions disagree on at
  least one request of the suite.
- **ARE** (affected-rule exposure): share of affected rules that are decisive on some request of the suite on which
  the versions disagree.
- **Obl.**: obligations posed per evolution, i.e. solver calls with the SMT backend.

**Key findings**

- **The BIS contained every affected rule on all subjects** (recall 100 %). This was also confirmed by exact Z3
  soundness queries: 11,259 on synthetic policies with up to 400 rules and 8,435 on GPMS (97 rules, about
  2·10¹⁷ requests). All of them were UNSAT.
- **A direct semantic-difference query also detects every change.** The 100 % EDR of `TPG-Reg+D` is therefore not
  credited to the graph. What the BIS contributes is a reduction in the number of per-rule distinguishing queries
  needed for full exposure: 10.1 instead of 25.3 on the authored policies, and 3.2 instead of 34.0 on XPA.
- **The scope-based oracle** was evaluated on 280 constructed commits that contain an undeclared edit and 280 clean
  commits. When every request is checked, it flags 278 of the 280 commits with an undeclared edit and none of the
  clean ones.

The complete tables, including significance tests, edge ablations, per-operator results, scalability and GPMS, are
in [`results/REPORT.md`](results/REPORT.md).

## Installation

```bash
git clone https://github.com/cuong-nguyenvan/tpgreg.git
cd tpgreg
python3 -m pip install -r requirements.txt
```

- **Requirements:** Python ≥ 3.10, NumPy, SciPy, Matplotlib and z3-solver.
- **Tested versions:** the results in `results/` were regenerated identically with Python 3.13, NumPy 2.5.3,
  SciPy 1.18.1, Matplotlib 3.11.2 and z3-solver 5.3.3.
- **No installation step:** the scripts add the repository root to `sys.path`.

## Quick start

The example changes the combining algorithm of a small financial policy from deny-overrides to first-applicable:

```python
import numpy as np
from tpgreg.policy_model import Grid
from tpgreg.benchmarks import fin, FIN_DOM
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise

G = Grid(FIN_DOM)                                        # all requests of the finite domain
g1, g2 = TPG(fin("DO", 5), G), TPG(fin("FA", 5), G)      # version 1 and version 2
changed, bis, container_seeds, followed = diff_bis(g1, g2)
use = ("precedes", "overrides", "scopes", "refers")
obligations = tpg_obligations(g1, g2, changed, bis, container_seeds, followed, use)
suite = minimise(obligations, np.random.default_rng(1))
print(sorted(bis))                                       # ['M.R1', 'M.R2']
print([G.request(q) for q in suite])                     # 3 requests
```

`experiments/demo_finance_example.py` runs the same example end to end, including the classification of changed
decisions.

## Reproducing the experiments

```bash
./run_all.sh            # all experiments (about 1.5 h on 2 cores)
./run_all.sh --fast     # without the SMT studies and the ndg-xacml cross-check (about 10 min on 2 cores)
./run_all.sh --no-smt   # everything except the SMT studies
./run_all.sh --smt-only # only the SMT studies (scalability, GPMS)
```

- **Output location.** Results are written to `results/`, which overwrites the pre-computed copy, and the logs go to
  `results/logs/`. The last step builds `results/REPORT.md` from the raw JSON files.
- **External policies.** The XPA policies are not redistributed. On the first run,
  `experiments/fetch_external_policies.sh` clones XPA at the fixed commit `89c000495d81a1a82ca8de2ab0fc73fecfc4e440`
  and copies the five policies (iTrust, Pluto, Conference, Fedora, GPMS) into `external/xpa/`. This step needs
  network access to GitHub. The step is skipped when `external/xpa/` already exists.
- **Determinism.** All seeds are fixed and `run_all.sh` sets `PYTHONHASHSEED=0`. Apart from timings, a rerun
  reproduces every JSON and CSV file in `results/` exactly. Timings depend on the machine; the reference timings were
  measured on a 2-core machine.

### Where each result comes from

| Result | Script | Output |
|---|---|---|
| Subjects and TPG statistics | `exp_single_edit_evolution.py` | `tables/benchmark_policy_sets.csv`, `tables/external_policy_sets.csv` |
| Impact analysis (BIS recall/precision, edge ablation) | `exp_single_edit_evolution.py`, `summarize_single_edit.py` | `tables/impact_analysis_and_edge_ablation.csv`, `tables/impact_set_recall_by_policy_set.csv` |
| Regression detection (EDR, ARE, suite size) | same | `tables/regression_detection_by_method.csv`, `tables/external_regression_detection_by_method.csv`, `tables/detection_rate_by_edit_operator.csv` |
| Obligations and generation cost | same | `tables/authored_obligations.csv`, `tables/external_obligations.csv` |
| Significance tests (bootstrap CI, Â12, Wilcoxon, McNemar) | `significance_tests.py` | `tables/significance_tests.csv` |
| Oracle correctness of path-based vs. decisive witnesses | `exp_single_edit_evolution.py` | `tables/oracle_correctness.csv` |
| Two-edit commits and scope-based oracle | `exp_two_edit_commits.py` | `tables/two_edit_commits.csv`, `tables/external_two_edit_commits.csv` |
| Z3 backend vs. enumeration | `check_smt_backend.py` | `tables/smt_backend_equivalence.csv` |
| PDP cross-check with ndg-xacml (552,556 requests) | `check_pdp_conformance.py` | `tables/pdp_conformance_ndg_xacml.csv` |
| Scalability (n = 50–800 rules, Z3) | `exp_scalability.py` | `tables/scalability_smt_backend*.csv` |
| GPMS (non-enumerable request space, Z3) | `exp_external_smt.py` | `tables/external_gpms_smt*.csv` |

All `tables/` paths are relative to `results/`. The raw per-evolution data are in
`results/<experiment>/per_evolution_*.json`, and the exported XACML policies and regression suites are in
`results/xacml_policies/` and `results/regression_suites/`.

### Tests

```bash
python3 tests/test_review_examples.py
```

The tests check corner cases of the decisive predicate against both enumeration and Z3:

- first-applicable with two rules of the same effect;
- a rule swap that leaves the decision unchanged;
- nested permit-overrides;
- soundness of the BIS on a two-level policy set.

Each check prints `PASS` or `FAIL`.

## Repository layout

```
tpgreg/
  policy_model.py        policy model and vectorised PDP (DO, PO, FA), exact decisiveness predicate
  typed_policy_graph.py  TPG construction and derived interaction edges
  impact_analysis.py     identifier-anchored diff and level-monotone BIS closure
  test_generation.py     witnesses W1, W1u, W2, W3 and greedy set-cover minimisation
  smt_backend.py         Z3 encoding of decisions, decisiveness and witnesses
  baselines.py           AST-Up and flow-graph suites (greedy and GA minimisation)
  mutation.py            single-edit operators (CCF, CRE, RDL, RRO, RAI, PTC, CAC, VDC, PRO)
  benchmarks.py          authored policy sets HACS, FMS, SIS and the FIN example
  xacml_import.py        XACML 3.0 import (used for the XPA policies)
  xacml_export.py        XACML 3.0 export
  external.py            loading of the external XPA policies
experiments/             one script per experiment, plus fetch_external_policies.sh
results/                 pre-computed results, logs, CSV tables and REPORT.md
tests/                   corner cases of the decisive predicate
third_party/             ndg-xacml 0.5.1 ported to Python 3 (BSD licence), used as an independent PDP
run_all.sh               runs all experiments and builds the report
```

## Scope and limitations

- **XACML fragment.** The prototype handles a root policy set of policies of rules; targets are conjunctions of
  predicates, and conditions are Boolean expressions over predicates and variable definitions. The supported combining
  algorithms are deny-overrides, permit-overrides and first-applicable. Indeterminate, obligations and advice are not
  modelled.
- **Synthetic evolutions.** All evolutions are generated by edit operators. The authored policies were written for
  this study. The XPA policies are independent but small and mostly single-policy, and they lose obligations and
  advice in the import. The large scalability policies are synthetic, and GPMS is evaluated on 100 sampled edits.
- **Statistics.** Evolutions of one subject are not independent, so the confidence intervals and p-values describe
  the evaluated subjects and do not by themselves establish generality.
- **Baselines.** The flow-graph baselines are our re-implementations, following the published description.

## Citation

If you use this code, please cite the paper (bibliographic details will be added after publication).

## Licence

The code in `tpgreg/`, `experiments/` and `tests/` is released under the MIT licence (see `LICENSE`).
`third_party/ndg_xacml_py3` keeps its original BSD licence.
