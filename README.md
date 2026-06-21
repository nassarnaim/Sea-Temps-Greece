# 🌊 Sea-Temps Greece

Automatically compiles and monitors **real-time sea surface temperature (SST)** plus
**wind &amp; weather forecasts** for nine Greek islands, and publishes a self-updating
dashboard. Refreshes **every 6 hours** via GitHub Actions — no servers to run.

**Islands:** Spetses, Serifos, Milos, Santorini, Rhodes, Paros (Aegean) ·
Kefalonia, Corfu, Zakynthos (Ionian).

## How it works

```
GitHub Actions (cron, every 6h)
  └─ python -m src.main
        ├─ fetch every source for every island (failure-tolerant)
        ├─ merge into a normalized per-island report
        └─ write JSON to data/  ──►  mirror into site/data/
  └─ commit data/  +  deploy site/ to GitHub Pages
```

A dependency-free static dashboard (`site/`, HTML + Chart.js) reads the JSON and shows
per-island SST, current conditions, 7-day forecast charts, a source-health strip, and
marine advisories.

## Data sources

| Source | Role | Access |
| --- | --- | --- |
| **Copernicus Marine (CMEMS)** | Authoritative SST | `copernicusmarine` toolbox (free account) |
| **Open-Meteo** | Backbone: wind/weather/waves + fallback SST | Free, no key |
| **POSEIDON / HCMR** | Greek-regional forecast + advisory | Best-effort (THREDDS/OPeNDAP) |
| **HNMS / EMY** | Marine bulletin & warnings | Best-effort (web) |
| **CEAMed** | Mediterranean SST anomaly (climate context) | Best-effort, **monthly, basin-wide** |

The merge priority for current SST is **CMEMS → POSEIDON → Open-Meteo**. Every source is
isolated: if one fails, the run still completes and the dashboard flags it. The Open-Meteo
backbone guarantees the system always produces data, even with no credentials.

> CEAMed is a **basin-wide monthly trend**, not a per-island live feed — it appears as
> shared climate context, not as each island's SST.

## Run locally

```bash
pip install -r requirements.txt        # copernicusmarine deps optional for backbone-only
python -m src.main                      # writes data/ and mirrors into site/data/
cd site && python -m http.server 8000   # open http://localhost:8000
```

Without CMEMS credentials the pipeline runs on the keyless backbone (Open-Meteo) and the
CMEMS source reports itself disabled.

## Enabling authoritative CMEMS SST

CMEMS needs **three** values; without all three it is skipped and the Open-Meteo
backbone provides SST (the rest of the system is unaffected).

1. Create a free account at <https://marine.copernicus.eu>.
2. Add repository secrets **`CMEMS_USERNAME`** and **`CMEMS_PASSWORD`**
   (Settings → Secrets and variables → Actions).
3. Add **`CMEMS_DATASET_ID`** — the exact catalogue id of the SST product you want.
   Find it once with the toolbox and set it as a repo **variable** or **secret**:

   ```bash
   pip install copernicusmarine
   copernicusmarine login                 # uses your account
   copernicusmarine describe --contains SST_MED_SST_L4_NRT_OBSERVATIONS_010_004
   # copy the dataset_id (e.g. a Mediterranean L4 NRT SST daily product) and set
   # it as CMEMS_DATASET_ID. The global L4 OSTIA NRT product also covers Greek waters.
   ```

The pipeline opens that dataset once for a Greek-wide box, loads the latest SST grid,
and samples each island — CMEMS SST then overrides the backbone value.

> Why explicit? CMEMS catalogue ids change and a wrong-but-existing id can be very slow
> to open and stall the scheduled run, so the id is required rather than guessed.

## GitHub Pages setup

In **Settings → Pages**, set **Source: GitHub Actions**. The `update.yml` workflow builds
and deploys the dashboard on every run and via **Run workflow** (manual dispatch).

## Configuration

Islands live in [`config/islands.yaml`](config/islands.yaml) — each has a land coordinate
(air weather) and an offshore sea coordinate (marine grids, to avoid land-masking), plus a
`region` (`aegean`/`ionian`). Add or adjust islands there.

## Layout

```
config/islands.yaml          island definitions
src/                         pipeline (config, model, sources/, render, main)
data/                        generated JSON (committed: latest, per-island, history)
site/                        static dashboard (GitHub Pages)
tests/                       pytest (mocked HTTP + merge/render)
.github/workflows/update.yml schedule + Pages deploy
```

## Tests

```bash
pytest -q
```
