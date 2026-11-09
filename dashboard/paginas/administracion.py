"""Administración del coordinador: menú (RF-15), personal y PIN (RNF-05) y códigos QR (RF-01)."""
import io
import os
import re

import qrcode
import streamlit as st

from plantilla import componentes as ui, datos

ui.encabezado("Administración", "Menú, personal y códigos QR. Los cambios se ven al instante en caja, cocina y el QR.")

ROLES = ["Cajero", "Cocina/barra", "Coordinador"]
PIN_VALIDO = re.compile(r"\d{4,8}")


def pin_error(pin: str, confirmacion: str) -> str | None:
    if not PIN_VALIDO.fullmatch(pin or ""):
        return "El PIN debe tener solo números, entre 4 y 8 dígitos."
    if pin != confirmacion:
        return "Los dos PIN no coinciden."
    return None


# --- Estado del sistema en una línea ----------------------------------------------
est = datos.estado_sistema()
m = est["min_respaldo"]
if m is None:
    resp = "⚠️ Último respaldo: sin registros todavía"
elif m <= 10:
    resp = f"✅ Último respaldo: hace {m:.0f} min"
else:
    resp = f"⚠️ Último respaldo: hace {m:.0f} min (debería ser cada 5 min)"
if est["monitoreo"] is None:
    mon = "Monitoreo: sin señal todavía"
else:
    mon = f"{'✅' if est['monitoreo'] == 'OK' else '⚠️'} Monitoreo: {est['monitoreo']} ({est['hora_monitoreo']})"
st.markdown(f"<div class='estado-sistema'>Estado del sistema · {resp} · {mon}</div>", unsafe_allow_html=True)

tab_menu, tab_personal, tab_qr = st.tabs(["🍽️ Menú", "👥 Personal", "🔳 Códigos QR"])


# --- (a) Menú ----------------------------------------------------------------------
def guardar_disponible(id_producto: int, nombre: str, clave: str) -> None:
    disponible = bool(st.session_state[clave])
    datos.ejecutar("UPDATE producto SET disponible = :d WHERE id_producto = :i", d=disponible, i=id_producto)
    st.toast(f"{nombre}: {'disponible' if disponible else 'agotado'}", icon="✅" if disponible else "⛔")


with tab_menu:
    menu = datos.menu()
    st.caption("Apaga el interruptor cuando un producto se agote: deja de aparecer para pedir. Se guarda al instante.")
    if menu.empty:
        ui.sin_datos("Todavía no hay productos en el menú. Agrega el primero abajo.")
    categorias = sorted(menu.categoria.unique().tolist())
    cols = st.columns(3)
    for i, cat in enumerate(categorias):
        with cols[i % 3].container(border=True):
            st.markdown(f"**{cat}**")
            for p in menu[menu.categoria == cat].itertuples():
                clave = f"disp_{p.id_producto}"
                st.session_state[clave] = bool(p.disponible)
                st.toggle(f"{p.nombre} · {ui.pesos(p.precio)}".replace("$", "\\$") + ("" if p.disponible else " · agotado"), key=clave,
                          on_change=guardar_disponible, args=(int(p.id_producto), p.nombre, clave))

    c1, c2 = st.columns(2)
    with c1, st.form("nuevo_producto", clear_on_submit=True, border=True):
        st.markdown("**Agregar un producto**")
        nombre = st.text_input("Nombre", max_chars=60, placeholder="Ej.: Aromática")
        categoria = st.selectbox("Categoría", categorias, index=None, accept_new_options=True,
                                 placeholder="Elige una o escribe una nueva")
        precio = st.number_input("Precio (pesos)", min_value=0, step=100, value=0)
        if st.form_submit_button("Agregar al menú", type="primary"):
            nombre, categoria = (nombre or "").strip(), (categoria or "").strip()
            if not nombre or not categoria:
                st.error("Escribe el nombre y elige la categoría.")
            elif len(categoria) > 20:
                st.error("La categoría puede tener máximo 20 letras.")
            elif precio <= 0:
                st.error("El precio debe ser mayor que cero.")
            elif nombre.lower() in set(menu.nombre.str.lower()):
                st.error(f"Ya existe un producto llamado «{nombre}».")
            else:
                datos.ejecutar("INSERT INTO producto (nombre, categoria, precio, disponible) VALUES (:n, :c, :p, TRUE)",
                               n=nombre, c=categoria, p=precio)
                st.toast(f"«{nombre}» agregado al menú.", icon="✅")
                st.rerun()
    with c2, st.form("cambiar_precio", border=True):
        st.markdown("**Cambiar un precio**")
        opciones = {f"{p.nombre} ({ui.pesos(p.precio)})": p for p in menu.itertuples()}
        elegido = st.selectbox("Producto", list(opciones), index=None, placeholder="Elige un producto")
        nuevo = st.number_input("Precio nuevo (pesos)", min_value=0, step=100, value=0)
        if st.form_submit_button("Guardar precio", type="primary"):
            if elegido is None:
                st.error("Elige un producto.")
            elif nuevo <= 0:
                st.error("El precio debe ser mayor que cero.")
            else:
                p = opciones[elegido]
                datos.ejecutar("UPDATE producto SET precio = :p WHERE id_producto = :i", p=nuevo, i=int(p.id_producto))
                st.toast(f"{p.nombre}: ahora cuesta {ui.pesos(nuevo)}.", icon="✅")
                st.rerun()


# --- (b) Personal -------------------------------------------------------------------
def guardar_activo(id_empleado: int, nombre: str, clave: str) -> None:
    activo = bool(st.session_state[clave])
    datos.ejecutar("UPDATE empleado SET activo = :a WHERE id_empleado = :i", a=activo, i=id_empleado)
    st.toast(f"{nombre}: {'activo' if activo else 'desactivado (ya no puede ingresar)'}", icon="✅" if activo else "⛔")


with tab_personal:
    caf = datos.catalogos()["cafeterias"]
    emp = datos.empleados()
    st.caption("Desactiva a quien ya no trabaje aquí: no podrá ingresar a caja ni a cocina. Se guarda al instante.")
    cols = st.columns(max(len(caf), 1))
    for col, c in zip(cols, caf.itertuples()):
        with col.container(border=True):
            st.markdown(f"**{c.nombre}**")
            gente = emp[emp.id_cafeteria == c.id_cafeteria]
            if gente.empty:
                st.caption("Sin personal registrado.")
            for e in gente.itertuples():
                clave = f"act_{e.id_empleado}"
                st.session_state[clave] = bool(e.activo)
                notas = [e.rol]
                if not e.activo:
                    notas.append("inactivo")
                if not e.tiene_pin:
                    notas.append("sin PIN")
                if e.bloqueado_hasta:
                    notas.append(f"bloqueado hasta las {e.bloqueado_hasta}")
                st.toggle(f"{e.nombre} · {' · '.join(notas)}", key=clave,
                          on_change=guardar_activo, args=(int(e.id_empleado), e.nombre, clave))

    c1, c2 = st.columns(2)
    with c1, st.form("nuevo_empleado", clear_on_submit=True, border=True):
        st.markdown("**Agregar empleado**")
        nombre = st.text_input("Nombre completo", max_chars=80)
        rol = st.selectbox("Rol", ROLES)
        nombre_caf = st.selectbox("Cafetería", caf.nombre.tolist())
        p1 = st.text_input("PIN (4 a 8 números)", type="password", max_chars=8)
        p2 = st.text_input("Repite el PIN", type="password", max_chars=8)
        if st.form_submit_button("Agregar empleado", type="primary"):
            nombre = (nombre or "").strip()
            id_caf = int(caf[caf.nombre == nombre_caf].id_cafeteria.iloc[0])
            repetido = nombre.lower() in set(emp[emp.id_cafeteria == id_caf].nombre.str.lower())
            error = ("Escribe el nombre." if not nombre else
                     f"Ya hay alguien llamado «{nombre}» en {nombre_caf}. Si olvidó su PIN, usa «Cambiar PIN»."
                     if repetido else pin_error(p1, p2))
            if error:
                st.error(error)
            else:
                datos.ejecutar(
                    """INSERT INTO empleado (id_cafeteria, nombre, rol, activo, pin_hash)
                       VALUES (:c, :n, :r, TRUE, crypt(:pin, gen_salt('bf')))""",
                    c=id_caf, n=nombre, r=rol, pin=p1)
                st.toast(f"{nombre} agregado. Ya puede ingresar con su PIN.", icon="✅")
                st.rerun()
    with c2, st.form("cambiar_pin", clear_on_submit=True, border=True):
        st.markdown("**Cambiar PIN**")
        opciones = {f"{e.nombre} · {e.rol} · {e.cafeteria}": int(e.id_empleado) for e in emp.itertuples()}
        quien = st.selectbox("Empleado", list(opciones), index=None, placeholder="Elige a la persona")
        p1 = st.text_input("PIN nuevo (4 a 8 números)", type="password", max_chars=8)
        p2 = st.text_input("Repite el PIN nuevo", type="password", max_chars=8)
        if st.form_submit_button("Guardar PIN", type="primary"):
            error = "Elige a la persona." if quien is None else pin_error(p1, p2)
            if error:
                st.error(error)
            else:
                # También quita el bloqueo por intentos fallidos
                datos.ejecutar(
                    """UPDATE empleado SET pin_hash = crypt(:pin, gen_salt('bf')),
                              intentos_fallidos = 0, bloqueado_hasta = NULL
                        WHERE id_empleado = :i""", pin=p1, i=opciones[quien])
                st.success(f"PIN de {quien.split(' · ')[0]} actualizado.")
    st.caption("Los PIN se guardan cifrados: nadie, ni el coordinador, puede verlos. Si alguien lo olvida, asígnale uno nuevo.")


# --- (c) Códigos QR -----------------------------------------------------------------
with tab_qr:
    base = os.environ.get("URL_PEDIDOS", "http://localhost:8080").rstrip("/")
    st.caption("Imprime el código de cada cafetería y ponlo en la fila. Para que los celulares lo abran, "
               "URL_PUBLICA en el archivo .env debe ser la IP del PC en la red Wi-Fi (ej. http://192.168.1.20:8080).")
    cafeterias = datos.catalogos()["cafeterias"]
    cols = st.columns(max(len(cafeterias), 1))
    for col, c in zip(cols, cafeterias.itertuples()):
        url = f"{base}/pedido.html?cafeteria={c.id_cafeteria}"
        buf = io.BytesIO()
        qrcode.make(url, box_size=8, border=2).save(buf, format="PNG")
        with col:
            st.image(buf.getvalue(), caption=f"{c.nombre} · {url}", width=220)
            st.download_button(f"Descargar QR · {c.nombre}", buf.getvalue(),
                               file_name=f"qr_cafeteria_{c.id_cafeteria}.png", mime="image/png",
                               key=f"qr{c.id_cafeteria}")

ui.pie_de_pagina()
