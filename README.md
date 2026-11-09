# Cafetería EAN · Gestión de pedidos con n8n

Implementación del sistema de información propuesto en el proyecto integrador
(*Gestión de pedidos en la cafetería de la Universidad EAN*). Todo pasa por **n8n**:

1. El cliente pide desde el celular (QR) o el cajero registra el pedido en caja → recibe un **turno**.
2. El **cajero autoriza** el pedido al cobrarlo en el mostrador → solo entonces pasa a cocina.
3. Cocina/barra prepara en orden de autorización y marca *Listo*.
4. La **pantalla de turnos muestra el número del turno y el nombre de quien pidió** (y el celular del cliente avisa).
5. Se entrega verificando el turno y el coordinador ve los 5 KPI en un dashboard hecho en Python.

Todo es gratuito y corre en Docker con un solo comando.

```
 Celular (QR) ─┐                       ┌─► Postgres (modelo E-R del proyecto) ─► Dashboard Python (Streamlit + Plotly)
 Caja ─────────┼─► Páginas web ─► n8n ─┤                                     └─► Power BI (opcional, puerto 5433)
 Cocina/barra ─┤   (nginx)      (13    ├─► Pantalla de turnos / celular del cliente
 Pantalla TV ──┘                flujos)└─► Telegram (opcional): alertas al coordinador y canal de turnos
```

## 1. Requisitos

- Docker Desktop (Windows/Mac) o Docker Engine (Linux) con `docker compose`.
- Puertos libres: **5679** (n8n), **8080** (páginas), **8501** (dashboard) y **5433** (Postgres).

> Este proyecto trae **su propio n8n** con los flujos ya importados, en el puerto **5679** para no chocar
> con otro n8n que ya tengan en el 5678. Si algún puerto está ocupado, cámbienlo en el archivo `.env`.
>
> Si una instalación falló por un puerto ocupado, después de cambiarlo recreen los contenedores con
> `docker compose up -d --force-recreate` (si no, n8n puede quedar sin red y no encontrar la base de datos).

## 2. Instalación (5 minutos)

**La forma más fácil:** con Docker Desktop abierto, hagan doble clic en **`instalar.bat`** (Windows) o
ejecuten `./instalar.sh` (Mac/Linux). El instalador levanta todo, configura la IP para el QR, espera a
que n8n active los flujos y abre las páginas en el navegador. **El sistema queda vacío, listo para usar**
(solo con el menú y el personal).

Si prefieren hacerlo a mano:

```bash
cd cafeteria-ean
cp .env.example .env          # en Windows PowerShell: copy .env.example .env
docker compose up -d --build
```

La primera vez tarda un poco: descarga las imágenes, crea la base de datos con el modelo
del proyecto, importa la credencial de Postgres y los 13 flujos en n8n y los publica.

Cuando termine:

| Qué | Dirección |
|---|---|
| Portal con todas las páginas | http://localhost:8080 |
| Pedido del cliente (lo que abre el QR) | http://localhost:8080/pedido.html?cafeteria=1 |
| Caja (registrar y **autorizar** pedidos) | http://localhost:8080/caja.html |
| Cocina y barra | http://localhost:8080/cocina.html |
| Pantalla de turnos (TV: número + nombre) | http://localhost:8080/turnos.html |
| **Dashboard de KPI (Python)** | http://localhost:8501 |
| n8n (ver y editar los flujos) | http://localhost:5679 |

En n8n, la primera vez se pide crear un usuario dueño (correo y contraseña locales, no se
envían a ningún lado). Los flujos ya aparecen importados y activos.

### Usuarios y contraseñas de prueba

Caja y cocina piden **empleado + PIN** (RNF-05). El dashboard pide la contraseña del coordinador.

| Quién | Rol | Cafetería | PIN |
|---|---|---|---|
| Laura Gómez | Cajero | Principal | 1111 |
| Andrés Rojas | Cocina/barra | Principal | 2222 |
| Paola Martínez | Cocina/barra | Principal | 3333 |
| Carlos Ruiz | Coordinador (puede caja y cocina) | Principal | 9999 |
| Diana Torres | Cajero | Torre 2 | 4444 |
| Miguel Herrera | Cocina/barra | Torre 2 | 5555 |
| Sofía Castro | Coordinador | Torre 2 | 8888 |
| Dashboard | Coordinador | — | `coordinador2026` (variable `DASHBOARD_PASSWORD` en `.env`) |

Los PIN se guardan cifrados (bcrypt). Tras 5 intentos fallidos el usuario queda bloqueado 5 minutos.
Para cambiarlos: `docker compose exec postgres psql -U cafeteria -c "UPDATE empleado SET pin_hash = crypt('NUEVO', gen_salt('bf')) WHERE nombre = 'Laura Gómez'"`.

### Empezar desde cero (borrar datos de prueba)

Si hicieron pruebas y quieren dejarlo limpio para el uso real:

```bash
./limpiar_datos.sh          # Windows: limpiar_datos.bat
```

Borra pedidos, clientes, pagos, facturas, reclamos, alertas, KPI y turnos. **Conserva el menú, las
cafeterías y el personal.** El siguiente pedido vuelve a ser el turno 1.

### Datos de demostración (opcional, solo para mostrar el dashboard)

```bash
docker compose exec dashboard python generar_datos_demo.py --dias 15
```

Genera 15 días hábiles **simulados**. No los usen junto con datos reales; se quitan con
`./limpiar_datos.sh`.

### Probar con celulares de verdad

El instalador detecta solo la IP del computador en el Wi-Fi y la pone en `URL_PUBLICA` (`.env`).
Si cambian de red (la IP cambia), ejecuten:

```bash
./configurar_red.sh        # Windows: configurar_red.bat
```

Después, en el dashboard → **Menú y código QR**, descarguen e impriman el QR de cada cafetería.
Los celulares deben estar en la **misma red Wi-Fi** que el computador. Si no abre: algunas redes
(como las de la universidad) bloquean la conexión entre dispositivos; en ese caso usen el punto de
acceso (hotspot) de un celular y conecten ahí el computador y los demás celulares.

## 3. Los 13 flujos de n8n

| # | Flujo | Disparador | Requerimientos |
|---|---|---|---|
| 00 | Manejo de errores | Cuando cualquier flujo falla | Continuidad (alerta al líder de turno) |
| 01 | Catálogo y menú | `GET /webhook/catalogo` | RF-03 |
| 02 | Recepción de pedido y turno | `POST /webhook/pedido` | RF-01, RF-02, RF-05, RF-10 · RN-03 |
| 03 | **Autorización del pedido en caja** y envío a cocina | `POST /webhook/autorizar` | RF-04, RF-06 · RN-01 |
| 04 | Consultas en vivo: cola, por autorizar, seguimiento, pantalla de turnos | `GET` | RF-06, RF-08 · RN-02 |
| 05 | Estados del pedido y aviso de *Listo* | `POST /webhook/estado` | RF-07, RF-08, RF-09 |
| 06 | Abandono automático de turnos sin pago | Cada minuto | RN-04 · RF-11 · KPI 5 |
| 07 | Alerta de espera en hora pico (> 3 min) | Cada 5 min | RF-14 · KPI 4 · riesgo 2 |
| 08 | Reclamos | `POST /webhook/reclamo` | RF-12 · KPI 2 |
| 09 | Cierre diario de KPI | Cada 15 min y a las 9 p. m. | RF-13 · RNF-09 |
| 10 | Monitoreo y respaldo | Cada 5 min | RPO 5 min · continuidad |
| 11 | Cliente sale de la fila sin pedir | `POST /webhook/abandono-fila` | RF-11 · KPI 5 |
| 12 | Ingreso del personal con PIN | `POST /webhook/ingreso` | RNF-05 |

Cada flujo tiene una nota adentro que explica qué hace y qué requisito cumple, para mostrarlo
en la sustentación. Las operaciones que deben ser atómicas (asignar turno, cobrar, cambiar
estado) están en funciones de Postgres (`db/02_funciones.sql`) que n8n llama: así dos pedidos
simultáneos nunca reciben el mismo turno.

### Reglas de negocio y controles implementados

- **RN-01** solo un pedido **autorizado por el cajero** entra a la cola de cocina. Solo puede autorizar un
  cajero o el coordinador activo de esa cafetería (lo valida la base de datos), y queda registrado quién lo hizo.
- **RN-02** la cola va en orden de autorización (primero en entrar, primero en salir).
- **RN-03** turno único por día y cafetería · **RN-04** turno sin autorizar en 10 min = abandono.
- **RN-05** franjas pico 10–11 y 12–14 (tabla `franja_horaria`).
- **RF-08** cuando el pedido está *Listo*, la pantalla muestra el **número de turno, el número de pedido y el nombre**
  de quien pidió. Por eso el nombre es obligatorio en ambos canales: basta con el nombre con el que se le llama.
- **RF-09** para entregar hay que digitar el turno que muestra el cliente.
- **RNF-06 / Ley 1581**: sin autorización explícita no se guardan celular ni correo (lo impide
  la base de datos con una restricción `CHECK`).
- **RNF-07**: las horas registradas no se pueden modificar (trigger) y cada cambio de estado
  queda en `historial_estado` con fecha, hora y usuario.
- **RNF-05**: cada acción del personal (registrar en caja, autorizar, cambiar estado, reclamo, abandono) viaja con
  el empleado y su PIN, y la base de datos lo vuelve a validar junto con el rol y la cafetería. Llamar los
  webhooks directamente sin un PIN válido no sirve. Solo el coordinador entra al dashboard.
- **RNF-01**: medido con `prueba_carga.py` (ver abajo): **0,47 s por pedido en promedio y 0,60 s en el p95**,
  con 150 pedidos enviados en 7 segundos, 10 a la vez (la meta era ≤ 3 s con 150 pedidos **por hora**).
- **RNF-08 / RPO 5 min**: el servicio `respaldo` copia la base cada 5 minutos en `./respaldos`
  y el flujo 10 alerta si una copia se atrasa.

## 4. Dashboard en Python (plantilla estandarizada)

Hecho con **Streamlit + Plotly** (ambos libres y gratuitos). Páginas:

1. **Resumen de KPI**: los 5 KPI con meta, semáforo y comparación contra la línea base, y la evolución diaria.
2. **Operación en vivo**: estado de los pedidos de hoy y alertas de n8n (se actualiza sola).
3. **Franjas, canales y productos**: QR contra caja, espera por franja y productos más pedidos.
4. **Demanda esperada**: analítica que estima qué preparar por franja pico, con datos agregados
   (sin datos personales y sin cambiar el orden FIFO, como pide la sección de ética).
5. **Reclamos, alertas y continuidad**: reclamos, alertas y estado de los respaldos.
6. **Menú y código QR**: marcar productos agotados (RF-15) y descargar los QR.

**La plantilla** está en `dashboard/plantilla/`:

- `tema.py` tiene los colores, la paleta (validada para daltonismo), las **metas de los KPI** y
  el estilo de los gráficos. Si cambian una meta aquí, cambia en todo el tablero.
- `componentes.py` trae piezas listas: `encabezado`, `filtros` (fecha, franja y cafetería),
  `fila_kpis`, `tarjeta_dato` y `grafico` (con su tabla de datos debajo).
- `datos.py` hace las consultas y calcula los KPI con las fórmulas del documento.

Para agregar una página nueva, copien `dashboard/paginas/_plantilla_pagina.py` y regístrenla en
`dashboard/app.py`. Si cambian código del dashboard: `docker compose up -d --build dashboard`.

**Power BI (opcional):** pueden conectar su archivo `.pbix` a la misma base de datos:
*Obtener datos → PostgreSQL*, servidor `localhost:5433`, base `cafeteria`, usuario `cafeteria`,
contraseña la de `.env`. La vista `v_pedidos` y la tabla `kpi_diario` ya traen todo listo.

## 5. Avisos por Telegram (opcional y gratis)

Sin configurar nada, el sistema funciona igual: el cliente ve el aviso en su celular y en la
pantalla de turnos. Para recibir además alertas en Telegram:

1. En Telegram hablen con **@BotFather** → `/newbot` → copien el token.
2. Escríbanle algo al bot y abran `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver su `chat.id`.
3. En `.env`: `TELEGRAM_BOT_TOKEN=...` y `TELEGRAM_CHAT_ID=...` (coordinador). Opcional:
   `TELEGRAM_CANAL_TURNOS=@su_canal` para publicar "Turno 23 listo" en un canal público de la
   cafetería (no usa datos personales).
4. `docker compose up -d`.

## 6. Comandos útiles

Prueba de carga (RNF-01). Envía pedidos reales por el mismo camino del celular y al final los borra:

```bash
docker compose exec dashboard python prueba_carga.py --pedidos 150 --simultaneos 10
```

```bash
docker compose ps                     # estado de los servicios
docker compose logs -f n8n            # ver lo que hace n8n
docker compose down                   # apagar (los datos se conservan)
docker compose down -v                # apagar y BORRAR todos los datos
./scripts/reimportar_flujos.sh        # volver a cargar los flujos desde n8n/workflows
```

Restaurar un respaldo:

```bash
gunzip -c respaldos/cafeteria_AAAAMMDD_HHMM.sql.gz | docker compose exec -T postgres psql -U cafeteria -d cafeteria
```

## 7. Estructura

```
db/                 esquema (modelo E-R), funciones que llama n8n y datos base (menú, personal, franjas)
n8n/workflows/      los 13 flujos en JSON (también se pueden importar a mano en otro n8n)
n8n/credenciales/   plantilla de la credencial de Postgres (la contraseña sale de .env)
web/                páginas de cliente, caja, cocina y turnos (HTML + JS, sin frameworks)
dashboard/          dashboard en Python con la plantilla estandarizada
scripts/            respaldo automático, reimportar flujos y el generador de los JSON de n8n
```

## 8. Alcance y limitaciones (para decirlo en la sustentación)

- **No hay pasarela de pago en línea, a propósito.** El pago se hace en caja y el cajero autoriza el
  pedido; el sistema registra el medio de pago (efectivo, tarjeta o transferencia) y genera el número
  de factura.
- **El PIN es un control básico, adecuado para el alcance del proyecto.** La sesión dura mientras la
  pestaña esté abierta, y los PIN quedan visibles en el historial de ejecuciones de n8n, que solo ve su
  administrador. En producción se usaría HTTPS y un inicio de sesión institucional.
- **El editor de n8n y Postgres solo se abren desde el PC donde corre Docker** (por seguridad). Las páginas
  (8080) y el dashboard (8501) sí se abren desde otros equipos de la red.
- **El aviso personal por SMS/WhatsApp no está incluido** porque cuesta dinero. Se reemplazó por
  el aviso en el celular del cliente, la pantalla de turnos y un canal de Telegram opcional.
- **Los datos de demostración son simulados** y así deben presentarse; los KPI reales salen de
  usar el sistema.
- **El nombre se muestra en una pantalla pública.** Por privacidad (Ley 1581 y la sección de ética),
  se sugiere pedir solo el nombre con el que se llama a la persona (ej. "Juan P."), no el nombre completo.
