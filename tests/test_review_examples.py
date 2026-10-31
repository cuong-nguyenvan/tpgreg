"""Counterexamples raised in the review, checked against the exact decisive
predicate (enumeration and Z3) and the competitor-free variant.
Run: python3 tests/test_review_examples.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from tpgreg.policy_model import PolicySet, Policy, Rule, Pred, p, Grid, evaluate
from tpgreg.typed_policy_graph import TPG, INTER
from tpgreg.test_generation import w1_mask, w1_mask_cf
from tpgreg.impact_analysis import diff_bis
from tpgreg.smt_backend import Encoder, solve

DOM = {"a": [0, 1]}
ANY = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return cond


def fa_same_effect():
    """FA with two always-applicable Permit rules: r2 is never decisive; the
    competitor-free W1 of r2 is satisfiable, the exact W1 is not."""
    ps = PolicySet("X", "DO", [], [Policy("X.P1", "FA", [], [Rule("X.P1.R1", "Permit"), Rule("X.P1.R2", "Permit")])])
    g = TPG(ps, Grid(DOM))
    ok = check("FA same effect: cf-W1(r2) satisfiable but r2 not decisive", w1_mask_cf(g, "X.P1.R2", INTER).any())
    ok &= check("FA same effect: exact W1(r2) unsatisfiable (dead)", not w1_mask(g, "X.P1.R2", INTER).any())
    enc = Encoder(DOM); _, Dz = enc.semantics(ps)
    _, st = solve(enc, Dz["X.P1.R2"], np.random.default_rng(0), k=1, status=True)
    ok &= check("FA same effect: Z3 Dec(r2) is UNSAT", st == "unsat")
    # swapping the two rules changes decisiveness but not the decision (Lemma 1 restriction)
    ps2 = PolicySet("X", "DO", [], [Policy("X.P1", "FA", [], [Rule("X.P1.R2", "Permit"), Rule("X.P1.R1", "Permit")])])
    G = Grid(DOM); e1, e2 = evaluate(ps, G), evaluate(ps2, G)
    ok &= check("FA swap: decision unchanged although r1 loses decisiveness",
                (e1.dec == e2.dec).all() and e1.decisive["X.P1.R1"].all() and not e2.decisive["X.P1.R1"].any())
    return ok


def nested_competition():
    """Root DO; policy A = {Permit r}; policy B (PO) = {Deny d, Permit p}; all
    always applicable. B returns Permit, so r is decisive although d could
    override r at the root: the exact W1 of r is satisfiable."""
    ps = PolicySet("Y", "DO", [], [Policy("Y.P1", "DO", [], [Rule("Y.P1.R1", "Permit")]),
                                   Policy("Y.P2", "PO", [], [Rule("Y.P2.R1", "Deny"), Rule("Y.P2.R2", "Permit")])])
    g = TPG(ps, Grid(DOM))
    ok = check("nested PO: r decisive on every request", g.ev.decisive["Y.P1.R1"].all())
    ok &= check("nested PO: exact W1(r) satisfiable", w1_mask(g, "Y.P1.R1", INTER).any())
    ok &= check("nested PO: cf-W1(r) unsatisfiable (review 3b)", not w1_mask_cf(g, "Y.P1.R1", INTER).any())
    return ok


def soundness_two_level():
    """An edit inside one policy changes a decision that is decided at the
    root against an unchanged rule of another policy (level-1 then level-0)."""
    pol_a = lambda thr: Policy("Z.P1", "DO", [], [Rule("Z.P1.R1", "Permit"), Rule("Z.P1.R2", "Deny", [], p("a", "ge", thr))])
    pol_b = Policy("Z.P2", "DO", [], [Rule("Z.P2.R1", "Deny", [], p("a", "eq", 1))])
    ps1, ps2 = PolicySet("Z", "PO", [], [pol_a(1), pol_b]), PolicySet("Z", "PO", [], [pol_a(2), pol_b])
    G = Grid(DOM); g1, g2 = TPG(ps1, G), TPG(ps2, G)
    CH, bis, _, _ = diff_bis(g1, g2)
    diff = g1.ev.dec != g2.ev.dec
    aff = {r for ev in (g1.ev, g2.ev) for r, m in ev.decisive.items() if (m & diff).any()}
    return check(f"two-level soundness: affected {sorted(aff)} within BIS {sorted(bis)}", diff.any() and aff <= bis)


if __name__ == "__main__":
    ok = fa_same_effect() & nested_competition() & soundness_two_level()
    sys.exit(0 if ok else 1)
