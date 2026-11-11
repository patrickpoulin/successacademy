#!/usr/bin/env bash
# Probe how data.nysed.gov paginates its school list.
set -u
UA="nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"
curl -sL -A "$UA" "https://data.nysed.gov/lists.php?type=school" > l.html
grep -oiE 'href="lists\.php[^"]*"' l.html | sort -u | head -40
grep -oiE 'href="[^"]*(letter|start|page|county)[^"]*"' l.html | sort -u | head -20
echo "titles: $(grep -c 'class="title"' l.html)"
for u in "https://data.nysed.gov/lists.php?type=school&start=B" "https://data.nysed.gov/lists.php?type=county" "https://data.nysed.gov/profile.php?county=32"; do
  curl -sL -A "$UA" -o x.html -w "$u %{http_code} %{size_download}\n" "$u"; echo " titles $(grep -c 'class=\"title\"' x.html) charter $(grep -ci 'charter' x.html)"; grep -oiE 'href="[^"]*(instid|county|lists)[^"]*"' x.html | head -8
done
