// Utilidades compartidas: llamadas a n8n, formato y lectura de parámetros.
const API = '/api';

async function api(ruta, datos) {
  const opciones = datos === undefined
    ? { method: 'GET' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) };
  let resp;
  try {
    resp = await fetch(`${API}/${ruta}`, opciones);
  } catch (e) {
    return { ok: false, mensaje: 'Sin conexión con el sistema. Usar comandas foliadas (contingencia).' };
  }
  try {
    return await resp.json();
  } catch (e) {
    return { ok: false, mensaje: `El sistema respondió ${resp.status}. ¿Están activos los flujos de n8n?` };
  }
}

const pesos = v => '$' + Number(v || 0).toLocaleString('es-CO', { maximumFractionDigits: 0 });
const parametro = (k, d) => new URLSearchParams(location.search).get(k) ?? d;
const $ = s => document.querySelector(s);

function esc(t) {
  return String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function mostrarMensaje(el, texto, tipo = 'error') {
  el.className = `mensaje ${tipo}`;
  el.textContent = texto;
  el.classList.remove('oculto');
  if (tipo === 'ok') setTimeout(() => el.classList.add('oculto'), 4000);
}

// Sonido corto sin archivos externos
function campana() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1320].forEach((f, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.2, ctx.currentTime + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.18 + 0.3);
      o.start(ctx.currentTime + i * 0.18); o.stop(ctx.currentTime + i * 0.18 + 0.32);
    });
  } catch (e) { /* sin audio */ }
}

// Selector de cafetería y de empleado reutilizable
async function cargarCatalogo(idCafeteria) {
  const r = await api(`catalogo?id_cafeteria=${encodeURIComponent(idCafeteria)}`);
  if (!r.ok) throw new Error(r.mensaje || 'No se pudo cargar el catálogo');
  return r;
}

function llenarSelect(sel, opciones, valor) {
  sel.innerHTML = opciones.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('');
  if (valor !== undefined) sel.value = String(valor);
}

function agruparPorCategoria(productos) {
  const g = {};
  productos.forEach(p => (g[p.categoria] ??= []).push(p));
  return g;
}

// ---------------------------------------------------------------------
// Ingreso del personal con PIN (RNF-05). Guarda la sesión solo en esta
// pestaña (sessionStorage) y la borra al cerrar sesión o si el PIN falla.
// ---------------------------------------------------------------------
function claveSesion(pantalla, idCaf) { return `sesion_${pantalla}_${idCaf}`; }

function leerSesion(pantalla, idCaf) {
  try { return JSON.parse(sessionStorage.getItem(claveSesion(pantalla, idCaf)) || 'null'); } catch (e) { return null; }
}

function cerrarSesion(pantalla, idCaf) {
  try { sessionStorage.removeItem(claveSesion(pantalla, idCaf)); } catch (e) {}
  location.reload();
}

// Si la respuesta dice que el PIN ya no es válido, se vuelve a pedir el ingreso
function revisarSesion(r, pantalla, idCaf) {
  if (r && ['PIN', 'BLOQUEADO'].includes(r.codigo)) { alert(r.mensaje); cerrarSesion(pantalla, idCaf); }
  return r;
}

function pedirIngreso(pantalla, idCaf, empleados) {
  const guardada = leerSesion(pantalla, idCaf);
  if (guardada) return Promise.resolve(guardada);
  const roles = pantalla === 'cocina' ? ['Cocina/barra', 'Coordinador'] : ['Cajero', 'Coordinador'];
  const lista = empleados.filter(e => roles.includes(e.rol)).sort((a, b) => roles.indexOf(a.rol) - roles.indexOf(b.rol));
  const capa = document.createElement('div');
  capa.className = 'capa-ingreso';
  capa.innerHTML = `<form class="tarjeta ingreso">
      <h2>Ingreso · ${pantalla === 'cocina' ? 'Cocina y barra' : 'Caja'}</h2>
      <label for="ing-emp">Empleado</label>
      <select id="ing-emp">${lista.map(e => `<option value="${e.id_empleado}">${esc(e.nombre)} (${esc(e.rol)})</option>`).join('')}</select>
      <label for="ing-pin">PIN</label>
      <input id="ing-pin" type="password" inputmode="numeric" autocomplete="off" maxlength="8" required>
      <div id="ing-msg" class="mensaje oculto"></div>
      <button class="primario" style="margin-top:12px;width:100%">Ingresar</button>
    </form>`;
  document.body.appendChild(capa);
  capa.querySelector('#ing-pin').focus();
  return new Promise(resolve => {
    capa.querySelector('form').onsubmit = async ev => {
      ev.preventDefault();
      const datos = { id_empleado: Number(capa.querySelector('#ing-emp').value), pin: capa.querySelector('#ing-pin').value,
                      pantalla, id_cafeteria: Number(idCaf) };
      const r = await api('ingreso', datos);
      if (!r.ok) { capa.querySelector('#ing-pin').value = ''; return mostrarMensaje(capa.querySelector('#ing-msg'), r.mensaje); }
      const sesion = { id_empleado: r.id_empleado, nombre: r.nombre, rol: r.rol, pin: datos.pin };
      try { sessionStorage.setItem(claveSesion(pantalla, idCaf), JSON.stringify(sesion)); } catch (e) {}
      capa.remove();
      resolve(sesion);
    };
  });
}

// ---------------------------------------------------------------------
// Diálogos y avisos para pantallas táctiles
// ---------------------------------------------------------------------
// Abre un <dialog> modal con el HTML dado; se elimina del DOM al cerrarse.
// Tocar fuera del recuadro lo cierra (salvo que esté ocupado).
function abrirDialogo(html, clase = '') {
  const d = document.createElement('dialog');
  d.className = `dialogo ${clase}`;
  d.innerHTML = `<div class="dialogo-cuerpo">${html}</div>`;
  document.body.appendChild(d);
  d.addEventListener('close', () => d.remove());
  d.addEventListener('click', e => { if (e.target === d && !d.dataset.ocupado) d.close(); });
  d.addEventListener('cancel', e => { if (d.dataset.ocupado) e.preventDefault(); });
  d.showModal();
  return d;
}
const hayDialogoAbierto = () => !!document.querySelector('dialog[open], .capa-ingreso');

// Franja grande y visible unos segundos (confirmaciones en hora pico)
function aviso(texto, tipo = 'ok', ms = 5000) {
  let el = document.getElementById('aviso-flotante');
  if (!el) { el = document.createElement('div'); el.id = 'aviso-flotante'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.className = `aviso-flotante ${tipo}`;
  el.textContent = texto;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('oculto'), ms);
  el.onclick = () => el.classList.add('oculto');
}
