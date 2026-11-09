"""Componentes estándar del dashboard.

Toda página se arma con las mismas piezas, en el mismo orden:

    encabezado(...)  ->  f = filtros()  ->  fila_kpis(...) / grafico(...) / tabla(...)

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


def filtros(incluir_fecha: bool = True) -> dict:
    """Filtros únicos en la barra lateral: fecha, franja horaria y cafetería (RF-13)."""
    cat = datos.catalogos()
    caf, fr, rango = cat["cafeterias"], cat["franjas"], cat["rango"]
    hoy = date.today()
    hasta_dato = rango["hasta"] or hoy
    desde_dato = rango["desde"] or hoy
    with st.sidebar:
        st.markdown("### Filtros")
        if incluir_fecha:
            preset = st.radio("Periodo", ["Hoy", "Últimos 7 días", "Últimos 30 días", "Todo", "Personalizado"],
                              index=3, key="f_periodo")
            if preset == "Hoy":
                desde, hasta = hoy, hoy
            elif preset == "Últimos 7 días":
                desde, hasta = hasta_dato - timedelta(days=6), hasta_dato
            elif preset == "Últimos 30 días":
                desde, hasta = hasta_dato - timedelta(days=29), hasta_dato
            elif preset == "Todo":
                desde, hasta = desde_dato, hasta_dato
            else:
                sel = st.date_input("Rango", (desde_dato, hasta_dato), key="f_rango")
                desde, hasta = (sel[0], sel[-1]) if isinstance(sel, (tuple, list)) and sel else (desde_dato, hasta_dato)
        else:
            desde = hasta = hoy
        nombres_caf = st.multiselect("Cafetería", caf.nombre.tolist(), default=caf.nombre.tolist(), key="f_caf")
        solo_pico = st.toggle("Solo horas pico (RN-05)", value=False, key="f_pico")
        opciones_fr = fr[fr.es_hora_pico] if solo_pico else fr
        nombres_fr = st.multiselect("Franja horaria", opciones_fr.nombre.tolist(),
                                    default=opciones_fr.nombre.tolist(), key=f"f_fr_{solo_pico}")
        st.caption("Datos de la base de la cafetería · se actualizan cada 30 s")
    ids_caf = tuple(int(i) for i in caf[caf.nombre.isin(nombres_caf)].id_cafeteria) or (-1,)
    ids_fr = tuple(int(i) for i in fr[fr.nombre.isin(nombres_fr)].id_franja) or (-1,)
    return {"desde": desde, "hasta": hasta, "cafeterias": ids_caf, "franjas": ids_fr}


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


def sin_datos(mensaje: str = "No hay datos para los filtros elegidos.") -> None:
    st.info(mensaje, icon="ℹ️")


def pie_de_pagina() -> None:
    st.markdown("<div class='pie'>Cafetería EAN · Sistema de gestión de pedidos · Sistemas de Información 2026</div>",
                unsafe_allow_html=True)
