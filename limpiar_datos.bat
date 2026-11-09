@echo off
rem Deja el sistema limpio para empezar a usarlo de verdad.
rem BORRA: pedidos, clientes, pagos, facturas, reclamos, alertas, KPI, historial y turnos.
rem CONSERVA: menu (productos y precios), cafeterias, franjas horarias y personal con sus PIN.
cd /d "%~dp0"
if /i not "%~1"=="--si" (
  echo Esto borra TODOS los pedidos y datos de prueba ^(el menu y el personal se conservan^).
  set /p resp="Continuar? escribe si: "
)
if /i not "%~1"=="--si" if /i not "%resp%"=="si" ( echo Cancelado. & pause & exit /b 0 )
docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria -c "BEGIN; TRUNCATE detalle_pedido, pago, notificacion, reclamo, historial_estado, pedido, cliente, turno_contador, alerta, kpi_diario, monitoreo, respaldo_log RESTART IDENTITY; ALTER SEQUENCE pedido_seq RESTART WITH 1; ALTER SEQUENCE factura_seq RESTART WITH 1; UPDATE empleado SET intentos_fallidos = 0, bloqueado_hasta = NULL; COMMIT;"
if errorlevel 1 ( echo [X] No se pudo limpiar. Esta encendido el sistema? & pause & exit /b 1 )
echo [OK] Datos de prueba eliminados. El proximo pedido sera el P00001, turno 1.
echo      Menu, cafeterias y personal intactos.
pause
