// Shared helpers + chart styling for every page.
const INK = '#141413', LINE = '#cccbc8', LINE_STRONG = '#87867f', CARD = '#faf9f5';
// Validated pair (colour-blind safe): actual = sienna solid, predicted/second = ochre dashed.
const SERIES = {primary: '#944123', secondary: '#cfa529'};
const LEVELS = ['Low', 'Moderate', 'High', 'Severe'];

Chart.defaults.animation = false;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.font.family = "Inter, system-ui, 'Segoe UI', Arial, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = LINE_STRONG;
Chart.defaults.borderColor = LINE + '99';
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 5;
Chart.defaults.elements.bar.borderRadius = 4;
Chart.defaults.plugins.legend.labels.boxWidth = 14;
Chart.defaults.plugins.legend.labels.boxHeight = 2;
Chart.defaults.plugins.legend.labels.color = INK;
Chart.defaults.plugins.legend.labels.filter = (item, data) => !data.datasets[item.datasetIndex].directLabel;
Object.assign(Chart.defaults.plugins.tooltip, {
  backgroundColor: INK, titleColor: CARD, bodyColor: CARD, cornerRadius: 8, padding: 10,
  titleFont: {weight: '600'}, displayColors: true, boxPadding: 4,
});

// Draws a dataset's `directLabel` at the right end of its line (used for threshold lines).
Chart.register({
  id: 'directLabels',
  afterDatasetsDraw(c) {
    const {ctx, chartArea} = c;
    c.data.datasets.forEach((ds, i) => {
      if (!ds.directLabel || !c.isDatasetVisible(i)) return;
      const pts = c.getDatasetMeta(i).data;
      if (!pts.length) return;
      ctx.save();
      ctx.font = "600 11px Inter, system-ui, sans-serif";
      ctx.fillStyle = LINE_STRONG;
      ctx.textAlign = 'right';
      ctx.fillText(ds.directLabel, chartArea.right - 4, pts[pts.length - 1].y - 5);
      ctx.restore();
    });
  },
});

// A threshold line: neutral, dotted, labelled directly instead of by colour.
function thresholdLine(labels, value, text) {
  return {label: text, data: labels.map(() => value), borderColor: LINE_STRONG, borderWidth: 1,
          borderDash: [2, 4], directLabel: text, pointHoverRadius: 0};
}

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

// Congestion level: colour swatch + label text (never colour alone).
function level(name) {
  if (!name) return '–';
  return `<span class="level"><i style="background:${LEVEL_COLORS[name]}"></i>${esc(name)}</span>`;
}

function levelLegend() {
  return LEVELS.map(level).join('');
}

const charts = {};
function chart(id, config) {            // create or replace a chart on a canvas
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
  return charts[id];
}

// Fills a <select> with locations; calls onChange(id) now and on every change.
async function locationSelect(selectEl, onChange) {
  const locs = await getJSON('/api/locations');
  selectEl.innerHTML = locs.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
  const fromUrl = new URLSearchParams(location.search).get('location');
  if (fromUrl) selectEl.value = fromUrl;
  selectEl.onchange = () => onChange(selectEl.value);
  onChange(selectEl.value);
  return locs;
}

function showError(e) {
  const box = document.createElement('div');
  box.className = 'flash error';
  box.textContent = 'Could not load data: ' + e.message;
  document.querySelector('main').prepend(box);
}

const fmtInt = v => v === null || v === undefined ? '–' : Math.round(v).toLocaleString();
