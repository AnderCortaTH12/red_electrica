// Vista "Aprovisionamiento": barras apiladas por país de origen a lo
// largo del año, donut GN/GNL del periodo seleccionado, y saldos por
// conexión internacional.
import { periodos, filasDe, valorEscalar } from "../data.js";
import { nombreMes, formatoNumero, colorPorIndice } from "../utils.js";

const TOP_N_PAISES = 7;

let chartPaises = null;
let chartDonut = null;
let chartSaldos = null;

function totalesPorPais(agregacion) {
  // GN + GNL sumados por país, para las series de la barra apilada.
  const filas = [...filasDe("aprovisionamiento_gn", agregacion), ...filasDe("aprovisionamiento_gnl", agregacion)];
  const totalPorPais = new Map();
  for (const f of filas) {
    if (!f.dimension || f.valor === null) continue;
    totalPorPais.set(f.dimension, (totalPorPais.get(f.dimension) || 0) + f.valor);
  }
  return [...totalPorPais.entries()].sort((a, b) => b[1] - a[1]);
}

export function pintarPaises(dom, agregacion) {
  if (!chartPaises) chartPaises = echarts.init(dom);

  const ranking = totalesPorPais("mes"); // el ranking de "top países" se decide por el total del año (mes a mes sumado)
  const top = ranking.slice(0, TOP_N_PAISES).map(([pais]) => pais);
  const ejeX = periodos().map(nombreMes);

  function serieDePais(pais) {
    return periodos().map((p) => {
      const gn = filasDe("aprovisionamiento_gn", agregacion, p).find((f) => f.dimension === pais);
      const gnl = filasDe("aprovisionamiento_gnl", agregacion, p).find((f) => f.dimension === pais);
      const total = (gn?.valor || 0) + (gnl?.valor || 0);
      return total || null;
    });
  }

  const otros = periodos().map((p, i) => {
    const filas = [...filasDe("aprovisionamiento_gn", agregacion, p), ...filasDe("aprovisionamiento_gnl", agregacion, p)];
    const totalMes = filas.reduce((acc, f) => acc + (f.valor || 0), 0);
    const totalTop = top.reduce((acc, pais) => acc + (serieDePais(pais)[i] || 0), 0);
    const resto = totalMes - totalTop;
    return resto > 0 ? Math.round(resto) : 0;
  });

  const series = top.map((pais, i) => ({
    name: pais,
    type: "bar",
    stack: "total",
    data: serieDePais(pais),
    itemStyle: { color: colorPorIndice(i) },
  }));
  series.push({
    name: "Otros",
    type: "bar",
    stack: "total",
    data: otros,
    itemStyle: { color: colorPorIndice(TOP_N_PAISES) },
  });

  chartPaises.setOption(
    {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => `${formatoNumero(v)} GWh` },
      legend: { top: 0, type: "scroll", textStyle: { color: "inherit" } },
      grid: { left: 56, right: 24, top: 40, bottom: 32 },
      xAxis: { type: "category", data: ejeX },
      yAxis: { type: "value", name: "GWh" },
      series,
    },
    true
  );
  return chartPaises;
}

export function pintarDonutOrigen(dom, agregacion, periodo) {
  if (!chartDonut) chartDonut = echarts.init(dom);

  const gn = valorEscalar("pct_total_gn", agregacion, periodo).valor;
  const gnl = valorEscalar("pct_total_gnl", agregacion, periodo).valor;
  const datos = [
    { name: "Gas natural (GN)", value: gn ?? 0 },
    { name: "GNL", value: gnl ?? 0 },
  ];

  chartDonut.setOption(
    {
      tooltip: { formatter: (i) => `${i.name}: ${formatoNumero(i.value, 1)}%` },
      legend: { bottom: 0, textStyle: { color: "inherit" } },
      series: [
        {
          type: "pie",
          radius: ["55%", "80%"],
          center: ["50%", "45%"],
          data: datos,
          label: { formatter: (i) => `${formatoNumero(i.value, 0)}%` },
          color: ["var(--chart-1)", "var(--chart-6)"].map((v) =>
            getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1)).trim()
          ),
        },
      ],
    },
    true
  );
  return chartDonut;
}

export function pintarSaldosConexion(dom, agregacion, periodo) {
  if (!chartSaldos) chartSaldos = echarts.init(dom);

  const filas = filasDe("conexion_internacional_saldo", agregacion, periodo).filter((f) => f.valor !== null);
  filas.sort((a, b) => b.valor - a.valor);

  chartSaldos.setOption(
    {
      tooltip: { valueFormatter: (v) => `${formatoNumero(v)} GWh` },
      grid: { left: 110, right: 24, top: 16, bottom: 24 },
      xAxis: { type: "value", name: "GWh" },
      yAxis: { type: "category", data: filas.map((f) => f.dimension) },
      series: [
        {
          type: "bar",
          data: filas.map((f) => ({
            value: f.valor,
            itemStyle: {
              color: getComputedStyle(document.documentElement)
                .getPropertyValue(f.valor >= 0 ? "--positive" : "--negative")
                .trim(),
            },
          })),
        },
      ],
    },
    true
  );
  return chartSaldos;
}

export function resize() {
  chartPaises && chartPaises.resize();
  chartDonut && chartDonut.resize();
  chartSaldos && chartSaldos.resize();
}
