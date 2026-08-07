// Vista "Resumen": gráfica de barras por sector y mapa+tabla de
// demanda por comunidad autónoma (fusionado desde la antigua vista
// "Territorio", ver docs/index.html).
import { valorEscalar, filasDe } from "../data.js";
import { formatoNumero, colorPorIndice } from "../utils.js";
import { registrarMapaEspana, NOMBRE_MAPA_CCAA, NOMBRE_MAPA_CCAA_INVERSO } from "./mapa-base.js";

const SECTORES = [
  { id: "demanda_industrial", nombre: "Industrial" },
  { id: "demanda_sector_electrico", nombre: "Sector eléctrico" },
  { id: "demanda_dc_pymes", nombre: "DC + PyMES" },
  { id: "demanda_cisternas", nombre: "Cisternas" },
];

let chartSectores = null;
let chartMapa = null;

export function pintarSectores(dom, agregacion, periodo) {
  if (!chartSectores) chartSectores = echarts.init(dom);

  const datos = SECTORES.map((s) => ({ ...s, valor: valorEscalar(s.id, agregacion, periodo).valor })).sort(
    (a, b) => (b.valor ?? -Infinity) - (a.valor ?? -Infinity)
  );

  chartSectores.setOption(
    {
      tooltip: { valueFormatter: (v) => (v == null ? "—" : `${formatoNumero(v)} GWh`) },
      grid: { left: 60, right: 16, top: 34, bottom: 28 },
      xAxis: { type: "category", data: datos.map((d) => d.nombre), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", name: "GWh", axisLabel: { fontSize: 10, formatter: (v) => formatoNumero(v) } },
      series: [
        {
          type: "bar",
          data: datos.map((d, i) => ({ value: d.valor, itemStyle: { color: colorPorIndice(i) } })),
          label: { show: true, position: "top", fontSize: 10, formatter: (i) => (i.value == null ? "—" : formatoNumero(i.value)) },
          barMaxWidth: 48,
        },
      ],
    },
    true
  );
  return chartSectores;
}

/** Fila { ccaa, valor, var_pct_interanual } por comunidad para una
 * métrica con dimensión "ccaa" -- usa el mismo periodo/agregación
 * fijos que la tabla (ver AGREGACION_TERRITORIO en main.js). */
export function filasPorCCAA(metricaId, agregacion, periodo) {
  const filas = filasDe(metricaId, agregacion, periodo);
  return Object.keys(NOMBRE_MAPA_CCAA).map((ccaa) => {
    const fila = filas.find((f) => f.dimension === ccaa);
    return { ccaa, valor: fila ? fila.valor : null, var_pct_interanual: fila ? fila.var_pct_interanual : null };
  });
}

export async function pintarMapaCCAA(dom, metricaId, agregacion, periodo, ccaaFiltro, onClickCCAA) {
  try {
    await registrarMapaEspana();
  } catch (err) {
    dom.parentElement.innerHTML = `<div class="empty-state">${err.message}</div>`;
    return null;
  }
  const esNuevo = !chartMapa;
  if (esNuevo) chartMapa = echarts.init(dom);
  // El listener se registra una única vez en la instancia (setOption no
  // lo borra): traduce el nombre del mapa (sin tildes) al nombre real
  // de Enagás antes de pasárselo a quien pintó el mapa.
  if (esNuevo && onClickCCAA) {
    chartMapa.on("click", (params) => onClickCCAA(NOMBRE_MAPA_CCAA_INVERSO[params.name] ?? params.name));
  }

  const filas = filasPorCCAA(metricaId, agregacion, periodo);
  const estilo = getComputedStyle(document.documentElement);
  const datosMapa = filas.map((f) => {
    const seleccionada = ccaaFiltro && f.ccaa === ccaaFiltro;
    return {
      name: NOMBRE_MAPA_CCAA[f.ccaa],
      value: f.valor,
      itemStyle: seleccionada
        ? { borderColor: estilo.getPropertyValue("--text").trim(), borderWidth: 2.5 }
        : undefined,
    };
  });
  const valores = filas.map((f) => f.valor).filter((v) => v !== null);
  const max = valores.length ? Math.max(...valores) : 1;

  chartMapa.setOption(
    {
      tooltip: {
        formatter: (i) => (i.value == null ? `${i.name}: sin dato` : `${i.name}: ${formatoNumero(i.value)} GWh`),
      },
      visualMap: {
        min: 0,
        max,
        left: "left",
        bottom: 0,
        itemWidth: 10,
        itemHeight: 60,
        text: ["más", "menos"],
        textStyle: { color: estilo.getPropertyValue("--text-secondary").trim(), fontSize: 10 },
        // Escala fija (no depende de tema claro/oscuro): a más consumo,
        // más oscuro -- un choropleth invertido confunde más que ayuda.
        inRange: { color: ["#cfe4ff", "#5aa2f0", "#0a3d7a"] },
      },
      series: [
        {
          type: "map",
          map: "espana-ccaa",
          roam: true,
          scaleLimit: { min: 1, max: 6 },
          zoom: 1.15,
          itemStyle: { borderColor: estilo.getPropertyValue("--border").trim() },
          emphasis: { label: { show: false }, itemStyle: { areaColor: estilo.getPropertyValue("--accent").trim() } },
          data: datosMapa,
        },
      ],
    },
    true
  );
  return chartMapa;
}

export function resize() {
  chartSectores && chartSectores.resize();
  chartMapa && chartMapa.resize();
}
