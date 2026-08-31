// Полоска аптайма как SVG — равномерное масштабирование даёт ровные бары при любом их числе.
import { escapeHtml } from './api.js';

const SVGNS = 'http://www.w3.org/2000/svg';

// entries: [{date|time, status, uptime}]; gran: 'day' | '24h'
export function uptimeBar(entries, key, gran, marked) {
  const n = entries.length || 1;
  const unit = 10;   // ширина ячейки в координатах viewBox
  const gap = 2;
  const height = 30;
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'ubar');
  svg.setAttribute('viewBox', `0 0 ${n * unit} ${height}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Availability history');
  entries.forEach((e, i) => {
    const ts = e.date || e.time;
    const rect = document.createElementNS(SVGNS, 'rect');
    rect.setAttribute('x', i * unit);
    rect.setAttribute('y', 0);
    rect.setAttribute('width', unit - gap);
    rect.setAttribute('height', height);
    rect.setAttribute('rx', 1.4);
    rect.setAttribute('class', 'utick u-' + e.status + (marked && marked.has(ts) ? ' has-incident' : ''));
    rect.dataset.key = key;
    rect.dataset.gran = gran;
    rect.dataset.ts = ts;
    rect.dataset.status = e.status;
    rect.dataset.uptime = e.uptime == null ? '' : String(e.uptime);
    svg.appendChild(rect);
  });
  return svg;
}

export function uptimeMeta(gran, count) {
  const meta = document.createElement('div');
  meta.className = 'umeta';
  const left = gran === '24h' ? `${count}h ago` : `${count} days ago`;
  const right = gran === '24h' ? 'now' : 'today';
  meta.innerHTML = `<span>${escapeHtml(left)}</span><span>${escapeHtml(right)}</span>`;
  return meta;
}
