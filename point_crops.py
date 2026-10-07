import argparse
import csv
import os
import re
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from pyproj import Transformer

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"

EVALSCRIPT = """
//VERSION=3
function setup() {
  return {input: ["B04", "B03", "B02"], output: {bands: 3, sampleType: "UINT8"}};
}
function evaluatePixel(s) {
  return [2.5 * s.B04 * 255, 2.5 * s.B03 * 255, 2.5 * s.B02 * 255];
}
"""


def get_token():
    # Credentials come from CDSE_USERNAME and CDSE_PASSWORD in .env
    load_dotenv()
    response = requests.post(AUTH_URL, data={
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": os.environ["CDSE_USERNAME"],
        "password": os.environ["CDSE_PASSWORD"],
    })
    response.raise_for_status()
    return response.json()["access_token"]


def read_points(path):
    with open(path, encoding="utf-8-sig") as f:
        return [{**row, "lat": float(row["lat"]), "lon": float(row["lon"])} for row in csv.DictReader(f)]


def folder_name(point_name):
    # Point names like "ZAR2 y ZAR3" become safe folder names like "ZAR2_y_ZAR3"
    # TODO: Fix unsafe folders as soon as detected
    return re.sub(r"\W+", "_", point_name)


def crop_bbox(lon, lat, size):
    """Square of `size` metres centred on the point, in the point's UTM zone, and that zone's EPSG code."""
    epsg = (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    return [x - size / 2, y - size / 2, x + size / 2, y + size / 2], epsg


def search_acquisitions(lon, lat, start, end, token):
    """All Sentinel-2 L2A acquisitions covering the point between start and end, as (datetime, cloud cover)."""
    body = {
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
        "collections": ["sentinel-2-l2a"],
        "limit": 100,
    }
    acquisitions = []
    while True:
        response = requests.post(CATALOG_URL, json=body, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        result = response.json()
        for feature in result["features"]:
            properties = feature["properties"]
            acquisitions.append((datetime.fromisoformat(properties["datetime"]), properties["eo:cloud_cover"]))
        if "next" not in result.get("context", {}):
            return acquisitions
        body["next"] = result["context"]["next"]


def select_acquisitions(acquisitions, per, max_cloud_cover):
    """Least cloudy acquisition of each period, ties broken by closeness to the middle of the period.

    Periods whose least cloudy acquisition is above max_cloud_cover are left out.
    """
    best = {}
    for when, cloud_cover in acquisitions:
        if cloud_cover > max_cloud_cover:
            continue
        if per == "year":
            period, middle = when.year, date(when.year, 7, 1)
        elif per == "month":
            period, middle = (when.year, when.month), date(when.year, when.month, 15)
        else:  # "all"
            period, middle = when.date(), when.date()
        key = (cloud_cover, abs((when.date() - middle).days))
        if period not in best or key < best[period][0]:
            best[period] = (key, when)
    return [when for _, (_, when) in sorted(best.items())]


def download_crop(bbox, epsg, when, resolution, token, path):
    body = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"}},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"timeRange": {"from": f"{when:%Y-%m-%d}T00:00:00Z", "to": f"{when:%Y-%m-%d}T23:59:59Z"}},
            }],
        },
        "output": {
            "resx": resolution,
            "resy": resolution,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": EVALSCRIPT,
    }
    response = requests.post(PROCESS_URL, json=body, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    with open(path, "wb") as f:
        f.write(response.content)


def download_point_crops(
    points_csv="points.csv",
    output_dir="./crops_monthly",
    size=2000,
    resolution=10,
    start="2024-01-01",
    end=None,
    per="month",
    max_cloud_cover=10.0,
):
    """Download Sentinel-2 L2A true colour PNG crops centred on each point of a CSV.

    points_csv: CSV with at least name, lat and lon columns (from kmz_to_csv.py)
    output_dir: crops are saved as <output_dir>/<point name>/<YYYY-MM-DD>.png
    size: side of the square crop in metres
    resolution: metres per pixel (10 is Sentinel-2's native resolution); PNGs are size/resolution pixels wide
    start, end: date range as "YYYY-MM-DD"; end defaults to now
    per: "year", "month" or "all" — one image per period (the least cloudy), or every acquisition
    max_cloud_cover: leave out periods whose least cloudy image has more cloud cover than this (0-100)
    """
    start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else datetime.now(timezone.utc)
    for point in read_points(points_csv):
        token = get_token()  # Fresh token per point, as tokens expire after ~30 minutes
        folder = os.path.join(output_dir, folder_name(point["name"]))
        os.makedirs(folder, exist_ok=True)
        bbox, epsg = crop_bbox(point["lon"], point["lat"], size)
        acquisitions = search_acquisitions(point["lon"], point["lat"], start, end, token)
        for when in select_acquisitions(acquisitions, per, max_cloud_cover):
            path = os.path.join(folder, f"{when:%Y-%m-%d}.png")
            download_crop(bbox, epsg, when, resolution, token, path)
            print(f"{point['name']}: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=download_point_crops.__doc__.splitlines()[0])
    parser.add_argument("--points-csv", default="points.csv")
    parser.add_argument("--output-dir", default="./crops_monthly")
    parser.add_argument("--size", type=float, default=2000, help="crop side in metres")
    parser.add_argument("--resolution", type=float, default=10, help="metres per pixel")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--per", choices=["year", "month", "all"], default="month")
    parser.add_argument("--max-cloud-cover", type=float, default=10.0)
    download_point_crops(**vars(parser.parse_args()))
