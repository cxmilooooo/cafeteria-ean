"""Genera los flujos de n8n (JSON importable). Uso: python scripts/generar_flujos_n8n.py n8n/workflows"""
import json, sys, uuid, pathlib

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CRED = {"postgres": {"id": "CafPostgres00001", "name": "Postgres Cafetería"}}
ERR_ID = "CafeEAN00Errores"
_ns = uuid.UUID("5b0e0e2a-3a59-4c1a-9a55-cafe0000ea11")


def uid(*k):
    return str(uuid.uuid5(_ns, "/".join(map(str, k))))


class WF:
    def __init__(self, wid, name, nota):
        self.wid, self.name = wid, name
        self.nodes, self.conn = [], {}
        self.sticky(nota, [-400, -260], 380, 300)

    def add(self, name, type_, ver, params, pos, **extra):
        n = {"id": uid(self.wid, name), "name": name, "type": type_, "typeVersion": ver,
             "position": pos, "parameters": params}
        n.update(extra)
        self.nodes.append(n)
        return name

    def sticky(self, text, pos, w=340, h=200, color=7):
        self.add(f"Nota {len(self.nodes)}", "n8n-nodes-base.stickyNote", 1,
                 {"content": text, "width": w, "height": h, "color": color}, pos)

    def link(self, a, b, out=0):
        lst = self.conn.setdefault(a, {"main": []})["main"]
        while len(lst) <= out:
            lst.append([])
        lst[out].append({"node": b, "type": "main", "index": 0})

    # ---- nodos de uso frecuente ----
    def webhook(self, name, method, path, pos):
        return self.add(name, "n8n-nodes-base.webhook", 2.1,
                        {"httpMethod": method, "path": path, "responseMode": "responseNode",
                         "options": {"allowedOrigins": "*"}},
                        pos, webhookId=uid(self.wid, "hook", path))

    def pg(self, name, query, pos, param=None, **extra):
        opts = {"queryReplacement": param} if param else {}
        return self.add(name, "n8n-nodes-base.postgres", 2.8,
                        {"operation": "executeQuery", "query": query, "options": opts},
                        pos, credentials=CRED, **extra)

    def respond(self, name, body, code, pos):
        return self.add(name, "n8n-nodes-base.respondToWebhook", 1.4,
                        {"respondWith": "json", "responseBody": body,
                         "options": {"responseCode": code}}, pos)

    def iff(self, name, left, pos, op=("boolean", "true"), right=None):
        cond = {"id": uid(self.wid, name, "c"), "leftValue": left,
                "operator": {"type": op[0], "operation": op[1]}}
        if right is None:
            cond["rightValue"] = ""
            cond["operator"]["singleValue"] = True
        else:
            cond["rightValue"] = right
        return self.add(name, "n8n-nodes-base.if", 2.2,
                        {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                    "typeValidation": "loose", "version": 2},
                                        "conditions": [cond], "combinator": "and"},
                         "looseTypeValidation": True, "options": {}}, pos)

    def code(self, name, js, pos):
        return self.add(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)

    def telegram(self, prefix, pos, chat_env="TELEGRAM_CHAT_ID"):
        """IF ¿Telegram configurado? -> HTTP sendMessage. Espera $json.mensaje."""
        x, y = pos
        i = self.iff(f"{prefix}: ¿Telegram configurado?", "={{ !!$env.TELEGRAM_BOT_TOKEN }}", [x, y])
        chat = f"$env.{chat_env} || $env.TELEGRAM_CHAT_ID"
        h = self.add(f"{prefix}: Enviar Telegram", "n8n-nodes-base.httpRequest", 4.2,
                     {"method": "POST",
                      "url": "=https://api.telegram.org/bot{{ $env.TELEGRAM_BOT_TOKEN }}/sendMessage",
                      "sendBody": True, "specifyBody": "json",
                      "jsonBody": "={{ JSON.stringify({ chat_id: " + chat + ", text: $json.mensaje }) }}",
                      "options": {}},
                     [x + 240, y - 80], onError="continueRegularOutput")
        self.link(i, h, 0)
        return i

    def save(self, fname, active=True):
        wf = {"id": self.wid, "name": self.name, "nodes": self.nodes, "connections": self.conn,
              "active": False, "settings": {"executionOrder": "v1", "timezone": "America/Bogota",
                                            "callerPolicy": "workflowsFromSameOwner",
                                            **({"errorWorkflow": ERR_ID} if self.wid != ERR_ID else {})},
              "pinData": {}, "tags": [], "meta": {"templateCredsSetupCompleted": True}}
        (OUT / fname).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")


OK = "={{ $json.r.ok }}"
R = "={{ $json.r }}"
CODE_R = "={{ $json.r.ok ? 200 : 409 }}"

# ---------------------------------------------------------------- 00 errores
w = WF(ERR_ID, "00 · Manejo de errores (continuidad)",
       "## 00 · Manejo de errores\nSe ejecuta cuando **cualquier** flujo de la cafetería falla.\n\n"
       "Registra la alerta en la base de datos y, si Telegram está configurado, avisa al líder de turno "
       "para activar la contingencia (comandas foliadas).\n\n**Matriz de riesgos 1 y 2 · Continuidad 11**")
t = w.add("Error en un flujo", "n8n-nodes-base.errorTrigger", 1, {}, [0, 0])
c = w.code("Armar mensaje de error", """const e = $input.first().json;
const flujo = e.workflow?.name ?? 'desconocido';
const nodo = e.execution?.lastNodeExecuted ?? '?';
const msg = e.execution?.error?.message ?? e.trigger?.error?.message ?? 'sin detalle';
return [{ json: {
  flujo, nodo, error: msg,
  mensaje: `⚠️ Cafetería EAN: falló el flujo "${flujo}" en el nodo "${nodo}".\\n${msg}\\nSi el sistema no responde en 30 min (RTO), activar comandas foliadas.`
}}];""", [220, 0])
p = w.pg("Registrar alerta", "INSERT INTO alerta (tipo, mensaje) VALUES ('Error de flujo', left($1, 400)) RETURNING id_alerta",
         [460, 100], "={{ $json.mensaje }}", onError="continueRegularOutput")
tg = w.telegram("Error", [460, -100])
w.link(t, c); w.link(c, p); w.link(c, tg)
w.save("00_manejo_errores.json")

# ---------------------------------------------------------------- 01 catálogo
w = WF("CafeEAN01Catalog", "01 · Catálogo y menú (RF-03)",
       "## 01 · Catálogo y menú\n`GET /webhook/catalogo?id_cafeteria=1`\n\nDevuelve cafeterías, el menú y (solo para las pantallas del personal) la lista de personal activo, con "
       "precio y **disponibilidad actualizada** (RF-03). Lo usan las páginas de cliente, caja y cocina.")
h = w.webhook("GET /catalogo", "GET", "catalogo", [0, 0])
p = w.pg("Leer catálogo", "SELECT api_catalogo($1::jsonb) AS r", [240, 0],
         "={{ JSON.stringify({ ...$json.query, incluir_personal: $json.headers['x-personal'] === 'si' }) }}")
r = w.respond("Responder catálogo", R, 200, [480, 0])
w.link(h, p); w.link(p, r)
w.save("01_catalogo.json")

# ---------------------------------------------------------------- 02 pedido
w = WF("CafeEAN02Pedidos", "02 · Recepción de pedido y turno (RF-01, 02, 05, 10)",
       "## 02 · Recepción de pedido\n`POST /webhook/pedido`\n\n1. Valida la estructura (canal, cantidades, nombre).\n"
       "2. La base de datos revisa disponibilidad, asigna el **turno único del día** (RN-03), guarda PEDIDO + DETALLE "
       "con `hora_llegada_fila` y `hora_toma_pedido` (RF-10) y registra la NOTIFICACION *Pedido recibido*.\n"
       "3. Responde el turno al celular o a la caja. El pedido queda *Registrado* esperando la autorización del cajero.\n\nEl pedido se registra **una sola vez** (fricción 3).")
h = w.webhook("POST /pedido", "POST", "pedido", [0, 0])
v = w.code("Validar y normalizar", """const b = $input.first().json.body ?? {};
const errores = [];
const canal = b.canal === 'Caja' ? 'Caja' : (b.canal === 'QR' ? 'QR' : null);
if (!canal) errores.push('canal debe ser QR o Caja');
const caf = parseInt(b.id_cafeteria, 10);
if (!caf) errores.push('id_cafeteria es obligatorio');
const items = Array.isArray(b.items) ? b.items : [];
if (items.length === 0) errores.push('el pedido debe tener al menos un producto');
const limpios = items.map(i => ({
  id_producto: parseInt(i.id_producto, 10),
  cantidad: parseInt(i.cantidad, 10),
  observaciones: (i.observaciones ?? '').toString().slice(0, 150)
}));
if (limpios.some(i => !i.id_producto || !(i.cantidad >= 1 && i.cantidad <= 20)))
  errores.push('cada producto necesita id y cantidad entre 1 y 20');
const cli = b.cliente ?? {};
// El nombre es obligatorio en ambos canales: se muestra en la pantalla de turnos cuando el pedido está listo
if (!(cli.nombre ?? '').trim()) errores.push('el nombre del cliente es obligatorio (se muestra en la pantalla al estar listo)');
if (canal === 'Caja' && (!b.id_cajero || !b.pin)) errores.push('un pedido en caja necesita el cajero que lo registra y su PIN');
// Ley 1581: los datos de contacto solo viajan si hay autorización explícita
const autoriza = cli.autoriza_datos === true;
const pedido = {
  id_cafeteria: caf, canal, id_cajero: b.id_cajero ?? null, pin: canal === 'Caja' ? (b.pin ?? null) : null,
  segundos_espera: Math.max(0, Math.min(1800, parseInt(b.segundos_espera, 10) || 0)),
  cliente: { nombre: (cli.nombre ?? '').trim(), tipo_cliente: cli.tipo_cliente ?? 'Otro',
             autoriza_datos: autoriza,
             celular: autoriza ? (cli.celular ?? null) : null,
             correo_institucional: autoriza ? (cli.correo_institucional ?? null) : null },
  items: limpios
};
return [{ json: { valido: errores.length === 0, errores, pedido } }];""", [220, 0])
i1 = w.iff("¿Datos válidos?", "={{ $json.valido }}", [440, 0])
p = w.pg("Crear pedido y asignar turno", "SELECT api_crear_pedido($1::jsonb) AS r", [660, -80],
         "={{ JSON.stringify($json.pedido) }}")
bad = w.respond("Responder 400 (datos inválidos)",
                "={{ { ok: false, codigo: 'VALIDACION', mensaje: $json.errores.join('; ') } }}", 400, [660, 140])
i2 = w.iff("¿Pedido creado?", OK, [880, -80])
ok = w.respond("Responder turno", R, 201, [1100, -160])
ko = w.respond("Responder 409 (agotado u otro)", R, 409, [1100, 20])
w.link(h, v); w.link(v, i1); w.link(i1, p, 0); w.link(i1, bad, 1); w.link(p, i2)
w.link(i2, ok, 0); w.link(i2, ko, 1)
w.save("02_recepcion_pedido.json")

# ---------------------------------------------------------------- 03 autorización en caja
w = WF("CafeEAN03PagoCoc", "03 · Autorización del pedido en caja y envío a cocina (RF-04, 06 · RN-01)",
       "## 03 · Autorización en caja\n`POST /webhook/autorizar`\n\nEl **cajero autoriza** el pedido (hecho por QR o en caja) "
       "cuando el cliente paga en el mostrador. Se valida **con su PIN** que quien autoriza sea un cajero o el coordinador "
       "activo de esa cafetería (RNF-05) y que el pedido siga *Registrado*.\n\nAl autorizarse se crea el PAGO con su factura, el pedido pasa a "
       "*Pagado* y **entra a la cola de cocina** en orden de autorización (RN-01, RN-02). Sin autorización en 10 minutos, "
       "el flujo 06 lo cancela (RN-04).")
h = w.webhook("POST /autorizar", "POST", "autorizar", [0, 0])
v = w.code("Validar solicitud del cajero", """const b = $input.first().json.body ?? {};
const errores = [];
if (!(b.id_pedido ?? '').toString().trim()) errores.push('falta el número de pedido');
if (!parseInt(b.id_cajero, 10) || !b.pin) errores.push('falta el cajero que autoriza o su PIN');
return [{ json: { valido: errores.length === 0, errores,
  autorizacion: { id_pedido: (b.id_pedido ?? '').toString().trim().toUpperCase(),
                  id_cajero: parseInt(b.id_cajero, 10) || null, pin: (b.pin ?? '').toString(),
                  medio_pago: b.medio_pago ?? 'Efectivo' } } }];""", [220, 0])
i0 = w.iff("¿Solicitud completa?", "={{ $json.valido }}", [440, 0])
p = w.pg("Autorizar pedido (RN-01)", "SELECT api_autorizar_pedido($1::jsonb) AS r", [660, -80],
         "={{ JSON.stringify($json.autorizacion) }}")
bad = w.respond("Responder 400", "={{ { ok: false, codigo: 'VALIDACION', mensaje: $json.errores.join('; ') } }}", 400, [660, 140])
i1 = w.iff("¿Autorizado?", OK, [880, -80])
ok = w.respond("Responder autorización y factura", R, 200, [1100, -160])
ko = w.respond("Responder 409 (no autorizado)", R, 409, [1100, 20])
w.link(h, v); w.link(v, i0); w.link(i0, p, 0); w.link(i0, bad, 1); w.link(p, i1); w.link(i1, ok, 0); w.link(i1, ko, 1)
w.save("03_autorizacion_caja.json")

# ---------------------------------------------------------------- 04 consultas
w = WF("CafeEAN04Consult", "04 · Consultas en vivo: cola, caja, seguimiento y turnos (RF-06, 08)",
       "## 04 · Consultas en vivo\n- `GET /cola?id_cafeteria=1` → cola de cocina en orden de pago (RN-02)\n"
       "- `GET /pendientes?id_cafeteria=1` → pedidos que esperan autorización del cajero\n"
       "- `GET /seguimiento?id_pedido=P00001` → estado para el celular del cliente\n"
       "- `GET /turnos?id_cafeteria=1` → pantalla de turnos: número de turno, pedido y **nombre** de quien pidió\n"
       "- `GET /pedidos-hoy?id_cafeteria=1` → pedidos del día para elegir uno al registrar un reclamo", )
for k, (path, fn) in enumerate([("cola", "api_cola"), ("pendientes", "api_pendientes_pago"),
                                ("seguimiento", "api_seguimiento"), ("turnos", "api_turnos"),
                                ("pedidos-hoy", "api_pedidos_hoy")]):
    y = k * 180
    h = w.webhook(f"GET /{path}", "GET", path, [0, y])
    p = w.pg(f"Consultar {path}", f"SELECT {fn}($1::jsonb) AS r", [240, y], "={{ JSON.stringify($json.query) }}")
    r = w.respond(f"Responder {path}", R, "={{ $json.r.ok ? 200 : 404 }}" if path == "seguimiento" else 200, [480, y])
    w.link(h, p); w.link(p, r)
w.save("04_consultas_en_vivo.json")

# ---------------------------------------------------------------- 05 estados
w = WF("CafeEAN05Estados", "05 · Estados del pedido y aviso de Listo (RF-07, 08, 09)",
       "## 05 · Estados y aviso *Listo*\n`POST /webhook/estado`\n\nCocina/barra mueve el pedido: **Pagado → En preparación → Listo → Entregado**.\n"
       "- *Listo*: guarda `hora_listo`, registra la NOTIFICACION y muestra en la pantalla el **número y el nombre** de quien pidió; además lo publica en el canal de Telegram "
       "de la cafetería (opcional, sin datos personales).\n- *Entregado*: exige el número de turno (RF-09) y guarda si se entregó correcto.\n"
       "- Si una entrega se marca incorrecta, avisa al coordinador.")
h = w.webhook("POST /estado", "POST", "estado", [0, 0])
p = w.pg("Cambiar estado", "SELECT api_cambiar_estado($1::jsonb) AS r", [220, 0], "={{ JSON.stringify($json.body) }}")
i1 = w.iff("¿Cambio válido?", OK, [440, 0])
ok = w.respond("Responder estado", R, 200, [660, -200])
ko = w.respond("Responder 409", R, 409, [660, 200])
sw = w.add("¿Qué estado?", "n8n-nodes-base.switch", 3.2, {"rules": {"values": [
    {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                    "conditions": [{"id": uid("sw", 1), "leftValue": "={{ $json.r.estado }}", "rightValue": "Listo",
                                    "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"},
     "renameOutput": True, "outputKey": "Listo"},
    {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                    "conditions": [{"id": uid("sw", 2), "leftValue": "={{ $json.r.entregado_correcto }}", "rightValue": False,
                                    "operator": {"type": "boolean", "operation": "false", "singleValue": True}}],
                    "combinator": "and"},
     "renameOutput": True, "outputKey": "Entrega incorrecta"}]},
    "options": {"fallbackOutput": "none"}}, [660, 0])
m1 = w.code("Mensaje: turno listo", """const r = $input.first().json.r;
// Canal público: solo el número de turno (el nombre se ve únicamente en la pantalla del punto de entrega)
return [{ json: { mensaje: `✅ Turno ${r.numero_turno} listo. Acércate al punto de entrega.` } }];""", [880, -60])
m2 = w.code("Mensaje: entrega incorrecta", """const r = $input.first().json.r;
return [{ json: { mensaje: `❗ Entrega incorrecta registrada: pedido ${r.id_pedido} (turno ${r.numero_turno}). Revisar reclamo.` } }];""", [880, 120])
t1 = w.telegram("Listo", [1100, -60], chat_env="TELEGRAM_CANAL_TURNOS")
t2 = w.telegram("Incorrecta", [1100, 120])
w.link(h, p); w.link(p, i1); w.link(i1, ok, 0); w.link(i1, sw, 0); w.link(i1, ko, 1)
w.link(sw, m1, 0); w.link(sw, m2, 1); w.link(m1, t1); w.link(m2, t2)
w.save("05_estados_y_aviso.json")

# ---------------------------------------------------------------- 06 abandono
w = WF("CafeEAN06Abandon", "06 · Abandono automático de turnos sin pago (RN-04 · RF-11)",
       "## 06 · Abandono automático\nCorre **cada minuto**.\n\nTodo turno *Registrado* que no se paga en **10 minutos (20 en hora pico)** se cancela, "
       "queda como *Abandonado* con `abandono_fila = true` y se anota en el historial. Alimenta el **KPI 5**. También cierra como *No recogido* los pedidos de días anteriores que quedaron abiertos.")
s = w.add("Cada minuto", "n8n-nodes-base.scheduleTrigger", 1.2,
          {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}}, [0, 0])
p = w.pg("Cancelar turnos vencidos", "SELECT fn_marcar_abandonos(10) AS r", [240, 0])
w.link(s, p)
w.save("06_abandono_automatico.json")

# ---------------------------------------------------------------- 07 alerta espera
w = WF("CafeEAN07Alerta3", "07 · Alerta de espera en hora pico (RF-14 · KPI 4)",
       "## 07 · Alerta de espera\nCorre **cada 5 minutos**. Solo actúa dentro de las franjas pico (RN-05: 10–11 y 12–14).\n\n"
       "Si la espera promedio de los últimos 30 min supera **3 minutos**, registra la alerta y avisa al coordinador para que "
       "una persona se dedique solo a cobrar mientras la otra prepara y entrega. No repite la alerta en 15 minutos.")
s = w.add("Cada 5 minutos", "n8n-nodes-base.scheduleTrigger", 1.2,
          {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, [0, 0])
p = w.pg("Medir espera por cafetería", "SELECT * FROM fn_evaluar_espera(3)", [240, 0])
a = w.pg("Registrar alerta", "INSERT INTO alerta (id_cafeteria, tipo, mensaje, valor) VALUES ($1, 'Espera alta', $2, $3) RETURNING *",
         [480, 0],
         "={{ [ $json.id_cafeteria, `Espera promedio de ${$json.espera_promedio} min en ${$json.franja} (${$json.pedidos} pedidos, ${$json.pendientes_cocina} en cocina). Meta ≤ 3 min: que una persona se dedique solo a cobrar hasta que baje la fila.`, $json.espera_promedio ] }}")
m = w.code("Mensaje al coordinador", """return $input.all().map(i => ({ json: {
  mensaje: `⏱️ ${i.json.mensaje}`
}}));""", [720, 0])
tg = w.telegram("Espera", [960, 0])
w.link(s, p); w.link(p, a); w.link(a, m); w.link(m, tg)
w.save("07_alerta_espera.json")

# ---------------------------------------------------------------- 08 reclamos
w = WF("CafeEAN08Reclamo", "08 · Reclamos (RF-12 · KPI 2)",
       "## 08 · Reclamos\n`POST /webhook/reclamo`\n\nRegistra el reclamo ligado al pedido (tipo, descripción, quién lo atendió y solución). "
       "Si es de entrega (incompleto, equivocado, a otra persona) marca el pedido como **no entregado correctamente** (KPI 2) "
       "y avisa al coordinador.")
h = w.webhook("POST /reclamo", "POST", "reclamo", [0, 0])
p = w.pg("Registrar reclamo", "SELECT api_reclamo($1::jsonb) AS r", [220, 0], "={{ JSON.stringify($json.body) }}")
i1 = w.iff("¿Registrado?", OK, [440, 0])
ok = w.respond("Responder reclamo", R, 201, [660, -120])
ko = w.respond("Responder 409", R, 409, [660, 140])
m = w.code("Mensaje al coordinador", """const r = $input.first().json.r;
return [{ json: { mensaje: `📝 Reclamo #${r.id_reclamo} (${r.tipo_reclamo}) del pedido ${r.id_pedido}: ${r.descripcion}` } }];""", [880, 0])
tg = w.telegram("Reclamo", [1100, 0])
w.link(h, p); w.link(p, i1); w.link(i1, ok, 0); w.link(i1, m, 0); w.link(i1, ko, 1); w.link(m, tg)
w.save("08_reclamos.json")

# ---------------------------------------------------------------- 09 cierre diario
w = WF("CafeEAN09CierreK", "09 · Cierre diario de KPI (RF-13 · RNF-09)",
       "## 09 · Cierre diario de KPI\nCorre de lunes a sábado a las **9:00 p. m.** y cada 15 min durante el día (RNF-09).\n\n"
       "Calcula los 5 KPI por cafetería, los guarda en `kpi_diario` (los lee el dashboard de Python) y envía el resumen "
       "con semáforo contra las metas al coordinador.")
s1 = w.add("Cada 15 minutos (7 a. m.–9 p. m.)", "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 7-20 * * 1-6"}]}}, [0, -100])
s2 = w.add("Cierre 9:00 p. m.", "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"field": "cronExpression", "expression": "0 21 * * 1-6"}]}}, [0, 100])
p1 = w.pg("Recalcular KPI del día", "SELECT fn_cierre_diario() AS r", [240, -100])
p2 = w.pg("Calcular KPI del día", "SELECT fn_cierre_diario() AS r", [240, 100])
m = w.code("Comparar contra metas", """const r = $input.first().json.r;
const metas = [
  ['kpi1', 'Tiempo de atención', v => v <= 5, ' min', '≤ 5'],
  ['kpi2', 'Entregas correctas', v => v >= 95, ' %', '≥ 95'],
  ['kpi3', 'Pedidos/hora pico', v => v >= 80, '', '≥ 80'],
  ['kpi4', 'Espera en fila', v => v <= 3, ' min', '≤ 3'],
  ['kpi5', 'Abandono de fila', v => v <= 2, ' %', '≤ 2'],
];
const bloques = (r.cafeterias ?? []).map(c => {
  const lineas = metas.map(([k, n, ok, u, meta]) => c[k] == null
    ? `⚪ ${n}: sin datos (meta ${meta})`
    : `${ok(Number(c[k])) ? '🟢' : '🔴'} ${n}: ${c[k]}${u} (meta ${meta})`);
  return `🏪 ${c.cafeteria} · ${c.clientes} clientes · $${Number(c.ventas).toLocaleString('es-CO')}\\n` + lineas.join('\\n');
});
return [{ json: { mensaje: `📊 Cierre del ${r.fecha}\\n\\n` + (bloques.join('\\n\\n') || 'Sin pedidos hoy.') } }];""", [480, 100])
tg = w.telegram("Cierre", [720, 100])
w.link(s1, p1); w.link(s2, p2); w.link(p2, m); w.link(m, tg)
w.save("09_cierre_diario_kpi.json")

# ---------------------------------------------------------------- 10 monitoreo
w = WF("CafeEAN10Monitor", "10 · Monitoreo y respaldo (continuidad · RPO 5 min)",
       "## 10 · Monitoreo y continuidad\nCorre **cada 5 minutos**.\n\nComprueba que la base de datos responde y que el último respaldo "
       "automático tiene menos de 10 minutos (RPO 5 min). Si algo falla avisa al líder de turno. Si la base de datos no responde, "
       "el flujo falla y lo atrapa **00 · Manejo de errores**.")
s = w.add("Cada 5 minutos", "n8n-nodes-base.scheduleTrigger", 1.2,
          {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, [0, 0])
p = w.pg("Revisar base de datos y respaldo", "SELECT fn_monitoreo() AS r", [240, 0])
i = w.iff("¿Respaldo atrasado?", "={{ $json.r.respaldo }}", [480, 0], op=("string", "equals"), right="ALERTA")
a = w.pg("Registrar alerta de respaldo",
         "INSERT INTO alerta (tipo, mensaje) SELECT 'Respaldo', $1 WHERE NOT EXISTS (SELECT 1 FROM alerta WHERE tipo = 'Respaldo' AND fecha_hora > ahora_local() - interval '30 minutes') RETURNING id_alerta, mensaje",
         [720, -60], "={{ 'Respaldo atrasado: último hace ' + ($json.r.minutos_ultimo_respaldo ?? '—') + ' min (RPO 5 min)' }}")
m = w.code("Mensaje de respaldo", """return [{ json: { mensaje: '💾 ' + $input.first().json.mensaje } }];""", [960, -60])
tg = w.telegram("Respaldo", [1200, -60])
w.link(s, p); w.link(p, i); w.link(i, a, 0); w.link(a, m); w.link(m, tg)
w.save("10_monitoreo_respaldo.json")

# ---------------------------------------------------------------- 11 abandono fila
w = WF("CafeEAN11Abandon", "11 · Cliente sale de la fila sin pedir (RF-11 · KPI 5)",
       "## 11 · Salida de la fila\n`POST /webhook/abandono-fila`\n\nEl cajero registra con un botón al cliente que se va sin pedir. "
       "Queda como pedido *Abandonado* con su hora de llegada. Alimenta el **KPI 5**.")
h = w.webhook("POST /abandono-fila", "POST", "abandono-fila", [0, 0])
p = w.pg("Registrar abandono", "SELECT api_abandono_fila($1::jsonb) AS r", [240, 0], "={{ JSON.stringify($json.body) }}")
r = w.respond("Responder abandono", R, CODE_R, [480, 0])
w.link(h, p); w.link(p, r)
w.save("11_abandono_fila.json")

# ---------------------------------------------------------------- 12 ingreso
w = WF("CafeEAN12Ingreso", "12 · Ingreso del personal con PIN (RNF-05)",
       "## 12 · Ingreso del personal\n`POST /webhook/ingreso`\n\nCaja y cocina piden **empleado + PIN** antes de trabajar. "
       "La base de datos compara el PIN cifrado (bcrypt), revisa el rol y la cafetería y **bloquea 5 minutos** tras 5 intentos "
       "fallidos. Cada acción posterior (registrar, autorizar, cambiar estado, reclamo) vuelve a validar el PIN, así que "
       "nadie puede autorizar pedidos llamando al webhook directamente.")
h = w.webhook("POST /ingreso", "POST", "ingreso", [0, 0])
p = w.pg("Verificar PIN y rol", "SELECT api_ingreso($1::jsonb) AS r", [240, 0], "={{ JSON.stringify($json.body) }}")
r = w.respond("Responder ingreso", R, "={{ $json.r.ok ? 200 : 401 }}", [480, 0])
w.link(h, p); w.link(p, r)
w.save("12_ingreso_personal.json")

print("ok", len(list(OUT.glob('*.json'))), "flujos")
