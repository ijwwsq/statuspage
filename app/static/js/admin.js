// Админка инцидентов. Логин по токену, дальше — создание/обновление инцидентов и ручные статусы.
import { admin, escapeHtml, fmtTime } from './api.js';
import { COMPONENT_STATUS, INCIDENT_STATUS, IMPACT } from './labels.js';

const root = document.getElementById('admin');
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
  card.innerHTML = `<h3>Вход</h3>
    <label>Admin-токен</label>
    <input id="token" type="password" autocomplete="current-password">
    <div class="mt"><button class="btn primary" id="do-login">Войти</button></div>
    ${message ? `<div class="err">${escapeHtml(message)}</div>` : ''}`;
  root.appendChild(card);
  const input = card.querySelector('#token');
  const submit = async () => {
    try {
      await admin('/login', { method: 'POST', body: { token: input.value } });
      dashboard();
    } catch {
      loginView('Неверный токен');
    }
  };
  card.querySelector('#do-login').onclick = submit;
  input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  input.focus();
}

function incidentForm(components) {
  const card = el('div', 'card');
  card.innerHTML = `<h3>Новый инцидент / работы</h3>
    <label>Заголовок</label><input id="f-title">
    <div class="field-row mt">
      <div><label>Тип</label><select id="f-type">
        <option value="incident">Инцидент</option>
        <option value="maintenance">Плановые работы</option></select></div>
      <div><label>Влияние</label><select id="f-impact">${opts(IMPACT, 'minor')}</select></div>
      <div><label>Статус</label><select id="f-status">${opts(INCIDENT_STATUS, 'investigating')}</select></div>
    </div>
    <label class="mt">Сообщение</label><textarea id="f-body"></textarea>
    <label class="mt">Затронутые компоненты</label>
    <div class="checks">${components.map((c) =>
      `<label><input type="checkbox" value="${escapeHtml(c.key)}"> ${escapeHtml(c.name)}</label>`).join('')}</div>
    <div class="mt"><button class="btn primary" id="f-submit">Опубликовать</button></div>
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
    if (!body.title || !body.body) { msg.className = 'err'; msg.textContent = 'Заголовок и сообщение обязательны'; return; }
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
    <textarea class="u-body mt" placeholder="Что нового по инциденту…"></textarea>
    <div class="mt"><button class="btn">Добавить обновление</button></div>
    <div class="u-msg"></div>`;
  wrap.querySelector('button').onclick = async () => {
    const msg = wrap.querySelector('.u-msg');
    const body = {
      status: wrap.querySelector('.u-status').value,
      body: wrap.querySelector('.u-body').value.trim(),
    };
    if (!body.body) { msg.className = 'err'; msg.textContent = 'Введите текст'; return; }
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
    <div class="muted">${escapeHtml(IMPACT[inc.impact] || inc.impact)} · создан ${escapeHtml(fmtTime(inc.created_at))}</div>`;
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
  card.innerHTML = '<h3>Ручные статусы компонентов</h3><div class="muted">Пусто = статус берётся из монитора.</div>';
  components.forEach((c) => {
    const row = el('div', 'field-row mt');
    row.innerHTML = `<div style="flex:2"><b>${escapeHtml(c.name)}</b>
        <div class="muted">монитор: ${escapeHtml(COMPONENT_STATUS[c.monitored_status] || c.monitored_status)}</div></div>
      <div><select class="c-status">
        <option value="">— авто —</option>${opts(COMPONENT_STATUS, c.manual_status || '')}</select></div>`;
    row.querySelector('.c-status').onchange = async (e) => {
      await admin(`/components/${encodeURIComponent(c.key)}/status`, {
        method: 'POST', body: { status: e.target.value || null },
      });
    };
    card.appendChild(row);
  });
  return card;
}

function testToolbar(components) {
  const bar = el('div', 'toolbar');
  const rand = () => (components.length
    ? components[Math.floor(Math.random() * components.length)].key : 'gateway');
  const mk = (label, payload) => {
    const b = el('button', 'btn small', label);
    b.onclick = async () => {
      b.disabled = true;
      try { await admin('/incidents', { method: 'POST', body: payload() }); } catch (e) { /* noop */ }
      dashboard();
    };
    return b;
  };
  bar.appendChild(mk('+ Тестовый инцидент', () => ({
    title: 'Тестовый инцидент · ' + new Date().toLocaleTimeString('ru-RU'),
    type: 'incident', impact: 'minor', status: 'investigating',
    body: 'Автосозданный инцидент для проверки витрины и уведомлений.',
    component_keys: [rand()],
  })));
  bar.appendChild(mk('+ Тестовые работы', () => ({
    title: 'Тестовые плановые работы',
    type: 'maintenance', impact: 'minor', status: 'investigating',
    body: 'Проверочное окно плановых работ.',
    component_keys: [rand()],
  })));
  return bar;
}

async function dashboard() {
  try {
    const [components, incidents] = await Promise.all([admin('/components'), admin('/incidents')]);
    root.innerHTML = '';
    root.appendChild(testToolbar(components));
    root.appendChild(incidentForm(components));
    root.appendChild(componentsCard(components));
    root.appendChild(el('div', 'section-title', 'Инциденты'));
    if (incidents.length) incidents.forEach((i) => root.appendChild(incidentCard(i)));
    else root.appendChild(el('div', 'empty', 'Инцидентов пока нет.'));
  } catch {
    loginView();
  }
}

// стартуем: если кука валидна — сразу дашборд, иначе логин
admin('/session').then(dashboard).catch(() => loginView());
