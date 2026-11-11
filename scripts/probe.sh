#!/usr/bin/env bash
# Probe data.nysed.gov school list and profile layout.
set -u
UA="nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"
curl -sL -A "$UA" "https://data.nysed.gov/lists.php?type=school" > l.html
echo "list bytes $(wc -c < l.html); charter links $(grep -oi 'profile.php?instid=[0-9]*\">[^<]*charter' l.html | wc -l)"
grep -oiE '<(select|option|form)[^>]{0,150}' l.html | head -20
python3 - <<'PY'
import re,html
t=open("l.html",encoding="utf8",errors="replace").read()
i=t.find("ACADEMIC LEADERSHIP"); print(t[i-600:i+400])
PY
echo "=== profile"
curl -sL -A "$UA" "https://data.nysed.gov/profile.php?instid=800000064236" > p.html
python3 - <<'PY'
import re,html
t=open("p.html",encoding="utf8",errors="replace").read()
t2=re.sub(r'(?s)<(script|style).*?</\1>','',t); t2=re.sub(r'<[^>]+>',' | ',t2); t2=re.sub(r'(\s*\|\s*)+',' | ',html.unescape(t2))
i=t2.find("ACADEMIC LEADERSHIP"); print(t2[i:i+1500])
PY
