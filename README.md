# TPG-Reg

**Change-impact-driven regression testing for evolving XACML policies, based on Typed Policy Graphs.**

Given two versions of an XACML policy set and the declared intent of the change, TPG-Reg

1. builds a **Typed Policy Graph** (TPG) for each version, with derived edges (`overrides`, `precedes`, `refers`)
   between rules that can interact;
2. matches the two graphs by XACML identifiers and computes the **Behavioral Impact Set** (BIS), the rules whose
   decisions the edit can change;
3. generates a regression suite inside the BIS from an exact decisiveness predicate: decisive (W1), interaction (W2) and
   difference (W3) witnesses, optionally distinguishing requests (`TPG-Reg+D`), or distinguishing requests only (`TPG-Reg(D)`);
4. runs it on both versions and classifies each changed decision as **intended** or **regression** against the declared edit scope.

## Main results

Behaviour-changing single-edit evolutions (synthetic), seeds 1–5. Authored sets: HACS, FMS, SIS (363 evolutions);
independent policies from the [XPA repository](https://github.com/dianxiangxu/XPA): iTrust, Pluto, Conference, Fedora (998).

| Method | EDR authored | ARE authored | Obligations | EDR XPA | ARE XPA | Obligations |
|---|---:|---:|---:|---:|---:|---:|
| Flow-graph suite, GA-minimised (Retest-all) | 51.7 % | 36.9 % | – | 46.4 % | 38.9 % | – |
| Syntactic difference (AST-Up) | 58.9 % | 31.5 % | – | 46.5 % | 34.9 % | – |
| Direct semantic difference, 1 request (Diff-1) | 100 % | 56.7 % | 1 | 100 % | 95.2 % | 1 |
| Distinguishing query for every rule (Diff-all) | 100 % | 100 % | 25.3 | 100 % | 100 % | 34.0 |
| **TPG-Reg** (W1–W3) | 92.9 % | 67.5 % | 60.8 | 99.9 % | 99.7 % | 12.8 |
| **TPG-Reg+D** | 100 % | 100 % | 70.9 | 100 % | 100 % | 16.0 |
| **TPG-Reg(D)** (distinguishing queries for BIS rules only) | 100 % | 100 % | 10.1 | 100 % | 100 % | 3.2 |

EDR: evolutions detected; ARE: affected rules exposed. The BIS contained every affected rule on all subjects, also
under exact Z3 soundness queries (11,259 on synthetic policies up to 400 rules, 8,435 on GPMS; all UNSAT). A direct
semantic-difference query detects every change as well; the BIS reduces the per-rule queries needed for full exposure.
The scope-based oracle flagged 278 of 280 constructed commits with an undeclared edit and none of the 280 clean ones.
Full results: [`results/REPORT.md`](results/REPORT.md).

## Installation and quick start

```bash
git clone https://github.com/cuong-nguyenvan/TPG-Reg.git && cd TPG-Reg
python3 -m pip install -r requirements.txt   # numpy, scipy, matplotlib, z3-solver (tested with Python 3.13)
```

```python
import numpy as np
from tpgreg.policy_model import Grid
from tpgreg.benchmarks import fin, FIN_DOM
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise

G = Grid(FIN_DOM)
g1, g2 = TPG(fin("DO", 5), G), TPG(fin("FA", 5), G)     # deny-overrides -> first-applicable
changed, bis, container_seeds, followed = diff_bis(g1, g2)
use = ("precedes", "overrides", "scopes", "refers")
suite = minimise(tpg_obligations(g1, g2, changed, bis, container_seeds, followed, use),
                 np.random.default_rng(1))
print(sorted(bis), [G.request(q) for q in suite])        # ['M.R1', 'M.R2'] and 3 tests
```

## Reproducing the experiments

```bash
./run_all.sh            # all experiments (about 1.5 hours on 2 cores)
./run_all.sh --fast     # without SMT studies and PDP cross-check (about 15 minutes)
./run_all.sh --no-smt   # everything except the SMT studies
./run_all.sh --smt-only # only the SMT studies (scalability, GPMS)
```

The external XPA policies are not redistributed; `experiments/fetch_external_policies.sh` (called by `run_all.sh`)
downloads them at a fixed commit into `external/xpa`. Results are deterministic (fixed seeds, `PYTHONHASHSEED=0`) except for timings; pre-computed results are in `results/`.

## Repository layout

```
tpgreg/        library: policy model and PDP, TPG, impact analysis, test generation,
               baselines, Z3 backend, mutation operators, benchmarks, XACML import/export
experiments/   one script per experiment (impact analysis, detection, intent oracle,
               scalability, PDP cross-check, report)
results/       pre-computed results, logs, tables and REPORT.md
tests/         unit tests for corner cases of the decisive predicate (FA same effect, nested PO/DO)
third_party/   ndg-xacml 0.5.1 ported to Python 3 (BSD licence), used as independent PDP
```

## Limitations

- Supports deny-overrides, permit-overrides and first-applicable; Indeterminate, obligations and advice are not modelled.
- All evolutions are synthetic (edit operators); the authored policies were written for this study, the XPA policies
  are independent but small and lose obligations and advice in the import, and the large scalability policies are synthetic.
