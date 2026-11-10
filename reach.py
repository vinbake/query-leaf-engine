"""
reach.py — "who comes to the park, and from where": an optional age band and postcode, kept as monthly tallies.

This is the ONE place the park keeps anything a visitor chose to say about themselves, and it is walled off on purpose.
Approved by Phil 2026-11-11 (Option A); the plan (2.7) and Standing Constraint 3 carry the matching wording.

The rules, each one tested in test_reach.py:
  - only a tally: (month, postcode, age band) -> a number. No session, no prompt code, no visit, no day, no IP, no
    user agent, no date of birth. Nothing here can be joined to anything else in the engine.
  - the visitor chose to give it. The park sends nothing unless the visitor typed a postcode or tapped an age band.
  - under-18s: the age band is counted, the postcode is NEVER stored (a postcode plus a child's age band can point to
    one person). The engine enforces this itself; it does not trust the park.
  - small areas stay hidden: the read-out shows an area or an age band only once at least MIN_GROUP visitors are in
    it. A postcode with three visitors tells you nothing and exposes people.
  - rows marked qa are test traffic and never reach the read-out.
  - once per phone per month is kept by the phone (the engine has no way to know who is who, by design).

Storage: Postgres when DATABASE_URL is set (the same database as the counts), otherwise in memory (local tests only).
"""
import os
import re
import threading

import counts

BANDS = ("under-12", "12-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65-plus")
UNDER_18 = ("under-12", "12-17")
try:
    MIN_GROUP = max(2, int(os.environ.get("REACH_MIN_GROUP", "10")))
except ValueError:
    MIN_GROUP = 10

# Australian postcode ranges by state or territory (Australia Post). PO-box ranges are included.
_RANGES = (
    ("ACT", 200, 299), ("ACT", 2600, 2618), ("ACT", 2900, 2920),
    ("NSW", 1000, 2599), ("NSW", 2619, 2898), ("NSW", 2921, 2999),
    ("NT", 800, 999), ("VIC", 3000, 3999), ("VIC", 8000, 8999),
    ("QLD", 4000, 4999), ("QLD", 9000, 9999),
    ("SA", 5000, 5999), ("WA", 6000, 6999), ("TAS", 7000, 7999),
)

_lock = threading.Lock()
_mem = {}   # (month, postcode, band, qa) -> n


def state_of(postcode):
    """The state or territory a 4-digit postcode belongs to, or None if it is not an Australian postcode."""
    if not re.fullmatch(r"\d{4}", postcode or ""):
        return None
    n = int(postcode)
    for st, lo, hi in _RANGES:
        if lo <= n <= hi:
            return st
    return None


def init():
    if not counts.USE_DB:
        return
    try:
        with counts._db() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS reach_counts ("
                "month text NOT NULL, postcode text NOT NULL DEFAULT '', band text NOT NULL DEFAULT '', "
                "qa boolean NOT NULL DEFAULT false, n integer NOT NULL DEFAULT 0, "
                "PRIMARY KEY (month, postcode, band, qa))")
    except Exception as e:
        counts._err("reach init", e)


def record(postcode, band, qa=False):
    """Add one to the tally for this month. Returns (ok, reason).

    A postcode that is not a real Australian one, or a band not on the list, is dropped, not stored. If nothing usable
    is left there is nothing to count. Under-18s never have a postcode stored."""
    pc = str(postcode).strip() if postcode is not None else ""
    pc = pc if state_of(pc) else ""
    bd = band if band in BANDS else ""
    if bd in UNDER_18:
        pc = ""
    if not pc and not bd:
        return False, "nothing to count"
    month = counts.today().strftime("%Y-%m")
    qa = bool(qa)
    if counts.USE_DB:
        try:
            with counts._db() as c:
                c.execute(
                    "INSERT INTO reach_counts (month, postcode, band, qa, n) VALUES (%s, %s, %s, %s, 1) "
                    "ON CONFLICT (month, postcode, band, qa) DO UPDATE SET n = reach_counts.n + 1",
                    (month, pc, bd, qa))
            return True, ""
        except Exception as e:
            counts._err("reach", e)
            return False, "store error"
    with _lock:
        key = (month, pc, bd, qa)
        _mem[key] = _mem.get(key, 0) + 1
    return True, ""


def _rows():
    if counts.USE_DB:
        with counts._db() as c:
            return c.execute("SELECT month, postcode, band, n FROM reach_counts WHERE qa = false").fetchall()
    with _lock:
        return [(m, p, b, n) for (m, p, b, q), n in _mem.items() if not q]


def readout(min_group=None):
    """Counts only, with small groups hidden. Never lists a postcode, state or age band below the minimum."""
    mg = MIN_GROUP if min_group is None else max(2, int(min_group))
    try:
        rows = _rows()
    except Exception as e:
        counts._err("reach readout", e)
        return {"ok": False, "error": "store error"}
    by_pc, by_state, by_band, by_month = {}, {}, {}, {}
    for month, pc, bd, n in rows:
        by_month[month] = by_month.get(month, 0) + n
        if bd:
            by_band[bd] = by_band.get(bd, 0) + n
        if pc:
            by_pc[pc] = by_pc.get(pc, 0) + n
            st = state_of(pc)
            by_state[st] = by_state.get(st, 0) + n

    def shown(d):
        return {k: v for k, v in sorted(d.items()) if v >= mg}

    hidden_pc = sum(1 for v in by_pc.values() if v < mg)
    return {"ok": True, "min_group": mg, "counted_from": min(by_month) if by_month else None,
            "by_month": {m: n for m, n in sorted(by_month.items()) if n >= mg},
            "by_band": shown(by_band), "by_state": shown(by_state), "by_postcode": shown(by_pc),
            "postcodes_hidden_for_size": hidden_pc,
            "note": "Tallies of what visitors chose to give, once per phone per month. Not unique people. Areas below the minimum are hidden."}
