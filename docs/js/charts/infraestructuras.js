// Vista "Infraestructuras": actividad por planta de regasificación y
// capacidades del TVB. Sin almacenamientos subterráneos (AASS): se
// decidió no incluirlos en el catálogo por ahora (datos solo
// disponibles como gráfico en el PDF, no como tabla -- ver
// Limitaciones conocidas del README).
import { filasDe, valorEscalar, metrica } from "../data.js";
import { formatoNumero, colorPorIndice } from "../utils.js";

let chartPlantas = null;
let chartTvb = null;

export function pintarPlantas(dom, agregacion, periodo) {
  if (!chartPlantas) chartPlantas = echarts.init(dom);

  const metricas = [
    { id: "planta_descargas_buques", nombre: "Descargas de buques" },
    { id: "planta_cargas_buques", nombre: "Cargas de buques" },
    { id: "planta_carga_cisternas", nombre: "Carga de cisternas" },
  ];

  const plantas = [...new Set(filasDe("planta_descargas_buques", agregacion, periodo).map((f) => f.dimension))].sort();

  const series = metricas.map((m, i) => ({
    name: m.nombre,
    type: "bar",
    data: plantas.map((planta) => {
      const fila = filasDe(m.id, agregacion, periodo).find((f) => f.dimension === planta);
      return fila ? fila.valor : null;
    }),
    itemStyle: { color: colorPorIndice(i) },
  }));

  chartPlantas.setOption(
    {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => (v === null ? "—" : `${formatoNumero(v)} GWh`) },
      legend: { top: 0, textStyle: { color: "inherit" } },
      grid: { left: 56, right: 24, top: 40, bottom: 32 },
      xAxis: { type: "category", data: plantas },
      yAxis: { type: "value", name: "GWh" },
      series,
    },
    true
  );
  return chartPlantas;
}

export function pintarTvb(dom, agregacion, periodo) {
  if (!chartTvb) chartTvb = echarts.init(dom);

  const metricas = [
    "tvb_capacidad_regasificacion_total",
    "tvb_capacidad_regasificacion_contratada",
    "tvb_capacidad_regasificacion_disponible",
    "tvb_regasificacion_comercial",
  ];
  const datos = metricas.map((id) => ({
    nombre: metrica(id).nombre.replace("TVB: ", ""),
    valor: valorEscalar(id, agregacion, periodo).valor,
    unidad: metrica(id).unidad_canonica,
  }));

  chartTvb.setOption(
    {
      tooltip: { formatter: (i) => `${formatoNumero(i.value)} ${datos[i.dataIndex]?.unidad ?? ""}` },
      grid: { left: 160, right: 40, top: 16, bottom: 24 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: datos.map((d) => d.nombre) },
      series: [
        {
          type: "bar",
          data: datos.map((d) => d.valor),
          itemStyle: { color: "var(--chart-1)".startsWith("var") ? getComputedStyle(document.documentElement).getPropertyValue("--chart-1").trim() : "" },
          label: { show: true, position: "right", formatter: (i) => `${formatoNumero(i.value)}` },
        },
      ],
    },
    true
  );
  return chartTvb;
}

export function resize() {
  chartPlantas && chartPlantas.resize();
  chartTvb && chartTvb.resize();
}
