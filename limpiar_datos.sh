#!/bin/sh
# Deja el sistema limpio para empezar a usarlo de verdad.
# BORRA: pedidos, clientes, pagos, facturas, reclamos, alertas, KPI, historial y turnos.
# CONSERVA: menú (productos y precios), cafeterías, franjas horarias y personal con sus PIN.
cd "$(dirname "$0")" || exit 1

if [ "$1" != "--si" ]; then
  printf "Esto borra TODOS los pedidos y datos de prueba (el menú y el personal se conservan).\n¿Continuar? escribe si: "
  read -r resp
  [ "$resp" = "si" ] || { echo "Cancelado."; exit 0; }
fi

docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria <<'SQL' || { echo "[X] No se pudo limpiar. ¿Está encendido el sistema? (docker compose up -d)"; exit 1; }
BEGIN;
TRUNCATE detalle_pedido, pago, notificacion, reclamo, historial_estado, pedido, cliente,
         turno_contador, alerta, kpi_diario, monitoreo, respaldo_log RESTART IDENTITY;
ALTER SEQUENCE pedido_seq RESTART WITH 1;
ALTER SEQUENCE factura_seq RESTART WITH 1;
UPDATE empleado SET intentos_fallidos = 0, bloqueado_hasta = NULL;
COMMIT;
SQL

echo "[OK] Datos de prueba eliminados. El próximo pedido será el P00001, turno 1."
echo "     Menú, cafeterías y personal intactos."
