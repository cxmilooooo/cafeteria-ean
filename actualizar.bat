@echo off
rem Actualiza una instalacion existente a la ultima version de GitHub SIN borrar datos.
cd /d "%~dp0"
echo [..] Bajando la ultima version...
git pull --ff-only || ( echo [X] git pull fallo. Revisa con: git status & pause & exit /b 1 )
findstr /b "CLAVE_PERSONAL=" .env >nul 2>nul || powershell -NoProfile -Command "$l = -join ((48..57)+(97..122) | Get-Random -Count 8 | %% {[char]$_}); Add-Content .env ('CLAVE_PERSONAL=' + $l)"
echo [..] Reconstruyendo y levantando...
docker compose up -d --build --force-recreate || ( pause & exit /b 1 )
echo [..] Esperando la base de datos...
:espera_db
docker compose exec -T postgres pg_isready -U cafeteria -d cafeteria >nul 2>nul || ( timeout /t 2 /nobreak >nul & goto espera_db )
echo [..] Actualizando funciones de la base de datos (los datos se conservan)...
docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria < db\02_funciones.sql || ( pause & exit /b 1 )
for %%m in (db\migraciones\*.sql) do (
  docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U cafeteria -d cafeteria < "%%m" || ( echo [X] Fallo la migracion %%m & pause & exit /b 1 )
)
echo [..] Recargando los flujos de n8n...
docker compose exec -T n8n sh -c "n8n import:workflow --separate --input=/init/workflows && for f in /init/workflows/*.json; do id=$(grep -m1 '\"id\"' $f | sed 's/.*\"id\": *\"\([^\"]*\)\".*/\1/'); n8n publish:workflow --id=$id; done" >nul
docker compose restart n8n >nul
call configurar_red.bat >nul
echo [..] Esperando a n8n...
:espera_n8n
timeout /t 3 /nobreak >nul
curl -sf "http://localhost:8080/api/catalogo?id_cafeteria=1" >nul 2>nul || goto espera_n8n
echo [OK] Actualizado. Recarga las paginas abiertas (caja, cocina, dashboard).
for /f "tokens=1,* delims==" %%a in ('findstr /b "CLAVE_PERSONAL=" .env') do echo      Pantallas del personal: http://localhost:8080/personal/  usuario: personal  clave: %%b
pause
