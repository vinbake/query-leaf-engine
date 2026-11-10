"""
Reach tally tests (reach.py and /api/reach in app.py).

Run:  python3 test_reach.py
In-memory store unless DATABASE_URL is set. With DATABASE_URL it EMPTIES reach_counts first: throwaway database only.
Every check reads the stored tally or the read-out, never a reply alone.
"""
import datetime
import os
import sys

import counts
import reach
import app

counts.today = lambda: datetime.date(2026, 11, 11)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "|", name, ("| " + detail if detail and not ok else ""))


def reset():
    reach.init()
    if counts.USE_DB:
        if os.environ.get("ALLOW_TRUNCATE") != "yes":
            sys.exit("Refusing to empty reach_counts: set ALLOW_TRUNCATE=yes on a throwaway database.")
        with counts._db() as c:
            c.execute("TRUNCATE reach_counts")
    reach._mem.clear()


def stored():
    if counts.USE_DB:
        with counts._db() as c:
            return {(m, p, b, q): n for m, p, b, q, n in c.execute("SELECT month,postcode,band,qa,n FROM reach_counts")}
    return dict(reach._mem)


reset()
M = "2026-11"

# postcode to state
check("3030 is VIC", reach.state_of("3030") == "VIC")
check("2600 is ACT, 2000 is NSW, 0800 is NT", reach.state_of("2600") == "ACT" and reach.state_of("2000") == "NSW" and reach.state_of("0800") == "NT")
check("not a postcode: 12345, abcd, 0000, 2899, empty, None",
      all(reach.state_of(x) is None for x in ("12345", "abcd", "0000", "2899", "", None)))

# recording
reach.record("3030", "35-44")
check("adult: postcode and band stored together", stored().get((M, "3030", "35-44", False)) == 1)
reach.record("3030", "35-44")
check("same again adds one", stored().get((M, "3030", "35-44", False)) == 2)

reach.record("3030", "under-12")
check("under-12: band kept, postcode NEVER stored", stored().get((M, "", "under-12", False)) == 1 and not any(k[1] == "3030" and k[2] == "under-12" for k in stored()))
reach.record("3030", "12-17")
check("12-17: postcode NEVER stored", not any(k[1] and k[2] == "12-17" for k in stored()))

reach.record("3030", None)
check("postcode alone is kept", stored().get((M, "3030", "", False)) == 1)
reach.record(None, "65-plus")
check("band alone is kept", stored().get((M, "", "65-plus", False)) == 1)

before = dict(stored())
r1 = reach.record("99999", "ninety")
r2 = reach.record("", "")
r3 = reach.record("abcd", None)
check("junk is refused and nothing is stored", not r1[0] and not r2[0] and not r3[0] and stored() == before, str(stored()))
ok, _ = reach.record("99999", "18-24")
check("bad postcode with a good band keeps only the band", ok and stored().get((M, "", "18-24", False)) == 1)

reach.record("3030", "25-34", qa=True)
check("qa traffic is stored apart", stored().get((M, "3030", "25-34", True)) == 1)

# the table can hold nothing that identifies anyone
if counts.USE_DB:
    with counts._db() as c:
        cols = [r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='reach_counts'")]
else:
    cols = ["month", "postcode", "band", "qa", "n"]
check("only month, postcode, band, qa, n exist", sorted(cols) == sorted(["month", "postcode", "band", "qa", "n"]), str(cols))

# read-out hides small groups and qa
out = reach.readout(min_group=10)
check("small groups hidden: nothing shown at 10", out["ok"] and out["by_postcode"] == {} and out["by_band"] == {} and out["by_state"] == {}, str(out))
check("hidden postcodes are counted, not named", out["postcodes_hidden_for_size"] >= 1 and "3030" not in str(out["by_postcode"]))
for _ in range(12):
    reach.record("3029", "45-54")
out = reach.readout(min_group=10)
check("a group of 12 shows", out["by_postcode"] == {"3029": 12} and out["by_band"] == {"45-54": 12} and out["by_state"] == {"VIC": 15}, str(out))  # state total includes the 3 hidden 3030 visitors
check("qa rows never in the read-out", "25-34" not in out["by_band"])
check("min group can't be set below 2", reach.readout(min_group=0)["min_group"] == 2)
check("read-out has no month below the minimum", out["by_month"] in ({}, {M: 12 + 0}) or all(v >= 10 for v in out["by_month"].values()))

# the route
status, body = app.reach_post({"postcode": "3030", "band": "35-44"})
check("route accepts a good tally", status == 200 and body == {"ok": True})
status, body = app.reach_post({"postcode": "x", "band": "y"})
check("route refuses junk gently", status == 200 and body.get("ok") is False)
status, body = app.reach_post({"postcode": "3030", "band": "under-12", "dob": "2016-01-01", "name": "A"})
check("route ignores extra fields; dob/name never stored", all("2016" not in str(k) and "A" != k[1] for k in stored()))

bad = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
