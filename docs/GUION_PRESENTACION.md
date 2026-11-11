# Guion de presentación · Sistema de pedidos Cafetería EAN con n8n

**Duración sugerida:** 12–15 minutos · **Presentan:** 2 a 4 personas
**Antes de empezar (5 min antes):**
- Docker Desktop abierto y el sistema encendido (`docker compose up -d`).
- Pestañas abiertas en el PC: Mostrador (`localhost:8080/personal/mostrador.html`), Pantalla de turnos
  (`localhost:8080/personal/turnos.html`, tocar "Activar sonido"), n8n (`localhost:5679`) y Dashboard (`localhost:8501`).
- Un celular en el mismo Wi-Fi con el QR a mano (Dashboard → Administración → Códigos QR).
- Opcional: cargar datos de demostración para que los indicadores tengan historia
  (`docker compose exec dashboard python generar_datos_demo.py --dias 15`) y quitarlos después con `./limpiar_datos.sh`.

---

## 1. El problema (1 min) — *Presentador 1*

> "En la cafetería de la universidad, en los cambios de clase y en el almuerzo, todos hacen una sola fila para
> pedir y pagar. El pedido se toma de forma verbal, se grita o se anota en papel para cocina, y el cliente no sabe
> cuándo está listo. Medimos el 13 de octubre: **7 minutos de atención promedio** y **10 personas que se fueron
> de la fila en 2 horas**. El problema no es la comida: es cómo se gestionan los pedidos."

**Mostrar:** la diapositiva del BPMN AS-IS con las fricciones (Manual, Espera, Duplicidad, Información, Trazabilidad).

---

## 2. La solución en una frase (1 min) — *Presentador 1*

> "Construimos un sistema donde el pedido se registra **una sola vez**, recibe un **turno**, pasa a cocina **solo
> cuando se cobra**, y el cliente ve en una pantalla **su número y su nombre** cuando está listo. El cerebro del
> sistema es **n8n**, que automatiza todo el proceso."

**Mostrar:** este esquema (dibujarlo en la diapositiva):

```
Celular (QR) / Mostrador ──► nginx (puerta segura) ──► n8n (13 flujos) ──► PostgreSQL (modelo E-R)
                                                          │
                                                          ├──► Pantalla de turnos (número + nombre + voz)
                                                          └──► Dashboard en Python (5 KPI)
```

> "Todo es software libre y gratuito, y corre en un solo computador con Docker."

---

## 3. Demostración en vivo del flujo completo (5 min) — *Presentador 2 maneja, Presentador 3 narra*

### Paso 1 · El cliente pide desde el celular
**Hacer:** escanear el QR, elegir 2 productos, escribir un nombre (ej. "Ana"), confirmar.
> "El cliente no instala nada: escanea el QR y pide. En ese momento, **n8n ejecuta el flujo 02, Recepción de
> pedido**: valida los datos, revisa que haya existencias, le asigna un **turno único del día** y lo guarda en la
> base como *Registrado*. El celular le muestra su turno."

### Paso 2 · La cajera cobra y autoriza
**Hacer:** en el Mostrador aparece arriba "Pedidos del QR por cobrar". Tocar **Cobrar** → **Efectivo**.
> "La cajera entró con su **PIN** (flujo 12). Al cobrar se ejecuta el **flujo 03, Autorización en caja**: verifica
> el PIN y el rol, crea el pago con su comprobante y pasa el pedido a *Pagado*. **Solo un pedido autorizado entra a
> la cola** — esa es nuestra regla de negocio RN-01. Si nadie lo cobra en 10 minutos (20 en hora pico), el
> **flujo 06** lo cancela solo y lo cuenta como abandono."

### Paso 3 · Pedido en caja en un solo paso
**Hacer:** tocar 2 productos, escribir un nombre, **Cobrar** → **Tarjeta**.
> "Quien prefiere pedir en caja también queda registrado una sola vez: se registra y se cobra en un paso.
> Así eliminamos la **duplicidad**: antes el pedido se decía en caja y otra vez en cocina."

### Paso 4 · Preparar y avisar
**Hacer:** en "Por preparar", tocar **✓ Listo** en el pedido de Ana. Mirar la pantalla de turnos y el celular.
> "Cocina trabaja en **orden de cobro** (RN-02). Al marcar Listo se ejecuta el **flujo 05**: guarda la hora, y la
> pantalla muestra **'Turno 1 · Ana'** con un tono y anuncio por voz. El celular de Ana también suena y vibra.
> Ya nadie tiene que gritar nombres ni el cliente esperar de pie en el mostrador."

### Paso 5 · Entregar
**Hacer:** en "Listos", tocar **Entregar** → **Sí, entregar**.
> "Para entregar se confirma el turno (RF-09) y se registra si la entrega fue correcta, que alimenta el KPI de
> entregas correctas. Si el cliente nunca vino, el botón **'No vino'** lo cierra."

---

## 4. Cómo funciona n8n por dentro (3 min) — *Presentador 3*

**Hacer:** abrir n8n (`localhost:5679`) y mostrar la lista de 13 flujos. Abrir el **02 · Recepción de pedido**.
> "Cada flujo tiene una nota que explica qué requisito cumple. Se lee de izquierda a derecha:
> **Webhook** — llega la petición del celular;
> **Validar** — un nodo de código revisa los datos;
> **¿Datos válidos?** — una decisión;
> **Postgres** — guarda el pedido y asigna el turno;
> **Responder** — le contesta al celular con su turno."

**Mostrar rápidamente los flujos automáticos** (no los dispara nadie):

| Flujo | Cada cuánto | Qué resuelve |
|---|---|---|
| 06 · Abandono automático | cada minuto | Cancela pedidos no cobrados (KPI 5) |
| 07 · Alerta de espera | cada 5 min en hora pico | Avisa si la espera pasa de 3 min (KPI 4) |
| 09 · Cierre diario | 9 p. m. | Calcula los 5 KPI del día |
| 10 · Monitoreo | cada 5 min | Verifica base de datos y respaldo (RPO 5 min) |
| 00 · Errores | si algo falla | Alerta para usar comandas en papel (continuidad) |

> "Las operaciones críticas — el turno único, que no se cobre dos veces, el PIN — están en funciones de la base de
> datos que n8n llama. Lo probamos: **30 pedidos al mismo tiempo recibieron 30 turnos distintos**, y **10 cobros
> simultáneos del mismo pedido generaron un solo pago**."

---

## 5. Los indicadores (2 min) — *Presentador 4*

**Hacer:** abrir el Dashboard (`localhost:8501`), página **Hoy** y luego **Indicadores**.
> "El coordinador ve los **5 KPI** del documento, con su meta y semáforo:
> 1. Tiempo de atención (meta ≤ 5 min, línea base 7)
> 2. Pedidos entregados correctamente (≥ 95 %)
> 3. Pedidos por hora en hora pico (≥ 80)
> 4. Espera en fila (≤ 3 min)
> 5. Abandono de fila (≤ 2 %)
>
> La página **Hoy** se actualiza sola y muestra el **cierre de caja** por medio de pago. En **Administración**
> el coordinador marca productos agotados, administra el personal y sus PIN, resuelve reclamos e imprime el QR.
> El dashboard está hecho en **Python con Streamlit y Plotly**, con una plantilla estandarizada."

*(Si se usan datos de demostración, decirlo: "estos son datos simulados de un piloto de 15 días".)*

---

## 6. Seguridad, ética y continuidad (1 min) — *Presentador 4*

> "Conectamos el proyecto con nuestra matriz de riesgos:
> - **Seguridad:** el personal entra con PIN cifrado y se bloquea tras 5 intentos; los clientes solo pueden pedir,
>   no ven las pantallas del personal; hay límite de pedidos por equipo contra abusos.
> - **Ley 1581:** sin autorización del cliente no se guarda su celular ni su correo.
> - **Continuidad:** respaldo automático cada 5 minutos, monitoreo de n8n y, si el sistema cae, las pantallas
>   avisan para pasar a comandas en papel.
> - **Ética en IA:** la analítica de demanda usa solo totales por franja y producto; no prioriza a ningún cliente
>   por su historial — la cola siempre es en orden de cobro."

---

## 7. Cierre (30 s) — *Presentador 1*

> "Pasamos de un proceso verbal, en papel y sin trazabilidad, a uno donde **cada pedido se registra una vez, se
> sigue en tiempo real y se mide**. n8n automatiza el flujo, la base de datos garantiza las reglas y el dashboard
> nos dice si cumplimos las metas. El sistema cumple el requisito de rendimiento con amplio margen: **0,47 segundos
> por pedido** contra una meta de 3."

---

## Preguntas frecuentes del jurado (respuestas cortas)

- **¿Por qué n8n?** Es libre, visual (se ve el proceso como diagrama, igual que el BPMN TO-BE) y permite cambiar
  reglas sin reprogramar todo.
- **¿Qué pasa si se cae el sistema?** Las pantallas avisan, se usan comandas en papel, y al volver se registra. Hay
  respaldo cada 5 minutos (RPO) y el sistema se recupera en segundos al reiniciar (RTO 30 min de la matriz).
- **¿Hay pasarela de pago?** No, a propósito: el pago es en caja y la cajera autoriza. El sistema registra el medio
  de pago y genera el comprobante.
- **¿Cuántas personas lo pueden usar?** Está pensado para 2: la pantalla **Mostrador** une cobrar, preparar y
  entregar. También hay pantallas separadas de caja y cocina.
- **¿El KPI de espera en fila es exacto?** En caja mide desde que se empieza a atender; en el QR, el tiempo que el
  cliente arma su pedido. Lo declaramos como limitación.
- **¿Dónde están los datos?** En PostgreSQL con el modelo entidad-relación del proyecto (10 tablas). Se pueden ver
  con DBeaver o conectar Power BI al puerto 5433.

## Plan B si algo falla en vivo

- Si el celular no abre el QR (Wi-Fi de la universidad bloquea dispositivos): usar el hotspot de un celular, o
  hacer el pedido del cliente desde una pestaña del mismo PC (`localhost:8080`).
- Si no suena la pantalla: tocar **🔔 Probar** y subir el volumen.
- Tener capturas en `docs/capturas/` por si la demo no arranca.
