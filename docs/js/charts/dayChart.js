import { COLORS, GEN_SERIES, chartGridColor, chartTextColor, formatHourMadrid, formatPrice } from "../utils.js";

/** Mix de generación del día (área apilada) + precio superpuesto en
 * eje secundario -- para ver de un vistazo la relación entre mix y
 * precio. */
export function renderDayChart(el, day) {
  if (!day) {
    el.innerHTML = '<p class="chart-empty">Sin datos para este día.</p>';
    return null;
  }

  const chart = echarts.init(el, null, { renderer: "canvas" });
  const textColor = chartTextColor();
  const gridColor = chartGridColor();
  const times = day.datetime_utc;

  const genSeries = GEN_SERIES.map((g) => ({
    name: g.label,
    type: "line",
    stack: "generacion",
    areaStyle: { color: g.color, opacity: 0.85 },
    lineStyle: { width: 0.5, color: g.color },
    showSymbol: false,
    data: day[g.key],
    yAxisIndex: 0,
  }));

  const option = {
    backgroundColor: "transparent",
    textStyle: { color: textColor, fontFamily: "inherit" },
    grid: { left: 56, right: 56, top: 36, bottom: 56 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "var(--surface-1, #11161f)",
      borderColor: gridColor,
      textStyle: { color: textColor },
      formatter: (params) => {
        const idx = params[0].dataIndex;
        const lines = [`<strong>${formatHourMadrid(times[idx])}</strong>`];
        params.forEach((p) => {
          if (p.seriesName === "Precio real") {
            lines.push(`${p.marker} ${p.seriesName}: ${formatPrice(p.value)}`);
          } else if (p.value !== null && p.value !== undefined) {
            lines.push(`${p.marker} ${p.seriesName}: ${Math.round(p.value).toLocaleString("es-ES")} MW`);
          }
        });
        return lines.join("<br/>");
      },
    },
    legend: {
      data: [...GEN_SERIES.map((g) => g.label), "Precio real"],
      textStyle: { color: textColor, fontSize: 11 },
      top: 0,
      type: "scroll",
    },
    xAxis: {
      type: "category",
      data: times,
      axisLabel: { color: textColor, formatter: (v) => formatHourMadrid(v) },
      axisLine: { lineStyle: { color: gridColor } },
    },
    yAxis: [
      {
        type: "value",
        name: "MW",
        nameTextStyle: { color: textColor },
        axisLabel: { color: textColor },
        splitLine: { lineStyle: { color: gridColor } },
      },
      {
        type: "value",
        name: "€/MWh",
        nameTextStyle: { color: textColor },
        axisLabel: { color: textColor },
        splitLine: { show: false },
        scale: true,
      },
    ],
    series: [
      ...genSeries,
      {
        name: "Precio real",
        type: "line",
        yAxisIndex: 1,
        data: day.precio_real,
        showSymbol: false,
        lineStyle: { color: COLORS.precioReal, width: 2.5 },
        itemStyle: { color: COLORS.precioReal },
        z: 10,
      },
    ],
  };

  chart.setOption(option);
  return chart;
}
