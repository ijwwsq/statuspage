// Полоска аптайма. Работает в двух гранулярностях: по дням и по часам (24ч).
import { escapeHtml } from './api.js';

// entries: [{date|time, status, uptime}]; gran: 'day' | '24h'
export function uptimeBar(entries, key, gran, marked) {
  const bar = document.createElement('div');
  bar.className = 'ubar';
  bar.style.gridTemplateColumns = `repeat(${entries.length}, minmax(0, 1fr))`;
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', 'История доступности');
  for (const e of entries) {
    const ts = e.date || e.time;
    const hasInc = marked && marked.has(ts);
    const tick = document.createElement('span');
    tick.className = 'utick u-' + e.status + (hasInc ? ' has-incident' : '');
    tick.dataset.key = key;
    tick.dataset.gran = gran;
    tick.dataset.ts = ts;
    tick.dataset.status = e.status;
    tick.dataset.uptime = e.uptime == null ? '' : String(e.uptime);
    bar.appendChild(tick);
  }
  return bar;
}

export function uptimeMeta(gran, count) {
  const meta = document.createElement('div');
  meta.className = 'umeta';
  const left = gran === '24h' ? `${count} ч назад` : `${count} дней назад`;
  const right = gran === '24h' ? 'сейчас' : 'сегодня';
  meta.innerHTML = `<span>${escapeHtml(left)}</span><span>${escapeHtml(right)}</span>`;
  return meta;
}
