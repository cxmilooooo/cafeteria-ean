"""Analítica: demanda esperada por franja y producto para preparar con anticipación.

Modelo deliberadamente simple y explicable: promedio de unidades vendidas en el
mismo día de la semana durante las últimas 4 semanas (si no hay historia, el
promedio de los últimos días con datos). Usa solo datos AGREGADOS: no mira el
historial de ninguna persona ni cambia el orden de la cola (que sigue siendo FIFO).
"""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Demanda esperada",
              "¿Qué conviene dejar adelantado antes del cambio de clase y del almuerzo?")
f = ui.filtros()
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

hist = datos.detalle(date(2000, 1, 1), date.today(), f["cafeterias"], f["franjas"])
if hist.empty:
    ui.sin_datos("Se necesita historia de pedidos para estimar la demanda.")
    st.stop()

hist["fecha"] = pd.to_datetime(hist.fecha)
manana = date.today() + timedelta(days=1)
if manana.weekday() == 6:
    manana += timedelta(days=1)
objetivo = st.date_input("Día a preparar", manana, key="dem_dia")
dia_sem = objetivo.weekday()

diario = hist.groupby(["fecha", "franja", "producto"]).cantidad.sum().reset_index()
mismo_dia = diario[diario.fecha.dt.weekday == dia_sem]
fechas = sorted(mismo_dia.fecha.unique())[-4:]
base = mismo_dia[mismo_dia.fecha.isin(fechas)]
metodo = f"promedio de los últimos {len(fechas)} {DIAS[dia_sem]}"
if base.empty:
    fechas = sorted(diario.fecha.unique())[-5:]
    base = diario[diario.fecha.isin(fechas)]
    metodo = f"promedio de los últimos {len(fechas)} días con datos"
n = max(len(fechas), 1)

# Completar con ceros los días en que un producto no se vendió
pron = (base.pivot_table(index=["franja", "producto"], columns="fecha", values="cantidad", aggfunc="sum", fill_value=0)
        .sum(axis=1).div(n).round(1).reset_index(name="unidades esperadas"))
pico = datos.catalogos()["franjas"].query("es_hora_pico").nombre.tolist()
pron_pico = pron[pron.franja.isin(pico)]

st.markdown(f"<div class='nota-etica'>Estimación para el <b>{DIAS[dia_sem]} {objetivo:%d/%m/%Y}</b> · método: {metodo}. "
            "Solo usa totales por franja y producto: no usa datos personales ni prioriza a ningún cliente "
            "(ver sección de ética y sesgo). La decisión final es del coordinador.</div>", unsafe_allow_html=True)
st.write("")

if pron_pico.empty:
    ui.sin_datos("No hay ventas en franjas pico para estimar.")
else:
    top = (pron_pico.groupby("producto")["unidades esperadas"].sum().sort_values(ascending=False).head(10).index)
    mapa = (pron_pico[pron_pico.producto.isin(top)]
            .pivot_table(index="producto", columns="franja", values="unidades esperadas", fill_value=0)
            .reindex(top)[[c for c in pico if c in pron_pico.franja.unique()]])
    fig = px.imshow(mapa, text_auto=".0f", aspect="auto", color_continuous_scale=tema.SECUENCIAL,
                    title="Unidades esperadas por producto en cada franja pico")
    fig.update_layout(coloraxis_colorbar=dict(title="unid."))
    fig.update_xaxes(title=None, side="top"); fig.update_yaxes(title=None)
    fig.update_traces(hovertemplate="%{y} · %{x}<br>%{z:.1f} unidades<extra></extra>")
    ui.grafico(fig, mapa.reset_index(), alto=440, clave="mapa_demanda")

    st.markdown("**Lista de preparación sugerida (franjas pico)**")
    lista = pron_pico.sort_values(["franja", "unidades esperadas"], ascending=[True, False])
    lista["unidades a preparar (+10 %)"] = (lista["unidades esperadas"] * 1.1).round().astype(int)
    st.dataframe(lista, hide_index=True, use_container_width=True)
    st.download_button("Descargar lista (CSV)", lista.to_csv(index=False).encode("utf-8"),
                       file_name=f"preparacion_{objetivo:%Y%m%d}.csv", mime="text/csv")

ui.pie_de_pagina()
