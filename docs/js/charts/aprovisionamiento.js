// Vista "Aprovisionamiento": tarjetas GN/GNL/Total, reparto por país
// del periodo (pie + tabla) y evolución anual -- las tres controladas
// por el mismo selector GN/GNL/Total (ver estado.tipoGas en main.js).
// A diferencia de CCAA/plantas/TVB, el Boletín SÍ publica el
// aprovisionamiento por país en las 3 agregaciones (mes, acumulado del
// año, TAM): todo aquí respeta el control global de agregación.
import { periodosDelAnio, filasDe, sumaDimension, sumaDimensionAnioAnterior, periodoAnterior } from "../data.js";
import { mesCorto, formatoNumero, colorPorIndice } from "../utils.js";

const TOP_N_PAISES = 6;

let chartEvolucion = null;
let chartPaisesPie = null;

export function totalesGnGnl(agregacion, periodo) {
  const gn = sumaDimension("aprovisionamiento_gn", agregacion, periodo);
  const gnl = sumaDimension("aprovisionamiento_gnl", agregacion, periodo);
  return { gn, gnl, total: gn + gnl };
}

/** Mismo cálculo que totalesGnGnl pero reconstruyendo cada país al año
 * anterior antes de sumar (ver sumaDimensionAnioAnterior en data.js). */
export function totalesGnGnlAnioAnterior(agregacion, periodo) {
  const gn = sumaDimensionAnioAnterior("aprovisionamiento_gn", agregacion, periodo);
  const gnl = sumaDimensionAnioAnterior("aprovisionamiento_gnl", agregacion, periodo);
  return { gn, gnl, total: gn + gnl };
}

function metricaIdDe(tipo) {
  return tipo === "gnl" ? "aprovisionamiento_gnl" : "aprovisionamiento_gn";
}

/** Valor por país para un tipo ("gn" | "gnl" | "total") en un periodo. */
function filasPaisTipo(tipo, agregacion, periodo) {
  if (tipo !== "total") {
    return filasDe(metricaIdDe(tipo), agregacion, periodo)
      .filter((f) => f.dimension && f.valor !== null)
      .map((f) => ({ pais: f.dimension, valor: f.valor, varInteranual: f.var_pct_interanual }));
  }
  const gnRows = filasDe("aprovisionamiento_gn", agregacion, periodo);
  const gnlRows = filasDe("aprovisionamiento_gnl", agregacion, periodo);
  const paises = new Set([...gnRows, ...gnlRows].map((r) => r.dimension).filter(Boolean));
  return [...paises].map((pais) => {
    const gn = gnRows.find((r) => r.dimension === pais);
    const gnl = gnlRows.find((r) => r.dimension === pais);
    const valor = (gn?.valor || 0) + (gnl?.valor || 0);
    const priorGn = gn && gn.var_pct_interanual != null ? gn.valor / (1 + gn.var_pct_interanual / 100) : null;
    const priorGnl = gnl && gnl.var_pct_interanual != null ? gnl.valor / (1 + gnl.var_pct_interanual / 100) : null;
    const priorTotal = (priorGn ?? 0) + (priorGnl ?? 0);
    const varInteranual = (priorGn !== null || priorGnl !== null) && priorTotal ? ((valor - priorTotal) / priorTotal) * 100 : null;
    return { pais, valor, varInteranual };
  });
}

/** Lista de países para un tipo/agregación/periodo, con variación
 * interanual (publicada por Enagás) y variación respecto al periodo
 * anterior de la misma agregación (calculada por el propio dashboard),
 * de mayor a menor volumen. */
export function paisesDelPeriodo(tipo, agregacion, periodo) {
  const actuales = filasPaisTipo(tipo, agregacion, periodo);
  const periodoPrevio = periodoAnterior(periodo);
  const previosMap = new Map(periodoPrevio ? filasPaisTipo(tipo, agregacion, periodoPrevio).map((p) => [p.pais, p.valor]) : []);

  return actuales
    .map((a) => {
      const previo = previosMap.get(a.pais);
      return {
        pais: a.pais,
        valor: a.valor,
        varInteranual: a.varInteranual,
        varAnterior: previo ? ((a.valor - previo) / previo) * 100 : null,
      };
    })
    .sort((a, b) => b.valor - a.valor);
}

// El eje X son los meses de UN año concreto: reacciona al selector de
// año (ver estado.periodo en main.js), no al de mes -- por eso recibe
// "anio" en vez del periodo completo.
export function pintarEvolucion(dom, tipo, agregacion, anio) {
  if (!chartEvolucion) chartEvolucion = echarts.init(dom);

  const periodosAnio = periodosDelAnio(anio);
  const metricaId = tipo === "total" ? null : metricaIdDe(tipo);
  const ejeX = periodosAnio.map(mesCorto);
  const datos = periodosAnio.map((p) => {
    if (metricaId) return sumaDimension(metricaId, agregacion, p) || null;
    const { total } = totalesGnGnl(agregacion, p);
    return total || null;
  });

  chartEvolucion.setOption(
    {
      tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "—" : `${formatoNumero(v)} GWh`) },
      grid: { left: 56, right: 16, top: 20, bottom: 24 },
      xAxis: { type: "category", data: ejeX, axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", name: "GWh", axisLabel: { fontSize: 10 } },
      series: [
        {
          type: "bar",
          data: datos,
          barMaxWidth: 34,
          itemStyle: { color: getComputedStyle(document.documentElement).getPropertyValue("--chart-1").trim() },
          label: { show: true, position: "top", fontSize: 9, formatter: (i) => (i.value == null ? "" : formatoNumero(i.value)) },
        },
      ],
    },
    true
  );
  return chartEvolucion;
}

export function pintarPaisesPie(dom, tipo, agregacion, periodo) {
  if (!chartPaisesPie) chartPaisesPie = echarts.init(dom);

  const lista = paisesDelPeriodo(tipo, agregacion, periodo);
  const top = lista.slice(0, TOP_N_PAISES);
  const restoValor = lista.slice(TOP_N_PAISES).reduce((acc, p) => acc + p.valor, 0);
  const datos = top.map((p) => ({ name: p.pais, value: Math.round(p.valor) }));
  if (restoValor > 0) datos.push({ name: "Otros", value: Math.round(restoValor) });

  chartPaisesPie.setOption(
    {
      tooltip: { formatter: (i) => `${i.name}: ${formatoNumero(i.value)} GWh (${formatoNumero(i.percent, 0)}%)` },
      legend: { bottom: 0, type: "scroll", textStyle: { color: "inherit", fontSize: 10 } },
      series: [
        {
          type: "pie",
          radius: ["42%", "70%"],
          center: ["50%", "38%"],
          data: datos,
          label: { formatter: (i) => `${formatoNumero(i.percent, 0)}%`, fontSize: 10 },
          color: datos.map((_, i) => colorPorIndice(i)),
        },
      ],
    },
    true
  );
  return chartPaisesPie;
}

export function resize() {
  chartEvolucion && chartEvolucion.resize();
  chartPaisesPie && chartPaisesPie.resize();
}
