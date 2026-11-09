-- Migración 001: dejar solo la Cafetería Principal.
-- Borra la "Cafetería Torre 2" con su personal y todos sus datos. Si ya no existe, no hace nada.
-- La ejecuta actualizar.sh / actualizar.bat en instalaciones existentes.
DO $$
DECLARE
    v_caf int;
BEGIN
    SELECT id_cafeteria INTO v_caf FROM cafeteria WHERE nombre = 'Cafetería Torre 2';
    IF v_caf IS NULL THEN
        RETURN;
    END IF;

    CREATE TEMP TABLE m_ped ON COMMIT DROP AS
        SELECT id_pedido, id_cliente FROM pedido WHERE id_cafeteria = v_caf;
    CREATE TEMP TABLE m_emp ON COMMIT DROP AS
        SELECT id_empleado FROM empleado WHERE id_cafeteria = v_caf;

    DELETE FROM reclamo          WHERE id_pedido IN (SELECT id_pedido FROM m_ped)
                                    OR id_empleado IN (SELECT id_empleado FROM m_emp);
    DELETE FROM pago             WHERE id_pedido IN (SELECT id_pedido FROM m_ped);
    DELETE FROM notificacion     WHERE id_pedido IN (SELECT id_pedido FROM m_ped);
    DELETE FROM historial_estado WHERE id_pedido IN (SELECT id_pedido FROM m_ped);
    DELETE FROM detalle_pedido   WHERE id_pedido IN (SELECT id_pedido FROM m_ped);

    ALTER TABLE pedido DISABLE TRIGGER pedido_proteger_horas;
    DELETE FROM pedido WHERE id_pedido IN (SELECT id_pedido FROM m_ped);
    -- Por si personal de la Torre 2 atendió pedidos de la Principal
    UPDATE pedido SET id_cajero = NULL     WHERE id_cajero     IN (SELECT id_empleado FROM m_emp);
    UPDATE pedido SET id_preparador = NULL WHERE id_preparador IN (SELECT id_empleado FROM m_emp);
    ALTER TABLE pedido ENABLE TRIGGER pedido_proteger_horas;
    UPDATE historial_estado SET id_empleado = NULL WHERE id_empleado IN (SELECT id_empleado FROM m_emp);

    DELETE FROM cliente WHERE id_cliente IN (SELECT id_cliente FROM m_ped WHERE id_cliente IS NOT NULL)
                          AND NOT EXISTS (SELECT 1 FROM pedido p WHERE p.id_cliente = cliente.id_cliente);
    DELETE FROM turno_contador WHERE id_cafeteria = v_caf;
    DELETE FROM kpi_diario     WHERE id_cafeteria = v_caf;
    DELETE FROM alerta         WHERE id_cafeteria = v_caf;
    DELETE FROM empleado       WHERE id_cafeteria = v_caf;
    DELETE FROM cafeteria      WHERE id_cafeteria = v_caf;
    RAISE NOTICE 'Cafetería Torre 2 eliminada';
END $$;
