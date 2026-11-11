# NYC charter schools map

A GitHub Pages site that maps every NYC charter school and cross-checks the lists published by:

- **NYC DOE** LCGMS school list (current; Office of Organizational Data download)
- **NYSED** school list on data.nysed.gov (all authorizers; BEDS codes from each profile, cached in `data/nysed_profiles.json`)
- **SUNY Charter Schools Institute** school finder (SUNY-authorized schools only)
- **NYC Open Data** 2019-20 school locations (historical baseline and coordinates)

A GitHub Action (`.github/workflows/update.yml`) runs `scripts/fetch.py` daily, writes `site/data/schools.json`,
and deploys `site/` to Pages. Schools flagged ⚠ on the map are ones where the sources disagree
(missing from a list, or a different BEDS code, DBN, borough or authorizer).

Run locally: `python3 scripts/fetch.py && python3 -m http.server -d site`

`scripts/probe.sh` (run via the "Probe data sources" workflow) is a scratch tool for checking what a source returns.
