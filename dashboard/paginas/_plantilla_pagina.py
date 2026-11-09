"""Plantilla para crear una página nueva del dashboard.

1. Copien este archivo en paginas/ con otro nombre (ej. paginas/ventas.py).
2. Regístrenlo en app.py dentro de PAGINAS:  st.Page("paginas/ventas.py", title="Ventas", icon="💰")
3. Mantengan el orden: encabezado -> filtros -> tarjetas -> gráficos -> pie.
"""
import plotly.express as px

from plantilla import componentes as ui, datos, tema

ui.encabezado("Título de la página", "Una frase que diga qué pregunta responde esta página.")
f = ui.filtros()
df = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])

if df.empty:
    ui.sin_datos()
else:
    ui.fila_datos([ui.tarjeta_dato("Pedidos", f"{len(df):,}".replace(",", "."), "en el periodo")])
    serie = df.groupby("fecha").size().reset_index(name="pedidos")
    fig = px.line(serie, x="fecha", y="pedidos", title="Pedidos por día", color_discrete_sequence=[tema.SERIES[0]])
    ui.grafico(fig, serie)

ui.pie_de_pagina()
