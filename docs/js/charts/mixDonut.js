import { GEN_SERIES, RENEWABLE_KEYS, chartTextColor } from "../utils.js";

/** Donut con el reparto porcentual de generación del día + % renovable
 * en el centro. */
export function renderMixDonut(el, day) {
  if (!day) {
    el.innerHTML = '<p class="chart-empty">Sin datos.</p>';
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();

  const totals = GEN_SERIES.map((g) => {
    const values = day[g.key].filter((v) => v !== null && v !== undefined);
    const sum = values.reduce((acc, v) => acc + Math.max(v, 0), 0);
    return { name: g.label, value: sum, key: g.key, color: g.color };
  }).filter((d) => d.value > 0);

  const totalAll = totals.reduce((acc, d) => acc + d.value, 0);
  const totalRenewable = totals
    .filter((d) => RENEWABLE_KEYS.has(d.key))
    .reduce((acc, d) => acc + d.value, 0);
  const pctRenewable = totalAll > 0 ? Math.round((totalRenewable / totalAll) * 100) : null;

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    tooltip: {
      trigger: "item",
      formatter: (p) => `${p.marker} ${p.name}: ${p.percent.toFixed(1)}%`,
    },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        data: totals.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
      },
    ],
    graphic: {
      elements: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: {
            text: pctRenewable !== null ? `${pctRenewable}%` : "—",
            fill: textColor,
            fontSize: 26,
            fontWeight: 500,
            textAlign: "center",
          },
        },
      ],
    },
  };

  chart.setOption(option);
  return chart;
}
