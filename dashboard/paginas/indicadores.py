"""Indicadores: ¿el nuevo proceso cumple las metas? Se lee de arriba abajo.

1. Los 5 KPI del periodo con semáforo
2. Evolución diaria de un KPI contra su meta
3. QR contra caja y espera por franja
4. Productos más pedidos y reclamos por tipo
5. Demanda esperada para preparar el próximo día
"""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Indicadores", "¿El nuevo proceso de pedidos cumple las metas? Elige el periodo y la cafetería.")
f = ui.filtros()
df = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])

if df.empty:
    ui.sin_datos("Todavía no hay pedidos en este periodo. Cuando la cafetería empiece a recibir pedidos, "
                 "aquí verás los indicadores. Prueba también con un periodo más largo.")
    ui.pie_de_pagina()
    st.stop()

linea = dict(color=tema.TINTA_2, width=1.5, dash="dash")
orden_fr = datos.catalogos()["franjas"].nombre.tolist()

# --- 1. Los 5 KPI ---------------------------------------------------------------
k = datos.calcular_kpis(df)
ui.subtitulo("¿Cumplimos las metas?", "Promedio del periodo elegido, comparado con la meta y la línea base.")
ui.fila_kpis(k)
ui.fila_datos([
    ui.tarjeta_dato("Clientes que llegaron", ui.miles(k["llegados"]), "incluye los que se fueron de la fila"),
    ui.tarjeta_dato("Pedidos entregados", ui.miles(k["entregados"]), ""),
    ui.tarjeta_dato("Ventas", ui.pesos(k["ventas"]), "pedidos pagados"),
    ui.tarjeta_dato("Pedidos por QR", f"{(df.canal == 'QR').mean() * 100:.0f} %", "del total de clientes"),
])
if df.id_cafeteria.nunique() > 1:
    with st.expander("Ver los indicadores por cafetería"):
        filas = [{"Cafetería": nombre, **{tema.KPIS[c]["nombre"]: kk[c] for c in tema.KPIS}}
                 for nombre, g in df.groupby("cafeteria") for kk in [datos.calcular_kpis(g)]]
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

# --- 2. Evolución diaria ---------------------------------------------------------
ui.subtitulo("Evolución día a día", "Elige un indicador. La línea punteada es la meta; el día de hoy no se incluye "
                                    "porque aún no termina.")
nombres = {tema.KPIS[c]["nombre"]: c for c in tema.KPIS}
elegido = st.segmented_control("Indicador", list(nombres), default=list(nombres)[0], key="kpi_tend",
                               label_visibility="collapsed") or list(nombres)[0]
clave = nombres[elegido]
info = tema.KPIS[clave]
diario = datos.kpis_por_dia(df[df.fecha < date.today()])
diario = diario[["fecha", clave]].dropna() if not diario.empty else diario

if len(diario) < 2:
    ui.sin_datos("Se necesitan al menos dos días completos con datos para ver la evolución. "
                 "Elige un periodo más largo o vuelve en unos días.")
else:
    fig = go.Figure()
    fig.add_scatter(x=diario.fecha, y=diario[clave], mode="lines+markers", name=info["nombre"],
                    line=dict(color=tema.SERIES[0]),
                    hovertemplate="%{x|%d %b}<br>%{y:.2f} " + info["unidad"] + "<extra></extra>")
    fig.add_hline(y=info["meta"], line=linea, annotation_text=f"Meta {info['meta']:g} {info['unidad']}",
                  annotation_position="top left", annotation_font_color=tema.TINTA_2)
    if info["linea_base"]:
        fig.add_hline(y=info["linea_base"], line=dict(color=tema.TINTA_SUAVE, width=1, dash="dot"),
                      annotation_text=f"Línea base {info['linea_base']:g}", annotation_position="bottom left",
                      annotation_font_color=tema.TINTA_SUAVE)
    fig.update_layout(title=f"{info['nombre']} ({info['unidad']}) por día", showlegend=False, hovermode="x unified")
    fig.update_yaxes(rangemode="tozero", title=None)
    fig.update_xaxes(title=None)
    ui.grafico(fig, diario.rename(columns={clave: f"{info['nombre']} ({info['unidad']})"}), clave="tendencia")
    st.caption(f"Cómo se calcula: {info['formula']}")

# --- 3. QR contra caja y espera por franja ------------------------------------
ui.subtitulo("¿Dónde se pierde tiempo?", "Compara el pedido por QR contra la caja y mira en qué franja se espera más.")
atendidos = df[~df.abandono_fila & df.min_espera_fila.notna()]
entregados = df[df.estado == "Entregado"]
c1, c2 = st.columns(2)
with c1:
    comp = pd.concat([
        atendidos.groupby("canal").min_espera_fila.mean().rename("Espera en fila"),
        entregados.groupby("canal").min_atencion.mean().rename("Atención total"),
    ], axis=1).round(2).reset_index()
    if comp.empty:
        ui.sin_datos("Aún no hay pedidos atendidos para comparar QR y caja.")
    else:
        largo = comp.melt(id_vars="canal", var_name="medida", value_name="minutos").dropna()
        fig = px.bar(largo, x="medida", y="minutos", color="canal", barmode="group", text="minutos",
                     title="QR contra caja (minutos promedio)", color_discrete_map=tema.COLOR_CANAL,
                     category_orders={"canal": ["QR", "Caja"], "medida": ["Espera en fila", "Atención total"]})
        fig.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False,
                          hovertemplate="%{x}<br>%{y:.2f} min<extra>%{fullData.name}</extra>")
        fig.update_layout(legend_title_text="")
        fig.update_xaxes(title=None); fig.update_yaxes(title=None, rangemode="tozero")
        ui.grafico(fig, comp.rename(columns={"canal": "Canal", "Espera en fila": "Espera en fila (min)",
                                             "Atención total": "Atención total (min)"}), clave="qr_caja")
with c2:
    por_fr = (atendidos.groupby("franja").min_espera_fila.mean().round(2)
              .reindex([x for x in orden_fr if x in set(atendidos.franja)]).reset_index())
    por_fr.columns = ["franja", "espera (min)"]
    if por_fr.empty:
        ui.sin_datos("Aún no hay esperas registradas por franja.")
    else:
        fig = px.bar(por_fr, x="franja", y="espera (min)", title="Espera en fila por franja (minutos promedio)",
                     text="espera (min)", color_discrete_sequence=[tema.SERIES[0]])
        fig.add_hline(y=tema.KPIS["kpi4"]["meta"], line=linea, annotation_text=f"Meta {tema.KPIS['kpi4']['meta']:g} min",
                      annotation_position="top left", annotation_font_color=tema.TINTA_2)
        fig.update_traces(texttemplate="%{y:.1f}", textposition="inside", insidetextanchor="end",
                          textfont_color="white", hovertemplate="%{x}<br>%{y:.2f} min<extra></extra>")
        fig.update_xaxes(title=None); fig.update_yaxes(title=None, rangemode="tozero")
        ui.grafico(fig, por_fr, clave="espera_franja")

# --- 4. Productos y reclamos ----------------------------------------------------
ui.subtitulo("Lo que más se pide y de qué se quejan", "")
c3, c4 = st.columns(2)
with c3:
    det = datos.detalle(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])
    if det.empty:
        ui.sin_datos("Aún no hay productos vendidos en este periodo.")
    else:
        top = (det.groupby("producto").agg(unidades=("cantidad", "sum"), ventas=("subtotal", "sum"))
               .reset_index().sort_values("unidades", ascending=False).head(10))
        top["ventas"] = top.ventas.astype(float)
        fig = px.bar(top, x="unidades", y="producto", orientation="h", text="unidades",
                     title="Los 10 productos más pedidos (unidades)", color_discrete_sequence=[tema.SERIES[0]])
        fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
        fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} unidades<extra></extra>")
        ui.grafico(fig, top, alto=400, clave="productos")
with c4:
    rec = datos.reclamos(f["desde"], f["hasta"], f["cafeterias"])
    if rec.empty:
        st.success("No hubo reclamos en este periodo.", icon="✅")
    else:
        t = rec.tipo_reclamo.value_counts().reset_index()
        t.columns = ["tipo", "reclamos"]
        abiertos = int((rec.estado == "Abierto").sum())
        fig = px.bar(t, x="reclamos", y="tipo", orientation="h", text="reclamos",
                     title=f"Reclamos por tipo ({len(rec)} en total, {abiertos} sin resolver)",
                     color_discrete_sequence=[tema.SERIES[0]])
        fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
        fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x}<extra></extra>")
        detalle = rec.rename(columns={"fecha_hora": "Fecha y hora", "cafeteria": "Cafetería", "id_pedido": "Pedido",
                                      "tipo_reclamo": "Tipo", "descripcion": "Descripción", "estado": "Estado"})
        ui.grafico(fig, detalle, alto=400, clave="reclamos")

# --- 5. Demanda esperada ---------------------------------------------------------
# Modelo simple y explicable: promedio de unidades vendidas el mismo día de la semana en las
# últimas 4 semanas (si no hay, los últimos 5 días con datos). Solo usa totales agregados:
# no mira el historial de ninguna persona ni cambia el orden de la cola (FIFO).
ui.subtitulo("Demanda esperada", "Qué conviene dejar adelantado antes del cambio de clase y del almuerzo.")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
hist = datos.detalle(date(2000, 1, 1), date.today() - timedelta(days=1), f["cafeterias"],
                     tuple(int(i) for i in datos.catalogos()["franjas"].id_franja))
pico = datos.catalogos()["franjas"].query("es_hora_pico").nombre.tolist()
if hist.empty:
    ui.sin_datos("Para estimar la demanda se necesita al menos un día completo de pedidos.")
else:
    hist["fecha"] = pd.to_datetime(hist.fecha)
    manana = date.today() + timedelta(days=1)
    if manana.weekday() == 6:
        manana += timedelta(days=1)
    objetivo = st.date_input("Día a preparar", manana, key="dem_dia", format="DD/MM/YYYY")
    dia_sem = objetivo.weekday()
    diario_p = hist.groupby(["fecha", "franja", "producto"]).cantidad.sum().reset_index()
    mismo_dia = diario_p[diario_p.fecha.dt.weekday == dia_sem]
    fechas = sorted(mismo_dia.fecha.unique())[-4:]
    base = mismo_dia[mismo_dia.fecha.isin(fechas)]
    metodo = f"promedio de los últimos {len(fechas)} {DIAS[dia_sem]}"
    if base.empty:
        fechas = sorted(diario_p.fecha.unique())[-5:]
        base = diario_p[diario_p.fecha.isin(fechas)]
        metodo = f"promedio de los últimos {len(fechas)} días con datos"
    n = max(len(fechas), 1)
    pron = (base.pivot_table(index=["franja", "producto"], columns="fecha", values="cantidad", aggfunc="sum",
                             fill_value=0).sum(axis=1).div(n).round(1).reset_index(name="unidades esperadas"))
    pron_pico = pron[pron.franja.isin(pico) & (pron["unidades esperadas"] > 0)]

    st.markdown(f"<div class='nota-etica'>Estimación para el <b>{DIAS[dia_sem]} {objetivo:%d/%m/%Y}</b> · {metodo}. "
                "Solo usa totales por franja y producto: no usa datos personales ni prioriza a ningún cliente. "
                "La decisión final es del coordinador.</div>", unsafe_allow_html=True)
    st.write("")
    if pron_pico.empty:
        ui.sin_datos("No hay ventas en horas pico para estimar la demanda.")
    else:
        top = pron_pico.groupby("producto")["unidades esperadas"].sum().sort_values(ascending=False).head(10).index
        mapa = (pron_pico[pron_pico.producto.isin(top)]
                .pivot_table(index="producto", columns="franja", values="unidades esperadas", fill_value=0)
                .reindex(top)[[c for c in pico if c in set(pron_pico.franja)]])
        fig = px.imshow(mapa, text_auto=".0f", aspect="auto", color_continuous_scale=tema.SECUENCIAL,
                        title="Unidades esperadas por producto en cada hora pico")
        fig.update_layout(coloraxis_colorbar=dict(title="unid."))
        fig.update_xaxes(title=None, side="top"); fig.update_yaxes(title=None)
        fig.update_traces(hovertemplate="%{y} · %{x}<br>%{z:.1f} unidades<extra></extra>")
        lista = pron_pico.sort_values(["franja", "unidades esperadas"], ascending=[True, False]).copy()
        lista["unidades a preparar (+10 %)"] = (lista["unidades esperadas"] * 1.1).round().astype(int)
        ui.grafico(fig, lista, alto=420, clave="mapa_demanda")
        st.download_button("Descargar lista de preparación (CSV)", lista.to_csv(index=False).encode("utf-8"),
                           file_name=f"preparacion_{objetivo:%Y%m%d}.csv", mime="text/csv")

ui.pie_de_pagina()
