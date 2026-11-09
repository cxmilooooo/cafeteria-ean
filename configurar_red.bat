@echo off
rem Detecta la IP de este PC en la red Wi-Fi/LAN y la pone en URL_PUBLICA (.env),
rem que es la direccion que codifican los codigos QR. Ejecutenlo de nuevo si cambian de red.
cd /d "%~dp0"
if not exist ".env" copy ".env.example" ".env" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress;" ^
  "if (-not $ip) { Write-Host '[X] No se encontro la IP de la red. Esta conectado al Wi-Fi?'; exit 1 }" ^
  "$env_ = Get-Content .env; $puerto = ($env_ | Where-Object { $_ -match '^WEB_PORT=' }) -replace 'WEB_PORT=',''; if (-not $puerto) { $puerto = '8080' }" ^
  "$url = 'http://' + $ip + ':' + $puerto.Trim();" ^
  "if ($env_ -match '^URL_PUBLICA=') { $env_ = $env_ -replace '^URL_PUBLICA=.*', ('URL_PUBLICA=' + $url) } else { $env_ += ('URL_PUBLICA=' + $url) }" ^
  "Set-Content -Path .env -Value $env_ -Encoding ascii; Write-Host ('[OK] URL_PUBLICA=' + $url)"
if errorlevel 1 exit /b 1
docker compose ps --status running --services 2>nul | findstr /x dashboard >nul
if not errorlevel 1 (
  docker compose up -d dashboard >nul 2>nul
  echo [OK] Dashboard actualizado: el QR ya apunta a la nueva direccion.
)
echo     Los celulares deben estar en la misma red Wi-Fi.
