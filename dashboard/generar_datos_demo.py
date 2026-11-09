"""Genera datos SIMULADOS de días anteriores para que el dashboard tenga historia.

Simula un piloto de N días hábiles (lunes a sábado) en las dos cafeterías: al
inicio casi todo se pide en caja y los tiempos se parecen a la línea base
(≈ 7 min de atención); con los días crece el uso del QR y los tiempos bajan.
Los datos quedan marcados en historial_estado con origen 'demo'.

Uso (con el sistema arriba):
    docker compose exec dashboard python generar_datos_demo.py --dias 15
    docker compose exec dashboard python generar_datos_demo.py --borrar   # quita los datos demo
"""
import argparse
import os
import random
from datetime import date, datetime, time, timedelta

import psycopg

URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://cafeteria:cafeteria2026@localhost:5433/cafeteria")
URL = URL.replace("postgresql+psycopg://", "postgresql://")

# Llegadas por hora (cafetería principal). La Torre 2 recibe el 85 %.
LLEGADAS = {7: 22, 8: 28, 9: 26, 10: 72, 11: 30, 12: 82, 13: 78, 14: 24, 15: 18, 16: 16, 17: 14, 18: 8, 19: 5}
NOMBRES = ["Valentina", "Santiago", "Mariana", "Sebastián", "Isabella", "Mateo", "Sara", "Nicolás", "Gabriela",
           "Samuel", "Daniela", "Alejandro", "Laura", "David", "Camila", "Tomás", "Juliana", "Felipe", "Natalia", "Andrés"]
MENU = {  # producto -> peso por franja (mañana, cambio de clase, almuerzo, tarde)
    "Tinto": (9, 8, 2, 6), "Café con leche": (8, 6, 1, 4), "Capuchino": (5, 5, 1, 4), "Chocolate": (3, 2, 0, 2),
    "Jugo natural": (3, 3, 6, 3), "Limonada de coco": (1, 2, 5, 2), "Gaseosa": (1, 2, 5, 3), "Agua": (2, 3, 4, 3),
    "Empanada": (5, 8, 2, 5), "Pan de bono": (6, 6, 1, 4), "Arepa con queso": (5, 5, 1, 3),
    "Sándwich de pollo": (2, 4, 3, 3), "Croissant": (4, 3, 0, 2), "Almuerzo del día": (0, 0, 14, 1),
    "Almuerzo vegetariano": (0, 0, 5, 0), "Wrap de pollo": (0, 1, 6, 2), "Ensalada": (0, 1, 4, 1),
    "Fruta picada": (2, 2, 2, 2), "Brownie": (1, 2, 3, 3),
}


def franja_menu(h):
    return 0 if h < 10 else 1 if h < 11 else 2 if 12 <= h < 14 else 3


def es_pico(h):
    return h == 10 or 12 <= h < 14


def simular(cur, dias):
    cur.execute("SELECT id_cafeteria FROM cafeteria ORDER BY 1")
    cafeterias = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT id_producto, nombre, precio FROM producto")
    productos = {n: (i, float(p)) for i, n, p in cur.fetchall()}
    cur.execute("SELECT id_empleado, id_cafeteria, rol FROM empleado WHERE activo")
    emp = cur.fetchall()
    cur.execute("SELECT id_franja, hora_inicio, hora_fin FROM franja_horaria")
    franjas = cur.fetchall()

    def id_franja(t):
        return next(f for f, a, b in franjas if a <= t < b)

    # Días hábiles anteriores a hoy
    fechas, d = [], date.today() - timedelta(days=1)
    while len(fechas) < dias:
        if d.weekday() < 6:
            fechas.append(d)
        d -= timedelta(days=1)
    fechas.reverse()

    total = 0
    for n_dia, fecha in enumerate(fechas):
        av = n_dia / max(len(fechas) - 1, 1)        # avance del piloto 0 -> 1
        dia_factor = {0: 1.0, 1: 1.05, 2: 1.05, 3: 1.0, 4: 0.9, 5: 0.75}[fecha.weekday()]
        for caf in cafeterias:
            escala = 1.0 if caf == cafeterias[0] else 0.85
            cajeros = [e[0] for e in emp if e[1] == caf and e[2] == "Cajero"]
            cocina = [e[0] for e in emp if e[1] == caf and e[2] == "Cocina/barra"]
            turno = 0
            for hora, base in LLEGADAS.items():
                # En hora pico la demanda se recupera a medida que baja la espera (menos gente desiste)
                recuperacion = 1 + 0.15 * av if es_pico(hora) else 1.0
                for _ in range(int(random.gauss(base * escala * dia_factor * recuperacion, 3))):
                    llegada = datetime.combine(fecha, time(hora)) + timedelta(seconds=random.randint(0, 3599))
                    pico = es_pico(hora)
                    qr = random.random() < 0.15 + 0.50 * av
                    # Espera en fila: alta en hora pico al comienzo del piloto, baja al final
                    media_espera = (4.6 - 2.6 * av) if pico else (1.2 - 0.5 * av)
                    if qr:
                        media_espera *= 0.45                       # el QR evita la fila de caja
                    espera = max(0.2, random.lognormvariate(0, 0.45) * media_espera)
                    p_aband = (0.07 - 0.055 * av) if pico else 0.01
                    if not qr and random.random() < p_aband * (1.5 if espera > 4 else 0.6):
                        cur.execute("""INSERT INTO pedido (id_cafeteria,id_franja,id_cajero,canal,fecha,hora_llegada_fila,
                                       estado,abandono_fila) VALUES (%s,%s,%s,'Caja',%s,%s,'Abandonado',true) RETURNING id_pedido""",
                                    (caf, id_franja(llegada.time()), random.choice(cajeros), fecha, llegada.time()))
                        cur.execute("INSERT INTO historial_estado (id_pedido,estado_anterior,estado_nuevo,origen,fecha_hora) "
                                    "VALUES (%s,NULL,'Abandonado','demo',%s)", (cur.fetchone()[0], llegada))
                        total += 1
                        continue

                    turno += 1
                    toma = llegada + timedelta(minutes=espera)
                    # Cliente (solo pedidos por QR o algunos de caja con nombre)
                    id_cli = None
                    if True:  # todo pedido lleva el nombre que se muestra en la pantalla
                        tipo = random.choices(["Estudiante", "Docente", "Administrativo", "Otro"], [75, 12, 10, 3])[0]
                        autoriza = qr and random.random() < 0.55
                        cur.execute("INSERT INTO cliente (nombre,tipo_cliente,celular,autoriza_datos) VALUES (%s,%s,%s,%s) RETURNING id_cliente",
                                    (random.choice(NOMBRES), tipo, f"3{random.randint(100000000, 299999999)}" if autoriza else None, autoriza))
                        id_cli = cur.fetchone()[0]
                    # Productos
                    pesos = [MENU[n][franja_menu(hora)] for n in MENU]
                    elegidos = set(random.choices(list(MENU), pesos, k=random.choice([1, 1, 2, 2, 3])))
                    lineas = [(productos[n][0], random.choice([1, 1, 1, 2]), productos[n][1]) for n in elegidos]
                    valor = sum(c * p for _, c, p in lineas)
                    # QR que nunca se paga -> RN-04
                    if qr and random.random() < 0.03 - 0.015 * av:
                        cur.execute("""INSERT INTO pedido (id_cliente,id_cafeteria,id_franja,numero_turno,canal,fecha,hora_llegada_fila,
                                       hora_toma_pedido,estado,abandono_fila,valor_total) VALUES (%s,%s,%s,%s,'QR',%s,%s,%s,'Abandonado',true,%s)
                                       RETURNING id_pedido""",
                                    (id_cli, caf, id_franja(llegada.time()), turno, fecha, llegada.time(), toma.time(), valor))
                        pid = cur.fetchone()[0]
                        cur.executemany("INSERT INTO detalle_pedido VALUES (%s,%s,%s,%s,%s,NULL)", [(pid, i, c, p, c * p) for i, c, p in lineas])
                        cur.execute("INSERT INTO historial_estado (id_pedido,estado_anterior,estado_nuevo,origen,fecha_hora) "
                                    "VALUES (%s,'Registrado','Abandonado','demo',%s)", (pid, toma + timedelta(minutes=10)))
                        total += 1
                        continue
                    pago = toma + timedelta(minutes=random.uniform(0.1, 0.6))
                    carga = 1.25 if pico else 1.0
                    prep = max(0.8, random.gauss((2.8 - 0.6 * av) * carga * (0.9 if len(lineas) == 1 else 1.15), 0.8))
                    listo = pago + timedelta(minutes=prep)
                    entrega = listo + timedelta(minutes=max(0.1, random.gauss(0.7 - 0.4 * av, 0.25)))
                    correcto = random.random() < (0.89 + 0.08 * av)
                    cur.execute("""INSERT INTO pedido (id_cliente,id_cafeteria,id_franja,id_cajero,id_preparador,numero_turno,canal,
                                   fecha,hora_llegada_fila,hora_toma_pedido,hora_listo,hora_entrega,estado,abandono_fila,
                                   entregado_correcto,valor_total)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Entregado',false,%s,%s) RETURNING id_pedido""",
                                (id_cli, caf, id_franja(llegada.time()), None if qr else random.choice(cajeros),
                                 random.choice(cocina), turno, "QR" if qr else "Caja", fecha, llegada.time(), toma.time(),
                                 listo.time(), entrega.time(), correcto, valor))
                    pid = cur.fetchone()[0]
                    cur.executemany("INSERT INTO detalle_pedido VALUES (%s,%s,%s,%s,%s,NULL)", [(pid, i, c, p, c * p) for i, c, p in lineas])
                    medio = random.choice(["Transferencia", "Tarjeta"]) if qr else random.choices(["Efectivo", "Tarjeta", "Transferencia"], [50, 25, 25])[0]
                    cur.execute("INSERT INTO pago (id_pedido,medio_pago,valor,fecha_hora,numero_factura) VALUES (%s,%s,%s,%s,%s)",
                                (pid, medio, valor, pago, f"DEMO-{pid}"))
                    cur.execute("INSERT INTO historial_estado (id_pedido,estado_anterior,estado_nuevo,origen,fecha_hora) "
                                "VALUES (%s,'Listo','Entregado','demo',%s)", (pid, entrega))
                    if not correcto and random.random() < 0.7:
                        cur.execute("INSERT INTO reclamo (id_pedido,id_empleado,tipo_reclamo,descripcion,solucion,fecha_hora,estado) "
                                    "VALUES (%s,%s,%s,%s,%s,%s,'Resuelto')",
                                    (pid, random.choice(cajeros), random.choice(["Pedido incompleto", "Pedido equivocado", "Entregado a otra persona"]),
                                     "Registrado en la simulación", "Se repuso el producto", entrega + timedelta(minutes=2)))
                    total += 1
        cur.execute("SELECT fn_cierre_diario(%s)", (fecha,))
        print(f"  {fecha}  avance {av:4.0%}")
    return total


def borrar(cur):
    cur.execute("""CREATE TEMP TABLE demo AS SELECT DISTINCT id_pedido FROM historial_estado WHERE origen = 'demo'""")
    cur.execute("CREATE TEMP TABLE demo_cli AS SELECT DISTINCT id_cliente FROM pedido WHERE id_pedido IN (SELECT id_pedido FROM demo) AND id_cliente IS NOT NULL")
    for t in ("reclamo", "pago", "notificacion", "historial_estado", "detalle_pedido"):
        cur.execute(f"DELETE FROM {t} WHERE id_pedido IN (SELECT id_pedido FROM demo)")
    cur.execute("ALTER TABLE pedido DISABLE TRIGGER pedido_proteger_horas")
    cur.execute("DELETE FROM pedido WHERE id_pedido IN (SELECT id_pedido FROM demo)")
    cur.execute("ALTER TABLE pedido ENABLE TRIGGER pedido_proteger_horas")
    cur.execute("DELETE FROM cliente WHERE id_cliente IN (SELECT id_cliente FROM demo_cli)")
    cur.execute("DELETE FROM kpi_diario WHERE fecha < (now() AT TIME ZONE 'America/Bogota')::date")
    print(f"Datos demo eliminados: {cur.rowcount} filas de kpi_diario recalculables.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=15)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--borrar", action="store_true")
    a = ap.parse_args()
    random.seed(a.semilla)
    with psycopg.connect(URL) as con, con.cursor() as cur:
        if a.borrar:
            borrar(cur)
        else:
            cur.execute("SELECT count(*) FROM historial_estado WHERE origen = 'demo'")
            if cur.fetchone()[0]:
                raise SystemExit("Ya hay datos demo. Bórrenlos primero con --borrar.")
            print(f"Generando {a.dias} días simulados...")
            print(f"Listo: {simular(cur, a.dias):,} clientes simulados.")
