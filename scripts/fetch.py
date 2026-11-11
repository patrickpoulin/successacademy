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
    """NYC DOE school locations on NYC Open Data. The newest one published is
    2019-20 (wg9x-4ke6), so it's a historical baseline with coordinates."""
    ds = "wg9x-4ke6"
    rows = json.loads(get(f"https://data.cityofnewyork.us/resource/{ds}.json",
                          {"$where": "managed_by_name='Charter'", "$limit": 5000}))
    out = []
    for r in rows:
        if re.search(r"closed", r.get("status_descriptions", ""), re.I):
            continue
        dbn = r.get("system_code")
        out.append(rec(name=r.get("location_name"), dbn=dbn, beds=r.get("beds"),
                       address=(r.get("primary_address_line_1") or "").title(),
                       borough=borough_of(dbn[2] if dbn and len(dbn) > 2 else None),
                       lat=r.get("latitude"), lon=r.get("longitude"),
                       grades=(r.get("grades_final_text") or "").replace(",", ", ")))
    return out, f"https://data.cityofnewyork.us/d/{ds}"


def read_table(blob):
    """Rows (as dicts) from an .xlsx, an HTML-table .xls, or CSV."""
    if blob[:2] == b"PK":
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        rows = list(it)
    else:
        text = blob.decode("utf-8", "replace")
        if "<table" in text.lower():
            p = Tables(); p.feed(text)
            rows = max(p.tables, key=len)
        else:
            rows = list(csv.reader(io.StringIO(text)))
    hi = next(i for i, r in enumerate(rows) if sum(1 for c in r if c) >= 5)  # skip title rows
    header = [clean(h) for h in rows[hi]]
    return [dict(zip(header, [clean(c) for c in r])) for r in rows[hi + 1:] if any(r)]


def src_doe_lcgms():
    """NYC DOE LCGMS school report: the current district + charter school list,
    behind the Excel download button on the DOE Office of Organizational Data page."""
    url = "https://www.nycenet.edu/PublicApps/LCGMS.aspx"
    page = get(url)
    form = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))
    btn = re.search(r"__doPostBack\(&#39;([^&]+)&#39;", page).group(1)
    form.update({"__EVENTTARGET": btn, "__EVENTARGUMENT": ""})
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(),
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=120) as r:
        blob = r.read()
        log(f"  LCGMS download: {r.headers.get('Content-Type')} {len(blob)} bytes")
    rows = read_table(blob)
    log("  LCGMS columns: " + " | ".join(rows[0].keys()))
    out = []
    for row in rows:
        managed = pick(row, r"managed by")
        dbn = pick(row, r"ats system code", r"system code", r"^dbn$")
        if not (re.search(r"charter", managed or "", re.I) or (dbn or "").startswith("84")):
            continue
        if re.search(r"closed", pick(row, r"status") or "", re.I):
            continue
        out.append(rec(
            name=pick(row, r"^location name$", r"school name", r"name"), dbn=dbn, beds=pick(row, r"beds"),
            address=pick(row, r"primary address", r"address"),
            borough=borough_of(pick(row, r"city", r"borough"), dbn[2] if dbn and len(dbn) > 2 else None),
            zip=pick(row, r"zip"), grades=pick(row, r"grades final", r"grades"),
            lat=pick(row, r"latitude"), lon=pick(row, r"longitude")))
    if not out:
        raise RuntimeError("no charter rows found in LCGMS file")
    return out, "https://infohub.nyced.org/in-our-schools/operations/lcgms"


def src_suny():
    """SUNY Charter Schools Institute school finder (SUNY-authorized only).
    One row per school; a school with several campuses lists each address."""
    base = "https://www.newyorkcharters.org/charter-schools/"
    out, seen = [], set()
    cell = lambda cls, row: (re.search(r'<td class="%s"[^>]*>(.*?)</td>' % cls, row, re.S) or [None, ""])[1]
    for pg in range(1, 80):
        page = get(base, {"pg": pg} if pg > 1 else None)
        rows = re.findall(r'<tr class="school-\d+ school-row.*?</tr>', page, re.S)
        new = 0
        for row in rows:
            m = re.search(r'<a href="(/charter-schools/[^"]+)">(.*?)</a>', row, re.S)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            new += 1
            if "new york city" not in clean(re.sub("<[^>]+>", " ", cell("region", row))).lower():
                continue
            addrs = [clean(re.sub(r"<br\s*/?>", ", ", a)) for a in re.findall(r"<li>(.*?)</li>", cell("locations", row), re.S)]
            out.append(rec(name=clean(m.group(2)), borough=borough_of(clean(cell("borough", row))),
                           grades=clean(re.sub("<[^>]+>", " ", cell("grades", row))).split(" for ")[0],
                           address=addrs[0] if addrs else None, authorizer="SUNY Trustees"))
            out[-1]["campuses"] = addrs
            out[-1]["url"] = "https://www.newyorkcharters.org" + m.group(1)
        if not new:
            break
    if not out:
        raise RuntimeError("SUNY finder returned no NYC schools (page layout may have changed)")
    return out, base


SOURCES = {
    "lcgms": {"label": "NYC DOE LCGMS school list (current)", "short": "DOE", "fn": src_doe_lcgms},
    "opendata": {"label": "NYC Open Data school locations (2019-20 snapshot)", "short": "OpenData 2019",
                 "fn": src_doe_opendata, "historical": True},
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
        if all(SOURCES[k].get("historical") for k in s["in"]):
            issues.append("Only in the 2019-20 list; may have closed or been renamed")
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
    if SOURCES[src].get("historical"):
        return False
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
