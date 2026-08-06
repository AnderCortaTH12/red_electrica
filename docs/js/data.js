// Carga y consulta de los datos del observatorio. El dataset completo
// (docs/data/serie.json) son unos pocos miles de filas con 6 meses de
// 2026 -- cabe de sobra cargarlo entero en memoria, a diferencia de un
// proyecto con series horarias de años (ahí sí haría falta paginar por
// mes, ver el proyecto de forecasting eléctrico anterior).

let _catalogo = null;
let _catalogoPorId = null;
let _serie = null;
let _ultimo = null;
let _periodos = null;

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`No se pudo cargar ${path}: HTTP ${res.status}`);
  return res.json();
}

export async function cargarDatos() {
  const [catalogo, serie, ultimo] = await Promise.all([
    fetchJson("data/catalogo.json"),
    fetchJson("data/serie.json"),
    fetchJson("data/ultimo.json"),
  ]);

  _catalogo = catalogo;
  _catalogoPorId = Object.fromEntries(catalogo.map((m) => [m.metrica_id, m]));
  _ultimo = ultimo;

  // De {columns, rows} a objetos, y un índice por
  // metrica_id|dimension|agregacion|periodo para lookups O(1).
  const cols = serie.columns;
  _serie = serie.rows.map((row) => Object.fromEntries(cols.map((c, i) => [c, row[i]])));

  _periodos = [...new Set(_serie.map((r) => r.periodo))].sort();

  return { catalogo: _catalogo, serie: _serie, ultimo: _ultimo, periodos: _periodos };
}

export function catalogo() {
  return _catalogo;
}

export function metrica(metricaId) {
  return _catalogoPorId[metricaId];
}

export function periodos() {
  return _periodos;
}

export function ultimoPeriodo() {
  return _periodos[_periodos.length - 1];
}

export function ultimo() {
  return _ultimo;
}

/** Todas las filas de una métrica para una agregación dada (todas las
 * dimensiones y periodos), o filtradas por periodo si se pasa. */
export function filasDe(metricaId, agregacion, periodo = null) {
  return _serie.filter(
    (r) => r.metrica_id === metricaId && r.agregacion === agregacion && (periodo === null || r.periodo === periodo)
  );
}

/** Valor escalar (dimension = null) de una métrica en un periodo y
 * agregación concretos. */
export function valorEscalar(metricaId, agregacion, periodo) {
  const fila = _serie.find(
    (r) => r.metrica_id === metricaId && r.agregacion === agregacion && r.periodo === periodo && r.dimension === null
  );
  return fila ? { valor: fila.valor, var_pct_interanual: fila.var_pct_interanual } : { valor: null, var_pct_interanual: null };
}

/** Serie temporal [[periodo, valor], ...] de una métrica escalar para
 * una agregación, en todos los periodos disponibles. */
export function serieTemporal(metricaId, agregacion) {
  return _periodos.map((p) => [p, valorEscalar(metricaId, agregacion, p).valor]);
}

/** Hijos directos (por `padre`) de una métrica en el catálogo. */
export function hijosDe(metricaId) {
  return _catalogo.filter((m) => m.padre === metricaId);
}

export function raicesJerarquia() {
  return _catalogo.filter((m) => m.padre === null && m.dimension === null && !m.metrica_id.startsWith("tvb_") && !m.metrica_id.startsWith("planta_"));
}
