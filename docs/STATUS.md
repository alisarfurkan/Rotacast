# Status & next steps (handoff, 2026-11-12)

## Done (all committed, 90 tests passing)
- Connectors: NASA POWER, MODIS NDVI + land cover (ORNL), SoilGrids (+fallback), terrain tiles (SRTM), GRACE CSR mascons (Konya CSV cached), CHIRPS/IMERG via ClimateSERV with monthly POWER rain bias correction (Çumra: POWER 533 → CHIRPS 302 mm/yr).
- Engine: FAO-56 ET0, climate shift (heat days doubled, ET0 up, rain unchanged), NDVI Field Memory (summer crop 18/26 yrs, bare Dec–Mar), FAO-56 water balance, rotations, Pareto picking, scoring. 21-crop knowledge base.
- API (`uvicorn rotacast.api.main:app --app-dir backend`): `/api/field/analyze`, `/api/basin/konya`, `/api/crops`; serves `frontend/dist`.
- Frontend: field analysis + Basin View tab, TR/EN; mocks = real demo reports.
- Konya field result (corrected rain), p50: baseline 4,829 m³/ha/yr, water_saver 1,206, soil_builder 1,379, balanced_income 1,843 (income 2,782 vs 1,978).
- Basin: 19 POWER cells, baseline mix calibrated to Konya 2024 crop areas, GRACE −1.22 cm/yr ≈ −534 Mm³/yr.

## Known issues (fix in priority order)
1. Basin report uses RAW POWER rain (ClimateSERV was flaky during the run) → rerun `backend/scripts/build_basin_report.py` when ClimateSERV is healthy; possible connector bug: `precip.py` may return partial data silently when chunks fail.
2. Basin potato expansion is not credible (no market cap) → cap crop expansion or exclude potato from basin strategies; do not quote potato numbers.
3. Basin offsets > 100 % at 30–50 % adoption → pitch should lead with 10 % adoption (~36–42 % of GRACE loss) as an order-of-magnitude scenario.
4. `ROTACAST_OFFLINE=1` falls back to raw POWER rain in the field report if the CHIRPS cache key misses — check before an offline demo.
5. Perennials (alfalfa, sainfoin) excluded from generated candidates (single-season simulator).

## Next steps
1. 13 Nov: read challenge Resources tab, Judging & Awards Guide, Project Submission Guide; update PLAN §1/§10.
2. `docs/METHODS.md` (material: WP3b modelling choices, phenology/climate methods, precip correction, basin assumptions) + root `README.md`.
3. Pitch: slides/video script, submission text, SI-usage statement.
4. Optional: public deploy (single container), SMAP validation (needs Earthdata), Claude narrative layer (needs API key).
