#!/bin/sh
# Primer arranque: importa la credencial de Postgres y los 13 flujos, y los publica.
# En arranques siguientes no toca nada (para no pisar cambios hechos en la interfaz).
# Para volver a importar: borrar el archivo marcador o usar  scripts/reimportar_flujos.sh
set -e
MARCA=/home/node/.n8n/.cafeteria_importado

if [ ! -f "$MARCA" ]; then
  echo ">> Importando credencial y flujos de la Cafetería EAN..."
  sed "s|__DB_PASSWORD__|${DB_PASSWORD}|" /init/credenciales/postgres.plantilla.json > /tmp/cred.json
  n8n import:credentials --input=/tmp/cred.json
  rm -f /tmp/cred.json
  n8n import:workflow --separate --input=/init/workflows
  for f in /init/workflows/*.json; do
    id=$(grep -m1 '"id"' "$f" | sed 's/.*"id": *"\([^"]*\)".*/\1/')
    n8n publish:workflow --id="$id" || echo "No se pudo publicar $id"
  done
  touch "$MARCA"
  echo ">> Flujos importados y publicados."
fi

exec n8n start
