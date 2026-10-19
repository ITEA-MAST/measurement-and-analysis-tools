/* ==========================================================================
   Carbon Atlas — portal
   Plain DOM and inline SVG. No libraries.

   The portal reads `data/*.json` and makes no request to a data source.
   `atlas export` writes those files from the store. ARCHITECTURE.md.

   Three files hold every country: `daily_all`, `hours` and `profile`. A panel
   that ranks 33 countries reads one file and indexes into it. `daily/<ISO>`
   and `recent/<ISO>` are read only when the country is selected.
   ========================================================================== */

/* ---------- state -------------------------------------------------------- */
const S = {
  tab: 'overview',
  date: null,            /* set from the store at boot */
  hour: 12,
  period: 30,
  agg: 'hour',
  source: null,          /* the collected source id */
  q: '',
  hideEmpty: true,
  band: true,
  tray: ['DE', 'FR', 'PL', 'SE'],
  seasonCountry: 'DE',
  fcKey: null,           /* the forecast curve: 'ISO|source_id' */
  raw: { country: 'DE', view: 'records' },
  srcFilter: 'all',
  srcCat: 'all',
  calc: { kwh: 1000, pattern: 'flat', start: 9, end: 17, pue: 1.39, base: 'DE', pool: 'tray' }
};
const TRAY_MAX = 6;

/* The tile map. [column, row] on a 9 x 8 grid, placed by geography. */
const GP = {
  AT: [5,5], BA: [6,7], BE: [4,4], BG: [8,6], CH: [4,5], CY: [9,8], CZ: [6,4],
  DE: [5,3], DK: [5,2], EE: [7,2], ES: [2,6], FI: [7,1], FR: [3,5], GB: [3,2],
  GE: [9,6], GR: [8,8], HR: [6,6], HU: [6,5], IE: [2,3], IT: [4,6], LT: [8,4],
  LU: [5,4], LV: [7,3], MD: [8,5], ME: [5,7], MK: [8,7], NL: [4,3], NO: [5,1],
  PL: [6,3], PT: [1,6], RO: [7,5], RS: [7,6], SE: [6,1], SI: [5,6], SK: [7,4],
  XK: [7,7]
};

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

/* ---------- the loaded files --------------------------------------------- */
const D = {};
const CACHE = { daily: {}, recent: {} };

/* ---------- format and colour -------------------------------------------- */
const RAMP = [[0,'#49B39C'],[100,'#A4D9CD'],[250,'#E9C23B'],[450,'#E2807E'],[700,'#D33227'],[1200,'#7A1D16']];
const RAMP_MAX = RAMP[RAMP.length - 1][0];
function hex2rgb(h) { return [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)]; }
function ciColor(v) {
  if (v == null || isNaN(v)) return '#D0DAE1';
  v = Math.max(0, Math.min(RAMP_MAX, v));
  for (let i = 1; i < RAMP.length; i++) {
    if (v <= RAMP[i][0]) {
      const [a0, ac] = RAMP[i-1], [b0, bc] = RAMP[i];
      const t = (v - a0) / (b0 - a0), A = hex2rgb(ac), B = hex2rgb(bc);
      return `rgb(${Math.round(A[0]+(B[0]-A[0])*t)},${Math.round(A[1]+(B[1]-A[1])*t)},${Math.round(A[2]+(B[2]-A[2])*t)})`;
    }
  }
  return '#7A1D16';
}
/* a colour inside a band, for a grid that must show small differences */
function bandColor(v, lo, hi) {
  if (v == null || isNaN(v) || hi <= lo) return '#D0DAE1';
  const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
  return ciColor(RAMP[0][0] + t * RAMP_MAX);
}
/* The legend gradient, built from RAMP and given to the stylesheet as
   `--ca-ramp`. The stops sit at the value of each ramp point, so the legend
   and a tile of the same value carry the same colour. */
function rampGradient() {
  return 'linear-gradient(90deg,' +
    RAMP.map(p => `${p[1]} ${(p[0] / RAMP_MAX * 100).toFixed(3)}%`).join(',') + ')';
}

/* The ink of a coloured cell.

   The choice takes the colour that the cell really has, and not a threshold on
   the value. The ramp stays light up to about 600, and a band colour does not
   follow the value at all. The test is the WCAG contrast ratio: the dark ink
   wins when it beats white on that background. */
const INK_DARK_LUM = 0.00733;      /* the relative luminance of --wk-text, #00152E */
function relLuminance(rgb) {
  const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
}
function darkInk(colour) {
  const text = String(colour);
  let rgb = null;
  if (text[0] === '#') rgb = hex2rgb(text);
  else { const m = text.match(/\d+/g); if (m && m.length >= 3) rgb = m.slice(0, 3).map(Number); }
  if (!rgb) return false;
  const l = relLuminance(rgb);
  return (l + 0.05) / (INK_DARK_LUM + 0.05) > 1.05 / (l + 0.05);
}
const fmt = (v, d = 0) => (v == null || isNaN(v)) ? '—'
  : Number(v).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
const PALETTE = ['#01316C','#D33227','#1FA7B3','#49B39C','#436B84','#E9C23B'];
const pad2 = n => String(n).padStart(2, '0');
/* "1 region" and "4 regions". A count on the page never reads "region(s)". */
const plural = (n, word, many) => `${fmt(n)} ${n === 1 ? word : (many || word + 's')}`;
/* the verb that goes with that count. A count of 1 takes the singular verb. */
const verb = (n, one, many) => n === 1 ? one : many;

/* ---------- dates, all in UTC -------------------------------------------- */
const DAY_MS = 86400000;
function dayNum(text) {                     /* 'YYYY-MM-DD' -> days since epoch */
  const [y, m, d] = text.split('-').map(Number);
  return Date.UTC(y, m - 1, d) / DAY_MS;
}
function dayText(num) {
  const dt = new Date(num * DAY_MS);
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth()+1)}-${pad2(dt.getUTCDate())}`;
}
function shortDay(text) {
  const [y, m, d] = text.split('-').map(Number);
  return `${d} ${MONTHS[m-1]}`;
}
function prettyDay(text) {
  const [y, m, d] = text.split('-').map(Number);
  const names = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  return `${names[new Date(Date.UTC(y, m-1, d)).getUTCDay()]} ${d} ${MONTHS[m-1]} ${y}`;
}
function tsNum(text) {                      /* 'YYYY-MM-DD HH:MM:SS' -> ms UTC */
  const [dpart, tpart] = String(text).replace('T', ' ').split(' ');
  const [y, m, d] = dpart.split('-').map(Number);
  const [hh, mm, ss] = (tpart || '00:00:00').split(':').map(Number);
  return Date.UTC(y, m - 1, d, hh || 0, mm || 0, ss || 0);
}

/* ---------- indexes into the dense files ---------------------------------

   Every dense file is keyed by the source first, and by the country second.
   Two publishers give a different number for the same hour of the same
   country, and that difference is the measurement. A panel reads the arrays
   of the selected source, and of no other source. */
let DAY0 = 0, NDAY = 0, HOUR0 = 0, NHOUR = 0;

function dayFile(source) { return (D.dailyAll.sources || {})[source || S.source] || {}; }
function hourFile(source) { return (D.hours.sources || {})[source || S.source] || {}; }
function profFile(source) { return (D.profile.sources || {})[source || S.source] || {}; }
/* what the store holds for this country, from this source. The source
   defaults to the selected one. The coverage table names another source,
   because it gives one row for each source and not for the selected one. */
function srcMeta(iso, source) { return ((BY_ISO[iso] || {}).sources || {})[source || S.source] || null; }
function srcRows(iso) { const m = srcMeta(iso); return m ? m.rows : 0; }

function dayIndex(text) { return dayNum(text) - DAY0; }
function dayIn(text) { const i = dayIndex(text); return i >= 0 && i < NDAY; }
function dayMean(iso, text) {
  const c = dayFile()[iso]; if (!c) return null;
  const i = dayIndex(text);
  return (i >= 0 && i < NDAY) ? c.mean_unweighted[i] : null;
}
function dayRange(iso, text) {
  const c = dayFile()[iso]; if (!c) return [null, null];
  const i = dayIndex(text);
  return (i >= 0 && i < NDAY) ? [c.lo[i], c.hi[i]] : [null, null];
}
function hourIndex(text, hour) { return Math.round((tsNum(text + ' 00:00:00') + hour * 3600000 - HOUR0) / 3600000); }
function hourVal(iso, text, hour, source) {
  const a = hourFile(source)[iso]; if (!a) return null;
  const i = hourIndex(text, hour);
  return (i >= 0 && i < NHOUR) ? a[i] : null;
}
function hoursIn(text) { const i = hourIndex(text, 0); return i >= 0 && i + 23 < NHOUR; }

/* the value that a ranking panel shows for one country */
function repValue(iso) {
  if (S.agg === 'hour') return hourVal(iso, S.date, S.hour);
  const list = windowDates().map(d => dayMean(iso, d)).filter(v => v != null);
  return list.length ? list.reduce((a, b) => a + b, 0) / list.length : null;
}

/* the days of the analysis window, clipped to the file */
function windowDates() {
  const end = dayNum(S.date), out = [];
  for (let n = S.period - 1; n >= 0; n--) {
    const t = dayText(end - n);
    if (dayIn(t)) out.push(t);
  }
  return out;
}
/* a long window is drawn with fewer points, so a chart stays readable */
function sampled(list, max) {
  if (list.length <= max) return list;
  const step = Math.ceil(list.length / max), out = [];
  for (let i = 0; i < list.length; i += step) out.push(list[i]);
  if (out[out.length-1] !== list[list.length-1]) out.push(list[list.length-1]);
  return out;
}

/* ---------- the country list --------------------------------------------- */
let COUNTRIES = [];          /* every country of the zone model */
let BY_ISO = {};
let WITH_DATA = [];          /* the countries that the store holds for this source */
let WITH_DAYS = [];          /* those of them that the exported day window covers */
let OUT_OF_WINDOW = [];      /* the rest: history in the store, nothing in the window */

function countryName(iso) { return (BY_ISO[iso] || {}).name || iso; }
function hasData(iso) { return srcRows(iso) > 0; }

/* The countries that the selected source reports. A source change changes
   these lists, so the tray and every country control follow them.

   `daily_all` and `hours` hold a window of the newest days, and `profile`,
   `monthly` and the per-country files hold all the history. A country whose
   last record is older than the window therefore has a Time of year tab and a
   Raw data tab, and no value on any panel that reads the window. */
function refreshCountries() {
  const day = dayFile();
  WITH_DATA = COUNTRIES.filter(c => srcRows(c.iso)).map(c => c.iso);
  WITH_DAYS = WITH_DATA.filter(iso => day[iso]);
  OUT_OF_WINDOW = WITH_DATA.filter(iso => !day[iso]);
}

/* ==========================================================================
   A country with a measured defect in its values

   REFERENCE.md section 2 gives the strongest rule of the project: "Do not
   quote a Georgian number." The rule was on paper only. Every panel of this
   page quoted the number with no mark at all.

   The flag never hides a value and never drops a country. The page shows the
   number and states the defect beside it. A reader who sees the number sees
   the flag at the same time, on the ranking table, on the tile, on the
   compare card, on the season panel, in the workload calculator and on the
   Raw data tab.

   ⚠ The flag comes from the data where the data holds it. A country entry of
   `register.json` can carry a `quality` object, and `dataFlag` reads it
   first. No entry carries one on 2026-09-23, so the list below is the
   fallback of today. Delete a country from the list on the day that the
   register carries it, or the page states the defect two times.
   ========================================================================== */
const DATA_FLAG = {
  /* energy-charts GE. Measured on 2026-09-23 and recorded in REFERENCE.md
     section 2. The four guards of the collector all pass it: 3.0 g is inside
     the store band, and the step, the field set and the count are right. */
  GE: {
    mark: 'floor at 3.0',
    rule: 'Do not quote a Georgian number.',
    why: '2,254 of the 28,975 records of Georgia sit at exactly 3.0 gCO₂eq/kWh, which is 7.8 %. ' +
         '27.9 % of them sit at or below 5.0 g. IPCC AR5 Annex III puts the lifecycle median of ' +
         'hydro near 24 gCO₂eq/kWh, so no national grid reaches 3 g under that table. The 723 ' +
         'records after 2026-08-23 hold no 3.0 value, and the older records keep the floor. ' +
         'REFERENCE.md section 2.'
  }
};
function dataFlag(iso) {
  const given = (BY_ISO[iso] || {}).quality;   /* the register, on the day that it carries one */
  return given || DATA_FLAG[iso] || null;
}
/* the red badge of a flagged country. It goes beside the name of the country,
   and the tooltip states the rule and the measurement behind it. */
function flagBadge(iso) {
  const f = dataFlag(iso);
  if (!f) return '';
  return ` <span class="badge group" ${tipAttr(esc(f.rule) + ' ' + esc(f.why))}>${esc(f.mark)}</span>`;
}
/* one line of a tooltip, for a tile and for any other mark with no room for a
   badge of its own */
function flagTipRow(iso) {
  const f = dataFlag(iso);
  return f ? `<div class="tr"><span>⚠ ${esc(f.rule)} ${esc(f.why)}</span></div>` : '';
}
/* the callout of every flagged country of a list. `brief` gives the rule
   alone, for a panel that carries the badge and its tooltip as well. */
function flagCallout(isos, brief) {
  const list = (isos || []).filter(iso => dataFlag(iso));
  if (!list.length) return '';
  const text = list.map(iso => {
    const f = dataFlag(iso);
    return `${esc(countryName(iso))}: ${esc(f.rule)}${brief ? '' : ' ' + esc(f.why)}`;
  }).join(' ');
  return `<div class="callout warn"><span class="ico">⚠</span><span>${text}` +
         ` The page keeps the value on screen and states the defect beside it.</span></div>`;
}

/* ==========================================================================
   The hover tooltip

   A `title` attribute is not usable on this page. It waits about a second,
   and a cell of the 365-day strip is 2 px wide, so the pointer leaves the
   cell before the tooltip opens. Every tooltip here is a `data-tip`
   attribute, and one box shows it at once. The attribute holds HTML, so a
   chart can give one row for each series.
   ========================================================================== */
/* The unit of the selected source, and not one unit for the whole page.
   energy-charts gives gCO2eq/kWh. NESO, RTE and Energinet give gCO2/kWh, and
   that is a different number. `meta.sources[].unit` comes from the stored
   rows. */
const SOURCE_UNIT = {};        /* for the screen: gCO₂eq/kWh */
const SOURCE_UNIT_ASCII = {};  /* for a CSV file: gCO2eq/kWh */
/* The `eq` substring stays as it is. The CO₂ against CO₂eq test below reads it. */
const pretty = u => String(u || '').replace('CO2', 'CO₂');
function unitOf(source) { return SOURCE_UNIT[source || S.source] || 'gCO₂eq/kWh'; }
function unitAscii(source) { return SOURCE_UNIT_ASCII[source || S.source] || 'gCO2eq/kWh'; }
/* The gas that the source reports. A unit with no `eq` counts CO₂ only. */
function gasOf(source) { return unitOf(source).indexOf('eq') < 0 ? 'CO₂' : 'CO₂eq'; }
function massUnitOf(source) { return 'kg ' + gasOf(source); }

/* one line of a tooltip: a colour mark, a name and a value */
function tipRow(colour, name, value, unit) {
  return `<div class="tr"><span>${colour ? `<i style="background:${colour}"></i> ` : ''}${esc(name)}</span>` +
         `<b>${value}${unit ? ' ' + unit : ''}</b></div>`;
}
function tipHead(text) { return `<span class="tk">${esc(text)}</span>`; }
/* Put the HTML in the attribute. The markup uses double quotes, so change
   each one to &quot; and the attribute stays closed. */
const tipAttr = html => `data-tip="${String(html).replace(/"/g, '&quot;')}"`;

function wireTip() {
  const box = document.getElementById('tip');
  let held = null;
  const hide = () => { box.classList.remove('on'); held = null; };
  const place = event => {
    const pad = 14, w = box.offsetWidth, h = box.offsetHeight;
    let left = event.clientX + pad, top = event.clientY + pad;
    if (left + w > window.innerWidth - 8) left = event.clientX - w - pad;
    if (top + h > window.innerHeight - 8) top = event.clientY - h - pad;
    box.style.left = Math.max(8, left) + 'px';
    box.style.top = Math.max(8, top) + 'px';
  };
  document.addEventListener('mouseover', event => {
    const target = event.target.closest ? event.target.closest('[data-tip]') : null;
    if (!target) return;
    held = target;
    box.innerHTML = target.getAttribute('data-tip');
    box.classList.add('on');
    place(event);
  });
  document.addEventListener('mousemove', event => { if (held) place(event); });
  document.addEventListener('mouseout', event => {
    if (held && !held.contains(event.relatedTarget)) hide();
  });
  window.addEventListener('scroll', hide, true);
  window.addEventListener('blur', hide);
}

/* ==========================================================================
   Chart primitives
   ========================================================================== */
function lineChart(series, xLabels, opts) {
  opts = opts || {};
  const W = opts.w || 560, H = opts.h || 220, ml = 46, mr = 12, mt = 10, mb = 26;
  const iw = W - ml - mr, ih = H - mt - mb;
  const n = xLabels.length;
  let lo = Infinity, hi = -Infinity;
  series.forEach(s => {
    s.values.forEach(v => { if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; } });
    if (s.band) s.band.forEach(b => {
      if (b && b[0] != null) { if (b[0] < lo) lo = b[0]; if (b[1] > hi) hi = b[1]; }
    });
  });
  if (!isFinite(lo)) return '<div class="empty">No record in this range.</div>';
  const pad = (hi - lo) * 0.12 || 10;
  lo = Math.max(0, lo - pad); hi = hi + pad;
  const x = i => ml + iw * (n === 1 ? 0.5 : i / (n - 1));
  const y = v => mt + ih - ih * (v - lo) / (hi - lo);
  let g = '';
  for (let t = 0; t <= 4; t++) {
    const vv = lo + (hi - lo) * t / 4, yy = y(vv);
    g += `<line class="gridline" x1="${ml}" x2="${W-mr}" y1="${yy}" y2="${yy}"/>`;
    g += `<text x="${ml-6}" y="${yy+3}" text-anchor="end" fill="#33475B" font-size="9.5">${fmt(vv)}</text>`;
  }
  const every = Math.max(1, Math.ceil(n / 13));
  xLabels.forEach((l, i) => {
    if (i % every !== 0 && i !== n - 1) return;
    g += `<text x="${x(i)}" y="${H-8}" text-anchor="middle" fill="#33475B" font-size="9.5">${esc(l)}</text>`;
  });
  if (opts.markIndex != null && opts.markIndex >= 0) {
    g += `<line x1="${x(opts.markIndex)}" x2="${x(opts.markIndex)}" y1="${mt}" y2="${mt+ih}"
           stroke="#00152E" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`;
  }
  (opts.marks || []).forEach(i => {
    g += `<rect x="${(x(i)-2)}" y="${mt}" width="4" height="${ih}" fill="#01316C" opacity=".07"/>`;
  });
  series.forEach(s => {
    if (!s.band) return;
    let run = [];
    const flush = () => {
      if (run.length > 1) {
        const up = run.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${y(p[2]).toFixed(1)}`).join(' ');
        const dn = run.slice().reverse().map(p => `L${p[0].toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
        g += `<path d="${up} ${dn} Z" fill="${s.color}" opacity=".13"/>`;
      }
      run = [];
    };
    s.band.forEach((b, i) => {
      if (b && b[0] != null && isFinite(b[0])) run.push([x(i), b[0], b[1]]); else flush();
    });
    flush();
  });
  series.forEach(s => {
    let d = '', open = false;
    s.values.forEach((v, i) => {
      if (v == null) { open = false; return; }
      d += `${open ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      open = true;
    });
    g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2.1}"
           stroke-linejoin="round" ${s.dash ? `stroke-dasharray="${s.dash}"` : ''}/>`;
    if (n <= 48) s.values.forEach((v, i) => {
      if (v == null) return;
      g += `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.5" fill="${s.color}"/>`;
    });
  });
  /* The hover layer. One column for each point, so the tooltip opens
     anywhere in the chart and not on a 2.5 px dot only. */
  const unit = opts.unit || unitOf();
  const colW = n === 1 ? iw : iw / (n - 1);
  for (let i = 0; i < n; i++) {
    const lines = series.map(s => s.values[i] == null ? '' :
      tipRow(s.color, s.label, fmt(s.values[i], 1), unit)).filter(Boolean).join('');
    const left = Math.max(ml, x(i) - colW / 2);
    g += `<rect class="hit" fill="transparent" x="${left.toFixed(1)}" y="${mt}"
           width="${Math.min(colW, W - mr - left).toFixed(1)}" height="${ih}"
           ${tipAttr(tipHead(opts.xHead ? opts.xHead(xLabels[i], i) : xLabels[i]) +
             (lines || 'No record at this point.'))}/>`;
  }
  const legend = series.map(s =>
    `<span style="display:inline-flex;align-items:center;gap:5px;font-size:11.5px">
       <i style="width:11px;height:3px;background:${s.color};display:inline-block;border-radius:2px"></i>${esc(s.label)}</span>`
  ).join('');
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">${g}</svg>
          <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:6px">${legend}</div>`;
}

/* a bar chart of one value for each label, with an optional low-high whisker */
function barChart(rows, opts) {
  opts = opts || {};
  const W = opts.w || 1120, H = opts.h || 260, ml = 46, mr = 12, mt = 10, mb = 26;
  const iw = W - ml - mr, ih = H - mt - mb;
  let lo = 0, hi = -Infinity;
  rows.forEach(r => {
    [r.value, r.hi, r.lo].forEach(v => { if (v != null && v > hi) hi = v; });
  });
  if (!isFinite(hi)) return '<div class="empty">No record in this range.</div>';
  hi *= 1.08;
  const gap = iw / rows.length, bw = Math.max(2, gap * 0.66);
  const y = v => mt + ih - ih * (v - lo) / (hi - lo);
  let g = '';
  for (let t = 0; t <= 4; t++) {
    const vv = lo + (hi - lo) * t / 4, yy = y(vv);
    g += `<line class="gridline" x1="${ml}" x2="${W-mr}" y1="${yy}" y2="${yy}"/>`;
    g += `<text x="${ml-6}" y="${yy+3}" text-anchor="end" fill="#33475B" font-size="9.5">${fmt(vv)}</text>`;
  }
  rows.forEach((r, i) => {
    const cx = ml + gap * i + gap / 2;
    if (r.value != null) {
      g += `<rect x="${(cx-bw/2).toFixed(1)}" y="${y(r.value).toFixed(1)}" width="${bw.toFixed(1)}"
             height="${Math.max(0, mt+ih-y(r.value)).toFixed(1)}" fill="${r.color || ciColor(r.value)}" rx="2"/>`;
    }
    if (r.lo != null && r.hi != null) {
      g += `<line x1="${cx}" x2="${cx}" y1="${y(r.hi)}" y2="${y(r.lo)}" stroke="#00152E" stroke-width="1" opacity=".55"/>`;
      g += `<line x1="${cx-4}" x2="${cx+4}" y1="${y(r.hi)}" y2="${y(r.hi)}" stroke="#00152E" stroke-width="1" opacity=".55"/>`;
      g += `<line x1="${cx-4}" x2="${cx+4}" y1="${y(r.lo)}" y2="${y(r.lo)}" stroke="#00152E" stroke-width="1" opacity=".55"/>`;
    }
    const every = Math.max(1, Math.ceil(rows.length / 24));
    if (i % every === 0)
      g += `<text x="${cx.toFixed(1)}" y="${H-8}" text-anchor="middle" font-size="9.5" fill="#33475B">${esc(r.label)}</text>`;
    /* the hover column, the full height of the chart */
    g += `<rect class="hit" fill="transparent" x="${(ml + gap * i).toFixed(1)}" y="${mt}" width="${gap.toFixed(1)}"
           height="${ih}" ${tipAttr(r.tip || (tipHead(r.label) +
             (r.value == null ? 'No record.' : tipRow(null, 'Value', fmt(r.value, 1), opts.unit || unitOf()))))}/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">${g}</svg>`;
}

/* a grid of coloured cells with the number inside */
function heatTable(rowLabels, colLabels, cell, opts) {
  opts = opts || {};
  let lo = Infinity, hi = -Infinity;
  rowLabels.forEach((_, r) => colLabels.forEach((__, c) => {
    const v = cell(r, c); if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }));
  if (!isFinite(lo)) return '<div class="empty">No record for this country.</div>';
  const colour = opts.absolute ? ciColor : (v => bandColor(v, lo, hi));
  let h = `<div class="gridscroll"><table class="heat"><thead><tr><th class="rowh"></th>`;
  colLabels.forEach(l => h += `<th>${esc(l)}</th>`);
  h += `</tr></thead><tbody>`;
  rowLabels.forEach((rl, r) => {
    let best = null, bestC = -1;
    colLabels.forEach((_, c) => { const v = cell(r, c); if (v != null && (best == null || v < best)) { best = v; bestC = c; } });
    h += `<tr><th class="rowh">${esc(rl)}</th>`;
    colLabels.forEach((cl, c) => {
      const v = cell(r, c);
      const bg = colour(v);
      const tip = tipHead(opts.head ? opts.head(rl, cl) : `${String(rl).split(' · ')[0]} · ${cl}`) +
        (v == null ? 'No record in this cell.'
          : tipRow(null, opts.cellName || 'Mean', fmt(v, 1), unitOf()) +
            (c === bestC && opts.markBest ? tipRow(null, 'Rank', 'the cleanest of the row', '') : ''));
      h += `<td class="${darkInk(bg) ? 'dark-text' : ''} ${c === bestC && opts.markBest ? 'best' : ''}"
             style="background:${bg}" ${tipAttr(tip)}>${v == null ? '' : fmt(v)}</td>`;
    });
    h += `</tr>`;
  });
  return h + `</tbody></table></div>`;
}

/* ==========================================================================
   The collapsible source block
   ========================================================================== */
const STATUS_DOT = {
  'verified-live': 'live', 'key-required': 'key', 'blocked': 'block', 'documented-only': 'doc'
};
function srcEntry(id) { return (D.byId || {})[id]; }

/* `licence_status` in the register is a deliberate marker: it says that nobody
   read the terms of the publisher. A source that carries no licence and no
   marker is a different state, because the register makes no statement about
   it. The page puts the marker where the licence goes, and `licence_note` gives
   the full text of the marker in the tooltip. A source with a licence keeps the
   text of that licence. */
function licenceMark(s) {
  return (s && !s.licence && s.licence_status) ? String(s.licence_status) : '';
}

function srcListHTML(ids) {
  return '<ul class="srclist">' + ids.map(id => {
    const s = srcEntry(id);
    if (!s) return '';
    const links = [
      ['Site', s.site_url], ['API base', s.api_base], ['Docs', s.docs_url],
      ['Methodology', s.methodology_url], ['Data portal', s.data_portal_url],
      ['OpenAPI', s.openapi_url], ['Licence', s.licence_url]
    ].filter(p => p[1]).map(p => `<a href="${esc(p[1])}" target="_blank" rel="noopener">${esc(p[0])} ↗</a>`).join('');
    const risks = (s.risks || []).map(r => `<div>⚠ ${esc(r)}</div>`).join('');
    const m = s.methodology || {};
    const collected = (D.meta.collectors || []).indexOf(s.id) >= 0;
    const mark = licenceMark(s);
    const licHint = s.licence_verified_on
      ? ` <span class="ciso" ${tipAttr(esc(s.licence_verification || ''))}>checked ${esc(s.licence_verified_on)}</span>`
      : mark
        ? ` <span class="ciso" ${tipAttr(esc(s.licence_note || ''))}>nobody read the terms of the publisher</span>`
        : ' <span class="ciso">not traced to a publisher statement</span>';
    return `<li>
      <div class="st"><span class="dot ${STATUS_DOT[s.status] || 'doc'}"></span>
        <span class="nm">${esc(s.name)}</span>
        <span class="op">${esc(s.operator)} · ${esc(s.status)}${s.verified_on ? ' on ' + esc(s.verified_on) : ''}</span>
        <span class="badge plain">${esc(s.category)}</span>
        ${collected ? '<span class="badge native" data-tip="The store holds records from this source.">in the store</span>' : ''}</div>
      <div class="meta"><b>Basis:</b> ${esc(m.basis || 'not stated')} &nbsp;·&nbsp;
        <b>Scope:</b> ${esc(m.scope || 'not stated')}</div>
      <div class="meta"><b>Access:</b> ${esc(s.auth)}, ${esc(s.cost)} &nbsp;·&nbsp;
        <b>Licence:</b> ${esc(s.licence || mark || 'not stated')}${licHint} &nbsp;·&nbsp;
        <b>Attribution:</b> ${esc(s.attribution || 'none stated')}</div>
      ${risks ? `<div class="meta" style="color:#8A2B22;margin-top:5px">${risks}</div>` : ''}
      <div class="links">${links}</div>
    </li>`;
  }).join('') + '</ul>';
}

function renderSourceBlocks() {
  const ids = (D.meta.collectors || []).slice();
  const head = `<div style="margin-bottom:8px">This panel uses ${ids.length} of the
     ${(D.sourceList || []).length} sources in the register. ${D.pairs
       ? `The <b>Source discrepancy</b> tab measures the gap between the sources that share a
          country.`
       : `A second source is necessary for a discrepancy number. See the
          <b>Source discrepancy</b> tab.`}</div>`;
  document.querySelectorAll('.srcbody[data-src="panel"]').forEach(box => {
    box.innerHTML = head + srcListHTML(ids);
  });
}

/* ==========================================================================
   Boot
   ========================================================================== */
const FILES = [
  ['meta', 'meta.json'], ['latest', 'latest.json'], ['monthly', 'monthly.json'],
  ['health', 'health.json'], ['register', 'register.json'], ['dailyAll', 'daily_all.json'],
  ['hours', 'hours.json'], ['profile', 'profile.json'], ['forecast', 'forecast.json']
];

async function boot() {
  if (location.protocol === 'file:') {
    document.getElementById('fileErr').classList.add('on');
  }
  /* `pairs.json` goes with the files above, and its absence is not a fault. An
     export from before the analysis step holds no such file. The Source
     discrepancy tab then keeps the text that it had, and every other tab is
     the same. A file that holds no `pairs` array counts as absent. The request
     starts here, with the others, and it carries its own catch: a failure must
     never reach the banner of the group. */
  const optional = fetch('data/pairs.json')
    .then(r => r.ok ? r.json() : null).catch(() => null);
  try {
    const bodies = await Promise.all(FILES.map(f => fetch('data/' + f[1]).then(r => {
      if (!r.ok) throw new Error(f[1] + ': HTTP ' + r.status);
      return r.json();
    })));
    FILES.forEach((f, i) => D[f[0]] = bodies[i]);
  } catch (error) {
    /* Two different faults, and one banner. The banner of index.html names the
       file: address, which is the wrong instruction to a reader who is already
       on a server and has no export. */
    const bar = document.getElementById('fileErr');
    if (location.protocol !== 'file:') {
      bar.innerHTML = '<strong>The export is not on disk.</strong> The page reached the server and ' +
        'the server has no data file for it. Write the files, then load the page again: ' +
        '<code>python -m atlas export</code>';
    }
    bar.classList.add('on');
    document.getElementById('hdrSub').textContent = 'The data files did not load. ' + error.message;
    return;
  }
  const measured = await optional;
  D.pairs = (measured && Array.isArray(measured.pairs)) ? measured : null;
  prepare();
  wire();
  wireTip();
  renderAll();
}

function prepare() {
  D.sourceList = D.register.sources.sources;
  D.byId = {};
  D.sourceList.forEach(s => D.byId[s.id] = s);
  D.zones = D.register.zones;

  (D.meta.sources || []).forEach(s => {
    if (s.unit) { SOURCE_UNIT[s.source_id] = pretty(s.unit); SOURCE_UNIT_ASCII[s.source_id] = s.unit; }
  });
  document.documentElement.style.setProperty('--ca-ramp', rampGradient());

  const rows = {};
  D.meta.countries.forEach(c => rows[c.iso] = c);
  COUNTRIES = D.zones.countries.map(z => Object.assign({}, z, rows[z.iso] || { rows: 0 }));
  COUNTRIES.forEach(c => BY_ISO[c.iso] = c);

  DAY0 = dayNum(D.dailyAll.start_day); NDAY = D.dailyAll.days;
  HOUR0 = tsNum(D.hours.start_hour_utc); NHOUR = D.hours.hours;

  /* the source with the most countries opens the page */
  const stored = (D.meta.collectors || []).slice().sort((a, b) =>
    Object.keys(dayFile(b)).length - Object.keys(dayFile(a)).length);
  S.source = stored[0] || null;
  refreshCountries();
  const start = bestHour();
  S.date = start.date || D.dailyAll.end_day;
  S.hour = start.hour;
  S.tray = S.tray.filter(iso => WITH_DAYS.indexOf(iso) >= 0);
  if (!S.tray.length) S.tray = WITH_DAYS.slice(0, 4);
  S.seasonCountry = S.raw.country = S.calc.base = S.tray[0];
  const first = fcGroups().filter(k => fcIndex()[k].country === S.tray[0])[0];
  S.fcKey = first || fcGroups()[0] || null;

  /* the date control can not leave the file */
  const cd = document.getElementById('cDate');
  cd.min = D.dailyAll.start_day; cd.max = D.dailyAll.end_day; cd.value = S.date;
  document.getElementById('iDate').setAttribute('data-tip',
    `The day that every tab uses. The store holds ${String(D.meta.first_ts_utc).slice(0,10)} to ` +
    `${String(D.meta.last_ts_utc).slice(0,10)}. The day controls cover the last ${NDAY} days. ` +
    `The Time of year tab covers all the history.`);
  document.getElementById('iSource').setAttribute('data-tip',
    `The source of the numbers on this page. A source with no records in the store can not be ` +
    `selected. The Source register tab gives all ${D.sourceList.length} sources and their state.`);

  /* the header */
  document.getElementById('hdrClock').textContent = String(D.meta.last_ts_utc).slice(0, 16);
  document.getElementById('hdrSub').textContent = 'UTC · the newest value in the store';
  const years = Math.max(1, Math.round(
    (dayNum(String(D.meta.last_ts_utc).slice(0,10)) -
     dayNum(String(D.meta.first_ts_utc).slice(0,10))) / 365.25));
  document.getElementById('hdrFresh').textContent =
    `${(D.meta.collectors||[]).length} of ${D.sourceList.length} sources · ${years} years of history`;
  /* One credit for each publisher, with the licence of that publisher. The two
     Elia series are one publisher and one dataset, so they collapse to one
     credit. A licence that the register does not hold is named as absent, and
     the licence of another publisher is never put in its place. A register entry
     that marks the licence carries the words of that marker here. */
  const credits = [];
  (D.meta.collectors || []).forEach(id => {
    const s = srcEntry(id) || {};
    const label = s.attribution || s.name || id;
    const mark = licenceMark(s);
    const lic = s.licence || (mark ? 'licence ' + mark : 'licence not traced');
    const line = `${esc(label)} (${esc(lic)})`;
    if (credits.indexOf(line) < 0) credits.push(line);
  });
  document.getElementById('footText').innerHTML =
    `Carbon Atlas · Wirtek · exported ` +
    `${String(D.meta.generated_at_utc).slice(0, 16).replace('T', ' ')} UTC · Data: ` +
    `${credits.join(' · ')}.`;

  /* the source control lists every register entry, and offers the collected ones */
  const sel = document.getElementById('cSource');
  sel.innerHTML = D.sourceList.filter(s => s.category.indexOf('carbon') === 0 || s.category === 'generation-mix')
    .map(s => {
      const on = (D.meta.collectors || []).indexOf(s.id) >= 0;
      return `<option value="${esc(s.id)}" ${on ? '' : 'disabled'} ${s.id === S.source ? 'selected' : ''}>
        ${esc(s.name)}${on ? '' : ' — no records in the store'}</option>`;
    }).join('');

  fillCountrySelect('cSeasonCountry', WITH_DATA, () => S.seasonCountry);
  fillCountrySelect('cRawCountry', WITH_DATA, () => S.raw.country);
  fillForecastSelect();
  fillCountrySelect('cAddCountry', WITH_DAYS, () => '');

  const cats = ['all'].concat(Array.from(new Set(D.sourceList.map(s => s.category))).sort());
  document.getElementById('cSrcCat').innerHTML = cats.map(c =>
    `<option value="${esc(c)}">${c === 'all' ? 'All categories' : esc(c)}</option>`).join('');

  /* the state filter offers the states that the register holds, and no other */
  const states = Array.from(new Set(D.sourceList.map(s => s.status))).sort();
  document.getElementById('cSrcFilter').innerHTML =
    '<option value="all">All states</option><option value="collected">In the store</option>' +
    states.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
}

/* The newest hour that most countries report.

   The publishers do not finish at the same time. The newest value in the store
   can come from one country only, and a page that opens on that hour shows one
   row. So the portal opens on the newest hour that holds at least 90% of the
   records of the best hour of the last 3 days. */
function bestHour() {
  const back = Math.min(NHOUR, 72);
  const counts = [];
  for (let i = NHOUR - 1; i >= NHOUR - back; i--) {
    let n = 0;
    WITH_DAYS.forEach(iso => { if ((hourFile()[iso] || [])[i] != null) n++; });
    counts.push([i, n]);
  }
  const best = Math.max.apply(null, counts.map(c => c[1]));
  if (!best) return { date: null, hour: 12, countries: 0 };
  const found = counts.filter(c => c[1] >= best * 0.9)[0] || counts[0];
  const when = new Date(HOUR0 + found[0] * 3600000);
  return {
    date: `${when.getUTCFullYear()}-${pad2(when.getUTCMonth()+1)}-${pad2(when.getUTCDate())}`,
    hour: when.getUTCHours(), countries: found[1]
  };
}

/* A source change changes the country list, the tray and every country
   control. A country that the new source does not report leaves the tray. */
function selectSource(id) {
  S.source = id;
  D._monthIndex = null;          /* the month index is per source */
  D._monthFill = null;           /* and so is the step of every month */
  refreshCountries();
  S.tray = S.tray.filter(iso => WITH_DAYS.indexOf(iso) >= 0);
  if (!S.tray.length) S.tray = WITH_DAYS.slice(0, 4);
  if (WITH_DATA.indexOf(S.seasonCountry) < 0) S.seasonCountry = WITH_DATA[0];
  if (WITH_DATA.indexOf(S.raw.country) < 0) S.raw.country = WITH_DATA[0];
  if (WITH_DAYS.indexOf(S.calc.base) < 0) S.calc.base = WITH_DAYS[0];
  fillCountrySelect('cSeasonCountry', WITH_DATA, () => S.seasonCountry);
  fillCountrySelect('cRawCountry', WITH_DATA, () => S.raw.country);
  fillCountrySelect('cAddCountry', WITH_DAYS, () => '');
  const start = bestHour();
  if (start.date) { S.date = start.date; S.hour = start.hour;
    document.getElementById('cDate').value = S.date;
    document.getElementById('cHour').value = S.hour;
    document.getElementById('cHourV').textContent = pad2(S.hour) + ':00';
  }
  renderAll();
}

function fillCountrySelect(id, list, current) {
  const value = current();
  document.getElementById(id).innerHTML = list.map(iso =>
    `<option value="${iso}" ${iso === value ? 'selected' : ''}>${esc(countryName(iso))} (${iso})</option>`).join('');
}

/* The forecast control lists one curve, and not one country. Two publishers
   that forecast the same country give two curves, and the page never mixes
   them. */
function fillForecastSelect() {
  const by = fcIndex();
  document.getElementById('cFcCountry').innerHTML = fcGroups().map(key => {
    const g = by[key];
    const name = (srcEntry(g.source) || {}).name || g.source;
    return `<option value="${esc(key)}" ${key === S.fcKey ? 'selected' : ''}>` +
           `${esc(countryName(g.country))} (${esc(g.country)}) · ${esc(name)}</option>`;
  }).join('');
}

/* the store line of the header. The country count follows the source. */
function renderHeaderStore() {
  const counts = D.meta.counts || {};
  document.getElementById('hdrStore').textContent =
    `${WITH_DATA.length} countries from this source · ${fmt(counts.record_rows)} records in the store`;
}

/* ==========================================================================
   How to read a number on this page

   The panel follows the Source control. It states what the publisher of the
   selected source measures, and it adds nothing that the register does not
   hold.
   ========================================================================== */
function basisSentence(basis) {
  const text = String(basis || '').toLowerCase();
  if (text.indexOf('consumption') >= 0)
    return `The values are the emissions of the electricity that this country consumes. The
            emissions of an import are counted.`;
  if (text.indexOf('production') >= 0)
    return `The values are the emissions of the electricity that this country produces. The
            emissions of an import are not traced.`;
  return '';
}

function renderBasisPanel() {
  const entry = srcEntry(S.source) || {}, m = entry.methodology || {};
  document.getElementById('advSummary').textContent =
    `${m.basis || 'not stated'} · ${m.scope || 'not stated'} · ${unitOf()}`;
  const includes = Array.isArray(m.includes) && m.includes.length
    ? ` The publisher counts ${esc(m.includes.join(', '))}.` : '';
  document.getElementById('advBody').innerHTML = `
    <div style="font-size:12.5px;color:var(--wk-text-gray);max-width:96ch">
      <ul style="margin:0 0 8px 18px;padding:0">
        <li><b>Accounting basis:</b> ${esc(m.basis || 'not stated')}.
          ${basisSentence(m.basis)}${includes}</li>
        <li><b>Scope:</b> ${esc(m.scope || 'not stated')}.</li>
        <li><b>Unit:</b> ${unitOf()}, at the step of the publisher.
          ${unitOf().indexOf('eq') < 0 ? `⚠ This source gives CO₂ and not CO₂eq, so it counts
          no other greenhouse gas. A number from it is below a CO₂eq number of the same hour.` : ''}</li>
        <li><b>Mean:</b> ${esc(D.meta.note)} The workload calculator is not affected, because it
          multiplies the energy of each hour by the intensity of that hour.</li>
        <li><b>Time:</b> UTC. A local day starts at a different hour in each country.</li>
      </ul>
      <p style="margin:0">A number from a source with a different basis is not comparable with these
      numbers. This page states the basis, and it converts nothing. The <b>Source register</b> tab
      gives the basis of each of the ${D.sourceList.length} sources.</p>
    </div>`;
}

/* ==========================================================================
   OVERVIEW
   ========================================================================== */
function visibleIsos() {
  const q = S.q.trim().toLowerCase();
  return COUNTRIES.filter(c => {
    if (!q) return true;
    return c.name.toLowerCase().indexOf(q) >= 0 || c.iso.toLowerCase().indexOf(q) >= 0;
  }).map(c => c.iso);
}

function rankRows() {
  const visible = new Set(visibleIsos());
  const rows = COUNTRIES.filter(c => visible.has(c.iso))
    .map(c => ({ iso: c.iso, name: c.name, v: repValue(c.iso), rows: srcRows(c.iso) }));
  const kept = S.hideEmpty ? rows.filter(r => r.v != null) : rows;
  return kept.sort((a, b) => {
    if (a.v == null) return 1;
    if (b.v == null) return -1;
    return a.v - b.v;
  });
}

function whenText() {
  return S.agg === 'hour'
    ? `${prettyDay(S.date)} · ${pad2(S.hour)}:00 UTC`
    : `mean of ${windowDates().length} days to ${shortDay(S.date)}`;
}

function renderOverview() {
  const rows = rankRows().filter(r => r.v != null);
  const best = rows[0], worst = rows[rows.length - 1];
  const mean = rows.length ? rows.reduce((a, r) => a + r.v, 0) / rows.length : null;
  /* These two describe the source, so they count every country and not the
     countries that the search box leaves visible. */
  const withRecord = COUNTRIES.filter(c => repValue(c.iso) != null).length;
  const noRecord = COUNTRIES.length - withRecord;

  /* A source that reports one country only can not rank countries. The
     cleanest and the dirtiest would name the same country, and a ratio of
     one country against itself is always 1.0. So that source gets its own
     tiles. NESO, RTE, Energinet and the two Elia series each serve one
     country. The test is the country list of the source, and never the
     filtered rows: a search for one name does not make a source national. */
  if (WITH_DAYS.length < 2) {
    const solo = WITH_DAYS[0];
    const one = solo ? { iso: solo, name: countryName(solo), v: repValue(solo) } : null;
    const window = one ? windowDates().map(d => dayMean(one.iso, d)).filter(v => v != null) : [];
    const swing = window.length ? Math.max.apply(null, window) / Math.min.apply(null, window) : null;
    document.getElementById('kpis').innerHTML = `
      <div class="kpi info"><div class="k">The country of this source</div>
        <div class="v">${one ? esc(one.name) : '—'}</div>
        <div class="u">${esc((srcEntry(S.source) || {}).name || S.source)}</div></div>
      <div class="kpi good"><div class="k">${S.agg === 'hour' ? 'This hour' : 'Window mean'}</div>
        <div class="v">${one ? fmt(one.v, 1) : '—'}</div>
        <div class="u">${unitOf()} · ${whenText()}${one ? flagBadge(one.iso) : ''}</div></div>
      <div class="kpi"><div class="k">Window mean of the daily means</div>
        <div class="v">${window.length ? fmt(window.reduce((a, b) => a + b, 0) / window.length, 1) : '—'}</div>
        <div class="u">${plural(window.length, 'day')} to ${shortDay(S.date)}</div></div>
      <div class="kpi hl"><div class="k">Cleanest to dirtiest day</div>
        <div class="v">${swing ? swing.toFixed(1) : '—'}×</div>
        <div class="u">inside the window</div></div>
      <div class="kpi"><div class="k">Records from this source</div>
        <div class="v">${one ? fmt(srcRows(one.iso)) : '—'}</div>
        <div class="u">${one && pairsWith(one.iso, S.source).length
          ? `The <b>Source discrepancy</b> tab measures this source against
             ${plural(pairsWith(one.iso, S.source).length, 'other source')} for this country.`
          : `A second source for this country is on the <b>Source discrepancy</b> tab.`}</div></div>`;
  } else {
    document.getElementById('kpis').innerHTML = `
    <div class="kpi good"><div class="k">Cleanest</div>
      <div class="v">${best ? esc(best.name) : '—'}</div>
      <div class="u">${best ? fmt(best.v, 1) + ' ' + unitOf() + flagBadge(best.iso) : ''}</div></div>
    <div class="kpi bad"><div class="k">Dirtiest</div>
      <div class="v">${worst ? esc(worst.name) : '—'}</div>
      <div class="u">${worst ? fmt(worst.v, 1) + ' ' + unitOf() + flagBadge(worst.iso) : ''}</div></div>
    <div class="kpi info"><div class="k">Mean of the shown countries</div>
      <div class="v">${fmt(mean)}</div>
      <div class="u">${unitOf()} · each country counts one time</div></div>
    <div class="kpi hl"><div class="k">Cleanest to dirtiest</div>
      <div class="v">${rows.length > 1 && best.v ? (worst.v / best.v).toFixed(1) : '—'}×</div>
      <div class="u">${rows.length > 1 ? `${esc(worst.name)} against ${esc(best.name)}`
        : 'the filter leaves one country, so there is no ratio'}</div></div>
    <div class="kpi"><div class="k">Countries with a record</div>
      <div class="v">${withRecord}</div>
      <div class="u">${noRecord} without one · ${whenText()}</div></div>`;
  }

  document.getElementById('rankHint').textContent =
    `${rows.length} rows · ${whenText()} · ${(srcEntry(S.source) || {}).name || S.source}`;

  const all = rankRows();
  const max = Math.max.apply(null, all.map(r => r.v || 0)) || 1;
  let html = `<thead><tr><th class="nosort">#</th><th class="nosort">Country</th>
     <th class="nosort">${unitOf()}</th><th class="nosort" style="width:34%">&nbsp;</th>
     <th class="nosort">Window mean</th><th class="nosort">Records</th></tr></thead><tbody>`;
  all.forEach((r, i) => {
    const wm = S.agg === 'window' ? r.v : (() => {
      const list = windowDates().map(d => dayMean(r.iso, d)).filter(v => v != null);
      return list.length ? list.reduce((a, b) => a + b, 0) / list.length : null;
    })();
    const inTray = S.tray.indexOf(r.iso) >= 0;
    html += `<tr data-iso="${r.iso}" style="${inTray ? 'background:var(--wk-bg-darker)' : ''}">
      <td class="num">${r.v == null ? '—' : i + 1}</td>
      <td><span class="isopill">${r.iso}</span> <span class="cname">${esc(r.name)}</span>
        ${r.rows ? '' : '<span class="badge proxy" data-tip="The source of this page does not report this country. The store holds no record for it.">no record</span>'}${flagBadge(r.iso)}</td>
      <td class="num"><b>${fmt(r.v, 1)}</b></td>
      <td>${r.v == null ? '' : `<div class="barwrap"><i style="width:${(r.v/max*100).toFixed(1)}%;background:${ciColor(r.v)}"></i></div>`}</td>
      <td class="num">${fmt(wm, 1)}</td>
      <td class="num">${fmt(r.rows)}</td></tr>`;
  });
  document.getElementById('rankTable').innerHTML = html + '</tbody>';
  document.querySelectorAll('#rankTable tr[data-iso]').forEach(tr =>
    tr.onclick = () => toggleTray(tr.dataset.iso));

  /* the tile map */
  const visible = new Set(visibleIsos());
  const cells = {};
  COUNTRIES.forEach(c => { if (GP[c.iso]) cells[GP[c.iso][1] + ':' + GP[c.iso][0]] = c; });
  let cg = '', missing = [];
  for (let row = 1; row <= 8; row++) for (let col = 1; col <= 9; col++) {
    const c = cells[row + ':' + col];
    if (!c) { cg += '<div></div>'; continue; }
    const v = repValue(c.iso);
    if (v == null) missing.push(c.iso);
    const bg = ciColor(v);
    const dim = visible.has(c.iso) ? '' : 'opacity:.18;';
    const tip = tipHead(c.name + ' · ' + whenText()) +
      (v == null ? 'No record at this time.'
        : tipRow(null, S.agg === 'hour' ? 'This hour' : 'Window mean', fmt(v, 1), unitOf())) +
      tipRow(null, 'Records from this source', fmt(srcRows(c.iso)), '') +
      flagTipRow(c.iso) +
      '<div class="tr"><span>Select the tile to put it in the tray.</span></div>';
    /* A tile is too small for a badge, so the mark of a flagged country is the
       ⚠ of the callout below the grid. The tooltip carries the rule. */
    cg += `<div class="tile ${darkInk(bg) ? 'dark-text' : ''} ${S.tray.indexOf(c.iso) >= 0 ? 'sel' : ''}"
       style="background:${bg};${dim}" data-iso="${c.iso}" ${tipAttr(tip)}>
       ${c.iso}${dataFlag(c.iso) ? ' ⚠' : ''}<span class="tv">${v == null ? '—' : fmt(v)}</span></div>`;
  }
  document.getElementById('carto').innerHTML = cg;
  document.querySelectorAll('#carto .tile[data-iso]').forEach(t =>
    t.onclick = () => toggleTray(t.dataset.iso));
  document.getElementById('cartoNote').innerHTML = (missing.length
    ? `<div class="callout warn"><span class="ico">⚠</span><span>A grey tile has no record at this
       time: ${missing.join(', ')}. The <b>Raw data</b> tab gives the coverage of each
       country.</span></div>` : '') +
    /* the second mark of the grid: a tile that carries ⚠ holds a value that a
       reader must not quote */
    flagCallout(COUNTRIES.filter(c => GP[c.iso]).map(c => c.iso));

  /* the day, hour by hour */
  const others = windowDates().filter(d => d !== S.date);
  const labels = Array.from({ length: 24 }, (_, h) => pad2(h));
  const series = S.tray.map((iso, i) => {
    const values = labels.map((_, h) => hourVal(iso, S.date, h));
    let band = null;
    if (S.band && others.length) {
      band = labels.map((_, h) => {
        let lo = Infinity, hi = -Infinity;
        others.forEach(d => { const v = hourVal(iso, d, h); if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; } });
        return isFinite(lo) ? [lo, hi] : null;
      });
    }
    return { label: countryName(iso), color: PALETTE[i % PALETTE.length], values, band };
  });
  const inHours = hoursIn(S.date);
  document.getElementById('tsHint').textContent =
    `${prettyDay(S.date)} · ${S.tray.length} countries` +
    (inHours ? '' : ` · the hourly file holds the last ${D.hours.days} days only`);
  document.getElementById('dayChart').innerHTML = S.tray.length
    ? lineChart(series, labels, { h: 210, markIndex: S.hour,
        xHead: l => `${shortDay(S.date)} · ${l}:00 UTC` })
    : '<div class="empty">Add a country to the comparison tray.</div>';

  /* day by day */
  const dates = sampled(windowDates(), 200);
  document.getElementById('daysHint').textContent =
    `${dates.length} of ${windowDates().length} days to ${shortDay(S.date)}`;
  const dseries = S.tray.map((iso, i) => ({
    label: countryName(iso), color: PALETTE[i % PALETTE.length],
    values: dates.map(d => dayMean(iso, d))
  }));
  document.getElementById('daysChart').innerHTML = S.tray.length
    ? lineChart(dseries, dates.map(shortDay), { w: 1180, h: 330, markIndex: dates.indexOf(S.date),
        xHead: (l, i) => `${prettyDay(dates[i])} · daily mean` })
    : '<div class="empty">Add a country to the comparison tray.</div>';

  document.getElementById('daysStats').innerHTML = dseries.map(s => {
    const v = s.values.filter(x => x != null);
    if (!v.length) return `<div class="s"><b style="color:${s.color}">${esc(s.label)}</b><span>no record in the window</span></div>`;
    const mn = Math.min.apply(null, v), mx = Math.max.apply(null, v);
    const mu = v.reduce((a, b) => a + b, 0) / v.length;
    const bestD = dates[s.values.indexOf(mn)], worstD = dates[s.values.indexOf(mx)];
    return `<div class="s"><b style="color:${s.color}">${esc(s.label)}</b>
      <span>mean ${fmt(mu, 1)} · range ${fmt(mn, 1)} to ${fmt(mx, 1)} (${(mx/mn).toFixed(2)}×)<br>
      cleanest ${shortDay(bestD)} · dirtiest ${shortDay(worstD)}</span></div>`;
  }).join('');
}

/* ==========================================================================
   TIME OF YEAR
   ========================================================================== */
function monthlyOf(iso) {
  if (!D._monthIndex) {
    D._monthIndex = {};
    D.monthly.rows.filter(r => r[1] === S.source).forEach(r => {
      (D._monthIndex[r[0]] = D._monthIndex[r[0]] || []).push(
        { month: r[2], n: r[3], mean: r[4], lo: r[5], hi: r[6], median: r[7] });
    });
  }
  return D._monthIndex[iso] || [];
}

/* ⚠ A month is thin against its own step, and never against a fixed count of
   records. A month of an hourly country holds at most 744 records, and a month
   of a 15-minute country at most 2,976. One constant of 300 therefore marks
   the first at 40 % and the second at 10 %. A 15-minute country that lost
   80 % of a month passed that test with no mark at all.

   The step of a country and a source changes inside the store. 14 series went
   from 60 minutes to 15 inside their own span, and Cyprus went the other way.
   So the step of a month comes from the months around it, and never from the
   month itself. A month that lost most of its records would otherwise read as
   a complete month at a coarser step, and it would excuse itself.

   The smallest step of the neighbours wins. A month that holds a change of
   step is then measured against the coarser of the two. It is not called thin
   for a change that the publisher made. The cost is that a thin month beside
   a change of step can pass. */
const STEP_PER_DAY = [24, 48, 96, 288];   /* 60, 30, 15 and 5 minutes */
const THIN_SHARE = 80;                    /* a month below this share is thin */

/* 'YYYY-MM' -> the days of that month */
function monthDays(month) {
  return new Date(Date.UTC(+month.slice(0, 4), +month.slice(5, 7), 0)).getUTCDate();
}
/* 'YYYY-MM' plus a number of months, as 'YYYY-MM' */
function monthShift(month, count) {
  const when = new Date(Date.UTC(+month.slice(0, 4), +month.slice(5, 7) - 1 + count, 1));
  return `${when.getUTCFullYear()}-${pad2(when.getUTCMonth() + 1)}`;
}
/* the step that a count implies: the smallest standard step that holds it.
   The 2 % of room absorbs the hour that a clock change adds in October. */
function stepOfCount(records, days) {
  const perDay = days ? records / days : 0;
  for (let i = 0; i < STEP_PER_DAY.length; i++) {
    if (perDay <= STEP_PER_DAY[i] * 1.02) return STEP_PER_DAY[i];
  }
  return STEP_PER_DAY[STEP_PER_DAY.length - 1];
}

/* What each month of one country and the selected source must hold, and what
   share of it the store has. The map is keyed by 'YYYY-MM'.

   The first month of the series counts from the first stored day, and the
   newest month counts to the newest day of the store. So the running month is
   not thin because it is running. A series that stopped inside the newest
   month is thin, and energy-charts MD is in that state today. */
function monthFill(iso) {
  D._monthFill = D._monthFill || {};
  if (D._monthFill[iso]) return D._monthFill[iso];
  const list = monthlyOf(iso);
  const firstDay = String((srcMeta(iso) || {}).first_ts_utc || '').slice(0, 10);
  const lastDay = String(D.dailyAll.end_day || '');
  const days = {}, own = {};
  list.forEach(r => {
    const all = monthDays(r.month);
    const from = firstDay.slice(0, 7) === r.month ? +firstDay.slice(8, 10) : 1;
    const to = lastDay.slice(0, 7) === r.month ? Math.min(all, +lastDay.slice(8, 10)) : all;
    days[r.month] = Math.max(1, to - from + 1);
    own[r.month] = stepOfCount(r.n, days[r.month]);
  });
  const out = {};
  list.forEach(r => {
    const near = [];
    [-2, -1, 1, 2].forEach(k => {
      const step = own[monthShift(r.month, k)];
      if (step != null) near.push(step);
    });
    /* a month with no neighbour in the store is measured against itself, and
       it is then never thin */
    const step = near.length ? Math.min.apply(null, near) : own[r.month];
    const expected = step * days[r.month];
    out[r.month] = {
      n: r.n, step: step, days: days[r.month], expected: expected,
      share: expected ? r.n / expected * 100 : null,
    };
  });
  D._monthFill[iso] = out;
  return out;
}
/* the share of one month, or null where the file holds no such month */
function monthShare(iso, month) {
  const one = monthFill(iso)[month];
  return one ? one.share : null;
}
function monthIsThin(iso, month) {
  const share = monthShare(iso, month);
  return share != null && share < THIN_SHARE;
}

function renderSeason() {
  const iso = S.seasonCountry;
  const meta = srcMeta(iso) || {};
  document.getElementById('seasonSpan').innerHTML =
    `This tab uses all the history in the store, and not the analysis window.
     ${esc(countryName(iso))} holds ${fmt(meta.rows)} records from
     ${esc((srcEntry(S.source) || {}).name || S.source)}, from
     ${String(meta.first_ts_utc).slice(0,10)} to ${String(meta.last_ts_utc).slice(0,10)}.`;
  /* Every grid of this tab reads one country, so the flag of that country
     belongs at the top of the tab and not on one panel of it. */
  document.getElementById('seasonFlag').innerHTML = flagCallout([iso]);

  /* month by hour of the day */
  const prof = (profFile()[iso] || {}).grid || [];
  const total = (profFile()[iso] || {}).records || [];
  document.getElementById('profHint').textContent =
    `${esc(countryName(iso))} · ${fmt(total.reduce((a, b) => a + b, 0))} records`;
  document.getElementById('profGrid').innerHTML = prof.length
    ? heatTable(MONTHS.map((m, i) => `${m} · ${fmt(total[i])}`),
        Array.from({ length: 24 }, (_, h) => pad2(h)),
        (r, c) => prof[r] ? prof[r][c] : null,
        { markBest: true, cellName: 'Mean of this hour, all years',
          head: (rl, cl) => `${countryName(iso)} · ${String(rl).split(' · ')[0]} · ${cl}:00 UTC` })
    : '<div class="empty">No record for this country.</div>';

  /* what the grid says */
  const flat = [];
  prof.forEach((row, m) => row.forEach((v, h) => { if (v != null) flat.push({ m, h, v }); }));
  if (flat.length) {
    const min = flat.reduce((a, b) => b.v < a.v ? b : a);
    const max = flat.reduce((a, b) => b.v > a.v ? b : a);
    const byMonth = prof.map(row => {
      const l = row.filter(v => v != null);
      return l.length ? l.reduce((a, b) => a + b, 0) / l.length : null;
    });
    const byHour = Array.from({ length: 24 }, (_, h) => {
      const l = prof.map(row => row[h]).filter(v => v != null);
      return l.length ? l.reduce((a, b) => a + b, 0) / l.length : null;
    });
    const mLo = byMonth.indexOf(Math.min.apply(null, byMonth.filter(v => v != null)));
    const mHi = byMonth.indexOf(Math.max.apply(null, byMonth.filter(v => v != null)));
    const hLo = byHour.indexOf(Math.min.apply(null, byHour.filter(v => v != null)));
    const hHi = byHour.indexOf(Math.max.apply(null, byHour.filter(v => v != null)));
    /* The calendar months do not all cover the same number of years. A series
       that starts in the middle of a year gives one month one year more than
       another, and a dirty year then sits on those months only. So each month
       carries its year count, and the ratio carries one decimal. */
    const monthYears = MONTHS.map((_, m) => new Set(monthlyOf(iso)
      .filter(r => Number(r.month.slice(5, 7)) === m + 1).map(r => r.month.slice(0, 4))).size);
    const yearsOf = m => monthYears[m] ? ` · ${plural(monthYears[m], 'year')}` : '';
    document.getElementById('profStats').innerHTML = `
      <div class="s"><b>Cleanest month</b><span>${MONTHS[mLo]} · ${fmt(byMonth[mLo], 1)} ${unitOf()}${yearsOf(mLo)}</span></div>
      <div class="s"><b>Dirtiest month</b><span>${MONTHS[mHi]} · ${fmt(byMonth[mHi], 1)} ${unitOf()}${yearsOf(mHi)}
        · ${(byMonth[mHi]/byMonth[mLo]).toFixed(1)}× the cleanest</span></div>
      <div class="s"><b>Cleanest hour of the day</b><span>${pad2(hLo)}:00 UTC · ${fmt(byHour[hLo], 1)}</span></div>
      <div class="s"><b>Dirtiest hour of the day</b><span>${pad2(hHi)}:00 UTC · ${fmt(byHour[hHi], 1)}
        · ${(byHour[hHi]/byHour[hLo]).toFixed(2)}× the cleanest</span></div>
      <div class="s"><b>Cleanest cell</b><span>${MONTHS[min.m]} at ${pad2(min.h)}:00 · ${fmt(min.v, 1)}</span></div>
      <div class="s"><b>Dirtiest cell</b><span>${MONTHS[max.m]} at ${pad2(max.h)}:00 · ${fmt(max.v, 1)}
        · ${(max.v/min.v).toFixed(2)}× the cleanest cell</span></div>`;
  } else {
    document.getElementById('profStats').innerHTML = '';
  }

  /* every month of every year */
  const list = monthlyOf(iso);
  const years = Array.from(new Set(list.map(r => r.month.slice(0, 4)))).sort();
  const byKey = {};
  list.forEach(r => byKey[r.month] = r);
  document.getElementById('yearsHint').textContent =
    `${esc(countryName(iso))} · ${years.length} years · ${list.length} months`;
  document.getElementById('yearsGrid').innerHTML = years.length
    ? heatTable(years, MONTHS, (r, c) => {
        const k = `${years[r]}-${pad2(c + 1)}`;
        return byKey[k] ? byKey[k].mean : null;
      }, { absolute: false, cellName: 'Mean of the month',
           head: (rl, cl) => `${countryName(iso)} · ${cl} ${rl}` })
    : '<div class="empty">No month in the store for this country.</div>';
  const fill = monthFill(iso);
  const thin = list.filter(r => monthIsThin(iso, r.month));
  /* the finest step first, so the minutes read from the smallest up */
  const steps = Array.from(new Set(thin.map(r => fill[r.month].step))).sort((a, b) => b - a);
  document.getElementById('yearsNote').innerHTML = thin.length
    ? `<div class="callout warn"><span class="ico">⚠</span><span>${plural(thin.length, 'month')}
       ${verb(thin.length, 'holds', 'hold')} fewer than ${THIN_SHARE}% of the records that the
       step of this series gives ${verb(thin.length, 'it', 'them')}, which is
       ${steps.map(s => `${fmt(1440 / s)} minutes`).join(' or ')} for
       ${verb(thin.length, 'that month', 'those months')}. The mean of
       ${verb(thin.length, 'that month covers', 'those months covers')} a part of the month only:
       ${thin.slice(0, 12).map(r => `${esc(r.month)} (${fmt(r.n)} of ${fmt(fill[r.month].expected)},
        ${fmt(fill[r.month].share, 0)}%)`).join(', ')}${thin.length > 12 ? ' …' : ''}.
       The <b>Raw data</b> tab gives the coverage day by day.</span></div>` : '';

  /* the month spread across the years */
  const rows = MONTHS.map((name, m) => {
    /* the same rule as the warning above: a month below THIN_SHARE of what
       its own step gives is not a year of this month */
    const sel = list.filter(r =>
      Number(r.month.slice(5, 7)) === m + 1 && !monthIsThin(iso, r.month));
    if (!sel.length) return { label: name, value: null };
    const means = sel.map(r => r.mean);
    const mu = means.reduce((a, b) => a + b, 0) / means.length;
    const low = Math.min.apply(null, means), high = Math.max.apply(null, means);
    return {
      label: name, value: mu, lo: low, hi: high,
      tip: tipHead(`${countryName(iso)} · ${name}, ${sel.length} years`) +
           tipRow(null, 'Mean of the years', fmt(mu, 1), unitOf()) +
           tipRow(null, 'Lowest year', `${fmt(low, 1)} (${sel[means.indexOf(low)].month.slice(0,4)})`, unitOf()) +
           tipRow(null, 'Highest year', `${fmt(high, 1)} (${sel[means.indexOf(high)].month.slice(0,4)})`, unitOf())
    };
  });
  const got = rows.filter(r => r.value != null);
  document.getElementById('monthHint').textContent =
    got.length ? `${esc(countryName(iso))} · the whisker is the lowest and the highest year` : '';
  document.getElementById('monthChart').innerHTML = got.length
    ? barChart(rows, { h: 280 }) : '<div class="empty">No complete month for this country.</div>';

  /* the last 365 days, for each tray country */
  const days = [];
  for (let n = 364; n >= 0; n--) { const t = dayText(dayNum(D.dailyAll.end_day) - n); if (dayIn(t)) days.push(t); }
  document.getElementById('calHint').textContent =
    `${days.length} days to ${shortDay(D.dailyAll.end_day)}`;
  /* The axis under the strip. The strip starts 364 days before the last stored
     day, so a month gets the width of its own days and not one slot of twelve.
     A month with few days in the strip gets no name, because the name does not
     fit in the space. */
  const axis = [];
  days.forEach(d => {
    const m = Number(d.slice(5, 7)) - 1;
    const last = axis[axis.length - 1];
    if (last && last.m === m) last.span++; else axis.push({ m: m, span: 1 });
  });
  const axisHtml = axis.map(a =>
    `<span style="grid-column:span ${a.span}">${a.span >= 8 ? MONTHS[a.m] : ''}</span>`).join('');
  document.getElementById('calStrip').innerHTML = S.tray.length ? S.tray.map(iso => {
    const cells = days.map(d => {
      const v = dayMean(iso, d);
      const tip = tipHead(`${countryName(iso)} · ${prettyDay(d)}`) +
        (v == null ? 'No record on this day.' : tipRow(null, 'Daily mean', fmt(v, 1), unitOf()));
      return `<i style="background:${ciColor(v)}" ${tipAttr(tip)}
        class="${d === S.date ? 'sel' : ''}"></i>`;
    }).join('');
    const values = days.map(d => dayMean(iso, d)).filter(v => v != null);
    const mn = values.length ? Math.min.apply(null, values) : null;
    const mx = values.length ? Math.max.apply(null, values) : null;
    return `<div class="calrow">
      <div class="cl"><span class="isopill">${iso}</span> ${esc(countryName(iso))}</div>
      <div class="calcells" style="grid-template-columns:repeat(${days.length},1fr)">${cells}</div>
      <div class="cstat">${fmt(mn)} to ${fmt(mx)}<br>${values.length} days</div></div>`;
  }).join('') + `<div class="calrow"><div class="cl"></div>
     <div class="calaxis" style="grid-template-columns:repeat(${days.length},1fr)">${axisHtml}</div>
     <div class="cstat"></div></div>`
    : '<div class="empty">Add a country to the comparison tray.</div>';

  /* head to head */
  const dates = windowDates();
  document.getElementById('h2hHint').textContent = `${dates.length} days to ${shortDay(S.date)}`;
  const pairs = [];
  for (let i = 0; i < S.tray.length; i++) for (let j = i + 1; j < S.tray.length; j++) {
    const a = S.tray[i], b = S.tray[j];
    let win = 0, both = 0, diff = 0;
    dates.forEach(d => {
      const va = dayMean(a, d), vb = dayMean(b, d);
      if (va == null || vb == null) return;
      both++; diff += va - vb; if (va < vb) win++;
    });
    if (!both) continue;
    pairs.push({ a, b, share: win / both * 100, diff: diff / both, both });
  }
  document.getElementById('h2h').innerHTML = pairs.length
    ? `<div class="tscroll"><table class="dt"><thead><tr>
        <th class="nosort">Pair</th><th class="nosort">Days compared</th>
        <th class="nosort">First is cleaner</th><th class="nosort">Mean difference</th>
        <th class="nosort">Reading</th></tr></thead><tbody>` +
      pairs.map(p => `<tr>
        <td><span class="isopill">${p.a}</span> against <span class="isopill">${p.b}</span></td>
        <td class="num">${p.both}</td>
        <td class="num"><b>${p.share.toFixed(0)}%</b></td>
        <td class="num">${p.diff > 0 ? '+' : ''}${fmt(p.diff, 1)} g</td>
        <td>${p.share >= 90 ? `${esc(countryName(p.a))} is almost always cleaner.`
            : p.share <= 10 ? `${esc(countryName(p.b))} is almost always cleaner.`
            : `The order changes. ${esc(countryName(p.a))} is cleaner on ${p.share.toFixed(0)}% of the days.`}</td>
        </tr>`).join('') + '</tbody></table></div>'
    : '<div class="empty">Put two or more countries in the tray.</div>';
}

/* ==========================================================================
   WORKLOAD CALCULATOR
   ========================================================================== */
function calcPool() {
  const pool = S.calc.pool === 'tray' ? S.tray.slice() : WITH_DAYS.slice();
  if (pool.indexOf(S.calc.base) < 0) pool.unshift(S.calc.base);
  return pool;
}
/* the hours that the run covers, before any record is checked */
function patternHours() {
  const c = S.calc;
  if (c.pattern === 'flat') return Array.from({ length: 24 }, (_, h) => h);
  const hours = [];
  let h = c.start;
  for (let n = 0; n < 24; n++) { if (h === c.end) break; hours.push(h); h = (h + 1) % 24; }
  return hours.length ? hours : Array.from({ length: 24 }, (_, h) => h);
}

/* ⚠ Every region in the comparison must cover the same hours.

   The newest day is a part day: a publisher finishes at a different time in
   each country, and some countries have no recent record at all. A sum across
   "the hours that this region has" gives a region with fewer hours a smaller
   total, which reads as a saving and is not one.

   So a region enters the comparison only when it reports EVERY hour of the
   run. The panel names the regions that it dropped. */
function covers(iso, date) {
  return patternHours().every(h => hourVal(iso, date, h) != null);
}
function qualified(pool, date) {
  return pool.filter(iso => covers(iso, date));
}

/* the energy in each hour of the run */
function runEnergy(hours) {
  const out = new Array(24).fill(0);
  if (!hours.length) return out;
  hours.forEach(h => out[h] = S.calc.kwh / hours.length);
  return out;
}

/* The day that the calculator runs on. It keeps the selected day when the
   current region covers the whole run. If not, it steps back to the newest day
   that it does cover, and the panel says which day it used. */
function calcDate() {
  let day = hoursIn(S.date) ? S.date : D.hours.end_hour_utc.slice(0, 10);
  if (covers(S.calc.base, day)) return day;
  for (let n = 1; n <= 10; n++) {
    const t = dayText(dayNum(day) - n);
    if (hoursIn(t) && covers(S.calc.base, t)) return t;
  }
  return day;
}

function gramsFixed(iso, date, energy) {
  let total = 0;
  for (let h = 0; h < 24; h++) {
    if (!energy[h]) continue;
    const v = hourVal(iso, date, h);
    if (v == null) return { grams: null };
    total += energy[h] * S.calc.pue * v;
  }
  return { grams: total };
}

function gramsDynamic(pool, date, energy) {
  let total = 0;
  const pick = [];
  for (let h = 0; h < 24; h++) {
    if (!energy[h]) { pick.push(null); continue; }
    let bestIso = null, bestV = null;
    pool.forEach(iso => {
      const v = hourVal(iso, date, h);
      if (v != null && (bestV == null || v < bestV)) { bestV = v; bestIso = iso; }
    });
    if (bestV == null) return { grams: null, pick: [] };
    total += energy[h] * S.calc.pue * bestV;
    pick.push(bestIso);
  }
  return { grams: total, pick };
}

function renderCalc() {
  const c = S.calc, pool = calcPool(), date = calcDate();
  const want = patternHours(), used = want, energy = runEnergy(want);
  const inPool = qualified(pool, date);
  const dropped = pool.filter(iso => inPool.indexOf(iso) < 0);

  document.getElementById('calcInputs').innerHTML = `
    <div class="ctl"><label for="kKwh">Energy of one run, kWh
      <i class="i" data-tip="The electricity that the IT equipment uses for one run.">i</i></label>
      <input type="number" id="kKwh" min="0.1" step="10" value="${c.kwh}"></div>
    <div class="ctl"><label for="kPattern">Run pattern
      <i class="i" data-tip="Continuous spreads the energy across all 24 hours. A block puts it in the selected hours only.">i</i></label>
      <select id="kPattern">
        <option value="flat" ${c.pattern==='flat'?'selected':''}>Continuous across 24 hours</option>
        <option value="block" ${c.pattern==='block'?'selected':''}>One block of hours</option>
      </select></div>
    <div class="ctl"><label for="kStart">Block start, UTC
      <i class="i" data-tip="The first hour of the block. The block runs up to the end hour, and it does not include it.">i</i></label>
      <select id="kStart" ${c.pattern==='flat'?'disabled':''}>
        ${Array.from({length:24},(_,h)=>`<option value="${h}" ${h===c.start?'selected':''}>${pad2(h)}:00</option>`).join('')}
      </select></div>
    <div class="ctl"><label for="kEnd">Block end, UTC
      <i class="i" data-tip="The hour that the block stops at. An end at or before the start makes the block cross midnight.">i</i></label>
      <select id="kEnd" ${c.pattern==='flat'?'disabled':''}>
        ${Array.from({length:24},(_,h)=>`<option value="${h}" ${h===c.end?'selected':''}>${pad2(h)}:00</option>`).join('')}
      </select></div>
    <div class="ctl"><label for="kBase">Current region
      <i class="i" data-tip="Where the work runs now. The saving is measured against this region.">i</i></label>
      <select id="kBase">${WITH_DAYS.map(iso =>
        `<option value="${iso}" ${iso===c.base?'selected':''}>${esc(countryName(iso))} (${iso})</option>`).join('')}
      </select></div>
    <div class="ctl"><label for="kPool">Candidate regions
      <i class="i" data-tip="The regions that the work can move to. The tray holds the countries that you selected.">i</i></label>
      <select id="kPool">
        <option value="tray" ${c.pool==='tray'?'selected':''}>The comparison tray</option>
        <option value="all" ${c.pool==='all'?'selected':''}>Every country with a record</option>
      </select></div>
    <div class="ctl"><label for="kPue">PUE
      <i class="i" data-tip="Power Usage Effectiveness. The energy that the whole site draws, divided by the energy that the IT equipment draws. The default of 1.39 is the figure of the IONOS Sustainability Report 2025. It is one operator, and you can change it.">i</i></label>
      <input type="number" id="kPue" min="1" max="3" step="0.01" value="${c.pue}"></div>`;

  const total = energy.reduce((a, b) => a + b, 0);
  document.getElementById('calcPueNote').innerHTML =
    `The run uses ${fmt(total, 1)} kWh across ${plural(want.length, 'hour')}. PUE ${c.pue} makes
     the site draw ${fmt(total * c.pue, 1)} kWh. The calculation uses the site energy.
     The day is ${prettyDay(date)}${date === S.date ? '' :
       `, and not ${shortDay(S.date)}, because ${esc(countryName(c.base))} does not report every
        hour of the run on that day`}.
     The default PUE of 1.39 comes from the IONOS Sustainability Report 2025, which is one operator
     in one country. PUE scales the kilogram figures, and it does not change the saving
     percentages.` +
    (dropped.length ? `<div class="callout warn" style="margin-top:9px"><span class="ico">⚠</span><span>
       ${plural(dropped.length, 'candidate region')} ${verb(dropped.length, 'does', 'do')} not report
       every hour of this run on this day, so the comparison leaves
       ${verb(dropped.length, 'it', 'them')} out: ${dropped.join(', ')}. A sum across "the hours that
       this region has" gives a region with fewer hours a smaller total, and that is not a
       saving.</span></div>` : '');

  if (inPool.indexOf(c.base) < 0) {
    document.getElementById('calcScenarios').innerHTML =
      `<div class="empty">${esc(countryName(c.base))} has no record for every hour of this run, on
       this day or on the 10 days before it. Select another current region, another day, or a
       shorter block.</div>`;
    ['calcTable', 'calcTrace', 'calcDays', 'calcDaysStats',
     'calcTableHint', 'calcTraceHint', 'calcDaysHint'].forEach(id =>
      document.getElementById(id).innerHTML = '');
    return;
  }

  const stay = gramsFixed(c.base, date, energy);
  const each = inPool.map(iso => Object.assign({ iso }, gramsFixed(iso, date, energy)))
    .filter(r => r.grams != null).sort((a, b) => a.grams - b.grams);
  const bestFixed = each[0];
  const dyn = gramsDynamic(inPool, date, energy);

  const kg = g => g == null ? null : g / 1000;
  const save = (a, b) => (a.grams != null && b.grams) ? (1 - a.grams / b.grams) * 100 : null;
  document.getElementById('calcScenarios').innerHTML = `
    <div class="scenario"><div class="t">Stay in ${esc(countryName(c.base))}</div>
      <div class="n">${fmt(kg(stay.grams), 1)} kg</div>
      <div class="d">${gasOf()} for this run · ${plural(used.length, 'hour')}</div></div>
    <div class="scenario best"><div class="t">Move the run to the best region</div>
      <div class="n">${bestFixed ? fmt(kg(bestFixed.grams), 1) : '—'} kg</div>
      <div class="d">${bestFixed ? esc(countryName(bestFixed.iso)) : '—'} ·
        <span class="save">${bestFixed && save(bestFixed, stay) != null ? save(bestFixed, stay).toFixed(1) : '—'}% less</span>
        ${bestFixed ? flagBadge(bestFixed.iso) : ''}</div></div>
    <div class="scenario dynamic"><div class="t">Follow the cleanest region, hour by hour</div>
      <div class="n">${fmt(kg(dyn.grams), 1)} kg</div>
      <div class="d">${plural(new Set(dyn.pick.filter(Boolean)).size, 'region')} used ·
        <span class="save">${save(dyn, stay) != null ? save(dyn, stay).toFixed(1) : '—'}% less</span></div></div>`;

  document.getElementById('calcTableHint').textContent =
    `${each.length} regions · ${prettyDay(date)} · ${used.length} hours · ` +
    `${(srcEntry(S.source) || {}).name || ''}`;
  let html = `<thead><tr><th class="nosort">#</th><th class="nosort">Region</th>
    <th class="nosort">${massUnitOf()}</th><th class="nosort" style="width:28%">&nbsp;</th>
    <th class="nosort">Against the current region</th>
    <th class="nosort">Mean intensity of the run, ${unitOf()}</th>
    <th class="nosort">Cleanest hour of the run, ${unitOf()}</th></tr></thead><tbody>`;
  const worst = each.length ? each[each.length - 1].grams : 1;
  each.forEach((r, i) => {
    const mean = r.grams / (total * c.pue);
    const values = used.map(h => hourVal(r.iso, date, h));
    const lo = Math.min.apply(null, values);
    html += `<tr ${r.iso === c.base ? 'style="background:var(--wk-bg-darker)"' : ''}>
      <td class="num">${i + 1}</td>
      <td><span class="isopill">${r.iso}</span> ${esc(countryName(r.iso))}
        ${r.iso === c.base ? '<span class="badge plain">current</span>' : ''}${flagBadge(r.iso)}</td>
      <td class="num"><b>${fmt(kg(r.grams), 1)}</b></td>
      <td><div class="barwrap"><i style="width:${(r.grams/worst*100).toFixed(1)}%;background:${ciColor(mean)}"></i></div></td>
      <td class="num">${r.grams < stay.grams ? '−' : '+'}${Math.abs(save(r, stay) || 0).toFixed(1)}%</td>
      <td class="num">${fmt(mean, 1)}</td>
      <td class="num">${pad2(used[values.indexOf(lo)])}:00 · ${fmt(lo, 1)}</td></tr>`;
  });
  document.getElementById('calcTable').innerHTML = html + '</tbody>';

  /* the hours of the run */
  const labels = Array.from({ length: 24 }, (_, h) => pad2(h));
  const shown = [c.base].concat(each.slice(0, 5).map(r => r.iso).filter(i => i !== c.base));
  document.getElementById('calcTraceHint').textContent =
    `${prettyDay(date)} · ${shown.length} regions · the marked hours carry the energy`;
  document.getElementById('calcTrace').innerHTML = lineChart(
    shown.map((iso, i) => ({
      label: countryName(iso), color: PALETTE[i % PALETTE.length],
      values: labels.map((_, h) => hourVal(iso, date, h))
    })), labels,
    { w: 1180, h: 280, marks: energy.map((v, h) => v > 0 ? h : -1).filter(h => h >= 0),
      xHead: l => `${shortDay(date)} · ${l}:00 UTC` });

  /* the same run on each day of the window.
     A day is used only when every region reports every hour of the run, so the
     days in this chart are comparable with each other. */
  const trace = windowDates().filter(d => hoursIn(d))
    .filter(d => inPool.every(iso => covers(iso, d)))
    .map(d => {
      const a = gramsFixed(c.base, d, energy), b = gramsDynamic(inPool, d, energy);
      return {
        day: d, stay: kg(a.grams), dyn: kg(b.grams),
        save: (a.grams && b.grams != null) ? (1 - b.grams / a.grams) * 100 : null
      };
    });
  document.getElementById('calcDaysHint').textContent =
    `${plural(trace.length, 'complete day')} · the hourly file holds the last ${D.hours.days} days`;
  document.getElementById('calcDays').innerHTML = trace.length
    ? lineChart([
        { label: `Stay in ${countryName(c.base)}`, color: PALETTE[1], values: trace.map(t => t.stay) },
        { label: 'Follow the cleanest region', color: PALETTE[3], values: trace.map(t => t.dyn) }
      ], trace.map(t => shortDay(t.day)),
        { w: 1180, h: 280, unit: massUnitOf(), xHead: (l, i) => `${prettyDay(trace[i].day)} · the same run` })
    : '<div class="empty">No day of the window has a record in every region for every hour of the run.</div>';
  /* The day stays with its own saving. A day with no saving shortens the list,
     and an index into the list then names a different day. */
  const saved = trace.filter(t => t.save != null);
  const saves = saved.map(t => t.save);
  const lo = saved.length ? saved.reduce((a, b) => b.save < a.save ? b : a) : null;
  const hi = saved.length ? saved.reduce((a, b) => b.save > a.save ? b : a) : null;
  document.getElementById('calcDaysStats').innerHTML = saves.length ? `
    <div class="s"><b>Mean saving</b><span>${(saves.reduce((a,b)=>a+b,0)/saves.length).toFixed(1)}%
      across ${saves.length} days</span></div>
    <div class="s"><b>Smallest saving</b><span>${lo.save.toFixed(1)}% · ${shortDay(lo.day)}</span></div>
    <div class="s"><b>Largest saving</b><span>${hi.save.toFixed(1)}% · ${shortDay(hi.day)}</span></div>
    <div class="s"><b>Read it as a range</b><span>One day is not a measurement of the saving. The
      range above is what this pool of regions gave across the window.</span></div>` : '';
}

/* ==========================================================================
   COMPARE
   ========================================================================== */
function toggleTray(iso) {
  const i = S.tray.indexOf(iso);
  if (i >= 0) S.tray.splice(i, 1);
  else if (S.tray.length < TRAY_MAX) S.tray.push(iso);
  else { S.tray.shift(); S.tray.push(iso); }
  renderAll();
}

/* How the source got the value of this country.

   The stored `granularity` of the rows is the answer, and the export carries
   it. Where it is absent, the register gives the mode of the national source
   of that country. Where neither says anything, the card claims nothing:
   Denmark is a roll-up of DK1 and DK2, and a fixed "native" badge states the
   opposite of that. */
function provenanceBadge(iso) {
  const meta = srcMeta(iso) || {};
  const nat = (BY_ISO[iso] || {}).national || {};
  const owns = nat.source_id === S.source;
  let mode = meta.granularity || (owns ? nat.mode : null);
  if (mode === 'aggregate') mode = 'aggregated';
  if (mode === 'aggregated') {
    const zones = (nat.zones || []).join(' + ');
    return `<span class="badge aggregated" data-tip="The source reports smaller zones. The country
      value is a roll-up of those zones, weighted by demand.">roll-up${zones ? ' · ' + esc(zones) : ''}</span>`;
  }
  if (mode === 'native')
    return `<span class="badge native" data-tip="The source reports this country directly. The value
      is not a roll-up of smaller zones.">native</span>`;
  if (mode) return `<span class="badge proxy">${esc(mode)}</span>`;
  return '';
}

function renderCompare() {
  const dates = windowDates();
  const year = [];
  for (let n = 364; n >= 0; n--) { const t = dayText(dayNum(D.dailyAll.end_day) - n); if (dayIn(t)) year.push(t); }

  document.getElementById('cmpCards').innerHTML = S.tray.length ? S.tray.map((iso, i) => {
    const entry = BY_ISO[iso] || {};
    const wv = dates.map(d => dayMean(iso, d)).filter(v => v != null);
    const yv = year.map(d => dayMean(iso, d));
    const got = yv.filter(v => v != null);
    const mn = got.length ? Math.min.apply(null, got) : null;
    const mx = got.length ? Math.max.apply(null, got) : null;
    const latest = (D.latest.rows.filter(r => r[0] === iso && r[1] === S.source)[0] || []);
    const meta = srcMeta(iso) || {};
    const prof = (profFile()[iso] || {}).grid || [];
    const byHour = Array.from({ length: 24 }, (_, h) => {
      const l = prof.map(row => row[h]).filter(v => v != null);
      return l.length ? l.reduce((a, b) => a + b, 0) / l.length : null;
    });
    const hLo = byHour.indexOf(Math.min.apply(null, byHour.filter(v => v != null)));
    return `<div class="cmpcard">
      <h3><span class="isopill">${iso}</span> ${esc(entry.name)}
        ${provenanceBadge(iso)}${flagBadge(iso)}</h3>
      ${flagCallout([iso], true)}
      <div class="cmprow"><span class="k">Value at ${pad2(S.hour)}:00 UTC</span><b>${fmt(hourVal(iso, S.date, S.hour), 1)}</b></div>
      <div class="cmprow"><span class="k">Window mean, ${wv.length} days</span>
        <b>${fmt(wv.length ? wv.reduce((a,b)=>a+b,0)/wv.length : null, 1)}</b></div>
      <div class="cmprow"><span class="k">Window range</span>
        <b>${wv.length ? fmt(Math.min.apply(null,wv),1) + ' to ' + fmt(Math.max.apply(null,wv),1) : '—'}</b></div>
      <div class="cmprow"><span class="k">Cleanest day of the year</span>
        <b>${mn == null ? '—' : shortDay(year[yv.indexOf(mn)]) + ' · ' + fmt(mn, 1)}</b></div>
      <div class="cmprow"><span class="k">Dirtiest day of the year</span>
        <b>${mx == null ? '—' : shortDay(year[yv.indexOf(mx)]) + ' · ' + fmt(mx, 1)}</b></div>
      <div class="cmprow"><span class="k">Day-to-day swing of the year</span>
        <b>${mn && mx ? (mx/mn).toFixed(2) + '×' : '—'}</b></div>
      <div class="cmprow"><span class="k">Cleanest hour, all years</span>
        <b>${byHour[hLo] == null ? '—' : pad2(hLo) + ':00 UTC · ' + fmt(byHour[hLo], 1)}</b></div>
      <div class="cmprow"><span class="k">Records from this source</span><b>${fmt(meta.rows)}</b></div>
      <div class="cmprow"><span class="k">History from</span><b>${String(meta.first_ts_utc).slice(0,10)}</b></div>
      <div class="cmprow"><span class="k">Newest record</span><b>${String(latest[2] || '').slice(0,16)}</b></div>
      <div style="margin-top:9px"><button class="btn tiny" data-drop="${iso}">Take out of the tray</button></div>
    </div>`;
  }).join('') : '<div class="empty">Add a country with the control above, or select a row on the Overview tab.</div>';

  document.querySelectorAll('#cmpCards button[data-drop]').forEach(b =>
    b.onclick = () => toggleTray(b.dataset.drop));

  const labels = Array.from({ length: 24 }, (_, h) => pad2(h));
  document.getElementById('cmpTable').innerHTML = S.tray.length
    ? `<thead><tr><th class="nosort">Country</th>${labels.map(l => `<th class="nosort">${l}</th>`).join('')}
       </tr></thead><tbody>` + S.tray.map(iso =>
      `<tr><td><span class="isopill">${iso}</span> ${esc(countryName(iso))}</td>` +
      labels.map((_, h) => {
        const v = hourVal(iso, S.date, h);
        const bg = v == null ? null : ciColor(v);
        return `<td class="num" style="background:${bg || ''};
          color:${bg == null ? '' : (darkInk(bg) ? 'var(--wk-text)' : '#fff')}">${fmt(v)}</td>`;
      }).join('') + '</tr>').join('') + '</tbody>'
    : '';
}

/* ==========================================================================
   SOURCE DISCREPANCY

   The measurement is `data/pairs.json`. `atlas measure` prints it and
   `atlas export` writes it, so `atlas daily` refreshes it with the other
   files. This page computes none of it: it reads the file and lays it out.

   Two kinds of pair. A `basis` pair holds the unit and the factor table
   constant and changes the accounting basis only. Every other pair is a
   `method` pair, and it changes several things at one time.

   A value of the file can be null: `ratio`, `gap_share_pct`,
   `abs_gap_share_pct` and `correlation` where the statistic is undefined, and
   `same_hour_pct` and `within_one_hour_pct` where the pair has no complete
   day. Each cell below gives an em dash for a null.
   ========================================================================== */
function pairsAll() { return (D.pairs && D.pairs.pairs) ? D.pairs.pairs : []; }
function pairsOfKind(kind) { return pairsAll().filter(p => p.kind === kind); }
/* the pairs of one country that hold one named source */
function pairsWith(iso, source) {
  return pairsAll().filter(p => p.country === iso && (p.a === source || p.b === source));
}
function srcShort(id) { return (srcEntry(id) || {}).name || id; }
const pct = (v, d = 1) => v == null ? '—' : `${fmt(v, d)}%`;
/* ⚠ `a` is the first source id in alphabetical order, and not the larger of
   the two means, so a gap and a share of the gap carry a sign. A cell that
   drops the sign states the opposite of the measurement for three of the six
   pairs. The denominator of the share is the larger mean of the pair, and
   `pairs.json` names it in the field `denominator`, so the share stays inside
   100 % and the sign alone says which source id sorts first. */
const signed = (v, d = 1) => v == null ? '—' : `${v < 0 ? '−' : '+'}${fmt(Math.abs(v), d)}`;
const signedPct = (v, d = 1) => v == null ? '—' : `${signed(v, d)}%`;

/* The unit belongs to the source, and the file carries the unit of each member
   of the pair. Two different units make the gap a difference of two different
   quantities. */
function unitMark(p) {
  if (p.same_unit) return '';
  /* `badge group` is the red badge of this page. It marks a row that a reader
     must not take as one measurement of one quantity. */
  return ` <span class="badge group" ${tipAttr('The two sources do not publish the same quantity. ' +
    'A gCO₂ number counts carbon dioxide. A gCO₂eq number counts the other greenhouse gases with ' +
    'it. The gap of this row holds that difference and the difference of the two methods together.')
    }>⚠ ${esc(pretty(p.unit_a))} against ${esc(pretty(p.unit_b))}</span>`;
}
function pairSourceCell(id, unit, basis) {
  return `<span class="cname">${esc(srcShort(id))}</span>
    <div class="ciso">${esc(pretty(unit) || 'unit not stated')} ·
      ${esc(basis || 'basis not stated')}</div>`;
}
/* `tipHead` escapes its own text, and `tipRow` escapes the name only. */
function pairSpan(p) {
  return tipAttr(tipHead(`${p.country} · ${srcShort(p.a)} against ${srcShort(p.b)}`) +
    tipRow('', 'First shared hour', esc(p.first_ts_utc) + ' UTC') +
    tipRow('', 'Last shared hour', esc(p.last_ts_utc) + ' UTC'));
}
/* the lowest and the highest of one field, over a list of pairs */
function spread(list, field) {
  const values = list.map(p => p[field]).filter(v => v != null);
  return values.length
    ? { lo: Math.min.apply(null, values), hi: Math.max.apply(null, values) } : null;
}

function renderDiscrepancy() {
  const collected = D.meta.collectors || [];
  const twoPlus = COUNTRIES.filter(c => Object.keys(c.sources || {}).length >= 2).length;
  const file = D.pairs;
  document.getElementById('discState').innerHTML =
    `<b>The store holds ${plural(collected.length, 'source')}.</b> ` +
    (twoPlus
      ? `${plural(twoPlus, 'country', 'countries')} ${verb(twoPlus, 'holds', 'hold')} two or more
         sources, so a discrepancy is measurable there. ` + (file
        ? `The analysis step measures it. <code>python -m atlas daily</code> writes the numbers to
           <code>data/pairs.json</code> on each run, and the panels below read that file.`
        : `The analysis step does not compute it yet, so this tab gives the state and not the
           number.`)
      : `A discrepancy needs two independent sources for one country and one hour, so this tab
         gives no measurement yet.`) +
    ` It gives the state of each country, and the source that can give the second value. The store
      never mixes two sources into one value.`;

  /* the measured panels, and nothing at all without the file */
  const box = document.getElementById('discMeasured');
  if (box) box.style.display = file ? '' : 'none';
  if (file && box) renderPairPanels(file);

  const rows = COUNTRIES.map(c => {
    const nat = c.national ? c.national.source_id : null;
    const em = c.em ? c.em.mode : null;
    return {
      iso: c.iso, name: c.name, rows: c.rows || 0,
      collected: Object.keys(c.sources || {}),
      national: nat, natMode: c.national ? c.national.mode : null,
      em: em, emZones: (c.em && c.em.zones) ? c.em.zones.length : 0,
      groups: (c.groups || []).join(', ')
    };
  });
  let html = `<thead><tr><th class="nosort">Country</th><th class="nosort">Sources in the store</th>
    <th class="nosort">Records</th><th class="nosort">National source in the register</th>
    <th class="nosort">Electricity Maps</th><th class="nosort">Group rule</th>
    <th class="nosort">What is missing</th></tr></thead><tbody>`;
  rows.forEach(r => {
    html += `<tr>
      <td><span class="isopill">${r.iso}</span> ${esc(r.name)}</td>
      <td>${r.collected.length ? r.collected.map(id =>
        `<span class="badge native">${esc((srcEntry(id)||{}).name || id)}</span>`).join(' ')
        : '<span class="badge proxy">none</span>'}</td>
      <td class="num">${fmt(r.rows)}</td>
      <td>${r.national ? esc((srcEntry(r.national)||{}).name || r.national) +
        (r.natMode === 'aggregate' ? ' <span class="badge aggregated" data-tip="The source reports smaller zones. The country value is a roll-up of those zones, weighted by demand.">roll-up</span>' : '')
        : '<span class="ciso">none in the register</span>'}</td>
      <td>${r.em ? esc(r.em) + (r.emZones ? ` <span class="ciso">${r.emZones} zones</span>` : '') : '—'}</td>
      <td>${r.groups ? `<span class="badge group" data-tip="One reading covers several countries. Those countries are not independent of each other.">${esc(r.groups)}</span>` : '—'}</td>
      <td>${r.collected.length >= 2 ? 'nothing' :
        `${plural(2 - r.collected.length, 'more source')} for a discrepancy number`}</td>
      </tr>`;
  });
  document.getElementById('discTable').innerHTML = html + '</tbody>';

  /* the order of the work, from the register */
  const byStatus = {};
  D.sourceList.forEach(s => (byStatus[s.status] = byStatus[s.status] || []).push(s));
  const ready = (byStatus['verified-live'] || []).filter(s =>
    collected.indexOf(s.id) < 0 && (s.category === 'carbon-intensity' || s.category === 'generation-mix'));
  const keyed = (byStatus['key-required'] || []);
  const blocked = (byStatus['blocked'] || []);
  /* a group with no source writes no line */
  const items = [];
  if (ready.length) items.push(
    `<li><b>${plural(ready.length, 'source')} ${verb(ready.length, 'answered a live probe and needs',
       'answered a live probe and need')} no key.</b> ${verb(ready.length, 'It is', 'They are')} open
       now: ${ready.map(s => `${esc(s.name)} (${esc(s.coverage && s.coverage.countries_verified ?
       s.coverage.countries_verified.length + ' countries' : s.category)})`).join(', ')}.</li>`);
  if (keyed.length) items.push(
    `<li><b>${plural(keyed.length, 'source')} ${verb(keyed.length, 'needs', 'need')} a key.</b>
       ${keyed.map(s => esc(s.name)).join(', ')}.
       ${keyed.filter(s => s.id === 'entsoe').length ? `ENTSO-E reaches every country in the zone
       model. It gives the second value for the countries that no national operator serves.` : ''}</li>`);
  if (blocked.length) items.push(
    `<li><b>${plural(blocked.length, 'source')} did not answer the probe.</b>
       ${blocked.map(s => esc(s.name)).join(', ')}.
       ${verb(blocked.length, 'It needs', 'Each one needs')} a different route to its data.</li>`);
  document.getElementById('discPlan').innerHTML = `
    <ol style="margin:0 0 0 18px;padding:0;font-size:13px;line-height:1.6">${items.join('')}</ol>
    <div class="callout warn" style="margin-top:12px"><span class="ico">⚠</span><span>
      A second source does not make the first one wrong. The two use different accounting bases and
      different factor tables. The discrepancy is the measurement of that difference. This portal
      never averages the two into one value.</span></div>`;

  document.getElementById('discPipe').innerHTML = `
    <div class="step"><b>1. Two sources</b>The store keeps each source in its own rows, at the step
      of the publisher. This step runs today.</div>
    <div class="step"><b>2. One hour</b>The analysis takes the mean of each source in each hour,
      then joins the two on the country and the hour. ${D.pairs ? 'This step runs today.'
        : 'This step is not built.'}</div>
    <div class="step"><b>3. The spread of each hour</b>For each country and hour: the range, the
      widest pair, and the spread against the mean. This step is not built.</div>
    <div class="step"><b>4. The reason</b>A rule names the causes from the register: the basis, the
      scope, the factor table and the zone roll-up. This step is not built.</div>`;
}

/* The measured panels. Every number here is a field of `data/pairs.json`.
   The page rounds nothing and computes no mean: the file gives each value at
   the number of places that the contract states. */
function renderPairPanels(file) {
  const all = pairsAll();
  const method = pairsOfKind('method');
  const basis = pairsOfKind('basis');
  const chance = file.chance || {};
  const range = file.range || {};
  const skipped = Array.isArray(file.skipped) ? file.skipped : [];
  const isos = Array.from(new Set(all.map(p => p.country))).sort();
  const sameSpread = spread(method, 'same_hour_pct');
  const when = `${esc(file.generated_at_utc)} UTC`;
  const storeTo = `${esc(file.store_last_ts_utc)} UTC`;

  document.getElementById('discWhen').innerHTML =
    `measured ${when} · the store holds records to ${storeTo}`;

  document.getElementById('discKpis').innerHTML = `
    <div class="kpi info"><div class="k">Pairs measured</div>
      <div class="v">${all.length}</div>
      <div class="u">${method.length} of the method · ${basis.length} of the basis</div></div>
    <div class="kpi hl"><div class="k">The gap as a share</div>
      <div class="v" style="font-size:20px">${pct(range.lo_pct)} to ${pct(range.hi_pct)}</div>
      <div class="u">${method.length ? `over the ${plural(method.length, 'method pair')} ·
        against the ${esc(file.denominator || 'larger mean of the pair')}`
        : 'the file holds no method pair'}</div></div>
    <div class="kpi"><div class="k">Countries with two sources or more</div>
      <div class="v">${isos.length}</div>
      <div class="u">${isos.join(', ') || 'none'}</div></div>
    <div class="kpi bad"><div class="k">The same cleanest hour</div>
      <div class="v" style="font-size:20px">${sameSpread
        ? `${pct(sameSpread.lo)} to ${pct(sameSpread.hi)}` : '—'}</div>
      <div class="u">of the complete days · chance alone gives
        ${pct(chance.same_hour_pct, 2)}</div></div>
    <div class="kpi"><div class="k">Measured</div>
      <div class="v" style="font-size:17px">${when}</div>
      <div class="u">the store holds records to ${storeTo}</div></div>`;

  /* ---- the method pairs ---- */
  let html = `<thead><tr><th class="nosort">Country</th>
    <th class="nosort">Source A</th><th class="nosort">Source B</th>
    <th class="nosort">Shared hours</th>
    <th class="nosort">Mean of A</th><th class="nosort">Mean of B</th>
    <th class="nosort">Mean gap, A less B</th><th class="nosort">Ratio, A to B</th>
    <th class="nosort" ${tipAttr('The mean gap divided by the larger mean of the pair, times ' +
      '100. The gap itself is the mean of A less the mean of B. Source A is the first source ' +
      'id in alphabetical order, so the share carries a sign. A minus sign says that source ' +
      'A holds the smaller mean. The larger mean is the denominator of every share in ' +
      'this file, and no share of it passes 100%.')}>Gap as a share of the larger mean</th>
    <th class="nosort" ${tipAttr('The correlation of the two series, over the shared hours. A ' +
      'value near 1 says that the two move together, whatever the size of the gap.')
      }>Correlation</th></tr></thead><tbody>`;
  method.forEach(p => {
    html += `<tr${p.same_unit ? '' : ' style="background:var(--wk-bg-darker)"'}>
      <td><span class="isopill">${esc(p.country)}</span>
        <span class="cname">${esc(countryName(p.country))}</span>${unitMark(p)}</td>
      <td>${pairSourceCell(p.a, p.unit_a, p.basis_a)}</td>
      <td>${pairSourceCell(p.b, p.unit_b, p.basis_b)}</td>
      <td class="num" ${pairSpan(p)}>${fmt(p.hours)}</td>
      <td class="num">${fmt(p.mean_a, 1)}</td>
      <td class="num">${fmt(p.mean_b, 1)}</td>
      <td class="num"><b>${signed(p.mean_gap)} g</b></td>
      <td class="num">${p.ratio == null ? '—' : fmt(p.ratio, 2) + '×'}</td>
      <td class="num">${signedPct(p.gap_share_pct)}</td>
      <td class="num">${fmt(p.correlation, 2)}</td></tr>`;
  });
  document.getElementById('discPairTable').innerHTML = method.length
    ? html + '</tbody>'
    : `<tbody><tr><td>No pair of this store changes the method.</td></tr></tbody>`;

  /* ⚠ A pair with two units compares two quantities. The rule of this project
     is to state the mixing, and this note states it. */
  const mixed = method.filter(p => !p.same_unit);
  document.getElementById('discUnitNote').innerHTML = mixed.length
    ? `<div class="callout warn" style="margin-top:12px"><span class="ico">⚠</span><span>
        ${mixed.length} of the ${plural(method.length, 'method pair')} do not share a unit, and the
        marked rows name the two units. A gCO₂ number counts carbon dioxide. A gCO₂eq number counts
        the other greenhouse gases with it. So the gap of a marked row holds two differences at one
        time: the units and the methods. This page does not separate them. The marked pairs are
        ${mixed.map(p => `${esc(p.country)} ${esc(srcShort(p.a))} against
        ${esc(srcShort(p.b))}`).join(', ')}.</span></div>`
    : '';

  document.getElementById('discMethodText').innerHTML = `
    <p style="margin:0 0 8px">${esc(file.method)}</p>
    <p style="margin:0">A pair with fewer than ${fmt(file.min_hours)} shared hours is not measured.
      ${skipped.length
        ? `This run skipped ${plural(skipped.length, 'pair')}: ` + skipped.map(s =>
          `${esc(s.country)} ${esc(srcShort(s.a))} against ${esc(srcShort(s.b))}
           (${fmt(s.hours)} hours)`).join(', ') + '.'
        : 'This run skipped none.'}
      <code>python -m atlas measure</code> prints the same table at the terminal.</p>`;

  /* ---- which hour did each source call the cleanest ---- */
  /* the range of the day counts, and not their sum: two pairs of one country
     count the same day two times */
  const daySpread = spread(method, 'days');
  document.getElementById('discDaysHint').textContent = daySpread
    ? `${plural(method.length, 'method pair')} · ${fmt(daySpread.lo)} to
       ${plural(daySpread.hi, 'complete day')} each`
    : `${plural(method.length, 'method pair')}`;
  let days = `<thead><tr><th class="nosort">Country</th><th class="nosort">The pair</th>
    <th class="nosort">Complete days</th><th class="nosort">The same hour</th>
    <th class="nosort">Within one hour</th></tr></thead><tbody>`;
  method.forEach(p => {
    days += `<tr${p.same_unit ? '' : ' style="background:var(--wk-bg-darker)"'}>
      <td><span class="isopill">${esc(p.country)}</span>
        <span class="cname">${esc(countryName(p.country))}</span></td>
      <td>${esc(srcShort(p.a))} against ${esc(srcShort(p.b))}</td>
      <td class="num">${fmt(p.days)}</td>
      <td class="num"><b>${pct(p.same_hour_pct)}</b></td>
      <td class="num">${pct(p.within_one_hour_pct)}</td></tr>`;
  });
  /* the chance rate beside the measurement, in the same columns */
  days += `<tr style="background:var(--wk-bg-darker)">
    <td colspan="2">Two series that agree by chance alone</td>
    <td class="num">—</td>
    <td class="num">${pct(chance.same_hour_pct, 2)}</td>
    <td class="num">${pct(chance.within_one_hour_pct)}</td></tr>`;
  document.getElementById('discDaysTable').innerHTML = days + '</tbody>';
  const within = spread(method, 'within_one_hour_pct');
  document.getElementById('discDaysRead').textContent = sameSpread
    ? `The method pairs name the same hour on ${pct(sameSpread.lo)} to ${pct(sameSpread.hi)} of the
       complete days. Chance alone gives ${pct(chance.same_hour_pct, 2)}, and two sources that
       always agree give 100%.${within ? ` They come within one hour on ${pct(within.lo)} to
       ${pct(within.hi)}, against ${pct(chance.within_one_hour_pct)} by chance alone.` : ''}
       A scheduler on one source and a scheduler on the other start the work at a different hour
       on the other days. Neither source is wrong. They answer a different question.`
    : 'No pair holds a day that both sources cover with 24 hours.';

  /* ---- the basis pair ---- */
  renderBasisPair(basis, method, chance);
}

/* The pair that holds the unit and the factor table constant. It is the only
   pair of the register that changes the accounting basis alone, so it is the
   only one that separates the basis from the method. */
function renderBasisPair(basis, method, chance) {
  const hint = document.getElementById('discBasisHint');
  if (!basis.length) {
    hint.textContent = 'no such pair in the store';
    document.getElementById('discBasis').innerHTML =
      `<p class="lead">No publisher in the store gives the same hour of the same country on two
       accounting bases.${method.length ? ` Every pair above changes the method and the basis
       together, and no such pair can say which one moves the number.` : ''}</p>`;
    return;
  }
  const p = basis[0];
  const opA = (srcEntry(p.a) || {}).operator, opB = (srcEntry(p.b) || {}).operator;
  const who = (opA && opA === opB) ? esc(opA) : 'One publisher';
  const sibling = method.filter(m => m.country === p.country);
  /* The mean can hide what the hours hold. The test states the size, so the
     sentence below is true of these two numbers and of no others. */
  const hides = p.abs_gap_share_pct != null && p.gap_share_pct != null &&
    Math.abs(p.abs_gap_share_pct) > Math.abs(p.gap_share_pct) * 3;
  hint.textContent = `${p.country} · ${fmt(p.hours)} shared hours`;
  document.getElementById('discBasis').innerHTML = `
    <p class="lead">${who} gives the same hour of the same country on two accounting bases.
      The two series share the unit and the factor table, so the accounting basis is the only
      difference between them. ${sibling.length
        ? `${plural(sibling.length, 'pair')} above ${verb(sibling.length, 'changes', 'change')}
           the method and the basis together, and ${verb(sibling.length, 'it cannot', 'they cannot')}
           say which one moves the number. This pair can.`
        : 'A pair that changes the method and the basis together cannot say which one moves the number.'}</p>
    <div class="statgrid">
      <div class="s"><b>What the pair holds constant</b><span>${esc(pretty(p.unit_a))} and the
        factor table of ${who}. The two bases are ${esc(p.basis_a)} and
        ${esc(p.basis_b)}.</span></div>
      <div class="s"><b>The two means</b><span>${fmt(p.mean_a, 1)} against ${fmt(p.mean_b, 1)}
        ${esc(pretty(p.unit_a))}, over ${fmt(p.hours)} shared hours to
        ${esc(p.last_ts_utc)} UTC.</span></div>
      <div class="s"><b>The gap of the two means</b><span>${signed(p.mean_gap)} g, which is
        ${signedPct(p.gap_share_pct)} of the larger of the two means.${p.mean_gap == null ? ''
          : ` The sign says that source A holds the ${p.mean_gap < 0 ? 'smaller' : 'larger'}
             mean.`}</span></div>
      <div class="s"><b>The gap hour by hour</b><span>${fmt(p.mean_abs_gap, 1)} g on the mean of the
        absolute gap, which is ${pct(p.abs_gap_share_pct)} of that same larger mean. The
        correlation is ${fmt(p.correlation, 2)}.</span></div>
      <div class="s"><b>The cleanest hour</b><span>The two bases name the same hour on
        ${pct(p.same_hour_pct)} of ${plural(p.days, 'complete day')}, and come within one hour on
        ${pct(p.within_one_hour_pct)}. Chance alone gives
        ${pct(chance.same_hour_pct, 2)}.</span></div>
      ${hides ? `<div class="s"><b>What this separates</b><span>The mean of the two bases differs by
        ${pct(Math.abs(p.gap_share_pct))}, and the hours differ by ${pct(p.abs_gap_share_pct)}. A
        mean of the whole period does not show the basis. An hour of a schedule does.</span></div>`
        : ''}
    </div>`;
}

/* ==========================================================================
   FORECAST
   ========================================================================== */
/* One group for each curve. The export writes one curve for each country and
   each source, so the key carries both: two publishers that forecast the same
   country give two curves, and the page never joins them into one line. */
function fcIndex() {
  if (D._fc) return D._fc;
  const by = {};
  D.forecast.rows.forEach(r => {
    const key = r[0] + '|' + r[1];
    (by[key] = by[key] || { key: key, country: r[0], source: r[1], run_at: r[2], points: [] })
      .points.push({ ts: r[3], value: r[4], horizon: r[5] });
  });
  Object.values(by).forEach(g => {
    g.points.sort((a, b) => tsNum(a.ts) - tsNum(b.ts));
    g.hours = g.points.length ? (tsNum(g.points[g.points.length-1].ts) - tsNum(g.run_at)) / 3600000 : 0;
  });
  D._fc = by;
  return by;
}
function fcGroups() { return Object.keys(fcIndex()).sort(); }
/* the countries that hold at least one curve, whatever the publisher */
function fcCountries() {
  const by = fcIndex();
  return Array.from(new Set(Object.keys(by).map(k => by[k].country))).sort();
}

function renderForecast() {
  const by = fcIndex();
  const keys = fcGroups();
  const isos = fcCountries();
  const runs = D.forecast.runs_in_store.rows;
  /* Both counts are the same for every source: the file holds every publisher,
     so the denominator is every country that the store holds, and not the
     country list of the Source control. */
  const measured = COUNTRIES.filter(c => c.rows).map(c => c.iso);
  const noCurve = measured.filter(iso => isos.indexOf(iso) < 0);

  document.getElementById('fcState').innerHTML =
    `<b>${plural(keys.length, 'forward curve')} for ${plural(isos.length, 'country', 'countries')}</b>
     at the last capture. ${noCurve.length ? `${noCurve.join(', ')} gave none.` : ''}
     A publisher replaces its forecast with each new run, and it keeps no history of the old runs.
     This page shows the newest curve that the store captured. The store holds
     ${runs.map(r => `${plural(r[1], 'run')} of ${esc((srcEntry(r[0])||{}).name || r[0])}`).join(', ')}.`;

  const hours = keys.map(k => by[k].hours);
  const label = k => `${by[k].country} · ${esc((srcEntry(by[k].source) || {}).name || by[k].source)}`;
  /* the newest run of any source, and not the first row of a list that the
     export ordered by source id */
  const newest = runs.reduce((a, r) => (a && tsNum(a) >= tsNum(r[4]) ? a : r[4]), '');
  document.getElementById('fcKpis').innerHTML = `
    <div class="kpi info"><div class="k">Countries with a curve</div><div class="v">${isos.length}</div>
      <div class="u">of ${measured.length} with a measurement</div></div>
    <div class="kpi hl"><div class="k">Shortest horizon</div>
      <div class="v">${hours.length ? Math.min.apply(null, hours).toFixed(1) : '—'} h</div>
      <div class="u">${hours.length ? label(keys[hours.indexOf(Math.min.apply(null,hours))]) : ''}</div></div>
    <div class="kpi hl"><div class="k">Longest horizon</div>
      <div class="v">${hours.length ? Math.max.apply(null, hours).toFixed(1) : '—'} h</div>
      <div class="u">${hours.length ? label(keys[hours.indexOf(Math.max.apply(null,hours))]) : ''}</div></div>
    <div class="kpi"><div class="k">Points captured</div>
      <div class="v">${fmt(runs.reduce((a, r) => a + r[2], 0))}</div><div class="u">across every run</div></div>
    <div class="kpi"><div class="k">Newest capture</div>
      <div class="v" style="font-size:16px">${String(newest).slice(0,16)}</div>
      <div class="u">UTC</div></div>`;

  const g = by[S.fcKey];
  document.getElementById('fcHint').textContent = g
    ? `${countryName(g.country)} · ${(srcEntry(g.source) || {}).name || g.source} · ${unitOf(g.source)}` +
      ` · ${g.points.length} points · captured ${String(g.run_at).slice(0,16)} UTC · ${g.hours.toFixed(1)} h ahead`
    : '';
  if (g) {
    const labels = g.points.map(p => String(p.ts).slice(5, 16));
    /* the measurement of the same source, never of another one */
    const rows = hourFile(g.source)[g.country] || [];
    const actual = g.points.map(p => {
      const t = tsNum(p.ts), i = Math.round((t - HOUR0) / 3600000);
      return (i >= 0 && i < NHOUR) ? rows[i] : null;
    });
    const series = [{ label: 'Forecast, as captured', color: PALETTE[2], values: g.points.map(p => p.value), dash: '5 3' }];
    if (actual.some(v => v != null)) series.push({ label: 'Measured', color: PALETTE[0], values: actual });
    /* the unit of the publisher of this curve, and not of the Source control */
    document.getElementById('fcChart').innerHTML =
      lineChart(series, labels, { w: 1180, h: 300, unit: unitOf(g.source),
        xHead: l => `${countryName(g.country)} · ${l} UTC` });
  } else {
    document.getElementById('fcChart').innerHTML = '<div class="empty">This country gave no curve.</div>';
  }

  document.getElementById('fcTableHint').textContent =
    `${plural(keys.length, 'curve')} · each row carries the unit of its own publisher`;
  document.getElementById('fcTable').innerHTML =
    `<thead><tr><th class="nosort">Country</th><th class="nosort">Source</th><th class="nosort">Points</th>
      <th class="nosort">Hours ahead</th><th class="nosort">Step</th>
      <th class="nosort">First</th><th class="nosort">Last</th>
      <th class="nosort">Lowest</th><th class="nosort">Highest</th>
      <th class="nosort">Unit</th></tr></thead><tbody>` +
    keys.map(key => {
      const x = by[key], values = x.points.map(p => p.value);
      const step = x.points.length > 1
        ? (tsNum(x.points[1].ts) - tsNum(x.points[0].ts)) / 60000 : null;
      return `<tr ${key === S.fcKey ? 'style="background:var(--wk-bg-darker)"' : ''} data-fc="${esc(key)}">
        <td><span class="isopill">${x.country}</span> ${esc(countryName(x.country))}</td>
        <td>${esc((srcEntry(x.source) || {}).name || x.source)}</td>
        <td class="num">${x.points.length}</td>
        <td class="num"><b>${x.hours.toFixed(1)}</b></td>
        <td class="num">${step == null ? '—' : step + ' min'}</td>
        <td>${String(x.points[0].ts).slice(5,16)}</td>
        <td>${String(x.points[x.points.length-1].ts).slice(5,16)}</td>
        <td class="num">${fmt(Math.min.apply(null, values), 1)}</td>
        <td class="num">${fmt(Math.max.apply(null, values), 1)}</td>
        <td>${unitOf(x.source)}</td></tr>`;
    }).join('') + '</tbody>';
  document.querySelectorAll('#fcTable tr[data-fc]').forEach(tr => tr.onclick = () => {
    S.fcKey = tr.dataset.fc;
    document.getElementById('cFcCountry').value = S.fcKey;
    renderForecast();
  });

  /* The span of the capture comes from the runs, and so does the conclusion.
     A typed "one day" falsifies itself on the next day of collection. */
  const days = Array.from(new Set(runs.flatMap(r =>
    [String(r[3]).slice(0, 10), String(r[4]).slice(0, 10)]))).sort();
  const first = days[0], last = days[days.length - 1];
  const nDays = first && last ? dayNum(last) - dayNum(first) + 1 : 0;
  const span = nDays > 1 ? `from ${first} to ${last}` : (first ? `all from ${first}` : 'from no run');
  const scope = nDays > 1 ? plural(nDays, 'day') : 'one day';
  document.getElementById('fcWhy').innerHTML = `
    <p style="font-size:13px;margin:0 0 9px">A score needs the same hour from two sides: the forecast
    that a publisher made before the hour, and the measurement of that hour. The store holds
    ${plural(runs.reduce((a, r) => a + r[1], 0), 'captured run')}, ${span}, so a mean error
    here describes ${scope} of capture and not the publisher.</p>
    <ul style="margin:0 0 9px 18px;padding:0;font-size:13px;line-height:1.6">
      <li><b>The mean error and the bias</b> need many runs at each lead time. That needs some weeks
        of capture.</li>
      <li><b>The skill against persistence</b> divides the error of the forecast by the error of a
        simple rule. The rule is that the next hour is the same as this hour. A ratio above 1 means
        that the forecast is worse than no forecast.</li>
      <li><b>The decision test</b> is the test that matters for a scheduler. Did the forecast pick
        the cleanest hour, and what did a wrong choice cost, in the unit of the publisher?</li>
    </ul>
    <p style="font-size:13px;margin:0">Two sources in the register keep their own forecast history.
    A score of those two is possible on the first day of collection: Energinet back to 2016, and
    NESO back to 2018.</p>`;
}

/* ==========================================================================
   RAW DATA
   ========================================================================== */
/* A missing per-country file must not render as an empty table: an empty table
   reads as a real answer. The result carries the fault instead, and only a
   good body enters the cache. */
async function countryFile(kind, iso) {
  if (CACHE[kind][iso]) return CACHE[kind][iso];
  const url = `data/${kind}/${iso}.json`;
  let body;
  try {
    const answer = await fetch(url);
    if (!answer.ok) return { error: `${url}: HTTP ${answer.status}` };
    body = await answer.json();
  } catch (error) {
    return { error: `${url}: ${error.message}` };
  }
  CACHE[kind][iso] = body;
  return body;
}

/* the panel of a file that did not load */
function rawFileError(message) {
  RAW_ROWS = []; RAW_HEAD = [];
  document.getElementById('rawTable').innerHTML =
    `<tbody><tr><td><div class="empty">This file did not load, so the table below it is not the
     answer and is empty. ${esc(message)}. Run <code>python -m atlas export</code> again.
     </div></td></tr></tbody>`;
}

let RAW_ROWS = [], RAW_HEAD = [];

/* ==========================================================================
   The coverage table
   --------------------------------------------------------------------------
   The table reads `health.json` by field name, and never by a fixed position.
   The file states the order in `fields`, and each column below names the
   fields that it shows. A field that no column names gets a column of its own
   at the end of the row. So a new field in the file reaches the page on the
   day that it appears. The table can not fall behind the file again.

   The file holds 18 fields, and 18 columns are too many to read at once. The
   reader asks one question here: does this country have its data. The columns
   on screen carry that answer: the range, the records, the periods with no
   record, and the widest hole. The exact counts and the exact stamps are in
   the tooltip of the cell. The text of the collector is behind the detail
   block that the other panels use. The CSV download keeps every field and
   every row.
   ========================================================================== */
let HEALTH_IX = null, HEALTH_IX_OF = null, HEALTH_IX_LEN = -1;
function healthFields() { return (D.health || {}).fields || []; }
function healthIx() {
  const fields = healthFields();
  if (HEALTH_IX_OF !== fields || HEALTH_IX_LEN !== fields.length) {
    HEALTH_IX_OF = fields; HEALTH_IX_LEN = fields.length; HEALTH_IX = {};
    fields.forEach((name, i) => { HEALTH_IX[name] = i; });
  }
  return HEALTH_IX;
}
/* the value of one field of one row, or null when the file has no such field */
function healthGet(row, name) {
  const i = healthIx()[name];
  const value = (i == null || !row) ? null : row[i];
  return value == null ? null : value;
}

/* the first sentence of a long text, or the first part of it. The summary of a
   detail block must stay on one line in a cell. */
function firstLine(text, max) {
  const t = String(text).replace(/\s+/g, ' ').trim();
  const stop = t.indexOf('. ');
  if (stop > 0 && stop < max) return t.slice(0, stop + 1);
  return t.length <= max ? t : t.slice(0, max).trim() + '…';
}

const COVER_COLS = [
  { reads: ['country'], label: 'country', left: true,
    cell: g => `<td class="l"><span class="isopill">${esc(g('country'))}</span> ${esc(countryName(g('country')))}</td>` },

  { reads: ['source_id'], label: 'source', left: true,
    cell: g => `<td class="l">${esc((srcEntry(g('source_id')) || {}).name || g('source_id'))}</td>` },

  { reads: ['kind'], label: 'kind', left: true,
    cell: g => `<td class="l">${esc(g('kind'))}</td>` },

  /* The first day and the last day are one answer, so they are one cell.

     ⚠ They are not the range of the stored data. `export.py` takes them from
     the RUN table, so they name the first day and the last day on which the
     collector ran with no error. 30 of the 39 actual rows disagree with the
     first stored record of the same series on 2026-09-23: AT gives
     2015-06-01 against a first record at 2015-05-31 22:00, and CY gives
     2015-07-27 against 2015-07-25 21:00. The Stored range card above this
     table gives the true instants, so a column that reads "stored range"
     here puts two answers to one question on one screen. The data is right.
     The label was not. */
  { reads: ['first_day', 'last_day'], label: 'collection ran',
    tip: 'The first day and the last day on which the collector ran and reported no error. This ' +
         'is the record of the run, and not the range of the stored data. The Stored range card ' +
         'above this table gives the stamp of the first record and of the last one.',
    left: true,
    cell: g => {
      const first = g('first_day'), last = g('last_day');
      if (!first && !last) return '<td class="l miss">—</td>';
      /* the true first instant, beside the run day, when the two differ. The
         forecast rows have no counterpart in the store meta, so they get the
         plain text. */
      const stored = g('kind') === 'actual'
        ? (srcMeta(g('country'), g('source_id')) || {}).first_ts_utc : null;
      const differs = stored && String(stored).slice(0, 10) !== first;
      const tip = 'The collector ran on these days and reported no error. ' +
        (differs
          ? `The first stored record of this series is ${esc(String(stored).slice(0, 16))} UTC, ` +
            'which is a different day. The two answer different questions.'
          : 'It is the record of the run, and not the range of the stored data.');
      return `<td class="l" ${tipAttr(tip)}>${esc(first || '—')}` +
             `<span class="sub">to ${esc(last || '—')}</span></td>`;
    } },

  { reads: ['step_minutes'], label: 'step', cell: g => {
      const step = g('step_minutes');
      if (step == null) return '<td class="miss">—</td>';
      return `<td class="tick" ${tipAttr(`The data of this row gives one record for each ${fmt(step)} minutes.`)}>${fmt(step)} min</td>`;
    } },

  { reads: ['records', 'expected'], label: 'records', cell: g => {
      const records = g('records'), expected = g('expected');
      const tip = expected == null
        ? `The store holds ${fmt(records)} records for this row. The file gives no count of the periods that the range holds.`
        : `The store holds ${fmt(records)} records. The range from the first record to the last one holds ${fmt(expected)} periods.`;
      return `<td ${tipAttr(tip)}>${fmt(records)}` +
             `${expected == null ? '' : `<span class="sub">of ${fmt(expected)}</span>`}</td>`;
    } },

  /* the shortfall. A row with no absent period stays quiet: the count is 0 in
     the grey of a cell that holds nothing to act on. */
  { reads: ['absent'], label: 'absent', cell: g => {
      const absent = g('absent'), expected = g('expected');
      if (absent == null) return `<td class="miss" ${tipAttr('This row gives no count of the absent periods.')}>—</td>`;
      if (absent === 0) return `<td class="miss" ${tipAttr('Each period between the first record and the last one holds a record.')}>0</td>`;
      const share = expected ? (absent / expected) * 100 : null;
      const tip = share == null
        ? `${fmt(absent)} periods between the first record and the last one hold no record.`
        : `${fmt(absent)} periods between the first record and the last one hold no record. ` +
          `That is ${pct(share)} of the ${fmt(expected)} periods in the range.`;
      /* a share that rounds to 0.0 % gives the reader nothing, and it reads as
         a zero that the count above it contradicts. The tooltip keeps it. */
      const showShare = share != null && share >= 0.05;
      return `<td ${tipAttr(tip)}>${fmt(absent)}` +
             `${showShare ? `<span class="sub">${pct(share)}</span>` : ''}</td>`;
    } },

  /* the widest hole. It is an answer only when a period is absent. A row with
     absent 0 gives the step of the publisher here, and not a hole. */
  { reads: ['hole_from', 'hole_to', 'hole_hours'], label: 'widest hole', left: true,
    cell: g => {
      const absent = g('absent'), from = g('hole_from'), to = g('hole_to'), hours = g('hole_hours');
      if (!absent || !from || !to) {
        const tip = absent === 0 && hours != null
          ? `This series has no hole. The widest step between two records is ${fmt(hours, 1)} hours.`
          : 'This row gives no hole.';
        return `<td class="l miss" ${tipAttr(tip)}>—</td>`;
      }
      const tip = `The widest hole is between the record at ${esc(from)} and the record at ${esc(to)}. ` +
                  `It is ${fmt(hours, 1)} hours wide, and ${fmt(absent)} periods in it hold no record.`;
      return `<td class="l" ${tipAttr(tip)}>${esc(String(from).slice(0, 10))} to ${esc(String(to).slice(0, 10))}` +
             `<span class="sub">${fmt(hours, 1)} hours</span></td>`;
    } },

  /* the three day counts are one answer, so they are one cell. The empty days
     and the failed days show only when there are some. */
  { reads: ['days_ok', 'days_empty', 'days_fail'], label: 'days', cell: g => {
      const ok = g('days_ok'), empty = g('days_empty'), failed = g('days_fail');
      const bits = [];
      if (empty) bits.push(`${fmt(empty)} empty`);
      if (failed) bits.push(`<span style="color:#8A2B22">${fmt(failed)} failed</span>`);
      const tip = `${fmt(ok)} days gave a value. ${fmt(empty)} days gave an answer with no value in it. ` +
                  `${fmt(failed)} days failed with an error.`;
      return `<td ${tipAttr(tip)}>${fmt(ok)} ok` +
             `${bits.length ? `<span class="sub">${bits.join(' · ')}</span>` : ''}</td>`;
    } },

  { reads: ['last_run_at'], label: 'last run', left: true, cell: g => {
      const run = g('last_run_at');
      return run ? `<td class="l">${esc(String(run).slice(0, 16))}</td>` : '<td class="l miss">—</td>';
    } },

  /* the text of the collector. It is long, so it sits behind the detail block
     that the other panels use, and the summary states the first sentence. */
  { reads: ['an_error', 'a_note'], label: 'error or note', left: true, cell: g => {
      const error = g('an_error'), note = g('a_note');
      if (!error && !note) return '<td class="l miss">—</td>';
      return `<td class="l"><details class="src" style="margin:0;border-top:none;padding-top:0">` +
             `<summary>${esc(firstLine(error || note, 46))}</summary>` +
             `<div class="srcbody" style="max-width:520px">` +
             `${error ? `<div>The error: ${esc(error)}</div>` : ''}` +
             `${note ? `<div>The note: ${esc(note)}</div>` : ''}` +
             `</div></details></td>`;
    } }
];

/* a field that no column above names. It gets the name of the field for a
   header, and the value of the file for a cell. */
function coverExtraCell(value) {
  if (value == null) return '<td class="miss">—</td>';
  if (typeof value === 'number') return `<td>${fmt(value, Number.isInteger(value) ? 0 : 1)}</td>`;
  return `<td class="l">${esc(String(value).slice(0, 90))}</td>`;
}

/* the two lines of the meta card of the selected country and source. They give
   the shortfall and the hole before the reader opens the coverage table. */
function recordsLine(ga) {
  const records = ga('records'), expected = ga('expected'), absent = ga('absent');
  if (records == null) return 'This source has no row for this country.';
  if (expected == null) return `${fmt(records)} records`;
  return `${fmt(records)} of ${fmt(expected)} periods, ${fmt(absent)} absent`;
}
function holeLine(ga) {
  const absent = ga('absent'), from = ga('hole_from'), to = ga('hole_to'),
        hours = ga('hole_hours'), step = ga('step_minutes');
  if (absent && from && to) {
    return `widest hole ${esc(String(from).slice(0, 10))} to ${esc(String(to).slice(0, 10))}, ` +
           `${fmt(hours, 1)} hours`;
  }
  if (absent === 0) return `no hole, one record each ${fmt(step)} minutes`;
  return 'no hole is known';
}

function coverTableHTML(iso) {
  const fields = healthFields();
  const cols = COVER_COLS.filter(c => c.reads.every(name => fields.indexOf(name) >= 0));
  const named = {};
  cols.forEach(c => c.reads.forEach(name => { named[name] = 1; }));
  const extra = fields.filter(name => !named[name]);
  const extraIx = extra.map(name => fields.indexOf(name));

  const head = '<thead><tr>' +
    /* a column can carry a tooltip on its header, for a label that names
       something other than what a reader expects under it */
    cols.map(c => `<th class="${c.left ? 'l' : ''}" ${c.tip ? tipAttr(esc(c.tip)) : ''}>` +
                  `${esc(c.label)}</th>`).join('') +
    extra.map(name => `<th class="l">${esc(name)}</th>`).join('') +
    '</tr></thead>';

  const body = '<tbody>' + D.health.rows.map(row => {
    const g = name => healthGet(row, name);
    return `<tr class="${g('country') === iso ? 'sel' : ''}">` +
      cols.map(c => c.cell(g)).join('') +
      extraIx.map(i => coverExtraCell(row[i])).join('') +
      '</tr>';
  }).join('') + '</tbody>';

  return head + body;
}

async function renderRaw() {
  const iso = S.raw.country, view = S.raw.view;
  const entry = BY_ISO[iso] || {};
  const meta = srcMeta(iso) || {};
  /* the health row of this country and this source, read by field name */
  const health = D.health.rows.filter(r =>
    healthGet(r, 'country') === iso && healthGet(r, 'source_id') === S.source);
  const actual = health.filter(r => healthGet(r, 'kind') === 'actual')[0] || [];
  const ga = name => healthGet(actual, name);
  renderRawPipe();

  /* the licence card states the marker of the register when the register holds
     one, because an empty card gives the reader no statement at all */
  const licSrc = srcEntry(S.source) || {};
  const licMark = licenceMark(licSrc);
  const licText = licMark
    ? `<span ${tipAttr(esc(licSrc.licence_note || ''))}>${esc(licMark)}</span>`
    : esc(licSrc.licence || '');
  const licWho = licMark && !licSrc.attribution
    ? 'nobody read the terms of the publisher'
    : esc(licSrc.attribution || '');

  document.getElementById('rawMeta').innerHTML = `
    <div class="m"><div class="kk">Country</div><b>${esc(entry.name)}</b> (${iso})
      ${flagBadge(iso)}<br>
      <span class="ciso">${fmt(meta.rows)} records from this source</span></div>
    <div class="m"><div class="kk">Source</div><b>${esc((srcEntry(S.source)||{}).name || '')}</b><br>
      <span class="ciso">${esc((srcEntry(S.source)||{}).operator || '')}</span></div>
    <div class="m"><div class="kk">Stored range</div>
      ${String(meta.first_ts_utc).slice(0,16)}<br>to ${String(meta.last_ts_utc).slice(0,16)} UTC<br>
      <span class="ciso">the stamp of the first record and of the last one</span></div>
    <div class="m"><div class="kk">Days collected</div>
      <b>${fmt(ga('days_ok'))} ok</b>, ${fmt(ga('days_empty'))} empty, ${fmt(ga('days_fail'))} failed<br>
      <span class="ciso">last run ${String(ga('last_run_at') || '').slice(0,16)}</span></div>
    <div class="m"><div class="kk">Records and holes</div>
      ${recordsLine(ga)}<br>
      <span class="ciso">${holeLine(ga)}</span></div>
    <div class="m"><div class="kk">Licence</div>${licText}<br>
      <span class="ciso">${licWho}</span></div>`;

  if (view === 'records') {
    const body = await countryFile('recent', iso);
    document.getElementById('rawTitle').textContent = 'Records, at the step of the publisher';
    if (body.error) { document.getElementById('rawLead').textContent = ''; rawFileError(body.error); return; }
    /* the per-country files hold every source. This table shows one. */
    const rows = body.rows.filter(r => r[0] === S.source);
    document.getElementById('rawLead').innerHTML =
      `The last ${body.days} days, exactly as the publisher gave them. The store keeps the
       step of the publisher and never resamples on the way in. A resample can not be undone.
       ${fmt(rows.length)} rows.`;
    RAW_HEAD = ['ts_utc', 'source_id', 'value ' + unitAscii(), 'change from the last record', 'step minutes'];
    RAW_ROWS = rows.map((r, i) => {
      const prev = rows[i - 1];
      const step = prev ? (tsNum(r[1]) - tsNum(prev[1])) / 60000 : null;
      const delta = prev ? r[2] - prev[2] : null;
      return [r[1], r[0], r[2], delta, step];
    });
    document.getElementById('rawTable').innerHTML =
      `<thead><tr><th class="l">ts_utc</th><th class="l">source_id</th><th>value</th>
        <th>change</th><th>step</th></tr></thead><tbody>` +
      RAW_ROWS.slice(-1500).map(r => `<tr>
        <td class="l">${esc(r[0])}</td><td class="l">${esc(r[1])}</td>
        <td class="cell" style="background:${ciColor(r[2])};color:${darkInk(ciColor(r[2]))?'var(--wk-text)':'#fff'}">${fmt(r[2],1)}</td>
        <td class="${r[3] == null ? 'miss' : ''}">${r[3] == null ? '—' : (r[3] > 0 ? '+' : '') + fmt(r[3], 1)}</td>
        <td class="tick">${r[4] == null ? '—' : r[4]}</td></tr>`).join('') + '</tbody>';
  } else if (view === 'days') {
    const body = await countryFile('daily', iso);
    document.getElementById('rawTitle').textContent = 'Day by day, all the history';
    if (body.error) { document.getElementById('rawLead').textContent = ''; rawFileError(body.error); return; }
    const rows = body.rows.filter(r => r[0] === S.source);
    document.getElementById('rawLead').innerHTML =
      `One row for each day that the store holds for this country. <code>n</code> is the number of
       records in the day. A day with fewer records than the step allows is a partial day.
       ${fmt(rows.length)} days.`;
    const u = unitAscii();
    RAW_HEAD = ['day', 'source_id', 'records', 'mean_unweighted ' + u, 'lo ' + u, 'hi ' + u];
    RAW_ROWS = rows.map(r => [r[1], r[0], r[2], r[3], r[4], r[5]]);
    const full = Math.max.apply(null, rows.map(r => r[2]));
    document.getElementById('rawTable').innerHTML =
      `<thead><tr><th class="l">day</th><th>records</th><th>mean</th><th>lowest</th><th>highest</th>
        <th>range</th></tr></thead><tbody>` +
      RAW_ROWS.slice().reverse().slice(0, 1500).map(r => `<tr>
        <td class="l">${esc(r[0])}</td>
        <td class="${r[2] < full ? 'held' : ''}" ${tipAttr(r[2] < full
          ? `A part day. It holds ${r[2]} records, and a complete day holds ${full}.`
          : `A complete day. It holds all ${full} records.`)}>${r[2]}</td>
        <td class="cell" style="background:${ciColor(r[3])};color:${darkInk(ciColor(r[3]))?'var(--wk-text)':'#fff'}">${fmt(r[3],1)}</td>
        <td>${fmt(r[4],1)}</td><td>${fmt(r[5],1)}</td>
        <td class="tick">${fmt(r[5]-r[4],1)}</td></tr>`).join('') + '</tbody>';
  } else {
    document.getElementById('rawTitle').textContent = 'Coverage and failures';
    /* the note of the file states what `expected` and the hole stamps mean.
       The page gives that note to the reader, in the words of the store. */
    const fileNote = String((D.health || {}).note || '')
      .replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]))
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    document.getElementById('rawLead').innerHTML =
      `One row for each source, country and kind. It gives the days that the collector ran, the
       records in the store, the periods with no record, and the widest hole between two records.
       The store holds ${fmt((D.meta.counts||{}).run_rows)} run rows, and the CSV download gives
       every field of this file. ${fileNote}
       The collection ran column gives <code>first_day</code> and <code>last_day</code> from the
       run table. They are the days of the run, and not the range of the stored data. The Stored
       range card above gives the stamp of the first record and of the last one. The two are a
       different day for most of the rows.`;
    /* the download keeps every field and every row, and the table above it
       shows the fields that answer the question of the panel */
    RAW_HEAD = D.health.fields;
    RAW_ROWS = D.health.rows.map(r => r.slice());
    document.getElementById('rawTable').innerHTML = coverTableHTML(iso);
  }
}

/* the pipe under the table. It follows the source and not the view, so a file
   that did not load still leaves it on screen. */
function renderRawPipe() {
  document.getElementById('rawPipe').innerHTML = `
    <div class="step"><b>1. The publisher</b>${esc((srcEntry(S.source)||{}).api_base || '')},
      at ${esc(((srcEntry(S.source)||{}).rate_limit||{}).requests_per_minute || '?')} requests each minute.</div>
    <div class="step"><b>2. The payload</b>It is written to disk and hashed, before anything reads
      it. The evidence of every number stays on disk.</div>
    <div class="step"><b>3. Four guards</b>The field set, the value range, the time step and the
      count. A payload that fails a guard writes no record.</div>
    <div class="step"><b>4. The store</b>A new row for each value. An equal value writes nothing, and
      a changed value writes a new revision. No row is ever overwritten.</div>
    <div class="step"><b>5. This page</b>The store writes the data files that this page reads. The
      page makes no request to a publisher.</div>`;
  document.getElementById('rawPipeNote').innerHTML = `
    <div class="callout info"><span class="ico">ℹ</span><span>The coverage table above is the record
      of what the store asked for and what it received. A day with no <code>ok</code> row is asked
      for again, so a gap closes by itself on the next day. An <b>empty</b> day is an answer with no
      value in it, and a <b>failed</b> day is an error from the publisher.</span></div>`;
}

function downloadCsv() {
  /* The name states the scope that the rows really have. The coverage view
     holds every country and every source, and the other two hold one country
     and the selected source. */
  const name = S.raw.view === 'coverage'
    ? 'atlas-coverage.csv'
    : `atlas-${S.raw.country}-${S.source}-${S.raw.view}.csv`;
  const lines = [RAW_HEAD.join(',')].concat(RAW_ROWS.map(r =>
    r.map(v => v == null ? '' : (/[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : v)).join(',')));
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}

/* ==========================================================================
   SOURCE REGISTER
   ========================================================================== */
function renderRegister() {
  const collected = D.meta.collectors || [];
  let list = D.sourceList.slice();
  if (S.srcFilter === 'collected') list = list.filter(s => collected.indexOf(s.id) >= 0);
  else if (S.srcFilter !== 'all') list = list.filter(s => s.status === S.srcFilter);
  if (S.srcCat !== 'all') list = list.filter(s => s.category === S.srcCat);

  const counts = {};
  D.sourceList.forEach(s => counts[s.status] = (counts[s.status] || 0) + 1);
  document.getElementById('srcCount').innerHTML =
    `${list.length} of ${D.sourceList.length} sources ` +
    `<span class="hint">${Object.keys(counts).sort().map(k =>
      `${k}: ${counts[k]}`).join(' · ')} · collected: ${collected.length}</span>`;
  document.getElementById('srcList').innerHTML = list.length
    ? srcListHTML(list.map(s => s.id))
    : '<div class="empty">No source matches these filters.</div>';
}

/* ==========================================================================
   Render and events
   ========================================================================== */
function renderTrayStrip() {
  document.getElementById('trayStrip').innerHTML = S.tray.length
    ? S.tray.map((iso, i) => `<span class="chip on" data-iso="${iso}">
        <i style="width:9px;height:9px;border-radius:50%;background:${PALETTE[i % PALETTE.length]};display:inline-block"></i>
        ${iso} ${esc(countryName(iso))}<span class="x">×</span></span>`).join('')
    : '<span class="ciso">The tray is empty. Select a row or a tile on the Overview tab.</span>';
  document.querySelectorAll('#trayStrip .chip').forEach(c =>
    c.onclick = () => toggleTray(c.dataset.iso));
  const reporting = WITH_DAYS.filter(iso => hourVal(iso, S.date, S.hour) != null).length;
  /* A country with history older than the day window keeps its Time of year
     tab and its Raw data tab, and it has no value on a panel of the window. */
  const outside = OUT_OF_WINDOW.length
    ? ` · outside the ${NDAY}-day window: ${OUT_OF_WINDOW.join(', ')}` : '';
  document.getElementById('windowLabel').innerHTML =
    `${windowDates().length} days to ${shortDay(S.date)} · ` +
    `${S.agg === 'hour' ? `the value is the hour ${pad2(S.hour)}:00 UTC`
                        : 'the value is the mean of the window'} · ` +
    `${reporting} of ${plural(WITH_DAYS.length, 'country', 'countries')} ` +
    `${verb(WITH_DAYS.length, 'reports', 'report')} ${pad2(S.hour)}:00 UTC${outside}`;
}

function renderAll() {
  document.querySelectorAll('.rampmax').forEach(el => el.textContent = `${fmt(RAMP_MAX)} ${unitOf()}`);
  renderHeaderStore();
  renderBasisPanel();
  renderTrayStrip();
  renderSourceBlocks();
  if (S.tab === 'overview') renderOverview();
  else if (S.tab === 'season') renderSeason();
  else if (S.tab === 'calc') renderCalc();
  else if (S.tab === 'compare') renderCompare();
  else if (S.tab === 'discrepancy') renderDiscrepancy();
  else if (S.tab === 'forecast') renderForecast();
  else if (S.tab === 'raw') renderRaw();
  else if (S.tab === 'sources') renderRegister();
}

function wire() {
  document.getElementById('tabs').onclick = event => {
    const b = event.target.closest('button[data-tab]');
    if (!b) return;
    S.tab = b.dataset.tab;
    document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tabpanel').forEach(p =>
      p.classList.toggle('active', p.id === 'tab-' + S.tab));
    renderAll();
  };

  const cd = document.getElementById('cDate');
  cd.onchange = () => { if (cd.value) { S.date = cd.value; renderAll(); } };
  document.getElementById('btnPrevDay').onclick = () => {
    const t = dayText(dayNum(S.date) - 1);
    if (dayIn(t)) { S.date = t; cd.value = t; renderAll(); }
  };
  document.getElementById('btnNextDay').onclick = () => {
    const t = dayText(dayNum(S.date) + 1);
    if (dayIn(t)) { S.date = t; cd.value = t; renderAll(); }
  };
  const ch = document.getElementById('cHour');
  ch.value = S.hour;
  document.getElementById('cHourV').textContent = pad2(S.hour) + ':00';
  ch.oninput = () => {
    S.hour = Number(ch.value);
    document.getElementById('cHourV').textContent = pad2(S.hour) + ':00';
    renderAll();
  };
  document.getElementById('cPeriod').onchange = event => { S.period = Number(event.target.value); renderAll(); };
  document.getElementById('cAgg').onchange = event => { S.agg = event.target.value; renderAll(); };
  document.getElementById('cSource').onchange = event => selectSource(event.target.value);

  document.querySelectorAll('.fCountry').forEach(input => input.oninput = () => {
    S.q = input.value;
    document.querySelectorAll('.fCountry').forEach(other => { if (other !== input) other.value = S.q; });
    renderOverview();
  });
  document.getElementById('fEmpty').onchange = event => {
    S.hideEmpty = event.target.value === 'hide'; renderOverview();
  };
  document.getElementById('optBand').onchange = event => { S.band = event.target.checked; renderOverview(); };

  document.getElementById('cSeasonCountry').onchange = event => { S.seasonCountry = event.target.value; renderSeason(); };
  document.getElementById('cFcCountry').onchange = event => { S.fcKey = event.target.value; renderForecast(); };
  document.getElementById('cRawCountry').onchange = event => { S.raw.country = event.target.value; renderRaw(); };
  document.getElementById('cRawView').onchange = event => { S.raw.view = event.target.value; renderRaw(); };
  document.getElementById('btnCsv').onclick = downloadCsv;

  document.getElementById('cAddCountry').onchange = event => {
    if (event.target.value) toggleTray(event.target.value);
  };
  document.getElementById('btnClearTray').onclick = () => { S.tray = []; renderAll(); };

  document.getElementById('cSrcFilter').onchange = event => { S.srcFilter = event.target.value; renderRegister(); };
  document.getElementById('cSrcCat').onchange = event => { S.srcCat = event.target.value; renderRegister(); };

  /* the calculator controls are drawn on each render, so they are delegated */
  document.getElementById('tab-calc').addEventListener('change', event => {
    const id = event.target.id, value = event.target.value;
    if (id === 'kKwh') S.calc.kwh = Math.max(0.1, Number(value) || 0);
    else if (id === 'kPattern') S.calc.pattern = value;
    else if (id === 'kStart') S.calc.start = Number(value);
    else if (id === 'kEnd') S.calc.end = Number(value);
    else if (id === 'kBase') S.calc.base = value;
    else if (id === 'kPool') S.calc.pool = value;
    else if (id === 'kPue') S.calc.pue = Math.max(1, Number(value) || 1);
    else return;
    renderCalc();
  });
}

boot();
