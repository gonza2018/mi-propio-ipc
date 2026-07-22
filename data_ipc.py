"""
data_ipc.py

Carga y normaliza los dos archivos oficiales del INDEC que alimentan
"Mi Propio IPC" (versión Santiago del Estero / región Noroeste):

  1. serie_ipc_divisiones.csv
     -> Nivel general por región (incluye "Noroeste" y "Nacional").
        Se usa para las dos líneas de referencia del gráfico: IPC Noroeste
        e IPC Nacional.

  2. sh_ipc_aperturas.xls (hoja "Variación mensual aperturas")
     -> Variación mensual (%) de cada apertura/rubro, desagregada por
        región. Se usa para calcular "Tu IPC" aplicando los pesos que
        carga el usuario sobre estos valores históricos reales.

Ambos archivos vienen en formato "ancho" (una columna por mes) y con
bloques por región dentro de la misma hoja/csv, así que las funciones acá
los convierten a formato "tidy" (una fila por período).

No requiere conexión a internet: por defecto lee los archivos locales de
la carpeta data/. (Para automatizar la descarga en el futuro, alcanza con
reemplazar la lectura de archivo por un requests.get a la URL del INDEC y
guardar el contenido antes de llamar a estas mismas funciones de parseo.)
"""

from __future__ import annotations

import difflib
import io
import re
import unicodedata

import pandas as pd
import requests

REGION = "Noroeste"  # fija: esta app es para Santiago del Estero (región NOA)
REGION_NACIONAL = "Nacional"

URL_DIVISIONES = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv"
URL_APERTURAS = "https://www.indec.gob.ar/ftp/cuadros/economia/sh_ipc_aperturas.xls"


def _descargar(url: str, timeout: int = 8) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _resolver_fuente(path_local: str, url: str) -> tuple[object, str]:
    """Intenta traer el archivo de internet primero; si no hay conexión (o
    falla la descarga), usa el archivo local de data/. Devuelve (fuente,
    origen) donde origen es 'remoto' o 'local', y fuente es algo que
    pandas puede leer directo (BytesIO o path)."""
    contenido = _descargar(url)
    if contenido is not None:
        return io.BytesIO(contenido), "remoto"
    return path_local, "local"

# ---------------------------------------------------------------------------
# Árbol de categorías (aperturas del IPC) tal como se muestra en el formulario
# ---------------------------------------------------------------------------
# `apertura`: etiqueta a buscar (por similitud) en la hoja "Variación mensual
# aperturas" del xls, dentro del bloque de la región `REGION`.
# `aprox=True`: no existe una fila propia para ese rubro en el archivo del
# INDEC (INDEC no publica ese nivel de detalle); se usa como aproximación la
# variación de la división completa a la que pertenece.
CATEGORIES = [
    {
        "id": "alimentos",
        "label": "Alimentos y bebidas no alcohólicas",
        "apertura": "Alimentos y bebidas no alcohólicas",
        "children": [
            {"id": "carnes", "label": "Carnes y derivados", "apertura": "Carnes y derivados"},
            {"id": "frutas", "label": "Frutas", "apertura": "Frutas"},
            {"id": "verduras", "label": "Verduras, tubérculos y legumbres", "apertura": "Verduras, tubérculos y legumbres"},
            {"id": "resto_alimentos", "label": "Resto de alimentos y bebidas n.a.p.",
             "apertura": "Alimentos y bebidas no alcohólicas", "aprox": True},
        ],
    },
    {"id": "bebidas_alcoholicas", "label": "Bebidas alcohólicas y tabaco",
     "apertura": "Bebidas alcohólicas y tabaco", "children": []},
    {"id": "indumentaria", "label": "Prendas de vestir y calzado",
     "apertura": "Prendas de vestir y calzado", "children": []},
    {
        "id": "vivienda",
        "label": "Vivienda, agua, electricidad, gas y otros combustibles",
        "apertura": "Vivienda, agua, electricidad, gas y otros combustibles",
        "children": [
            {"id": "alquiler", "label": "Alquiler de la vivienda y gastos conexos",
             "apertura": "Alquiler de la vivienda y gastos conexos"},
            {"id": "electricidad_gas", "label": "Electricidad, gas y otros combustibles",
             "apertura": "Electricidad, gas y otros combustibles"},
        ],
    },
    {"id": "equipamiento_hogar", "label": "Equipamiento y mantenimiento del hogar",
     "apertura": "Equipamiento y mantenimiento del hogar", "children": []},
    {
        "id": "salud",
        "label": "Salud",
        "apertura": "Salud",
        "children": [
            {"id": "medicamentos", "label": "Productos medicinales, artefactos y equipos para la salud",
             "apertura": "Productos medicinales, artefactos y equipos para la salud"},
            {"id": "prepaga", "label": "Gastos de prepaga", "apertura": "Gastos de prepagas"},
        ],
    },
    {
        "id": "transporte",
        "label": "Transporte",
        "apertura": "Transporte",
        "children": [
            {"id": "combustibles", "label": "Combustibles y lubricantes para vehículos de uso del hogar",
             "apertura": "Combustibles y lubricantes para vehículos de uso del hogar"},
            {"id": "transporte_publico", "label": "Transporte público", "apertura": "Transporte público"},
        ],
    },
    {"id": "comunicacion", "label": "Servicios de telefonía e internet",
     "apertura": "Servicios de telefonía e internet", "children": []},
    {"id": "recreacion", "label": "Recreación y cultura",
     "apertura": "Recreación y cultura", "children": []},
    {"id": "educacion", "label": "Educación", "apertura": "Educación", "children": []},
    {"id": "restaurantes", "label": "Restaurantes y comidas fuera del hogar",
     "apertura": "Restaurantes y comidas fuera del hogar", "children": []},
    {"id": "cuidado_personal", "label": "Cuidado personal",
     "apertura": "Cuidado personal", "children": []},
]


def flatten_leaves() -> list[dict]:
    """Categorías 'hoja' (las que llevan input de $ en el formulario)."""
    leaves = []
    for cat in CATEGORIES:
        if cat["children"]:
            for ch in cat["children"]:
                leaves.append({**ch, "parent": cat["id"]})
        else:
            leaves.append({**cat, "parent": None})
    return leaves


LEAVES = flatten_leaves()
LEAF_IDS = [l["id"] for l in LEAVES]


# ---------------------------------------------------------------------------
# Normalización de texto y matching por similitud
# (mismo espíritu que el normalizar_texto()/fuzzy-match ya usado en el
# proyecto de la base maestra, para no introducir un criterio nuevo)
# ---------------------------------------------------------------------------

def normalizar(texto) -> str:
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFKD", str(texto).strip().lower())
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _mejor_match(etiqueta_objetivo: str, etiquetas_disponibles: list[str], umbral: float = 0.75) -> str | None:
    norm_obj = normalizar(etiqueta_objetivo)
    disponibles_norm = {normalizar(e): e for e in etiquetas_disponibles}
    if norm_obj in disponibles_norm:
        return disponibles_norm[norm_obj]
    candidatos = difflib.get_close_matches(norm_obj, list(disponibles_norm.keys()), n=1, cutoff=umbral)
    return disponibles_norm[candidatos[0]] if candidatos else None


def _a_float(val) -> float | None:
    if isinstance(val, (int, float)):
        return None if pd.isna(val) else float(val)
    if isinstance(val, str):
        v = val.strip().replace(",", ".")
        try:
            return float(v)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# 1) serie_ipc_divisiones.csv -> nivel general por región
# ---------------------------------------------------------------------------

def cargar_nivel_general_divisiones(path_csv: str) -> pd.DataFrame:
    """Devuelve DataFrame [periodo, region, v_m_IPC] solo para 'NIVEL GENERAL'
    (Codigo == '0'), que es lo que se necesita para las líneas de referencia
    IPC Noroeste / IPC Nacional."""
    df = pd.read_csv(path_csv, sep=";", encoding="latin1")
    df = df[df["Codigo"].astype(str).str.strip() == "0"].copy()
    df["periodo"] = pd.to_datetime(df["Periodo"].astype(str), format="%Y%m")
    df["v_m_IPC"] = df["v_m_IPC"].apply(_a_float)
    df["region"] = df["Region"].astype(str).str.strip()
    return df[["periodo", "region", "v_m_IPC"]].dropna(subset=["v_m_IPC"]).sort_values("periodo")


# ---------------------------------------------------------------------------
# 2) sh_ipc_aperturas.xls -> variación mensual por apertura y región
# ---------------------------------------------------------------------------

def cargar_variacion_mensual_aperturas(path_xls: str,
                                        sheet_name: str = "Variación mensual aperturas") -> pd.DataFrame:
    """Devuelve DataFrame tidy [region, apertura, periodo, valor] a partir
    del formato "ancho con bloques por región" del archivo del INDEC."""
    raw = pd.read_excel(path_xls, sheet_name=sheet_name, header=None)
    col0 = raw[0].astype(str)
    bloques = raw.index[col0.str.match(r"^Regi[oó]n\s", na=False)].tolist()
    bloques.append(len(raw))

    filas = []
    for i in range(len(bloques) - 1):
        inicio, fin = bloques[i], bloques[i + 1]
        region_nombre = re.sub(r"^Regi[oó]n\s+", "", str(raw.iloc[inicio, 0])).strip()
        fechas = pd.to_datetime(raw.iloc[inicio, 1:], errors="coerce")
        fechas = fechas.dt.to_period("M").dt.to_timestamp()

        for fila_idx in range(inicio + 1, fin):
            etiqueta = raw.iloc[fila_idx, 0]
            if pd.isna(etiqueta):
                continue
            etiqueta = str(etiqueta).strip()
            valores = raw.iloc[fila_idx, 1:]
            for periodo, val in zip(fechas, valores):
                if pd.isna(periodo):
                    continue
                v = _a_float(val)
                if v is None:
                    continue
                filas.append({"region": region_nombre, "apertura": etiqueta, "periodo": periodo, "valor": v})

    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Motor de cálculo
# ---------------------------------------------------------------------------

class DatosIPC:
    """Envuelve los dos datasets ya cargados y ofrece los métodos de cálculo
    que usa la app."""

    def __init__(self, path_csv: str, path_xls: str):
        fuente_csv, origen_csv = _resolver_fuente(path_csv, URL_DIVISIONES)
        fuente_xls, origen_xls = _resolver_fuente(path_xls, URL_APERTURAS)
        self.origenes = {"divisiones": origen_csv, "aperturas": origen_xls}

        self.nivel_general = cargar_nivel_general_divisiones(fuente_csv)
        self.variacion_aperturas = cargar_variacion_mensual_aperturas(fuente_xls)
        self._pivot_region = self.variacion_aperturas[
            self.variacion_aperturas["region"] == REGION
        ].pivot_table(index="periodo", columns="apertura", values="valor")

        # resuelve, una sola vez, a qué columna real del pivot corresponde
        # cada apertura pedida por el árbol de categorías (por similitud)
        etiquetas_reales = list(self._pivot_region.columns)
        self._resolucion = {}
        for leaf in LEAVES:
            match = _mejor_match(leaf["apertura"], etiquetas_reales)
            self._resolucion[leaf["id"]] = match

    def aperturas_sin_match(self) -> list[str]:
        return [leaf["label"] for leaf in LEAVES if self._resolucion.get(leaf["id"]) is None]

    def ultimo_periodo(self) -> pd.Timestamp:
        return self._pivot_region.index.max()

    def serie_referencia(self, region: str) -> pd.Series:
        s = self.nivel_general[self.nivel_general["region"] == region].set_index("periodo")["v_m_IPC"]
        return s.sort_index()

    def serie_personal(self, gastos: dict[str, float]) -> pd.Series | None:
        """gastos: {leaf_id: monto en pesos}. Devuelve la serie mensual (%)
        de 'Tu IPC' aplicando esos pesos (normalizados) sobre la variación
        histórica real de cada apertura, período a período. Si en algún mes
        falta el dato de alguna apertura, se renormaliza entre las que sí
        tienen dato ese mes (para no perder el mes entero)."""
        total = sum(v for v in gastos.values() if v and v > 0)
        if total <= 0:
            return None

        pesos = {leaf_id: v / total for leaf_id, v in gastos.items() if v and v > 0}
        columnas = {leaf_id: self._resolucion.get(leaf_id) for leaf_id in pesos}
        columnas = {k: v for k, v in columnas.items() if v is not None}
        if not columnas:
            return None

        sub = self._pivot_region[list(set(columnas.values()))]

        resultado = {}
        for periodo, fila in sub.iterrows():
            disponibles = {leaf_id: col for leaf_id, col in columnas.items() if pd.notna(fila[col])}
            if not disponibles:
                continue
            peso_total_disp = sum(pesos[l] for l in disponibles)
            valor = sum(pesos[l] / peso_total_disp * fila[col] for l, col in disponibles.items())
            resultado[periodo] = valor

        return pd.Series(resultado).sort_index()


def encadenar_variacion(serie: pd.Series, inicio, fin) -> float | None:
    """Encadena variaciones mensuales (%) entre `inicio` y `fin` (inclusive)."""
    ventana = serie[(serie.index >= inicio) & (serie.index <= fin)].sort_index()
    if ventana.empty:
        return None
    factor = (1 + ventana / 100).prod()
    return round((factor - 1) * 100, 2)


def resumen(serie_personal: pd.Series, periodo_seleccionado: pd.Timestamp) -> dict:
    if serie_personal is None or periodo_seleccionado not in serie_personal.index:
        return {"mensual": None, "acumulado": None, "interanual": None}

    mensual = round(float(serie_personal.loc[periodo_seleccionado]), 2)

    inicio_anio = pd.Timestamp(year=periodo_seleccionado.year, month=1, day=1)
    acumulado = encadenar_variacion(serie_personal, inicio_anio, periodo_seleccionado)

    inicio_12m = periodo_seleccionado - pd.DateOffset(months=11)
    interanual = encadenar_variacion(serie_personal, inicio_12m, periodo_seleccionado)

    return {"mensual": mensual, "acumulado": acumulado, "interanual": interanual}


def marco_comparacion(datos: DatosIPC, serie_personal: pd.Series, meses_ventana: int = 13) -> pd.DataFrame:
    """DataFrame largo [periodo, serie, valor] con las 3 líneas del gráfico,
    recortado a los últimos `meses_ventana` meses disponibles."""
    ref_noroeste = datos.serie_referencia(REGION)
    ref_nacional = datos.serie_referencia(REGION_NACIONAL)

    ultimo = datos.ultimo_periodo()
    inicio_ventana = ultimo - pd.DateOffset(months=meses_ventana - 1)

    frames = []
    if serie_personal is not None:
        s = serie_personal[serie_personal.index >= inicio_ventana]
        frames.append(pd.DataFrame({"periodo": s.index, "serie": "Tu IPC mensual", "valor": s.values}))

    s_noa = ref_noroeste[ref_noroeste.index >= inicio_ventana]
    frames.append(pd.DataFrame({"periodo": s_noa.index, "serie": f"IPC {REGION}", "valor": s_noa.values}))

    s_nac = ref_nacional[ref_nacional.index >= inicio_ventana]
    frames.append(pd.DataFrame({"periodo": s_nac.index, "serie": "IPC Nacional", "valor": s_nac.values}))

    return pd.concat(frames, ignore_index=True).sort_values("periodo")
