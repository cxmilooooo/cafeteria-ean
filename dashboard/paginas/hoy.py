"""Hoy: cómo va el servicio en este momento. Se actualiza sola cada 15 segundos (ver app.py)."""
from datetime import datetime

import streamlit as st

from plantilla import componentes as ui, datos

ui.encabezado("Hoy", "Cómo va el servicio en este momento. La página se actualiza sola cada 15 segundos.")
f = ui.filtros(periodo=False, pico=False)

EN_CURSO = ["Registrado", "Pagado", "En preparación", "Listo"]
EN_COCINA = ["Pagado", "En preparación"]


def tablero():
    hoy = datos.pedidos_hoy(f["cafeterias"])
    ahora = datetime.now()
    st.caption(f"Actualizado a las {ahora:%H:%M:%S}")

    if hoy.empty:
        st.info("Todavía no hay pedidos hoy. Cuando lleguen, aquí verás cómo va el servicio.", icon="☕")
    else:
        k = datos.calcular_kpis(hoy)
        activos = hoy[hoy.estado.isin(EN_CURSO)].copy()
        listos = int((hoy.estado == "Listo").sum())
        ui.contadores([
            ("Pedidos de hoy", ui.miles(k["llegados"]), f"{ui.miles(k['entregados'])} ya entregados"),
            ("En cocina ahora", ui.miles(int(hoy.estado.isin(EN_COCINA).sum())), "pagados o en preparación"),
            ("Listos para entregar", ui.miles(listos), "esperando que los recojan"),
            ("Ventas de hoy", ui.pesos(k["ventas"]), "pedidos pagados"),
        ])

        ui.subtitulo("¿Cumplimos las metas hoy?",
                     "Verde: en meta · amarillo: cerca · rojo: fuera de meta. El día aún no termina.")
        ui.fila_kpis(k, comparar_linea_base=False)

        ui.subtitulo(f"Pedidos en curso ({len(activos)})", "Del más antiguo al más reciente.")
        if activos.empty:
            st.success("No hay pedidos pendientes en este momento.", icon="✅")
        else:
            activos["espera"] = activos.hora_llegada_fila.map(
                lambda h: max(0, int((ahora - datetime.combine(ahora.date(), h)).total_seconds() // 60)))
            activos = activos.sort_values("hora_llegada_fila")
            columnas = {"numero_turno": "Turno", "cafeteria": "Cafetería", "canal": "Canal", "estado": "Estado",
                        "hora_llegada_fila": "Llegó", "espera": "Minutos desde que llegó"}
            if f["una_cafeteria"]:
                columnas.pop("cafeteria")
            tabla = activos[list(columnas)].rename(columns=columnas)
            tabla["Llegó"] = activos.hora_llegada_fila.map(lambda h: h.strftime("%H:%M"))
            st.dataframe(tabla, hide_index=True, use_container_width=True,
                         height=min(38 + 35 * len(tabla), 420))

    caja = datos.caja_hoy()
    ui.subtitulo("Cierre de caja de hoy", "Lo que debería haber en caja y en cada medio de pago.")
    if caja.empty:
        st.caption("Todavía no hay cobros hoy.")
    else:
        total = float(caja["Total"].sum())
        caja["Total"] = caja["Total"].map(lambda v: ui.pesos(float(v)))
        st.dataframe(caja, hide_index=True, use_container_width=True)
        st.markdown(f"**Total del día: {ui.pesos(total)}**")

    alertas = datos.alertas_hoy(f["cafeterias"])
    ui.subtitulo(f"Alertas de hoy ({len(alertas)})",
                 "Las envía el sistema cuando la espera supera 3 minutos, falla un respaldo u ocurre un error.")
    if alertas.empty:
        st.success("Sin alertas hoy.", icon="✅")
    else:
        st.dataframe(alertas, hide_index=True, use_container_width=True)


tablero()
ui.pie_de_pagina()
