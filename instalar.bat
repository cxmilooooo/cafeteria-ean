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

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo  [OK] Archivo .env creado.
)

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

echo  [..] Cargando datos de demostracion (si ya existen, se omite)...
docker compose exec -T dashboard python generar_datos_demo.py --dias 15

echo.
echo  ==============================================
echo   LISTO. Se abriran las paginas en el navegador.
echo  ==============================================
echo   Portal (cliente, caja, cocina, turnos): http://localhost:8080
echo   Dashboard de KPI:                        http://localhost:8501   (clave: coordinador2026)
echo   n8n (editar los flujos):                 http://localhost:5679
echo   PIN caja: Laura 1111  ^|  PIN cocina: Andres 2222
echo.
echo   Para apagar:  docker compose down
echo.
start "" http://localhost:8080
start "" http://localhost:8501
pause
