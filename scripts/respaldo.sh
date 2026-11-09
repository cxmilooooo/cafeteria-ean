#!/bin/sh
# Respaldo automático de la base de datos cada 5 minutos (RPO = 5 min).
# Guarda los archivos en ./respaldos y conserva las últimas 24 horas.
# Cada copia queda registrada en la tabla respaldo_log, que vigila el flujo 10 de n8n.
while true; do
  archivo="/respaldos/cafeteria_$(date +%Y%m%d_%H%M).sql.gz"
  if pg_dump --no-owner | gzip > "$archivo"; then
    bytes=$(stat -c %s "$archivo")
    psql -qc "INSERT INTO respaldo_log (archivo, bytes) VALUES ('$(basename "$archivo")', $bytes)"
    echo "Respaldo listo: $archivo ($bytes bytes)"
  else
    echo "ERROR: falló el respaldo $archivo"
  fi
  find /respaldos -name 'cafeteria_*.sql.gz' -mmin +1440 -exec rm -f {} \;
  sleep 300
done
