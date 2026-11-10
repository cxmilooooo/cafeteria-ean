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
    conexion(false);
    return { ok: false, mensaje: 'Sin conexión con el sistema. Usar comandas en papel mientras vuelve.' };
  }
  if (resp.status === 429) return { ok: false, mensaje: 'Demasiadas solicitudes seguidas. Espera unos segundos e intenta de nuevo.' };
  if (resp.status >= 502) { conexion(false); return { ok: false, mensaje: 'El sistema no responde. Usar comandas en papel mientras vuelve.' }; }
  conexion(true);
  try {
    const j = await resp.json();
    if (j && j.ok === undefined) return { ok: false, mensaje: 'No se pudo completar. Revisa los datos e intenta de nuevo.' };
    return j;
  } catch (e) {
    return { ok: false, mensaje: 'No se pudo completar. Intenta de nuevo.' };
  }
}

// Aviso global si el sistema no responde 2 veces seguidas (para pasar a comandas en papel)
let _fallos = 0;
function conexion(ok) {
  _fallos = ok ? 0 : _fallos + 1;
  let b = document.getElementById('sin-conexion');
  if (_fallos >= 2 && !b) {
    b = document.createElement('div'); b.id = 'sin-conexion';
    b.textContent = '⚠️ Sin conexión con el sistema. Usar comandas en papel; se recupera solo cuando vuelva.';
    b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:50;background:#b3261e;color:#fff;padding:12px 16px;font-weight:700;text-align:center';
    document.body.appendChild(b);
  } else if (ok && b) b.remove();
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

// ---------------------------------------------------------------------
// Sonidos sin archivos externos. Los navegadores bloquean el audio hasta que
// la persona toca la página, así que el contexto de audio se "desbloquea" con
// el primer toque o tecla y luego se reutiliza.
// ---------------------------------------------------------------------
let _audio = null;
function audio() {
  try {
    _audio ??= new (window.AudioContext || window.webkitAudioContext)();
    if (_audio.state === 'suspended') _audio.resume();
  } catch (e) { _audio = null; }
  return _audio;
}
function sonidoDisponible() { return !!_audio && _audio.state === 'running'; }
['pointerdown', 'keydown', 'touchstart'].forEach(ev =>
  window.addEventListener(ev, () => audio(), { once: true, passive: true }));

function _tonos(notas, volumen) {
  const ctx = audio(); if (!ctx) return;
  notas.forEach(([f, t, dur]) => {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine'; o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
    const t0 = ctx.currentTime + t;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(volumen, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.start(t0); o.stop(t0 + dur + 0.05);
  });
}

// Aviso corto (pedido nuevo en caja o cocina)
function campana() { _tonos([[880, 0, 0.3], [1320, 0.18, 0.35]], 0.25); }

// Pedido listo: tono fuerte de 3 notas, repetido dos veces para que se escuche en el mostrador
function tonoListo() {
  const notas = [[784, 0, 0.45], [988, 0.22, 0.45], [1319, 0.44, 0.8]];
  _tonos([...notas, ...notas.map(([f, t, d]) => [f, t + 1.4, d])], 0.6);
}

// Anuncio por voz (si el navegador lo permite): "Turno 12, María"
function anunciar(texto) {
  try {
    if (!('speechSynthesis' in window)) return;
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-CO'; u.rate = 0.95; u.volume = 1;
    const voz = speechSynthesis.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith('es'));
    if (voz) u.voice = voz;
    speechSynthesis.speak(u);
  } catch (e) { /* sin voz */ }
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
