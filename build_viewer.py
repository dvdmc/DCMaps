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
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --bg: #f6f6f4; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6b66; --border: #e2e2dd; --accent: #c0392b;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #161615; --panel: #1f1f1d; --text: #ecebe6; --muted: #9c9b94; --border: #34342f; --accent: #e5604f; }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
    font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .layout { display: flex; height: 100%; }
  #map { flex: 1; min-width: 0; }
  aside { width: 440px; max-width: 100%; background: var(--panel); border-left: 1px solid var(--border);
    overflow-y: auto; padding: 20px; }
  @media (max-width: 800px) {
    .layout { flex-direction: column; }
    #map { flex: none; height: 45vh; }
    aside { width: 100%; border-left: none; border-top: 1px solid var(--border); padding: 16px; flex: 1; }
  }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: var(--muted); margin: 0 0 16px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 2px 10px;
    border-radius: 999px; border: 1px solid var(--border); }
  .dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid rgba(0,0,0,.5); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 16px 0; }
  dt { color: var(--muted); }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  .frame { position: relative; width: 100%; aspect-ratio: 1; background: var(--border); border-radius: 6px; overflow: hidden; }
  .frame img { width: 100%; height: 100%; display: block; object-fit: cover; }
  .frame .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); }
  .frame [hidden] { display: none; }
  .controls { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
  .controls input[type=range] { flex: 1; accent-color: var(--accent); }
  button { font: inherit; background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 10px; cursor: pointer; min-width: 36px; }
  button:hover { border-color: var(--muted); }
  .when { display: flex; justify-content: space-between; margin-top: 8px; font-variant-numeric: tabular-nums; }
  .when strong { font-size: 16px; }
  .when span { color: var(--muted); }
  .note { color: var(--muted); font-size: 12px; margin-top: 12px; }
  .legend { background: var(--panel); color: var(--text); padding: 8px 10px; border-radius: 6px;
    border: 1px solid var(--border); line-height: 1.8; }
  .legend div { display: flex; align-items: center; gap: 6px; }
  .placeholder { color: var(--muted); margin-top: 40px; text-align: center; }
</style>
</head>
<body>
<div class="layout">
  <div id="map"></div>
  <aside id="panel"><p class="placeholder">Haz clic en un punto del mapa para ver sus imágenes Sentinel-2.</p></aside>
</div>
<script>
const DATA = __DATA__;
const COLORS = __COLORS__;
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const map = L.map("map").setView([40.3, -3.7], 6);  // Spain
// OSM's tile servers block pages opened from file:// (no Referer) and CARTO needs an API key; Esri needs neither
const basemaps = {
  "Mapa": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Tiles &copy; Esri, HERE, Garmin, OpenStreetMap contributors"
  }),
  "Satélite": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Tiles &copy; Esri, Maxar, Earthstar Geographics"
  }),
};
basemaps["Mapa"].addTo(map);
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
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function monthLabel(m) { const [y, mo] = m.split("-"); return `${MONTHS[+mo - 1]} ${y}`; }

DATA.forEach(p => {
  const marker = L.circleMarker([p.lat, p.lon], {radius: 7, color: "#000", weight: 1, fillColor: color(p), fillOpacity: 0.95})
    .addTo(map).bindTooltip(p.name);
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
    <h1>${esc(p.name)}</h1>
    <p class="sub"><span class="pill"><span class="dot" style="background:${color(p)}"></span>${esc(p.status || "Sin estado")}</span></p>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    <div class="frame"><img id="img" alt=""><div class="empty" id="empty" hidden>Sin imágenes</div></div>
    <div class="controls">
      <button id="prev" title="Anterior (←)">‹</button>
      <input type="range" id="slider" min="0" max="${Math.max(p.frames.length - 1, 0)}" value="${index}">
      <button id="next" title="Siguiente (→)">›</button>
      <button id="play" title="Reproducir">▶</button>
    </div>
    <div class="when"><strong id="month"></strong><span id="date"></span></div>
    <p class="note">Sentinel-2 L2A, color verdadero, centrada en el punto.
      Se muestra la adquisición menos nublada de cada mes.</p>`;
  document.getElementById("slider").addEventListener("input", e => { index = +e.target.value; show(); });
  document.getElementById("prev").addEventListener("click", () => step(-1));
  document.getElementById("next").addEventListener("click", () => step(1));
  document.getElementById("play").addEventListener("click", () => timer ? stop() : play());
  show();
}

function show() {
  const f = current.frames[index];
  const img = document.getElementById("img");
  document.getElementById("empty").hidden = !!f;
  img.hidden = !f;
  if (!f) return;
  img.src = f.src;
  img.alt = `${current.name} ${f.date}`;
  document.getElementById("slider").value = index;
  document.getElementById("month").textContent = monthLabel(f.month);
  document.getElementById("date").textContent = `imagen del ${f.date}`;
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


def build_viewer(points_csv="points.csv", crops_dir="crops_monthly", output_html="viewer.html"):
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
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved {output_html} with {len(data)} points and {sum(len(p['frames']) for p in data)} images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=build_viewer.__doc__.splitlines()[0])
    parser.add_argument("--points-csv", default="points.csv")
    parser.add_argument("--crops-dir", default="crops_monthly")
    parser.add_argument("--output-html", default="viewer.html")
    build_viewer(**vars(parser.parse_args()))
