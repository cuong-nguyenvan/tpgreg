"""External policy with a non-enumerable request space (GPMS from the XPA
repository, 97 rules in 3 policies, about 2e17 requests): the full SMT
pipeline of exp_scalability.py on E randomly selected single-edit
evolutions. Ground truth is exact up to UNKNOWN: one global query decides
whether behaviour changed, and one query per rule,
  exists q: dec1(q) != dec2(q) and (Dec_P1(r, q) or Dec_P2(r, q)),
gives the affected rules (also checks BIS soundness).

Usage: python3 exp_external_smt.py <out dir> [evolutions]
Output: runs_external_GPMS.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
import sys
import exp_scalability as X
from tpgreg.external import external_smt

X.OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/external"
X.E_PER_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 100
X.ANALYSIS_ONLY = False
X.main(subjects=external_smt(), outname="runs_external_GPMS.json")
