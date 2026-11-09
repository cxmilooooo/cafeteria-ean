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
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo  [X] No se pudo levantar. Si dice "port is already allocated", ya hay algo usando el puerto:
  echo      - Si es otro n8n en el 5678: detenlo con  docker stop NOMBRE  o cambia N8N_PORT en .env
  pause & exit /b 1
)

echo  [..] Esperando a que n8n importe y active los flujos...
:espera
timeout /t 3 /nobreak >nul
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
echo   n8n (editar los flujos):                 http://localhost:5678
echo   PIN caja: Laura 1111  ^|  PIN cocina: Andres 2222
echo.
echo   Para apagar:  docker compose down
echo.
start "" http://localhost:8080
start "" http://localhost:8501
pause
