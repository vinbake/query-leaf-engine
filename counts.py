"""
counts.py — anonymous counting for the Week 12 gates (G1–G4).

The method is set out in the project's gate tracker. The rules it must obey
(plan Standing Constraint 3, decision D12):

  - no visitor identifier of any kind: no ID, no IP address, no user agent
  - nothing a visitor said about themselves. The optional feedback text is a
    response about a question, capped at 500 characters
  - times are kept to the day (PARK_TZ, default Australia/Melbourne)
  - rows marked qa are test traffic and never reach a gate number

A crisis route never reaches finalize, so it is never recorded here.

Storage: Postgres when DATABASE_URL is set (the same database as the share
codes), otherwise in memory (local tests only, lost on restart).
"""
import datetime
import os
import threading

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

DATABASE_URL = os.environ.get("DATABASE_URL", "")
try:
    import psycopg
except ImportError:
    psycopg = None
USE_DB = bool(DATABASE_URL and psycopg)

PARK_TZ = os.environ.get("PARK_TZ", "Australia/Melbourne")
PARK_OPENED = datetime.date(2026, 10, 1)   # no first-visit date can be earlier
RETURN_WINDOW_DAYS = 7                     # G1: a browser needs a week to come back
MAX_FEEDBACK_CHARS = 500

VISIT_KINDS = ("first", "returned", "daily")
TAP_COLUMNS = {"copy": "copied", "open_ai": "opened_ai", "share": "shared"}
RATINGS = {"yes": "yes", "partly": "partly", "no": "no",
           # the engine's older option names, kept as aliases
           "brilliant_answer": "yes", "something_missing": "partly", "didnt_work": "no"}
DEVICES = ("phone", "desktop")

_lock = threading.Lock()
_mem_visits = {}        # (day, first_day, kind, qa) -> n
_mem_interactions = {}  # code -> dict


def today():
    """The park's current day."""
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(PARK_TZ)).date()
        except Exception:
            pass
    return datetime.datetime.utcnow().date()


def _db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def _err(where, e):
    print("ERROR counts", where, type(e).__name__, flush=True)


def init():
    if not USE_DB:
        return
    try:
        with _db() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS visit_counts ("
                "day date NOT NULL, first_day date NOT NULL, kind text NOT NULL, "
                "qa boolean NOT NULL DEFAULT false, n integer NOT NULL DEFAULT 0, "
                "PRIMARY KEY (day, first_day, kind, qa))")
            c.execute(
                "CREATE TABLE IF NOT EXISTS interactions ("
                "code text PRIMARY KEY, day date NOT NULL, kind text NOT NULL DEFAULT 'prompt', "
                "tree text NOT NULL, path text NOT NULL DEFAULT '', root_cause text NOT NULL DEFAULT '', "
                "device text NOT NULL DEFAULT '', qa boolean NOT NULL DEFAULT false, "
                "copied boolean NOT NULL DEFAULT false, opened_ai boolean NOT NULL DEFAULT false, "
                "shared boolean NOT NULL DEFAULT false, share_opens integer NOT NULL DEFAULT 0, "
                "fb_rating text, fb_text text, fb_day date)")
    except Exception as e:
        _err("init", e)


def _parse_day(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except Exception:
        return None


# ---------- writes ----------

def record_visit(kind, first_day, qa=False):
    """Count one visit message. Returns (ok, reason).

    first    the browser's first ever visit; its first day is today
    returned the first time that browser comes back on a later day
    daily    once per browser per day
    """
    if kind not in VISIT_KINDS:
        return False, "unknown kind"
    day = today()
    if kind == "first":
        fd = day
    else:
        fd = _parse_day(first_day)
        if fd is None or fd < PARK_OPENED:
            return False, "bad first_day"
        if fd > day:
            fd = day
        if kind == "returned" and fd >= day:
            return False, "same day"      # not a return yet; the browser tries again later
    qa = bool(qa)
    if USE_DB:
        try:
            with _db() as c:
                c.execute(
                    "INSERT INTO visit_counts (day, first_day, kind, qa, n) VALUES (%s, %s, %s, %s, 1) "
                    "ON CONFLICT (day, first_day, kind, qa) DO UPDATE SET n = visit_counts.n + 1",
                    (day, fd, kind, qa))
            return True, ""
        except Exception as e:
            _err("visit", e)
            return False, "store error"
    with _lock:
        key = (day, fd, kind, qa)
        _mem_visits[key] = _mem_visits.get(key, 0) + 1
    return True, ""


def record_interaction(code, tree, path, root_cause, device="", qa=False, kind="prompt"):
    """One row per result shown. Keyed by the prompt code, which names a prompt, not a person."""
    device = device if device in DEVICES else ""
    row = {"code": code, "day": today(), "kind": kind, "tree": tree, "path": path[:300],
           "root_cause": root_cause[:300], "device": device, "qa": bool(qa),
           "copied": False, "opened_ai": False, "shared": False, "share_opens": 0,
           "fb_rating": None, "fb_text": None, "fb_day": None}
    if USE_DB:
        try:
            with _db() as c:
                c.execute(
                    "INSERT INTO interactions (code, day, kind, tree, path, root_cause, device, qa) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (code) DO NOTHING",
                    (code, row["day"], kind, tree, row["path"], row["root_cause"], device, row["qa"]))
            return True
        except Exception as e:
            _err("interaction", e)
            return False
    with _lock:
        _mem_interactions.setdefault(code, row)
    return True


def record_tap(code, tap):
    """copy / open_ai / share set a flag once; share_open adds one. Returns (ok, reason)."""
    if tap not in TAP_COLUMNS and tap != "share_open":
        return False, "unknown tap"
    if USE_DB:
        try:
            with _db() as c:
                if tap == "share_open":
                    cur = c.execute("UPDATE interactions SET share_opens = share_opens + 1 WHERE code = %s", (code,))
                else:
                    col = TAP_COLUMNS[tap]          # from a fixed list, never from the request
                    cur = c.execute(f"UPDATE interactions SET {col} = true WHERE code = %s", (code,))
                return (True, "") if cur.rowcount else (False, "unknown code")
        except Exception as e:
            _err("tap", e)
            return False, "store error"
    with _lock:
        row = _mem_interactions.get(code)
        if not row:
            return False, "unknown code"
        if tap == "share_open":
            row["share_opens"] += 1
        else:
            row[TAP_COLUMNS[tap]] = True
    return True, ""


def clean_text(text):
    """Collapse whitespace, cap the length. Empty becomes None."""
    if text is None:
        return None
    text = " ".join(str(text).split())[:MAX_FEEDBACK_CHARS]
    return text or None


def record_feedback(code, rating, text=None):
    """One answer per interaction; a later answer replaces it. Returns (ok, reason)."""
    rating = RATINGS.get(str(rating))
    if not rating:
        return False, "unknown rating"
    text = clean_text(text) if rating in ("partly", "no") else None
    day = today()
    if USE_DB:
        try:
            with _db() as c:
                if text is None and rating in ("partly", "no"):
                    # a tap without text must not wipe text already given for the same answer
                    cur = c.execute(
                        "UPDATE interactions SET fb_text = CASE WHEN fb_rating = %s THEN fb_text ELSE NULL END, "
                        "fb_rating = %s, fb_day = %s WHERE code = %s", (rating, rating, day, code))
                else:
                    cur = c.execute(
                        "UPDATE interactions SET fb_rating = %s, fb_text = %s, fb_day = %s WHERE code = %s",
                        (rating, text, day, code))
                return (True, "") if cur.rowcount else (False, "unknown code")
        except Exception as e:
            _err("feedback", e)
            return False, "store error"
    with _lock:
        row = _mem_interactions.get(code)
        if not row:
            return False, "unknown code"
        if text is None and rating in ("partly", "no") and row["fb_rating"] == rating:
            text = row["fb_text"]
        row["fb_rating"], row["fb_text"], row["fb_day"] = rating, text, day
    return True, ""


def delete_interaction(code):
    """Selftest cleanup only."""
    if USE_DB:
        try:
            with _db() as c:
                c.execute("DELETE FROM interactions WHERE code = %s AND qa = true", (code,))
        except Exception as e:
            _err("delete", e)
        return
    with _lock:
        row = _mem_interactions.get(code)
        if row and row["qa"]:
            _mem_interactions.pop(code, None)


# ---------- reads ----------

_COLS = ("code", "day", "kind", "tree", "path", "root_cause", "device", "qa", "copied",
         "opened_ai", "shared", "share_opens", "fb_rating", "fb_text", "fb_day")


def get_interaction(code):
    """The stored record, read back from the store. Used by the selftest."""
    if USE_DB:
        try:
            with _db() as c:
                r = c.execute(f"SELECT {', '.join(_COLS)} FROM interactions WHERE code = %s", (code,)).fetchone()
                return dict(zip(_COLS, r)) if r else None
        except Exception as e:
            _err("get", e)
            return None
    with _lock:
        row = _mem_interactions.get(code)
        return dict(row) if row else None


def _load(as_of):
    """All visit counts and interactions up to as_of. Feedback text is never loaded."""
    if USE_DB:
        with _db() as c:
            visits = c.execute(
                "SELECT day, first_day, kind, qa, n FROM visit_counts WHERE day <= %s", (as_of,)).fetchall()
            inter = c.execute(
                "SELECT kind, tree, path, root_cause, device, qa, copied, opened_ai, shared, share_opens, "
                "fb_rating, (fb_text IS NOT NULL) FROM interactions WHERE day <= %s", (as_of,)).fetchall()
        return visits, inter
    with _lock:
        visits = [(k[0], k[1], k[2], k[3], n) for k, n in _mem_visits.items() if k[0] <= as_of]
        inter = [(r["kind"], r["tree"], r["path"], r["root_cause"], r["device"], r["qa"], r["copied"],
                  r["opened_ai"], r["shared"], r["share_opens"], r["fb_rating"], r["fb_text"] is not None)
                 for r in _mem_interactions.values() if r["day"] <= as_of]
    return visits, inter


def _rate(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def metrics(as_of=None):
    """Counts only, no text. Test rows are reported separately and never mixed in."""
    as_of = _parse_day(as_of) or today()
    try:
        visits, inter = _load(as_of)
    except Exception as e:
        _err("metrics", e)
        return {"ok": False, "error": "store error"}

    cutoff = as_of - datetime.timedelta(days=RETURN_WINDOW_DAYS)
    v = {"first": 0, "returned": 0, "daily": 0}
    eligible = returned = qa_visits = 0
    for day, first_day, kind, qa, n in visits:
        if qa:
            qa_visits += n
            continue
        v[kind] = v.get(kind, 0) + n
        if first_day <= cutoff:
            if kind == "first":
                eligible += n
            elif kind == "returned":
                returned += n

    def blank():
        return {"interactions": 0, "prompts": 0, "used": 0, "copied": 0, "opened_ai": 0, "shared": 0,
                "share_opens": 0, "feedback": 0, "yes": 0, "partly": 0, "no": 0, "with_text": 0}

    total, by_tree, by_kind, by_device, nodes = blank(), {}, {}, {}, {}
    qa_interactions = qa_feedback = 0
    for kind, tree, path, root_cause, device, qa, copied, opened_ai, shared, share_opens, rating, has_text in inter:
        if qa:
            qa_interactions += 1
            qa_feedback += 1 if rating else 0
            continue
        buckets = [total, by_tree.setdefault(tree, blank()), by_kind.setdefault(kind, blank()),
                   by_device.setdefault(device or "unknown", blank())]
        node = nodes.setdefault((tree, path, root_cause), {"tree": tree, "path": path, "root_cause": root_cause,
                                                           "interactions": 0, "used": 0, "yes": 0, "partly": 0, "no": 0})
        used = bool(copied or opened_ai)
        node["interactions"] += 1
        node["used"] += 1 if used else 0
        if rating:
            node[rating] += 1
        for b in buckets:
            b["interactions"] += 1
            if kind == "prompt":
                b["prompts"] += 1
                b["used"] += 1 if used else 0
                b["copied"] += 1 if copied else 0
                b["opened_ai"] += 1 if opened_ai else 0
                b["shared"] += 1 if shared else 0
                b["share_opens"] += share_opens or 0
            if rating:
                b["feedback"] += 1
                b[rating] += 1
                b["with_text"] += 1 if has_text else 0

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "timezone": PARK_TZ,
        "store": "postgres" if USE_DB else "memory",
        "note": "Counts only. Test (qa) rows are listed under qa and are in no other number.",
        "g1": {"eligible_first_visits": eligible, "returned": returned, "rate_percent": _rate(returned, eligible),
               "rule": f"browsers whose first visit was {RETURN_WINDOW_DAYS} or more days before as_of"},
        "g2": {"prompts": total["prompts"], "used": total["used"], "rate_percent": _rate(total["used"], total["prompts"]),
               "rule": "used = Copy or Open in AI tapped at least once; Share is separate"},
        "g3": {"interactions": total["interactions"], "feedback": total["feedback"],
               "rate_percent": _rate(total["feedback"], total["interactions"])},
        "visits": v,
        "totals": total,
        "by_tree": by_tree,
        "by_kind": by_kind,
        "by_device": by_device,
        "nodes": sorted(nodes.values(), key=lambda n: (-n["interactions"], n["tree"], n["path"])),
        "qa": {"visits": qa_visits, "interactions": qa_interactions, "feedback": qa_feedback},
    }
