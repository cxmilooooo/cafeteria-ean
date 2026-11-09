"""Tema visual único del dashboard.

Todos los colores, metas y el estilo de los gráficos salen de aquí. Para cambiar
la identidad visual (por ejemplo, a los colores de la universidad) basta con
editar este archivo: las páginas no tienen colores escritos a mano.
"""
import plotly.graph_objects as go
import plotly.io as pio

# Superficie, tinta y líneas
SUPERFICIE = "#fcfcfb"
FONDO = "#f9f9f7"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_SUAVE = "#898781"
REJILLA = "#e1e0d9"
EJE = "#c3c2b7"

# Paleta categórica en orden fijo (validada para daltonismo en pares adyacentes).
# Regla: el color sigue a la entidad, nunca a su posición en el ranking.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Colores fijos por entidad, para que "QR" sea siempre del mismo color en todas las páginas
COLOR_CANAL = {"QR": SERIES[0], "Caja": SERIES[1]}
COLOR_TIPO_CLIENTE = {"Estudiante": SERIES[0], "Docente": SERIES[1], "Administrativo": SERIES[2], "Otro": SERIES[3]}

# Secuencial (una sola tonalidad, de claro a oscuro) para magnitudes
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Estado (reservado: nunca se usa como color de una serie). Siempre va con ícono + texto.
ESTADO = {
    "bien":    {"color": "#0ca30c", "texto": "#006300", "icono": "●", "etiqueta": "En meta"},
    "atencion": {"color": "#fab219", "texto": "#8a5a00", "icono": "▲", "etiqueta": "Cerca de la meta"},
    "mal":     {"color": "#d03b3b", "texto": "#b3261e", "icono": "■", "etiqueta": "Fuera de meta"},
    "sin":     {"color": "#c3c2b7", "texto": "#52514e", "icono": "○", "etiqueta": "Sin datos"},
}

# Ficha de los 5 KPI del documento (sección 10). Cambiar la meta aquí la cambia en todo el tablero.
KPIS = {
    "kpi1": {"nombre": "Tiempo promedio de atención", "unidad": "min", "meta": 5.0, "sentido": "menor",
             "linea_base": 7.0, "formula": "Σ minutos de atención / # clientes atendidos",
             "fuente": "pedido.hora_llegada_fila → pedido.hora_entrega"},
    "kpi2": {"nombre": "Pedidos entregados correctamente", "unidad": "%", "meta": 95.0, "sentido": "mayor",
             "linea_base": None, "formula": "(# entregados correctamente / # entregados) × 100",
             "fuente": "pedido.entregado_correcto y reclamo"},
    "kpi3": {"nombre": "Pedidos por hora en hora pico", "unidad": "ped/h", "meta": 80.0, "sentido": "mayor",
             "linea_base": 70.0, "formula": "# pedidos completados en franja pico / # horas pico analizadas",
             "fuente": "pedido.estado + franja_horaria.es_hora_pico"},
    "kpi4": {"nombre": "Tiempo promedio de espera en fila", "unidad": "min", "meta": 3.0, "sentido": "menor",
             "linea_base": None, "formula": "Σ minutos de espera / # clientes atendidos",
             "fuente": "pedido.hora_llegada_fila → pedido.hora_toma_pedido"},
    "kpi5": {"nombre": "Abandono de fila", "unidad": "%", "meta": 2.0, "sentido": "menor",
             "linea_base": None, "formula": "(# clientes que abandonan / # clientes que llegan) × 100",
             "fuente": "pedido.abandono_fila"},
}

# Margen para "cerca de la meta" (10 %)
TOLERANCIA = 0.10


def estado_kpi(clave: str, valor) -> str:
    if valor is None or valor != valor:  # None o NaN
        return "sin"
    k = KPIS[clave]
    meta = k["meta"]
    if k["sentido"] == "menor":
        if valor <= meta:
            return "bien"
        return "atencion" if valor <= meta * (1 + TOLERANCIA) else "mal"
    if valor >= meta:
        return "bien"
    return "atencion" if valor >= meta * (1 - TOLERANCIA) else "mal"


def registrar_plantilla_plotly() -> None:
    """Plantilla 'cafeteria': marcas finas, rejilla tenue, un solo eje, leyenda arriba."""
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13, color=TINTA_2),
        title=dict(font=dict(size=15, color=TINTA), x=0, xanchor="left", y=0.98, yanchor="top"),
        paper_bgcolor=SUPERFICIE, plot_bgcolor=SUPERFICIE,
        colorway=SERIES,
        margin=dict(l=8, r=8, t=84, b=8),
        xaxis=dict(showgrid=False, linecolor=EJE, ticks="", tickfont=dict(color=TINTA_SUAVE), zeroline=False,
                   title=dict(font=dict(color=TINTA_SUAVE))),
        yaxis=dict(gridcolor=REJILLA, gridwidth=1, linecolor=EJE, showline=False, zeroline=False,
                   tickfont=dict(color=TINTA_SUAVE), title=dict(font=dict(color=TINTA_SUAVE))),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0, title_text="",
                    font=dict(color=TINTA_2)),
        hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=EJE, font=dict(color=TINTA)),
        hovermode="closest",
        bargap=0.35, bargroupgap=0.08,
    )
    t.data.bar = [go.Bar(marker=dict(line=dict(color=SUPERFICIE, width=2), cornerradius=4))]
    t.data.scatter = [go.Scatter(line=dict(width=2), marker=dict(size=8, line=dict(color=SUPERFICIE, width=2)))]
    pio.templates["cafeteria"] = t
    pio.templates.default = "cafeteria"
