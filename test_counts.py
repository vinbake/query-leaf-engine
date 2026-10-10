"""
Gate counting tests (counts.py and its routes in app.py).

Run:  python3 test_counts.py
Uses the in-memory store unless DATABASE_URL is set. With DATABASE_URL it
EMPTIES the two counting tables first, so point it at a throwaway database only.
Every check reads the stored record or the metrics read-out, never a reply alone.
"""
import datetime
import json
import os
import sys

import counts
import app

D0 = datetime.date(2026, 10, 14)
_now = {"day": D0}
counts.today = lambda: _now["day"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "|", name, ("| " + detail if detail and not ok else ""))


def day(offset):
    _now["day"] = D0 + datetime.timedelta(days=offset)
    return _now["day"]


def reset():
    app._db_init()
    counts.init()
    if counts.USE_DB:
        if os.environ.get("ALLOW_TRUNCATE") != "yes":
            sys.exit("Refusing to empty the counting tables: set ALLOW_TRUNCATE=yes on a throwaway database.")
        with counts._db() as c:
            c.execute("TRUNCATE visit_counts, interactions")
    else:
        counts._mem_visits.clear()
        counts._mem_interactions.clear()


def prompt(tree, steps, qa=False, device="phone"):
    _, r = app.start({"tree": tree})
    sid = r["session_id"]
    for node, text in steps:
        app.answer({"session_id": sid, "tree": tree, "node_id": node, "answer_text": text})
    status, f = app.finalize({"session_id": sid, "tree": tree, "qa": qa, "device": device})
    return sid, f


OAK = [("Q1", "Income too low"), ("Q2.Income", "Irregular/gig work")]
WATTLE = [("Q1", "Energy/tiredness"), ("Q2.Energy", "Recently"), ("Q2.Energy.Recent", "Stress increased")]


def main():
    reset()
    print("store:", "postgres" if counts.USE_DB else "memory")

    # ---------- G1: return rate ----------
    day(0)
    for _ in range(10):
        app.visit({"kind": "first"})
    app.visit({"kind": "first", "qa": True})
    _, r = app.visit({"kind": "returned", "first_day": D0.isoformat()})
    check("G1 a 'returned' on the first day is refused", r["ok"] is False and r["reason"] == "same day")
    _, r = app.visit({"kind": "sideways"})
    check("G1 unknown kind refused", r["ok"] is False)
    _, r = app.visit({"kind": "daily", "first_day": "2020-01-01"})
    check("G1 a first day before the park opened is refused", r["ok"] is False)

    day(1)
    for _ in range(3):
        app.visit({"kind": "returned", "first_day": D0.isoformat()})
    app.visit({"kind": "returned", "first_day": D0.isoformat(), "qa": True})
    day(3)
    for _ in range(2):
        app.visit({"kind": "first"})
    day(6)
    m = counts.metrics()
    check("G1 nobody is eligible before 7 days", m["g1"]["eligible_first_visits"] == 0 and m["g1"]["rate_percent"] is None,
          json.dumps(m["g1"]))
    day(7)
    m = counts.metrics()
    check("G1 day 7: 3 of 10 returned = 30.0%", m["g1"] ["eligible_first_visits"] == 10 and m["g1"]["returned"] == 3
          and m["g1"]["rate_percent"] == 30.0, json.dumps(m["g1"]))
    day(9)
    app.visit({"kind": "returned", "first_day": D0.isoformat()})
    day(10)
    app.visit({"kind": "returned", "first_day": (D0 + datetime.timedelta(days=3)).isoformat()})
    m = counts.metrics()
    check("G1 day 10: 5 of 12 returned = 41.7%", m["g1"]["eligible_first_visits"] == 12 and m["g1"]["returned"] == 5
          and m["g1"]["rate_percent"] == 41.7, json.dumps(m["g1"]))
    m7 = counts.metrics((D0 + datetime.timedelta(days=7)).isoformat())
    check("G1 an earlier reading is unchanged by later returns", m7["g1"]["returned"] == 3
          and m7["g1"]["eligible_first_visits"] == 10, json.dumps(m7["g1"]))
    check("G1 test visits are counted apart", m["qa"]["visits"] == 2 and m["visits"]["first"] == 12, json.dumps(m["qa"]))

    # ---------- G2 and G3: prompts used, feedback ----------
    day(10)
    base = counts.metrics()["totals"]["prompts"]
    codes = []
    for _ in range(4):
        _, f = prompt("oak", OAK)
        codes.append(f["share_code"])
    _, fw = prompt("wattle", WATTLE, device="desktop")
    codes.append(fw["share_code"])
    _, fq = prompt("oak", OAK, qa=True)

    app.tap(codes[0], {"type": "copy"})
    app.tap(codes[0], {"type": "copy"})            # twice, still one use
    app.tap(codes[1], {"type": "open_ai"})
    app.tap(codes[2], {"type": "share"})           # share alone is not a use
    app.tap(codes[4], {"type": "copy"})
    app.tap(codes[4], {"type": "open_ai"})
    app.tap(fq["share_code"], {"type": "copy"})    # test row
    app.tap(codes[2], {"type": "share_open"})
    app.tap(codes[2], {"type": "share_open"})
    status, _ = app.tap(codes[0], {"type": "delete everything"})
    check("G2 unknown tap type refused", status == 400)

    long_text = "The questions never asked about my shifts. " * 30
    app.feedback(codes[0], {"rating": "yes", "text": "ignored for a yes"})
    app.feedback(codes[1], {"rating": "partly", "text": long_text})
    app.feedback(codes[4], {"rating": "didnt_work"})                 # old option name
    app.feedback(fq["share_code"], {"rating": "no", "text": "qa text"})
    status, _ = app.feedback(codes[3], {"rating": "five stars"})
    check("G3 unknown rating refused", status == 400)
    status, _ = app.feedback("ZZZZZ9", {"rating": "yes"})
    check("G3 unknown code refused", status == 404)

    m = counts.metrics()
    t = m["totals"]
    check("G2 5 prompts, 3 used = 60.0%", t["prompts"] - base == 5 and m["g2"]["used"] == 3
          and m["g2"]["rate_percent"] == 60.0, json.dumps(m["g2"]))
    check("G2 share and share opens counted apart", t["shared"] == 1 and t["share_opens"] == 2 and t["copied"] == 2
          and t["opened_ai"] == 2, json.dumps(t))
    check("G3 3 of 5 gave feedback = 60.0%", m["g3"]["feedback"] == 3 and m["g3"]["interactions"] == 5
          and m["g3"]["rate_percent"] == 60.0 and t["yes"] == 1 and t["partly"] == 1 and t["no"] == 1, json.dumps(m["g3"]))
    check("By tree and by device", m["by_tree"]["oak"]["prompts"] == 4 and m["by_tree"]["wattle"]["used"] == 1
          and m["by_device"]["phone"]["prompts"] == 4 and m["by_device"]["desktop"]["prompts"] == 1,
          json.dumps(m["by_tree"]))
    node = next(n for n in m["nodes"] if n["tree"] == "oak")
    check("Per-node counts for the Monday review", node["path"] == "Q1 > Q2.Income" and node["interactions"] == 4
          and node["used"] == 2 and node["yes"] == 1 and node["partly"] == 1, json.dumps(node))
    check("Test rows are in no gate number", m["qa"]["interactions"] == 1 and m["qa"]["feedback"] == 1, json.dumps(m["qa"]))

    row0, row1, row4 = (counts.get_interaction(c) for c in (codes[0], codes[1], codes[4]))
    check("Stored: a yes keeps no text", row0["fb_rating"] == "yes" and row0["fb_text"] is None)
    check("Stored: text capped at 500 characters", row1["fb_rating"] == "partly" and len(row1["fb_text"]) == 500)
    check("Stored: old option name mapped", row4["fb_rating"] == "no" and row4["copied"] and row4["opened_ai"])
    check("Stored record carries no visitor detail", set(row0) == set(counts._COLS), ", ".join(sorted(row0)))
    dumped = json.dumps(m)
    check("The read-out holds no feedback text", "shifts" not in dumped and "qa text" not in dumped)

    # ---------- finalize twice, crisis, days ----------
    sid, f1 = prompt("oak", OAK)
    _, f2 = app.finalize({"session_id": sid, "tree": "oak"})
    m2 = counts.metrics()
    check("A reload does not count a second prompt", f1["share_code"] == f2["share_code"]
          and m2["totals"]["prompts"] == t["prompts"] + 1)

    before = counts.metrics()["totals"]["interactions"]
    _, r = app.start({"tree": "acacia"})
    sid = r["session_id"]
    app.answer({"session_id": sid, "tree": "acacia", "node_id": "Q1", "answer_text": "Everything feels too much"})
    _, a = app.answer({"session_id": sid, "tree": "acacia", "node_id": "Q4", "answer_text": "I'm not sure"})
    _, fc = app.finalize({"session_id": sid, "tree": "acacia"})
    check("A crisis route is never recorded", a.get("status") == "CRISIS_ROUTE" and fc.get("status") == "CRISIS_ROUTE"
          and "share_code" not in fc and counts.metrics()["totals"]["interactions"] == before)

    day(11)
    _, f = prompt("oak", OAK)
    check("The day stored is the park's day", counts.get_interaction(f["share_code"])["day"] == D0 + datetime.timedelta(days=11))
    check("A reading for an earlier day leaves later rows out",
          counts.metrics((D0 + datetime.timedelta(days=10)).isoformat())["totals"]["prompts"] == m2["totals"]["prompts"])

    # ---------- the engine's own selftest ----------
    before_st = counts.metrics()
    st = app.selftest()
    for r in st["results"]:
        check("selftest " + r["test"], r["status"] == "PASS", r.get("detail", ""))
    after = counts.metrics()
    check("selftest changes no gate number and leaves no test prompts behind",
          after["totals"] == before_st["totals"] and after["g1"] == before_st["g1"]
          and after["qa"]["interactions"] == before_st["qa"]["interactions"])

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
