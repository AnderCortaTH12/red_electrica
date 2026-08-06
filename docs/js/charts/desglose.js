// Vista "Desglose de la demanda": sunburst navegable de la jerarquía
// Total → Nacional/Internacional → Convencional/Eléctrico →
// Industrial/DC+PyMES/Cisternas (definida por `padre` en el catálogo).
// Clic en un anillo para profundizar -- comportamiento nativo de
// ECharts sunburst.
import { hijosDe, valorEscalar, metrica } from "../data.js";
import { formatoNumero } from "../utils.js";

let chart = null;

function construirNodo(metricaId, agregacion, periodo) {
  const info = metrica(metricaId);
  const { valor } = valorEscalar(metricaId, agregacion, periodo);
  const hijos = hijosDe(metricaId).filter((h) => h.dimension === null);
  const node = {
    name: info.nombre,
    metrica_id: metricaId,
    value: valor ?? 0,
  };
  if (hijos.length > 0) {
    node.children = hijos.map((h) => construirNodo(h.metrica_id, agregacion, periodo));
  }
  return node;
}

export function pintarDesglose(dom, agregacion, periodo) {
  if (!chart) chart = echarts.init(dom);

  const raiz = construirNodo("total_salidas", agregacion, periodo);
  const unidad = metrica("total_salidas").unidad_canonica;

  chart.setOption(
    {
      tooltip: {
        formatter: (info) => `${info.name}<br/><strong>${formatoNumero(info.value)} ${unidad}</strong>`,
      },
      series: [
        {
          type: "sunburst",
          data: raiz.children,
          radius: [0, "92%"],
          sort: null,
          emphasis: { focus: "ancestor" },
          levels: [
            {},
            { r0: "15%", r: "45%", itemStyle: { borderWidth: 2 }, label: { rotate: "tangential" } },
            { r0: "45%", r: "70%", label: { align: "right" } },
            { r0: "70%", r: "92%", label: { position: "outside", silent: false } },
          ],
          label: { fontSize: 11 },
        },
      ],
    },
    true
  );
  return chart;
}

export function resize() {
  chart && chart.resize();
}
