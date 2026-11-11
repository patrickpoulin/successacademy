#!/usr/bin/env python3
"""Fetch NYC charter school lists from several official sources, merge them,
and write site/data/schools.json for the map.

Each source returns a list of normalized records. A source that fails is
recorded as down; the merge still runs on the rest so the site keeps working.
Run: python3 scripts/fetch.py  (stdlib only)
"""
import csv, html, io, json, os, re, sys, time, traceback, urllib.parse, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data", "schools.json")
GEOCACHE = os.path.join(ROOT, "data", "geocache.json")
UA = "nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"

BOROUGHS = {"M": "Manhattan", "X": "Bronx", "K": "Brooklyn", "Q": "Queens", "R": "Staten Island"}
BORO_NAMES = {"manhattan": "Manhattan", "new york": "Manhattan", "bronx": "Bronx", "brooklyn": "Brooklyn",
              "kings": "Brooklyn", "queens": "Queens", "staten island": "Staten Island", "richmond": "Staten Island"}
NYC_COUNTIES = {"NEW YORK", "BRONX", "KINGS", "QUEENS", "RICHMOND"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, params=None, tries=3, binary=False):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return b if binary else b.decode(r.headers.get_content_charset() or "utf-8", "replace")
        except Exception as e:
            log(f"  GET {url} failed ({e}); try {i + 1}/{tries}")
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip()


def borough_of(*vals):
    for v in vals:
        v = clean(v).lower()
        if not v:
            continue
        if v.upper() in BOROUGHS:
            return BOROUGHS[v.upper()]
        for k, name in BORO_NAMES.items():
            if k in v:
                return name
    return None


def pick(row, *patterns):
    """First non-empty value whose column name matches any regex (case-insensitive)."""
    for p in patterns:
        for k, v in row.items():
            if re.search(p, k, re.I) and clean(v):
                return clean(v)
    return None


def rec(**kw):
    r = {k: None for k in ("name", "beds", "dbn", "address", "borough", "zip", "lat", "lon", "grades", "authorizer")}
    r.update({k: v for k, v in kw.items() if v not in ("", None)})
    if r["beds"]:
        r["beds"] = re.sub(r"\D", "", r["beds"]) or None
    if r["dbn"]:
        r["dbn"] = r["dbn"].upper().replace(" ", "")
    for k in ("lat", "lon"):
        try:
            r[k] = float(r[k]) if r[k] is not None else None
        except ValueError:
            r[k] = None
    return r


class Tables(HTMLParser):
    """Collect every <table> as a list of rows of cell text, plus links."""
    def __init__(self):
        super().__init__()
        self.tables, self.links, self._cell, self._row, self._href = [], [], None, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, d):
        if self._cell is not None:
            self._cell.append(d)


# ---------------------------------------------------------------- sources

def src_doe_opendata():
    """NYC DOE school locations on NYC Open Data (Socrata). Finds the newest
    'school locations' dataset at run time and keeps rows marked charter."""
    cat = json.loads(get("https://api.us.socrata.com/api/catalog/v1", {
        "domains": "data.cityofnewyork.us", "q": "school locations", "only": "datasets", "limit": 50}))
    cands = []
    for r in cat["results"]:
        x = r["resource"]
        cols = [c.lower() for c in x.get("columns_field_name", [])]
        if "location" in x["name"].lower() and any("managed_by" in c for c in cols):
            cands.append((x.get("data_updated_at") or "", x["id"], x["name"]))
    if not cands:
        raise RuntimeError("no school-locations dataset with a managed_by column found")
    cands.sort(reverse=True)
    _, ds, dsname = cands[0]
    log(f"  using dataset {ds} ({dsname})")
    rows = json.loads(get(f"https://data.cityofnewyork.us/resource/{ds}.json", {"$limit": 50000}))
    out = []
    for row in rows:
        flat = {k: (v if not isinstance(v, dict) else json.dumps(v)) for k, v in row.items()}
        if not re.search(r"charter", " ".join(str(flat.get(k, "")) for k in flat if re.search(r"managed|categor|type", k)), re.I):
            continue
        lat = pick(flat, r"^latitude$", r"lat")
        lon = pick(flat, r"^longitude$", r"lon")
        if (lat is None or lon is None) and isinstance(row.get("location_1"), dict):
            lat, lon = row["location_1"].get("latitude"), row["location_1"].get("longitude")
        dbn = pick(flat, r"ats_system_code", r"^dbn$", r"system_code")
        out.append(rec(
            name=pick(flat, r"^location_name$", r"school_name", r"name"),
            dbn=dbn, beds=pick(flat, r"beds"),
            address=pick(flat, r"primary_address_line_1", r"address"),
            borough=borough_of(pick(flat, r"borough"), dbn[2] if dbn and len(dbn) > 2 else None),
            zip=pick(flat, r"zip"), lat=lat, lon=lon,
            grades=pick(flat, r"grades_final_text", r"grades")))
    return out, f"https://data.cityofnewyork.us/d/{ds}"


def src_suny():
    """SUNY Charter Schools Institute school finder (SUNY-authorized only)."""
    base = "https://www.newyorkcharters.org/charter-schools/"
    out, seen = [], set()
    for pg in range(1, 60):
        p = Tables()
        p.feed(get(base, {"pg": pg} if pg > 1 else None))
        rows = [r for t in p.tables for r in t]
        if not rows:
            break
        header = [h.lower() for h in rows[0]]
        new = 0
        for r in rows[1:]:
            d = dict(zip(header, r))
            key = d.get("school")
            if not key or key in seen:
                continue
            seen.add(key)
            new += 1
            region = d.get("region", "")
            boro = borough_of(d.get("borough"))
            if not (boro or re.search(r"new york city|nyc", region, re.I)):
                continue
            out.append(rec(name=key, borough=boro, grades=d.get("grades"), address=d.get("location"),
                           authorizer="SUNY Trustees"))
        if not new:
            break
    if not out:
        raise RuntimeError("SUNY finder returned no NYC schools (page layout may have changed)")
    return out, base


SOURCES = {
    "doe": {"label": "NYC DOE school locations (NYC Open Data)", "short": "DOE", "fn": src_doe_opendata},
    "suny": {"label": "SUNY Charter Schools Institute", "short": "SUNY", "fn": src_suny,
             "scope": "SUNY Trustees"},
}


# ---------------------------------------------------------------- merge

STOP = {"charter", "school", "schools", "the", "of", "for", "and", "academy", "public", "cs", "ii", "nyc",
        "new", "york", "a", "at", "inc", "high", "middle", "elementary", "es", "ms", "hs"}


def name_key(n):
    n = clean(n).lower().replace("&", " and ")
    n = re.sub(r"\bcharter school\b|\bcs\b", " ", n)
    return " ".join(w for w in re.findall(r"[a-z0-9]+", n) if w not in STOP)


def similar(a, b):
    a, b = set(a.split()), set(b.split())
    return len(a & b) / max(1, len(a | b))


def merge(results):
    schools = []  # each: {fields..., in: {src: True}, names: {src: name}, recs: {src: rec}}

    def find(r):
        for s in schools:
            if r["beds"] and r["beds"] in s["_beds"]:
                return s
            if r["dbn"] and r["dbn"] in s["_dbn"]:
                return s
        k = name_key(r["name"])
        best, score = None, 0.0
        for s in schools:
            for sk in s["_keys"]:
                sc = similar(k, sk)
                if sc > score:
                    best, score = s, sc
        # require same borough when both known
        if best and score >= 0.75 and (not r["borough"] or not best["borough"] or r["borough"] == best["borough"]):
            return best
        return None

    for src, recs in results.items():
        for r in recs:
            s = find(r)
            if not s:
                s = {"_beds": set(), "_dbn": set(), "_keys": set(), "in": {}, "names": {}, "recs": {}}
                schools.append(s)
            if src in s["recs"]:  # second campus of the same school in the same source
                s.setdefault("_extra", []).append((src, r))
            s["in"][src] = True
            s["names"][src] = r["name"]
            s["recs"].setdefault(src, r)
            if r["beds"]: s["_beds"].add(r["beds"])
            if r["dbn"]: s["_dbn"].add(r["dbn"])
            s["_keys"].add(name_key(r["name"]))
            for f in ("name", "beds", "dbn", "address", "borough", "zip", "lat", "lon", "grades", "authorizer"):
                if s.get(f) is None and r[f] is not None:
                    s[f] = r[f]
    return schools


def finalize(schools, ok_sources):
    out = []
    for s in schools:
        issues = []
        missing = [SOURCES[k]["short"] for k in ok_sources if k not in s["in"] and applies(k, s)]
        if missing:
            issues.append("Not listed by " + ", ".join(missing))
        recs = s["recs"]
        for f, label in (("beds", "BEDS code"), ("dbn", "DBN"), ("borough", "borough")):
            vals = {k: r[f] for k, r in recs.items() if r[f]}
            if len(set(vals.values())) > 1:
                issues.append(f"{label} differs: " + "; ".join(f"{SOURCES[k]['short']} {v}" for k, v in vals.items()))
        auths = {k: r["authorizer"] for k, r in recs.items() if r["authorizer"]}
        if len(set(auths.values())) > 1:
            issues.append("Authorizer differs: " + "; ".join(f"{SOURCES[k]['short']} {v}" for k, v in auths.items()))
        sid = s.get("beds") or s.get("dbn") or name_key(s["name"]).replace(" ", "-")
        out.append({
            "id": sid, "name": s["name"], "beds": s.get("beds"), "dbn": s.get("dbn"), "address": s.get("address"),
            "borough": s.get("borough"), "zip": s.get("zip"), "lat": s.get("lat"), "lon": s.get("lon"),
            "grades": s.get("grades"), "authorizer": s.get("authorizer"),
            "in": {k: True for k in s["in"]}, "names": s["names"], "issues": issues})
    # unique ids
    seen = {}
    for o in out:
        n = seen.get(o["id"], 0)
        seen[o["id"]] = n + 1
        if n:
            o["id"] = f"{o['id']}-{n}"
    out.sort(key=lambda o: o["name"].lower())
    return out


def applies(src, s):
    """Authorizer lists only cover their own schools, so missing from SUNY
    isn't a disagreement for a school another authorizer oversees."""
    scope = SOURCES[src].get("scope")
    if not scope:
        return True
    return s.get("authorizer") == scope


# ---------------------------------------------------------------- geocode

def geocode(schools):
    cache = {}
    if os.path.exists(GEOCACHE):
        cache = json.load(open(GEOCACHE))
    n = 0
    for s in schools:
        if s["lat"] is not None or not s["address"]:
            continue
        q = s["address"] + ("" if re.search(r"\bNY\b|New York", s["address"]) else f", {s['borough'] or 'New York'}, NY")
        if q not in cache and n < 300:
            n += 1
            try:
                d = json.loads(get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
                                   {"address": q, "benchmark": "Public_AR_Current", "format": "json"}, tries=2))
                m = d["result"]["addressMatches"]
                cache[q] = [m[0]["coordinates"]["y"], m[0]["coordinates"]["x"]] if m else None
            except Exception as e:
                log(f"  geocode failed for {q}: {e}")
                continue
        if cache.get(q):
            s["lat"], s["lon"] = cache[q]
    os.makedirs(os.path.dirname(GEOCACHE), exist_ok=True)
    json.dump(cache, open(GEOCACHE, "w"), indent=0, sort_keys=True)
    log(f"geocoded {n} new addresses")


def main():
    results, meta = {}, {}
    for key, src in SOURCES.items():
        log(f"== {key}")
        m = {"label": src["label"], "short": src["short"], "url": "", "ok": False, "count": 0,
             "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            recs, url = src["fn"]()
            results[key] = recs
            m.update(ok=True, count=len(recs), url=url)
            log(f"  {len(recs)} schools")
        except Exception as e:
            traceback.print_exc()
            m["error"] = f"{type(e).__name__}: {e}"[:300]
        meta[key] = m
    if not results:
        sys.exit("every source failed; leaving existing data in place")
    schools = finalize(merge(results), list(results))
    geocode(schools)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "sources": meta, "schools": schools},
                  f, indent=1)
    log(f"wrote {len(schools)} schools, {sum(1 for s in schools if s['issues'])} with disagreements")


if __name__ == "__main__":
    main()
