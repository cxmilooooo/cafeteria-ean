#!/bin/sh
# Respaldo automático de la base de datos cada 5 minutos (RPO = 5 min).
# Guarda los archivos en ./respaldos y conserva las últimas 24 horas.
# Solo registra la copia (tabla respaldo_log, que vigila el flujo 10) si pg_dump terminó bien.
while true; do
  archivo="/respaldos/cafeteria_$(date +%Y%m%d_%H%M).sql.gz"
  tmp="$archivo.tmp"
  if pg_dump --no-owner --clean --if-exists > /tmp/respaldo.sql && [ -s /tmp/respaldo.sql ]; then
    gzip -c /tmp/respaldo.sql > "$tmp" && mv "$tmp" "$archivo"
    bytes=$(stat -c %s "$archivo")
    psql -qc "INSERT INTO respaldo_log (archivo, bytes) VALUES ('$(basename "$archivo")', $bytes)"
    echo "Respaldo listo: $archivo ($bytes bytes)"
  else
    echo "ERROR: falló el respaldo (no se guardó ningún archivo)"
  fi
  rm -f /tmp/respaldo.sql "$tmp"
  find /respaldos -name 'cafeteria_*.sql.gz' -mmin +1440 -exec rm -f {} \;
  sleep 300
done
