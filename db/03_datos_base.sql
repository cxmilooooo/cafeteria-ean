-- Datos base: cafeterías, franjas (RN-05), personal y menú.
-- Cámbienlos libremente: el resto del sistema los lee de estas tablas.

INSERT INTO cafeteria (nombre, ubicacion) VALUES
  ('Cafetería Principal', 'Sede Nogal · Primer piso');

-- RN-05: las horas pico son el cambio de clase (10–11) y el almuerzo (12–14)
INSERT INTO franja_horaria (nombre, hora_inicio, hora_fin, es_hora_pico) VALUES
  ('Madrugada / cerrado', '00:00', '07:00', false),
  ('Mañana',              '07:00', '10:00', false),
  ('Cambio de clase',     '10:00', '11:00', true),
  ('Media mañana',        '11:00', '12:00', false),
  ('Almuerzo',            '12:00', '14:00', true),
  ('Tarde',               '14:00', '18:00', false),
  ('Noche',               '18:00', '23:59:59.999999', false);

INSERT INTO empleado (id_cafeteria, nombre, rol) VALUES
  (1, 'Laura Gómez',     'Cajero'),
  (1, 'Andrés Rojas',    'Cocina/barra'),
  (1, 'Paola Martínez',  'Cocina/barra'),
  (1, 'Carlos Ruiz',     'Coordinador');

INSERT INTO producto (nombre, categoria, precio) VALUES
  ('Tinto',                 'Bebida caliente', 2500),
  ('Café con leche',        'Bebida caliente', 4000),
  ('Capuchino',             'Bebida caliente', 6000),
  ('Chocolate',             'Bebida caliente', 4500),
  ('Jugo natural',          'Bebida fría',     6000),
  ('Limonada de coco',      'Bebida fría',     7500),
  ('Gaseosa',               'Bebida fría',     4000),
  ('Agua',                  'Bebida fría',     3000),
  ('Empanada',              'Snack',           3500),
  ('Pan de bono',           'Snack',           3000),
  ('Arepa con queso',       'Snack',           5500),
  ('Sándwich de pollo',     'Snack',          12000),
  ('Croissant',             'Snack',           5000),
  ('Almuerzo del día',      'Almuerzo',       18000),
  ('Almuerzo vegetariano',  'Almuerzo',       17000),
  ('Wrap de pollo',         'Almuerzo',       15000),
  ('Ensalada',              'Almuerzo',       14000),
  ('Fruta picada',          'Postre',          5000),
  ('Brownie',               'Postre',          4500);

-- PIN del personal (RNF-05). Se guardan cifrados con bcrypt; cámbienlos antes de usarlo de verdad.
UPDATE empleado e SET pin_hash = crypt(v.pin, gen_salt('bf'))
FROM (VALUES ('Laura Gómez', '1111'), ('Andrés Rojas', '2222'), ('Paola Martínez', '3333'),
             ('Carlos Ruiz', '9999')) AS v(nombre, pin)
WHERE e.nombre = v.nombre;
