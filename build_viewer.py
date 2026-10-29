import argparse
import glob
import json
import os

from point_crops import folder_name, read_points

STATUS_COLORS = {
    "En operación": "limegreen",
    "En construcción": "red",
    "En aprobación": "gold",
    "En proyección": "deepskyblue",
}

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Centros de datos Aragón</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  /* Colours and font of nocentrosdedatosaragon.org */
  :root {
    --bg: #023047; --panel: #023047; --card: #1f3640; --text: #ffb703; --muted: #8ecae6;
    --border: rgba(142, 202, 230, .25); --accent: #fb8500;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
    font: 15px/1.5 "Roboto", system-ui, sans-serif; }
  .layout { display: flex; height: 100%; }
  #map { flex: 1; min-width: 0; }
  aside { width: 440px; max-width: 100%; background: var(--panel); border-left: 1px solid var(--border);
    overflow-y: auto; padding: 20px; }
  @media (max-width: 800px) {
    .layout { flex-direction: column; }
    #map { flex: none; height: 45vh; }
    aside { width: 100%; border-left: none; border-top: 1px solid var(--border); padding: 16px; flex: 1; }
  }
  h1 { font-size: 26px; font-weight: 700; margin: 0 0 6px; }
  .sub { color: var(--muted); margin: 0 0 16px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 2px 10px;
    border-radius: 999px; border: 1px solid var(--border); }
  .dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid rgba(0,0,0,.5); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 16px 0; }
  dt { color: var(--muted); }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  .frame { position: relative; width: 100%; aspect-ratio: 1; background: var(--card); border-radius: 16px; overflow: hidden; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; }
  .frame .month { position: absolute; top: 10px; left: 10px; padding: 2px 10px; border-radius: 8px;
    background: rgba(2, 48, 71, .8); font-weight: 700; font-variant-numeric: tabular-nums; }
  .controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .controls input[type=range] { flex: 1; accent-color: var(--accent); }
  button { font: inherit; font-weight: 500; background: var(--card); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 4px 10px; cursor: pointer; min-width: 36px; }
  button:hover { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .legend, .leaflet-control-layers { background: var(--card); color: var(--text); padding: 8px 10px;
    border-radius: 12px; border: 1px solid var(--border); line-height: 1.8; }
  .leaflet-container { background: var(--card); font-family: inherit; }
  .legend div { display: flex; align-items: center; gap: 6px; }
  .placeholder { color: var(--muted); margin-top: 40px; text-align: center; }
</style>
</head>
<body>
<div class="layout">
  <div id="map"></div>
  <aside id="panel"><p class="placeholder">Haz clic en un punto del mapa para ver su información e imágenes satelitales</p></aside>
</div>
<script>
const DATA = __DATA__;
const COLORS = __COLORS__;
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const map = L.map("map").fitBounds(DATA.map(p => [p.lat, p.lon]), {padding: [40, 40]});  // Zoom to the points (Aragón)
// OSM's tile servers block pages opened from file:// (no Referer) and CARTO needs an API key; Esri needs neither
const basemaps = {
  "Mapa": L.layerGroup([
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16, attribution: "Tiles &copy; Esri, HERE, Garmin, OpenStreetMap contributors"
    }),
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {maxZoom: 16}),
  ]),
  "Satélite": L.layerGroup([
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Tiles &copy; Esri, Maxar, Earthstar Geographics"
    }),
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {maxZoom: 19}),
  ]),
};
basemaps["Satélite"].addTo(map);
L.control.layers(basemaps, null, {position: "topright"}).addTo(map);

const legend = L.control({position: "bottomleft"});
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = Object.entries(COLORS).map(([s, c]) => `<div><span class="dot" style="background:${c}"></span>${s}</div>`).join("")
    + `<div><span class="dot" style="background:#fff"></span>Otros</div>`;
  return div;
};
legend.addTo(map);

const panel = document.getElementById("panel");
let current = null, index = 0, timer = null, selectedMarker = null;

function color(p) { return COLORS[p.status] || "#ffffff"; }
// Shown names are municipality + number (HUE2 -> "Huesca 2"); points without a municipality
// take it from another point with the same code prefix (ZAR2 y ZAR3 -> "Zaragoza 2 y 3")
const TOWNS = Object.fromEntries(DATA.filter(p => p.municipality).map(p => [p.name.match(/^[A-Za-z]+/)[0], p.municipality]));
function label(p) {
  const town = p.municipality || TOWNS[p.name.match(/^[A-Za-z]+/)[0]];
  return town ? `${town} ${p.name.replace(/[A-Za-z]+(?=[0-9])/g, "")}` : p.name;
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function monthLabel(m) { const [y, mo] = m.split("-"); return `${MONTHS[+mo - 1]} ${y}`; }

DATA.forEach(p => {
  const marker = L.circleMarker([p.lat, p.lon], {radius: 7, color: "#000", weight: 1, fillColor: color(p), fillOpacity: 0.95})
    .addTo(map).bindTooltip(label(p));
  marker.on("click", () => select(p, marker));
});

function select(p, marker) {
  stop();
  if (selectedMarker) selectedMarker.setStyle({weight: 1, radius: 7});
  marker.setStyle({weight: 3, radius: 9});
  selectedMarker = marker;
  // Keep the same month when switching between points, if that point has it
  const month = current && current.frames[index] ? current.frames[index].month : null;
  current = p;
  const same = p.frames.findIndex(f => f.month === month);
  index = same >= 0 ? same : p.frames.length - 1;
  p.frames.forEach(f => { new Image().src = f.src; });  // preload for smooth sliding
  render();
}

function render() {
  const p = current;
  const rows = [
    ["Operador", p.operator], ["Municipio", p.municipality], ["Consumo", p.power_mw ? `${p.power_mw} MW` : ""],
    ["Lat, lon", `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`], ["Descripción", p.description]
  ].filter(([, v]) => v !== "" && v != null);
  panel.innerHTML = `
    <h1>${esc(label(p))}</h1>
    <p class="sub"><span class="pill"><span class="dot" style="background:${color(p)}"></span>${esc(p.status || "Sin estado")}</span></p>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  if (!p.frames.length) return;  // Only points under construction or in operation have images
  panel.innerHTML += `
    <div class="controls">
      <button id="prev" title="Anterior (←)">‹</button>
      <input type="range" id="slider" min="0" max="${Math.max(p.frames.length - 1, 0)}" value="${index}">
      <button id="next" title="Siguiente (→)">›</button>
      <button id="play" title="Reproducir">▶</button>
    </div>
    <div class="frame"><img id="img" alt=""><span class="month" id="month"></span></div>`;
  document.getElementById("slider").addEventListener("input", e => { index = +e.target.value; show(); });
  document.getElementById("prev").addEventListener("click", () => step(-1));
  document.getElementById("next").addEventListener("click", () => step(1));
  document.getElementById("play").addEventListener("click", () => timer ? stop() : play());
  show();
}

function show() {
  const f = current.frames[index];
  const img = document.getElementById("img");
  img.src = f.src;
  img.alt = `${label(current)} ${f.date}`;
  document.getElementById("slider").value = index;
  document.getElementById("month").textContent = monthLabel(f.month);
}

function step(d) {
  if (!current || !current.frames.length) return;
  index = (index + d + current.frames.length) % current.frames.length;
  show();
}
function play() { timer = setInterval(() => step(1), 700); document.getElementById("play").textContent = "❚❚"; }
function stop() {
  clearInterval(timer); timer = null;
  const b = document.getElementById("play"); if (b) b.textContent = "▶";
}

document.addEventListener("keydown", e => {
  if (e.key === "ArrowLeft") { stop(); step(-1); }
  if (e.key === "ArrowRight") { stop(); step(1); }
});
</script>
</body>
</html>
"""


def build_viewer(points_csv="points.csv", crops_dir="output/crops_monthly", output_html="output/viewer.html"):
    """Write an HTML page with a map of the points; clicking one shows its crops with a month slider.

    Image paths are relative to the HTML file, so keep it next to crops_dir.
    """
    base = os.path.dirname(os.path.abspath(output_html))
    data = []
    for point in read_points(points_csv):
        frames = []
        for path in sorted(glob.glob(os.path.join(crops_dir, folder_name(point["name"]), "*.png"))):
            day = os.path.splitext(os.path.basename(path))[0]
            src = os.path.relpath(path, base).replace(os.sep, "/")
            frames.append({"month": day[:7], "date": day, "src": src})
        data.append({**point, "frames": frames})
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__COLORS__", json.dumps(STATUS_COLORS, ensure_ascii=False))
    os.makedirs(base, exist_ok=True)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved {output_html} with {len(data)} points and {sum(len(p['frames']) for p in data)} images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=build_viewer.__doc__.splitlines()[0])
    parser.add_argument("--points-csv", default="points.csv")
    parser.add_argument("--crops-dir", default="output/crops_monthly")
    parser.add_argument("--output-html", default="output/viewer.html")
    build_viewer(**vars(parser.parse_args()))
