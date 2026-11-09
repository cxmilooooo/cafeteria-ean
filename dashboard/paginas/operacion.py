"""Operación del día en vivo: estado de la cola y alertas recientes."""
import plotly.express as px
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Operación en vivo",
              "¿Cómo va la cafetería en este momento? Se actualiza sola cada 30 segundos.")
f = ui.filtros(incluir_fecha=False)
ORDEN = ["Registrado", "Pagado", "En preparación", "Listo", "Entregado", "Abandonado"]


@st.fragment(run_every=30)
def tablero():
    datos.pedidos.clear()
    hoy = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])
    if hoy.empty:
        ui.sin_datos("Hoy todavía no hay pedidos.")
        return
    k = datos.calcular_kpis(hoy)
    ui.fila_kpis(k, comparar_linea_base=False)

    activos = hoy[hoy.estado.isin(["Registrado", "Pagado", "En preparación", "Listo"])]
    c1, c2 = st.columns([3, 2])
    with c1:
        conteo = hoy.estado.value_counts().reindex(ORDEN, fill_value=0).reset_index()
        conteo.columns = ["estado", "pedidos"]
        fig = px.bar(conteo, x="pedidos", y="estado", orientation="h", text="pedidos",
                     title="Pedidos de hoy por estado", color_discrete_sequence=[tema.SERIES[0]])
        fig.update_yaxes(categoryorder="array", categoryarray=ORDEN[::-1], title=None)
        fig.update_xaxes(title=None, showgrid=True, gridcolor=tema.REJILLA)
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}: %{x} pedidos<extra></extra>")
        ui.grafico(fig, conteo, alto=300, clave="estados")
    with c2:
        st.markdown(f"**En curso ahora ({len(activos)})**")
        st.dataframe(activos[["numero_turno", "cafeteria", "canal", "estado", "hora_llegada_fila"]]
                     .rename(columns={"numero_turno": "Turno", "cafeteria": "Cafetería", "canal": "Canal",
                                      "estado": "Estado", "hora_llegada_fila": "Llegó"}),
                     hide_index=True, use_container_width=True, height=260)

    alertas = datos.consulta(
        """SELECT a.fecha_hora AS "Hora", coalesce(c.nombre, 'General') AS "Cafetería", a.tipo AS "Tipo",
                  a.mensaje AS "Mensaje"
             FROM alerta a LEFT JOIN cafeteria c ON c.id_cafeteria = a.id_cafeteria
            WHERE a.fecha_hora::date = (now() AT TIME ZONE 'America/Bogota')::date
            ORDER BY a.fecha_hora DESC LIMIT 20""")
    st.markdown(f"**Alertas de hoy ({len(alertas)})** · las genera n8n (espera > 3 min, respaldos, errores)")
    if alertas.empty:
        st.success("Sin alertas hoy.", icon="✅")
    else:
        st.dataframe(alertas, hide_index=True, use_container_width=True)


tablero()
ui.pie_de_pagina()
