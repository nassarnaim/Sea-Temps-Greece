"use strict";

// WMO weather code -> short label + emoji (subset, good enough for a glance).
const WMO = {
  0: ["Clear", "☀️"], 1: ["Mainly clear", "🌤️"], 2: ["Partly cloudy", "⛅"],
  3: ["Overcast", "☁️"], 45: ["Fog", "🌫️"], 48: ["Rime fog", "🌫️"],
  51: ["Light drizzle", "🌦️"], 53: ["Drizzle", "🌦️"], 55: ["Heavy drizzle", "🌧️"],
  61: ["Light rain", "🌦️"], 63: ["Rain", "🌧️"], 65: ["Heavy rain", "🌧️"],
  71: ["Light snow", "🌨️"], 73: ["Snow", "🌨️"], 75: ["Heavy snow", "❄️"],
  80: ["Showers", "🌦️"], 81: ["Showers", "🌧️"], 82: ["Violent showers", "⛈️"],
  95: ["Thunderstorm", "⛈️"], 96: ["Thunderstorm + hail", "⛈️"], 99: ["Thunderstorm + hail", "⛈️"],
};

function wmoText(code) {
  const e = WMO[code];
  return e ? `${e[1]} ${e[0]}` : "—";
}

function degToArrow(deg) {
  if (deg == null) return "";
  const dirs = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"];
  return dirs[Math.round(deg / 45) % 8];
}

function fmt(v, digits = 1, unit = "") {
  return v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(digits)}${unit}`;
}

let charts = [];

async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function renderSourceStrip(runSources) {
  const strip = document.getElementById("source-strip");
  strip.innerHTML = "";
  (runSources || []).forEach((s) => {
    const pill = document.createElement("span");
    pill.className = "source-pill";
    pill.title = s.message || "";
    pill.innerHTML = `<span class="dot ${s.ok ? "ok" : "fail"}"></span>${s.name}`;
    strip.appendChild(pill);
  });
}

function renderCards(latest) {
  const root = document.getElementById("cards");
  root.innerHTML = "";
  latest.islands.forEach((isl) => {
    const c = isl.conditions || {};
    const card = document.createElement("article");
    card.className = "card";
    card.tabIndex = 0;
    const anomaly = isl.climate && isl.climate.anomaly_c != null
      ? `<div class="anomaly">Med SST anomaly: ${fmt(isl.climate.anomaly_c, 2, "°C")}</div>` : "";
    const advisory = (isl.advisories && isl.advisories.length)
      ? `<div class="card-advisory">⚠︎ ${isl.advisories.length} advisory${isl.advisories.length > 1 ? "ies" : ""} — click for details</div>` : "";
    card.innerHTML = `
      <div class="card-top">
        <h3>${isl.name}</h3>
        <span class="badge ${isl.region}">${isl.region}</span>
      </div>
      <div class="sst">
        <span class="value">${fmt(isl.sst.value_c, 1)}</span><span class="unit">°C SST</span>
      </div>
      <p class="sst-src">source: ${isl.sst.source || "—"}</p>
      <div class="conditions">
        <div class="cond"><span class="k">Weather</span><span class="v">${wmoText(c.weather_code)}</span></div>
        <div class="cond"><span class="k">Air</span><span class="v">${fmt(c.air_temp_c, 1, "°C")}</span></div>
        <div class="cond"><span class="k">Wind</span><span class="v">${fmt(c.wind_speed_kn, 0, " kn")} <span class="arrow">${degToArrow(c.wind_dir_deg)}</span></span></div>
        <div class="cond"><span class="k">Gust</span><span class="v">${fmt(c.wind_gust_kn, 0, " kn")}</span></div>
        <div class="cond"><span class="k">Waves</span><span class="v">${fmt(c.wave_height_m, 1, " m")}</span></div>
        <div class="cond"><span class="k">Period</span><span class="v">${fmt(c.wave_period_s, 0, " s")}</span></div>
      </div>
      ${anomaly}
      ${advisory}
    `;
    card.addEventListener("click", () => openDetail(isl.slug, isl.name));
    card.addEventListener("keydown", (e) => { if (e.key === "Enter") openDetail(isl.slug, isl.name); });
    root.appendChild(card);
  });
}

function destroyCharts() {
  charts.forEach((ch) => ch.destroy());
  charts = [];
}

function lineChart(canvasId, labels, datasets, yTitle) {
  const ctx = document.getElementById(canvasId);
  const ch = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#cfe3ee" } } },
      scales: {
        x: { ticks: { color: "#8fb0c2", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { title: { display: true, text: yTitle, color: "#8fb0c2" }, ticks: { color: "#8fb0c2" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
      elements: { point: { radius: 0 } },
    },
  });
  charts.push(ch);
}

async function openDetail(slug, name) {
  const detail = document.getElementById("detail");
  document.getElementById("detail-title").textContent = `${name} — 7-day forecast`;
  detail.classList.remove("hidden");
  detail.scrollIntoView({ behavior: "smooth", block: "start" });

  let data;
  try {
    data = await loadJSON(`data/islands/${slug}.json`);
  } catch (e) {
    document.getElementById("detail-meta").textContent = `Could not load detail: ${e.message}`;
    return;
  }
  const fc = data.forecast || {};
  const labels = (fc.time || []).map((t) => t.replace("T", " ").slice(5, 16));
  document.getElementById("detail-meta").textContent =
    `${data.region} · lat ${data.lat}, lon ${data.lon} · updated ${data.updated_at}`;

  destroyCharts();
  lineChart("chart-temp", labels, [
    { label: "Air °C", data: fc.air_temp_c, borderColor: "#ffb74d", backgroundColor: "transparent", tension: .3 },
    { label: "Sea °C", data: fc.sea_temp_c, borderColor: "#29b6f6", backgroundColor: "transparent", tension: .3 },
  ], "°C");
  lineChart("chart-wind", labels, [
    { label: "Wind kn", data: fc.wind_speed_kn, borderColor: "#26a69a", backgroundColor: "transparent", tension: .3 },
    { label: "Gust kn", data: fc.wind_gust_kn, borderColor: "#ef5350", backgroundColor: "transparent", tension: .3 },
  ], "knots");
  lineChart("chart-wave", labels, [
    { label: "Wave height m", data: fc.wave_height_m, borderColor: "#7e57c2", backgroundColor: "transparent", tension: .3 },
  ], "metres");

  const advRoot = document.getElementById("detail-advisories");
  advRoot.innerHTML = "";
  (data.advisories || []).forEach((a) => {
    const d = document.createElement("div");
    d.className = "adv";
    d.textContent = `⚠︎ [${a.source}] ${a.text}`;
    advRoot.appendChild(d);
  });
  if (data.climate && data.climate.note) {
    const d = document.createElement("div");
    d.className = "adv";
    const an = data.climate.anomaly_c != null ? `${data.climate.anomaly_c}°C` : "n/a";
    d.textContent = `🌡 [${data.climate.source || "climate"}] Med SST anomaly ${an} — ${data.climate.note}`;
    advRoot.appendChild(d);
  }
}

async function init() {
  document.getElementById("detail-close").addEventListener("click", () => {
    document.getElementById("detail").classList.add("hidden");
    destroyCharts();
  });
  try {
    const latest = await loadJSON("data/latest.json");
    document.getElementById("updated").textContent =
      `Last updated: ${latest.generated_at} · ${latest.island_count} islands`;
    renderSourceStrip(latest.run_sources);
    renderCards(latest);
  } catch (e) {
    document.getElementById("cards").innerHTML =
      `<p class="error">Could not load data (${e.message}). Run <code>python -m src.main</code> to generate it.</p>`;
  }
}

init();
