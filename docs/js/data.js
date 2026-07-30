// Carga de datos: fetch con manejo de error explícito (nunca una
// pantalla en blanco si un JSON falta o el fetch falla) y caché en
// memoria para no repetir peticiones del mismo mensual al navegar.

const monthlyCache = new Map();

export class DataError extends Error {}

async function fetchJson(path) {
  let response;
  try {
    response = await fetch(path, { cache: "no-cache" });
  } catch (err) {
    throw new DataError(`No se pudo conectar para cargar ${path}`);
  }
  if (!response.ok) {
    throw new DataError(`${path} respondió ${response.status}`);
  }
  try {
    return await response.json();
  } catch (err) {
    throw new DataError(`${path} no es JSON válido`);
  }
}

export async function loadLatest() {
  return fetchJson("data/latest.json");
}

export async function loadModelPerformance() {
  return fetchJson("data/model_performance.json");
}

export async function loadSummary() {
  const raw = await fetchJson("data/summary.json");
  // transpone {columns, rows} a un array de objetos, mas comodo para
  // el resto del codigo
  const { columns, rows } = raw;
  return rows.map((row) => {
    const obj = {};
    columns.forEach((col, i) => {
      obj[col] = row[i];
    });
    return obj;
  });
}

export async function loadMonth(yearMonth) {
  if (monthlyCache.has(yearMonth)) return monthlyCache.get(yearMonth);
  const data = await fetchJson(`data/monthly/${yearMonth}.json`);
  monthlyCache.set(yearMonth, data);
  return data;
}

/** Extrae las 24h de un día concreto (YYYY-MM-DD, calendario UTC) de
 * un JSON mensual ya cargado. */
export function extractDay(monthData, dateStr) {
  const indices = [];
  monthData.datetime_utc.forEach((t, i) => {
    if (t.startsWith(dateStr)) indices.push(i);
  });
  if (indices.length === 0) return null;

  const pick = (key) => indices.map((i) => monthData[key][i]);
  return {
    datetime_utc: pick("datetime_utc"),
    precio_real: pick("precio_real"),
    precio_modelo: pick("precio_modelo"),
    precio_baseline: pick("precio_baseline"),
    demanda_real: pick("demanda_real"),
    gen_eolica: pick("gen_eolica"),
    gen_solar_fv: pick("gen_solar_fv"),
    gen_solar_termica: pick("gen_solar_termica"),
    gen_nuclear: pick("gen_nuclear"),
    gen_hidraulica: pick("gen_hidraulica"),
    gen_ciclo_combinado: pick("gen_ciclo_combinado"),
    gen_carbon: pick("gen_carbon"),
  };
}
