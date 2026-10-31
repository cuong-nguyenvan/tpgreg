"""Import XACML 3.0 policies into the simplified policy model.

Supported subset (sufficient for the external XPA policies used in the
evaluation): PolicySet or Policy root; targets with AnyOf/AllOf/Match using
string-equal, boolean-equal or integer comparisons; conditions built from
and/or/not, *-equal, integer comparisons over *-one-and-only, string-is-in
and string-at-least-one-member-of with a literal bag. Attributes are read
from AttributeDesignator (AttributeId) or AttributeSelector (Path).
Obligations and advice are ignored. A target that is not a conjunction of
single-attribute disjunctions is moved into the rule condition (rules only).

Finite domains: every literal compared with an attribute, plus one value
"_other" for string attributes; booleans {true,false}; for integers, every
threshold c together with c-1 and c+1.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from .policy_model import PolicySet, Policy, Rule, Pred, p, AND, OR, NOT

ALG = {"deny-overrides": "DO", "permit-overrides": "PO", "first-applicable": "FA",
       "ordered-deny-overrides": "DO", "ordered-permit-overrides": "PO"}
CMP = {"greater-than": "gt", "less-than": "lt", "greater-than-or-equal": "ge", "less-than-or-equal": "le"}


def _tag(e):
    return e.tag.split("}")[-1]


def _kids(e, name=None):
    return [c for c in e if name is None or _tag(c) == name]


def _fn(e):
    return e.get("FunctionId", e.get("MatchId", "")).split(":")[-1]


def _alg(s):
    return ALG[s.split(":")[-1]]


class Importer:
    def __init__(self, prefix):
        self.prefix = prefix
        self.vals = {}       # attr -> set of literal values
        self.types = {}      # attr -> "string" | "boolean" | "integer"

    def attr(self, e):
        if _tag(e) == "AttributeDesignator":
            a = re.split(r"[:/]", e.get("AttributeId"))[-1]
        else:   # AttributeSelector
            m = re.search(r"([A-Za-z0-9_.\-]+)/text\(\)", e.get("Path", ""))
            a = m.group(1) if m else e.get("Path")
        t = e.get("DataType", "#string").split("#")[-1]
        self.types[a] = t
        self.vals.setdefault(a, set())
        return a

    def lit(self, e, a):
        t = self.types.get(a, "string")
        v = e.text.strip()
        if t == "integer":
            v = int(v)
        self.vals[a].add(v)
        return v

    # ------------------------------------------------------------ targets
    def match(self, m):
        f = _fn(m)
        av = _kids(m, "AttributeValue")[0]
        des = [c for c in m if _tag(c) in ("AttributeDesignator", "AttributeSelector")][0]
        a = self.attr(des)
        v = self.lit(av, a)
        if f.endswith("-equal"):
            return Pred(a, "eq", v)
        for k, op in CMP.items():
            if f.endswith(k):    # XACML Match: f(value, attribute) -> value op attribute
                inv = {"gt": "lt", "lt": "gt", "ge": "le", "le": "ge"}[op]
                return Pred(a, inv, v)
        raise ValueError(f"unsupported match {f}")

    def target(self, t):
        """Returns (list of Pred or None, expression)."""
        if t is None:
            return [], None
        conj_preds, exprs, ok = [], [], True
        for anyof in _kids(t, "AnyOf"):
            alts = [[self.match(m) for m in _kids(allof, "Match")] for allof in _kids(anyof, "AllOf")]
            if all(len(x) == 1 for x in alts) and len({x[0].attr for x in alts}) == 1 and all(x[0].op == "eq" for x in alts):
                vs = tuple(x[0].val for x in alts)
                conj_preds.append(Pred(alts[0][0].attr, "eq", vs[0]) if len(vs) == 1 else Pred(alts[0][0].attr, "in", vs))
            elif len(alts) == 1:
                conj_preds.extend(alts[0])
            else:
                ok = False
                exprs.append(OR(*[AND(*[("p", q) for q in x]) if len(x) > 1 else ("p", x[0]) for x in alts]))
        if ok:
            return conj_preds, None
        allx = [("p", q) for q in conj_preds] + exprs
        return None, (allx[0] if len(allx) == 1 else AND(*allx))

    # ------------------------------------------------------------ conditions
    def _arg_attr(self, e):
        if _tag(e) in ("AttributeDesignator", "AttributeSelector"):
            return self.attr(e)
        if _tag(e) == "Apply" and (_fn(e).endswith("one-and-only") or _fn(e).endswith("-bag")) and len(_kids(e)) == 1 \
                and _tag(_kids(e)[0]) in ("AttributeDesignator", "AttributeSelector"):
            return self.attr(_kids(e)[0])
        return None

    def expr(self, e):
        f = _fn(e)
        args = [c for c in e if _tag(c) in ("Apply", "AttributeValue", "AttributeDesignator", "AttributeSelector")]
        if f == "and":
            return AND(*[self.expr(x) for x in args])
        if f == "or":
            return OR(*[self.expr(x) for x in args])
        if f == "not":
            return NOT(self.expr(args[0]))
        if f.endswith("-equal") and len(args) == 2:
            a0, a1 = self._arg_attr(args[0]), self._arg_attr(args[1])
            a, lv = (a0, args[1]) if a0 else (a1, args[0])
            return p(a, "eq", self.lit(lv, a))
        for k, op in CMP.items():
            if f.endswith("-" + k):    # f(attr, value)
                a = self._arg_attr(args[0])
                if a is not None:
                    return p(a, op, self.lit(args[1], a))
                a = self._arg_attr(args[1])
                inv = {"gt": "lt", "lt": "gt", "ge": "le", "le": "ge"}[op]
                return p(a, inv, self.lit(args[0], a))
        if f.endswith("is-in"):
            a = self._arg_attr(args[1])
            return p(a, "eq", self.lit(args[0], a))
        if f.endswith("at-least-one-member-of"):
            bag = [x for x in args if _tag(x) == "Apply" and _fn(x).endswith("-bag")
                   and all(_tag(c) == "AttributeValue" for c in x)]
            other = [x for x in args if x not in bag]
            a = self._arg_attr(other[0])
            vs = tuple(self.lit(v, a) for v in _kids(bag[0], "AttributeValue"))
            return p(a, "eq", vs[0]) if len(vs) == 1 else p(a, "in", vs)
        raise ValueError(f"unsupported function {f}")

    # ------------------------------------------------------------ structure
    def rule(self, r, pid, i):
        tpreds, texpr = self.target(r.find("{*}Target"))
        c = r.find("{*}Condition")
        cond = self.expr([x for x in c if _tag(x) == "Apply"][0]) if c is not None else None
        if tpreds is None:
            cond = texpr if cond is None else AND(texpr, cond)
            tpreds = []
        return Rule(f"{pid}.R{i}", r.get("Effect"), tpreds, cond)

    def policy(self, e, k):
        pid = f"{self.prefix}.P{k}"
        tp, tx = self.target(e.find("{*}Target"))
        if tp is None:
            raise ValueError("non-conjunctive policy target")
        rules = [self.rule(r, pid, i + 1) for i, r in enumerate(_kids(e, "Rule"))]
        return Policy(pid, _alg(e.get("RuleCombiningAlgId")), tp, rules, {})

    def load(self, path, root_alg="DO"):
        root = ET.parse(path).getroot()
        if _tag(root) == "Policy":
            pols = [self.policy(root, 1)]
            alg, tgt = root_alg, []
        else:
            pols = [self.policy(x, i + 1) for i, x in enumerate(_kids(root, "Policy"))]
            alg = _alg(root.get("PolicyCombiningAlgId"))
            tp, _ = self.target(root.find("{*}Target"))
            tgt = tp or []
        return PolicySet(self.prefix, alg, tgt, pols)

    def domains(self):
        dom = {}
        for a in sorted(self.vals):
            t = self.types.get(a, "string")
            vs = self.vals[a]
            if t == "boolean":
                dom[a] = ["true", "false"]
            elif t == "integer":
                dom[a] = sorted({x + d for x in vs for d in (-1, 0, 1)})
            else:
                dom[a] = sorted(vs) + ["_other"]
        return dom


def import_policies(paths, prefix, root_alg="DO"):
    """One or several XACML files -> (PolicySet, domains). Several Policy files
    are combined under one root with root_alg."""
    imp = Importer(prefix)
    if len(paths) == 1:
        ps = imp.load(paths[0], root_alg)
    else:
        pols = []
        for path in paths:
            sub = imp.load(path, root_alg)
            for pol in sub.policies:
                k = len(pols) + 1
                pid = f"{prefix}.P{k}"
                for i, r in enumerate(pol.rules):
                    r.id = f"{pid}.R{i + 1}"
                pol.id = pid
                pols.append(pol)
        ps = PolicySet(prefix, root_alg, [], pols)
    return ps, imp.domains()
