#!/usr/bin/env bash
# How complete are data.nysed.gov's school listings?
set -u
UA="nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"
curl -sL -A "$UA" "https://data.nysed.gov/lists.php?type=school" > l.html
echo "lists: profile links $(grep -o 'profile.php?instid=' l.html | wc -l), unique $(grep -o 'profile.php?instid=[0-9]*' l.html | sort -u | wc -l), charter-named $(grep -oiE 'instid=[0-9]+"[^>]*>[^<]*charter' l.html | sort -u | wc -l)"
grep -oiE '(page|offset|start|letter|alpha|next|more)[=a-z0-9&;"]{0,40}' l.html | sort | uniq -c | sort -rn | head -15
grep -oiE '<a [^>]*(data-|onclick|ajax)[^>]{0,120}' l.html | head -5
grep -oiE 'src="[^"]+\.js[^"]*"' l.html | head
for c in 32 33; do
  curl -sL -A "$UA" "https://data.nysed.gov/profile.php?county=$c" > c.html
  echo "county $c: links $(grep -o 'instid=[0-9]*' c.html | sort -u | wc -l), charter-named $(grep -oiE 'instid=[0-9]+"[^>]*>[^<]*charter' c.html | sort -u | wc -l)"
  grep -oiE 'href="[^"]*(district|lists|county|page)[^"]*"' c.html | sort -u | head -10
done
python3 - <<'PY'
import re
t=open("c.html",encoding="utf8",errors="replace").read()
for m in re.finditer(r'(?i)charter', t):
    print(re.sub(r"\s+"," ",t[max(0,m.start()-200):m.start()+80])); break
PY
