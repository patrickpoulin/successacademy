# NYC charter schools map

A GitHub Pages site that maps every NYC charter school and cross-checks the lists published by:

- **NYC DOE** school locations on NYC Open Data
- **SUNY Charter Schools Institute** (SUNY-authorized schools)
- more sources (NYSED, NYC DOE Charter Schools Office) as their endpoints are confirmed

A GitHub Action (`.github/workflows/update.yml`) runs `scripts/fetch.py` daily, writes `site/data/schools.json`,
and deploys `site/` to Pages. Schools flagged ⚠ on the map are ones where the sources disagree
(missing from a list, or a different BEDS code, DBN, borough or authorizer).

Run locally: `python3 scripts/fetch.py && python3 -m http.server -d site`
