import { cargarDatos, periodos, ultimoPeriodo, ultimo, valorEscalar, metrica, periodoAnterior } from "./data.js";
import { AGREGACIONES, nombreMes, nombreMesLargo, formatoNumero, formatoPct, claseVariacion, debounce } from "./utils.js";
import { pintarSparkline } from "./charts/sparkline.js";
import * as Resumen from "./charts/resumen.js";
import * as Aprovisionamiento from "./charts/aprovisionamiento.js";
import * as Infraestructuras from "./charts/infraestructuras.js";

// Como mucho 5 tarjetas en una fila (ver instrucción de layout): se
// deja fuera demanda_dc_pymes (el segmento más pequeño), que igualmente
// se ve en la gráfica "Demanda por sector" de al lado.
const KPI_METRICAS = ["demanda_nacional", "demanda_convencional", "demanda_industrial", "demanda_cisternas", "demanda_sector_electrico"];

const CCAA_METRICAS = [
  { id: "demanda_ccaa_convencional", etiqueta: "Convencional" },
  { id: "demanda_ccaa_sector_electrico", etiqueta: "Sector eléctrico" },
  { id: "demanda_ccaa_cisternas", etiqueta: "Cisternas" },
];

const TIPOS_GAS = [
  { id: "total", etiqueta: "Total" },
  { id: "gn", etiqueta: "GN" },
  { id: "gnl", etiqueta: "GNL" },
];

const estado = {
  agregacion: "mes",
  periodo: null,
  vista: "resumen",
  ccaaMetrica: "demanda_ccaa_sector_electrico",
  ordenTerritorio: { columna: "demanda_ccaa_sector_electrico", asc: false },
  tipoGas: "total",
  ccaaFiltro: null,
  plantaFiltro: null,
};

async function iniciar() {
  inicializarTema();

  try {
    await cargarDatos();
  } catch (err) {
    document.querySelector("main").innerHTML = `<div class="empty-state">No se pudieron cargar los datos: ${err.message}</div>`;
    return;
  }

  estado.periodo = ultimoPeriodo();

  construirSegmentedControl();
  construirSelectorFecha();
  construirTabs();
  construirSegmentedCCAA();
  construirSegmentedTipoGas();
  pintarFooter();

  renderVistaActiva();

  window.addEventListener(
    "resize",
    debounce(() => {
      Resumen.resize();
      Aprovisionamiento.resize();
      Infraestructuras.resize();
    }, 150)
  );
}

// ---------- Tema claro / oscuro ----------

function inicializarTema() {
  const boton = document.getElementById("theme-toggle");
  const sistemaOscuro = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  let tema = localStorage.getItem("tema") || (sistemaOscuro ? "dark" : "light");
  aplicarTema(tema);

  boton.addEventListener("click", () => {
    tema = tema === "dark" ? "light" : "dark";
    localStorage.setItem("tema", tema);
    aplicarTema(tema);
    // Los gráficos leen los colores de las variables CSS en el momento
    // de pintarse: hay que repintar la vista activa para que cambien.
    if (estado.periodo) renderVistaActiva();
  });
}

function aplicarTema(tema) {
  document.documentElement.dataset.theme = tema;
  document.getElementById("theme-toggle").textContent = tema === "dark" ? "☀️" : "🌙";
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

// Selector de fecha en dos pasos (año, luego mes) en vez de una lista
// plana "ene-26"..."jun-26": más legible y preparado para cuando haya
// más de un año de histórico.
function construirSelectorFecha() {
  const selAnio = document.getElementById("selector-anio");
  const selMes = document.getElementById("selector-mes");

  const mesesPorAnio = new Map();
  for (const p of periodos()) {
    const [anio, mes] = p.split("-");
    if (!mesesPorAnio.has(anio)) mesesPorAnio.set(anio, []);
    mesesPorAnio.get(anio).push(mes);
  }
  const anios = [...mesesPorAnio.keys()].sort();

  selAnio.innerHTML = anios.map((a) => `<option value="${a}">${a}</option>`).join("");

  function poblarMeses(anio) {
    selMes.innerHTML = mesesPorAnio.get(anio).map((m) => `<option value="${m}">${nombreMesLargo(m)}</option>`).join("");
  }

  const [anioActual, mesActual] = estado.periodo.split("-");
  selAnio.value = anioActual;
  poblarMeses(anioActual);
  selMes.value = mesActual;

  selAnio.addEventListener("change", () => {
    poblarMeses(selAnio.value);
    const mesesDelAnio = mesesPorAnio.get(selAnio.value);
    selMes.value = mesesDelAnio[mesesDelAnio.length - 1];
    estado.periodo = `${selAnio.value}-${selMes.value}`;
    renderVistaActiva();
  });
  selMes.addEventListener("change", () => {
    estado.periodo = `${selAnio.value}-${selMes.value}`;
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

function construirSegmentedCCAA() {
  const cont = document.getElementById("segmented-ccaa-metrica");
  cont.innerHTML = "";
  for (const { id, etiqueta } of CCAA_METRICAS) {
    const btn = document.createElement("button");
    btn.textContent = etiqueta;
    btn.className = id === estado.ccaaMetrica ? "active" : "";
    btn.addEventListener("click", () => {
      estado.ccaaMetrica = id;
      estado.ordenTerritorio = { columna: id, asc: false };
      [...cont.children].forEach((b) => b.classList.toggle("active", b === btn));
      renderResumenTerritorio();
    });
    cont.appendChild(btn);
  }
}

function construirSegmentedTipoGas() {
  const cont = document.getElementById("segmented-tipo-gas");
  cont.innerHTML = "";
  for (const { id, etiqueta } of TIPOS_GAS) {
    const btn = document.createElement("button");
    btn.textContent = etiqueta;
    btn.className = id === estado.tipoGas ? "active" : "";
    btn.addEventListener("click", () => {
      estado.tipoGas = id;
      [...cont.children].forEach((b) => b.classList.toggle("active", b === btn));
      renderPaisesYEvolucion();
    });
    cont.appendChild(btn);
  }
}

function renderVistaActiva() {
  switch (estado.vista) {
    case "resumen":
      renderResumen();
      break;
    case "aprovisionamiento":
      renderAprovisionamiento();
      break;
    case "infraestructuras":
      renderInfraestructuras();
      break;
  }
}

function variacionPropia(actual, base) {
  if (actual === null || actual === undefined || !base) return null;
  return ((actual - base) / base) * 100;
}

// ---------- Vista: Resumen ----------

function renderResumen() {
  const cont = document.getElementById("kpi-grid");
  cont.innerHTML = "";

  for (const metricaId of KPI_METRICAS) {
    const info = metrica(metricaId);
    const { valor, var_pct_interanual } = valorEscalar(metricaId, estado.agregacion, estado.periodo);
    const acumAnualPct = valorEscalar(metricaId, "acumulado_anual", estado.periodo).var_pct_interanual;

    const card = document.createElement("div");
    card.className = "card kpi-card";
    card.innerHTML = `
      <div class="kpi-label">${info.nombre}</div>
      <div class="kpi-value">${formatoNumero(valor)} <span class="kpi-unit">${info.unidad_canonica}</span></div>
      <div class="kpi-deltas">
        <span class="kpi-delta-row"><span class="kpi-delta-tag">Acum. año</span><span class="kpi-delta ${claseVariacion(acumAnualPct)}">${formatoPct(acumAnualPct)}</span></span>
        <span class="kpi-delta-row"><span class="kpi-delta-tag">Interanual</span><span class="kpi-delta ${claseVariacion(var_pct_interanual)}">${formatoPct(var_pct_interanual)}</span></span>
      </div>
      <div class="kpi-sparkline"></div>
    `;
    cont.appendChild(card);

    const puntos = periodos().map((p) => [p, valorEscalar(metricaId, estado.agregacion, p).valor]);
    const dom = card.querySelector(".kpi-sparkline");
    requestAnimationFrame(() => pintarSparkline(dom, puntos, var_pct_interanual === null ? null : var_pct_interanual >= 0));
  }

  Resumen.pintarSectores(document.getElementById("chart-sectores"), estado.agregacion, estado.periodo);
  renderResumenTerritorio();
}

// ---------- Vista: Resumen -> demanda por CCAA (mapa + tabla) ----------

// El Boletín solo publica el desglose por CCAA en columna mensual (sin
// acumulado/TAM, a diferencia del resto de métricas) -- esta sección
// ignora a propósito el control global de agregación y lo deja fijo en
// "mes", en vez de mostrar un mapa/tabla vacíos cuando se elige otra.
const AGREGACION_TERRITORIO = "mes";

function alClicarCCAA(ccaa) {
  estado.ccaaFiltro = estado.ccaaFiltro === ccaa ? null : ccaa;
  renderResumenTerritorio();
}

function renderResumenTerritorio() {
  document.getElementById("aviso-agregacion-territorio").style.display =
    estado.agregacion === AGREGACION_TERRITORIO ? "none" : "block";

  Resumen.pintarMapaCCAA(
    document.getElementById("chart-mapa-ccaa"),
    estado.ccaaMetrica,
    AGREGACION_TERRITORIO,
    estado.periodo,
    estado.ccaaFiltro,
    alClicarCCAA
  );

  const chip = document.getElementById("filtro-ccaa-chip");
  if (estado.ccaaFiltro) {
    chip.style.display = "inline-flex";
    chip.innerHTML = `Filtrado: ${estado.ccaaFiltro} <button type="button" aria-label="Quitar filtro">✕</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      estado.ccaaFiltro = null;
      renderResumenTerritorio();
    });
  } else {
    chip.style.display = "none";
  }

  const filasPorMetrica = Object.fromEntries(
    CCAA_METRICAS.map(({ id }) => [id, Resumen.filasPorCCAA(id, AGREGACION_TERRITORIO, estado.periodo)])
  );
  let nombresCCAA = filasPorMetrica[estado.ccaaMetrica].map((f) => f.ccaa);
  if (estado.ccaaFiltro) nombresCCAA = nombresCCAA.filter((c) => c === estado.ccaaFiltro);

  let filas = nombresCCAA.map((ccaa) => {
    const fila = { ccaa };
    for (const { id } of CCAA_METRICAS) {
      const encontrada = filasPorMetrica[id].find((f) => f.ccaa === ccaa);
      fila[id] = encontrada ? encontrada.valor : null;
      fila[`${id}_var`] = encontrada ? encontrada.var_pct_interanual : null;
    }
    return fila;
  });

  const { columna, asc } = estado.ordenTerritorio;
  filas.sort((a, b) => {
    const va = columna === "ccaa" ? a.ccaa : a[columna] ?? -Infinity;
    const vb = columna === "ccaa" ? b.ccaa : b[columna] ?? -Infinity;
    if (typeof va === "string") return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    return asc ? va - vb : vb - va;
  });

  const columnaActiva = CCAA_METRICAS.find((c) => c.id === estado.ccaaMetrica);
  const thead = document.getElementById("territorio-thead");
  const columnas = [{ id: "ccaa", etiqueta: "Comunidad autónoma" }, columnaActiva];
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
      renderResumenTerritorio();
    });
  });

  const tbody = document.getElementById("territorio-tbody");
  if (filas.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${columnas.length}" class="empty-state">Sin datos por CCAA para este periodo.</td></tr>`;
    document.getElementById("territorio-tfoot").innerHTML = "";
    return;
  }
  tbody.innerHTML = filas
    .map(
      (f) => `
      <tr>
        <td>${f.ccaa}</td>
        <td>${formatoNumero(f[estado.ccaaMetrica])} GWh
          ${f[`${estado.ccaaMetrica}_var`] !== null ? `<br/><span class="kpi-delta ${claseVariacion(f[`${estado.ccaaMetrica}_var`])}" style="font-size:.72rem">${formatoPct(f[`${estado.ccaaMetrica}_var`])}</span>` : ""}
        </td>
      </tr>`
    )
    .join("");

  const total = filas.reduce((acc, f) => acc + (f[estado.ccaaMetrica] ?? 0), 0);
  document.getElementById("territorio-tfoot").innerHTML = `
    <tr class="fila-total"><td>Total</td><td>${formatoNumero(total)} GWh</td></tr>
  `;
}

// ---------- Vista: Aprovisionamiento ----------

function renderAprovisionamiento() {
  const cont = document.getElementById("aprovisionamiento-cards");
  const { gn, gnl, total } = Aprovisionamiento.totalesGnGnl(estado.agregacion, estado.periodo);
  const periodoPrevio = periodoAnterior(estado.periodo);
  const previos = periodoPrevio
    ? Aprovisionamiento.totalesGnGnl(estado.agregacion, periodoPrevio)
    : { gn: null, gnl: null, total: null };
  const anioAnterior = Aprovisionamiento.totalesGnGnlAnioAnterior(estado.agregacion, estado.periodo);

  const tarjetas = [
    { etiqueta: "Aprovisionamiento total", valor: total, anterior: variacionPropia(total, previos.total), ly: variacionPropia(total, anioAnterior.total) },
    { etiqueta: "Total GN", valor: gn, anterior: variacionPropia(gn, previos.gn), ly: variacionPropia(gn, anioAnterior.gn) },
    { etiqueta: "Total GNL", valor: gnl, anterior: variacionPropia(gnl, previos.gnl), ly: variacionPropia(gnl, anioAnterior.gnl) },
  ];

  cont.innerHTML = tarjetas
    .map(
      (t) => `
    <div class="card kpi-card">
      <div class="kpi-label">${t.etiqueta}</div>
      <div class="kpi-value">${formatoNumero(t.valor)} <span class="kpi-unit">GWh</span></div>
      <div class="kpi-deltas">
        <span class="kpi-delta-row"><span class="kpi-delta-tag">Periodo anterior</span><span class="kpi-delta ${claseVariacion(t.anterior)}">${formatoPct(t.anterior)}</span></span>
        <span class="kpi-delta-row"><span class="kpi-delta-tag">Interanual</span><span class="kpi-delta ${claseVariacion(t.ly)}">${formatoPct(t.ly)}</span></span>
      </div>
    </div>`
    )
    .join("");

  renderPaisesYEvolucion();
}

function renderPaisesYEvolucion() {
  Aprovisionamiento.pintarPaisesPie(document.getElementById("chart-paises-pie"), estado.tipoGas, estado.agregacion, estado.periodo);
  renderTablaPaises();

  const anio = estado.periodo.split("-")[0];
  document.getElementById("titulo-evolucion").textContent = `Evolución a lo largo del año (${anio})`;
  Aprovisionamiento.pintarEvolucion(document.getElementById("chart-evolucion-gn-gnl"), estado.tipoGas, estado.agregacion, anio);
}

function renderTablaPaises() {
  const tbody = document.getElementById("paises-tbody");
  const lista = Aprovisionamiento.paisesDelPeriodo(estado.tipoGas, estado.agregacion, estado.periodo);
  if (lista.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Sin datos de países para este periodo.</td></tr>`;
    return;
  }
  tbody.innerHTML = lista
    .map(
      (p) => `
    <tr>
      <td style="text-align:left">${p.pais}</td>
      <td>${formatoNumero(p.valor)}</td>
      <td class="${claseVariacion(p.varAnterior)}">${formatoPct(p.varAnterior)}</td>
      <td class="${claseVariacion(p.varInteranual)}">${formatoPct(p.varInteranual)}</td>
    </tr>`
    )
    .join("");
}

// ---------- Vista: Infraestructuras ----------

// Igual que el desglose por CCAA: ni las plantas de regasificación ni
// el TVB traen columna de acumulado/TAM en el Boletín, solo mensual.
// Los saldos por conexión sí (ver AGREGACIONES / estado.agregacion).
const AGREGACION_INFRAESTRUCTURAS = "mes";

function alClicarPlanta(planta) {
  estado.plantaFiltro = estado.plantaFiltro === planta ? null : planta;
  renderInfraestructuras();
}

function renderInfraestructuras() {
  document.getElementById("aviso-agregacion-infraestructuras").style.display =
    estado.agregacion === AGREGACION_INFRAESTRUCTURAS ? "none" : "block";

  Infraestructuras.pintarMapaPlantas(
    document.getElementById("chart-mapa-plantas"),
    AGREGACION_INFRAESTRUCTURAS,
    estado.periodo,
    estado.plantaFiltro,
    alClicarPlanta
  );
  Infraestructuras.pintarPlantas(document.getElementById("chart-plantas"), AGREGACION_INFRAESTRUCTURAS, estado.periodo, estado.plantaFiltro);
  Infraestructuras.pintarTvb(document.getElementById("chart-tvb"), AGREGACION_INFRAESTRUCTURAS, estado.periodo);
  Infraestructuras.pintarSaldosConexion(document.getElementById("chart-saldos"), estado.agregacion, estado.periodo);

  const chip = document.getElementById("filtro-planta-chip");
  if (estado.plantaFiltro) {
    chip.style.display = "inline-flex";
    chip.innerHTML = `Filtrado: ${estado.plantaFiltro} <button type="button" aria-label="Quitar filtro">✕</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      estado.plantaFiltro = null;
      renderInfraestructuras();
    });
  } else {
    chip.style.display = "none";
  }

  const { total, contratada, disponible, comercial, pctContratada, pctUsoComercial } = Infraestructuras.datosTvbResumen(
    AGREGACION_INFRAESTRUCTURAS,
    estado.periodo
  );
  const tarjetas = [
    { etiqueta: "Capacidad total", valor: total, unidad: "GWh/mes" },
    { etiqueta: "Capacidad contratada", valor: contratada, unidad: "GWh/mes", pct: pctContratada, pctEtiqueta: "% de la capacidad total" },
    { etiqueta: "Capacidad disponible", valor: disponible, unidad: "GWh/mes" },
    { etiqueta: "Regasificación comercial (mes)", valor: comercial, unidad: "GWh", pct: pctUsoComercial, pctEtiqueta: "% de la capacidad total usada" },
  ];
  document.getElementById("tvb-cards").innerHTML = tarjetas
    .map(
      (t) => `
    <div class="card kpi-card">
      <div class="kpi-label">${t.etiqueta}</div>
      <div class="kpi-value">${formatoNumero(t.valor)} <span class="kpi-unit">${t.unidad}</span></div>
      ${
        t.pct !== undefined
          ? `<div class="kpi-deltas"><span class="kpi-delta-row"><span class="kpi-delta-tag">${t.pctEtiqueta}</span><span class="kpi-delta neutral">${formatoNumero(t.pct, 1)}%</span></span></div>`
          : ""
      }
    </div>`
    )
    .join("");
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
