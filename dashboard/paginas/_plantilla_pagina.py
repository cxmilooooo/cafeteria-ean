"""Plantilla para crear una página nueva del dashboard.

1. Copien este archivo en paginas/ con otro nombre (ej. paginas/ventas.py).
2. Regístrenlo en app.py dentro de PAGINAS:  st.Page("paginas/ventas.py", title="Ventas", icon="💰")
3. Mantengan el orden: encabezado -> filtros -> contadores/KPI -> subtítulo + gráfico -> pie.
4. Si no hay datos, un mensaje amable (ui.sin_datos) en vez de un gráfico vacío.
"""
import plotly.express as px

from plantilla import componentes as ui, datos, tema

ui.encabezado("Título de la página", "Una frase que diga qué pregunta responde esta página.")
f = ui.filtros()  # periodo, cafetería y solo horas pico; ui.filtros(periodo=False) para el día en curso
df = datos.pedidos(f["desde"], f["hasta"], f["cafeterias"], f["franjas"])

if df.empty:
    ui.sin_datos()
else:
    k = datos.calcular_kpis(df)  # las fórmulas de los 5 KPI viven solo en datos.py
    ui.contadores([("Pedidos", ui.miles(k["llegados"]), "en el periodo"),
                   ("Ventas", ui.pesos(k["ventas"]), "pedidos pagados")])
    ui.subtitulo("Pedidos por día", "Una frase que explique cómo leer el gráfico.")
    serie = df.groupby("fecha").size().reset_index(name="pedidos")
    fig = px.line(serie, x="fecha", y="pedidos", title="Pedidos por día", color_discrete_sequence=[tema.SERIES[0]])
    ui.grafico(fig, serie)  # el gráfico y, debajo, su tabla de datos en un desplegable

ui.pie_de_pagina()
