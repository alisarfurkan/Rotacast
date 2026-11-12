# Sources and citations

Every dataset, table, library and reference used by Rotacast is listed here with an id.
Code and data files refer to these ids (`source_id`, `sources:`). Add an entry before you use a source.

| id | Source | Used for | License / access | URL |
|---|---|---|---|---|
| nasa_power | NASA POWER Project, Daily API, Agroclimatology community, NASA Langley Research Center | Daily weather, radiation, soil wetness | Open data, credit NASA/POWER | https://power.larc.nasa.gov/ |
| modis_mod13q1 | Didan, K. (2021). MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061. NASA EOSDIS LP DAAC; via ORNL DAAC MODIS/VIIRS Web Service | NDVI time series (Field Memory) | Public, no auth | https://modis.ornl.gov/data/modis_webservice.html |
| modis_mcd12q1 | Friedl, M., Sulla-Menashe, D. (2022). MCD12Q1 MODIS/Terra+Aqua Land Cover Type Yearly L3 Global 500m SIN Grid V061. NASA EOSDIS LP DAAC; via ORNL DAAC web service | Land cover class | Public, no auth | https://modis.ornl.gov/data/modis_webservice.html |
| grace_csr_mascon | Save, H., Bettadpur, S., Tapley, B.D. (2016). High resolution CSR GRACE RL05 mascons, JGR Solid Earth 121. Data: CSR GRACE/GRACE-FO RL06.3 mascons, doi:10.15781/cgq9-nh24 | Terrestrial water storage trend (regional.py) | NASA data policy | https://download.csr.utexas.edu/outgoing/grace/RL0603_mascons/ |
| soilgrids | Poggio, L. et al. (2021). SoilGrids 2.0. SOIL 7:217–240 | Soil texture, field capacity, wilting point (0–30 cm) | CC BY 4.0 | https://rest.isric.org/soilgrids/v2.0/ |
| soil_default | Documented regional default soil profile (see connectors/soil.py) | Fallback soil profile when SoilGrids is unavailable | Assumption | https://soilgrids.org/ |
| saxton_rawls_2006 | Saxton, K.E., Rawls, W.J. (2006). Soil water characteristic estimates by texture and organic matter. SSSAJ 70:1569–1578 | Field capacity and wilting point from texture and SOC | Published article | https://doi.org/10.2136/sssaj2005.0117 |
| srtm_terrain_tiles | AWS Open Data Terrain Tiles (Mapzen terrarium), SRTM-derived (NASA SRTM) | Elevation and slope | Public | https://registry.opendata.aws/terrain-tiles/ |
| fao56 | Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop evapotranspiration. FAO Irrigation and Drainage Paper 56 | ET0, crop coefficients, water balance | Open publication | https://www.fao.org/4/x0490e/x0490e00.htm |
| fao33 | Doorenbos, J., Kassam, A.H. (1979). Yield response to water. FAO Irrigation and Drainage Paper 33 | Yield response to water (crops.yaml) | Open publication | https://www.fao.org/land-water/databases-and-software/crop-information/en/ |
| fao66 | Steduto, P., Hsiao, T.C., Fereres, E., Raes, D. (2012). Crop yield response to water. FAO Irrigation and Drainage Paper 66 | Yield response to water (reference) | Open publication | https://www.fao.org/4/i2800e/i2800e.pdf |
| ecocrop | FAO ECOCROP database | Crop climatic suitability (crops.yaml) | Open access (FAO) | https://gaez.fao.org/pages/ecocrop |
| faostat | FAOSTAT | Crop reference data (crops.yaml) | CC BY 4.0 | https://www.fao.org/faostat/ |
| tuik | TÜİK (TurkStat) crop production statistics | Turkish crop production reference (crops.yaml) | Public statistics | https://data.tuik.gov.tr/ |
| tmo | Toprak Mahsulleri Ofisi purchase prices | Turkish purchase price reference (crops.yaml) | Public website | https://www.tmo.gov.tr/ |
| rusle_ah703 | Renard, K.G. et al. (1997). RUSLE, USDA Agriculture Handbook 703 | Cover-management factor C for erosion (crops.yaml, rotations.py) | Public domain | https://www.ars.usda.gov/ |
| peoples2009 | Peoples, M.B. et al. (2009). Symbiosis 48:1–17, doi:10.1007/BF03179980 | Legume nitrogen credit reference (crops.yaml) | Journal article, see DOI | https://doi.org/10.1007/BF03179980 |
| scs_cn | USDA-SCS curve number method (NEH-4 / TR-55) | Daily runoff and effective precipitation, CN 75 (engine/waterbalance.py) | Public domain | https://www.nrcs.usda.gov/ |
| konya_irrigated_share | KOP Bölgesi Sosyo-Ekonomik Göstergeler (Dec 2024): Konya irrigated land 828,948 ha; TÜİK 2020 agricultural area 1,859,079 ha (both quoted in Konya İl Tarım ve Orman Müdürlüğü, 2026 Konya Tarımı) → share 0.446 | Irrigated share for Konya (regional.py `BasinParams.irrigated_share`) | Government statistics | https://konya.tarimorman.gov.tr/Belgeler/kitap/%C4%B0l_Tar%C4%B1m_ve_Orman_Ocak_26_4DonemV2.pdf |
| gpm_imerg | Huffman, G.J. et al. GPM IMERG Final Precipitation L3 0.1° (V07), NASA GES DISC (fallback; DOI to verify: 10.5067/GPM/IMERG/3B-HH/07); daily series via NASA SERVIR ClimateSERV (datatype 26) | Fallback satellite rain for POWER bias correction | Public, no auth (NASA data policy) | https://gpm.nasa.gov/data/imerg |
| chirps | Funk, C. et al. (2015) The climate hazards infrared precipitation with stations (CHIRPS), Scientific Data 2:150066, doi:10.1038/sdata.2015.66; UCSB Climate Hazards Center, daily series via NASA SERVIR ClimateSERV (datatype 0) | Primary satellite-gauge rain for monthly bias correction of POWER rain | Public, no auth | https://www.chc.ucsb.edu/data/chirps |

TODO verify: gpm_imerg, chirps. These ids are in the code (connectors/precip.py, report.py SOURCES) but were not in the citation list supplied for this update. The row text is taken from the code; check the license and citation wording.

## Methods & statistics

- Mann, H.B. (1945). Nonparametric tests against trend. Econometrica 13:245–259.
- Kendall, M.G. (1975). Rank Correlation Methods. Charles Griffin.
- Sen, P.K. (1968). Estimates of the regression coefficient based on Kendall's tau. JASA 63:1379–1389.
- Savitzky, A., Golay, M.J.E. (1964). Smoothing and differentiation of data by simplified least squares procedures. Anal. Chem. 36:1627–1639.
- Jönsson, P., Eklundh, L. (2004). TIMESAT, a program for analyzing time-series of satellite sensor data. Computers & Geosciences 30:833–845.

## Software

- React (MIT)
- Vite (MIT)
- TypeScript (Apache-2.0)
- Tailwind CSS (MIT)
- MapLibre GL JS (BSD-3-Clause)
- Apache ECharts (Apache-2.0)
- FastAPI (MIT)
- NumPy, SciPy, pandas (BSD)
- xarray (Apache-2.0)
- Fonts: Fraunces and Inter (SIL Open Font License)
- Map tiles: Esri World Imagery ("Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community")
- Map tiles: OpenStreetMap (ODbL, © OpenStreetMap contributors)

## SI tools

- Anthropic Claude (Opus 5.5 orchestrator; Sonnet 5.5 and Haiku 5.5 worker agents via Claude Code) used for code generation, documentation and review.
