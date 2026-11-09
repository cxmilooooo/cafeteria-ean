"""Resumen de los 5 KPI del proyecto contra sus metas y su línea base."""
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Resumen de KPI",
              "¿El nuevo proceso de pedidos cumple las metas? Los 5 indicadores de la sección 10 del documento.")
f = ui.filtros()
df = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])

if df.empty:
    ui.sin_datos("Aún no hay pedidos. Hagan uno desde la página del QR o carguen los datos de demostración.")
    st.stop()

k = datos.calcular_kpis(df)
ui.fila_kpis(k)
ui.fila_datos([
    ui.tarjeta_dato("Clientes que llegaron", f"{k['llegados']:,}".replace(",", "."), "incluye abandonos"),
    ui.tarjeta_dato("Pedidos entregados", f"{k['entregados']:,}".replace(",", "."), ""),
    ui.tarjeta_dato("Ventas", f"${k['ventas']:,.0f}".replace(",", "."), "pedidos pagados"),
    ui.tarjeta_dato("Pedidos por QR", f"{(df.canal == 'QR').mean() * 100:.0f} %", "del total de clientes"),
])

# --- Tendencia diaria de un KPI contra su meta (una sola serie, una sola escala)
st.markdown("#### Evolución diaria")
nombres = {tema.KPIS[c]["nombre"]: c for c in tema.KPIS}
elegido = st.segmented_control("Indicador", list(nombres), default=list(nombres)[0], key="kpi_tend",
                               label_visibility="collapsed") or list(nombres)[0]
clave = nombres[elegido]
info = tema.KPIS[clave]
# El día en curso está incompleto: se excluye de la tendencia (se ve en "Operación en vivo")
diario = datos.kpis_por_dia(df[df.fecha < date.today()])[["fecha", clave]].dropna()

if diario.empty:
    ui.sin_datos("No hay datos suficientes para este indicador en el periodo.")
else:
    fig = go.Figure()
    fig.add_scatter(x=diario.fecha, y=diario[clave], mode="lines+markers", name=info["nombre"],
                    line=dict(color=tema.SERIES[0]),
                    hovertemplate="%{x|%d %b}<br>%{y:.2f} " + info["unidad"] + "<extra></extra>")
    fig.add_hline(y=info["meta"], line=dict(color=tema.TINTA_2, width=1.5, dash="dash"),
                  annotation_text=f"Meta {info['meta']:g} {info['unidad']}", annotation_position="top left",
                  annotation_font_color=tema.TINTA_2)
    if info["linea_base"]:
        fig.add_hline(y=info["linea_base"], line=dict(color=tema.TINTA_SUAVE, width=1, dash="dot"),
                      annotation_text=f"Línea base {info['linea_base']:g}", annotation_position="bottom left",
                      annotation_font_color=tema.TINTA_SUAVE)
    fig.update_layout(title=f"{info['nombre']} ({info['unidad']}) por día", showlegend=False, hovermode="x unified")
    fig.update_yaxes(rangemode="tozero")
    tabla = diario.rename(columns={clave: f"{info['nombre']} ({info['unidad']})"})
    ui.grafico(fig, tabla, clave="tendencia")
    st.caption(f"Fórmula: {info['formula']} · Fuente: {info['fuente']}")

# --- Demanda por hora del día, con las franjas pico marcadas
c1, c2 = st.columns(2)
with c1:
    por_hora = df.groupby("hora").size().reset_index(name="clientes")
    dias = max(df.fecha.nunique(), 1)
    por_hora["promedio por día"] = (por_hora.clientes / dias).round(1)
    fig = px.bar(por_hora, x="hora", y="promedio por día", title="Clientes por hora (promedio diario)",
                 color_discrete_sequence=[tema.SERIES[0]])
    for fr in datos.catalogos()["franjas"].query("es_hora_pico").itertuples():
        x0 = pd.Timedelta(str(fr.hora_inicio)).total_seconds() / 3600 - 0.5
        x1 = pd.Timedelta(str(fr.hora_fin)).total_seconds() / 3600 - 0.5
        fig.add_vrect(x0=x0, x1=x1, fillcolor=tema.REJILLA, opacity=0.5, line_width=0, layer="below",
                      annotation_text=fr.nombre, annotation_position="top left",
                      annotation_font_color=tema.TINTA_SUAVE, annotation_font_size=11)
    fig.update_xaxes(dtick=1, title="Hora del día")
    fig.update_yaxes(title=None)
    fig.update_traces(hovertemplate="%{x}:00 h<br>%{y} clientes/día<extra></extra>")
    ui.grafico(fig, por_hora, clave="por_hora")

with c2:
    filas = []
    for (cid, nombre), g in df.groupby(["id_cafeteria", "cafeteria"]):
        kk = datos.calcular_kpis(g)
        filas.append({"Cafetería": nombre, **{tema.KPIS[c]["nombre"]: kk[c] for c in tema.KPIS}})
    st.markdown("**KPI por cafetería**")
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.markdown("**Metas del proyecto**")
    st.dataframe(pd.DataFrame([{"KPI": v["nombre"], "Meta": f"{'≤' if v['sentido'] == 'menor' else '≥'} {v['meta']:g} {v['unidad']}",
                                "Línea base": v["linea_base"] if v["linea_base"] else "1.ª semana de registro"}
                               for v in tema.KPIS.values()]), hide_index=True, use_container_width=True)

ui.pie_de_pagina()
