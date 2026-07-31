import { loadLatest, loadMonth, loadModelPerformance, loadSummary, extractDay, DataError } from "./data.js";
import {
  formatDatetimeMadrid,
  formatPercent,
  formatPrice,
  numberFormat,
  utcDateStr,
  addDaysUtc,
  yearMonthFromDateStr,
} from "./utils.js";
import { renderPriceChart } from "./charts/priceChart.js";
import { renderDayChart } from "./charts/dayChart.js";
import { renderMixDonut } from "./charts/mixDonut.js";
import { renderLongTermChart } from "./charts/longTermChart.js";
import { renderErrorByYearChart, renderScatterChart } from "./charts/performanceChart.js";

const charts = []; // para resize()

function trackChart(instance) {
  if (instance) charts.push(instance);
}

window.addEventListener("resize", () => {
  charts.forEach((c) => {
    try {
      c.resize();
    } catch (err) {
      // el contenedor pudo haberse vaciado (chart-empty); ignorar
    }
  });
});

function sectionError(el, message) {
  el.innerHTML = `<p class="chart-empty">⚠ ${message}</p>`;
}

// ---- Cabecera de estado ----

function renderStatusBar(latest) {
  const bar = document.getElementById("status-bar");
  const { status, kpis } = latest;

  const healthClass =
    status.health === "green" ? "health-green" : status.health === "amber" ? "health-amber" : "health-red";

  const deltaClass =
    kpis.delta_vs_ayer_pct === null ? "" : kpis.delta_vs_ayer_pct >= 0 ? "delta-up" : "delta-down";

  let flagsHtml = "";
  if (status.quality_flags && status.quality_flags.length > 0) {
    flagsHtml =
      '<div class="quality-flags">' +
      status.quality_flags
        .map((f) => `<span class="quality-flag">⚠ ${f.nombre ? f.nombre + ": " : ""}${f.detalle}</span>`)
        .join("") +
      "</div>";
  }

  bar.innerHTML = `
    <span class="brand">Forecasting Eléctrico</span>
    <span class="status-item">
      <span class="value price tabular">${formatPrice(kpis.precio_actual)}</span>
    </span>
    <span class="status-item">
      <span class="label">vs ayer</span>
      <span class="value tabular ${deltaClass}">${formatPercent(kpis.delta_vs_ayer_pct)}</span>
    </span>
    <span class="status-item">
      <span class="label">Actualizado</span>
      <span class="value">${status.last_run_at ? formatDatetimeMadrid(status.last_run_at) : "—"}</span>
    </span>
    <span class="status-item">
      <span class="label">Modelo</span>
      <span class="value">${status.model_type || "—"} · ${
    status.model_version ? formatDatetimeMadrid(status.model_version) : "sin entrenar"
  }</span>
    </span>
    <span class="status-item">
      <span class="health-dot ${healthClass}"></span>
      <span class="value">${status.health === "green" ? "OK" : status.health === "amber" ? "Avisos" : "Fallo"}</span>
    </span>
    ${flagsHtml}
  `;
}

// ---- Sección día: estado compartido ----

const dayState = { currentDate: null };

function renderDayKpis(day) {
  const el = document.getElementById("day-kpis");
  if (!day) {
    el.innerHTML = "";
    return;
  }
  const prices = day.precio_real.filter((v) => v !== null && v !== undefined);
  const min = prices.length ? Math.min(...prices) : null;
  const max = prices.length ? Math.max(...prices) : null;
  const mean = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;

  el.innerHTML = `
    <div><div class="kpi-value tabular">${formatPrice(min, "")}</div><div class="kpi-label">Mín €/MWh</div></div>
    <div><div class="kpi-value tabular">${formatPrice(mean, "")}</div><div class="kpi-label">Media €/MWh</div></div>
    <div><div class="kpi-value tabular">${formatPrice(max, "")}</div><div class="kpi-label">Máx €/MWh</div></div>
  `;
}

async function loadAndRenderDay(dateStr) {
  dayState.currentDate = dateStr;
  const picker = document.getElementById("day-picker");
  if (picker.value !== dateStr) picker.value = dateStr;

  const loadingEl = document.getElementById("day-loading");
  const dayChartEl = document.getElementById("day-chart");
  const donutEl = document.getElementById("mix-donut");
  loadingEl.hidden = false;

  try {
    const yearMonth = yearMonthFromDateStr(dateStr);
    const monthData = await loadMonth(yearMonth);
    const day = extractDay(monthData, dateStr);

    if (!day) {
      sectionError(dayChartEl, "No hay datos para este día todavía.");
      donutEl.innerHTML = "";
      renderDayKpis(null);
      return;
    }

    trackChart(renderDayChart(dayChartEl, day));
    trackChart(renderMixDonut(donutEl, day));
    renderDayKpis(day);
  } catch (err) {
    const message = err instanceof DataError ? err.message : "Error inesperado cargando el día.";
    sectionError(dayChartEl, message);
    donutEl.innerHTML = "";
    renderDayKpis(null);
  } finally {
    loadingEl.hidden = true;
  }
}

function setupDayControls(latestDateStr) {
  const picker = document.getElementById("day-picker");
  picker.max = latestDateStr;
  picker.value = latestDateStr;
  picker.addEventListener("change", () => {
    if (picker.value) loadAndRenderDay(picker.value);
  });

  document.querySelectorAll(".quick-buttons button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.quick;
      let target = latestDateStr;
      if (kind === "ayer") target = addDaysUtc(latestDateStr, -1);
      else if (kind === "7d") target = addDaysUtc(latestDateStr, -7);
      else if (kind === "año") target = addDaysUtc(latestDateStr, -365);
      loadAndRenderDay(target);
    });
  });
}

// ---- Sección rendimiento ----

function renderHonestyBlock(performance) {
  const el = document.getElementById("honesty-block");
  const holdout = performance.holdout || {};

  if (!holdout.mae_modelo) {
    el.innerHTML =
      "Todavía no hay una evaluación de holdout registrada para el modelo actual.";
    return;
  }

  const peor = holdout.mae_modelo > holdout.mae_baseline;
  const diferenciaPct = ((holdout.mae_modelo - holdout.mae_baseline) / holdout.mae_baseline) * 100;

  el.innerHTML = `
    <strong>El modelo actual (${holdout.modelo_tipo || "placeholder"}) ${
    peor ? "pierde contra" : "supera al"
  } baseline naive.</strong>
    En el holdout de evaluación (${holdout.test_start ? formatDatetimeMadrid(holdout.test_start).slice(0, 10) : "—"}
    en adelante, régimen ${holdout.regimen || "post_tope"}): MAE del modelo
    ${numberFormat(holdout.mae_modelo)} €/MWh frente a ${numberFormat(holdout.mae_baseline)} €/MWh del baseline
    (${peor ? "+" : ""}${numberFormat(diferenciaPct, 0)}% ${peor ? "peor" : "mejor"}).
    ${
      peor
        ? "Los modelos de árboles (como LightGBM) no pueden predecir por encima del precio " +
          "máximo visto en entrenamiento -- las predicciones quedan ancladas cerca de ese techo " +
          "mientras el precio real sigue subiendo. Por eso el modelo combina una tendencia lineal " +
          "(que sí extrapola) con un LightGBM sobre el residuo (ver README, Limitaciones conocidas)."
        : "El modelo combina una tendencia lineal (que extrapola más allá del rango visto en " +
          "entrenamiento) con un LightGBM sobre el residuo, precisamente para evitar quedarse " +
          "anclado cuando el precio sube fuera de ese rango."
    }
  `;
}

// ---- Arranque ----

async function main() {
  // 1) latest.json: siempre, bloquea el primer pintado util
  let latest;
  try {
    latest = await loadLatest();
    renderStatusBar(latest);
    trackChart(renderPriceChart(document.getElementById("price-chart"), latest));
  } catch (err) {
    sectionError(document.getElementById("price-chart"), "No se pudo cargar el estado actual.");
    document.getElementById("status-bar").innerHTML =
      '<span class="brand">Forecasting Eléctrico</span><span class="status-item">⚠ Sin datos</span>';
  }

  // 2) selector de dia: arranca en la ultima hora conocida de latest.json
  const latestDateStr =
    latest && latest.horas_72h && latest.horas_72h.datetime_utc.length
      ? latest.horas_72h.datetime_utc[latest.horas_72h.datetime_utc.length - 1].slice(0, 10)
      : utcDateStr(new Date());
  setupDayControls(latestDateStr);
  loadAndRenderDay(latestDateStr);

  // 3) largo plazo: no bloquea el resto
  loadSummary()
    .then((rows) => trackChart(renderLongTermChart(document.getElementById("longterm-chart"), rows)))
    .catch((err) =>
      sectionError(
        document.getElementById("longterm-chart"),
        err instanceof DataError ? err.message : "Error cargando la vista de largo plazo."
      )
    );

  // 4) rendimiento del modelo: no bloquea el resto
  loadModelPerformance()
    .then((performance) => {
      trackChart(renderErrorByYearChart(document.getElementById("error-chart"), performance));
      trackChart(renderScatterChart(document.getElementById("scatter-chart"), performance));
      renderHonestyBlock(performance);
    })
    .catch((err) => {
      const message = err instanceof DataError ? err.message : "Error cargando el rendimiento del modelo.";
      sectionError(document.getElementById("error-chart"), message);
      sectionError(document.getElementById("scatter-chart"), message);
      document.getElementById("honesty-block").textContent = message;
    });
}

main();
