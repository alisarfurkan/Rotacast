# Rotacast frontend (WP4)

Vite + React 19 + TypeScript + Tailwind CSS 4 + MapLibre GL + Apache ECharts.

## Run

```bash
npm install
npm run dev      # http://localhost:5173  (proxies /api -> http://localhost:8000)
npm run build    # type-check + production build into dist/
```

## Mock vs live

- `analyzeField()` in `src/api.ts` POSTs to `/api/field/analyze`.
- Add `?mock=1` to the URL to force the bundled report `src/mock/fieldReport.konya.json`.
- If the backend is unreachable (network error / 5xx / non-JSON), the mock is used automatically and a banner says so.

## Layout

- `src/types.ts` - FieldReport request/response types (docs/CONTRACTS.md section 4)
- `src/i18n.ts` - all UI strings (tr default, en)
- `src/crops.ts` - crop ids, names, categories
- `src/components/` - UI sections (Header, FieldPicker, InputPanel, FieldMemory, ClimateShift, Strategies, EvidenceDrawer, Footer, BasinPlaceholder, charts)
