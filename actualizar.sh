#!/bin/sh
# Actualiza una instalación existente a la última versión de GitHub SIN borrar datos:
# baja el código, reconstruye, actualiza las funciones de la base y vuelve a cargar los flujos de n8n.
cd "$(dirname "$0")" || exit 1

echo "[..] Bajando la última versión..."
git pull --ff-only || { echo "[X] git pull falló (¿cambiaste archivos a mano?). Revisa con: git status"; exit 1; }

# Instalaciones anteriores: crear la clave del local para las pantallas del personal
if ! grep -q '^CLAVE_PERSONAL=' .env 2>/dev/null; then
  printf '\n# Clave del local para las pantallas del personal (usuario: personal)\nCLAVE_PERSONAL=%s\n' \
    "$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 8)" >> .env
  nueva_clave_local=si
fi

echo "[..] Reconstruyendo y levantando..."
docker compose up -d --build --force-recreate || exit 1

echo "[..] Esperando la base de datos..."
until docker compose exec -T postgres pg_isready -U cafeteria -d cafeteria >/dev/null 2>&1; do sleep 2; done

echo "[..] Actualizando funciones de la base de datos (los datos se conservan)..."
docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria < db/02_funciones.sql || exit 1
for m in db/migraciones/*.sql; do
  [ -f "$m" ] || continue
  docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria < "$m" || { echo "[X] Falló la migración $m"; exit 1; }
done

echo "[..] Recargando los flujos de n8n..."
./scripts/reimportar_flujos.sh >/dev/null || exit 1
./configurar_red.sh >/dev/null 2>&1

intentos=0
until curl -sf "http://localhost:8080/api/catalogo?id_cafeteria=1" >/dev/null 2>&1; do
  intentos=$((intentos + 1)); [ "$intentos" -gt 60 ] && { echo "[X] n8n no respondió. Mira: docker compose logs n8n --tail 30"; exit 1; }
  sleep 3
done
echo "[OK] Actualizado. Recarga las páginas abiertas (caja, cocina, dashboard)."
echo "     Pantallas del personal: http://localhost:8080/personal/  · usuario: personal · clave: $(grep -E '^CLAVE_PERSONAL=' .env | cut -d= -f2)"
[ "$nueva_clave_local" = si ] && echo "     (Clave del local NUEVA: anótala; también está en el archivo .env)"
