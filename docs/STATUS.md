# Status & next steps (handoff, 2026-11-13)

## Done (all committed, 100 tests passing)
- Connectors: NASA POWER, MODIS NDVI + land cover (ORNL), SoilGrids (+fallback), terrain tiles (SRTM), GRACE CSR mascons (Konya CSV cached), CHIRPS/IMERG via ClimateSERV with monthly POWER rain bias correction (Çumra: POWER 533 → CHIRPS 302 mm/yr). ClimateSERV failures are retried; coverage is recorded and sources with < 80 % of years are rejected.
- Engine: FAO-56 ET0, climate shift (heat days doubled, ET0 up, rain unchanged), NDVI Field Memory (summer crop 18/26 yrs, bare Dec–Mar), FAO-56 water balance, rotations, Pareto picking, scoring. 21-crop knowledge base.
- API (`uvicorn rotacast.api.main:app --app-dir backend`): `/api/field/analyze`, `/api/basin/konya`, `/api/crops`; serves `frontend/dist`.
- Frontend: field analysis + Basin View tab (defaults to 10 % adoption, headline card, market warning), TR/EN; mocks = real demo reports.
- Konya field result (corrected rain), p50: baseline 4,829 m³/ha/yr, water_saver 1,206, soil_builder 1,379, balanced_income 1,843 (income 2,782 vs 1,978).
- Basin (rebuilt 2026-11-13, CHIRPS-corrected in 19/19 cells): baseline demand p50 3,155 Mm³/yr; GRACE −1.22 cm/yr ≈ −534 Mm³/yr.
  Headline (10 % adoption, 10 yr, trend climate): water_saver −220 Mm³/yr = 41 % (37–46) of GRACE loss; soil_builder −166 = 31 % (28–35); balanced_income −164 = 31 % (28–35). All market-plausible.
  Potato excluded from basin strategies; crops whose production rises > 25 % of baseline are flagged (only at 30–50 %: sunflower, dry bean, sugar beet). Crops new to the irrigated baseline are listed in `new_crops`, not flagged.
- Docs: `docs/METHODS.md`, root `README.md`, `docs/SOURCES.md`.
- `backend/scripts/check_offline.py` → PASS (field + basin work with `ROTACAST_OFFLINE=1`).

## Known issues
1. Perennials (alfalfa, sainfoin) excluded from generated candidates (single-season simulator).
2. Offline mode only covers cached points: a field clicked away from the demo point needs network (CHIRPS ~1 min/year-chunk).
3. 30–50 % adoption offsets exceed 90–200 % of GRACE loss → present only as sensitivity runs.
4. Rules: Space Apps FAQ says no work before the event (14 Nov); repo commits are dated 12–13 Nov — check with organisers.

## Next steps
1. 13 Nov: read challenge Resources tab, Judging & Awards Guide, Project Submission Guide; update PLAN §1/§10.
2. Screenshot for README (`docs/screenshot.png`), UI check of Basin View in browser.
3. Pitch: slides/video script, submission text, SI-usage statement.
4. Optional: public deploy (single container), SMAP validation (needs Earthdata), Claude narrative layer (needs API key).
