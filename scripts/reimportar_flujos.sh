#!/bin/sh
# Vuelve a importar los 13 flujos desde n8n/workflows (pisa los cambios hechos en la interfaz).
set -e
cd "$(dirname "$0")/.."
docker compose exec n8n sh -c '
  n8n import:workflow --separate --input=/init/workflows &&
  for f in /init/workflows/*.json; do
    id=$(grep -m1 "\"id\"" "$f" | sed "s/.*\"id\": *\"\([^\"]*\)\".*/\1/")
    n8n publish:workflow --id="$id"
  done'
docker compose restart n8n
echo "Flujos reimportados y publicados."
