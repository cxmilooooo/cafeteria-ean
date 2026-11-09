"""Coordinador: disponibilidad del menú (RF-15) y códigos QR para pedir (RF-01)."""
import io
import os

import qrcode
import streamlit as st

from plantilla import componentes as ui, datos

ui.encabezado("Menú y código QR",
              "Marquen productos como agotados (se refleja al instante en el QR y en caja) e impriman el QR de cada cafetería.")

st.markdown("#### Disponibilidad del menú")
menu = datos.consulta("SELECT id_producto, nombre, categoria, precio, disponible FROM producto ORDER BY categoria, nombre")
menu["precio"] = menu.precio.astype(float)
editado = st.data_editor(menu, hide_index=True, use_container_width=True, disabled=["id_producto"],
                         column_config={"precio": st.column_config.NumberColumn("precio", format="$%d", min_value=0),
                                        "disponible": st.column_config.CheckboxColumn("disponible")},
                         key="editor_menu")
if st.button("Guardar cambios del menú", type="primary"):
    cambios = 0
    for orig, nuevo in zip(menu.itertuples(), editado.itertuples()):
        if (orig.nombre, orig.categoria, orig.precio, orig.disponible) != (nuevo.nombre, nuevo.categoria, nuevo.precio, nuevo.disponible):
            datos.ejecutar("UPDATE producto SET nombre=:n, categoria=:c, precio=:p, disponible=:d WHERE id_producto=:i",
                           n=nuevo.nombre, c=nuevo.categoria, p=nuevo.precio, d=bool(nuevo.disponible), i=int(nuevo.id_producto))
            cambios += 1
    st.success(f"{cambios} producto(s) actualizados.")

st.markdown("#### Código QR para pedir")
base = os.environ.get("URL_PEDIDOS", "http://localhost:8080").rstrip("/")
st.caption("Para que los celulares lo abran, URL_PUBLICA en el archivo .env debe ser la IP del PC en la red Wi-Fi "
           "(ej. http://192.168.1.20:8080).")
cols = st.columns(max(len(datos.catalogos()["cafeterias"]), 1))
for col, caf in zip(cols, datos.catalogos()["cafeterias"].itertuples()):
    url = f"{base}/pedido.html?cafeteria={caf.id_cafeteria}"
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    with col:
        st.image(buf.getvalue(), caption=f"{caf.nombre}\n{url}", width=220)
        st.download_button(f"Descargar QR · {caf.nombre}", buf.getvalue(), file_name=f"qr_cafeteria_{caf.id_cafeteria}.png",
                           mime="image/png", key=f"qr{caf.id_cafeteria}")
ui.pie_de_pagina()
