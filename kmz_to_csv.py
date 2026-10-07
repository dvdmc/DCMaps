import csv
import sys
import zipfile
import xml.etree.ElementTree as ET

import requests

NS = {"kml": "http://www.opengis.net/kml/2.2"}
DESCRIPTION_FIELDS = ["operator", "municipality", "power_mw", "status"]


def read_kml(kmz_path):
    """ Read a KML file from a KMZ archive and return the root element."""
    with zipfile.ZipFile(kmz_path) as z:
        kml_name = next(n for n in z.namelist() if n.endswith(".kml"))
        return ET.fromstring(z.read(kml_name))


def resolve_network_links(root):
    # The KMZ may only point to a remote map (e.g. Google My Maps); fetch it
    hrefs = [el.text.strip() for el in root.findall(".//kml:NetworkLink/kml:Link/kml:href", NS)]
    if not hrefs:
        return [root]
    roots = []
    for href in hrefs:
        url = href + ("&" if "?" in href else "?") + "forcekml=1"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        roots.append(ET.fromstring(response.content))
    return roots


def extract_points(root):
    for placemark in root.iter(f"{{{NS['kml']}}}Placemark"):
        coords = placemark.find(".//kml:Point/kml:coordinates", NS)
        if coords is None:
            continue
        lon, lat, *_ = coords.text.strip().split(",")
        name = placemark.findtext("kml:name", default="", namespaces=NS).strip()
        description = placemark.findtext("kml:description", default="", namespaces=NS).strip()
        # Descriptions are tab-separated: operator, municipality, power demand (MW), status
        parts = description.split("\t")
        row = {"name": name, "lat": float(lat), "lon": float(lon)}
        if len(parts) == len(DESCRIPTION_FIELDS):
            row.update(zip(DESCRIPTION_FIELDS, parts))
            row["power_mw"] = float(row["power_mw"].replace(",", "."))
        else:
            row["description"] = description
        yield row


def main(kmz_path="map_online_info.kmz", csv_path="points.csv"):
    rows = [row for root in resolve_network_links(read_kml(kmz_path)) for row in extract_points(root)]
    fieldnames = ["name", "lat", "lon", *DESCRIPTION_FIELDS, "description"]
    # utf-8-sig so Excel shows accented characters correctly
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} points to {csv_path}")


if __name__ == "__main__":
    main(*sys.argv[1:])
