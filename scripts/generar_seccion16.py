import sys
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
D = sys.argv[1]; OUT = sys.argv[2]
doc = Document()
st = doc.styles['Normal']; st.font.name = 'Calibri'; st.font.size = Pt(11)
fig = [0]
def h(t, n=1): doc.add_heading(t, level=n)
def p(t, bold_prefix=None):
    par = doc.add_paragraph()
    if bold_prefix: par.add_run(bold_prefix).bold = True
    par.add_run(t); par.paragraph_format.space_after = Pt(6); return par
def bullets(items):
    for i in items:
        par = doc.add_paragraph(style='List Bullet')
        if isinstance(i, tuple): par.add_run(i[0]).bold = True; par.add_run(i[1])
        else: par.add_run(i)
def img(path, caption, width=16):
    fig[0] += 1
    doc.add_picture(f'{D}/{path}', width=Cm(width)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = doc.add_paragraph(); c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run(f'Figura 16.{fig[0]}. {caption}'); r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x55,0x55,0x55)
def tabla(cab, filas):
    t = doc.add_table(rows=1, cols=len(cab)); t.style = 'Light Grid Accent 1'
    for i, c in enumerate(cab): t.rows[0].cells[i].text = c
    for f in filas:
        cells = t.add_row().cells
        for i, v in enumerate(f): cells[i].text = v
    doc.add_paragraph()

h('16. Automatización con n8n', 1)
p('La automatización del proceso de gestión de pedidos se implementó con n8n, una plataforma de automatización de flujos de trabajo de código abierto que permite modelar cada proceso como un diagrama de nodos conectados. n8n actúa como el núcleo del sistema de información: recibe las acciones del cliente y del personal, aplica las reglas de negocio definidas en el documento, registra cada evento en la base de datos y genera las alertas y los indicadores. Las interfaces nunca acceden directamente a la base de datos: toda operación pasa por un flujo de n8n, lo que centraliza la lógica, garantiza la trazabilidad y facilita modificar el proceso sin reprogramar las pantallas.')
p('La solución completa está publicada en el repositorio https://github.com/cxmilooooo/cafeteria-ean y se instala en un solo computador con un único comando.')

h('16.1 Implementación con Docker', 2)
p('Todos los componentes se ejecutan como contenedores de Docker, orquestados con Docker Compose. Esto permite que el sistema se instale de la misma forma en cualquier computador (Windows, macOS o Linux), sin instalar manualmente cada programa, y que se recupere automáticamente si un servicio se reinicia (política restart: unless-stopped). El archivo docker-compose.yml define cinco servicios:')
tabla(['Servicio', 'Imagen', 'Función en el sistema', 'Puerto'], [
    ['postgres', 'postgres:16-alpine', 'Base de datos con el modelo entidad-relación del proyecto (10 tablas) y las funciones que aplican las reglas críticas.', '5433 (solo local)'],
    ['n8n', 'n8nio/n8n:2.46.7', 'Motor de automatización con los 13 flujos del proceso.', '5679 (solo local)'],
    ['web', 'nginx:alpine', 'Sirve las páginas (cliente, Mostrador, caja, cocina, turnos) y actúa como puerta de entrada segura hacia los webhooks de n8n.', '8080'],
    ['dashboard', 'Python 3.12 (Streamlit + Plotly)', 'Tablero de los 5 KPI para el coordinador y administración del menú y el personal.', '8501 (solo local)'],
    ['respaldo', 'postgres:16-alpine', 'Copia de seguridad automática de la base de datos cada 5 minutos (RPO = 5 min).', '—'],
])
img('docker_compose_yml.png', 'Archivo docker-compose.yml que define los servicios del sistema.', 14)
p('Al iniciar por primera vez, el contenedor de n8n ejecuta un script de arranque (n8n/iniciar-n8n.sh) que importa automáticamente la credencial de conexión a PostgreSQL y los 13 flujos desde archivos JSON, y los publica para que queden activos. De esta forma no es necesario configurar n8n manualmente.')
img('docker_ps.png', 'Servicios del sistema en ejecución (docker compose ps).', 16)
img('docker_logs_n8n.png', 'Registro de n8n: importación automática de la credencial y de los 13 flujos.', 14)
p('La comunicación sigue el camino: interfaz → nginx → webhook de n8n → función de PostgreSQL → respuesta. nginx separa el acceso público (el cliente solo puede consultar el menú, hacer su pedido y ver su estado) del acceso del personal, que exige una clave del local, y limita la cantidad de peticiones por equipo para evitar abusos.')
img('docker_api.png', 'Prueba del webhook del catálogo a través de nginx: n8n responde el menú en formato JSON.', 12)

h('16.2 Funcionamiento general de n8n', 2)
p('Cada flujo de n8n se lee de izquierda a derecha y está compuesto por nodos. En el sistema se usan los siguientes tipos:')
tabla(['Nodo', 'Función'], [
    ['Webhook', 'Punto de entrada: una dirección web que recibe la petición de la interfaz (por ejemplo, un pedido nuevo).'],
    ['Schedule Trigger', 'Ejecuta el flujo automáticamente cada cierto tiempo (cada minuto, cada 5 minutos o a las 9 p. m.).'],
    ['Code', 'Valida y normaliza los datos recibidos con JavaScript.'],
    ['IF / Switch', 'Decide el camino a seguir según una condición (por ejemplo, si los datos son válidos).'],
    ['Postgres', 'Ejecuta la función de base de datos que aplica la regla de negocio y guarda la información.'],
    ['Respond to Webhook', 'Devuelve la respuesta a la interfaz (por ejemplo, el número de turno).'],
    ['HTTP Request', 'Envía avisos opcionales por Telegram (sin datos personales).'],
])
p('Las operaciones que deben ser atómicas —asignar el turno, autorizar el cobro, cambiar el estado y verificar el PIN— se implementaron como funciones de PostgreSQL que n8n invoca. Así, aunque dos personas actúen al mismo tiempo, nunca se repite un turno ni se cobra dos veces un pedido. Cada flujo incluye una nota que indica qué requisito del documento cumple. Los 13 flujos se agrupan en dos tipos: los que se activan por una acción (webhooks) y los automáticos (programados).')
img('n8n_lista_flujos.png', 'Lista de los 13 flujos del sistema en n8n, publicados y activos.', 16)

h('16.3 Flujos activados por una acción', 2)
flujos = [
 ('01', 'Catálogo y menú (RF-03)', 'Recibe la solicitud del menú (GET /webhook/catalogo), consulta los productos con su precio y disponibilidad y los devuelve. Si el coordinador marca un producto como agotado, deja de mostrarse. La lista de empleados solo se envía a las pantallas del personal.'),
 ('02', 'Recepción de pedido y turno (RF-01, RF-02, RF-05, RF-10, RN-03)', 'Recibe el pedido (POST /webhook/pedido) desde el celular del cliente o desde caja. El nodo Code valida productos, cantidades y nombre, y elimina los datos de contacto si el cliente no autorizó su tratamiento (Ley 1581). El nodo IF descarta los datos inválidos; el nodo Postgres verifica existencias, asigna un turno único del día, guarda el pedido y su detalle con la hora de llegada, y el último nodo responde con el turno. El pedido se registra una sola vez, lo que elimina la fricción de duplicidad del AS-IS.'),
 ('12', 'Ingreso del personal con PIN (RNF-05)', 'Verifica el PIN del empleado, almacenado cifrado con bcrypt, junto con su rol y cafetería. Tras cinco intentos fallidos bloquea al usuario por cinco minutos. Cada acción posterior vuelve a validar el PIN.'),
 ('03', 'Autorización del pedido en caja (RF-04, RF-06, RN-01)', 'Cuando la cajera cobra, valida la solicitud, verifica el PIN y el rol, comprueba que el pedido siga en estado Registrado, crea el pago con su comprobante y pasa el pedido a Pagado, dejando registrado quién lo autorizó. Implementa la regla RN-01: solo un pedido autorizado entra a la cola de preparación.'),
 ('04', 'Consultas en vivo (RF-06, RF-08, RN-02)', 'Agrupa cinco webhooks de consulta que las pantallas usan cada pocos segundos: la cola de preparación en orden de cobro (RN-02), los pedidos por cobrar, el seguimiento del cliente, la pantalla de turnos (número y nombre) y los pedidos del día para registrar reclamos.'),
 ('05', 'Estados del pedido y aviso de Listo (RF-07, RF-08, RF-09)', 'Controla las transiciones Pagado → En preparación → Listo → Entregado (o No recogido) sin permitir saltar pasos. Al pasar a Listo registra la hora y la notificación; al entregar exige el turno y registra si la entrega fue correcta (KPI 2). Un nodo Switch envía el aviso de pedido listo y alerta al coordinador ante una entrega incorrecta.'),
 ('08', 'Reclamos (RF-12, KPI 2)', 'Registra el reclamo asociado al pedido. Si se trata de un error de entrega, marca el pedido como no entregado correctamente y notifica al coordinador, quien lo resuelve desde el dashboard.'),
 ('11', 'Cliente sale de la fila sin pedir (RF-11, KPI 5)', 'Registra al cliente que abandona la fila antes de pedir, con su hora de llegada, para el indicador de abandono.'),
]
for num, titulo, texto in flujos:
    h(f'Flujo {num} · {titulo}', 3); p(texto); img(f'flujo_{num}.png', f'Flujo {num} · {titulo.split(" (")[0]} en n8n.', 16)

h('16.4 Flujos automáticos (programados)', 2)
auto = [
 ('06', 'Abandono automático (RN-04, RF-11, KPI 5)', 'Se ejecuta cada minuto. Cancela como Abandonado los pedidos registrados que no se cobraron en 10 minutos (20 en hora pico, cuando la fila es más larga) y cierra como No recogido los pedidos abiertos de días anteriores.'),
 ('07', 'Alerta de espera en hora pico (RF-14, KPI 4)', 'Se ejecuta cada 5 minutos solo en las franjas pico (RN-05: 10–11 y 12–14). Si la espera promedio de los últimos 30 minutos supera la meta de 3 minutos, registra una alerta para que una persona se dedique solo a cobrar; no repite la alerta en 15 minutos.'),
 ('09', 'Cierre diario de KPI (RF-13, RNF-09)', 'Calcula los 5 indicadores del día con las fórmulas del documento, los guarda en la tabla kpi_diario y a las 9 p. m. genera un resumen con semáforo frente a las metas.'),
 ('10', 'Monitoreo y respaldo (continuidad)', 'Cada 5 minutos verifica que la base de datos responda y que el último respaldo tenga menos de 10 minutos, de acuerdo con el RPO definido en el plan de continuidad. Si algo falla, genera una alerta.'),
 ('00', 'Manejo de errores (continuidad)', 'Se activa cuando cualquier flujo falla: registra qué flujo y qué nodo fallaron y alerta al líder de turno para activar la contingencia con comandas en papel.'),
]
for num, titulo, texto in auto:
    h(f'Flujo {num} · {titulo}', 3); p(texto); img(f'flujo_{num}.png', f'Flujo {num} · {titulo.split(" (")[0]} en n8n.', 16)

h('16.5 Trazabilidad entre flujos, requisitos y reglas', 2)
tabla(['Requisito / regla', 'Flujo que lo implementa'], [
    ['RF-01, RF-02 Registro del pedido (QR y caja)', '02'], ['RF-03 Menú con disponibilidad', '01'],
    ['RF-04, RF-06 Cobro y envío a la cola', '03'], ['RF-05 Turno único', '02'],
    ['RF-07, RF-08, RF-09 Estados, aviso y entrega', '05, 04'], ['RF-10 Registro de horas', '02, 03, 05'],
    ['RF-11 Abandonos', '06, 11'], ['RF-12 Reclamos', '08'], ['RF-13 KPI', '09'], ['RF-14 Alerta de espera', '07'],
    ['RN-01 Solo pedidos autorizados entran a cocina', '03'], ['RN-02 Cola en orden de cobro', '04'],
    ['RN-03 Turno único por día', '02'], ['RN-04 Cancelación por falta de pago', '06'], ['RN-05 Franjas pico', '07, 09'],
    ['RNF-05 Acceso por rol con PIN', '12 y validación en 02, 03, 05, 08, 11'], ['Continuidad (RPO 5 min)', '10, 00'],
])

h('16.6 Resultados de las pruebas', 2)
bullets([
    ('Rendimiento (RNF-01): ', '150 pedidos enviados en 7 segundos se procesaron con un promedio de 0,47 s por pedido (p95 = 0,60 s), frente a una meta de 3 s.'),
    ('Concurrencia: ', '30 pedidos simultáneos recibieron 30 turnos distintos, y 10 autorizaciones simultáneas del mismo pedido generaron un solo pago.'),
    ('Reglas: ', 'no es posible saltar estados, cobrar dos veces ni entregar con un turno equivocado; los pedidos no cobrados se cancelan automáticamente.'),
    ('Seguridad: ', 'no se encontraron inyecciones SQL ni XSS; los PIN se almacenan cifrados y las acciones sin PIN válido son rechazadas.'),
    ('Recuperación: ', 'tras reiniciar Docker, los flujos vuelven a estar activos en segundos sin intervención manual.'),
])
p('En conclusión, n8n permitió convertir el BPMN TO-BE en un proceso ejecutable y medible: cada pedido se registra una sola vez, avanza por estados controlados, deja trazabilidad de sus horas y alimenta automáticamente los indicadores con los que el coordinador evalúa si se cumplen las metas del proyecto.')
doc.save(OUT); print('ok', fig[0], 'figuras')
