"""Scalability study with the Z3 backend on synthetic policies whose request
space cannot be enumerated (four integer attributes in [0, 10^6]).

For each size n, one policy set and E single-edit evolutions are generated.
Per evolution we measure: incremental TPG update, difference + BIS,
witness solving + greedy minimisation (W1-W3), distinguishing queries (D),
and a single global semantic-difference query. Ground truth: the global query
decides whether behaviour changed; up to S distinguishing requests sampled
from it give affected rules, used to check BIS soundness and exposure.

Usage: python3 exp_scalability.py <out dir> <sizes, e.g. 50,100,200,400> <evolutions per size> [analysis]
Output: runs_full_pipeline_n<sizes>.json or runs_analysis_only_n<sizes>.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import copy, json, sys, time
import numpy as np
import z3
from tpgreg.policy_model import PolicySet, Policy, Rule, Pred, p, AND, OR, VAR, evaluate, EFF, NA
from tpgreg.typed_policy_graph import TPG, INTER
from tpgreg.impact_analysis import diff_bis
from tpgreg.smt_backend import Encoder, Batch, IntRange, solve
from tpgreg.mutation import evolutions

SIZES, E_PER_SIZE, ANALYSIS_ONLY, OUT = [50, 100, 200, 400], 30, False, "../results/scalability"
TO = 10000   # ms per query


def make_domains():
    dom = {f"c{i}": [f"v{j}" for j in range(20)] for i in range(1, 7)}
    for i in range(1, 5):
        dom[f"n{i}"] = IntRange(0, 10 ** 6)
    return dom


def gen_policy(n, seed):
    rng = np.random.default_rng(seed)
    pick = lambda xs: xs[int(rng.integers(len(xs)))]
    algs = ["DO", "PO", "FA"]
    pols = []
    for pi in range((n + 9) // 10):
        vars_ = {}
        if rng.random() < 0.5:
            vars_["w"] = AND(p("n1", "ge", int(rng.integers(0, 5 * 10 ** 5))),
                             p("n1", "lt", int(rng.integers(5 * 10 ** 5, 10 ** 6))))
        rules = []
        for ri in range(min(10, n - 10 * pi)):
            tgt = []
            if rng.random() < 0.9:
                tgt.append(Pred("c1", "eq", f"v{int(rng.integers(20))}"))
            if rng.random() < 0.6:
                tgt.append(Pred("c4", "in", tuple(sorted({f"v{int(x)}" for x in rng.integers(0, 20, 2)}))))
            atoms = [p(f"n{int(rng.integers(1, 5))}", pick(["ge", "lt", "gt", "le"]), int(rng.integers(0, 10 ** 6)))
                     for _ in range(int(rng.integers(1, 3)))]
            if "w" in vars_ and rng.random() < 0.3:
                atoms.append(VAR("w"))
            cond = atoms[0] if len(atoms) == 1 else (AND(*atoms) if rng.random() < 0.7 else OR(*atoms))
            rules.append(Rule(f"X.P{pi}.R{ri}", "Permit" if rng.random() < 0.6 else "Deny", tgt, cond))
        ptgt = [Pred("c3", "eq", f"v{pi % 20}")] if rng.random() < 0.9 else []
        pols.append(Policy(f"X.P{pi}", pick(algs), ptgt, rules, vars_))
    return PolicySet("X", pick(algs), [], pols)


def pol_sig(pol):
    return repr((pol.alg, pol.target, pol.vars, [(r.id, r.effect, r.target, r.cond) for r in pol.rules]))


class SMTGraph(TPG):
    """TPG whose overlap test is a Z3 query; reuses results of a previous
    version for rule pairs whose policies are unchanged (incremental)."""

    def __init__(self, ps, enc, prev=None):
        self.enc = enc
        self.appf, self.regionf, self.localf, self.effv = enc.app(ps)
        self.solver = z3.Solver()
        self.solver.set("timeout", TO)
        self.solver.add(*enc.cons)
        self.cache = {}
        self.queries = self.pruned = self.reused = self.unknown = 0
        clean = set()
        if prev is not None and prev.ps.alg == ps.alg and repr(prev.ps.target) == repr(ps.target):
            psig = {pol.id: (i, pol_sig(pol)) for i, pol in enumerate(prev.ps.policies)}
            for i, pol in enumerate(ps.policies):
                if psig.get(pol.id) == (i, pol_sig(pol)):
                    clean.add(pol.id)
        self.prev, self.clean = prev, clean
        super().__init__(ps, None, ev=type("E", (), {"app": None})())

    def _overlap(self, pa, ra, pb, rb):
        key = (ra.id, rb.id)
        if self.prev is not None and pa.id in self.clean and pb.id in self.clean and key in self.prev.cache:
            self.reused += 1
            self.cache[key] = self.prev.cache[key]
            return self.cache[key]
        if _disjoint(ra, rb, pa, pb):
            self.pruned += 1
            self.cache[key] = False
            return False
        self.queries += 1
        s = self.solver
        s.push()
        s.add(self.appf[ra.id], self.appf[rb.id])
        r = s.check()
        s.pop()
        if r == z3.unknown:
            self.unknown += 1
        self.cache[key] = r != z3.unsat
        return self.cache[key]


def _disjoint(ra, rb, pa, pb):
    def sets(ts):
        out = {}
        for t in ts:
            if t.op == "eq":
                s = {t.val}
            elif t.op == "in":
                s = set(t.val)
            else:
                continue
            out[t.attr] = out[t.attr] & s if t.attr in out else s
        return out
    A, B = sets(list(ra.target) + list(pa.target)), sets(list(rb.target) + list(pb.target))
    return any(a in B and not (A[a] & B[a]) for a in A)


def competitors(g, rid):
    out = set()
    rn = "R:" + rid
    for e in g.edges:
        if e[0] == "precedes" and e[2] == rn:
            out.add(e[1][2:])
        elif e[0] == "overrides" and rn in (e[1], e[2]):
            d = e[2][2:] if e[1] == rn else e[1][2:]
            if (e[3] == "DO" and g.effv[d] == 2) or (e[3] == "PO" and g.effv[d] == 1):
                out.add(d)
    return out


def obligations(g1, g2, CH, bis, followed, with_d, sem1, sem2, w1="exact"):
    """List of (formula, checker) where checker(ev1, ev2, i) -> bool.
    sem_v = (root decision term, {rule: exact decisive predicate})."""
    (dec1, D1), (dec2, D2) = sem1, sem2
    obl = []
    for v, g, Dv in ((1, g1, D1), (2, g2, D2)):
        for rid in sorted(bis):
            if rid not in g.appf:
                continue
            if w1 == "exact":       # W1_v(r, q) := Dec_v(r, q)
                obl.append((Dv[rid], lambda e1, e2, i, v=v, rid=rid: bool((e1 if v == 1 else e2).decisive[rid][i])))
            else:
                comp = sorted(competitors(g, rid))
                f = z3.And([g.appf[rid]] + [z3.Not(g.appf[c]) for c in comp])
                obl.append((f, lambda e1, e2, i, v=v, rid=rid, comp=comp:
                            (e1 if v == 1 else e2).app[rid][i] and not any((e1 if v == 1 else e2).app[c][i] for c in comp)))
            if rid in CH:
                others = sorted(set(g.appf) - {rid})
                f = z3.And([g.appf[rid]] + [z3.Not(g.appf[c]) for c in others])
                obl.append((f, lambda e1, e2, i, v=v, rid=rid, others=others:
                            (e1 if v == 1 else e2).app[rid][i] and not any((e1 if v == 1 else e2).app[c][i] for c in others)))
        for e in sorted(followed):
            if e in g.edges:
                a, b = e[1][2:], e[2][2:]
                obl.append((z3.And(g.appf[a], g.appf[b]),
                            lambda e1, e2, i, v=v, a=a, b=b: (e1 if v == 1 else e2).app[a][i] and (e1 if v == 1 else e2).app[b][i]))
    for rid in sorted(CH):
        if rid in g1.appf and rid in g2.appf:
            obl.append((z3.And(g1.appf[rid], z3.Not(g2.appf[rid])), lambda e1, e2, i, rid=rid: e1.app[rid][i] and not e2.app[rid][i]))
            obl.append((z3.And(g2.appf[rid], z3.Not(g1.appf[rid])), lambda e1, e2, i, rid=rid: e2.app[rid][i] and not e1.app[rid][i]))
    if with_d:
        for rid in sorted(bis):
            obl.append((d_formula(rid, sem1, sem2), d_checker(rid)))
    return obl


def d_formula(rid, sem1, sem2):
    (dec1, D1), (dec2, D2) = sem1, sem2
    parts = [Dv[rid] for Dv in (D1, D2) if rid in Dv]
    return z3.And(dec1 != dec2, z3.Or(parts))


def d_checker(rid):
    def chk(e1, e2, i):
        return bool(e1.dec[i] != e2.dec[i] and ((rid in e1.decisive and e1.decisive[rid][i]) or
                                                (rid in e2.decisive and e2.decisive[rid][i])))
    return chk


def generate(g1, g2, ps1, ps2, dom, obl, rng, k=3):
    """Solve each obligation (k candidates), then greedy set cover using PDP
    evaluation of both versions on the candidates. Returns the suite and
    solver statistics (calls, sat, unsat, unknown, time)."""
    cands = []
    st = {"calls": 0, "sat": 0, "unsat": 0, "unknown": 0}
    t0 = time.perf_counter()
    for f, _ in obl:
        sols, r = solve(g1.enc, f, rng, k=k, timeout_ms=TO, status=True)
        st["calls"] += 1
        st[r] += 1
        cands.extend(sols)
    st["t_solve"] = time.perf_counter() - t0
    if not cands:
        st["t_min"] = 0.0
        return [], st
    t0 = time.perf_counter()
    B = Batch(dom, cands)
    e1, e2 = evaluate(ps1, B), evaluate(ps2, B)
    cov = np.array([[bool(chk(e1, e2, i)) for i in range(len(cands))] for _, chk in obl])
    left = cov.any(axis=1)
    chosen = []
    while left.any():
        gain = cov[left].sum(axis=0)
        best = int(np.argmax(gain))
        if gain[best] == 0:
            break
        chosen.append(best)
        left &= ~cov[:, best]
    st["t_min"] = time.perf_counter() - t0
    return [cands[i] for i in chosen], st


def evaluate_suite(suite, ps1, ps2, dom, aff):
    if not suite:
        return False, 0
    B = Batch(dom, suite)
    a1, a2 = evaluate(ps1, B), evaluate(ps2, B)
    dmask = a1.dec != a2.dec
    exposed = {rid for rid in aff
               if (rid in a1.decisive and (a1.decisive[rid] & dmask).any()) or
                  (rid in a2.decisive and (a2.decisive[rid] & dmask).any())}
    return bool(dmask.any()), len(exposed)


def main(subjects=None, outname=None):
    """subjects: optional list of (label, policy set, domains); by default the
    synthetic policies of the sizes in SIZES."""
    import os; os.makedirs(OUT, exist_ok=True)
    if subjects is None:
        dom = make_domains()
        subjects = [(n, gen_policy(n, seed=n), dom) for n in SIZES]
    rows = []
    for n, ps1, dom in subjects:
        enc = Encoder(dom)
        t0 = time.perf_counter()
        g1 = SMTGraph(ps1, enc)
        t_build = time.perf_counter() - t0
        sem1 = enc.semantics(ps1); dec1 = sem1[0]
        evs = evolutions(ps1, {a: (list(range(0, 10 ** 6 + 1, 10 ** 5)) if isinstance(v, IntRange) else v) for a, v in dom.items()})
        rng = np.random.default_rng(n if isinstance(n, int) else sum(map(ord, n)))
        sel = rng.choice(len(evs), size=min(E_PER_SIZE, len(evs)), replace=False)
        print(f"n={n}: |E*|={len([e for e in g1.edges if e[0] in INTER])} build={t_build:.1f}s queries={g1.queries} pruned={g1.pruned} unknown={g1.unknown} evolutions={len(evs)}", flush=True)
        for k in sel:
            evo = evs[int(k)]
            ps2 = evo["ps"]
            row = {"n": n, "op": evo["op"], "desc": evo["desc"], "t_build1": t_build, "q_build1": g1.queries,
                   "E_star": len([e for e in g1.edges if e[0] in INTER]), "pruned1": g1.pruned}
            t0 = time.perf_counter(); g2 = SMTGraph(ps2, enc, prev=g1); row["t_tpg2"] = time.perf_counter() - t0
            row.update(q_tpg2=g2.queries, reused=g2.reused, unknown=g2.unknown)
            t0 = time.perf_counter(); CH, bis, cs, fol = diff_bis(g1, g2); row["t_bis"] = time.perf_counter() - t0
            row.update(CH=len(CH), BIS=len(bis))
            sem2 = enc.semantics(ps2); dec2 = sem2[0]
            # global semantic difference (one query) and affected-rule sample
            s = z3.Solver(); s.set("timeout", 60000); s.add(*enc.cons); s.add(dec1 != dec2)
            t0 = time.perf_counter(); r = s.check(); row["t_global"] = time.perf_counter() - t0
            row["changed"] = (r == z3.sat)
            row["global_unknown"] = (r == z3.unknown)
            if ANALYSIS_ONLY:
                rows.append(row)
                print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in row.items() if k2 != "desc"}, flush=True)
                continue
            # Exact per-rule query (also the Diff-all baseline): for every rule r,
            #   exists q: dec1(q) != dec2(q) and (Dec_P1(r, q) or Dec_P2(r, q)).
            # SAT for r outside the BIS is a soundness violation (confirmed with
            # the PDP); UNKNOWN is reported separately. The SAT rules form the
            # exact affected set (up to UNKNOWN) used for exposure.
            per_rule = {}
            sols_all, obl_all, in_bis = [], [], []
            t_all = t_donly = 0.0
            if r == z3.sat:
                for rid in sorted(set(g1.appf) | set(g2.appf)):
                    t0 = time.perf_counter()
                    sols, st = solve(enc, d_formula(rid, sem1, sem2), rng, k=1, timeout_ms=TO, status=True)
                    dt = time.perf_counter() - t0
                    t_all += dt
                    if rid in bis:
                        t_donly += dt
                    per_rule[rid] = st
                    if sols:
                        sols_all.extend(sols); obl_all.append(d_checker(rid)); in_bis.append(rid in bis)
                        if rid not in bis:   # confirm a potential violation with the PDP
                            B = Batch(dom, sols)
                            if not d_checker(rid)(evaluate(ps1, B), evaluate(ps2, B), 0):
                                per_rule[rid] = "sat_unconfirmed"
            aff = {rid for rid, st in per_rule.items() if st == "sat"}
            outside = [rid for rid in per_rule if rid not in bis]
            viol_conf = 0
            for rid in outside:
                if per_rule[rid] == "sat":
                    viol_conf += 1
            row["outside_rules"] = len(outside)
            row["outside_unsat"] = sum(per_rule[x] == "unsat" for x in outside)
            row["outside_sat"] = sum(per_rule[x] == "sat" for x in outside)
            row["outside_unknown"] = sum(per_rule[x] == "unknown" for x in outside)
            row["violations"] = viol_conf
            row["aff_exact"] = len(aff)
            row["aff_unknown"] = sum(st == "unknown" for st in per_rule.values())
            row["aff_outside_bis"] = len(aff - bis)
            # TPG-Reg (W) and TPG-Reg+D (D)
            for mode in ("W", "D"):
                obl = obligations(g1, g2, CH, bis, fol, mode == "D", sem1, sem2)
                t0 = time.perf_counter()
                suite, st = generate(g1, g2, ps1, ps2, dom, obl, rng)
                row[f"t_gen_{mode}"] = time.perf_counter() - t0
                row[f"obl_{mode}"] = len(obl)
                for kk in ("calls", "sat", "unsat", "unknown", "t_solve", "t_min"):
                    row[f"{kk}_{mode}"] = st[kk]
                row[f"T_{mode}"] = len(suite)
                t0 = time.perf_counter()
                row[f"det_{mode}"], row[f"exp_{mode}"] = evaluate_suite(suite, ps1, ps2, dom, aff)
                row[f"t_pdp_{mode}"] = time.perf_counter() - t0
            # direct semantic-difference baselines (no TPG, no BIS)
            t0 = time.perf_counter()
            d1 = solve(enc, dec1 != dec2, rng, k=1, timeout_ms=TO) if r == z3.sat else []
            row["t_diff1"] = time.perf_counter() - t0
            row["det_diff1"], row["exp_diff1"] = evaluate_suite(d1, ps1, ps2, dom, aff)
            t0 = time.perf_counter()
            dk = solve(enc, dec1 != dec2, rng, k=max(1, row["T_D"]), timeout_ms=TO) if r == z3.sat else []
            row["t_diffk"] = time.perf_counter() - t0
            row["T_diffk"] = len(dk)
            row["det_diffk"], row["exp_diffk"] = evaluate_suite(dk, ps1, ps2, dom, aff)
            # Diff-all: greedy cover over the per-rule solutions of all rules;
            # TPG-Reg(D-only): the same restricted to rules in the BIS
            def cover(idx):
                out = []
                if not idx:
                    return out
                sl = [sols_all[i] for i in idx]
                B = Batch(dom, sl)
                e1, e2 = evaluate(ps1, B), evaluate(ps2, B)
                cov = np.array([[obl_all[i](e1, e2, j) for j in range(len(sl))] for i in idx])
                left = cov.any(axis=1)
                while left.any():
                    gain = cov[left].sum(axis=0); best = int(np.argmax(gain))
                    if gain[best] == 0:
                        break
                    out.append(sl[best]); left &= ~cov[:, best]
                return out
            for key, idx, tq, calls in (("diffall", list(range(len(sols_all))), t_all, len(per_rule)),
                                        ("donly", [i for i in range(len(sols_all)) if in_bis[i]], t_donly,
                                         sum(1 for x in per_rule if x in bis))):
                t0 = time.perf_counter()
                su = cover(idx)
                row[f"t_{key}"] = tq + time.perf_counter() - t0
                row[f"calls_{key}"] = calls
                row[f"T_{key}"] = len(su)
                row[f"det_{key}"], row[f"exp_{key}"] = evaluate_suite(su, ps1, ps2, dom, aff)
            rows.append(row)
            print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in row.items() if k2 not in ("desc",)}, flush=True)
        name = outname or f"runs_{'analysis_only' if ANALYSIS_ONLY else 'full_pipeline'}_n{'-'.join(map(str, SIZES))}.json"
        json.dump(rows, open(f"{OUT}/{name}", "w"), indent=0)


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else OUT
    SIZES = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else SIZES
    E_PER_SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else E_PER_SIZE
    ANALYSIS_ONLY = len(sys.argv) > 4 and sys.argv[4] == "analysis"
    main()
