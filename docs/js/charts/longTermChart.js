import { COLORS, chartGridColor, chartTextColor, formatPrice } from "../utils.js";

// Mismas fechas que src/model/regimes.py (calendario Europe/Madrid en
// el backend; aquí se comparan como fecha UTC de summary.json -- el
// desfase de unas horas en la frontera no es relevante a escala de
// años).
const TOPE_GAS_INICIO = "2022-06-15";
const POST_TOPE_INICIO = "2024-01-01";

export function renderLongTermChart(el, summaryRows) {
  if (!summaryRows || summaryRows.length === 0) {
    el.innerHTML = '<p class="chart-empty">Sin datos de largo plazo.</p>';
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();
  const gridColor = chartGridColor();

  const dates = summaryRows.map((r) => r.date);
  const medio = summaryRows.map((r) => r.precio_medio);
  const first = dates[0];
  const last = dates[dates.length - 1];

  const regimeAreas = [
    [
      { xAxis: first, itemStyle: { color: COLORS.regimeNormal } },
      { xAxis: TOPE_GAS_INICIO },
    ],
    [
      { xAxis: TOPE_GAS_INICIO, itemStyle: { color: COLORS.regimeTopeGas } },
      { xAxis: POST_TOPE_INICIO },
    ],
    [
      { xAxis: POST_TOPE_INICIO, itemStyle: { color: COLORS.regimePostTope } },
      { xAxis: last },
    ],
  ];

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    grid: { left: 56, right: 24, top: 24, bottom: 64 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "var(--surface-1, #11161f)",
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: (params) => {
        const p = params[0];
        return `<strong>${p.axisValue}</strong><br/>Precio medio: ${formatPrice(p.value)}`;
      },
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: textColor },
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
      { type: "inside" },
      { type: "slider", textStyle: { color: textColor }, borderColor: gridColor },
    ],
    series: [
      {
        name: "Precio medio diario",
        type: "line",
        data: medio,
        showSymbol: false,
        lineStyle: { color: COLORS.precioReal, width: 1.5 },
        itemStyle: { color: COLORS.precioReal },
        markArea: { silent: true, data: regimeAreas },
      },
    ],
  };

  chart.setOption(option);
  return chart;
}
