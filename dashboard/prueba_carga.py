"""Prueba de carga para RNF-01: registro del pedido y turno en ≤ 3 s con 150 pedidos por hora.

Envía pedidos reales por el mismo camino que el celular (nginx → n8n → Postgres),
varios a la vez, mide cuánto tarda cada uno y al final borra los pedidos de prueba.

Uso:
    docker compose exec dashboard python prueba_carga.py              # 150 pedidos, 10 simultáneos
    docker compose exec dashboard python prueba_carga.py --pedidos 300 --simultaneos 20
"""
import argparse
import json
import os
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import psycopg

URL_API = os.environ.get("URL_API", "http://web/api")
DB = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
MARCA = "PRUEBA CARGA"


def un_pedido(i: int):
    cuerpo = json.dumps({
        "id_cafeteria": 1 + i % 2, "canal": "QR", "segundos_espera": 30,
        "cliente": {"nombre": f"{MARCA} {i}", "tipo_cliente": "Estudiante", "autoriza_datos": False},
        "items": [{"id_producto": 1 + i % 19, "cantidad": 1}, {"id_producto": 1 + (i * 7) % 19, "cantidad": 2}],
    }).encode()
    req = urllib.request.Request(f"{URL_API}/pedido", data=cuerpo, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ok = json.loads(r.read()).get("ok", False)
    except Exception:
        ok = False
    return time.perf_counter() - inicio, ok


def limpiar():
    with psycopg.connect(DB) as con, con.cursor() as cur:
        cur.execute("CREATE TEMP TABLE x AS SELECT p.id_pedido, p.id_cliente FROM pedido p JOIN cliente c "
                    "ON c.id_cliente = p.id_cliente WHERE c.nombre LIKE %s", (MARCA + "%",))
        for t in ("notificacion", "historial_estado", "detalle_pedido", "pago"):
            cur.execute(f"DELETE FROM {t} WHERE id_pedido IN (SELECT id_pedido FROM x)")
        cur.execute("ALTER TABLE pedido DISABLE TRIGGER pedido_proteger_horas")
        cur.execute("DELETE FROM pedido WHERE id_pedido IN (SELECT id_pedido FROM x)")
        cur.execute("ALTER TABLE pedido ENABLE TRIGGER pedido_proteger_horas")
        cur.execute("DELETE FROM cliente WHERE id_cliente IN (SELECT id_cliente FROM x)")
        n = cur.rowcount
        # El contador de turnos vuelve al último turno real del día
        cur.execute("""UPDATE turno_contador t SET ultimo = coalesce((SELECT max(numero_turno) FROM pedido p
                       WHERE p.id_cafeteria = t.id_cafeteria AND p.fecha = t.fecha), 0)""")
        print(f"Pedidos de prueba eliminados: {n} (contador de turnos restablecido)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pedidos", type=int, default=150)
    ap.add_argument("--simultaneos", type=int, default=10)
    ap.add_argument("--conservar", action="store_true", help="no borrar los pedidos de prueba")
    a = ap.parse_args()

    print(f"Enviando {a.pedidos} pedidos, {a.simultaneos} al mismo tiempo...")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.simultaneos) as ex:
        res = list(ex.map(un_pedido, range(a.pedidos)))
    total = time.perf_counter() - t0
    tiempos = sorted(t for t, ok in res if ok)
    fallos = sum(1 for _, ok in res if not ok)
    if tiempos:
        p95 = tiempos[max(0, int(len(tiempos) * 0.95) - 1)]
        print(f"\nPedidos correctos : {len(tiempos)} de {a.pedidos}  (fallidos: {fallos})")
        print(f"Tiempo total      : {total:.1f} s  →  equivale a {len(tiempos) / total * 3600:,.0f} pedidos por hora")
        print(f"Tiempo por pedido : promedio {statistics.mean(tiempos):.2f} s · mediana {statistics.median(tiempos):.2f} s · "
              f"p95 {p95:.2f} s · máximo {tiempos[-1]:.2f} s")
        cumple = p95 <= 3 and fallos == 0
        print(f"RNF-01 (≤ 3 s con 150 pedidos/hora): {'CUMPLE' if cumple else 'NO CUMPLE'}")
    else:
        print("Ningún pedido fue aceptado. ¿Están activos los flujos de n8n?")
    if not a.conservar:
        limpiar()
