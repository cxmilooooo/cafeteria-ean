-- Migración 002: agrega el estado "No recogido" (pedido listo que el cliente nunca recogió).
ALTER TABLE pedido DROP CONSTRAINT IF EXISTS pedido_estado_check;
ALTER TABLE pedido ADD CONSTRAINT pedido_estado_check
    CHECK (estado IN ('Registrado','Pagado','En preparación','Listo','Entregado','Abandonado','No recogido'));
