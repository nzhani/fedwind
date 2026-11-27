# Dataset catalogue (requirement DR-10)

Every dataset the project uses, with its source, licence or terms of use, and where it is used.
Add a row **before** a new dataset is used in an experiment, the report or the website.
All times are UTC (DR-09).

## Datasets used for training, evaluation and forecasts

| ID | Content | Source | Licence / terms | Period, resolution | Where in the repo | Used for |
|---|---|---|---|---|---|---|
| **KZMET** (wind, 5 lab sites) | `WS50M` wind speed at 50 m (target), `WD50M` direction, `T2M` temperature, `PS` surface pressure | NASA Langley Research Center **POWER** project, hourly point API (`power.larc.nasa.gov/api/temporal/hourly/point`, community RE) | NASA open data: free to use without restriction; POWER asks users to acknowledge the source (text below) | 2015-01-01 to 2024-12-31, hourly | `Long-term_Forecasting/datasets/custom/nasa_<site>.csv`; deployment copies in `<data>/sites/<site>/` | Federated training and evaluation (wind), lab-site forecasts on the website |
| **KZSOLAR** (solar, 5 lab sites) | `ALLSKY_SFC_SW_DWN` all-sky GHI (target), `CLRSKY_SFC_SW_DWN` NASA clear-sky GHI (checks only), `T2M` | NASA POWER, as above | as above | 2015-01-01 to 2024-12-31, hourly | `Long-term_Forecasting/datasets/solar/nasa_<site>.csv`; `<data>/sites/<site>/` | Federated training and evaluation (solar), lab-site forecasts |
| **Simulated plants** | `WS50M` (wind) or `ALLSKY_SFC_SW_DWN` (solar) at the plant's coordinates | NASA POWER, fetched by the site agent (`site_agent/sources/nasa_power.py`) | as above | last 40 days (wind) / 150 days (solar) for reporting; with `SIM_HISTORY_YEARS`, whole past years for training | on the plant only: `data/store/` of the site kit | Demo plants: heartbeat, quality counts, training store, shared forecast window |
| **Real plant data** | hourly exports by the plant (data contract in the kit's `data/README.md`) | each plant operator | stays the operator's; shared only as model updates, and (with consent) a 14-day window kept 30 days | the plant's own | on the plant only | Training at the plant; central forecasts with consent |

Lab sites (coordinates are approximate city centres, `deploy/seed/sites.json`):

| Wind | lat, lon | Solar | lat, lon |
|---|---|---|---|
| almaty | 43.24, 76.89 | konaev | 43.87, 77.07 |
| zhezkazgan | 47.78, 67.71 | shymkent | 42.32, 69.59 |
| aktau | 43.65, 51.17 | kyzylorda | 44.85, 65.51 |
| taraz | 42.90, 71.37 | saran | 49.79, 72.84 |
| aktobe | 50.28, 57.17 | turkistan | 43.30, 68.27 |

How to reproduce: `python Long-term_Forecasting/scripts/download_kzmet.py` (wind) and
`... --energy solar` (solar). NASA marks missing values with -999; the loader interpolates them.

**Acknowledgement to use in the report and on slides** (as requested by the POWER project):
"These data were obtained from the NASA Langley Research Center (LaRC) POWER Project funded through
the NASA Earth Science/Applied Science Program."

## Registry entries without data in the repository

`my_flower_app/task.py` (`DATASET_REGISTRY`) also names **VNMET**, **GREECE**, **CAPITALS** and
**MIXED5** from earlier experiments. Their files are not in the repository and they are not used in
the fall results. Before any of them is used again, add its source and licence here.

## Other third-party assets

| Asset | Source | Licence | Used for |
|---|---|---|---|
| GPT-2 (small) weights | OpenAI, via Hugging Face `gpt2` | MIT | Frozen backbone of the forecasting model |
| Kazakhstan outline and lakes | Natural Earth 1:50m vectors | Public domain | Federation map on the website (`federated-website/scripts/make_kz_map.py`) |
| Geist, Instrument Serif, Fragment Mono fonts | Vercel; Instrument; Weiweihuanghuang (Google Fonts) | SIL Open Font License 1.1 | Website typography (self-hosted in `federated-website/app/fonts/`) |
