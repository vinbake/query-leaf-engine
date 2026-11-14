"""
Acacia D38 spec tests (trees_config.json acacia + au_context acacia catalogue).

Run:  python3 test_acacia.py
Drives each reachable Acacia pinhole through the real engine and checks the handoff
prompt is the D38 spec prompt — opening in the visitor's voice, the pinhole formulation,
the "not general wellbeing tips" line, and every named service resolved from the catalogue —
and never the generic fallback.
"""
import sys

from trees_config import load_trees_config
from au_context import load_au_context
from query_engine import QueryEngine, Answer, Tree

TREES = load_trees_config()
AU = load_au_context()
ACA = TREES["acacia"]
CAT = AU["acacia"].get("catalogue", {})
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "|", name, ("| " + detail if detail and not ok else ""))


# 1. every service key used in any Acacia spec resolves in the catalogue (no silent drops)
unresolved = set()
spec_count = 0
for node, cfg in ACA.items():
    if not isinstance(cfg, dict):
        continue
    for ans, spec in (cfg.get("prompt") or {}).items():
        spec_count += 1
        for s in spec["services"]:
            if s not in CAT:
                unresolved.add((node, ans, s))
check("every spec service key resolves in the catalogue", not unresolved, str(unresolved))
check("all 10 pinholes carry a spec", spec_count == 10, f"found {spec_count}")

# 2. tree-level D38 fields present
check("tree-level not_generic / default_opening / Q1 openings present",
      ACA.get("not_generic") and ACA.get("default_opening") and ACA["Q1"].get("openings"))


def finalize(steps):
    eng = QueryEngine(TREES, AU)
    r = None
    for node, ans in steps:
        r = eng.add_answer(Answer(node_id=node, tree=Tree.ACACIA, user_response=ans))
    assert r == "PINHOLE", f"expected PINHOLE, got {r!r} for {steps}"
    return eng.finalize_prompt(Tree.ACACIA).prompt_text


Q3 = [("Q1", "I can't focus")]
Q5 = [("Q1", "Everything feels too much"), ("Q4", "Yes, safe")]
CASES = [
    ("Q2.Sleep/Dread", [("Q1", "I can't sleep"), ("Q2.Sleep", "Dread about something specific")],
     "I can't sleep", ["gp_mhtp", "beyond_blue", "lifeline"]),
    ("Q2.Wired/Out of nowhere", [("Q1", "I'm exhausted but wired"), ("Q2.Wired", "Out of nowhere")],
     "I'm exhausted but wired", ["gp", "healthdirect", "lifeline"]),
    ("Q3/Rest", Q3 + [("Q3", "Rest")], "I can't focus", ["personal_leave", "gp_mhtp", "lifeline"]),
    ("Q3/Someone to talk to", Q3 + [("Q3", "Someone to talk to")], "I can't focus",
     ["beyond_blue", "medicare_mhc", "gp_mhtp", "mindspot", "headspace", "lifeline"]),
    ("Q3/A break", Q3 + [("Q3", "A break")], "I can't focus", ["personal_leave", "flex_request", "eap", "gp"]),
    ("Q3/Fixing", Q3 + [("Q3", "Fixing the thing that's stressing me")], "I can't focus",
     ["gp_mhtp", "beyond_blue", "lifeline"]),
    ("Q3/Understanding", Q3 + [("Q3", "Understanding why I feel this way")], "I can't focus",
     ["gp_mhtp", "beyond_blue", "mindspot", "lifeline"]),
    ("Q5/Temporary", Q5 + [("Q5", "Temporary")], "everything feels like too much at the moment",
     ["gp_mhtp", "beyond_blue", "lifeline"]),
    ("Q5/Ongoing", Q5 + [("Q5", "Ongoing")], "everything feels like too much at the moment",
     ["gp_mhtp", "flex_request", "eap", "medicare_mhc", "beyond_blue", "lifeline"]),
    ("Q5/Stuck", Q5 + [("Q5", "It was temporary but now it's stuck")], "everything feels like too much at the moment",
     ["gp_mhtp", "medicare_mhc", "beyond_blue", "lifeline"]),
]

for label, steps, opening, keys in CASES:
    p = finalize(steps)
    spec_path = "do not ask me any clarifying questions" in p and "What I told the Query Leaf:" in p
    not_generic = "Work on that root cause first, not general wellbeing tips" in p
    opening_ok = f"I'm in Australia and {opening}." in p
    services_ok = all(CAT[k] in p for k in keys)
    no_fallback = "What I described to the Query Leaf:" not in p
    check(f"{label}: D38 spec prompt",
          spec_path and not_generic and opening_ok and services_ok and no_fallback,
          f"spec={spec_path} notgeneric={not_generic} opening={opening_ok} services={services_ok} nofallback={no_fallback}")

# 3. the safety number is in every Acacia prompt (Option B: lifeline in each spec's services)
with_lifeline = sum(1 for _, steps, _, _ in CASES if "13 11 14" in finalize(steps))
check("Lifeline 13 11 14 appears in every Acacia prompt", with_lifeline == len(CASES), f"{with_lifeline}/{len(CASES)}")

# 4. crisis route still fires and never becomes a prompt
eng = QueryEngine(TREES, AU)
r = None
for node, ans in [("Q1", "Everything feels too much"), ("Q4", "I'm not sure")]:
    r = eng.add_answer(Answer(node_id=node, tree=Tree.ACACIA, user_response=ans))
check("unsafe Q4 answer routes to crisis, no pinhole prompt", r == "CRISIS_ROUTE")

bad = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
