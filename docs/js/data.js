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

/** Periodos de un año concreto ("2025"), ordenados. Para gráficas que
 * muestran la evolución mes a mes de UN año (p.ej. Aprovisionamiento):
 * deben reaccionar al selector de año pero no al de mes. */
export function periodosDelAnio(anio) {
  return _periodos.filter((p) => p.startsWith(`${anio}-`));
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

/** Reconstruye el valor del mismo mes del año anterior a partir del
 * var_pct_interanual que ya trae cada fila (publicado por el propio
 * Boletín/Progreso de Enagás): valor_actual = valor_año_anterior · (1 + var/100).
 * No inventa datos nuevos: solo despeja en la otra dirección el mismo
 * porcentaje que ya se muestra en el dashboard. Se usa para las
 * variaciones interanuales de las tarjetas (Resumen, Aprovisionamiento)
 * aunque el histórico propio del observatorio solo tenga un año. */
export function valorAnioAnterior(metricaId, agregacion, periodo) {
  const { valor, var_pct_interanual } = valorEscalar(metricaId, agregacion, periodo);
  if (valor === null || var_pct_interanual === null || var_pct_interanual === undefined) return null;
  const divisor = 1 + var_pct_interanual / 100;
  if (divisor === 0) return null;
  return valor / divisor;
}

/** Periodo inmediatamente anterior en el histórico cargado (para
 * variaciones mes a mes calculadas por el propio dashboard, no
 * publicadas por Enagás). */
export function periodoAnterior(periodo) {
  const idx = _periodos.indexOf(periodo);
  return idx > 0 ? _periodos[idx - 1] : null;
}

/** Suma de todas las filas con dimensión (p.ej. países, plantas) de una
 * métrica en un periodo/agregación dados. */
export function sumaDimension(metricaId, agregacion, periodo) {
  return filasDe(metricaId, agregacion, periodo)
    .filter((f) => f.valor !== null)
    .reduce((acc, f) => acc + f.valor, 0);
}

/** Igual que sumaDimension pero reconstruyendo el año anterior fila a
 * fila (ver valorAnioAnterior) antes de sumar -- para no perder precisión
 * promediando porcentajes ya agregados. */
export function sumaDimensionAnioAnterior(metricaId, agregacion, periodo) {
  return filasDe(metricaId, agregacion, periodo)
    .filter((f) => f.valor !== null && f.var_pct_interanual !== null && f.var_pct_interanual !== undefined)
    .reduce((acc, f) => acc + f.valor / (1 + f.var_pct_interanual / 100), 0);
}
