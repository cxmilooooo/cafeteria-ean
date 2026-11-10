@echo off
chcp 65001 >nul
title Cafeteria EAN - Instalador
cd /d "%~dp0"
echo.
echo  ==============================================
echo   Cafeteria EAN - instalacion automatica
echo  ==============================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo  [X] No se encontro Docker. Instala Docker Desktop desde
  echo      https://www.docker.com/products/docker-desktop/ y vuelve a ejecutar este archivo.
  pause & exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo  [X] Docker esta instalado pero no esta encendido.
  echo      Abre Docker Desktop, espera a que diga "Engine running" y vuelve a ejecutar este archivo.
  pause & exit /b 1
)

set primera_vez=no
if not exist ".env" (
  copy ".env.example" ".env" >nul
  powershell -NoProfile -Command "$c = -join ((48..57)+(97..122) | Get-Random -Count 10 | %% {[char]$_}); (Get-Content .env) -replace '^DASHBOARD_PASSWORD=.*', ('DASHBOARD_PASSWORD=' + $c) | Set-Content .env -Encoding ascii"
  set primera_vez=si
  echo  [OK] Archivo .env creado con una clave nueva para el dashboard.
)

rem Direccion de la red para el codigo QR
call configurar_red.bat

echo  [..] Levantando el sistema (la primera vez tarda varios minutos)...
docker compose up -d --build --force-recreate
if errorlevel 1 (
  echo.
  echo  [X] No se pudo levantar. Si dice "port is already allocated", ya hay algo usando el puerto:
  echo      - Si es otro programa en ese puerto: cambia el puerto en el archivo .env
  pause & exit /b 1
)

echo  [..] Esperando a que n8n importe y active los flujos...
set /a intentos=0
:espera
timeout /t 3 /nobreak >nul
set /a intentos+=1
if %intentos% GTR 100 (
  echo  [X] n8n no respondio en 5 minutos. Ultimas lineas de su registro:
  docker compose logs n8n --tail 20
  echo  Prueba:  docker compose up -d --force-recreate   y vuelve a ejecutar este archivo.
  pause & exit /b 1
)
curl -sf "http://localhost:8080/api/catalogo?id_cafeteria=1" >nul 2>nul
if errorlevel 1 goto espera
echo  [OK] Flujos de n8n activos.

rem Primera instalacion: PIN aleatorios para el personal, guardados en credenciales.txt
if "%primera_vez%"=="si" goto credenciales
if not exist credenciales.txt goto credenciales
goto fin_credenciales
:credenciales
for /f "tokens=1,* delims==" %%a in ('findstr /b "DASHBOARD_PASSWORD=" .env') do set clave=%%b
> credenciales.txt echo CREDENCIALES DE LA CAFETERIA (guardalas y no las compartas)
>> credenciales.txt echo Dashboard del coordinador (http://localhost:8501): %clave%
>> credenciales.txt echo PIN del personal (cambialos en Dashboard - Administracion - Personal):
docker compose exec -T postgres psql -qtA -F " - " -U cafeteria -d cafeteria -c "WITH n AS (SELECT id_empleado, nombre, rol, lpad(floor(random() * 10000)::int::text, 4, '0') AS pin FROM empleado WHERE activo), u AS (UPDATE empleado e SET pin_hash = crypt(n.pin, gen_salt('bf')), intentos_fallidos = 0, bloqueado_hasta = NULL FROM n WHERE e.id_empleado = n.id_empleado RETURNING n.nombre, n.rol, n.pin) SELECT nombre, rol, 'PIN ' || pin FROM u ORDER BY rol, nombre" >> credenciales.txt
echo  [OK] Claves y PIN guardados en credenciales.txt
:fin_credenciales

rem El sistema queda vacio, listo para usar. Datos de demostracion (opcional):
rem   docker compose exec dashboard python generar_datos_demo.py --dias 15

echo.
echo  ==============================================
echo   LISTO. Se abriran las paginas en el navegador.
echo  ==============================================
echo   Portal (cliente, caja, cocina, turnos): http://localhost:8080
echo   Dashboard de KPI:                        http://localhost:8501
echo   n8n (editar los flujos):                 http://localhost:5679
echo   Claves y PIN del personal: abre el archivo credenciales.txt de esta carpeta
start "" credenciales.txt
echo.
echo   Para apagar:  docker compose down
echo.
start "" http://localhost:8080
start "" http://localhost:8501
pause
