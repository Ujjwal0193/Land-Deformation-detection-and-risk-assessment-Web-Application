# MineGuard: Land Deformation Detection & Risk Assessment

**Monitoring ground movement around mines from space, using Sentinel-1 radar (InSAR).**
Pick a mine on a map, choose a time window, and MineGuard finds the satellite data, processes it through ESA SNAP, locates the active pit and shows how the ground is moving.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_19-TypeScript-61DAFB?logo=react&logoColor=black)
![ESA SNAP](https://img.shields.io/badge/ESA-SNAP-003247)
![Sentinel-1](https://img.shields.io/badge/Sentinel--1-SAR-0B3D91)

## Why it matters

Open-pit mines and coalfields deform slowly before slope failures and subsidence events. Ground surveys are expensive and patchy; Sentinel-1 revisits every site every few days for free. MineGuard turns that raw radar archive into a repeatable, mostly hands-off monitoring workflow.

## What it does

- **Finds the data automatically.** Searches and downloads Sentinel-1 SLC scenes from the Copernicus Data Space Ecosystem (OData API, OAuth2), keeping a consistent orbit track so scenes line up.
- **Runs a headless InSAR pipeline.** A SNAP Graph Processing Tool workflow: TOPSAR-Split (IW2, VV) → Apply-Orbit-File → Back-Geocoding with SRTM DEM → Interferogram → TOPSAR-Deburst.
- **Locates the active pit.** Uses interferometric coherence (stable rock ≈ 0.8–1.0, active mining ≈ 0.0–0.3) to find the mine centre and mask low-quality pixels.
- **Measures movement.** Converts phase change to line-of-sight displacement and tracks it across 2023 → 2024 → 2025, exported as plots and CSV.
- **Web app for the workflow.** React + TypeScript dashboard with an interactive map (Leaflet / Mapbox): search a mine, pick dates, crop the area, follow processing, choose hotspots, view results. FastAPI backend with a directory watcher that picks up new scenes.

Case study: **Chuquicamata, Chile**, one of the largest open-pit copper mines in the world. The mine catalogue also includes sites such as Jharia (India).

## Architecture

```
React + TS dashboard (map, timeline, crop, hotspots)
            │  REST
            ▼
FastAPI backend ── download / processing / hotspot / summary APIs
            │
            ├── CDSE search + download manager ──► Sentinel-1 SLC scenes
            ├── processing queue ──► ESA SNAP GPT graph (headless)
            └── analysis: coherence, pit detection, LOS displacement ──► plots + CSV
```

## Repository layout

| Path | What |
|---|---|
| `MineGuard_Proto/mineguard/frontend/` | React 19 + TypeScript + Vite dashboard |
| `MineGuard_Proto/mineguard/backend/` | FastAPI app (`main.py`), APIs and scene services |
| `MineGuard_Proto/pipeline/` | Download manager and processing queue |
| `MineGuard_Proto/src/` | InSAR analysis, SNAP graph (`graphs/process_graph.xml`), plotting |
| `MineGuard_Proto/config/` | Pipeline config and hotspot definitions |
| `mineguard_ieee_report.tex` | Technical report (IEEE format) |

## Run it

**Prerequisites:** Python 3.10+, Node.js, [ESA SNAP](https://step.esa.int/main/download/snap-download/) with `gpt` on your PATH, and a free [Copernicus Data Space](https://dataspace.copernicus.eu/) account.

```bash
cd MineGuard_Proto
pip install -r requirements.txt
```

Create a `.env` with your Copernicus credentials:

```
CDSE_USER=your_email@example.com
CDSE_PASS=your_password
```

Command-line pipeline (search → download → process → plot):

```bash
python run_pipeline.py
```

Web app:

```bash
# terminal 1 (from MineGuard_Proto/)
uvicorn mineguard.backend.main:app --port 8000
# terminal 2
cd mineguard/frontend && npm install && npm run dev
```

## Scope and limitations

This is a research prototype. Phase unwrapping (SNAPHU) is deliberately skipped to keep processing light, so displacement is measured within one phase cycle (about 2.8 cm) and is best read as an indicator of active movement rather than absolute subsidence. Line-of-sight motion is interpreted as vertical. Adding unwrapping and a time-series method (PS / SBAS) is the natural next step.

## License

Academic and research use.
