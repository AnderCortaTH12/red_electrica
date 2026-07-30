import { COLORS, chartGridColor, chartTextColor, formatDatetimeMadrid, formatPrice } from "../utils.js";

/** Combina horas_72h (pasado, con precio real) y prediccion_24h
 * (puede solaparse con el pasado reciente -- el horizonte real de
 * predicción varía día a día, ver README) en una sola línea de
 * tiempo: el pasado ya tiene su precio_modelo/baseline en horas_72h,
 * así que de la predicción solo se añade la cola que cae DESPUÉS del
 * último dato conocido. */
function buildTimeline(latest) {
  const horas = latest.horas_72h;
  const pred = latest.prediccion_24h;

  const times = [...horas.datetime_utc];
  const real = [...horas.precio_real];
  const modelo = [...horas.precio_modelo];
  const baseline = [...horas.precio_baseline];

  const lastKnown = times.length ? times[times.length - 1] : null;

  if (pred && pred.datetime_utc) {
    pred.datetime_utc.forEach((t, i) => {
      if (lastKnown !== null && t <= lastKnown) return; // ya cubierto por horas_72h
      times.push(t);
      real.push(null);
      modelo.push(pred.precio_modelo[i]);
      baseline.push(pred.precio_baseline[i]);
    });
  }

  return { times, real, modelo, baseline, lastKnown };
}

export function renderPriceChart(el, latest) {
  const { times, real, modelo, baseline, lastKnown } = buildTimeline(latest);

  if (times.length === 0) {
    el.innerHTML = '<p class="chart-empty">Sin datos de precio disponibles.</p>';
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();
  const gridColor = chartGridColor();

  const markAreas = [];
  // franja negativa: sombrea desde el minimo del eje hasta 0
  markAreas.push([
    { yAxis: "min", itemStyle: { color: COLORS.negativo } },
    { yAxis: 0 },
  ]);

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    grid: { left: 56, right: 24, top: 36, bottom: 64 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "var(--surface-1, #11161f)",
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: (params) => {
        if (!params.length) return "";
        const idx = params[0].dataIndex;
        const t = times[idx];
        const r = real[idx];
        const m = modelo[idx];
        const b = baseline[idx];
        const lines = [`<strong>${formatDatetimeMadrid(t)}</strong>`];
        if (r !== null && r !== undefined) lines.push(`Real: ${formatPrice(r)}`);
        if (m !== null && m !== undefined) lines.push(`Modelo: ${formatPrice(m)}`);
        if (b !== null && b !== undefined) lines.push(`Baseline: ${formatPrice(b)}`);
        if (r !== null && r !== undefined && m !== null && m !== undefined) {
          lines.push(`Error modelo: ${formatPrice(m - r)}`);
        }
        return lines.join("<br/>");
      },
    },
    legend: {
      data: ["Real", "Modelo", "Baseline"],
      textStyle: { color: textColor },
      top: 0,
    },
    xAxis: {
      type: "category",
      data: times,
      axisLabel: {
        color: textColor,
        formatter: (value) => formatDatetimeMadrid(value).slice(0, 5),
      },
      axisLine: { lineStyle: { color: gridColor } },
    },
    yAxis: {
      type: "value",
      name: "€/MWh",
      nameTextStyle: { color: textColor },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridColor } },
      scale: true,
    },
    dataZoom: [
      { type: "inside", start: 60, end: 100 },
      { type: "slider", start: 60, end: 100, textStyle: { color: textColor }, borderColor: gridColor },
    ],
    series: [
      {
        name: "Real",
        type: "line",
        data: real,
        showSymbol: false,
        lineStyle: { color: COLORS.precioReal, width: 2 },
        itemStyle: { color: COLORS.precioReal },
        markArea: { silent: true, data: markAreas },
        connectNulls: false,
      },
      {
        name: "Modelo",
        type: "line",
        data: modelo,
        showSymbol: false,
        lineStyle: { color: COLORS.precioModelo, width: 2 },
        itemStyle: { color: COLORS.precioModelo },
        connectNulls: true,
      },
      {
        name: "Baseline",
        type: "line",
        data: baseline,
        showSymbol: false,
        lineStyle: { color: COLORS.precioBaseline, width: 1.5, type: "dashed" },
        itemStyle: { color: COLORS.precioBaseline },
        connectNulls: true,
      },
    ],
  };

  if (lastKnown && times[times.length - 1] > lastKnown) {
    option.series[1].markArea = {
      silent: true,
      data: [
        [
          { xAxis: lastKnown, itemStyle: { color: "rgba(245, 115, 76, 0.06)" } },
          { xAxis: times[times.length - 1] },
        ],
      ],
      label: { show: true, position: "insideTop", formatter: "Predicción", color: textColor },
    };
  }

  chart.setOption(option);
  return chart;
}
