// Vista "Comparativa": líneas mes a mes de varias métricas
// superpuestas. Solo hay 2026 en el dataset (histórico desde
// 2026-01), así que por ahora es una única línea por métrica -- se
// avisa explícitamente en la UI (ver comparativa.html/main.js) en vez
// de dejar un selector de año mudo.
import { periodos, serieTemporal, metrica } from "../data.js";
import { nombreMes, colorPorIndice, formatoNumero } from "../utils.js";

let chart = null;

export function pintarComparativa(dom, metricaIds, agregacion) {
  if (!chart) chart = echarts.init(dom);

  const ejeX = periodos().map(nombreMes);
  const series = metricaIds.map((id, i) => ({
    name: metrica(id).nombre,
    type: "line",
    data: serieTemporal(id, agregacion).map((p) => p[1]),
    smooth: 0.2,
    symbolSize: 6,
    lineStyle: { width: 2.5, color: colorPorIndice(i) },
    itemStyle: { color: colorPorIndice(i) },
  }));

  chart.setOption(
    {
      color: metricaIds.map((_, i) => colorPorIndice(i)),
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (v === null ? "—" : formatoNumero(v)),
      },
      legend: { top: 0, textStyle: { color: "inherit" } },
      grid: { left: 56, right: 24, top: 40, bottom: 32 },
      xAxis: { type: "category", data: ejeX },
      yAxis: { type: "value" },
      series,
    },
    true
  );
  return chart;
}

export function resize() {
  chart && chart.resize();
}
