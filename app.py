"""
Mi Propio IPC — Santiago del Estero / Región Noroeste (NOA)

Ejecutar con:
    streamlit run app.py

Usa los archivos locales en data/ (no necesita internet):
    - serie_ipc_divisiones.csv
    - sh_ipc_aperturas.xls
"""

import base64
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import data_ipc as d

st.set_page_config(page_title="Mi Propio IPC | DGEyC Santiago del Estero", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Identidad visual (paleta extraída del isologo y la portada institucional
# de la Dirección General de Estadística y Censos de Santiago del Estero /
# estilo de http://www.estadisticasde.gob.ar/)
# ---------------------------------------------------------------------------
ROJO = "#ee3135"
AZUL = "#0097dc"
AZUL_CLARO = "#70b0de"
GRIS_TEXTO = "#2b2b2b"

COLOR_PERSONAL = "#0a3d62"
COLOR_NOROESTE = AZUL_CLARO
COLOR_NACIONAL = ROJO
PALETA_TORTA = [
    "#e8c38f", "#bacc7a", "#d1ae6e", "#a9a9a9",
    AZUL, ROJO, AZUL_CLARO, "#0a3d62",
    "#f2a154", "#7fb069", "#5c9ead", "#c96567",
]

ASSETS = Path(__file__).parent / "assets"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


st.markdown(
    f"""
    <style>
    .franja-ondas {{
        height: 10px; width: 100%; margin: 0.5rem 0 1.5rem 0; border-radius: 4px;
        background: linear-gradient(90deg, {ROJO} 0%, {ROJO} 35%, {AZUL_CLARO} 55%, {AZUL} 100%);
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: #f3ede2;
        border-radius: 12px;
        padding: 0.5rem 0.25rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

logo_path = ASSETS / "logo_dgeyc.png"
if logo_path.exists():
    st.markdown(
        f"<img src='data:image/png;base64,{_b64(logo_path)}' style='height:70px;'>",
        unsafe_allow_html=True,
    )
st.markdown("<div class='franja-ondas'></div>", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Buscando datos actualizados del INDEC…")
def cargar_datos():
    return d.DatosIPC("data/serie_ipc_divisiones.csv", "data/sh_ipc_aperturas.xls")


datos = cargar_datos()

etiqueta_origen = {"remoto": "🟢 datos actualizados desde el INDEC", "local": "🟡 sin conexión: usando datos locales"}
with st.sidebar:
    st.markdown("**Fuente de datos**")
    st.caption(f"serie_ipc_divisiones.csv — {etiqueta_origen[datos.origenes['divisiones']]}")
    st.caption(f"sh_ipc_aperturas.xls — {etiqueta_origen[datos.origenes['aperturas']]}")

    with st.expander("ℹ️ Para más información"):
        st.markdown(
            "El Índice de Precios al Consumidor (IPC) mide la variación promedio de "
            "precios de una canasta representativa de todos los hogares, construida "
            "a partir de una encuesta a miles de familias. Como ningún hogar consume "
            "exactamente esa canasta promedio —varía según los ingresos, si se alquila "
            "o no, la época del año o la región— es esperable que la inflación que "
            "percibe cada familia se aleje del dato nacional. Por eso el INDEC pone a "
            "disposición esta calculadora: permite aproximar la variación de precios "
            "de tu propia canasta, usando los mismos datos de relevamiento que se "
            "usan para construir el IPC oficial."
        )

        def _boton_pdf(nombre_archivo: str, etiqueta: str):
            ruta = ASSETS / nombre_archivo
            if ruta.exists():
                st.download_button(
                    etiqueta, data=ruta.read_bytes(), file_name=nombre_archivo,
                    mime="application/pdf", use_container_width=True,
                )
            else:
                st.caption(f"📄 {etiqueta} _(agregar `{nombre_archivo}` en assets/)_")

        _boton_pdf("ipc_nacional_que_es_06_18.pdf", "¿Qué es el Índice de precios al consumidor?")
        _boton_pdf("como_usar_indice_precios_2022.pdf", "¿Cómo usar un índice de precios? Preguntas frecuentes")

sin_match = datos.aperturas_sin_match()
if sin_match:
    st.sidebar.warning(f"No se encontró dato del INDEC para: {', '.join(sin_match)}")

for leaf in d.LEAVES:
    st.session_state.setdefault(f"gasto_{leaf['id']}", 0.0)
st.session_state.setdefault("show_results", False)

st.title("📊 Mi Propio IPC")
st.caption("Dirección General de Estadística y Censos — Región Noroeste (NOA), Santiago del Estero")
st.markdown(
    "Completá cuánto gastás en cada rubro durante el último mes difundido "
    "para ver cuál hubiera sido la variación de precios de tu propio consumo, "
    "comparada con el IPC oficial de la región Noroeste y con el IPC Nacional."
)

st.divider()

col_form, col_result = st.columns([1, 1.2], gap="large")

with col_form:
  with st.container(border=True):
    st.markdown("##### Selección de aperturas del IPC")
    h1, h2, h3 = st.columns([3, 2, 2])
    h2.markdown("**Gasto en pesos**")
    h3.markdown("**Participación %**")

    total_actual = sum(st.session_state[f"gasto_{lid}"] for lid in d.LEAF_IDS)

    def _row(label: str, leaf_id: str | None, bold: bool = False, value: float | None = None):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            st.markdown(f"**{label}**" if bold else label)
        if leaf_id is not None:
            with c2:
                v = st.number_input(
                    label, key=f"gasto_{leaf_id}", min_value=0.0, step=100.0,
                    format="%.0f", label_visibility="collapsed",
                )
            pct = (v / total_actual * 100) if total_actual > 0 else 0.0
            with c3:
                st.markdown(f"{pct:.2f} %")
        else:
            with c2:
                st.markdown(f"$ {value:,.0f}")
            pct = (value / total_actual * 100) if total_actual > 0 else 0.0
            with c3:
                st.markdown(f"{pct:.2f} %")

    for cat in d.CATEGORIES:
        if cat["children"]:
            parent_total = sum(st.session_state[f"gasto_{ch['id']}"] for ch in cat["children"])
            _row(cat["label"], leaf_id=None, bold=True, value=parent_total)
            for ch in cat["children"]:
                _row(ch["label"], leaf_id=ch["id"])
        else:
            _row(cat["label"], leaf_id=cat["id"], bold=True)

    total_final = sum(st.session_state[f"gasto_{lid}"] for lid in d.LEAF_IDS)
    st.markdown("---")
    ct1, ct2 = st.columns([3, 4])
    ct1.markdown("**Total**")
    ct2.markdown(f"**$ {total_final:,.0f}**")

    if st.button("Calcular tu IPC", type="primary", use_container_width=True):
        st.session_state["show_results"] = True

with col_result:
  with st.container(border=True):
    if not st.session_state["show_results"]:
        st.info("Completá tus gastos por rubro y presioná **Calcular tu IPC** para ver el resultado.")
    else:
        gastos = {lid: st.session_state[f"gasto_{lid}"] for lid in d.LEAF_IDS}
        serie_personal = datos.serie_personal(gastos)

        if serie_personal is None:
            st.warning("Cargá al menos un gasto mayor a 0 para poder calcular tu IPC.")
        else:
            periodo_sel = datos.ultimo_periodo()
            resumen = d.resumen(serie_personal, periodo_sel)
            mes_es = periodo_sel.strftime("%B de %Y").capitalize()

            st.markdown(f"##### En función de tus gastos, calculamos la variación % de tu IPC a {mes_es}")
            st.markdown(
                f"<div style='text-align:center; font-size:1.05rem; line-height:2;'>"
                f"La variación porcentual mensual fue de <b>{resumen['mensual']:.1f}%</b><br>"
                f"La variación porcentual acumulada del año fue de <b>{resumen['acumulado']:.1f}%</b><br>"
                f"La variación porcentual interanual fue de <b>{resumen['interanual']:.1f}%</b>"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.markdown("###### Participación de tu gasto por categoría")
            torta_data = []
            for cat in d.CATEGORIES:
                if cat["children"]:
                    monto = sum(st.session_state[f"gasto_{ch['id']}"] for ch in cat["children"])
                else:
                    monto = st.session_state[f"gasto_{cat['id']}"]
                if monto > 0:
                    torta_data.append({"categoria": cat["label"], "monto": monto})
            torta_df = pd.DataFrame(torta_data)

            torta = (
                alt.Chart(torta_df)
                .mark_arc()
                .encode(
                    theta=alt.Theta("monto:Q", stack=True),
                    color=alt.Color(
                        "categoria:N", title=None,
                        scale=alt.Scale(range=PALETA_TORTA),
                        legend=alt.Legend(orient="bottom", columns=2, labelLimit=260),
                    ),
                    tooltip=["categoria:N", alt.Tooltip("monto:Q", format=",.0f", title="Gasto ($)")],
                )
                .properties(height=320)
            )
            st.altair_chart(torta, use_container_width=True)

            st.markdown(f"###### Variaciones % mensuales de IPC {d.REGION}, IPC Nacional y tu IPC")
            cmp_df = d.marco_comparacion(datos, serie_personal)

            linea = (
                alt.Chart(cmp_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("periodo:T", title=None, axis=alt.Axis(format="%b-%Y")),
                    y=alt.Y("valor:Q", title=None, axis=alt.Axis(format=".1f")),
                    color=alt.Color(
                        "serie:N", title=None,
                        scale=alt.Scale(
                            domain=["Tu IPC mensual", f"IPC {d.REGION}", "IPC Nacional"],
                            range=[COLOR_PERSONAL, COLOR_NOROESTE, COLOR_NACIONAL],
                        ),
                    ),
                    tooltip=["periodo:T", "serie:N", alt.Tooltip("valor:Q", format=".2f")],
                )
                .properties(height=350)
            )
            st.altair_chart(linea, use_container_width=True)

            st.caption(
                "Nota metodológica: la variación acumulada e interanual se calculan "
                "encadenando las variaciones mensuales reales del INDEC de cada apertura, "
                "con tus pesos actuales aplicados también a los meses históricos."
            )

st.markdown("<div class='franja-ondas'></div>", unsafe_allow_html=True)
st.caption("Dirección General de Estadística y Censos — Provincia de Santiago del Estero · Fuente: INDEC")
