// Vista "Infraestructuras": actividad por planta de regasificación
// (gráfica + mapa), capacidad del TVB y saldos por conexión
// internacional (movido aquí desde Aprovisionamiento). Sin
// almacenamientos subterráneos (AASS): se decidió no incluirlos en el
// catálogo por ahora -- ver Limitaciones conocidas del README.
import { valorEscalar, filasDe, metrica } from "../data.js";
import { formatoNumero, colorPorIndice } from "../utils.js";
import { registrarMapaEspana, COORDS_PLANTA } from "./mapa-base.js";

let chartPlantas = null;
let chartMapaPlantas = null;
let chartTvb = null;
let chartSaldos = null;

export function pintarPlantas(dom, agregacion, periodo, plantaFiltro) {
  if (!chartPlantas) chartPlantas = echarts.init(dom);

  const metricas = [
    { id: "planta_descargas_buques", nombre: "Descargas de buques" },
    { id: "planta_cargas_buques", nombre: "Cargas de buques" },
    { id: "planta_carga_cisternas", nombre: "Carga de cisternas" },
  ];

  let plantas = [...new Set(filasDe("planta_descargas_buques", agregacion, periodo).map((f) => f.dimension))].sort();
  if (plantaFiltro) plantas = plantas.filter((p) => p === plantaFiltro);

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
      legend: { top: 0, textStyle: { color: "inherit", fontSize: 10 } },
      grid: { left: 50, right: 16, top: 36, bottom: 28 },
      // interval:0 fuerza a mostrar TODAS las etiquetas del eje: el
      // algoritmo "auto" de echarts se pone a saltarse alguna (p.ej.
      // BILBAO) cuando calcula, de forma demasiado conservadora, que
      // podrían solaparse -- aunque con 7 categorías cortas no pasa.
      xAxis: { type: "category", data: plantas, axisLabel: { fontSize: 10, interval: 0 } },
      yAxis: { type: "value", name: "GWh" },
      series,
    },
    true
  );
  return chartPlantas;
}

/** Actividad total (descargas + cargas + cisternas) por planta, para
 * el tamaño de la burbuja del mapa. */
function actividadTotalPorPlanta(agregacion, periodo) {
  const metricas = ["planta_descargas_buques", "planta_cargas_buques", "planta_carga_cisternas"];
  const totales = new Map();
  for (const id of metricas) {
    for (const f of filasDe(id, agregacion, periodo)) {
      if (!f.dimension || f.valor === null) continue;
      totales.set(f.dimension, (totales.get(f.dimension) || 0) + f.valor);
    }
  }
  return totales;
}

export async function pintarMapaPlantas(dom, agregacion, periodo, plantaFiltro, onClickPlanta) {
  try {
    await registrarMapaEspana();
  } catch (err) {
    dom.parentElement.innerHTML = `<div class="empty-state">${err.message}</div>`;
    return null;
  }
  const esNuevo = !chartMapaPlantas;
  if (esNuevo) chartMapaPlantas = echarts.init(dom);
  // El polígono de la CCAA queda por encima de la burbuja en el
  // hit-test de echarts (aunque la burbuja se vea "encima" visualmente),
  // así que el clic casi siempre llega como un clic sobre el geo, no
  // sobre la serie scatter. En vez de depender de qué componente lo
  // reporta, se coge el punto de clic en coordenadas geográficas y se
  // busca la planta más cercana dentro de un radio razonable.
  if (esNuevo && onClickPlanta) {
    chartMapaPlantas.on("click", (params) => {
      const [lon, lat] = chartMapaPlantas.convertFromPixel({ geoIndex: 0 }, [params.event.offsetX, params.event.offsetY]);
      let masCercana = null;
      let distMin = Infinity;
      for (const [planta, [plon, plat]] of Object.entries(COORDS_PLANTA)) {
        const dist = Math.hypot(lon - plon, lat - plat);
        if (dist < distMin) {
          distMin = dist;
          masCercana = planta;
        }
      }
      // ~0.8º ronda el radio visual de la burbuja más grande a este zoom.
      if (masCercana && distMin < 0.8) onClickPlanta(masCercana);
    });
  }

  const totales = actividadTotalPorPlanta(agregacion, periodo);
  const valores = [...totales.values()];
  const max = valores.length ? Math.max(...valores) : 1;

  const estilo = getComputedStyle(document.documentElement);
  const datos = Object.entries(COORDS_PLANTA).map(([planta, coords]) => {
    const seleccionada = plantaFiltro && planta === plantaFiltro;
    return {
      name: planta.charAt(0) + planta.slice(1).toLowerCase(),
      value: [...coords, totales.get(planta) ?? 0],
      itemStyle: seleccionada
        ? { color: estilo.getPropertyValue("--negative").trim(), opacity: 1, borderColor: estilo.getPropertyValue("--text").trim(), borderWidth: 2 }
        : undefined,
    };
  });

  chartMapaPlantas.setOption(
    {
      tooltip: {
        formatter: (i) => `${i.name}: ${formatoNumero(i.value[2])} GWh (descargas + cargas + cisternas)`,
      },
      geo: {
        map: "espana-ccaa",
        roam: true,
        zoom: 1.05,
        selectedMode: false,
        // Sin esto, el geo de fondo saca su propio tooltip por defecto
        // (solo el nombre de la CCAA, sin formatear) al pasar el ratón
        // o hacer clic cerca de una burbuja -- el tooltip que importa
        // es el de la serie scatter, con formatter propio más abajo.
        tooltip: { show: false },
        itemStyle: {
          areaColor: estilo.getPropertyValue("--bg").trim(),
          borderColor: estilo.getPropertyValue("--border").trim(),
        },
        // Este mapa es solo el fondo para las burbujas de planta: nunca
        // se muestra el nombre de la CCAA, ni al pasar el ratón ni tras
        // hacer clic (con selectedMode:false de más, por si acaso).
        label: { show: false },
        emphasis: { itemStyle: { areaColor: estilo.getPropertyValue("--bg").trim() }, label: { show: false } },
        select: { label: { show: false } },
      },
      series: [
        {
          type: "scatter",
          coordinateSystem: "geo",
          data: datos,
          symbolSize: (val) => (max ? 10 + (val[2] / max) * 26 : 10),
          itemStyle: { color: estilo.getPropertyValue("--chart-1").trim(), opacity: 0.85 },
          label: { show: true, formatter: (i) => i.name, position: "top", fontSize: 10, color: estilo.getPropertyValue("--text-secondary").trim() },
        },
      ],
    },
    true
  );
  return chartMapaPlantas;
}

// Las 3 capacidades del TVB comparten unidad (GWh/mes): se pintan
// juntas. La regasificación comercial (GWh, energía real del mes, no
// una capacidad) se muestra aparte en tarjetas -- mezclarla en la
// misma barra horizontal hacía que el gráfico se viera raro.
const TVB_CAPACIDAD = [
  "tvb_capacidad_regasificacion_total",
  "tvb_capacidad_regasificacion_contratada",
  "tvb_capacidad_regasificacion_disponible",
];

export function pintarTvb(dom, agregacion, periodo) {
  if (!chartTvb) chartTvb = echarts.init(dom);

  const datos = TVB_CAPACIDAD.map((id) => ({
    nombre: metrica(id).nombre.replace("TVB: capacidad ", "").replace("de regasificación ", ""),
    valor: valorEscalar(id, agregacion, periodo).valor,
  }));

  chartTvb.setOption(
    {
      tooltip: { valueFormatter: (v) => `${formatoNumero(v)} GWh/mes` },
      grid: { left: 130, right: 50, top: 12, bottom: 20 },
      xAxis: { type: "value", axisLabel: { fontSize: 10 } },
      yAxis: { type: "category", data: datos.map((d) => d.nombre), axisLabel: { fontSize: 10 } },
      series: [
        {
          type: "bar",
          data: datos.map((d, i) => ({ value: d.valor, itemStyle: { color: colorPorIndice(i) } })),
          label: { show: true, position: "right", fontSize: 10, formatter: (i) => (i.value == null ? "—" : formatoNumero(i.value)) },
          barMaxWidth: 26,
        },
      ],
    },
    true
  );
  return chartTvb;
}

export function pintarSaldosConexion(dom, agregacion, periodo) {
  if (!chartSaldos) chartSaldos = echarts.init(dom);

  const filas = filasDe("conexion_internacional_saldo", agregacion, periodo).filter((f) => f.valor !== null);
  filas.sort((a, b) => b.valor - a.valor);

  chartSaldos.setOption(
    {
      tooltip: { valueFormatter: (v) => `${formatoNumero(v)} GWh` },
      grid: { left: 100, right: 16, top: 12, bottom: 20 },
      xAxis: { type: "value", name: "GWh", axisLabel: { fontSize: 10 } },
      yAxis: { type: "category", data: filas.map((f) => f.dimension), axisLabel: { fontSize: 10 } },
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
          barMaxWidth: 22,
        },
      ],
    },
    true
  );
  return chartSaldos;
}

/** Resumen numérico del TVB para las tarjetas de la vista
 * Infraestructuras: capacidades + % contratada y % de uso comercial
 * sobre la capacidad total (cálculo propio del dashboard, no publicado
 * como porcentaje por Enagás). */
export function datosTvbResumen(agregacion, periodo) {
  const total = valorEscalar("tvb_capacidad_regasificacion_total", agregacion, periodo).valor;
  const contratada = valorEscalar("tvb_capacidad_regasificacion_contratada", agregacion, periodo).valor;
  const disponible = valorEscalar("tvb_capacidad_regasificacion_disponible", agregacion, periodo).valor;
  const comercial = valorEscalar("tvb_regasificacion_comercial", agregacion, periodo).valor;
  const pctContratada = total ? (contratada / total) * 100 : null;
  const pctUsoComercial = total ? (comercial / total) * 100 : null;
  return { total, contratada, disponible, comercial, pctContratada, pctUsoComercial };
}

export function resize() {
  chartPlantas && chartPlantas.resize();
  chartMapaPlantas && chartMapaPlantas.resize();
  chartTvb && chartTvb.resize();
  chartSaldos && chartSaldos.resize();
}
