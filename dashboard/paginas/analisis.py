"""Dónde se pierde tiempo: por franja, por canal y por producto."""
import pandas as pd
import plotly.express as px
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Franjas, canales y productos",
              "¿Dónde se concentra la espera y qué canal funciona mejor? Compara QR contra caja y las horas pico.")
f = ui.filtros()
df = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])
if df.empty:
    ui.sin_datos()
    st.stop()

orden_fr = datos.catalogos()["franjas"].nombre.tolist()
atendidos = df[~df.abandono_fila]

# Espera por franja y canal: misma unidad (minutos) -> un solo eje
c1, c2 = st.columns(2)
with c1:
    t = (atendidos.groupby(["franja", "canal"]).min_espera_fila.mean().round(2).reset_index()
         .rename(columns={"min_espera_fila": "espera (min)"}))
    fig = px.bar(t, x="franja", y="espera (min)", color="canal", barmode="group",
                 title="Espera en fila por franja y canal (min)", color_discrete_map=tema.COLOR_CANAL,
                 category_orders={"franja": orden_fr, "canal": ["QR", "Caja"]})
    fig.add_hline(y=tema.KPIS["kpi4"]["meta"], line=dict(color=tema.TINTA_2, width=1.5, dash="dash"),
                  annotation_text="Meta 3 min", annotation_position="top left", annotation_font_color=tema.TINTA_2)
    fig.update_traces(hovertemplate="%{x}<br>%{y:.2f} min<extra>%{fullData.name}</extra>")
    fig.update_xaxes(title=None); fig.update_yaxes(title=None)
    ui.grafico(fig, t, clave="espera_franja")
with c2:
    e = df[df.estado == "Entregado"]
    t2 = (e.groupby(["franja", "canal"]).min_atencion.mean().round(2).reset_index()
          .rename(columns={"min_atencion": "atención (min)"}))
    fig = px.bar(t2, x="franja", y="atención (min)", color="canal", barmode="group",
                 title="Tiempo total de atención por franja y canal (min)", color_discrete_map=tema.COLOR_CANAL,
                 category_orders={"franja": orden_fr, "canal": ["QR", "Caja"]})
    fig.add_hline(y=tema.KPIS["kpi1"]["meta"], line=dict(color=tema.TINTA_2, width=1.5, dash="dash"),
                  annotation_text="Meta 5 min", annotation_position="top left", annotation_font_color=tema.TINTA_2)
    fig.update_traces(hovertemplate="%{x}<br>%{y:.2f} min<extra>%{fullData.name}</extra>")
    fig.update_xaxes(title=None); fig.update_yaxes(title=None)
    ui.grafico(fig, t2, clave="atencion_franja")

# Adopción del QR en el tiempo
c3, c4 = st.columns(2)
with c3:
    adop = (df.groupby("fecha").canal.apply(lambda s: round(100 * (s == "QR").mean(), 1))
            .reset_index(name="% pedidos por QR"))
    fig = px.line(adop, x="fecha", y="% pedidos por QR", markers=True, title="Adopción del pedido por QR (%)",
                  color_discrete_sequence=[tema.COLOR_CANAL["QR"]])
    fig.update_yaxes(range=[0, 100], title=None); fig.update_xaxes(title=None)
    fig.update_traces(hovertemplate="%{x|%d %b}: %{y:.1f} %<extra></extra>")
    ui.grafico(fig, adop, clave="adopcion")
with c4:
    tipos = df.tipo_cliente.fillna("Sin identificar (caja)").value_counts().reset_index()
    tipos.columns = ["tipo de cliente", "clientes"]
    fig = px.bar(tipos, x="clientes", y="tipo de cliente", orientation="h", text="clientes",
                 title="Clientes por tipo", color_discrete_sequence=[tema.SERIES[0]])
    fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x}<extra></extra>")
    ui.grafico(fig, tipos, clave="tipos")

# Productos
det = datos.detalle(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])
if not det.empty:
    top = (det.groupby(["producto", "categoria"]).agg(unidades=("cantidad", "sum"), ventas=("subtotal", "sum"))
           .reset_index().sort_values("unidades", ascending=False).head(12))
    top["ventas"] = top.ventas.astype(float)
    fig = px.bar(top, x="unidades", y="producto", orientation="h", text="unidades",
                 title="Productos más pedidos (unidades)", color_discrete_sequence=[tema.SERIES[0]])
    fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} unidades<extra></extra>")
    ui.grafico(fig, top, alto=420, clave="productos")

ui.pie_de_pagina()
