"""Dashboard de KPI · Cafetería EAN (Streamlit + Plotly).

Ejecutar:  streamlit run app.py
Agregar una página: crear un archivo en paginas/ con la estructura de
paginas/_plantilla_pagina.py y registrarlo en la lista PAGINAS de abajo
(procuren no pasar de 3 o 4 páginas: el coordinador debe entender todo en segundos).
"""
import hmac
import os
import time

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

pagina = st.navigation(PAGINAS, position="top")

# Actualización automática: Hoy e Indicadores se recargan solos cada 15 segundos.
# Administración no, para no interrumpir a quien está escribiendo en un formulario.
if pagina.title != "Administración":
    st.session_state["_ultima_carga"] = time.time()

    @st.fragment(run_every=15)
    def _autorefresco():
        # El temporizador vuelve a ejecutar este bloque; si ya pasaron 15 s desde la última carga,
        # se recarga toda la página con datos frescos.
        if time.time() - st.session_state.get("_ultima_carga", 0) >= 14:
            st.cache_data.clear()
            st.rerun(scope="app")
    _autorefresco()

pagina.run()
