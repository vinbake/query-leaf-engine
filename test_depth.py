"""
Depth and D42 checks (2026-11-15, Option A of the question-layering review).

- No tree hands over after a single tap.
- Every path ends at a pinhole, a hand-over, or the crisis route: no dead ends.
- The new and reworded pinhole lines are questions (D40, Principle 6).
- A pinhole with a "professional" key puts the question-list ask into the prompt (D42);
  one without it keeps "pick one step I can take this week".

Run: python3 test_depth.py
"""
import collections

from query_engine import QueryEngine, Answer, Tree
from trees_config import load_trees_config
from au_context import load_au_context

TREES = load_trees_config()
META = {"question", "type", "answers", "routes", "pinholes", "professional", "stops_narrowing",
        "default_pinhole", "prompt", "openings", "safety_check", "note", "crisis_detection"}

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL") + " | " + name + (" | " + detail if detail and not ok else ""))


def walk(tree):
    cfg = TREES[tree]
    paths = []

    def go(node_id, depth, trail):
        node = cfg.get(node_id)
        if not isinstance(node, dict) or "answers" not in node:
            paths.append((depth - 1, trail, "DEAD:" + node_id))
            return
        for a in node["answers"]:
            t = trail + [(node_id, a)]
            if a in node.get("pinholes", {}) or node.get("stops_narrowing"):
                paths.append((depth, t, "PINHOLE"))
                continue
            nxt = node.get("routes", {}).get(a)
            if nxt is None:
                paths.append((depth, t, "NONE"))
            elif nxt.startswith("RECONCILE") or nxt == "PINHOLE":
                paths.append((depth, t, nxt))
            else:
                go(nxt, depth + 1, t)

    go("Q1", 1, [])
    return paths


# 1. depth and dead ends
for tree in TREES:
    paths = walk(tree)
    hist = collections.Counter(p[0] for p in paths)
    ones = [p for p in paths if p[0] <= 1]
    check(f"{tree}: no one-tap handoff", not ones, str([p[1] for p in ones]))
    dead = [p for p in paths if p[2] == "NONE" or (p[2].startswith("DEAD") and "CRISIS" not in p[2])]
    check(f"{tree}: no dead ends", not dead, str([(p[1], p[2]) for p in dead]))
    print(f"      {tree}: {len(paths)} paths, taps before handoff {dict(sorted(hist.items()))}")

# 2. new and reworded lines are questions
NEW_NODES = {"wattle": ["Q3.Weight", "Q3"], "gum": ["Q4"], "acacia": ["Q3.Focus", "Q3.Anxious"], "pine": ["Q4.Enough"]}
for tree, nodes in NEW_NODES.items():
    for n in nodes:
        pins = TREES[tree][n].get("pinholes", {})
        bad = [a for a, txt in pins.items() if not txt.rstrip().endswith("?")]
        check(f"{tree} {n}: pinhole lines are questions", pins and not bad, str(bad))

# 3. D42 ask in the prompt
def run(tree, steps):
    e = QueryEngine(TREES, load_au_context())
    last = None
    for node, text in steps:
        last = e.add_answer(Answer(node, tree, text))
    return e, last


PRO_PATHS = [
    (Tree.WATTLE, [("Q1", "Weight"), ("Q2.Weight", "How I feel in my body"), ("Q3.Weight", "What I eat")], "Dietitian"),
    (Tree.WATTLE, [("Q1", "Pain"), ("Q3", "Not yet")], "my GP"),
    (Tree.GUM, [("Q1", "I don't feel heard"), ("Q2.Heard", "They listen, then nothing changes"),
                ("Q4", "They know but nothing changes")], "relationship counsellor"),
    (Tree.ACACIA, [("Q1", "I can't focus"), ("Q2.Focus", "One thing I keep avoiding"),
                   ("Q3.Focus", "Understanding why I feel this way")], "my GP"),
]
for tree, steps, label in PRO_PATHS:
    e, last = run(tree, steps)
    ok = last == "PINHOLE"
    txt = e.finalize_prompt(tree).prompt_text if ok else ""
    check(f"D42 {tree.value} {steps[-1][1]!r}: question list for the {label}",
          ok and "questions to take to my" in txt and label in txt and "pick one step" not in txt,
          f"last={last} text={txt[:160]!r}")

e, last = run(Tree.PINE, [("Q1", "I'm doing everything but it doesn't feel enough"),
                          ("Q2.Enough", "My family"), ("Q4.Enough", "To prove I can")])
txt = e.finalize_prompt(Tree.PINE).prompt_text if last == "PINHOLE" else ""
check("No professional: generic ask unchanged", last == "PINHOLE" and "pick one step I can take this week" in txt
      and "questions to take to my" not in txt, f"last={last}")

# 4. the Oak spec path keeps its two asks and the step ask (no professional set on Oak yet)
e, last = run(Tree.OAK, [("Q1", "Income too low"), ("Q2.Income", "Irregular/gig work")])
txt = e.finalize_prompt(Tree.OAK).prompt_text if last == "PINHOLE" else ""
check("Oak spec prompt: (a) (b) (c) with the step ask", "(c) pick one step I can take this week" in txt, txt[:200])

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n{passed}/{len(results)} passed")
raise SystemExit(0 if passed == len(results) else 1)
