// Витрина статуса: тянет /api/summary, рендерит, поллит; тултип по инцидентам на графике.
import { getSummary, escapeHtml, fmtTime } from './api.js';
import { uptimeBar, uptimeMeta } from './uptime.js';
import { showTip, hideTip } from './tooltip.js';
import { COMPONENT_STATUS, INCIDENT_STATUS, IMPACT } from './labels.js';

const app = document.getElementById('app');
const updated = document.getElementById('updated');
const subscribe = document.getElementById('subscribe');

let incidentIndex = new Map();   // key компонента -> [инциденты]
let allIncidents = [];           // плоский список (для календаря)
let brand = {};
let uptimeGran = '90d';   // гранулярность аптайм-полос
let calSource = 'all';    // источник календаря: 'all' или ключ компонента
let lastData = null;
const UPTIME_GRAN = [['24h', '24 часа'], ['30d', '30 дней'], ['90d', '90 дней']];
const MONTHS_FULL = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

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
  allIncidents = all;
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
  right.appendChild(el('div', 'cstatus-line',
    `<span class="sdot s-${c.status}"></span><span>${escapeHtml(COMPONENT_STATUS[c.status] || c.status)}</span>`));
  if (pct != null) right.appendChild(el('div', 'cuptime', pct.toFixed(2) + '%'));
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

function kpiTiles(data) {
  const comps = data.groups.flatMap((g) => g.components);
  const up = comps.filter((c) => c.status === 'operational').length;
  const upVals = comps.map((c) => c.uptime).filter((v) => v != null);
  const avgUptime = upVals.length ? upVals.reduce((a, b) => a + b, 0) / upVals.length : null;
  const rtVals = (data.metrics || [])
    .map((m) => (m.recent && m.recent.length ? m.recent[m.recent.length - 1].value : null))
    .filter((v) => v != null);
  const avgRt = rtVals.length ? rtVals.reduce((a, b) => a + b, 0) / rtVals.length : null;

  const tiles = [
    ['Аптайм', avgUptime == null ? '—' : avgUptime.toFixed(2) + '%'],
    ['Сервисы онлайн', up + ' / ' + comps.length],
    ['Активные инциденты', String(data.incidents.length)],
    ['Ср. время ответа', avgRt == null ? '—' : Math.round(avgRt) + ' мс'],
  ];
  const row = el('div', 'kpis');
  tiles.forEach(([label, val]) => {
    row.appendChild(el('div', 'kpi',
      `<div class="kpi-val">${escapeHtml(val)}</div><div class="kpi-label">${escapeHtml(label)}</div>`));
  });
  return row;
}

function incidentsOnDateAny(date) {
  return allIncidents.filter((inc) => {
    const s = dayOf(inc.created_at);
    const e = inc.resolved_at ? dayOf(inc.resolved_at) : todayStr();
    return s && date >= s && date <= e;
  });
}

function calLevel(u) {
  if (u == null) return 'none';
  if (u >= 99.9) return '4';
  if (u >= 99) return '3';
  if (u >= 97) return '2';
  if (u >= 90) return '1';
  return '0';
}

function calTooltip(ds) {
  const date = new Date(ds.calDate + 'T00:00:00');
  const label = date.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });
  const up = ds.calUp === '' ? 'Нет данных' : Number(ds.calUp).toFixed(2) + '% аптайм';
  let html = `<div class="tip-date">${escapeHtml(label)}</div><div class="tip-up">${escapeHtml(up)}</div>`;
  for (const inc of incidentsOnDateAny(ds.calDate)) {
    const badge = inc.status === 'resolved' ? 'none' : inc.impact;
    html += `<div class="tip-inc"><div class="t">${escapeHtml(inc.title)}` +
      `<span class="badge ${badge}">${escapeHtml(INCIDENT_STATUS[inc.status] || inc.status)}</span></div></div>`;
  }
  return html;
}

function calendarSource(data) {
  if (calSource === 'all') return data.calendar || [];
  const comp = data.groups.flatMap((g) => g.components).find((c) => c.key === calSource);
  return comp ? comp.days.map((d) => ({ date: d.date, uptime: d.uptime })) : (data.calendar || []);
}

function monthBlock(year, month, byDay) {
  const block = el('div', 'cal-block');
  const vals = Object.values(byDay).map((d) => d.uptime).filter((v) => v != null);
  const pct = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  const pctStr = pct == null ? '—' : (pct >= 99.995 ? '100%' : pct.toFixed(2) + '%');
  block.appendChild(el('div', 'cal-block-head',
    `<span class="cal-block-title">${MONTHS_FULL[month]} ${year}</span>` +
    `<span class="cal-block-pct">${pctStr}</span>`));

  const grid = el('div', 'cal-month-grid');
  const offset = (new Date(year, month, 1).getDay() + 6) % 7;
  const dim = new Date(year, month + 1, 0).getDate();
  for (let i = 0; i < offset; i++) grid.appendChild(el('span', 'cal-cell cal-empty'));
  for (let day = 1; day <= dim; day++) {
    const d = byDay[day];
    const c = el('span', 'cal-cell cal-' + (d ? calLevel(d.uptime) : 'none'));
    if (d) { c.dataset.calDate = d.date; c.dataset.calUp = d.uptime == null ? '' : String(d.uptime); }
    grid.appendChild(c);
  }
  block.appendChild(grid);
  return block;
}

function calendarSection(data) {
  const wrap = el('div', 'cal-wrap');
  const head = el('div', 'cal-head');
  head.appendChild(el('div', 'section-title', 'Аптайм'));

  const comps = data.groups.flatMap((g) => g.components);
  const sel = document.createElement('select');
  sel.className = 'cal-select';
  [['all', 'Все сервисы'], ...comps.map((c) => [c.key, c.name])].forEach(([v, label]) => {
    const o = document.createElement('option');
    o.value = v; o.textContent = label;
    if (v === calSource) o.selected = true;
    sel.appendChild(o);
  });
  sel.onchange = () => { calSource = sel.value; if (lastData) render(lastData); };
  head.appendChild(sel);
  wrap.appendChild(head);

  const src = calendarSource(data);
  if (!src.length) return wrap;

  // сгруппировать по месяцам, показать последние 3
  const monthsMap = new Map();  // "y-m" -> {y,m,byDay}
  for (const d of src) {
    const dt = new Date(d.date + 'T00:00:00');
    const key = dt.getFullYear() + '-' + dt.getMonth();
    if (!monthsMap.has(key)) monthsMap.set(key, { y: dt.getFullYear(), m: dt.getMonth(), byDay: {} });
    monthsMap.get(key).byDay[dt.getDate()] = d;
  }
  const months = [...monthsMap.values()].sort((a, b) => (a.y - b.y) || (a.m - b.m)).slice(-3);

  const blocks = el('div', 'cal-blocks');
  months.forEach((mo) => blocks.appendChild(monthBlock(mo.y, mo.m, mo.byDay)));
  wrap.appendChild(blocks);
  return wrap;
}

function render(data) {
  brand = data.brand || {};
  lastData = data;
  applyBrand();
  buildIndex(data);
  app.innerHTML = '';

  const banner = el('div', 'banner ' + data.overall.level);
  banner.appendChild(el('span', 'dot'));
  banner.appendChild(el('h1', null, escapeHtml(data.overall.label)));
  banner.appendChild(el('span', 'banner-time', 'обновлено ' + fmtTime(data.generated_at)));
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

  if ((data.calendar || []).length) app.appendChild(calendarSection(data));

  app.appendChild(el('div', 'section-title', `История за ${data.history_days} дней`));
  if (data.history.length) {
    data.history.forEach((i) => app.appendChild(renderIncident(i)));
  } else {
    app.appendChild(el('div', 'empty', 'Инцидентов за период не было.'));
  }

}

// ---- тултип: делегирование на #app ------------------------------------------

app.addEventListener('mouseover', (e) => {
  const tick = e.target.closest('.utick');
  if (tick) { showTip(tickTooltip(tick.dataset), tick.getBoundingClientRect()); return; }
  const cell = e.target.closest('.cal-cell');
  if (cell && cell.dataset.calDate) { showTip(calTooltip(cell.dataset), cell.getBoundingClientRect()); }
});
app.addEventListener('mouseout', (e) => {
  if (e.target.closest('.utick') || e.target.closest('.cal-cell')) hideTip();
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
