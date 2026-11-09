"""Dashboard de KPI · Cafetería EAN (Streamlit + Plotly).

Ejecutar:  streamlit run app.py
Agregar una página: crear un archivo en paginas/ con la estructura de
paginas/_plantilla_pagina.py y registrarlo en la lista PAGINAS de abajo
(procuren no pasar de 3 o 4 páginas: el coordinador debe entender todo en segundos).
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

# Solo tres páginas, en la barra de arriba. Para agregar una, ver paginas/_plantilla_pagina.py
PAGINAS = [
    st.Page("paginas/hoy.py", url_path="hoy", title="Hoy", icon="🟢", default=True),
    st.Page("paginas/indicadores.py", url_path="indicadores", title="Indicadores", icon="📊"),
    st.Page("paginas/administracion.py", url_path="administracion", title="Administración", icon="⚙️"),
]

st.navigation(PAGINAS, position="top").run()
