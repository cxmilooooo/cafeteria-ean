#!/bin/sh
# Genera un PIN aleatorio de 4 dígitos para cada empleado activo y lo guarda en credenciales.txt
# (ese archivo no se sube a GitHub). Lo ejecuta el instalador la primera vez.
cd "$(dirname "$0")/.." || exit 1
clave=$(grep -E '^DASHBOARD_PASSWORD=' .env | cut -d= -f2)
{
  echo "CREDENCIALES DE LA CAFETERÍA (guárdalas y no las compartas)"
  echo "Generadas: $(date '+%Y-%m-%d %H:%M')"
  echo ""
  echo "Dashboard del coordinador (http://localhost:8501): $clave"
  echo ""
  echo "PIN del personal (cámbialos o agrega personas en Dashboard → Administración → Personal):"
  docker compose exec -T postgres psql -qtA -F ' · ' -U cafeteria -d cafeteria -c "
    WITH n AS (SELECT id_empleado, nombre, rol, lpad(floor(random() * 10000)::int::text, 4, '0') AS pin
                 FROM empleado WHERE activo),
         u AS (UPDATE empleado e SET pin_hash = crypt(n.pin, gen_salt('bf')), intentos_fallidos = 0, bloqueado_hasta = NULL
                 FROM n WHERE e.id_empleado = n.id_empleado RETURNING n.nombre, n.rol, n.pin)
    SELECT '  ' || nombre, rol, 'PIN ' || pin FROM u ORDER BY rol, nombre"
} > credenciales.txt
chmod 600 credenciales.txt
cat credenciales.txt
