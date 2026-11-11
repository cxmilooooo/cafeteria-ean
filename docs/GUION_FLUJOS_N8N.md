# Guion detallado · Cómo funciona cada flujo de n8n

Este guion explica **cada flujo y cada nodo** de n8n, en el orden en que ocurre un pedido. Para cada uno dice
**qué mostrar en pantalla** y **qué decir**. Úsenlo con n8n abierto en `http://localhost:5679`.

---

## Antes de empezar: cómo leer un flujo de n8n

> "En n8n cada flujo es un diagrama que se lee **de izquierda a derecha**. Cada cuadro es un **nodo**: una acción.
> Las líneas muestran por dónde pasa la información. Hay cuatro tipos de nodos que vamos a ver todo el tiempo:"

| Nodo | Ícono | Qué hace |
|---|---|---|
| **Webhook** | rayo | Es la "puerta": una dirección web que recibe lo que envía el celular o la caja. |
| **Schedule Trigger** | reloj | Arranca el flujo solo, cada cierto tiempo (cada minuto, cada 5 minutos, a las 9 p. m.). |
| **Code / IF / Switch** | `{}` / rombo | Validan los datos y **deciden** por qué camino seguir (sí / no). |
| **Postgres** | elefante | Lee o guarda en la base de datos. |
| **Respond to Webhook** | flecha de vuelta | Le **contesta** a la pantalla que hizo la petición. |
| **HTTP Request** | globo | Envía un mensaje a otro servicio (aquí, a Telegram, si está configurado). |

> "Además, cada flujo tiene una **nota amarilla** que dice qué hace y qué requisito del documento cumple:
> RF son requisitos funcionales, RN reglas de negocio y KPI los indicadores."

**Idea clave para decir:**
> "n8n es el cerebro: las pantallas nunca tocan la base de datos directamente. Siempre le piden las cosas a n8n,
> n8n valida, aplica las reglas y guarda. Las operaciones críticas — dar el turno, cobrar, verificar el PIN — las
> hace una **función de la base de datos** que n8n llama, para que dos personas al mismo tiempo nunca generen un
> turno repetido o un cobro doble."

---

## Parte 1 · Flujos que se activan cuando alguien hace algo (webhooks)

### Flujo 01 · Catálogo y menú (RF-03)
**Dirección:** `GET /webhook/catalogo` · **Lo usan:** el celular del cliente, la caja y el Mostrador.

**Nodos:** `GET /catalogo` → `Leer catálogo` (Postgres) → `Responder catálogo`

> "Cuando el cliente abre el QR, lo primero que pasa es este flujo. El **webhook** recibe la petición; el nodo
> **Postgres** llama a la función `api_catalogo`, que trae los productos con su precio y si están **disponibles**;
> y el último nodo le **responde** al celular con el menú. Si el coordinador marca un producto como agotado, aquí
> deja de aparecer. Por seguridad, la lista de empleados solo se envía a las pantallas del personal, nunca al
> cliente."

### Flujo 02 · Recepción de pedido y turno (RF-01, RF-02, RF-05, RF-10 · RN-03)
**Dirección:** `POST /webhook/pedido` · **Lo usan:** el celular (canal QR) y la caja (canal Caja).

**Nodos:**
1. `POST /pedido` — llega el pedido: productos, cantidades, observaciones y nombre del cliente.
2. `Validar y normalizar` (Code) — revisa que tenga al menos un producto, que las cantidades estén entre 1 y 20,
   que tenga nombre y, si es de caja, que traiga el cajero y su PIN. **Ley 1581:** si el cliente no autorizó, borra
   su celular y correo antes de guardar.
3. `¿Datos válidos?` (IF) — si algo falta, va por abajo a `Responder 400` con el error.
4. `Crear pedido y asignar turno` (Postgres) — llama a `api_crear_pedido`, que en una sola operación:
   revisa existencias, asigna el **turno único del día** (RN-03), guarda el PEDIDO y su DETALLE con las horas
   (RF-10) y registra la notificación "Pedido recibido".
5. `¿Pedido creado?` (IF) — si se agotó un producto, responde `409` explicando cuál.
6. `Responder turno` — le devuelve al celular su número de turno.

> "Este es el corazón de la recepción. Fíjense que el pedido se registra **una sola vez**: eso elimina la
> fricción de duplicidad del AS-IS, donde se decía en caja y otra vez en cocina. El pedido queda *Registrado*,
> esperando que la cajera lo cobre."

### Flujo 12 · Ingreso del personal con PIN (RNF-05)
**Dirección:** `POST /webhook/ingreso` · **Lo usan:** Mostrador, caja y cocina al entrar.

**Nodos:** `POST /ingreso` → `Verificar PIN y rol` (Postgres) → `Responder ingreso`

> "Antes de trabajar, cada persona entra con su **PIN**. La base compara el PIN **cifrado con bcrypt**, revisa el
> **rol** (cajero, cocina o coordinador) y la cafetería. Si alguien se equivoca 5 veces seguidas, el usuario se
> **bloquea 5 minutos**. Y no es solo al entrar: cada acción posterior vuelve a validar el PIN, así nadie puede
> saltarse la pantalla llamando a n8n directamente."

### Flujo 03 · Autorización del pedido en caja (RF-04, RF-06 · RN-01)
**Dirección:** `POST /webhook/autorizar` · **Lo usa:** la cajera al tocar Cobrar → Efectivo/Tarjeta/Transferencia.

**Nodos:**
1. `POST /autorizar` — llega el número de pedido, el medio de pago, la cajera y su PIN.
2. `Validar solicitud del cajero` (Code) — revisa que vengan el pedido, la cajera y el PIN.
3. `¿Solicitud completa?` (IF) — si falta algo, `Responder 400`.
4. `Autorizar pedido (RN-01)` (Postgres) — llama a `api_autorizar_pedido`, que verifica el PIN y el rol, revisa
   que el pedido siga *Registrado*, crea el **PAGO** con su comprobante (TK-…), pasa el pedido a *Pagado* y deja
   en el historial **quién** lo autorizó.
5. `¿Autorizado?` (IF) — si ya estaba cobrado o el PIN no sirve, `Responder 409`.
6. `Responder autorización y factura` — la caja muestra "Turno 12 · Ana → a preparar".

> "Esta es nuestra regla de negocio más importante, **RN-01: solo un pedido autorizado entra a cocina**. Probamos
> 10 cobros simultáneos del mismo pedido y solo uno ganó: nunca hay doble cobro."

### Flujo 04 · Consultas en vivo (RF-06, RF-08 · RN-02)
**Direcciones:** `GET /cola`, `/pendientes`, `/seguimiento`, `/turnos`, `/pedidos-hoy`.

**Nodos:** cinco filas iguales: `Webhook` → `Consultar …` (Postgres) → `Responder …`

> "Las pantallas se mantienen al día preguntándole a n8n cada pocos segundos:
> - **cola**: la lista de cocina, en **orden de cobro** (RN-02: primero en entrar, primero en salir);
> - **pendientes**: los pedidos del QR que la caja debe cobrar;
> - **seguimiento**: el estado que ve el cliente en su celular;
> - **turnos**: lo que muestra la pantalla del televisor, con número y nombre;
> - **pedidos-hoy**: la lista para elegir un pedido al registrar un reclamo."

### Flujo 05 · Estados del pedido y aviso de "Listo" (RF-07, RF-08, RF-09)
**Dirección:** `POST /webhook/estado` · **Lo usan:** cocina y Mostrador.

**Nodos:**
1. `POST /estado` — llega el pedido, el estado nuevo, quién lo hace y su PIN.
2. `Cambiar estado` (Postgres) — llama a `api_cambiar_estado`, que solo permite el camino correcto:
   **Pagado → En preparación → Listo → Entregado** (o **Listo → No recogido** si el cliente no vino).
   - Al pasar a **Listo** guarda `hora_listo` y la notificación "Pedido listo".
   - Para **Entregado** exige el número de turno (RF-09) y guarda si la entrega fue **correcta** (KPI 2).
3. `¿Cambio válido?` (IF) — si se intenta saltar un paso, `Responder 409`.
4. `Responder estado` — la pantalla se actualiza.
5. `¿Qué estado?` (Switch) — dos caminos especiales:
   - **Listo** → `Mensaje: turno listo` → envía a Telegram "✅ Turno 12 listo" (si está configurado; sin nombres,
     por privacidad).
   - **Entrega incorrecta** → avisa al coordinador.

> "Cuando alguien toca **✓ Listo**, este flujo cambia el estado y la pantalla de turnos muestra el número y el
> nombre del cliente con un tono y un anuncio por voz. Así se acaba gritar nombres y la congestión en el mostrador."

### Flujo 08 · Reclamos (RF-12 · KPI 2)
**Dirección:** `POST /webhook/reclamo` · **Lo usa:** la caja o el Mostrador (botón ⚠️ Reclamo).

**Nodos:** `POST /reclamo` → `Registrar reclamo` (Postgres) → `¿Registrado?` → `Responder reclamo` y
`Mensaje al coordinador` → Telegram.

> "El reclamo queda ligado al pedido. Si fue un error de entrega — incompleto, equivocado o entregado a otra
> persona — el pedido se marca como **no entregado correctamente**, y eso baja el KPI 2. El coordinador lo ve en
> el dashboard y lo marca como resuelto."

### Flujo 11 · Cliente sale de la fila sin pedir (RF-11 · KPI 5)
**Dirección:** `POST /webhook/abandono-fila` · **Lo usa:** el botón 🚶 "Se fue sin pedir".

**Nodos:** `POST /abandono-fila` → `Registrar abandono` (Postgres) → `Responder abandono`

> "Registra a quien se fue antes de pedir, con la hora en que llegó. Alimenta el KPI 5, abandono de fila."

---

## Parte 2 · Flujos automáticos (nadie los dispara, corren solos con un reloj)

### Flujo 06 · Abandono automático (RN-04 · RF-11 · KPI 5)
**Cada minuto.** **Nodos:** `Cada minuto` (Schedule) → `Cancelar turnos vencidos` (Postgres)

> "Cada minuto revisa los pedidos *Registrados* que nadie cobró. Si pasaron **10 minutos — o 20 en hora pico**,
> porque la fila es más larga — los cancela como *Abandonado*. También cierra como *No recogido* los pedidos que
> quedaron abiertos de días anteriores. Así ningún pedido queda colgado."

### Flujo 07 · Alerta de espera en hora pico (RF-14 · KPI 4)
**Cada 5 minutos.** **Nodos:** `Cada 5 minutos` → `Medir espera por cafetería` (Postgres) → `Registrar alerta`
→ `Mensaje al coordinador` → Telegram.

> "Solo actúa en las franjas pico: de 10 a 11 y de 12 a 2 (RN-05). Calcula la espera promedio de los últimos 30
> minutos; si pasa de **3 minutos**, la meta del KPI 4, registra una alerta: *'que una persona se dedique solo a
> cobrar hasta que baje la fila'*. No repite la alerta en 15 minutos para no saturar."

### Flujo 09 · Cierre diario de KPI (RF-13 · RNF-09)
**Cada 15 minutos (7 a. m.–9 p. m.) y a las 9 p. m.** **Nodos:** dos relojes → `Calcular KPI del día` (Postgres)
→ `Comparar contra metas` (Code) → Telegram.

> "Calcula los **5 KPI** del día con las fórmulas del documento y los guarda en la tabla `kpi_diario`. A las 9 de
> la noche arma un resumen con semáforo — verde si cumple la meta, rojo si no — y se lo envía al coordinador."

### Flujo 10 · Monitoreo y respaldo (continuidad · RPO 5 min)
**Cada 5 minutos.** **Nodos:** `Cada 5 minutos` → `Revisar base de datos y respaldo` (Postgres) →
`¿Respaldo atrasado?` → `Registrar alerta de respaldo` → Telegram.

> "Esto viene de nuestra matriz de continuidad. Un servicio aparte hace una **copia de la base cada 5 minutos**
> — ese es nuestro RPO. Este flujo verifica que la base responda y que la última copia tenga menos de 10 minutos;
> si no, alerta. Si la base no responde, el flujo falla y lo atrapa el flujo 00."

### Flujo 00 · Manejo de errores (continuidad)
**Se activa cuando cualquier otro flujo falla.** **Nodos:** `Error en un flujo` → `Armar mensaje de error` (Code)
→ `Registrar alerta` y Telegram.

> "Es el plan de contingencia automatizado: si algo falla, registra qué flujo y qué nodo fallaron y avisa al líder
> de turno. Además, las pantallas muestran un aviso rojo: *'Sin conexión, usar comandas en papel'*, que es lo que
> definimos en el documento de continuidad."

---

## Parte 3 · Recorrido de un pedido de principio a fin (para cerrar)

> "Juntemos todo con un solo pedido:"

| Momento | Qué ve la persona | Flujo | Estado en la base |
|---|---|---|---|
| Ana escanea el QR | El menú | 01 | — |
| Ana confirma | "Tu turno es el 12" | 02 | **Registrado** |
| La cajera entra | Pantalla de PIN | 12 | — |
| Aparece en "por cobrar" | Tarjeta con turno 12 | 04 | Registrado |
| La cajera cobra | "Turno 12 · Ana → a preparar" | 03 | **Pagado** |
| Cocina lo ve en la cola | Comanda con productos | 04 | Pagado |
| Cocina toca ✓ Listo | Pantalla: "12 · Ana" + voz | 05 | **Listo** |
| Se entrega | "Turno 12 entregado" | 05 | **Entregado** |
| Si nadie cobra en 10–20 min | — | 06 | Abandonado |
| Si Ana no vino | Botón "No vino" | 05 | No recogido |
| En la noche | Resumen de KPI | 09 | kpi_diario |

> "Cada paso deja su hora registrada. Con esas horas calculamos los KPI: tiempo de atención, espera en fila,
> pedidos por hora, entregas correctas y abandono. Eso es lo que vemos en el dashboard."

---

## Datos para responder preguntas técnicas

- **¿Dónde se guardan los datos?** En PostgreSQL, con las 10 tablas del modelo entidad-relación (PEDIDO,
  DETALLE_PEDIDO, CLIENTE, EMPLEADO, PRODUCTO, PAGO, NOTIFICACION, RECLAMO, CAFETERIA, FRANJA_HORARIA) más tablas de
  apoyo: historial de estados, alertas, KPI diarios y registro de respaldos.
- **¿Por qué parte de la lógica está en la base y no en n8n?** Porque asignar turnos y cobrar deben ser
  **atómicos**: si dos personas lo hacen al mismo tiempo, la base garantiza que no se repita el turno ni el cobro.
  n8n orquesta; la base protege los datos.
- **¿Cómo se comunica la pantalla con n8n?** Por direcciones web (webhooks). nginx hace de puerta: los clientes
  solo pueden usar catálogo, pedido y seguimiento; todo lo demás exige la clave del local.
- **¿Se puede cambiar una regla, por ejemplo los 10 minutos?** Sí: está en la función `fn_marcar_abandonos` que
  llama el flujo 06, y el horario de las alertas está en el nodo de reloj de cada flujo.
- **¿Qué pasa con el rendimiento?** Medido con una prueba de carga: **0,47 s por pedido** en promedio con 150
  pedidos en 7 segundos; la meta (RNF-01) era menos de 3 s.
