-- =====================================================================
--  Cafetería EAN · Gestión de pedidos
--  Esquema basado en el modelo entidad-relación del proyecto (Modelo.drawio)
--  Tablas del modelo: CAFETERIA, FRANJA_HORARIA, CLIENTE, EMPLEADO, PRODUCTO,
--  PEDIDO, DETALLE_PEDIDO, PAGO, NOTIFICACION, RECLAMO
--  Tablas de apoyo: turno_contador, historial_estado, alerta, kpi_diario,
--  respaldo_log, monitoreo
-- =====================================================================

SET client_encoding = 'UTF8';

-- Cifrado de los PIN del personal (RNF-05)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Hora local de Bogotá, sin depender de la zona horaria de la conexión
CREATE OR REPLACE FUNCTION ahora_local() RETURNS timestamp
LANGUAGE sql STABLE AS $$ SELECT timezone('America/Bogota', now()) $$;

-- ---------------------------------------------------------------------
-- Tablas del modelo entidad-relación
-- ---------------------------------------------------------------------
CREATE TABLE cafeteria (
    id_cafeteria   SERIAL PRIMARY KEY,
    nombre         VARCHAR(60)  NOT NULL,
    ubicacion      VARCHAR(100) NOT NULL
);

CREATE TABLE franja_horaria (
    id_franja      SERIAL PRIMARY KEY,
    nombre         VARCHAR(40) NOT NULL,
    hora_inicio    TIME        NOT NULL,
    hora_fin       TIME        NOT NULL,          -- exclusiva
    es_hora_pico   BOOLEAN     NOT NULL DEFAULT FALSE,
    CHECK (hora_fin > hora_inicio)
);

CREATE TABLE cliente (
    id_cliente            SERIAL PRIMARY KEY,
    nombre                VARCHAR(80) NOT NULL,
    tipo_cliente          VARCHAR(15) NOT NULL
        CHECK (tipo_cliente IN ('Estudiante','Docente','Administrativo','Otro')),
    celular               VARCHAR(15),
    correo_institucional  VARCHAR(80),
    autoriza_datos        BOOLEAN NOT NULL DEFAULT FALSE,
    -- Ley 1581 de 2012: sin autorización no se guardan datos de contacto (RNF-06)
    CHECK (autoriza_datos OR (celular IS NULL AND correo_institucional IS NULL))
);

CREATE TABLE empleado (
    id_empleado    SERIAL PRIMARY KEY,
    id_cafeteria   INT NOT NULL REFERENCES cafeteria(id_cafeteria),
    nombre         VARCHAR(80) NOT NULL,
    rol            VARCHAR(15) NOT NULL CHECK (rol IN ('Cajero','Cocina/barra','Coordinador')),
    activo         BOOLEAN NOT NULL DEFAULT TRUE,
    -- RNF-05: PIN cifrado (bcrypt). Tras 5 intentos fallidos el usuario se bloquea 5 minutos.
    pin_hash          TEXT,
    intentos_fallidos INT NOT NULL DEFAULT 0,
    bloqueado_hasta   TIMESTAMP
);

CREATE TABLE producto (
    id_producto    SERIAL PRIMARY KEY,
    nombre         VARCHAR(60) NOT NULL,
    categoria      VARCHAR(20) NOT NULL,
    precio         DECIMAL(10,2) NOT NULL CHECK (precio >= 0),
    disponible     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE SEQUENCE pedido_seq START 1;

CREATE TABLE pedido (
    id_pedido          VARCHAR(10) PRIMARY KEY
        DEFAULT ('P' || lpad(nextval('pedido_seq')::text, 5, '0')),
    id_cliente         INT REFERENCES cliente(id_cliente),
    id_cafeteria       INT NOT NULL REFERENCES cafeteria(id_cafeteria),
    id_franja          INT NOT NULL REFERENCES franja_horaria(id_franja),
    id_cajero          INT REFERENCES empleado(id_empleado),
    id_preparador      INT REFERENCES empleado(id_empleado),
    numero_turno       INT,
    canal              VARCHAR(10) NOT NULL CHECK (canal IN ('QR','Caja')),
    fecha              DATE NOT NULL,
    hora_llegada_fila  TIME NOT NULL,
    hora_toma_pedido   TIME,
    hora_listo         TIME,
    hora_entrega       TIME,
    estado             VARCHAR(15) NOT NULL DEFAULT 'Registrado'
        CHECK (estado IN ('Registrado','Pagado','En preparación','Listo','Entregado','Abandonado')),
    abandono_fila      BOOLEAN NOT NULL DEFAULT FALSE,
    entregado_correcto BOOLEAN,
    valor_total        DECIMAL(10,2) NOT NULL DEFAULT 0
);
-- RN-03: el turno es único por día y por cafetería
CREATE UNIQUE INDEX ux_pedido_turno ON pedido (id_cafeteria, fecha, numero_turno)
    WHERE numero_turno IS NOT NULL;
CREATE INDEX ix_pedido_fecha_estado ON pedido (fecha, id_cafeteria, estado);

CREATE TABLE detalle_pedido (
    id_pedido        VARCHAR(10) NOT NULL REFERENCES pedido(id_pedido) ON DELETE CASCADE,
    id_producto      INT NOT NULL REFERENCES producto(id_producto),
    cantidad         INT NOT NULL CHECK (cantidad BETWEEN 1 AND 20),
    precio_unitario  DECIMAL(10,2) NOT NULL,
    subtotal         DECIMAL(10,2) NOT NULL,
    observaciones    VARCHAR(150),
    PRIMARY KEY (id_pedido, id_producto)
);

CREATE TABLE pago (
    id_pago         SERIAL PRIMARY KEY,
    id_pedido       VARCHAR(10) NOT NULL UNIQUE REFERENCES pedido(id_pedido),
    medio_pago      VARCHAR(15) NOT NULL CHECK (medio_pago IN ('Efectivo','Tarjeta','Transferencia')),
    valor           DECIMAL(10,2) NOT NULL,
    fecha_hora      TIMESTAMP NOT NULL DEFAULT ahora_local(),
    numero_factura  VARCHAR(20) NOT NULL UNIQUE
);
CREATE SEQUENCE factura_seq START 1;

CREATE TABLE notificacion (
    id_notificacion   SERIAL PRIMARY KEY,
    id_pedido         VARCHAR(10) NOT NULL REFERENCES pedido(id_pedido),
    tipo              VARCHAR(20) NOT NULL CHECK (tipo IN ('Pedido recibido','Pedido listo')),
    canal             VARCHAR(15) NOT NULL,
    fecha_hora_envio  TIMESTAMP NOT NULL DEFAULT ahora_local(),
    enviada           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE reclamo (
    id_reclamo     SERIAL PRIMARY KEY,
    id_pedido      VARCHAR(10) NOT NULL REFERENCES pedido(id_pedido),
    id_empleado    INT NOT NULL REFERENCES empleado(id_empleado),
    tipo_reclamo   VARCHAR(30) NOT NULL
        CHECK (tipo_reclamo IN ('Pedido incompleto','Pedido equivocado','Entregado a otra persona','Demora','Otro')),
    descripcion    VARCHAR(300) NOT NULL,
    solucion       VARCHAR(300),
    fecha_hora     TIMESTAMP NOT NULL DEFAULT ahora_local(),
    estado         VARCHAR(15) NOT NULL DEFAULT 'Abierto' CHECK (estado IN ('Abierto','Resuelto'))
);

-- ---------------------------------------------------------------------
-- Tablas de apoyo (no cambian el modelo, lo complementan)
-- ---------------------------------------------------------------------
-- Contador atómico de turnos por cafetería y día (RN-03)
CREATE TABLE turno_contador (
    id_cafeteria  INT  NOT NULL REFERENCES cafeteria(id_cafeteria),
    fecha         DATE NOT NULL,
    ultimo        INT  NOT NULL,
    PRIMARY KEY (id_cafeteria, fecha)
);

-- RNF-07: cada cambio de estado queda en el historial con fecha, hora y usuario
CREATE TABLE historial_estado (
    id_historial     SERIAL PRIMARY KEY,
    id_pedido        VARCHAR(10) NOT NULL REFERENCES pedido(id_pedido),
    estado_anterior  VARCHAR(15),
    estado_nuevo     VARCHAR(15) NOT NULL,
    fecha_hora       TIMESTAMP NOT NULL DEFAULT ahora_local(),
    id_empleado      INT REFERENCES empleado(id_empleado),
    origen           VARCHAR(60) NOT NULL
);

-- RF-14 y monitoreo de continuidad
CREATE TABLE alerta (
    id_alerta     SERIAL PRIMARY KEY,
    id_cafeteria  INT REFERENCES cafeteria(id_cafeteria),
    tipo          VARCHAR(30) NOT NULL,
    mensaje       VARCHAR(400) NOT NULL,
    valor         DECIMAL(10,2),
    fecha_hora    TIMESTAMP NOT NULL DEFAULT ahora_local(),
    enviada_telegram BOOLEAN NOT NULL DEFAULT FALSE
);

-- Resultado del cierre diario que calcula n8n
CREATE TABLE kpi_diario (
    fecha                    DATE NOT NULL,
    id_cafeteria             INT  NOT NULL REFERENCES cafeteria(id_cafeteria),
    clientes_llegados        INT  NOT NULL,
    pedidos_entregados       INT  NOT NULL,
    kpi1_tiempo_atencion_min DECIMAL(6,2),
    kpi2_pct_correctos       DECIMAL(6,2),
    kpi3_pedidos_hora_pico   DECIMAL(6,2),
    kpi4_espera_fila_min     DECIMAL(6,2),
    kpi5_pct_abandono        DECIMAL(6,2),
    ventas                   DECIMAL(12,2) NOT NULL DEFAULT 0,
    calculado_en             TIMESTAMP NOT NULL DEFAULT ahora_local(),
    PRIMARY KEY (fecha, id_cafeteria)
);

-- El contenedor de respaldos registra aquí cada copia (RPO 5 min)
CREATE TABLE respaldo_log (
    id            SERIAL PRIMARY KEY,
    archivo       VARCHAR(200) NOT NULL,
    bytes         BIGINT,
    fecha_hora    TIMESTAMP NOT NULL DEFAULT ahora_local()
);

-- Latido del flujo de monitoreo
CREATE TABLE monitoreo (
    id          SERIAL PRIMARY KEY,
    componente  VARCHAR(30) NOT NULL,
    estado      VARCHAR(15) NOT NULL,
    detalle     VARCHAR(300),
    fecha_hora  TIMESTAMP NOT NULL DEFAULT ahora_local()
);

-- ---------------------------------------------------------------------
-- RNF-07: una hora registrada no se puede modificar a mano
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_proteger_horas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.hora_llegada_fila IS DISTINCT FROM NEW.hora_llegada_fila)
       OR (OLD.hora_toma_pedido IS NOT NULL AND OLD.hora_toma_pedido IS DISTINCT FROM NEW.hora_toma_pedido)
       OR (OLD.hora_listo       IS NOT NULL AND OLD.hora_listo       IS DISTINCT FROM NEW.hora_listo)
       OR (OLD.hora_entrega     IS NOT NULL AND OLD.hora_entrega     IS DISTINCT FROM NEW.hora_entrega)
       OR (OLD.fecha IS DISTINCT FROM NEW.fecha) THEN
        RAISE EXCEPTION 'RNF-07: las horas registradas del pedido % no se pueden modificar', OLD.id_pedido;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER pedido_proteger_horas BEFORE UPDATE ON pedido
FOR EACH ROW EXECUTE FUNCTION trg_proteger_horas();

-- ---------------------------------------------------------------------
-- Vista para el dashboard y los KPI
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_pedidos AS
SELECT
    p.id_pedido, p.fecha, p.id_cafeteria, c.nombre AS cafeteria,
    p.id_franja, f.nombre AS franja, f.es_hora_pico,
    p.canal, p.estado, p.numero_turno, p.abandono_fila, p.entregado_correcto,
    p.valor_total, cl.tipo_cliente,
    p.hora_llegada_fila, p.hora_toma_pedido, p.hora_listo, p.hora_entrega,
    EXTRACT(HOUR FROM p.hora_llegada_fila)::int AS hora,
    EXTRACT(EPOCH FROM (p.hora_toma_pedido - p.hora_llegada_fila)) / 60.0 AS min_espera_fila,
    EXTRACT(EPOCH FROM (p.hora_entrega     - p.hora_llegada_fila)) / 60.0 AS min_atencion,
    EXTRACT(EPOCH FROM (p.hora_listo       - pg.fecha_hora::time)) / 60.0 AS min_preparacion,
    pg.medio_pago
FROM pedido p
JOIN cafeteria c       ON c.id_cafeteria = p.id_cafeteria
JOIN franja_horaria f  ON f.id_franja    = p.id_franja
LEFT JOIN cliente cl   ON cl.id_cliente  = p.id_cliente
LEFT JOIN pago pg      ON pg.id_pedido   = p.id_pedido;
