"""Componentes estándar del dashboard.

Toda página se arma con las mismas piezas, en el mismo orden:

    encabezado(...)  ->  f = filtros()  ->  contadores(...) / fila_kpis(...) / subtitulo(...) / grafico(...)

Así cualquier integrante puede agregar una página nueva y se verá igual que las demás.
"""
from datetime import date, timedelta
from html import escape

import pandas as pd
import streamlit as st

from . import datos, tema


def encabezado(titulo: str, descripcion: str) -> None:
    st.markdown(f"<div class='enc'><h1>{escape(titulo)}</h1><p>{escape(descripcion)}</p></div>",
                unsafe_allow_html=True)


PERIODOS = ["Hoy", "Últimos 7 días", "Últimos 30 días", "Todo"]
CLAVES_FILTROS = ("f_periodo", "f_caf", "f_pico")  # se conservan al cambiar de página


def filtros(periodo: bool = True, pico: bool = True) -> dict:
    """Filtros únicos, en una fila arriba de la página (RF-13).

    - Periodo: Hoy / Últimos 7 días / Últimos 30 días / Todo
    - Cafetería: solo aparece si hay más de una ("Todas" por defecto)
    - Solo horas pico (RN-05)
    """
    cat = datos.catalogos()
    caf, fr, rango = cat["cafeterias"], cat["franjas"], cat["rango"]
    hoy = date.today()
    varias = len(caf) > 1
    anchos = [3] * periodo + [2] * varias + [1.4] * pico
    cols = iter(st.columns(anchos + [max(0.1, 8 - sum(anchos))], vertical_alignment="bottom")) if anchos else iter(())
    desde = hasta = hoy
    if periodo:
        with next(cols):
            st.session_state.setdefault("f_periodo", "Últimos 30 días")
            elegido = st.segmented_control("Periodo", PERIODOS, key="f_periodo") or "Últimos 30 días"
        if elegido == "Últimos 7 días":
            desde = hoy - timedelta(days=6)
        elif elegido == "Últimos 30 días":
            desde = hoy - timedelta(days=29)
        elif elegido == "Todo":
            desde, hasta = (rango["desde"] or hoy), max(rango["hasta"] or hoy, hoy)
    ids_caf = tuple(int(i) for i in caf.id_cafeteria) or (-1,)
    if varias:
        with next(cols):
            opciones = ["Todas"] + caf.nombre.tolist()
            if st.session_state.get("f_caf") not in opciones:
                st.session_state["f_caf"] = "Todas"
            nombre = st.selectbox("Cafetería", opciones, key="f_caf")
        if nombre != "Todas":
            ids_caf = tuple(int(i) for i in caf[caf.nombre == nombre].id_cafeteria)
    solo_pico = False
    if pico:
        with next(cols):
            solo_pico = st.toggle("Solo horas pico", key="f_pico",
                                  help="Cambio de clase y almuerzo: las franjas donde se mide la meta (RN-05).")
    franjas = fr[fr.es_hora_pico] if solo_pico else fr
    ids_fr = tuple(int(i) for i in franjas.id_franja) or (-1,)
    return {"desde": desde, "hasta": hasta, "cafeterias": ids_caf, "franjas": ids_fr,
            "una_cafeteria": len(ids_caf) == 1}


def recordar_filtros() -> None:
    """Streamlit borra el valor de un filtro cuando se cambia a una página que no lo muestra;
    volver a asignarlo en cada ejecución hace que se conserve entre páginas."""
    for k in CLAVES_FILTROS:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


def contadores(items: list[tuple[str, str, str]]) -> None:
    """Números grandes y simples: [(título, valor, nota), ...]."""
    html = "".join(f"<div class='contador'><div class='contador-nombre'>{escape(t)}</div>"
                   f"<div class='contador-valor'>{escape(v)}</div><div class='contador-nota'>{escape(n)}</div></div>"
                   for t, v, n in items)
    st.markdown(f"<div class='fila-contadores'>{html}</div>", unsafe_allow_html=True)


def subtitulo(texto: str, ayuda: str = "") -> None:
    extra = f"<p>{escape(ayuda)}</p>" if ayuda else ""
    st.markdown(f"<div class='sub'><h3>{escape(texto)}</h3>{extra}</div>", unsafe_allow_html=True)


def pesos(valor: float) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def miles(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _formato(valor, unidad: str) -> str:
    if valor is None:
        return "—"
    if unidad == "%":
        return f"{valor:.1f} %"
    if unidad == "ped/h":
        return f"{valor:.0f}"
    return f"{valor:.1f} {unidad}"


def tarjeta_kpi(clave: str, valor, comparacion=None) -> str:
    k = tema.KPIS[clave]
    est = tema.ESTADO[tema.estado_kpi(clave, valor)]
    signo = "≤" if k["sentido"] == "menor" else "≥"
    meta = f"Meta {signo} {_formato(k['meta'], k['unidad'])}"
    extra = ""
    if comparacion is not None and valor is not None:
        delta = valor - comparacion
        mejora = (delta < 0) if k["sentido"] == "menor" else (delta > 0)
        flecha = "↓" if delta < 0 else "↑"
        extra = (f"<div class='delta {'bueno' if mejora else 'malo'}'>{flecha} {abs(delta):.1f} vs. línea base "
                 f"{_formato(comparacion, k['unidad'])}</div>")
    return f"""<div class='kpi'>
      <div class='kpi-nombre'>{escape(k['nombre'])}</div>
      <div class='kpi-valor'>{_formato(valor, k['unidad'])}</div>
      <div class='kpi-meta'>{meta}</div>
      <div class='kpi-estado' style='color:{est['texto']}'><span style='color:{est['color']}'>{est['icono']}</span> {est['etiqueta']}</div>
      {extra}</div>"""


def fila_kpis(valores: dict, comparar_linea_base: bool = True) -> None:
    html = "".join(tarjeta_kpi(k, valores.get(k), tema.KPIS[k]["linea_base"] if comparar_linea_base else None)
                   for k in tema.KPIS)
    st.markdown(f"<div class='fila-kpi'>{html}</div>", unsafe_allow_html=True)


def tarjeta_dato(titulo: str, valor: str, nota: str = "") -> str:
    return (f"<div class='kpi'><div class='kpi-nombre'>{escape(titulo)}</div>"
            f"<div class='kpi-valor'>{escape(valor)}</div><div class='kpi-meta'>{escape(nota)}</div></div>")


def fila_datos(tarjetas: list) -> None:
    st.markdown(f"<div class='fila-kpi'>{''.join(tarjetas)}</div>", unsafe_allow_html=True)


def grafico(fig, tabla: pd.DataFrame | None = None, alto: int = 340, clave: str | None = None) -> None:
    """Muestra un gráfico con la plantilla y, debajo, su tabla de datos (accesibilidad)."""
    fig.update_layout(height=alto, template="cafeteria")
    # Barras horizontales con etiqueta: dejar aire a la derecha para que el número no se corte
    for tr in fig.data:
        if getattr(tr, "orientation", None) == "h" and tr.type == "bar" and tr.x is not None and len(tr.x):
            fig.update_xaxes(range=[0, max(float(v) for v in tr.x) * 1.15])
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "displayModeBar": False}, key=clave)
    if tabla is not None:
        with st.expander("Ver tabla de datos"):
            st.dataframe(tabla, use_container_width=True, hide_index=True)


def sin_datos(mensaje: str = "No hay datos para este periodo. Prueba con un periodo más largo u otra cafetería.") -> None:
    st.info(mensaje, icon="ℹ️")


def pie_de_pagina() -> None:
    st.markdown("<div class='pie'>Cafetería EAN · Sistema de gestión de pedidos · Sistemas de Información 2026</div>",
                unsafe_allow_html=True)
