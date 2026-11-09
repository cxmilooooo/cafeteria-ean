"""Calidad del servicio y continuidad: reclamos, alertas, respaldos y monitoreo."""
import plotly.express as px
import streamlit as st

from plantilla import componentes as ui, datos, tema

ui.encabezado("Reclamos, alertas y continuidad",
              "¿Qué está fallando y el sistema está protegido? Reclamos (RF-12), alertas de n8n y respaldos (RPO 5 min).")
f = ui.filtros()

rec = datos.consulta(
    """SELECT r.id_reclamo, r.fecha_hora, c.nombre AS cafeteria, r.id_pedido, r.tipo_reclamo, r.descripcion,
              r.solucion, r.estado, e.nombre AS atendido_por
         FROM reclamo r JOIN pedido p ON p.id_pedido = r.id_pedido
         JOIN cafeteria c ON c.id_cafeteria = p.id_cafeteria
         JOIN empleado e ON e.id_empleado = r.id_empleado
        WHERE r.fecha_hora::date BETWEEN :d AND :h AND p.id_cafeteria = ANY(:c)
        ORDER BY r.fecha_hora DESC""", d=f["desde"], h=f["hasta"], c=list(f["cafeterias"]))

resp = datos.consulta("SELECT max(fecha_hora) AS ultimo, count(*) AS total FROM respaldo_log").iloc[0]
mon = datos.consulta("SELECT estado, detalle, fecha_hora FROM monitoreo ORDER BY id DESC LIMIT 1")
ahora = datos.consulta("SELECT (now() AT TIME ZONE 'America/Bogota') AS t").iloc[0].t
min_resp = (ahora - resp.ultimo).total_seconds() / 60 if resp.ultimo is not None else None

ui.fila_datos([
    ui.tarjeta_dato("Reclamos en el periodo", str(len(rec)), f"{(rec.estado == 'Abierto').sum()} abiertos"),
    ui.tarjeta_dato("Último respaldo", f"hace {min_resp:.0f} min" if min_resp is not None else "—",
                    "objetivo RPO ≤ 5 min" + (" · ATRASADO" if min_resp is None or min_resp > 10 else " · OK")),
    ui.tarjeta_dato("Respaldos registrados", str(int(resp.total)), "se guardan 24 h en ./respaldos"),
    ui.tarjeta_dato("Monitoreo n8n", mon.iloc[0].estado if not mon.empty else "—",
                    f"{mon.iloc[0].fecha_hora:%H:%M}" if not mon.empty else "sin latidos todavía"),
])

c1, c2 = st.columns(2)
with c1:
    if rec.empty:
        ui.sin_datos("Sin reclamos en el periodo.")
    else:
        t = rec.tipo_reclamo.value_counts().reset_index()
        t.columns = ["tipo", "reclamos"]
        fig = px.bar(t, x="reclamos", y="tipo", orientation="h", text="reclamos", title="Reclamos por tipo",
                     color_discrete_sequence=[tema.SERIES[0]])
        fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
        fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x}<extra></extra>")
        ui.grafico(fig, t, alto=300, clave="reclamos_tipo")
with c2:
    al = datos.consulta(
        """SELECT a.tipo, count(*) AS alertas FROM alerta a
            WHERE a.fecha_hora::date BETWEEN :d AND :h GROUP BY a.tipo ORDER BY 2 DESC""",
        d=f["desde"], h=f["hasta"])
    if al.empty:
        ui.sin_datos("Sin alertas en el periodo.")
    else:
        fig = px.bar(al, x="alertas", y="tipo", orientation="h", text="alertas", title="Alertas generadas por n8n",
                     color_discrete_sequence=[tema.SERIES[0]])
        fig.update_yaxes(categoryorder="total ascending", title=None); fig.update_xaxes(title=None)
        fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x}<extra></extra>")
        ui.grafico(fig, al, alto=300, clave="alertas_tipo")

st.markdown("**Detalle de reclamos**")
st.dataframe(rec, hide_index=True, use_container_width=True)
ui.pie_de_pagina()
