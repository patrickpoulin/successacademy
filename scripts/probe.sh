#!/usr/bin/env bash
# Second probe: drill into LCGMS, NYC DOE charter page, NYSED, data.ny.gov.
set -u
UA="nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"
hr(){ echo; echo "=================== $* ==================="; }
hr "LCGMS.aspx body"
curl -sL -A "$UA" "https://www.nycenet.edu/PublicApps/LCGMS.aspx" | sed -n '/<body/,$p' | grep -vE '^\s*$' | head -120
hr "DOE charter page links + text"
curl -sL -A "$UA" "https://www.schools.nyc.gov/enrollment/enroll-grade-by-grade/charter-schools" > doe.html
grep -oiE 'href="[^"]+"' doe.html | grep -viE '\.css|\.js|#|facebook|twitter|instagram|youtube' | sort -u | head -80
python3 -c "import re,html;t=open('doe.html',encoding='utf8',errors='replace').read();t=re.sub(r'(?s)<(script|style).*?</\1>','',t);t=re.sub(r'<[^>]+>',' ',t);t=re.sub(r'\s+',' ',html.unescape(t));i=t.lower().find('charter');print(t[i:i+2500])"
hr "NYSED"
for u in https://www.nysed.gov/charter-schools https://eservices.nysed.gov/sedreports/list?id=1 https://data.nysed.gov/ https://www.p12.nysed.gov/irs/schoolDirectory/; do
  echo "--- $u"; curl -sSL -A "$UA" -o /tmp/n.html -m 30 -w "%{http_code} %{url_effective} %{size_download}\n" "$u" 2>&1 | tail -2
  grep -oiE 'href="[^"]+"' /tmp/n.html | grep -iE 'charter|sedref|report|xls|csv|download|director' | sort -u | head -40
done
hr "data.ny.gov catalog"
curl -sL "https://api.us.socrata.com/api/catalog/v1?domains=data.ny.gov&q=charter%20school&limit=25" | python3 -c '
import json,sys
for r in json.load(sys.stdin)["results"]:
  x=r["resource"]; print(x["id"], "|", x["name"], "|", x.get("data_updated_at"), "|", ",".join(x.get("columns_field_name",[]))[:300])'
hr "NYC Open Data newer school lists"
for q in "lcgms" "school directory" "charter"; do
curl -sL "https://api.us.socrata.com/api/catalog/v1?domains=data.cityofnewyork.us&q=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$q")&limit=15&order=updatedAt" | python3 -c '
import json,sys
for r in json.load(sys.stdin)["results"]:
  x=r["resource"]
  if x.get("data_updated_at","")>"2023": print(x["id"], "|", x["name"], "|", x.get("data_updated_at"), "|", ",".join(x.get("columns_field_name",[]))[:250])'
done
hr "wg9x-4ke6 charter sample"
curl -sL "https://data.cityofnewyork.us/resource/wg9x-4ke6.json?\$where=managed_by_name='Charter'&\$limit=2"; echo
curl -sL "https://data.cityofnewyork.us/resource/wg9x-4ke6.json?\$select=managed_by_name,count(*)&\$group=managed_by_name"; echo
hr "SUNY pages"
for pg in 1 2 24 25; do curl -sL -A "$UA" "https://www.newyorkcharters.org/charter-schools/?pg=$pg" | grep -c 'school-row'; done
