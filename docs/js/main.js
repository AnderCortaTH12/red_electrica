import { cargarDatos, periodos, ultimoPeriodo, ultimo, catalogo, valorEscalar, filasDe, metrica } from "./data.js";
import { AGREGACIONES, nombreMes, formatoNumero, formatoPct, claseVariacion, debounce } from "./utils.js";
import { pintarSparkline } from "./charts/sparkline.js";
import * as Desglose from "./charts/desglose.js";
import * as Comparativa from "./charts/comparativa.js";
import * as Aprovisionamiento from "./charts/aprovisionamiento.js";
import * as Infraestructuras from "./charts/infraestructuras.js";

const KPI_METRICAS = ["total_salidas", "demanda_nacional", "demanda_convencional", "demanda_sector_electrico"];
const CCAA_COLUMNAS = [
  { id: "demanda_ccaa_convencional", etiqueta: "Convencional" },
  { id: "demanda_ccaa_sector_electrico", etiqueta: "Sector eléctrico" },
  { id: "demanda_ccaa_cisternas", etiqueta: "Cisternas" },
];

const estado = {
  agregacion: "mes",
  periodo: null,
  vista: "resumen",
  comparativaSeleccion: new Set(KPI_METRICAS),
  ordenTerritorio: { columna: "demanda_ccaa_convencional", asc: false },
};

async function iniciar() {
  try {
    await cargarDatos();
  } catch (err) {
    document.querySelector("main").innerHTML = `<div class="empty-state">No se pudieron cargar los datos: ${err.message}</div>`;
    return;
  }

  estado.periodo = ultimoPeriodo();

  construirSegmentedControl();
  construirSelectorPeriodo();
  construirTabs();
  pintarFooter();

  renderVistaActiva();

  window.addEventListener(
    "resize",
    debounce(() => {
      Desglose.resize();
      Comparativa.resize();
      Aprovisionamiento.resize();
      Infraestructuras.resize();
    }, 150)
  );
}

// ---------- Controles globales ----------

function construirSegmentedControl() {
  const cont = document.getElementById("segmented-agregacion");
  cont.innerHTML = "";
  for (const { id, etiqueta } of AGREGACIONES) {
    const btn = document.createElement("button");
    btn.textContent = etiqueta;
    btn.className = id === estado.agregacion ? "active" : "";
    btn.addEventListener("click", () => {
      estado.agregacion = id;
      [...cont.children].forEach((b) => b.classList.toggle("active", b === btn));
      renderVistaActiva();
    });
    cont.appendChild(btn);
  }
}

function construirSelectorPeriodo() {
  const sel = document.getElementById("selector-periodo");
  sel.innerHTML = "";
  for (const p of periodos()) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = nombreMes(p);
    sel.appendChild(opt);
  }
  sel.value = estado.periodo;
  sel.addEventListener("change", () => {
    estado.periodo = sel.value;
    renderVistaActiva();
  });
}

function construirTabs() {
  const botones = document.querySelectorAll(".tab-btn");
  botones.forEach((btn) => {
    btn.addEventListener("click", () => {
      botones.forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${btn.dataset.view}`));
      estado.vista = btn.dataset.view;
      renderVistaActiva();
    });
  });
}

function renderVistaActiva() {
  switch (estado.vista) {
    case "resumen":
      renderResumen();
      break;
    case "desglose":
      renderDesglose();
      break;
    case "comparativa":
      renderComparativa();
      break;
    case "territorio":
      renderTerritorio();
      break;
    case "aprovisionamiento":
      renderAprovisionamiento();
      break;
    case "infraestructuras":
      renderInfraestructuras();
      break;
  }
}

// ---------- Vista: Resumen ----------

function renderResumen() {
  const cont = document.getElementById("kpi-grid");
  cont.innerHTML = "";

  for (const metricaId of KPI_METRICAS) {
    const info = metrica(metricaId);
    const { valor, var_pct_interanual } = valorEscalar(metricaId, estado.agregacion, estado.periodo);

    const card = document.createElement("div");
    card.className = "card kpi-card";
    card.innerHTML = `
      <div class="kpi-label">${info.nombre}</div>
      <div class="kpi-value">${formatoNumero(valor)} <span class="kpi-unit">${info.unidad_canonica}</span></div>
      <span class="kpi-delta ${claseVariacion(var_pct_interanual)}">${formatoPct(var_pct_interanual)} interanual</span>
      <div class="kpi-sparkline"></div>
    `;
    cont.appendChild(card);

    const puntos = periodos().map((p) => [p, valorEscalar(metricaId, estado.agregacion, p).valor]);
    const dom = card.querySelector(".kpi-sparkline");
    requestAnimationFrame(() => pintarSparkline(dom, puntos, var_pct_interanual === null ? null : var_pct_interanual >= 0));
  }
}

// ---------- Vista: Desglose ----------

function renderDesglose() {
  const dom = document.getElementById("chart-desglose");
  Desglose.pintarDesglose(dom, estado.agregacion, estado.periodo);
}

// ---------- Vista: Comparativa ----------

function metricasComparables() {
  return catalogo().filter((m) => m.dimension === null);
}

function renderComparativa() {
  const chips = document.getElementById("chips-comparativa");
  if (chips.childElementCount === 0) {
    for (const m of metricasComparables()) {
      const chip = document.createElement("button");
      chip.className = "chip" + (estado.comparativaSeleccion.has(m.metrica_id) ? " selected" : "");
      chip.textContent = m.nombre;
      chip.addEventListener("click", () => {
        if (estado.comparativaSeleccion.has(m.metrica_id)) {
          estado.comparativaSeleccion.delete(m.metrica_id);
        } else {
          estado.comparativaSeleccion.add(m.metrica_id);
        }
        chip.classList.toggle("selected");
        dibujarComparativa();
      });
      chips.appendChild(chip);
    }
  }
  dibujarComparativa();
}

function dibujarComparativa() {
  const dom = document.getElementById("chart-comparativa");
  const seleccion = [...estado.comparativaSeleccion];
  if (seleccion.length === 0) {
    dom.parentElement.querySelector(".empty-state")?.remove();
    const vacio = document.createElement("div");
    vacio.className = "empty-state";
    vacio.textContent = "Elige al menos una métrica para comparar.";
    dom.replaceWith(vacio);
    return;
  }
  Comparativa.pintarComparativa(dom, seleccion, estado.agregacion);
}

// ---------- Vista: Territorio ----------

// El Boletín solo publica el desglose por CCAA en columna mensual (sin
// acumulado/TAM, a diferencia del resto de métricas) -- esta vista
// ignora a propósito el control global de agregación y lo deja fijo en
// "mes", en vez de mostrar una tabla vacía cuando se elige otra.
const AGREGACION_TERRITORIO = "mes";

function filaCCAA(nombreCCAA) {
  const fila = { ccaa: nombreCCAA };
  for (const { id } of CCAA_COLUMNAS) {
    const encontrada = filasDe(id, AGREGACION_TERRITORIO, estado.periodo).find((f) => f.dimension === nombreCCAA);
    fila[id] = encontrada ? encontrada.valor : null;
    fila[`${id}_var`] = encontrada ? encontrada.var_pct_interanual : null;
  }
  return fila;
}

function renderTerritorio() {
  document.getElementById("aviso-agregacion-territorio").style.display =
    estado.agregacion === AGREGACION_TERRITORIO ? "none" : "block";

  const nombresCCAA = [
    ...new Set(
      CCAA_COLUMNAS.flatMap(({ id }) => filasDe(id, AGREGACION_TERRITORIO, estado.periodo).map((f) => f.dimension))
    ),
  ].filter(Boolean);

  let filas = nombresCCAA.map(filaCCAA);

  const { columna, asc } = estado.ordenTerritorio;
  filas.sort((a, b) => {
    const va = columna === "ccaa" ? a.ccaa : a[columna] ?? -Infinity;
    const vb = columna === "ccaa" ? b.ccaa : b[columna] ?? -Infinity;
    if (typeof va === "string") return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    return asc ? va - vb : vb - va;
  });

  const thead = document.getElementById("territorio-thead");
  const columnas = [{ id: "ccaa", etiqueta: "Comunidad autónoma" }, ...CCAA_COLUMNAS];
  thead.innerHTML =
    "<tr>" +
    columnas
      .map(({ id, etiqueta }) => {
        const clases = ["th-orden"];
        if (columna === id) clases.push("sorted", asc ? "asc" : "");
        return `<th data-col="${id}" class="${clases.join(" ")}">${etiqueta}</th>`;
      })
      .join("") +
    "</tr>";
  thead.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      estado.ordenTerritorio =
        estado.ordenTerritorio.columna === col
          ? { columna: col, asc: !estado.ordenTerritorio.asc }
          : { columna: col, asc: false };
      renderTerritorio();
    });
  });

  const tbody = document.getElementById("territorio-tbody");
  if (filas.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${columnas.length}" class="empty-state">Sin datos por CCAA para este periodo.</td></tr>`;
    return;
  }
  tbody.innerHTML = filas
    .map(
      (f) => `
      <tr>
        <td>${f.ccaa}</td>
        ${CCAA_COLUMNAS.map(
          ({ id }) => `
          <td>${formatoNumero(f[id])} GWh
            ${f[`${id}_var`] !== null ? `<br/><span class="kpi-delta ${claseVariacion(f[`${id}_var`])}" style="font-size:.72rem">${formatoPct(f[`${id}_var`])}</span>` : ""}
          </td>`
        ).join("")}
      </tr>`
    )
    .join("");
}

// ---------- Vista: Aprovisionamiento ----------

// pct_total_gn/pct_total_gnl (el donut) solo vienen en columna mensual
// en el Boletín, a diferencia de aprovisionamiento_gn/gnl y los saldos
// por conexión, que sí traen las 3 agregaciones -- mismo patrón que
// Territorio e Infraestructuras (ver AGREGACION_TERRITORIO).
const AGREGACION_DONUT = "mes";

function renderAprovisionamiento() {
  document.getElementById("aviso-agregacion-donut").style.display =
    estado.agregacion === AGREGACION_DONUT ? "none" : "block";

  Aprovisionamiento.pintarPaises(document.getElementById("chart-paises"), estado.agregacion);
  Aprovisionamiento.pintarDonutOrigen(document.getElementById("chart-donut-origen"), AGREGACION_DONUT, estado.periodo);
  Aprovisionamiento.pintarSaldosConexion(document.getElementById("chart-saldos"), estado.agregacion, estado.periodo);
}

// ---------- Vista: Infraestructuras ----------

// Igual que el desglose por CCAA: ni las plantas de regasificación ni
// el TVB traen columna de acumulado/TAM en el Boletín, solo mensual.
const AGREGACION_INFRAESTRUCTURAS = "mes";

function renderInfraestructuras() {
  document.getElementById("aviso-agregacion-infraestructuras").style.display =
    estado.agregacion === AGREGACION_INFRAESTRUCTURAS ? "none" : "block";

  Infraestructuras.pintarPlantas(document.getElementById("chart-plantas"), AGREGACION_INFRAESTRUCTURAS, estado.periodo);
  Infraestructuras.pintarTvb(document.getElementById("chart-tvb"), AGREGACION_INFRAESTRUCTURAS, estado.periodo);
}

// ---------- Pie de página ----------

function pintarFooter() {
  const info = ultimo();
  const el = document.getElementById("footer-info");
  const fecha = info.generado_el ? new Date(info.generado_el).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" }) : "—";
  el.innerHTML = `
    Último periodo cargado: <strong>${nombreMes(info.periodo)}</strong> ·
    Última actualización: <strong>${fecha}</strong><br/>
    Los datos de Enagás son un <strong>AVANCE</strong> provisional sujeto a revisión en publicaciones posteriores.
    Fuentes: <a href="https://www.enagas.es/es/gestion-tecnica-sistema/energy-data/publicaciones/boletin-estadistico-gas/" target="_blank" rel="noopener">Boletín Estadístico del Gas</a>
    y <a href="https://www.enagas.es/es/gestion-tecnica-sistema/energy-data/publicaciones/demanda-gas/" target="_blank" rel="noopener">Progreso mensual de la demanda</a>.
  `;
}

iniciar();
