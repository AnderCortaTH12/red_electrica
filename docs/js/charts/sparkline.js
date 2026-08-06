// Sparkline minimalista para las tarjetas KPI de la vista Resumen.
import { temaEcharts } from "../utils.js";

const instancias = new WeakMap();

export function pintarSparkline(dom, puntos, esPositivo) {
  let chart = instancias.get(dom);
  if (!chart) {
    chart = echarts.init(dom, null, { renderer: "svg" });
    instancias.set(dom, chart);
  }
  const tema = temaEcharts();
  const color = esPositivo ? "var(--positive)" : esPositivo === false ? "var(--negative)" : tema.subTextColor;
  const colorResuelto = color.startsWith("var")
    ? getComputedStyle(document.documentElement).getPropertyValue(color.slice(4, -1)).trim()
    : color;

  chart.setOption({
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: "category", show: false, data: puntos.map((p) => p[0]) },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series: [
      {
        type: "line",
        data: puntos.map((p) => p[1]),
        showSymbol: false,
        smooth: 0.3,
        lineStyle: { width: 2, color: colorResuelto },
        areaStyle: { color: colorResuelto, opacity: 0.08 },
      },
    ],
  });
  return chart;
}

export function redimensionarSparklines() {
  // no-op público: cada instancia se redimensiona vía ResizeObserver en main.js
}
