// Линейные графики времени ответа из реальных проверок. Гранулярность — как у аптайма.
import { escapeHtml } from './api.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const W = 640;
const H = 120;
const PAD_T = 12;
const PAD_B = 10;

const shortDate = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { day: 'numeric', month: 'short' });
const shortTime = (iso) => new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

function chartSvg(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = (max - min) || 1;
  const lo = min - span * 0.25;
  const hi = max + span * 0.25;
  const n = values.length;
  const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * W);
  const y = (v) => PAD_T + (1 - (v - lo) / (hi - lo)) * (H - PAD_T - PAD_B);

  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'metric-svg');

  for (let g = 0; g <= 2; g++) {
    const gy = PAD_T + (g / 2) * (H - PAD_T - PAD_B);
    const ln = document.createElementNS(SVGNS, 'line');
    ln.setAttribute('x1', 0); ln.setAttribute('x2', W); ln.setAttribute('y1', gy); ln.setAttribute('y2', gy);
    ln.setAttribute('class', 'metric-grid');
    ln.setAttribute('vector-effect', 'non-scaling-stroke');
    svg.appendChild(ln);
  }

  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
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

export function metricCard(metric, gran) {
  const fromPeriod = gran === '24h'
    ? (metric.recent || [])
    : (gran === '30d' ? (metric.days || []).slice(-30) : (metric.days || []));
  let points = fromPeriod
    .filter((p) => p.value != null)
    .map((p) => ({ label: p.time || p.date, value: p.value, live: !!p.time }));

  // если по выбранному периоду точек мало — показываем живую линию из последних замеров
  if (points.length < 2 && metric.recent && metric.recent.length >= 2) {
    points = metric.recent
      .filter((p) => p.value != null)
      .map((p) => ({ label: p.time, value: p.value, live: true }));
  }

  const card = document.createElement('div');
  card.className = 'metric';
  const cur = points.length ? points[points.length - 1].value : null;
  card.innerHTML =
    `<div class="metric-head"><span class="metric-name">${escapeHtml(metric.name)} · response time</span>` +
    `<span class="metric-cur">${cur == null ? '—' : Math.round(cur) + ' ' + escapeHtml(metric.unit)}</span></div>`;

  if (points.length < 2) {
    const note = points.length ? 'Collecting…' : 'No data';
    card.appendChild(Object.assign(document.createElement('div'), { className: 'muted metric-empty', textContent: note }));
    return card;
  }

  const vals = points.map((p) => p.value);
  card.appendChild(chartSvg(vals));

  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  card.appendChild(Object.assign(document.createElement('div'), {
    className: 'metric-stats',
    innerHTML: `<span>min ${Math.round(mn)}</span><span>avg ${Math.round(avg)}</span>` +
      `<span>max ${Math.round(mx)} ${escapeHtml(metric.unit)}</span>`,
  }));

  const fmt = points[0].live ? shortTime : shortDate;
  const xr = document.createElement('div');
  xr.className = 'metric-x';
  const mid = points[Math.floor(points.length / 2)];
  xr.innerHTML =
    `<span>${escapeHtml(fmt(points[0].label))}</span>` +
    `<span>${escapeHtml(fmt(mid.label))}</span>` +
    `<span>${escapeHtml(fmt(points[points.length - 1].label))}</span>`;
  card.appendChild(xr);
  return card;
}
