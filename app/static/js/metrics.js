// Линейные графики метрик (время ответа) в духе Atlassian System Metrics.
import { escapeHtml } from './api.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const W = 640;
const H = 120;
const PAD_T = 12;
const PAD_B = 10;

function fmtVal(v, unit) {
  return Math.round(v) + ' ' + unit;
}

function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function chartSvg(points) {
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const lo = min - span * 0.25;
  const hi = max + span * 0.25;

  const n = points.length;
  const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * W);
  const y = (v) => PAD_T + (1 - (v - lo) / (hi - lo)) * (H - PAD_T - PAD_B);

  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.classList.add('metric-svg');

  // горизонтальная сетка
  for (let g = 0; g <= 2; g++) {
    const gy = PAD_T + (g / 2) * (H - PAD_T - PAD_B);
    const line = document.createElementNS(SVGNS, 'line');
    line.setAttribute('x1', 0); line.setAttribute('x2', W);
    line.setAttribute('y1', gy); line.setAttribute('y2', gy);
    line.setAttribute('class', 'metric-grid');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    svg.appendChild(line);
  }

  const line = points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ');

  const area = document.createElementNS(SVGNS, 'polygon');
  area.setAttribute('points', `0,${H} ${line} ${W},${H}`);
  area.setAttribute('class', 'metric-area');
  svg.appendChild(area);

  const poly = document.createElementNS(SVGNS, 'polyline');
  poly.setAttribute('points', line);
  poly.setAttribute('class', 'metric-line');
  poly.setAttribute('vector-effect', 'non-scaling-stroke');
  svg.appendChild(poly);

  return svg;
}

export function metricCard(metric, days) {
  const points = metric.points.slice(-days);
  const card = document.createElement('div');
  card.className = 'metric';
  const cur = points.length ? points[points.length - 1].value : null;
  card.innerHTML =
    `<div class="metric-head">` +
    `<span class="metric-name">${escapeHtml(metric.name)} · время ответа</span>` +
    `<span class="metric-cur">${cur == null ? '—' : escapeHtml(fmtVal(cur, metric.unit))}</span>` +
    `</div>`;
  card.appendChild(chartSvg(points));
  if (points.length > 1) {
    const xr = document.createElement('div');
    xr.className = 'metric-x';
    const mid = points[Math.floor(points.length / 2)];
    xr.innerHTML =
      `<span>${escapeHtml(shortDate(points[0].date))}</span>` +
      `<span>${escapeHtml(shortDate(mid.date))}</span>` +
      `<span>${escapeHtml(shortDate(points[points.length - 1].date))}</span>`;
    card.appendChild(xr);
  }
  return card;
}
