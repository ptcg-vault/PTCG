#!/usr/bin/env python3
"""
  python job/job.py prices    # daily: TCGplayer prices (via tcgcsv.com) for every product anyone holds -> Supabase `prices`
  python job/job.py catalog   # weekly: write site/catalog.json (all Pokemon products) for in-browser search
Env for `prices`: SUPABASE_URL, SUPABASE_SERVICE_KEY   (stdlib only, no installs)
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://tcgcsv.com/tcgplayer/3"
UA = {"User-Agent": "tcg-vault/1.0 (personal project)"}


def jget(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"results": []}
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET failed: " + url)


def sb(path, method="GET", body=None, extra=None):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    h = {"apikey": key, "Content-Type": "application/json", **(extra or {})}
    if not key.startswith("sb_"):  # legacy JWT service_role key also goes in Authorization; new sb_secret_ keys don't
        h["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url.rstrip("/") + "/rest/v1/" + path, method=method, headers=h,
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read()
        return json.loads(t) if t else None


def prices():
    seen, off = {}, 0
    while True:
        rows = sb(f"lots?select=pid,gid&order=id&limit=1000&offset={off}")
        seen.update({r["pid"]: r["gid"] for r in rows})
        if len(rows) < 1000:
            break
        off += 1000
    if not seen:
        return print("No products tracked yet.")
    day, out = datetime.now(timezone.utc).date().isoformat(), []
    for gid in set(seen.values()):
        best = {}
        for r in jget(f"{BASE}/{gid}/prices")["results"]:
            pid = r["productId"]
            if seen.get(pid) != gid:
                continue
            v = r.get("marketPrice") if r.get("marketPrice") is not None else r.get("midPrice")
            if v is not None and (pid not in best or r.get("subTypeName") == "Normal"):
                best[pid] = v
        out += [{"pid": p, "date": day, "price": v} for p, v in best.items()]
        time.sleep(0.2)
    for i in range(0, len(out), 500):
        sb("prices?on_conflict=pid,date", "POST", out[i:i + 500], {"Prefer": "resolution=merge-duplicates,return=minimal"})
    print(f"{day}: saved {len(out)} prices for {len(seen)} tracked products")


def catalog():
    sets, rows = {}, []
    groups = jget(f"{BASE}/groups")["results"]
    for i, g in enumerate(groups, 1):
        sets[g["groupId"]] = [g["name"], g.get("abbreviation") or ""]
        for p in jget(f"{BASE}/{g['groupId']}/products")["results"]:
            num = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), "")
            rows.append([p["productId"], p["name"], g["groupId"], num or ""])
        if i % 50 == 0:
            print(f"{i}/{len(groups)} sets")
        time.sleep(0.15)
    out = Path(__file__).resolve().parent.parent / "site" / "catalog.json"
    out.write_text(json.dumps({"sets": sets, "rows": rows}, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {len(rows):,} products in {len(sets)} sets -> {out}")


if __name__ == "__main__":
    {"prices": prices, "catalog": catalog}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
