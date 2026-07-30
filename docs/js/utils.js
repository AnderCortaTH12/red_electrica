// Utilidades compartidas: formato, color, fechas.
//
// Los datos siempre viajan en UTC ("...Z"); la conversión a hora de
// Madrid se hace SIEMPRE aquí, en el cliente, con Intl.DateTimeFormat
// (que maneja el cambio de hora de forma nativa y correcta) — nunca a
// mano con sumas de horas, que es como se coló el bug de DST en el
// backend (ver README, Fase 3).

export const MADRID_TZ = "Europe/Madrid";

const HOUR_FORMATTER = new Intl.DateTimeFormat("es-ES", {
  timeZone: MADRID_TZ,
  hour: "2-digit",
  minute: "2-digit",
});

const DATETIME_FORMATTER = new Intl.DateTimeFormat("es-ES", {
  timeZone: MADRID_TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const DATE_FORMATTER = new Intl.DateTimeFormat("es-ES", {
  timeZone: MADRID_TZ,
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const WEEKDAY_SHORT_FORMATTER = new Intl.DateTimeFormat("es-ES", {
  timeZone: MADRID_TZ,
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
});

export function formatHourMadrid(isoUtc) {
  return HOUR_FORMATTER.format(new Date(isoUtc));
}

export function formatDatetimeMadrid(isoUtc) {
  return DATETIME_FORMATTER.format(new Date(isoUtc));
}

export function formatDateMadrid(isoUtc) {
  return DATE_FORMATTER.format(new Date(isoUtc));
}

export function formatWeekdayShort(isoUtc) {
  return WEEKDAY_SHORT_FORMATTER.format(new Date(isoUtc));
}

export function formatPrice(value, unit = " €/MWh") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${numberFormat(value)}${unit}`;
}

export function numberFormat(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${numberFormat(value, digits)}%`;
}

// Paleta de generación: fija y con significado. Renovables en verdes/
// azules, fósiles en grises/marrones, nuclear diferenciada. Mismos
// colores en TODOS los gráficos donde aparezca cada tecnología.
export const GEN_SERIES = [
  { key: "gen_eolica", label: "Eólica", color: "#2FD3A6" },
  { key: "gen_solar_fv", label: "Solar FV", color: "#F5B93F" },
  { key: "gen_solar_termica", label: "Solar térmica", color: "#E8823C" },
  { key: "gen_hidraulica", label: "Hidráulica", color: "#4FA3E3" },
  { key: "gen_nuclear", label: "Nuclear", color: "#B085F0" },
  { key: "gen_ciclo_combinado", label: "Ciclo combinado", color: "#8C7A66" },
  { key: "gen_carbon", label: "Carbón", color: "#6B7280" },
];

export const RENEWABLE_KEYS = new Set(["gen_eolica", "gen_solar_fv", "gen_solar_termica", "gen_hidraulica"]);

export const COLORS = {
  precioReal: "#E6E9EF",
  precioModelo: "#F5734C",
  precioBaseline: "#5B7A99",
  negativo: "rgba(239, 68, 68, 0.12)",
  regimeNormal: "rgba(79, 163, 255, 0.08)",
  regimeTopeGas: "rgba(245, 169, 35, 0.10)",
  regimePostTope: "rgba(239, 68, 68, 0.08)",
  green: "#29D398",
  amber: "#F5A623",
  red: "#EF4444",
};

export function isDarkMode() {
  const stored = document.documentElement.getAttribute("data-theme");
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function chartTextColor() {
  return isDarkMode() ? "#8a93a6" : "#5b6470";
}

export function chartGridColor() {
  return isDarkMode() ? "#1a212c" : "#e3e6ea";
}

// YYYY-MM-DD (calendario UTC, igual que summary.json/monthly -- lo
// documentamos así en vez de intentar mapear a días de Madrid, para no
// reintroducir líos de DST en la propia navegación del dashboard).
export function utcDateStr(date) {
  return date.toISOString().slice(0, 10);
}

export function addDaysUtc(dateStr, days) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return utcDateStr(d);
}

export function yearMonthFromDateStr(dateStr) {
  return dateStr.slice(0, 7);
}
