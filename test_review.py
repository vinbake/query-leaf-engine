"""
Locked review read-out tests (counts.review and /api/review in app.py).

Run:  python3 test_review.py
In-memory store unless DATABASE_URL is set. With DATABASE_URL it EMPTIES interactions first:
throwaway database only (set ALLOW_TRUNCATE=yes). Every check reads the review read-out, not a reply.

What it guards:
  - the review groups the "what was missing" text by the question path that drew it, worst first
  - qa (test) rows stay out unless include_qa is asked for
  - the window is by fb_day; feedback outside it is not shown
  - the route is locked: no key, or a wrong key, is 'not found' — the endpoint never reveals itself
  - the public metrics read-out still never carries the feedback text
"""
import datetime
import json
import os
import sys

import counts
import app

_now = {"day": datetime.date(2026, 11, 14)}
counts.today = lambda: _now["day"]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "|", name, ("| " + detail if detail and not ok else ""))


def reset():
    counts.init()
    if counts.USE_DB:
        if os.environ.get("ALLOW_TRUNCATE") != "yes":
            sys.exit("Refusing to empty interactions: set ALLOW_TRUNCATE=yes on a throwaway database.")
        with counts._db() as c:
            c.execute("TRUNCATE interactions")
    counts._mem_interactions.clear()


def add(code, tree, path, root_cause, rating, text=None, qa=False, day=None):
    """One interaction plus one feedback answer, dated by fb_day = day (default today)."""
    if day is not None:
        _now["day"] = day
    counts.record_interaction(code, tree, path, root_cause, qa=qa)
    counts.record_feedback(code, rating, text)
    _now["day"] = datetime.date(2026, 11, 14)


reset()

# Two answers on the SAME Oak node, plus a Gum node, a plain "yes", a qa row, and an out-of-window row.
add("OAKAAA", "oak", "Q1 > Q2.Income", "Income irregularity", "partly", "needs budgeting steps")
add("OAKBBB", "oak", "Q1 > Q2.Income", "Income irregularity", "no", "didn't fit gig work")
add("GUMAAA", "gum", "Q1 > Q2.Distant", "Drifting apart", "partly", "too generic")
add("YESONE", "oak", "Q1 > Q2.Spending", "Lifestyle creep", "yes")
add("QAONE", "oak", "Q1 > Q2.Income", "Income irregularity", "partly", "selftest note", qa=True)
add("OLDONE", "gum", "Q1 > Q2.Fighting", "Same fight", "no", "old feedback", day=datetime.date(2026, 11, 1))

# ---------- the read-out ----------
r = counts.review()  # default window: the last 7 days, 2026-11-08..2026-11-14
check("default window is the last 7 days", r["from"] == "2026-11-08" and r["to"] == "2026-11-14", str((r.get("from"), r.get("to"))))
check("totals count real feedback only", r["totals"] == {"feedback": 4, "yes": 1, "partly": 2, "no": 1, "with_text": 3}, str(r["totals"]))

nodes = {(n["tree"], n["path"]): n for n in r["nodes"]}
oak = nodes.get(("oak", "Q1 > Q2.Income"), {})
check("same node groups both answers", oak.get("feedback") == 2 and oak.get("partly") == 1 and oak.get("no") == 1, str(oak))
texts = sorted(note["text"] for note in oak.get("notes", []))
check("the node carries the verbatim 'what was missing' text", texts == ["didn't fit gig work", "needs budgeting steps"], str(texts))
check("a 'yes' is counted but leaves no note", nodes.get(("oak", "Q1 > Q2.Spending"), {}).get("notes") == [], str(nodes.get(("oak", "Q1 > Q2.Spending"))))
check("worst node (most partly+no) is listed first", r["nodes"][0]["path"] == "Q1 > Q2.Income", r["nodes"][0]["path"])
check("the out-of-window row is not shown", not any("old feedback" in json.dumps(n) for n in r["nodes"]))
check("the qa note is not shown by default", not any("selftest note" in json.dumps(n) for n in r["nodes"]))

# include_qa brings the test row in
rq = counts.review(include_qa=True)
check("include_qa adds the qa feedback", rq["totals"]["feedback"] == 5 and rq["totals"]["with_text"] == 4, str(rq["totals"]))
check("include_qa shows the qa note", any("selftest note" in json.dumps(n) for n in rq["nodes"]))

# a wider window reaches the older row
rw = counts.review(frm="2026-10-01", to="2026-11-14")
check("a wider window reaches the older feedback", any("old feedback" in json.dumps(n) for n in rw["nodes"]))
check("a reversed window is swept straight", counts.review(frm="2026-11-14", to="2026-11-08")["from"] == "2026-11-08")

# ---------- the lock ----------
app.REVIEW_KEY = ""
check("no key configured => endpoint is not found", app.review_route("anything")[0] == 404)
app.REVIEW_KEY = "s3cret-review-key"
check("wrong key => not found (never revealed)", app.review_route("nope")[0] == 404)
check("empty key => not found", app.review_route("")[0] == 404 and app.review_route(None)[0] == 404)
code, obj = app.review_route("s3cret-review-key")
check("right key => the review read-out", code == 200 and obj["ok"] is True and "nodes" in obj)
code, obj = app.review_route("s3cret-review-key", frm="2026-10-01", to="2026-11-14", include_qa=True)
check("right key passes the window and include_qa through", code == 200 and any("old feedback" in json.dumps(n) for n in obj["nodes"]))

# ---------- the public read-out must still carry no text ----------
dump = json.dumps(counts.metrics())
check("metrics() exposes no feedback text and no fb_text field",
      "needs budgeting steps" not in dump and "didn't fit gig work" not in dump and "fb_text" not in dump)

bad = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
