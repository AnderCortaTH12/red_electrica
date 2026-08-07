// Utilidades compartidas: formato de números, colores por variación,
// nombres de agregación/mes en español.

export const AGREGACIONES = [
  { id: "mes", etiqueta: "Mes" },
  { id: "acumulado_anual", etiqueta: "Acumulado del año" },
  { id: "tam", etiqueta: "Total anual móvil" },
];

const MESES_CORTOS = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

export function nombreMes(periodo) {
  if (!periodo) return "";
  const [anio, mes] = periodo.split("-").map(Number);
  return `${MESES_CORTOS[mes - 1]}-${String(anio).slice(2)}`;
}

/** Solo el mes, sin año -- para ejes de gráficas que ya están acotadas
 * a un único año (ver periodosDelAnio en data.js) y no necesitan
 * repetirlo en cada etiqueta. */
export function mesCorto(periodo) {
  if (!periodo) return "";
  const mes = Number(periodo.split("-")[1]);
  return MESES_CORTOS[mes - 1];
}

const MESES_LARGOS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

/** Nombre de mes completo a partir de su número ("01".."12") -- para el
 * selector de mes del selector de fecha (año + mes por separado). */
export function nombreMesLargo(mesStr) {
  return MESES_LARGOS[Number(mesStr) - 1] ?? mesStr;
}

export function formatoNumero(valor, decimales = 0) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).format(valor);
}

export function formatoPct(valor, decimales = 1) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  const signo = valor > 0 ? "+" : "";
  return `${signo}${formatoNumero(valor, decimales)}%`;
}

export function claseVariacion(valor) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "neutral";
  if (valor > 0) return "positive";
  if (valor < 0) return "negative";
  return "neutral";
}

const PALETA = [
  "var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)",
  "var(--chart-5)", "var(--chart-6)", "var(--chart-7)", "var(--chart-8)",
];

export function colorPorIndice(i) {
  return PALETA[i % PALETA.length].startsWith("var")
    ? getComputedStyle(document.documentElement).getPropertyValue(PALETA[i % PALETA.length].slice(4, -1)).trim()
    : PALETA[i % PALETA.length];
}

export function esModoOscuro() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function temaEcharts() {
  const estilo = getComputedStyle(document.documentElement);
  return {
    textColor: estilo.getPropertyValue("--text").trim(),
    subTextColor: estilo.getPropertyValue("--text-secondary").trim(),
    borderColor: estilo.getPropertyValue("--border").trim(),
    bgElevado: estilo.getPropertyValue("--bg-elevated").trim(),
  };
}

// Debounce simple para el redimensionado de gráficos ECharts.
export function debounce(fn, ms = 120) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
