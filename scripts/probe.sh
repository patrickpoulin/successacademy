#!/usr/bin/env bash
# One-off: print what each candidate source actually returns, so the fetcher can be written against real headers.
set -u
UA="Mozilla/5.0 (nyc-charter-schools data refresh)"
hr(){ echo; echo "=================== $* ==================="; }
hr "Socrata catalog: school locations"
curl -sL -A "$UA" "https://api.us.socrata.com/api/catalog/v1?domains=data.cityofnewyork.us&q=school%20locations&limit=40" | python3 -c '
import json,sys
for r in json.load(sys.stdin)["results"]:
  x=r["resource"]; print(x["id"], "|", x["name"], "|", x.get("data_updated_at"), "|", ",".join(x.get("columns_field_name",[]))[:400])'
hr "Socrata catalog: charter"
curl -sL -A "$UA" "https://api.us.socrata.com/api/catalog/v1?domains=data.cityofnewyork.us&q=charter%20school&limit=40" | python3 -c '
import json,sys
for r in json.load(sys.stdin)["results"]:
  x=r["resource"]; print(x["id"], "|", x["name"], "|", x.get("data_updated_at"), "|", ",".join(x.get("columns_field_name",[]))[:300])'
hr "LCGMS"
curl -sL -A "$UA" -o lcgms.bin -w "%{http_code} %{content_type} %{size_download} %{url_effective}\n" "https://www.nycenet.edu/PublicApps/LCGMS.aspx"
file lcgms.bin; head -c 1500 lcgms.bin | strings | head -40
hr "infohub lcgms page links"
curl -sL -A "$UA" "https://infohub.nyced.org/in-our-schools/operations/lcgms" | grep -oiE 'href="[^"]+"' | grep -iE 'xls|csv|lcgms|aspx' | sort -u | head -30
hr "SEDREF list"
curl -sL -A "$UA" -w "\n%{http_code} %{url_effective}\n" "https://eservices.nysed.gov/sedreports/list?id=1" | grep -oiE 'href="[^"]+"|<a[^>]*>[^<]*charter[^<]*</a>' | head -80
hr "SEDREF root"
curl -sL -A "$UA" -w "\n%{http_code} %{url_effective}\n" "https://eservices.nysed.gov/sedreports/" | grep -oiE 'href="[^"]+"' | head -60
hr "SUNY finder"
curl -sL -A "$UA" -w "\n%{http_code}\n" "https://www.newyorkcharters.org/charter-schools/" > suny.html; tail -1 suny.html
grep -oiE '<table[^>]*>|<th[^>]*>[^<]*</th>|pg=[0-9]+|admin-ajax[^"]*|wp-json[^"]*|\.csv[^"]*|\.xlsx[^"]*' suny.html | sort | uniq -c | head -40
python3 - <<'PY'
import re
h=open("suny.html",encoding="utf8",errors="replace").read()
i=h.find("<table"); print(h[i:i+3000])
PY
hr "NYC DOE charter pages"
for u in "https://www.schools.nyc.gov/enrollment/enroll-grade-by-grade/charter-schools" "https://www.schools.nyc.gov/schools/charter-schools" "https://www.schools.nyc.gov/about-us/leadership/charter-schools-office"; do
  curl -sL -A "$UA" -o p.html -w "$u -> %{http_code} %{url_effective}\n" "$u"; grep -oiE 'href="[^"]+\.(xlsx|xls|csv|pdf)[^"]*"' p.html | head -20
done
hr "NYSED charter pages"
for u in "https://www.nysed.gov/charter-schools" "https://www.nysed.gov/charter-schools/charter-schools-directory" "https://www.p12.nysed.gov/psc/csdirectory/CSLaunchPage.html" "https://www.nysed.gov/charter-schools/school-information"; do
  curl -sL -A "$UA" -o p.html -w "$u -> %{http_code} %{url_effective}\n" "$u"; grep -oiE 'href="[^"]+"' p.html | grep -iE 'xlsx|xls|csv|director|list' | head -20
done
