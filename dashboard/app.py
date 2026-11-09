"""Dashboard de KPI · Cafetería EAN (Streamlit + Plotly).

Ejecutar:  streamlit run app.py
Agregar una página: crear un archivo en paginas/ con la estructura de
paginas/_plantilla_pagina.py y registrarlo en la lista PAGINAS de abajo.
"""
import hmac
import os

import streamlit as st

import plantilla

st.set_page_config(page_title="Cafetería EAN · KPI", page_icon="☕", layout="wide")
plantilla.iniciar_pagina()

# Acceso del coordinador (RNF-05: solo el coordinador ve los reportes)
CLAVE = os.environ.get("DASHBOARD_PASSWORD", "")
if CLAVE and not st.session_state.get("autenticado"):
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.markdown("### ☕ Cafetería EAN · KPI")
        with st.form("ingreso"):
            clave = st.text_input("Contraseña del coordinador", type="password")
            if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
                if hmac.compare_digest(clave.encode(), CLAVE.encode()):
                    st.session_state.autenticado = True
                    st.rerun()
                st.error("Contraseña incorrecta")
    st.stop()

PAGINAS = {
    "Indicadores": [
        st.Page("paginas/resumen.py", url_path="resumen", title="Resumen de KPI", icon="📊", default=True),
        st.Page("paginas/operacion.py", url_path="operacion", title="Operación en vivo", icon="🟢"),
        st.Page("paginas/analisis.py", url_path="analisis", title="Franjas, canales y productos", icon="🔎"),
    ],
    "Analítica": [
        st.Page("paginas/demanda.py", url_path="demanda", title="Demanda esperada", icon="📈"),
        st.Page("paginas/calidad.py", url_path="calidad", title="Reclamos, alertas y continuidad", icon="🛡️"),
    ],
    "Coordinador": [
        st.Page("paginas/administracion.py", url_path="administracion", title="Menú y código QR", icon="⚙️"),
    ],
}

st.navigation(PAGINAS).run()
