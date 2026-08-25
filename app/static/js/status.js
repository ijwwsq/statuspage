// Витрина статуса: тянет /api/summary, рендерит, поллит; тултип по инцидентам на графике.
import { getSummary, escapeHtml, fmtTime } from './api.js';
import { uptimeBar, uptimeMeta } from './uptime.js';
import { showTip, hideTip } from './tooltip.js';
import { metricCard } from './metrics.js';
import { COMPONENT_STATUS, INCIDENT_STATUS, IMPACT } from './labels.js';

const app = document.getElementById('app');
const updated = document.getElementById('updated');
const subscribe = document.getElementById('subscribe');

let incidentIndex = new Map();   // key компонента -> [инциденты]
let brand = {};
let metricsData = [];
let uptimeGran = '90d';   // единая гранулярность для аптайма и метрик
let lastData = null;
const UPTIME_GRAN = [['24h', '24 часа'], ['30d', '30 дней'], ['90d', '90 дней']];

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}

const dayOf = (iso) => (iso ? iso.slice(0, 10) : null);
const todayStr = () => new Date().toISOString().slice(0, 10);

function buildIndex(data) {
  incidentIndex = new Map();
  const all = [...data.incidents, ...data.maintenance, ...data.history];
  for (const inc of all) {
    for (const c of inc.components) {
      if (!incidentIndex.has(c.key)) incidentIndex.set(c.key, []);
      incidentIndex.get(c.key).push(inc);
    }
  }
}

function incidentsOnDay(key, date) {
  const list = incidentIndex.get(key) || [];
  return list.filter((inc) => {
    const start = dayOf(inc.created_at);
    const end = inc.resolved_at ? dayOf(inc.resolved_at) : todayStr();
    return start && date >= start && date <= end;
  });
}

function incidentDates(key) {
  const set = new Set();
  for (const inc of incidentIndex.get(key) || []) {
    const start = dayOf(inc.created_at);
    const end = inc.resolved_at ? dayOf(inc.resolved_at) : todayStr();
    if (!start) continue;
    for (let d = new Date(start); d.toISOString().slice(0, 10) <= end; d.setDate(d.getDate() + 1)) {
      set.add(d.toISOString().slice(0, 10));
    }
  }
  return set;
}

// ---- тултип по засечке (стиль Atlassian: что было в этот день) --------------

function incidentsInRange(key, startMs, endMs) {
  const nowMs = Date.now();
  return (incidentIndex.get(key) || []).filter((inc) => {
    const c = Date.parse(inc.created_at);
    const r = inc.resolved_at ? Date.parse(inc.resolved_at) : nowMs;
    return c <= endMs && r >= startMs;
  });
}

function incidentHourSet(key, entries) {
  const set = new Set();
  for (const e of entries) {
    const s = Date.parse(e.time);
    if (incidentsInRange(key, s, s + 3600000).length) set.add(e.time);
  }
  return set;
}

function headHtml(label, status, uptime) {
  const dot = { up: 'var(--up)', partial: 'var(--partial)', down: 'var(--down)', unknown: 'var(--unknown)' }[status];
  let up;
  if (status === 'unknown') up = 'Нет данных';
  else if (status === 'up') up = 'Работал штатно · 100%';
  else up = `${Number(uptime).toFixed(2)}%`;
  return `<div class="tip-date">${escapeHtml(label)}</div>` +
    `<div class="tip-up"><span class="dot" style="background:${dot}"></span>${escapeHtml(up)}</div>`;
}

function stepsHtml(inc, showUpdate) {
  const badge = inc.status === 'resolved' ? 'none' : inc.impact;
  let html = `<div class="tip-inc"><div class="t">${escapeHtml(inc.title)}` +
    `<span class="badge ${badge}">${escapeHtml(INCIDENT_STATUS[inc.status] || inc.status)}</span></div>`;
  const ups = inc.updates.filter(showUpdate);
  if (ups.length) {
    html += '<ul class="tip-steps">';
    for (const u of ups) {
      const body = u.body.length > 150 ? u.body.slice(0, 150) + '…' : u.body;
      html += `<li><span class="s">${escapeHtml(INCIDENT_STATUS[u.status] || u.status)}</span> ` +
        `<span class="b">${escapeHtml(body)}</span></li>`;
    }
    html += '</ul>';
  } else {
    html += `<div class="muted" style="margin-top:4px">Продолжался · статус: ${escapeHtml(INCIDENT_STATUS[inc.status] || inc.status)}</div>`;
  }
  return html + '</div>';
}

function tickTooltip(ds) {
  if (ds.gran === '24h') {
    const start = new Date(ds.ts);
    const label = start.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    let html = headHtml(label, ds.status, ds.uptime);
    const s = start.getTime();
    const e = s + 3600000;
    for (const inc of incidentsInRange(ds.key, s, e)) {
      html += stepsHtml(inc, (u) => { const t = Date.parse(u.created_at); return t >= s && t < e; });
    }
    return html;
  }
  const date = new Date(ds.ts + 'T00:00:00');
  const label = date.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });
  let html = headHtml(label, ds.status, ds.uptime);
  for (const inc of incidentsOnDay(ds.key, ds.ts)) {
    html += stepsHtml(inc, (u) => dayOf(u.created_at) === ds.ts);
  }
  return html;
}

// ---- рендер ------------------------------------------------------------------

function renderComponent(c) {
  let entries;
  let gran;
  let marked;
  let pct;
  if (uptimeGran === '24h') {
    entries = c.hours || [];
    gran = '24h';
    marked = incidentHourSet(c.key, entries);
  } else {
    entries = uptimeGran === '30d' ? c.days.slice(-30) : c.days;
    gran = 'day';
    marked = incidentDates(c.key);
  }
  if (uptimeGran === '90d') {
    pct = c.uptime;
  } else {
    const vals = entries.filter((e) => e.uptime != null).map((e) => e.uptime);
    pct = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }

  const box = el('div', 'component');
  const row = el('div', 'row');
  const left = el('div');
  left.appendChild(el('div', 'name', escapeHtml(c.name)));
  if (c.description) left.appendChild(el('div', 'desc', escapeHtml(c.description)));
  row.appendChild(left);

  const right = el('div', 'cstatus');
  right.appendChild(el('div', 'pill ' + c.status, escapeHtml(COMPONENT_STATUS[c.status] || c.status)));
  if (pct != null) right.appendChild(el('div', 'cuptime', pct.toFixed(2) + '% аптайм'));
  row.appendChild(right);
  box.appendChild(row);

  box.appendChild(uptimeBar(entries, c.key, gran, marked));
  box.appendChild(uptimeMeta(gran, entries.length));
  return box;
}

function renderIncident(inc) {
  const box = el('div', 'incident');
  const head = el('div', 'head');
  head.appendChild(el('div', 'title', escapeHtml(inc.title)));
  const badge = inc.type === 'maintenance' ? 'maintenance' : inc.impact;
  head.appendChild(el('span', 'badge ' + badge, escapeHtml(IMPACT[inc.impact] || inc.impact)));
  box.appendChild(head);

  if (inc.type === 'maintenance' && inc.scheduled_for) {
    box.appendChild(el('div', 'affected',
      `Запланировано: ${escapeHtml(fmtTime(inc.scheduled_for))}` +
      (inc.scheduled_until ? ` — ${escapeHtml(fmtTime(inc.scheduled_until))}` : '')));
  }
  if (inc.components.length) {
    box.appendChild(el('div', 'affected',
      'Затронуто: ' + inc.components.map((x) => escapeHtml(x.name)).join(', ')));
  }

  const tl = el('ul', 'timeline');
  for (const u of [...inc.updates].reverse()) {
    tl.appendChild(el('li', null,
      `<span class="st">${escapeHtml(INCIDENT_STATUS[u.status] || u.status)}</span>` +
      `<span class="when">${escapeHtml(fmtTime(u.created_at))}</span>` +
      `<div class="body">${escapeHtml(u.body)}</div>`));
  }
  box.appendChild(tl);
  return box;
}

function metricsSection() {
  const wrap = el('div', 'metrics-wrap');
  wrap.appendChild(el('div', 'section-title', 'Метрики'));
  const grid = el('div', 'metrics-grid');
  metricsData.forEach((m) => grid.appendChild(metricCard(m, uptimeGran)));
  wrap.appendChild(grid);
  return wrap;
}

function statusHeader() {
  const wrap = el('div', 'status-header');
  wrap.appendChild(el('div', 'section-title', 'Состояние сервисов'));
  const seg = el('div', 'seg');
  UPTIME_GRAN.forEach(([g, label]) => {
    const b = el('button', 'seg-btn' + (g === uptimeGran ? ' active' : ''), label);
    b.onclick = () => { uptimeGran = g; if (lastData) render(lastData); };
    seg.appendChild(b);
  });
  wrap.appendChild(seg);
  return wrap;
}

function legend() {
  const items = [['up', 'Работает'], ['partial', 'Замедление'], ['down', 'Сбой'], ['unknown', 'Нет данных']];
  const l = el('div', 'legend');
  l.innerHTML = items.map(([k, label]) =>
    `<span class="leg"><span class="leg-dot u-${k}"></span>${label}</span>`).join('');
  return l;
}

function applyBrand() {
  if (brand.accent) document.documentElement.style.setProperty('--blue', brand.accent);
  if (brand.footer_note) {
    const foot = document.querySelector('.foot');
    if (foot && !foot.querySelector('.foot-note')) {
      foot.appendChild(el('span', 'muted foot-note', escapeHtml(brand.footer_note)));
    }
  }
}

function render(data) {
  brand = data.brand || {};
  metricsData = data.metrics || [];
  lastData = data;
  applyBrand();
  buildIndex(data);
  app.innerHTML = '';

  const banner = el('div', 'banner ' + data.overall.level);
  banner.appendChild(el('span', 'dot'));
  const bt = el('div');
  bt.appendChild(el('h1', null, escapeHtml(data.overall.label)));
  banner.appendChild(bt);
  app.appendChild(banner);

  if (data.incidents.length) {
    app.appendChild(el('div', 'section-title', 'Активные инциденты'));
    data.incidents.forEach((i) => app.appendChild(renderIncident(i)));
  }
  if (data.maintenance.length) {
    app.appendChild(el('div', 'section-title', 'Плановые работы'));
    data.maintenance.forEach((i) => app.appendChild(renderIncident(i)));
  }

  app.appendChild(statusHeader());
  app.appendChild(legend());
  for (const g of data.groups) {
    const group = el('div', 'group');
    group.appendChild(el('h2', null, escapeHtml(g.name)));
    const list = el('div', 'components');
    g.components.forEach((c) => list.appendChild(renderComponent(c)));
    group.appendChild(list);
    app.appendChild(group);
  }

  if (metricsData.length) app.appendChild(metricsSection());

  app.appendChild(el('div', 'section-title', `История за ${data.history_days} дней`));
  if (data.history.length) {
    data.history.forEach((i) => app.appendChild(renderIncident(i)));
  } else {
    app.appendChild(el('div', 'empty', 'Инцидентов за период не было.'));
  }

  updated.textContent = 'Обновлено ' + fmtTime(data.generated_at);
}

// ---- тултип: делегирование на #app ------------------------------------------

app.addEventListener('mouseover', (e) => {
  const tick = e.target.closest('.utick');
  if (!tick) return;
  showTip(tickTooltip(tick.dataset), tick.getBoundingClientRect());
});
app.addEventListener('mouseout', (e) => {
  if (e.target.closest('.utick')) hideTip();
});
window.addEventListener('scroll', hideTip, { passive: true });

// ---- подписка ---------------------------------------------------------------

function openSubscribe() {
  const overlay = el('div', 'modal-overlay');
  const url = brand.telegram_url;
  const action = url
    ? `<a class="btn primary" href="${escapeHtml(url)}" target="_blank" rel="noopener">Открыть бота в Telegram</a>`
    : `<span class="muted">Бот уведомлений ещё не подключён администратором.</span>`;
  overlay.innerHTML =
    `<div class="modal" role="dialog" aria-modal="true">
      <h3>Уведомления о статусе</h3>
      <p>Получайте оповещения об инцидентах и восстановлении сервисов в Telegram.</p>
      <ol>
        <li>Откройте бота уведомлений.</li>
        <li>Нажмите <b>Старт</b> (команда <code>/start</code>).</li>
        <li>Готово — уведомления будут приходить автоматически. <code>/stop</code> — отписаться.</li>
      </ol>
      <div class="modal-actions">
        <button class="btn ghost" data-close>Закрыть</button>
        ${action}
      </div>
    </div>`;
  const close = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay || e.target.hasAttribute('data-close')) close(); });
  document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } });
  document.body.appendChild(overlay);
}

if (subscribe) {
  subscribe.hidden = false;
  subscribe.addEventListener('click', (e) => { e.preventDefault(); openSubscribe(); });
}

// ---- цикл --------------------------------------------------------------------

let lastSig = '';
async function tick() {
  try {
    const data = await getSummary();
    const sig = JSON.stringify(data);
    if (sig === lastSig) return;   // ничего не изменилось — DOM не трогаем
    lastSig = sig;
    render(data);
  } catch {
    app.innerHTML = '<p class="empty">Не удалось загрузить статус. Повтор через 30с.</p>';
  }
}

tick();
setInterval(tick, 30000);
