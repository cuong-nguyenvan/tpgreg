"""Independent external policies from the XPA repository
(https://github.com/dianxiangxu/XPA, commit 89c0004, Experiments/), imported
with xacml_import. They are fetched by experiments/fetch_external_policies.sh
into ./external/xpa (not redistributed here). Evolutions of these policies
are synthetic (edit operators of mutation.py); no commit history is used."""
import os
from .xacml_import import import_policies

ROOT = os.environ.get("TPGREG_EXTERNAL", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "external", "xpa"))
# enumerable request spaces: exhaustive ground truth
ENUM = {"iTrust": "itrust3/itrust3.xml", "Pluto": "pluto3/pluto3.xml",
        "Conference": "conference3/conference3.xml", "Fedora": "fedora-rule3/fedora-rule3.xml"}
# request space of about 2e17: SMT backend, exact per-rule queries as ground truth
SMT = {"GPMS": "gpms/gpms.xml"}


def _mk(name, rel):
    ps, dom = import_policies([os.path.join(ROOT, rel)], name.upper())
    return (lambda ps=ps: __import__("copy").deepcopy(ps)), dom


def external_datasets():
    return {n: _mk(n, r) for n, r in ENUM.items()}


def external_smt():
    out = []
    for n, r in SMT.items():
        mk, dom = _mk(n, r)
        out.append((n, mk(), dom))
    return out
