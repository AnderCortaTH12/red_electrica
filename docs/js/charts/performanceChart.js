import { COLORS, chartGridColor, chartTextColor, formatPrice } from "../utils.js";

/** MAE por año: baseline (2014-hoy) vs modelo (solo régimen post_tope,
 * ver README) -- muestra cómo se ha ido el error en el tiempo. */
export function renderErrorByYearChart(el, performance) {
  const baseline = performance.baseline_por_anio || [];
  if (baseline.length === 0) {
    el.innerHTML = '<p class="chart-empty">Sin histórico de error todavía.</p>';
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();
  const gridColor = chartGridColor();

  const years = baseline.map((r) => r.periodo);
  const baselineMae = baseline.map((r) => r.mae);

  const modeloByYear = new Map((performance.modelo_por_anio || []).map((r) => [r.periodo, r.mae]));
  const modeloMae = years.map((y) => (modeloByYear.has(y) ? modeloByYear.get(y) : null));

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    grid: { left: 56, right: 24, top: 36, bottom: 36 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "var(--surface-1, #11161f)",
      borderColor: gridColor,
      textStyle: { color: textColor },
      valueFormatter: (v) => formatPrice(v),
    },
    legend: {
      data: ["Baseline (2014-hoy)", "Modelo (post_tope)"],
      textStyle: { color: textColor },
      top: 0,
    },
    xAxis: {
      type: "category",
      data: years,
      axisLabel: { color: textColor },
      axisLine: { lineStyle: { color: gridColor } },
    },
    yAxis: {
      type: "value",
      name: "MAE (€/MWh)",
      nameTextStyle: { color: textColor },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridColor } },
    },
    series: [
      {
        name: "Baseline (2014-hoy)",
        type: "bar",
        data: baselineMae,
        itemStyle: { color: COLORS.precioBaseline },
      },
      {
        name: "Modelo (post_tope)",
        type: "bar",
        data: modeloMae,
        itemStyle: { color: COLORS.precioModelo },
      },
    ],
  };

  chart.setOption(option);
  return chart;
}

/** Scatter predicho vs real + diagonal de predicción perfecta, con las
 * predicciones ya verificadas contra el precio real. */
export function renderScatterChart(el, performance) {
  const scatter = performance.scatter || [];
  if (scatter.length === 0) {
    el.innerHTML =
      '<p class="chart-empty">Aún no hay suficientes predicciones verificadas ' +
      "contra el precio real -- se va llenando día a día según el job diario " +
      "compara la predicción de ayer con el precio de hoy.</p>";
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();
  const gridColor = chartGridColor();

  const values = scatter.map((d) => [d.actual, d.predicted]);
  const allValues = values.flat();
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    grid: { left: 56, right: 24, top: 24, bottom: 48 },
    tooltip: {
      trigger: "item",
      backgroundColor: "var(--surface-1, #11161f)",
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: (p) => `Real: ${formatPrice(p.value[0])}<br/>Predicho: ${formatPrice(p.value[1])}`,
    },
    xAxis: {
      type: "value",
      name: "Precio real (€/MWh)",
      nameTextStyle: { color: textColor },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridColor } },
      min,
      max,
    },
    yAxis: {
      type: "value",
      name: "Precio predicho (€/MWh)",
      nameTextStyle: { color: textColor },
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: gridColor } },
      min,
      max,
    },
    series: [
      {
        name: "Predicción perfecta",
        type: "line",
        data: [[min, min], [max, max]],
        showSymbol: false,
        lineStyle: { color: gridColor, type: "dashed", width: 1 },
        tooltip: { show: false },
      },
      {
        name: "Predicciones",
        type: "scatter",
        data: values,
        symbolSize: 6,
        itemStyle: { color: COLORS.precioModelo, opacity: 0.7 },
      },
    ],
  };

  chart.setOption(option);
  return chart;
}
