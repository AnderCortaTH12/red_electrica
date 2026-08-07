// Registro compartido del GeoJSON de comunidades autónomas: lo usan
// tanto el mapa de demanda de Resumen como el mapa de plantas de
// Infraestructuras. echarts.registerMap ya es idempotente por nombre,
// pero esto evita además pedir el fichero dos veces.
let registro = null;

// Canarias, Ceuta y Melilla no están en el desglose de Enagás (ver
// NOMBRE_MAPA_CCAA) y quedan geográficamente muy lejos de la
// península: si se dejan en el mapa, echarts encaja la vista para que
// quepan todas, y la península sale diminuta en el centro. Se quitan
// del GeoJSON antes de registrarlo para que el ajuste automático
// aproveche el hueco en península + Baleares, que es lo único con datos.
const REGIONES_EXCLUIDAS = new Set(["Canarias", "Ceuta", "Melilla"]);

export function registrarMapaEspana() {
  if (!registro) {
    registro = fetch("data/spain-ccaa.geojson")
      .then((r) => {
        if (!r.ok) throw new Error(`No se pudo cargar el mapa: HTTP ${r.status}`);
        return r.json();
      })
      .then((geo) => {
        const geoPeninsula = { ...geo, features: geo.features.filter((f) => !REGIONES_EXCLUIDAS.has(f.properties?.name)) };
        echarts.registerMap("espana-ccaa", geoPeninsula);
      });
  }
  return registro;
}

export const NOMBRE_MAPA_CCAA = {
  "Andalucía": "Andalucia",
  "Aragón": "Aragon",
  "Asturias": "Asturias",
  "Baleares": "Baleares",
  "Cantabria": "Cantabria",
  "Castilla y León": "Castilla-Leon",
  "Castilla-La Mancha": "Castilla-La Mancha",
  "Cataluña": "Cataluña",
  "Comunidad Valenciana": "Valencia",
  "Extremadura": "Extremadura",
  "Galicia": "Galicia",
  "La Rioja": "La Rioja",
  "Madrid": "Madrid",
  "Murcia": "Murcia",
  "Navarra": "Navarra",
  "País Vasco": "Pais Vasco",
};

// Del nombre del mapa (sin tildes) al nombre que usa Enagás -- para
// traducir el `name` que devuelve el evento de clic del mapa de vuelta
// a la dimensión real de los datos.
export const NOMBRE_MAPA_CCAA_INVERSO = Object.fromEntries(
  Object.entries(NOMBRE_MAPA_CCAA).map(([enagas, mapa]) => [mapa, enagas])
);

// Coordenadas aproximadas [lon, lat] de las plantas de regasificación
// (no vienen en el PDF -- son de dominio público, ubicación física de
// cada planta). Los nombres son los que usa Enagás como `dimension`.
export const COORDS_PLANTA = {
  BARCELONA: [2.15, 41.35],
  BILBAO: [-3.02, 43.35],
  CARTAGENA: [-0.99, 37.6],
  HUELVA: [-6.95, 37.22],
  MUGARDOS: [-8.28, 43.46],
  MUSEL: [-5.71, 43.57],
  SAGUNTO: [-0.27, 39.68],
};
