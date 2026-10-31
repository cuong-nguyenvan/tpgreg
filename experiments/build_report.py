"""Collect the outputs of all experiments into CSV tables and a Markdown
report.

Usage: python3 build_report.py <results dir>
Output: <results dir>/REPORT.md, <results dir>/tables/*.csv
"""
import csv, glob, json, os, sys
import numpy as np

R = sys.argv[1] if len(sys.argv) > 1 else "../results"
T = os.path.join(R, "tables")
os.makedirs(T, exist_ok=True)


def load(name):
    p = os.path.join(R, name)
    return json.load(open(p)) if os.path.exists(p) else None


SE = "single_edit_evolution/"


def write_csv(name, header, rows):
    with open(os.path.join(T, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def md(header, rows):
    esc = lambda x: str(x).replace("|", "\\|")
    out = "\n| " + " | ".join(esc(h) for h in header) + " |\n|" + "|".join("---" for _ in header) + "|\n"
    for r in rows:
        out += "| " + " | ".join(esc(x) for x in r) + " |\n"
    return out


pct = lambda x: f"{100 * x:.1f}"
A, S, ST = load(SE + "summary.json"), load(SE + "policy_statistics.json"), load(SE + "significance_tests.json")
rep = ["# TPG-Reg — experiment report\n",
       "All numbers below are produced by the scripts in `experiments/` (see `run_all.sh`). "
       "EDR = evolution detection rate, ARE = affected-rule exposure, |T| = tests per evolution; "
       "mean over seeds 1–5 (± population SD).\n"]

# ---------------------------------------------------------------- datasets
if S:
    rows = []
    for ds, s in S.items():
        der = s["edges"]
        rows.append([ds, s["rules"], s["policies"], s["N"], sum(s["nodes"].values()), sum(der.values()),
                     f"{der.get('precedes', 0)}/{der.get('overrides', 0)}/{der.get('refers', 0)}",
                     A[ds]["n"], A[ds]["changed"]])
    h = ["Set", "Rules", "Policies", "|D|", "|V|", "|E|", "precedes/overrides/refers", "Evolutions", "Behaviour-changing"]
    write_csv("benchmark_policy_sets.csv", h, rows)
    rep += ["\n## Benchmark policy sets and TPG sizes\n", md(h, rows)]

# ---------------------------------------------------------------- impact analysis and ablation
if A:
    order = ["AST-Up", "TPG-Reg", "-precedes", "-overrides", "-scopes", "-refers"]
    rows = []
    for m in order:
        d = A["ALL"][m]
        rows.append([m, pct(d["BIS_recall"]), pct(d["BIS_prec"]), d["miss_evo"], f"{d['bis_size_ch']:.1f}",
                     pct(d["EDR"]), pct(d["ARE"]), f"{d['size_ch']:.1f}", d["eq_nonempty"]])
    h = ["Variant", "BIS recall %", "BIS precision %", "Evolutions with missed affected rule", "mean |BIS|",
         "EDR %", "ARE %", "|T|", "Equivalent evolutions with non-empty impact (of 99)"]
    write_csv("impact_analysis_and_edge_ablation.csv", h, rows)
    rep += [f"\n## Impact analysis and edge-type ablation ({A['ALL']['changed']} behaviour-changing single-edit evolutions)\n", md(h, rows)]
    per = []
    for ds in ("HACS", "FMS", "SIS"):
        per.append([ds] + [pct(A[ds][m]["BIS_recall"]) for m in order])
    write_csv("impact_set_recall_by_policy_set.csv", ["Set"] + order, per)
    rep += ["\nBIS recall per dataset (%):\n\n", md(["Set"] + order, per)]

    # regression detection by method
    meths = ["Retest-all(GA)", "Retest-all", "XFG-Regen(GA)", "XFG-Regen", "AST-Up", "Diff-1", "Diff-k", "Diff-all",
             "TPG-Reg(cfW1)", "TPG-Reg", "TPG-Reg(raw)", "TPG-Reg+D", "TPG-Reg(D-only)"]
    rows = []
    for m in meths:
        r = [m]
        for ds in ("HACS", "FMS", "SIS", "ALL"):
            d = A[ds][m]
            r += [f"{pct(d['EDR'])}±{100 * d['EDR_sd']:.1f}", f"{pct(d['ARE'])}±{100 * d['ARE_sd']:.1f}", f"{d['size_ch']:.1f}"]
        rows.append(r)
    h = ["Method"] + [f"{ds} {k}" for ds in ("HACS", "FMS", "SIS", "ALL") for k in ("EDR %", "ARE %", "|T|")]
    write_csv("regression_detection_by_method.csv", h, rows)
    rep += ["\n## Regression detection on single-edit evolutions\n",
            "Retest-all / XFG-Regen: path-based flow-graph suites of P1 / P2 (one request per rule path), minimised by a genetic algorithm (GA) or greedy set cover. "
            "TPG-Reg(raw): witnesses without minimisation.\n\n", md(h, rows)]
    ops = list(A["per_op"])
    rows = [[m] + [pct(A["per_op"][o][m]["EDR"]) for o in ops] for m in meths]
    h = ["Method"] + [f"{o} ({A['per_op'][o]['changed']})" for o in ops]
    write_csv("detection_rate_by_edit_operator.csv", h, rows)
    rep += ["\nEDR (%) per edit operator (behaviour-changing evolutions in parentheses):\n\n", md(h, rows)]
    if os.path.exists(os.path.join(R, SE + "detection_rates.png")):
        rep += ["\n![EDR and ARE](single_edit_evolution/detection_rates.png)\n"]

if ST:
    rows = [[k, f"{v['EDR']['p']:.2e}", f"{v['EDR']['A12']:.2f}", f"{v['ARE']['p']:.2e}", f"{v['ARE']['A12']:.2f}",
             v["McNemar_seed1"]["b"], v["McNemar_seed1"]["c"], f"{v['McNemar_seed1']['p']:.1e}"] for k, v in ST.items()]
    h = ["Comparison", "EDR Wilcoxon p", "EDR A12", "ARE Wilcoxon p", "ARE A12", "McNemar b", "McNemar c", "McNemar p"]
    write_csv("significance_tests.csv", h, rows)
    rep += ["\n### Significance tests (paired over behaviour-changing evolutions)\n", md(h, rows)]

# ---------------------------------------------------------------- external policies (XPA), enumerable
EA, ES = load("external_single_edit/summary.json"), load("external_single_edit/policy_statistics.json")
if EA:
    sets = list(ES)
    rows = [[ds, ES[ds]["rules"], ES[ds]["policies"], ES[ds]["N"], f"{ES[ds]['edges'].get('precedes', 0)}/{ES[ds]['edges'].get('overrides', 0)}/{ES[ds]['edges'].get('refers', 0)}",
             EA[ds]["n"], EA[ds]["changed"], pct(EA[ds]["TPG-Reg"]["BIS_recall"]), pct(EA[ds]["TPG-Reg"]["BIS_prec"])] for ds in sets]
    h = ["Set", "Rules", "Policies", "|D|", "precedes/overrides/refers", "Evolutions", "Behaviour-changing", "BIS recall %", "BIS precision %"]
    write_csv("external_policy_sets.csv", h, rows)
    rep += ["\n## Independent external policies (XPA repository; synthetic evolutions)\n", md(h, rows)]
    meths = ["Retest-all(GA)", "Retest-all", "XFG-Regen(GA)", "XFG-Regen", "AST-Up", "Diff-1", "Diff-k", "Diff-all",
             "TPG-Reg(cfW1)", "TPG-Reg", "TPG-Reg+D", "TPG-Reg(D-only)"]
    rows = [[m] + [pct(EA[ds][m]["EDR"]) for ds in sets] + [f"{pct(EA['ALL'][m]['EDR'])}±{100 * EA['ALL'][m]['EDR_sd']:.1f}",
             f"{pct(EA['ALL'][m]['ARE'])}±{100 * EA['ALL'][m]['ARE_sd']:.1f}", f"{EA['ALL'][m]['size_ch']:.1f}"] for m in meths]
    h = ["Method"] + [f"{ds} EDR %" for ds in sets] + ["All EDR %", "All ARE %", "|T|"]
    write_csv("external_regression_detection_by_method.csv", h, rows)
    rep += ["\nDetection on the behaviour-changing external evolutions:\n\n", md(h, rows)]
    c = EA["cost"]
    rows = [[ds, f"{c[ds]['obl_W']:.1f}", f"{c[ds]['obl_D']:.1f}", f"{c[ds]['obl_Donly']:.1f}", f"{c[ds]['obl_diffall']:.1f}"] for ds in c]
    h = ["Set", "Obligations TPG-Reg", "TPG-Reg+D", "TPG-Reg(D-only)", "Diff-all"]
    write_csv("external_obligations.csv", h, rows)
    rep += ["\nObligations posed per behaviour-changing evolution:\n\n", md(h, rows)]
if A and "cost" in A:
    c = A["cost"]
    rows = [[ds, f"{c[ds]['obl_W']:.1f}", f"{c[ds]['obl_D']:.1f}", f"{c[ds]['obl_Donly']:.1f}", f"{c[ds]['obl_diffall']:.1f}",
             f"{c[ds]['t_gen_W_ms']:.1f}", f"{c[ds]['t_gen_D_ms']:.1f}"] for ds in c]
    h = ["Set", "Obligations TPG-Reg", "TPG-Reg+D", "TPG-Reg(D-only)", "Diff-all", "gen ms W", "gen ms +D"]
    write_csv("authored_obligations.csv", h, rows)
    rep += ["\nAuthored sets: obligations posed per behaviour-changing evolution and generation time:\n\n", md(h, rows)]

# ---------------------------------------------------------------- oracle correctness
rows = []
for SS in (S, ES):
    for ds, s_ in (SS or {}).items():
        wf = [v for v in s_["wrong_frac"].values() if v is not None]
        wx = s_.get("w1_exhaustive", {})
        rows.append([ds, s_["rules"], f"{np.mean(s_['oracle']['xfg_err']):.1f}", pct(np.mean(s_['oracle']['xfg_err']) / s_["rules"]),
                     len(wx.get("exact", {}).get("wrong_expected", [])), len(wx.get("exact", {}).get("non_decisive", [])),
                     len(wx.get("cf", {}).get("wrong_expected", [])), " ".join(wx.get("cf", {}).get("non_decisive", [])) or "-",
                     " ".join(s_["never_decisive"]) or "-"])
if rows:
    h = ["Set", "Rules", "Path-oracle errors per suite", "Error rate %", "Exact W1: rules with wrong expected decision",
         "Exact W1: rules with non-decisive requests", "cf-W1: rules with wrong expected decision", "cf-W1: rules with non-decisive requests",
         "Dead rules (exact W1 unsatisfiable)"]
    write_csv("oracle_correctness.csv", h, rows)
    rep += ["\n## Oracle correctness: path-based oracle vs. decisive witness (exhaustive over the request space)\n", md(h, rows)]

# ---------------------------------------------------------------- two-edit commits
for _dir, _lab in (("two_edit_commits", "authored sets"), ("external_two_edit_commits", "external XPA policies")):
  Q5 = load(_dir + "/summary.json")
  if Q5:
      meths = [m for m in Q5["clean"] if isinstance(Q5["clean"][m], dict)]
      rows = [[m, pct(Q5["clean"][m]["flag"]), pct(Q5["clean"][m]["det"]), pct(Q5["dirty"][m]["flag"]),
               pct(Q5["dirty"][m]["det"]), f"{Q5['dirty'][m]['size']:.1f}"] for m in meths]
      rows.append(["Exhaustive (all requests)", pct(Q5["clean"]["oracle_flaggable_exhaustive"] / Q5["clean"]["n"]), "100",
                   pct(Q5["dirty"]["oracle_flaggable_exhaustive"] / Q5["dirty"]["n"]), "100", "-"])
      h = ["Method", "Clean: false alarm %", "Clean: detect %", "Dirty: flagged %", "Dirty: detect %", "Dirty: |T|"]
      write_csv(_dir + ".csv", h, rows)
      rep += [f"\n## Change-aware (intent) oracle on two-edit commits, {_lab} ({Q5['clean']['n']} clean, {Q5['dirty']['n']} with an undeclared edit)\n", md(h, rows)]

# ---------------------------------------------------------------- scalability and external SMT subject
def smt_tables(runs, title, csvname):
    global rep
    rows, cost = [], []
    for n in sorted({r["n"] for r in runs}, key=lambda x: (isinstance(x, str), x)):
        rs = [r for r in runs if r["n"] == n]
        ch = [r for r in rs if r["changed"]]
        full = "det_W" in rs[0]
        nrules = rs[0].get("outside_rules", 0) + rs[0].get("BIS", 0) if isinstance(n, str) else n
        row = [n, rs[0].get("E_star", ""), f"{rs[0]['t_build1']:.1f}", rs[0]["q_build1"], len(rs), len(ch),
               f"{np.median([r['t_tpg2'] for r in rs]):.2f}", f"{np.median([r['t_bis'] for r in rs]):.3f}",
               f"{np.median([r['BIS'] for r in rs]):.0f}", f"{np.median([r['t_global'] for r in rs]):.3f}"]
        if full:
            row += [sum(r["outside_rules"] for r in ch), sum(r["outside_unsat"] for r in ch), sum(r["outside_unknown"] for r in ch),
                    sum(r["violations"] for r in ch), sum(r["aff_exact"] for r in ch), sum(r["aff_unknown"] for r in ch)]
            aff = sum(r["aff_exact"] for r in ch) or 1
            for key, lab in (("W", "TPG-Reg"), ("D", "TPG-Reg+D"), ("diff1", "Diff-1"), ("diffk", "Diff-k"), ("donly", "TPG-Reg(D-only)"), ("diffall", "Diff-all")):
                T = {"W": "T_W", "D": "T_D", "diff1": None, "diffk": "T_diffk", "diffall": "T_diffall", "donly": "T_donly"}[key]
                calls = {"W": "calls_W", "D": "calls_D", "diff1": None, "diffk": None, "diffall": "calls_diffall", "donly": "calls_donly"}[key]
                tg = {"W": "t_gen_W", "D": "t_gen_D", "diff1": "t_diff1", "diffk": "t_diffk", "diffall": "t_diffall", "donly": "t_donly"}[key]
                cost.append([n, lab, pct(np.mean([r[f"det_{key}"] for r in ch])), pct(sum(r[f"exp_{key}"] for r in ch) / aff),
                             f"{np.mean([r[T] for r in ch]):.1f}" if T else "1.0",
                             f"{np.mean([r[calls] for r in ch]):.1f}" if calls else "1",
                             sum(r.get(f"unknown_{key}", 0) for r in ch) if key in ("W", "D") else "-",
                             f"{np.median([r[tg] for r in ch]):.2f}", f"{np.mean([r[tg] for r in ch]):.2f}"])
        else:
            row += ["not run"] * 6
        rows.append(row)
    h = ["n", "|E*|", "build s", "Z3 queries (build)", "evolutions", "changed", "G2 incr. s (med)", "BIS s (med)", "|BIS| (med)",
         "global diff s (med)", "outside-BIS rules queried", "UNSAT", "UNKNOWN", "soundness violations", "affected rules (exact)", "affected UNKNOWN"]
    write_csv(csvname + ".csv", h, rows)
    rep += [f"\n## {title}\n", md(h, rows)]
    if cost:
        h2 = ["n", "Method", "EDR %", "ARE %", "|T|", "solver calls", "UNKNOWN", "gen s (med)", "gen s (mean)"]
        write_csv(csvname + "_cost.csv", h2, cost)
        rep += ["\nEnd-to-end generation cost and effectiveness on behaviour-changing evolutions "
                "(gen = obligation construction + solving + minimisation; Diff-all also includes its per-rule queries):\n\n", md(h2, cost)]


sc = [r for f in sorted(glob.glob(os.path.join(R, "scalability", "runs_*.json"))) for r in json.load(open(f))]
if sc:
    smt_tables(sc, "Scalability with the Z3 backend (synthetic policies, integer domains [0, 10^6])", "scalability_smt_backend")
ex = [r for f in sorted(glob.glob(os.path.join(R, "external", "runs_*.json"))) for r in json.load(open(f))]
if ex:
    smt_tables(ex, "External policy GPMS (XPA repository) with the Z3 backend", "external_gpms_smt")

# ---------------------------------------------------------------- validation
X, Z = load("validation/pdp_conformance.json"), load("validation/smt_backend_equivalence.json")
if X or Z:
    rep += ["\n## Validation\n"]
if X:
    rows = [[k, v["versions"], v["checked"], v["mismatches"], v.get("exhaustive_original", "")] for k, v in X.items() if k != "examples"]
    h = ["Set", "Policy versions", "Requests evaluated", "Mismatches vs ndg-xacml", "Exhaustive original requests"]
    write_csv("pdp_conformance_ndg_xacml.csv", h, rows)
    rep += ["\nPrototype PDP vs. independent XACML PDP (ndg-xacml):\n\n", md(h, rows)]
if Z:
    rows = [[k, v["versions"], v["edges_identical"], v["smt_queries"], v["prefilter_pruned"], f"{v['witness_valid']}/{v['witness_checked']}"] for k, v in Z.items()]
    h = ["Set", "Versions", "Edge sets identical (Z3 vs enumeration)", "Z3 queries", "Pre-filtered pairs", "Valid Z3 witnesses"]
    write_csv("smt_backend_equivalence.csv", h, rows)
    rep += ["\nZ3 backend vs. enumeration backend:\n\n", md(h, rows)]

if os.path.exists(os.path.join(R, "finance_example", "output.txt")):
    rep += ["\n## Financial example (Commit A: refine R2, Commit B: refactoring)\n\n```\n" + open(os.path.join(R, "finance_example", "output.txt")).read() + "```\n"]

rep += ["\n## Result files\n",
        "- `tables/*.csv` — every table above\n",
        "- `single_edit_evolution/` — `per_evolution_<SET>.json` (per evolution and seed), `policy_statistics.json`, `summary.json`, `significance_tests.json`, `detection_rates.png`\n",
        "- `two_edit_commits/` — `per_commit.json`, `summary.json`\n",
        "- `scalability/` — `runs_full_pipeline_n*.json`, `runs_analysis_only_n*.json`\n",
        "- `validation/` — `pdp_conformance.json`, `smt_backend_equivalence.json`\n",
        "- `regression_suites/` — `<SET>_regression_tests.csv` (requests, decisions of both versions, decisive rules) and `<SET>_impact_sets.csv` for every evolution\n",
        "- `xacml_policies/` — policy sets and financial-example versions as XACML 2.0 XML\n",
        "- `finance_example/output.txt` — output of the financial example\n",
        "- `logs/` — console output of every step\n"]
open(os.path.join(R, "REPORT.md"), "w").write("".join(rep))
print("report written with", len(os.listdir(T)), "tables")
