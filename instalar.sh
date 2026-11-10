#!/bin/sh
# Cafetería EAN · instalación automática (Linux / macOS)
cd "$(dirname "$0")" || exit 1

command -v docker >/dev/null 2>&1 || { echo "[X] Instala Docker: https://www.docker.com/products/docker-desktop/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "[X] Docker no está encendido. Ábrelo y vuelve a ejecutar este script."; exit 1; }

primera_vez=no
if [ ! -f .env ]; then
  cp .env.example .env
  # Clave del dashboard aleatoria (no la publicada en GitHub)
  clave=$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 10)
  sed -i.bak "s|^DASHBOARD_PASSWORD=.*|DASHBOARD_PASSWORD=${clave}|" .env && rm -f .env.bak
  primera_vez=si
  echo "[OK] Archivo .env creado con una clave nueva para el dashboard."
fi

# Dirección de la red para el código QR (los celulares abren el pedido con ella)
./configurar_red.sh || echo "[!] Se sigue con localhost: el QR solo funcionará en este computador."

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

# Primera instalación: PIN aleatorios para el personal, guardados en credenciales.txt
if [ "$primera_vez" = si ] || [ ! -f credenciales.txt ]; then
  echo "[..] Generando PIN del personal..."
  ./scripts/generar_credenciales.sh >/dev/null && echo "[OK] Claves y PIN guardados en credenciales.txt (no se suben a GitHub)."
fi

# El sistema queda vacío, listo para usar. Datos de demostración (opcional):
#   docker compose exec dashboard python generar_datos_demo.py --dias 15

cat <<'FIN'

LISTO
  Portal (cliente, caja, cocina, turnos): http://localhost:8080
  Desde los celulares (misma red Wi-Fi):   ver URL_PUBLICA en .env · QR en Dashboard → Menú y código QR
  Dashboard de KPI:                        http://localhost:8501
  n8n (editar los flujos):                 http://localhost:5679
  Claves y PIN del personal: abre el archivo credenciales.txt de esta carpeta
  Para apagar: docker compose down
FIN
if command -v open >/dev/null 2>&1; then open http://localhost:8080; open http://localhost:8501
elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8080; xdg-open http://localhost:8501; fi
