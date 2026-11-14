# Status & next steps (handoff, updated 2026-11-14)

> **Read this before acting (people and AI assistants alike).** Every open task below has an owner. Only work on a
> task that is assigned to you. Tasks owned by someone else are listed for information only: do **not** start,
> plan in code, or partially implement them, even if they look next in line. If you are an AI coding assistant,
> ask your user before touching anything in "Next steps" that is not explicitly assigned to them.

## Done (all committed, 130 tests passing)
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

## Update 2026-11-14
- Challenge Resources tab reviewed: about half the listed sources are US-only (WSS, SSURGO, CDL, NAIP, NLCD, PRISM, CoCoRaHS, NWIS, AMS, NASS, OpenET, LANDFIRE). Usable global ones not yet integrated: SMAP, GLDAS, ECOSTRESS, HLS/Sentinel-2, FAO GAEZ, ERA5.
- Earthdata Login works (`~/.netrc`, kept outside the repo): GES DISC (GLDAS), NSIDC (SMAP L4), LP DAAC (HLS, ECOSTRESS) and the AppEEARS API were all tested on the Konya tile. Nothing integrated yet.
- Fixed: the per-crop "limited irrigation" button sent `limited`, which the engine silently treated as rain-fed; it now sends `deficit`, and unknown modes return 422 (commit `9944001`).
- Repo on GitHub (private): https://github.com/selejder/Rotacast. Rollback tag before the mode split: `v1-single-mode`.
- Beginner/Advanced modes are handed to a teammate (spec shared with them directly, not in the repo).

## Update 2026-11-14 (branch `feature/konya-zones`, not merged into main)
- App narrowed to **Konya province**: `/api/field/analyze` returns 422 `outside_konya` / `on_lake`; the map is locked to Konya.
- **7 agro-microclimate zones** (`data/zones/`, `backend/scripts/build_konya_zones.py`, METHODS §10): district groups
  + SRTM Taurus rule (≥ 1500 m) + 8 km Beyşehir lake buffer; profiled with MGM 1991–2020 classifications (12 stations)
  and NASA POWER 2001–2025 frost/temperature climatology. `GET /api/zones`; reports carry a `zone` block (CONTRACTS §6).
- Frontend: coloured zone layer + legend, Konya-only click check, zone line under the map, `ZoneCard` in the results.
- Fixed: `.mjs` served as text/plain on Windows, which broke the MapLibre worker (GeoJSON layers did not draw).
- An earlier attempt to derive zones by clustering MODIS LST/PET (AppEEARS) was dropped: hours of server-side queue.
- Zone crop whitelist (`data/zones/zone_crops.json`, METHODS §10.1): crops manually verified against official sources
  per zone (verified / pilot / caution; excluded crops never shown). Returned in `zone.crops`, shown in `ZoneCard`
  with source links. The rotation engine does not filter by it yet.
- Field cards replaced (METHODS §7.1, `engine/cards.py`): Balanced transition (default), Low risk and resilient,
  Innovative crop opportunity. Whitelist-only crops, hard water/erosion limits, area split, pilot trial rows.
  Basin view unchanged (old archetypes, same headline).
- Sample fields (cached, open in ~15 s, also offline): Çumra (central), Hadim (toros), Seydişehir, Beyşehir. Buttons
  under the map; a new point shows a "first analysis downloads 25 years of data" note. For demos run the server
  offline: `ROTACAST_OFFLINE=1` (launch config `rotacast-offline`, port 8003); online mode still queries slow NASA
  services even for cached points. Decision 2026-11-14: no further data downloads (west/north/karapinar not cached).
  MODIS NDVI is complete only for Çumra (Seydişehir ~40 %, Toros ~2 %, Beyşehir 0 % of chunks): the other sample
  fields show a "field history unavailable" note instead of Field Memory; cards still work.
- Done (2026-11-14, later): documented yields on the cards (`documented_yield` in zone_crops.json: kimyon ~50 kg/da,
  anason ~72 kg/da, Konya mean TÜİK 2024; çemen's 147 kg/da left out, source unverified), specialty income shown as
  "not computed". Sorghum pilots no longer map to the engine (Konya project = silage, engine = grain sorghum).
  Water-only model for kimyon and çemen (METHODS §7.2, `engine/specialty_water.py`, `knowledge/specialty_water.yaml`):
  Kc/root/p from Pereira et al. 2024 T7–T8, fixed calendar from the Ankara-Gölbaşı rain-fed trials (sow 26 Feb,
  harvest 23 Jul / 2 Aug). Cards: water covers the whole field (`water_coverage` 1, specialty rain-fed = 0 irrigation),
  every other number covers the field part only. Çumra: kimyon ETc ~486 mm, full-irrigation need ~3,844 m³/ha.
- Gap: still not modelled: kişniş, çörekotu, rezene (Kc exists, no local calendar), anason (no Kc), buckwheat,
  perennials; no specialty has income, yield response (Ky) or frost/heat risk. Rain-fed ETa of the specialties is
  conservative (roots capped at Table 8 depth).
- Next: nothing assigned on this branch; regional development screen ("Bölge kalkınması") postponed.
- Open: ask the organisers about pre-event commit dates. Branch pushed (2026-11-14). Regional development screen postponed by @selejder.
- Review fixes (2026-11-14, external check of a clean download): all sample-field cache files are now committed
  (`data/cache`, ~24 MB; Çumra, Toros, Seydişehir, Beyşehir verified offline from a fresh clone). "Income" is labelled
  "estimated gross income" everywhere (price x modelled yield − water cost; seed, fertiliser, fuel, labour, rent not
  deducted) with a glossary tooltip. The water-limit sentence is qualified when a specialty share has no water model.
  Frontend fallbacks refreshed (basin report 13 Nov, field report). `backend/requirements.lock.txt` pins tested
  versions; `.github/workflows/ci.yml` runs offline pytest + check_offline + frontend build. CHIRPS/IMERG license and
  DOI checked (SOURCES.md). README screenshot added (800x500, field cards view).
- Still open from the review: "+" detail-info module (spec needed from @selejder), frontend tests, bundle size
  (~2.3 MB, MapLibre not code-split), regional development screen (postponed).

## Next steps
0. **Beginner/Advanced modes.** Owner: the teammate who received the handoff spec. Others: do not start.
1. **LLM interpretation layer.** Owner: @selejder (repo owner). **Reserved, do not start.** Listed so everyone knows
   the design. Decisions already made:
   - The LLM **never produces data**. All numbers come from the simulation; the LLM only interprets the finished report (`facts`, strategies, evidence).
   - **Optional, on request only.** Nothing runs automatically. A "Bu sonucu bana açıkla / Explain this result" button on each strategy card and on the results page; an "ask a question" box in Advanced mode (questions like "what if I switch to drip?" re-run the simulation and the LLM explains the new result, it never estimates).
   - **Grounded:** every sentence must cite a fact id (f3, f7, ...); sentences with no citation or an unknown id are dropped in code. Each answer carries a note: "Generated by AI; numbers come from the simulation" plus clickable fact ids that open the evidence drawer.
   - **Backend only:** Anthropic Python SDK (`anthropic`), key in `.env` as `ANTHROPIC_API_KEY` (already gitignored), never sent to the browser. New endpoint (e.g. `POST /api/field/explain`) takes the report or its cache key and returns the explanation; stream the text.
   - **Fallbacks:** no key, network failure or a `refusal` stop reason → the buttons are hidden or show "feature off", and the existing deterministic evidence texts stay. The app must work fully without the LLM, including offline demo mode.
   - Model `claude-opus-5-5` (adaptive thinking, low/medium effort for speed); cache explanations per report so repeat clicks cost nothing. TR/EN follows the UI language.
   - Add tests (citation filter, fallback with no key) and declare the AI use in README/submission (SI disclosure).
   - Needs: an Anthropic API key from the user.
2. SMAP + GLDAS validation of the model's soil water (Earthdata access ready); later HLS 30 m field memory,
   ECOSTRESS ET/LST map. Owner: @selejder. Reserved, do not start.
3. Done: README screenshot (field cards). Still to do: a Basin View screenshot / UI check. Owner: unassigned (ask @selejder).
4. Pitch: slides/video script, submission text, SI-usage statement. Owner: unassigned (ask @selejder).
5. Optional: public deploy (single container). Owner: unassigned (ask @selejder).
