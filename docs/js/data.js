// Carga de datos: fetch con manejo de error explícito (nunca una
// pantalla en blanco si un JSON falta o el fetch falla) y caché en
// memoria para no repetir peticiones del mismo mensual al navegar.

import { addDays, madridDateStr, yearMonthFromDateStr } from "./utils.js";

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

const DAY_KEYS = [
  "datetime_utc",
  "precio_real",
  "precio_modelo",
  "precio_baseline",
  "demanda_real",
  "gen_eolica",
  "gen_solar_fv",
  "gen_solar_termica",
  "gen_nuclear",
  "gen_hidraulica",
  "gen_ciclo_combinado",
  "gen_carbon",
];

/** Extrae las 24h de un día natural ESPAÑOL (YYYY-MM-DD en
 * Europe/Madrid) de uno o varios JSON mensuales ya cargados.
 *
 * Recibe varios meses porque un día de Madrid empieza a las 22:00Z o
 * 23:00Z del día UTC anterior (según horario de verano): el día 1 de
 * cada mes tiene sus primeras horas en el fichero del mes anterior. */
export function extractDay(monthDatas, dateStr) {
  const months = Array.isArray(monthDatas) ? monthDatas : [monthDatas];
  const day = {};
  DAY_KEYS.forEach((k) => (day[k] = []));

  months.filter(Boolean).forEach((monthData) => {
    monthData.datetime_utc.forEach((t, i) => {
      if (madridDateStr(t) !== dateStr) return;
      DAY_KEYS.forEach((k) => day[k].push(monthData[k][i]));
    });
  });

  return day.datetime_utc.length === 0 ? null : day;
}

/** Carga los meses necesarios y devuelve el día de Madrid ya extraído. */
export async function loadDay(dateStr) {
  const yearMonth = yearMonthFromDateStr(dateStr);
  const prevMonth = yearMonthFromDateStr(addDays(dateStr, -1));

  const months = [await loadMonth(yearMonth)];
  if (prevMonth !== yearMonth) {
    // el mes anterior puede no existir (inicio de la serie): que falte
    // no debe impedir mostrar el resto del día
    try {
      months.unshift(await loadMonth(prevMonth));
    } catch (err) {
      /* sin mes previo: se muestran las horas disponibles */
    }
  }
  return extractDay(months, dateStr);
}
