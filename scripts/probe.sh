#!/usr/bin/env bash
# Probe NYSED sources for a machine-readable charter school list.
set -u
UA="nyc-charter-schools/1.0 (+https://github.com/patrickpoulin/successacademy)"
hr(){ echo; echo "=================== $* ==================="; }
hr "data.nysed.gov downloads"
curl -sL -A "$UA" https://data.nysed.gov/downloads.php > d.html; grep -oiE 'href="[^"]+"[^>]*>[^<]{0,120}' d.html | grep -iE 'zip|xls|csv|mdb|director|charter|enroll|bed' | head -60
hr "data.nysed.gov charter search"
curl -sL -A "$UA" "https://data.nysed.gov/lists.php?type=school" | grep -oiE 'href="[^"]+"[^>]*>[^<]{0,100}' | grep -iE 'charter' | head -20
hr "portal.nysed.gov SEDREF query"
curl -sSL -A "$UA" -o p.html -m 30 -w "%{http_code} %{url_effective} %{size_download}\n" 'https://portal.nysed.gov/pls/sedrefpublic/SED.sed_inst_qry_vw$.startup'; grep -oiE '<(form|input|select|option)[^>]{0,200}' p.html | head -40
hr "oms sedref"
curl -sSL -A "$UA" -o o.html -m 30 -w "%{http_code} %{url_effective} %{size_download}\n" 'http://www.oms.nysed.gov/sedref/home.html'; grep -oiE 'href="[^"]+"' o.html | head -30
