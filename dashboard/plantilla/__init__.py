"""Plantilla estandarizada del dashboard de la Cafetería EAN.

- tema.py        colores, metas de los KPI y plantilla de Plotly
- datos.py       consultas a Postgres y cálculo de los KPI
- componentes.py piezas visuales comunes (encabezado, filtros, tarjetas, gráficos)
- estilos.css    estilos de las tarjetas y del encabezado
"""
from pathlib import Path

import streamlit as st

from . import tema


def iniciar_pagina() -> None:
    """Se llama una vez desde app.py: aplica la plantilla de gráficos y los estilos."""
    tema.registrar_plantilla_plotly()
    css = (Path(__file__).parent / "estilos.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
