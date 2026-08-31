// Админка инцидентов. Логин по токену, дальше — создание/обновление инцидентов и ручные статусы.
import { admin, escapeHtml, fmtTime, getSummary } from './api.js';
import { metricCard } from './metrics.js';
import { COMPONENT_STATUS, INCIDENT_STATUS, IMPACT } from './labels.js';

const root = document.getElementById('admin');
let admGran = '90d';
const ADM_GRAN = [['24h', '24 hours'], ['30d', '30 days'], ['90d', '90 days']];
const opts = (map, sel) => Object.entries(map)
  .map(([k, v]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${escapeHtml(v)}</option>`)
  .join('');

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}

function loginView(message) {
  root.innerHTML = '';
  const card = el('div', 'card');
  card.innerHTML = `<h3>Sign in</h3>
    <label>Admin token</label>
    <input id="token" type="password" autocomplete="current-password">
    <div class="mt"><button class="btn primary" id="do-login">Sign in</button></div>
    ${message ? `<div class="err">${escapeHtml(message)}</div>` : ''}`;
  root.appendChild(card);
  const input = card.querySelector('#token');
  const submit = async () => {
    try {
      await admin('/login', { method: 'POST', body: { token: input.value } });
      dashboard();
    } catch {
      loginView('Wrong token');
    }
  };
  card.querySelector('#do-login').onclick = submit;
  input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  input.focus();
}

function incidentForm(components) {
  const card = el('div', 'card');
  card.innerHTML = `<h3>New incident / maintenance</h3>
    <label>Title</label><input id="f-title">
    <div class="field-row mt">
      <div><label>Type</label><select id="f-type">
        <option value="incident">Incident</option>
        <option value="maintenance">Scheduled maintenance</option></select></div>
      <div><label>Impact</label><select id="f-impact">${opts(IMPACT, 'minor')}</select></div>
      <div><label>Status</label><select id="f-status">${opts(INCIDENT_STATUS, 'investigating')}</select></div>
    </div>
    <label class="mt">Message</label><textarea id="f-body"></textarea>
    <label class="mt">Affected components</label>
    <div class="checks">${components.map((c) =>
      `<label><input type="checkbox" value="${escapeHtml(c.key)}"> ${escapeHtml(c.name)}</label>`).join('')}</div>
    <div class="mt"><button class="btn primary" id="f-submit">Publish</button></div>
    <div id="f-msg"></div>`;

  card.querySelector('#f-submit').onclick = async () => {
    const keys = [...card.querySelectorAll('.checks input:checked')].map((i) => i.value);
    const body = {
      title: card.querySelector('#f-title').value.trim(),
      type: card.querySelector('#f-type').value,
      impact: card.querySelector('#f-impact').value,
      status: card.querySelector('#f-status').value,
      body: card.querySelector('#f-body').value.trim(),
      component_keys: keys,
    };
    const msg = card.querySelector('#f-msg');
    if (!body.title || !body.body) { msg.className = 'err'; msg.textContent = 'Title and message are required'; return; }
    try {
      await admin('/incidents', { method: 'POST', body });
      dashboard();
    } catch (e) {
      msg.className = 'err'; msg.textContent = e.message;
    }
  };
  return card;
}

function updateForm(inc) {
  const wrap = el('div', 'mt');
  wrap.innerHTML = `<div class="field-row">
      <div><select class="u-status">${opts(INCIDENT_STATUS, inc.status)}</select></div>
    </div>
    <textarea class="u-body mt" placeholder="What's new on this incident…"></textarea>
    <div class="mt"><button class="btn">Add update</button></div>
    <div class="u-msg"></div>`;
  wrap.querySelector('button').onclick = async () => {
    const msg = wrap.querySelector('.u-msg');
    const body = {
      status: wrap.querySelector('.u-status').value,
      body: wrap.querySelector('.u-body').value.trim(),
    };
    if (!body.body) { msg.className = 'err'; msg.textContent = 'Enter a message'; return; }
    try {
      await admin(`/incidents/${inc.id}/updates`, { method: 'POST', body });
      dashboard();
    } catch (e) { msg.className = 'err'; msg.textContent = e.message; }
  };
  return wrap;
}

function incidentCard(inc) {
  const card = el('div', 'card');
  const badge = inc.status === 'resolved' ? 'none' : inc.impact;
  card.innerHTML = `<div class="head">
      <div class="title">${escapeHtml(inc.title)}</div>
      <span class="badge ${badge}">${escapeHtml(INCIDENT_STATUS[inc.status] || inc.status)}</span>
    </div>
    <div class="muted">${escapeHtml(IMPACT[inc.impact] || inc.impact)} · created ${escapeHtml(fmtTime(inc.created_at))}</div>`;
  const tl = el('ul', 'timeline');
  [...inc.updates].reverse().forEach((u) => {
    tl.appendChild(el('li', null,
      `<span class="st">${escapeHtml(INCIDENT_STATUS[u.status] || u.status)}</span>` +
      `<span class="when">${escapeHtml(fmtTime(u.created_at))}</span>` +
      `<div class="body">${escapeHtml(u.body)}</div>`));
  });
  card.appendChild(tl);
  if (inc.status !== 'resolved') card.appendChild(updateForm(inc));
  return card;
}

function componentsCard(components) {
  const card = el('div', 'card');
  card.innerHTML = '<h3>Manual component statuses</h3><div class="muted">Empty = status comes from the monitor.</div>';
  components.forEach((c) => {
    const row = el('div', 'field-row mt');
    row.innerHTML = `<div style="flex:2"><b>${escapeHtml(c.name)}</b>
        <div class="muted">monitor: ${escapeHtml(COMPONENT_STATUS[c.monitored_status] || c.monitored_status)}</div></div>
      <div><select class="c-status">
        <option value="">— auto —</option>${opts(COMPONENT_STATUS, c.manual_status || '')}</select></div>`;
    row.querySelector('.c-status').onchange = async (e) => {
      await admin(`/components/${encodeURIComponent(c.key)}/status`, {
        method: 'POST', body: { status: e.target.value || null },
      });
    };
    card.appendChild(row);
  });
  return card;
}

async function refreshMetrics(grid, seg) {
  grid.innerHTML = '';
  try {
    const data = await getSummary();
    const ms = data.metrics || [];
    if (ms.length) ms.forEach((m) => grid.appendChild(metricCard(m, admGran)));
    else grid.appendChild(el('div', 'muted', 'No metrics yet.'));
  } catch (e) {
    grid.innerHTML = '<div class="err">Failed to load metrics.</div>';
  }
  if (seg) [...seg.children].forEach((b, i) => b.classList.toggle('active', ADM_GRAN[i][0] === admGran));
}

async function metricsPanel() {
  const card = el('div', 'card');
  card.appendChild(el('h3', null, 'Response time'));
  const seg = el('div', 'seg mt');
  ADM_GRAN.forEach(([g, label]) => {
    const b = el('button', 'seg-btn' + (g === admGran ? ' active' : ''), label);
    b.onclick = () => { admGran = g; refreshMetrics(grid, seg); };
    seg.appendChild(b);
  });
  card.appendChild(seg);
  const grid = el('div', 'metrics-grid mt');
  card.appendChild(grid);
  await refreshMetrics(grid, seg);
  return card;
}

async function dashboard() {
  try {
    const [components, incidents] = await Promise.all([admin('/components'), admin('/incidents')]);
    root.innerHTML = '';
    root.appendChild(await metricsPanel());
    root.appendChild(incidentForm(components));
    root.appendChild(componentsCard(components));
    root.appendChild(el('div', 'section-title', 'Incidents'));
    if (incidents.length) incidents.forEach((i) => root.appendChild(incidentCard(i)));
    else root.appendChild(el('div', 'empty', 'No incidents yet.'));
  } catch {
    loginView();
  }
}

// стартуем: если кука валидна — сразу дашборд, иначе логин
admin('/session').then(dashboard).catch(() => loginView());
