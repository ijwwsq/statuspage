// Полоска аптайма за N дней. Каждая засечка несёт data-* для тултипа.
import { escapeHtml } from './api.js';

export function uptimeBar(days, key, incidentDates) {
  const bar = document.createElement('div');
  bar.className = 'ubar';
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', 'История доступности по дням');
  for (const d of days) {
    const tick = document.createElement('span');
    const hasInc = incidentDates && incidentDates.has(d.date);
    tick.className = 'utick u-' + d.status + (hasInc ? ' has-incident' : '');
    tick.dataset.key = key;
    tick.dataset.date = d.date;
    tick.dataset.status = d.status;
    tick.dataset.uptime = d.uptime == null ? '' : String(d.uptime);
    bar.appendChild(tick);
  }
  return bar;
}

export function uptimeMeta(days, uptimePct) {
  const meta = document.createElement('div');
  meta.className = 'umeta';
  const pct = uptimePct == null ? '—' : uptimePct.toFixed(2) + '% аптайм';
  meta.innerHTML =
    `<span>${escapeHtml(days)} дней назад</span>` +
    `<span>${escapeHtml(pct)}</span>` +
    `<span>сегодня</span>`;
  return meta;
}
