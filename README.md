# DCMaps

Interactive map for monthly Sentinel-2 satellite images of the data centres in Aragón.

The points come from a Google My Maps KMZ. For each point the scripts download a small true colour crop per month from the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu) (CDSE). `viewer.html` then shows the points on a map of Spain; clicking a point shows its data and its images with a month slider.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and a free CDSE account. Create a `.env` file with the account's credentials:

```
CDSE_USERNAME=you@example.com
CDSE_PASSWORD=...
```

## Usage

```
uv run kmz_to_csv.py      # map_online_info.kmz -> points.csv
uv run point_crops.py     # points.csv -> crops_monthly/<point>/<YYYY-MM-DD>.png
uv run build_viewer.py    # points.csv + crops_monthly/ -> viewer.html
```

Open `viewer.html` in a browser. It must stay next to `crops_monthly/`, and the background map needs internet.

## Scripts

| Script | What it does |
|---|---|
| `kmz_to_csv.py [kmz] [csv]` | Reads the KMZ (following its link to the online Google map) and writes one row per point: `name, lat, lon, operator, municipality, power_mw, status, description`. |
| `point_crops.py` | Downloads a PNG crop centred on each point for each period. |
| `build_viewer.py` | Writes `viewer.html` with the points, their data and the paths to their crops. |

`point_crops.py` options (`--help` for all):

| Option | Default | Meaning |
|---|---|---|
| `--size` | `2000` | Side of the square crop, in metres |
| `--resolution` | `10` | Metres per pixel (10 is Sentinel-2's finest); a crop is `size / resolution` pixels wide |
| `--start` / `--end` | `2024-01-01` / today | Date range |
| `--per` | `month` | `year`, `month` or `all` (every acquisition) |
| `--max-cloud-cover` | `10` | Periods whose least cloudy image is cloudier than this (%) are left out |
| `--points-csv` / `--output-dir` | `points.csv` / `crops_monthly` | Input and output |

## Notes

- Within each period the least cloudy image is used. The cloud percentage is Sentinel-2's estimate for the whole 110 km tile, so a crop can occasionally still show a cloud.
- Images are Sentinel-2 L2A (atmospherically corrected) true colour, fetched through the Sentinel Hub Process API on CDSE.
- `points.csv` is regenerated from the live Google map, so edits to that map show up the next time `kmz_to_csv.py` runs.
- A run downloads every crop again; the full monthly set (25 points × ~33 months) takes about 20 minutes.