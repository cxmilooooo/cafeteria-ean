-- =====================================================================
--  Funciones que n8n llama desde el nodo Postgres.
--  Cada una recibe un JSON y responde un JSON {ok: true|false, ...}.
--  Las operaciones que deben ser atómicas (turno, pago, cambio de estado)
--  viven aquí para que dos pedidos simultáneos nunca tomen el mismo turno.
-- =====================================================================

-- Franja horaria de una hora dada
CREATE OR REPLACE FUNCTION fn_franja(p_hora time) RETURNS int
LANGUAGE sql STABLE AS $$
    SELECT id_franja FROM franja_horaria
    WHERE p_hora >= hora_inicio AND p_hora < hora_fin
    ORDER BY es_hora_pico DESC, id_franja LIMIT 1
$$;

CREATE OR REPLACE FUNCTION fn_error(p_codigo text, p_mensaje text) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_build_object('ok', false, 'codigo', p_codigo, 'mensaje', p_mensaje)
$$;

CREATE OR REPLACE FUNCTION fn_historial(p_id_pedido text, p_ant text, p_nuevo text, p_emp int, p_origen text)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO historial_estado (id_pedido, estado_anterior, estado_nuevo, id_empleado, origen)
    VALUES (p_id_pedido, p_ant, p_nuevo, p_emp, p_origen)
$$;

-- ---------------------------------------------------------------------
-- RNF-05: verificación de empleado por PIN y rol. Devuelve NULL si todo está
-- bien o un JSON de error. Cinco PIN errados seguidos bloquean 5 minutos.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_verificar_empleado(p_id int, p_pin text, p_roles text[], p_caf int)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
    v_emp empleado%ROWTYPE;
BEGIN
    SELECT * INTO v_emp FROM empleado WHERE id_empleado = p_id AND activo FOR UPDATE;
    IF NOT FOUND THEN
        RETURN fn_error('NO_AUTORIZADO', 'Empleado no válido o inactivo');
    END IF;
    IF v_emp.bloqueado_hasta IS NOT NULL AND v_emp.bloqueado_hasta > ahora_local() THEN
        RETURN fn_error('BLOQUEADO', 'Usuario bloqueado por intentos fallidos. Intenta en unos minutos.');
    END IF;
    IF v_emp.pin_hash IS NULL OR p_pin IS NULL OR crypt(p_pin, v_emp.pin_hash) <> v_emp.pin_hash THEN
        UPDATE empleado SET intentos_fallidos = intentos_fallidos + 1,
               bloqueado_hasta = CASE WHEN intentos_fallidos + 1 >= 5 THEN ahora_local() + interval '5 minutes' END
         WHERE id_empleado = p_id;
        RETURN fn_error('PIN', 'PIN incorrecto');
    END IF;
    UPDATE empleado SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id_empleado = p_id AND intentos_fallidos > 0;
    IF NOT (v_emp.rol = ANY(p_roles)) THEN
        RETURN fn_error('NO_AUTORIZADO', v_emp.rol || ' no tiene permiso para esta acción');
    END IF;
    IF p_caf IS NOT NULL AND v_emp.id_cafeteria <> p_caf THEN
        RETURN fn_error('NO_AUTORIZADO', 'El empleado no pertenece a esta cafetería');
    END IF;
    RETURN NULL;
END $$;

-- Ingreso del personal a las páginas de caja y cocina
CREATE OR REPLACE FUNCTION api_ingreso(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_roles text[] := CASE p->>'pantalla' WHEN 'cocina' THEN ARRAY['Cocina/barra','Coordinador']
                                          ELSE ARRAY['Cajero','Coordinador'] END;
    v_err jsonb;
    v_emp empleado%ROWTYPE;
BEGIN
    v_err := fn_verificar_empleado(NULLIF(p->>'id_empleado','')::int, p->>'pin', v_roles,
                                   NULLIF(p->>'id_cafeteria','')::int);
    IF v_err IS NOT NULL THEN RETURN v_err; END IF;
    SELECT * INTO v_emp FROM empleado WHERE id_empleado = (p->>'id_empleado')::int;
    RETURN jsonb_build_object('ok', true, 'id_empleado', v_emp.id_empleado, 'nombre', v_emp.nombre, 'rol', v_emp.rol);
END $$;

-- ---------------------------------------------------------------------
-- Catálogo: cafeterías, empleados activos y menú (RF-03)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_catalogo(p jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_caf int := NULLIF(p->>'id_cafeteria','')::int;
BEGIN
    RETURN jsonb_build_object(
        'ok', true,
        'cafeterias', (SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY id_cafeteria), '[]') FROM cafeteria c),
        'empleados',  (SELECT coalesce(jsonb_agg(jsonb_build_object('id_empleado', id_empleado, 'nombre', nombre,
                                     'rol', rol, 'id_cafeteria', id_cafeteria) ORDER BY nombre), '[]')
                       FROM empleado WHERE activo AND (v_caf IS NULL OR id_cafeteria = v_caf)),
        'productos',  (SELECT coalesce(jsonb_agg(jsonb_build_object('id_producto', id_producto, 'nombre', nombre,
                                     'categoria', categoria, 'precio', precio, 'disponible', disponible)
                                     ORDER BY categoria, nombre), '[]')
                       FROM producto)
    );
END $$;

-- ---------------------------------------------------------------------
-- RF-01, RF-02, RF-05, RF-10: crear pedido y asignar turno
-- p = {id_cafeteria, canal, id_cajero?, segundos_espera, cliente:{...}, items:[{id_producto,cantidad,observaciones}]}
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_crear_pedido(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_ahora     timestamp := ahora_local();
    v_caf       int  := (p->>'id_cafeteria')::int;
    v_canal     text := p->>'canal';
    v_cajero    int  := NULLIF(p->>'id_cajero','')::int;
    v_seg       int  := LEAST(GREATEST(coalesce((p->>'segundos_espera')::int, 0), 0), 1800);
    v_llegada   timestamp;
    v_cli       jsonb := coalesce(p->'cliente', '{}'::jsonb);
    v_autoriza  boolean := coalesce((v_cli->>'autoriza_datos')::boolean, false);
    v_id_cli    int;
    v_turno     int;
    v_id        text;
    v_total     numeric;
    v_no_disp   text;
    v_err       jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cafeteria WHERE id_cafeteria = v_caf) THEN
        RETURN fn_error('CAFETERIA', 'La cafetería no existe');
    END IF;
    IF v_canal = 'Caja' THEN
        v_err := fn_verificar_empleado(v_cajero, p->>'pin', ARRAY['Cajero','Coordinador'], v_caf);
        IF v_err IS NOT NULL THEN RETURN v_err; END IF;
    END IF;

    -- Disponibilidad de cada producto (RF-03)
    SELECT string_agg(coalesce(pr.nombre, 'producto ' || i.id_producto), ', ')
      INTO v_no_disp
      FROM jsonb_to_recordset(p->'items') AS i(id_producto int, cantidad int)
      LEFT JOIN producto pr ON pr.id_producto = i.id_producto
     WHERE pr.id_producto IS NULL OR NOT pr.disponible;
    IF v_no_disp IS NOT NULL THEN
        RETURN fn_error('AGOTADO', 'No disponible: ' || v_no_disp);
    END IF;

    -- Cliente: sin autorización solo se guarda el nombre para llamarlo (Ley 1581)
    IF coalesce(trim(v_cli->>'nombre'), '') <> '' THEN
        INSERT INTO cliente (nombre, tipo_cliente, celular, correo_institucional, autoriza_datos)
        VALUES (left(trim(v_cli->>'nombre'), 80),
                coalesce(NULLIF(v_cli->>'tipo_cliente',''), 'Otro'),
                CASE WHEN v_autoriza THEN NULLIF(left(v_cli->>'celular', 15), '') END,
                CASE WHEN v_autoriza THEN NULLIF(left(v_cli->>'correo_institucional', 80), '') END,
                v_autoriza)
        RETURNING id_cliente INTO v_id_cli;
    END IF;

    -- Turno atómico por cafetería y día (RN-03)
    INSERT INTO turno_contador AS t (id_cafeteria, fecha, ultimo)
    VALUES (v_caf, v_ahora::date, 1)
    ON CONFLICT (id_cafeteria, fecha) DO UPDATE SET ultimo = t.ultimo + 1
    RETURNING ultimo INTO v_turno;

    v_llegada := v_ahora - make_interval(secs => v_seg);

    INSERT INTO pedido (id_cliente, id_cafeteria, id_franja, id_cajero, numero_turno, canal,
                        fecha, hora_llegada_fila, hora_toma_pedido, estado)
    VALUES (v_id_cli, v_caf, fn_franja(v_llegada::time),
            CASE WHEN v_canal = 'Caja' THEN v_cajero END,
            v_turno, v_canal, v_ahora::date, v_llegada::time, v_ahora::time, 'Registrado')
    RETURNING id_pedido INTO v_id;

    -- Si un producto viene repetido se suman las cantidades
    INSERT INTO detalle_pedido (id_pedido, id_producto, cantidad, precio_unitario, subtotal, observaciones)
    SELECT v_id, pr.id_producto, sum(i.cantidad), pr.precio, sum(i.cantidad) * pr.precio,
           NULLIF(left(string_agg(NULLIF(trim(i.observaciones), ''), '; '), 150), '')
      FROM jsonb_to_recordset(p->'items') AS i(id_producto int, cantidad int, observaciones text)
      JOIN producto pr ON pr.id_producto = i.id_producto
     GROUP BY pr.id_producto, pr.precio;

    SELECT sum(subtotal) INTO v_total FROM detalle_pedido WHERE id_pedido = v_id;
    UPDATE pedido SET valor_total = v_total WHERE id_pedido = v_id;

    PERFORM fn_historial(v_id, NULL, 'Registrado', v_cajero, 'n8n: ' || v_canal);
    INSERT INTO notificacion (id_pedido, tipo, canal) VALUES (v_id, 'Pedido recibido', 'Web');

    RETURN jsonb_build_object('ok', true, 'id_pedido', v_id, 'numero_turno', v_turno,
                              'valor_total', v_total, 'estado', 'Registrado', 'canal', v_canal,
                              'id_cafeteria', v_caf);
END $$;

-- ---------------------------------------------------------------------
-- RF-11: cliente que sale de la fila sin pedir (lo registra el cajero)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_abandono_fila(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_ahora  timestamp := ahora_local();
    v_caf    int := (p->>'id_cafeteria')::int;
    v_cajero int := NULLIF(p->>'id_cajero','')::int;
    v_seg    int := LEAST(GREATEST(coalesce((p->>'segundos_espera')::int, 0), 0), 1800);
    v_lleg   timestamp := v_ahora - make_interval(secs => v_seg);
    v_id     text;
    v_err    jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cafeteria WHERE id_cafeteria = v_caf) THEN
        RETURN fn_error('CAFETERIA', 'La cafetería no existe');
    END IF;
    v_err := fn_verificar_empleado(v_cajero, p->>'pin', ARRAY['Cajero','Coordinador'], v_caf);
    IF v_err IS NOT NULL THEN RETURN v_err; END IF;
    INSERT INTO pedido (id_cafeteria, id_franja, id_cajero, canal, fecha, hora_llegada_fila,
                        estado, abandono_fila)
    VALUES (v_caf, fn_franja(v_lleg::time), v_cajero, 'Caja', v_ahora::date, v_lleg::time,
            'Abandonado', true)
    RETURNING id_pedido INTO v_id;
    PERFORM fn_historial(v_id, NULL, 'Abandonado', v_cajero, 'n8n: salió de la fila');
    RETURN jsonb_build_object('ok', true, 'id_pedido', v_id);
END $$;

-- ---------------------------------------------------------------------
-- RF-04 y RN-01: el cajero AUTORIZA el pedido al cobrarlo en caja.
-- Solo un pedido Registrado se puede autorizar, solo lo puede hacer un cajero
-- (o el coordinador) activo de esa cafetería, y solo al autorizarse pasa a cocina.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_autorizar_pedido(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_id     text := upper(trim(p->>'id_pedido'));
    v_medio  text := coalesce(NULLIF(p->>'medio_pago',''), 'Efectivo');
    v_cajero int  := NULLIF(p->>'id_cajero','')::int;
    v_ped    pedido%ROWTYPE;
    v_emp    empleado%ROWTYPE;
    v_fact   text;
    v_cli    text;
    v_err    jsonb;
BEGIN
    SELECT * INTO v_ped FROM pedido WHERE id_pedido = v_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN fn_error('NO_EXISTE', 'El pedido ' || coalesce(v_id, '') || ' no existe');
    END IF;
    -- Solo un cajero o el coordinador de esta cafetería, con su PIN, puede autorizar
    v_err := fn_verificar_empleado(v_cajero, p->>'pin', ARRAY['Cajero','Coordinador'], v_ped.id_cafeteria);
    IF v_err IS NOT NULL THEN RETURN v_err; END IF;
    SELECT * INTO v_emp FROM empleado WHERE id_empleado = v_cajero;
    IF v_ped.estado <> 'Registrado' THEN
        RETURN fn_error('ESTADO', 'El pedido está ' || v_ped.estado || ' y no se puede autorizar');
    END IF;
    IF v_medio NOT IN ('Efectivo','Tarjeta','Transferencia') THEN
        RETURN fn_error('MEDIO', 'Medio de pago no válido');
    END IF;

    v_fact := 'FE-' || to_char(ahora_local(), 'YYYYMMDD') || '-' || lpad(nextval('factura_seq')::text, 5, '0');
    INSERT INTO pago (id_pedido, medio_pago, valor, numero_factura)
    VALUES (v_id, v_medio, v_ped.valor_total, v_fact);

    UPDATE pedido SET estado = 'Pagado', id_cajero = v_cajero WHERE id_pedido = v_id;
    PERFORM fn_historial(v_id, 'Registrado', 'Pagado', v_cajero, 'n8n: autorizado en caja (' || v_medio || ')');
    SELECT nombre INTO v_cli FROM cliente WHERE id_cliente = v_ped.id_cliente;

    RETURN jsonb_build_object('ok', true, 'id_pedido', v_id, 'numero_turno', v_ped.numero_turno,
                              'cliente', coalesce(v_cli, 'Cliente'), 'numero_factura', v_fact,
                              'valor', v_ped.valor_total, 'medio_pago', v_medio, 'estado', 'Pagado',
                              'autorizado_por', v_emp.nombre, 'id_cafeteria', v_ped.id_cafeteria);
END $$;

-- ---------------------------------------------------------------------
-- RF-07, RF-09: cambio de estado desde cocina/barra
-- Pagado -> En preparación -> Listo -> Entregado
-- Para entregar se exige el número de turno (RF-09)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_cambiar_estado(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_id      text := upper(trim(p->>'id_pedido'));
    v_nuevo   text := p->>'estado';
    v_emp     int  := NULLIF(p->>'id_empleado','')::int;
    v_turno   int  := NULLIF(p->>'numero_turno','')::int;
    v_ok_ent  boolean := coalesce((p->>'entregado_correcto')::boolean, true);
    v_ped     pedido%ROWTYPE;
    v_previo  text;
    v_ahora   time := ahora_local()::time;
    v_cliente text;
    v_err     jsonb;
BEGIN
    SELECT * INTO v_ped FROM pedido WHERE id_pedido = v_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN fn_error('NO_EXISTE', 'El pedido no existe');
    END IF;
    v_err := fn_verificar_empleado(v_emp, p->>'pin', ARRAY['Cocina/barra','Coordinador'], v_ped.id_cafeteria);
    IF v_err IS NOT NULL THEN RETURN v_err; END IF;

    v_previo := CASE v_nuevo WHEN 'En preparación' THEN 'Pagado'
                             WHEN 'Listo'          THEN 'En preparación'
                             WHEN 'Entregado'      THEN 'Listo' END;
    IF v_previo IS NULL THEN
        RETURN fn_error('ESTADO', 'Estado destino no válido: ' || coalesce(v_nuevo, ''));
    END IF;
    IF v_ped.estado <> v_previo THEN
        RETURN fn_error('TRANSICION', 'El pedido está ' || v_ped.estado || '; no puede pasar a ' || v_nuevo);
    END IF;

    IF v_nuevo = 'En preparación' THEN
        UPDATE pedido SET estado = v_nuevo, id_preparador = coalesce(v_emp, id_preparador)
         WHERE id_pedido = v_id;
    ELSIF v_nuevo = 'Listo' THEN
        UPDATE pedido SET estado = v_nuevo, hora_listo = v_ahora,
                          id_preparador = coalesce(id_preparador, v_emp)
         WHERE id_pedido = v_id;
        INSERT INTO notificacion (id_pedido, tipo, canal) VALUES (v_id, 'Pedido listo', 'Web/Pantalla');
    ELSE
        IF v_turno IS NULL OR v_turno <> v_ped.numero_turno THEN
            RETURN fn_error('TURNO', 'El número de turno no coincide con el pedido');
        END IF;
        UPDATE pedido SET estado = v_nuevo, hora_entrega = v_ahora, entregado_correcto = v_ok_ent
         WHERE id_pedido = v_id;
    END IF;

    PERFORM fn_historial(v_id, v_previo, v_nuevo, v_emp, 'n8n: cocina/barra');
    SELECT nombre INTO v_cliente FROM cliente WHERE id_cliente = v_ped.id_cliente;

    RETURN jsonb_build_object('ok', true, 'id_pedido', v_id, 'estado', v_nuevo,
                              'numero_turno', v_ped.numero_turno, 'id_cafeteria', v_ped.id_cafeteria,
                              'cliente', coalesce(v_cliente, 'Cliente'),
                              'entregado_correcto', CASE WHEN v_nuevo = 'Entregado' THEN v_ok_ent END);
END $$;

-- ---------------------------------------------------------------------
-- RF-06 y RN-02: cola de cocina en orden de pago (FIFO)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_cola(p jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object('ok', true, 'pedidos', coalesce(jsonb_agg(x ORDER BY x->>'pagado_en'), '[]'))
    FROM (
        SELECT jsonb_build_object(
            'id_pedido', pe.id_pedido, 'numero_turno', pe.numero_turno, 'estado', pe.estado,
            'canal', pe.canal, 'cliente', coalesce(cl.nombre, 'Cliente en caja'),
            'pagado_en', to_char(pg.fecha_hora, 'YYYY-MM-DD"T"HH24:MI:SS'),
            'minutos_desde_pago', round(EXTRACT(EPOCH FROM (ahora_local() - pg.fecha_hora)) / 60.0, 1),
            'items', (SELECT jsonb_agg(jsonb_build_object('producto', pr.nombre, 'cantidad', d.cantidad,
                                                          'observaciones', d.observaciones))
                        FROM detalle_pedido d JOIN producto pr ON pr.id_producto = d.id_producto
                       WHERE d.id_pedido = pe.id_pedido)) AS x
        FROM pedido pe
        JOIN pago pg ON pg.id_pedido = pe.id_pedido
        LEFT JOIN cliente cl ON cl.id_cliente = pe.id_cliente
        WHERE pe.id_cafeteria = (p->>'id_cafeteria')::int
          AND pe.fecha = ahora_local()::date
          AND pe.estado IN ('Pagado','En preparación','Listo')
    ) s
$$;

-- Pedidos registrados que esperan la autorización del cajero (con sus productos para verificarlos)
CREATE OR REPLACE FUNCTION api_pendientes_pago(p jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object('ok', true, 'pedidos', coalesce(jsonb_agg(jsonb_build_object(
              'id_pedido', pe.id_pedido, 'numero_turno', pe.numero_turno, 'canal', pe.canal,
              'cliente', coalesce(cl.nombre, 'Cliente en caja'), 'valor_total', pe.valor_total,
              'minutos', round(EXTRACT(EPOCH FROM (ahora_local()::time - pe.hora_toma_pedido)) / 60.0, 1),
              'items', (SELECT jsonb_agg(jsonb_build_object('producto', pr.nombre, 'cantidad', d.cantidad,
                                                            'observaciones', d.observaciones))
                          FROM detalle_pedido d JOIN producto pr ON pr.id_producto = d.id_producto
                         WHERE d.id_pedido = pe.id_pedido))
              ORDER BY pe.hora_toma_pedido), '[]'))
      FROM pedido pe LEFT JOIN cliente cl ON cl.id_cliente = pe.id_cliente
     WHERE pe.id_cafeteria = (p->>'id_cafeteria')::int
       AND pe.fecha = ahora_local()::date AND pe.estado = 'Registrado'
$$;

-- Pedidos de hoy (para elegir el pedido de un reclamo por turno y nombre, sin teclear códigos)
CREATE OR REPLACE FUNCTION api_pedidos_hoy(p jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object('ok', true, 'pedidos', coalesce(jsonb_agg(jsonb_build_object(
              'id_pedido', pe.id_pedido, 'numero_turno', pe.numero_turno, 'estado', pe.estado,
              'cliente', coalesce(cl.nombre, 'Cliente'), 'valor_total', pe.valor_total)
              ORDER BY pe.numero_turno DESC), '[]'))
      FROM pedido pe LEFT JOIN cliente cl ON cl.id_cliente = pe.id_cliente
     WHERE pe.id_cafeteria = (p->>'id_cafeteria')::int
       AND pe.fecha = ahora_local()::date AND pe.numero_turno IS NOT NULL AND pe.estado <> 'Abandonado'
$$;

-- Seguimiento del cliente desde su celular (RF-08)
CREATE OR REPLACE FUNCTION api_seguimiento(p jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_ped pedido%ROWTYPE;
    v_delante int;
BEGIN
    SELECT * INTO v_ped FROM pedido WHERE id_pedido = upper(trim(p->>'id_pedido'));
    IF NOT FOUND THEN
        RETURN fn_error('NO_EXISTE', 'Pedido no encontrado');
    END IF;
    -- Pedidos pagados antes que este y que aún no están listos
    SELECT count(*) INTO v_delante
      FROM pedido o JOIN pago po ON po.id_pedido = o.id_pedido
     WHERE o.id_cafeteria = v_ped.id_cafeteria AND o.fecha = v_ped.fecha
       AND o.estado IN ('Pagado','En preparación')
       AND po.fecha_hora < (SELECT fecha_hora FROM pago WHERE id_pedido = v_ped.id_pedido);
    RETURN jsonb_build_object('ok', true, 'id_pedido', v_ped.id_pedido, 'numero_turno', v_ped.numero_turno,
                              'estado', v_ped.estado, 'valor_total', v_ped.valor_total,
                              'pedidos_antes', coalesce(v_delante, 0));
END $$;

-- Pantalla de turnos (RF-08): número de turno, número de pedido y nombre de quien pidió
CREATE OR REPLACE FUNCTION api_turnos(p jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    WITH hoy AS (
        SELECT pe.numero_turno, pe.id_pedido, pe.estado, pe.hora_listo, pe.hora_toma_pedido,
               coalesce(cl.nombre, 'Cliente') AS cliente
          FROM pedido pe LEFT JOIN cliente cl ON cl.id_cliente = pe.id_cliente
         WHERE pe.id_cafeteria = (p->>'id_cafeteria')::int AND pe.fecha = ahora_local()::date
           AND pe.estado IN ('Pagado','En preparación','Listo')
    )
    SELECT jsonb_build_object('ok', true,
        'en_preparacion', coalesce((SELECT jsonb_agg(jsonb_build_object('numero_turno', numero_turno,
                'id_pedido', id_pedido, 'cliente', cliente) ORDER BY numero_turno)
             FROM hoy WHERE estado IN ('Pagado','En preparación')), '[]'),
        'listos', coalesce((SELECT jsonb_agg(jsonb_build_object('numero_turno', numero_turno,
                'id_pedido', id_pedido, 'cliente', cliente) ORDER BY hora_listo DESC)
             FROM hoy WHERE estado = 'Listo'), '[]'))
$$;

-- ---------------------------------------------------------------------
-- RF-12: reclamos
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION api_reclamo(p jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_id   text := upper(trim(p->>'id_pedido'));
    v_caf  int;
    v_rec  int;
    v_err  jsonb;
BEGIN
    SELECT id_cafeteria INTO v_caf FROM pedido WHERE id_pedido = v_id;
    IF NOT FOUND THEN
        RETURN fn_error('NO_EXISTE', 'El pedido no existe');
    END IF;
    v_err := fn_verificar_empleado(NULLIF(p->>'id_empleado','')::int, p->>'pin', ARRAY['Cajero','Coordinador'], v_caf);
    IF v_err IS NOT NULL THEN RETURN v_err; END IF;
    INSERT INTO reclamo (id_pedido, id_empleado, tipo_reclamo, descripcion, solucion, estado)
    VALUES (v_id, (p->>'id_empleado')::int, p->>'tipo_reclamo', left(p->>'descripcion', 300),
            NULLIF(left(p->>'solucion', 300), ''),
            CASE WHEN coalesce(p->>'solucion', '') <> '' THEN 'Resuelto' ELSE 'Abierto' END)
    RETURNING id_reclamo INTO v_rec;
    -- Un reclamo de entrega marca el pedido como no entregado correctamente (KPI 2)
    IF p->>'tipo_reclamo' IN ('Pedido incompleto','Pedido equivocado','Entregado a otra persona') THEN
        UPDATE pedido SET entregado_correcto = false WHERE id_pedido = v_id AND estado = 'Entregado';
    END IF;
    RETURN jsonb_build_object('ok', true, 'id_reclamo', v_rec, 'id_pedido', v_id, 'id_cafeteria', v_caf,
                              'tipo_reclamo', p->>'tipo_reclamo', 'descripcion', p->>'descripcion');
END $$;

-- ---------------------------------------------------------------------
-- RN-04 / RF-11: turnos no pagados en 10 minutos se cancelan como abandono
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_marcar_abandonos(p_minutos int DEFAULT 10) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_ids text[];
BEGIN
    WITH upd AS (
        UPDATE pedido SET estado = 'Abandonado', abandono_fila = true
         WHERE estado = 'Registrado'
           AND (fecha + hora_toma_pedido) < ahora_local() - make_interval(mins => p_minutos)
        RETURNING id_pedido
    ) SELECT array_agg(id_pedido) INTO v_ids FROM upd;

    INSERT INTO historial_estado (id_pedido, estado_anterior, estado_nuevo, origen)
    SELECT unnest(v_ids), 'Registrado', 'Abandonado', 'n8n: RN-04 sin pago';

    RETURN jsonb_build_object('ok', true, 'cancelados', coalesce(array_length(v_ids, 1), 0),
                              'ids', coalesce(to_jsonb(v_ids), '[]'));
END $$;

-- ---------------------------------------------------------------------
-- RF-14: espera promedio de los últimos 30 min en franja pico, por cafetería.
-- Devuelve solo las cafeterías que superan el umbral y que no tienen una
-- alerta igual en los últimos 15 minutos (para no saturar al coordinador).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_evaluar_espera(p_umbral numeric DEFAULT 3) RETURNS TABLE (
    id_cafeteria int, cafeteria text, franja text, espera_promedio numeric, pedidos int, pendientes_cocina int)
LANGUAGE sql AS $$
    WITH ahora AS (SELECT ahora_local() AS t),
    franja_actual AS (
        SELECT f.* FROM franja_horaria f, ahora
        WHERE f.es_hora_pico AND ahora.t::time >= f.hora_inicio AND ahora.t::time < f.hora_fin
    ),
    medidas AS (
        SELECT p.id_cafeteria,
               avg(EXTRACT(EPOCH FROM (p.hora_toma_pedido - p.hora_llegada_fila)) / 60.0) AS espera,
               count(*) AS n
        FROM pedido p, ahora
        WHERE p.fecha = ahora.t::date AND p.hora_toma_pedido IS NOT NULL
          AND p.hora_toma_pedido >= (ahora.t - interval '30 minutes')::time
        GROUP BY p.id_cafeteria
    )
    SELECT c.id_cafeteria, c.nombre::text, fa.nombre::text, round(m.espera, 2), m.n::int,
           (SELECT count(*)::int FROM pedido q WHERE q.id_cafeteria = c.id_cafeteria
               AND q.fecha = (SELECT t FROM ahora)::date AND q.estado IN ('Pagado','En preparación'))
    FROM medidas m
    JOIN cafeteria c ON c.id_cafeteria = m.id_cafeteria
    CROSS JOIN franja_actual fa
    WHERE m.espera > p_umbral
      AND NOT EXISTS (SELECT 1 FROM alerta a WHERE a.id_cafeteria = c.id_cafeteria
                        AND a.tipo = 'Espera alta' AND a.fecha_hora > (SELECT t FROM ahora) - interval '15 minutes')
$$;

-- ---------------------------------------------------------------------
-- Cálculo de los 5 KPI de un día (lo usa el cierre diario de n8n)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_cierre_diario(p_fecha date DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_fecha date := coalesce(p_fecha, ahora_local()::date);
    v_horas_pico numeric;
BEGIN
    SELECT coalesce(sum(EXTRACT(EPOCH FROM (hora_fin - hora_inicio)) / 3600.0), 1)
      INTO v_horas_pico FROM franja_horaria WHERE es_hora_pico;

    INSERT INTO kpi_diario AS k (fecha, id_cafeteria, clientes_llegados, pedidos_entregados,
        kpi1_tiempo_atencion_min, kpi2_pct_correctos, kpi3_pedidos_hora_pico,
        kpi4_espera_fila_min, kpi5_pct_abandono, ventas, calculado_en)
    SELECT v_fecha, v.id_cafeteria,
           count(*),
           count(*) FILTER (WHERE v.estado = 'Entregado'),
           round(avg(v.min_atencion) FILTER (WHERE v.estado = 'Entregado'), 2),
           round(100.0 * count(*) FILTER (WHERE v.entregado_correcto)
                 / NULLIF(count(*) FILTER (WHERE v.estado = 'Entregado'), 0), 2),
           round(count(*) FILTER (WHERE v.estado = 'Entregado' AND v.es_hora_pico) / v_horas_pico, 2),
           round(avg(v.min_espera_fila) FILTER (WHERE NOT v.abandono_fila), 2),
           round(100.0 * count(*) FILTER (WHERE v.abandono_fila) / NULLIF(count(*), 0), 2),
           coalesce(sum(v.valor_total) FILTER (WHERE v.medio_pago IS NOT NULL), 0),
           ahora_local()
      FROM v_pedidos v
     WHERE v.fecha = v_fecha
     GROUP BY v.id_cafeteria
    ON CONFLICT (fecha, id_cafeteria) DO UPDATE SET
        clientes_llegados = EXCLUDED.clientes_llegados,
        pedidos_entregados = EXCLUDED.pedidos_entregados,
        kpi1_tiempo_atencion_min = EXCLUDED.kpi1_tiempo_atencion_min,
        kpi2_pct_correctos = EXCLUDED.kpi2_pct_correctos,
        kpi3_pedidos_hora_pico = EXCLUDED.kpi3_pedidos_hora_pico,
        kpi4_espera_fila_min = EXCLUDED.kpi4_espera_fila_min,
        kpi5_pct_abandono = EXCLUDED.kpi5_pct_abandono,
        ventas = EXCLUDED.ventas,
        calculado_en = EXCLUDED.calculado_en;

    RETURN jsonb_build_object('ok', true, 'fecha', v_fecha, 'cafeterias',
        (SELECT coalesce(jsonb_agg(jsonb_build_object(
                'cafeteria', c.nombre, 'clientes', k.clientes_llegados, 'entregados', k.pedidos_entregados,
                'kpi1', k.kpi1_tiempo_atencion_min, 'kpi2', k.kpi2_pct_correctos,
                'kpi3', k.kpi3_pedidos_hora_pico, 'kpi4', k.kpi4_espera_fila_min,
                'kpi5', k.kpi5_pct_abandono, 'ventas', k.ventas) ORDER BY c.id_cafeteria), '[]')
           FROM kpi_diario k JOIN cafeteria c ON c.id_cafeteria = k.id_cafeteria
          WHERE k.fecha = v_fecha));
END $$;

-- ---------------------------------------------------------------------
-- Monitoreo de continuidad: base de datos viva y respaldo reciente (RPO 5 min)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_monitoreo() RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    v_ult timestamp;
    v_min numeric;
    v_estado text;
BEGIN
    SELECT max(fecha_hora) INTO v_ult FROM respaldo_log;
    v_min := round(EXTRACT(EPOCH FROM (ahora_local() - v_ult)) / 60.0, 1);
    v_estado := CASE WHEN v_ult IS NULL OR v_min > 10 THEN 'ALERTA' ELSE 'OK' END;
    INSERT INTO monitoreo (componente, estado, detalle)
    VALUES ('respaldo', v_estado, coalesce('Último respaldo hace ' || v_min || ' min', 'Sin respaldos registrados'));
    -- Se conservan 3 días de latidos
    DELETE FROM monitoreo WHERE fecha_hora < ahora_local() - interval '3 days';
    RETURN jsonb_build_object('ok', true, 'base_datos', 'OK', 'respaldo', v_estado,
                              'minutos_ultimo_respaldo', v_min);
END $$;
