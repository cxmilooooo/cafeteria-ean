#!/bin/sh
# Detecta la IP de este computador en la red Wi-Fi/LAN y la pone en URL_PUBLICA (.env),
# que es la dirección que codifican los códigos QR para que los celulares abran el pedido.
# Ejecútenlo de nuevo cada vez que cambien de red (la IP cambia).
cd "$(dirname "$0")" || exit 1
[ -f .env ] || cp .env.example .env

ip=""
if command -v ipconfig >/dev/null 2>&1; then            # macOS
  for i in en0 en1 en2 en3; do
    ip=$(ipconfig getifaddr "$i" 2>/dev/null) && [ -n "$ip" ] && break
  done
fi
if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then   # Linux
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$ip" ]; then
  echo "[X] No se encontró la IP de la red. ¿Está conectado al Wi-Fi?"
  exit 1
fi

puerto=$(grep -E '^WEB_PORT=' .env | cut -d= -f2 | tr -d ' ')
url="http://${ip}:${puerto:-8080}"

if grep -q '^URL_PUBLICA=' .env; then
  sed -i.bak "s|^URL_PUBLICA=.*|URL_PUBLICA=${url}|" .env && rm -f .env.bak
else
  echo "URL_PUBLICA=${url}" >> .env
fi
echo "[OK] URL_PUBLICA=${url}"

# Si el sistema ya está corriendo, el dashboard toma la nueva dirección para el QR
if docker compose ps --status running --services 2>/dev/null | grep -q '^dashboard$'; then
  docker compose up -d dashboard >/dev/null 2>&1 && echo "[OK] Dashboard actualizado: el QR ya apunta a ${url}"
fi
echo "    Los celulares deben estar en la misma red Wi-Fi. Prueben abriendo ${url} desde uno."
