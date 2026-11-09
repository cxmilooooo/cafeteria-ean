#!/bin/sh
# Cafetería EAN · instalación automática (Linux / macOS)
cd "$(dirname "$0")" || exit 1

command -v docker >/dev/null 2>&1 || { echo "[X] Instala Docker: https://www.docker.com/products/docker-desktop/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "[X] Docker no está encendido. Ábrelo y vuelve a ejecutar este script."; exit 1; }

[ -f .env ] || { cp .env.example .env && echo "[OK] Archivo .env creado."; }

echo "[..] Levantando el sistema (la primera vez tarda varios minutos)..."
docker compose up -d --build --force-recreate || {
  echo "[X] No se pudo levantar. Si dice 'port is already allocated', libera el puerto o cámbialo en .env."
  exit 1
}

echo "[..] Esperando a que n8n importe y active los flujos..."
intentos=0
until curl -sf "http://localhost:8080/api/catalogo?id_cafeteria=1" >/dev/null 2>&1; do
  intentos=$((intentos + 1))
  if [ "$intentos" -gt 100 ]; then   # unos 5 minutos
    echo "[X] n8n no respondió en 5 minutos. Últimas líneas de su registro:"
    docker compose logs n8n --tail 20
    echo "Prueben:  docker compose up -d --force-recreate   y vuelvan a ejecutar este script."
    exit 1
  fi
  sleep 3
done
echo "[OK] Flujos de n8n activos."

echo "[..] Cargando datos de demostración (si ya existen, se omite)..."
docker compose exec -T dashboard python generar_datos_demo.py --dias 15 || true

cat <<'FIN'

LISTO
  Portal (cliente, caja, cocina, turnos): http://localhost:8080
  Dashboard de KPI:                        http://localhost:8501   (clave: coordinador2026)
  n8n (editar los flujos):                 http://localhost:5679
  PIN caja: Laura 1111 | PIN cocina: Andrés 2222
  Para apagar: docker compose down
FIN
if command -v open >/dev/null 2>&1; then open http://localhost:8080; open http://localhost:8501
elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8080; xdg-open http://localhost:8501; fi
