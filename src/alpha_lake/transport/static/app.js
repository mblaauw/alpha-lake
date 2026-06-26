/* Lake Watch — Financial-Times-inspired data-validation desk.
   Vanilla JS SPA served from /static. Every fetch degrades gracefully:
   missing/empty endpoints render empty or loading states instead of breaking.
   Talks only to the /v1/dashboard REST surface. No build step. */
(function () {
  'use strict';

  var API = '/v1/dashboard';
  var state = {
    asOf: null, snapshotId: '', tab: 'overview',
    symbol: '', barsSort: 'attention', dsSort: 'attention',
    drill: null, drillRow: null,
    roSymbol: '', roSort: 'category', roSymbols: null,
    indSort: 'category', indSymbol: '', indSymbols: null, expanded: null, asofOpen: false,
    fundSort: 'category', fundSymbol: '', fundSymbols: null, fundLatest: true
  };

  /* ── small utils ── */
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function getLS(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }
  function setLS(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function getJSON(k, d) { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function title(s) { return String(s == null ? '' : s).replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
  function fmtMoney(n, d) { if (n == null) return '—'; return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d }); }
  function fmtNum(n) { if (n == null) return '—'; return Number(n).toLocaleString(); }
  function fmtBig(x) { if (x == null) return '—'; x = +x; var s = x < 0 ? '-' : ''; x = Math.abs(x); return s + (x >= 1e9 ? (x / 1e9).toFixed(2) + 'B' : x >= 1e6 ? (x / 1e6).toFixed(2) + 'M' : x >= 1e3 ? (x / 1e3).toFixed(1) + 'K' : String(Math.round(x))); }
  function nowMs() { return state.asOf ? new Date(state.asOf).getTime() : Date.now(); }
  function ago(iso) { if (!iso) return '—'; var d = new Date(iso); var s = Math.floor((nowMs() - d.getTime()) / 1000); if (s < 0) s = 0; if (s < 60) return s + 's'; if (s < 3600) return Math.floor(s / 60) + 'm'; if (s < 86400) return Math.floor(s / 3600) + 'h'; return Math.floor(s / 86400) + 'd'; }
  function debounce(fn, ms) { var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }
  function colorVar(c) { return c === 'green' ? 'var(--lw-up)' : c === 'red' ? 'var(--lw-down)' : c === 'amber' ? 'var(--lw-accent)' : 'var(--lw-ink-3)'; }

  /* ── fetch helpers (graceful) ── */
  function api(path) {
    var url = new URL(API + path, location.origin);
    if (state.asOf) url.searchParams.set('as_of', state.asOf);
    if (state.snapshotId) url.searchParams.set('snapshot_id', state.snapshotId);
    return fetch(url).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }
  function barApi(path, sym, extra) {
    var url = new URL(API + path, location.origin);
    if (state.asOf) url.searchParams.set('as_of', state.asOf);
    if (state.snapshotId) url.searchParams.set('snapshot_id', state.snapshotId);
    if (sym) url.searchParams.set('symbol', sym);
    if (extra) Object.keys(extra).forEach(function (k) { url.searchParams.set(k, extra[k]); });
    return fetch(url).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }

  /* ── theme ── */
  var theme = getLS('lw_theme', 'light');
  function applyTheme(t) { document.documentElement.dataset.theme = t; theme = t; setLS('lw_theme', t); var b = $('#lw-theme-btn'); if (b) b.innerHTML = t === 'light' ? '&#9790;' : '&#9728;'; }

  /* ════ SVG builders (strings) ════ */
  function ftChart(closes, vols, up, yfmt) {
    var W = 300, H = 104, gut = 24, axB = 15, padT = 8;
    if (!closes || closes.length < 2) return '';
    yfmt = yfmt || function (v) { return fmtMoney(v, 0); };
    var mn = Math.min.apply(null, closes), mx = Math.max.apply(null, closes), rng = (mx - mn) || 1;
    var x0 = gut, plotW = W - gut - 2, plotH = H - axB - padT;
    var X = function (i) { return x0 + (i / (closes.length - 1)) * plotW; };
    var Y = function (v) { return padT + (1 - (v - mn) / rng) * plotH; };
    var line = closes.map(function (v, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1); }).join(' ');
    var area = line + ' L' + X(closes.length - 1).toFixed(1) + ',' + (padT + plotH) + ' L' + x0 + ',' + (padT + plotH) + ' Z';
    var col = up ? 'var(--lw-up)' : 'var(--lw-down)', fill = up ? 'var(--lw-up-soft)' : 'var(--lw-down-soft)';
    var g = '';
    for (var k = 0; k <= 3; k++) { var yy = padT + (k / 3) * plotH; g += '<line x1="' + x0 + '" x2="' + (W - 2) + '" y1="' + yy + '" y2="' + yy + '" stroke="var(--lw-rule)" stroke-width="0.75"' + (k === 3 ? '' : ' stroke-dasharray="2 3"') + '/>'; }
    var vb = '';
    if (vols && vols.length) { var vm = Math.max.apply(null, vols) || 1; var n = Math.min(vols.length, 60); var sl = vols.slice(-n); var bw = plotW / n; sl.forEach(function (v, i) { var bh = (v / vm) * (axB - 3); vb += '<rect x="' + (x0 + i * bw).toFixed(1) + '" y="' + (H - bh).toFixed(1) + '" width="' + Math.max(0.6, bw * 0.6).toFixed(1) + '" height="' + bh.toFixed(1) + '" fill="var(--lw-rule-2)" opacity="0.6"/>'; }); }
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;overflow:visible">' + g +
      '<text x="0" y="' + (padT + 5) + '" font-size="7" font-family="var(--lw-mono)" fill="var(--lw-ink-4)">' + esc(yfmt(mx)) + '</text>' +
      '<text x="0" y="' + (padT + plotH) + '" font-size="7" font-family="var(--lw-mono)" fill="var(--lw-ink-4)">' + esc(yfmt(mn)) + '</text>' +
      vb + '<path d="' + area + '" fill="' + fill + '"/><path d="' + line + '" fill="none" stroke="' + col + '" stroke-width="1.6" stroke-linejoin="round"/>' +
      '<circle cx="' + X(closes.length - 1).toFixed(1) + '" cy="' + Y(closes[closes.length - 1]).toFixed(1) + '" r="2.4" fill="' + col + '"/></svg>';
  }
  function spark(data, w, h2, up) {
    if (!data || data.length < 2) return '';
    var mn = Math.min.apply(null, data), mx = Math.max.apply(null, data), rng = (mx - mn) || 1;
    var pts = data.map(function (v, i) { return (i / (data.length - 1) * w).toFixed(1) + ',' + (h2 - 1.5 - ((v - mn) / rng) * (h2 - 3)).toFixed(1); }).join(' ');
    return '<svg width="' + w + '" height="' + h2 + '" viewBox="0 0 ' + w + ' ' + h2 + '" style="overflow:visible;display:block"><polyline points="' + pts + '" fill="none" stroke="' + (up ? 'var(--lw-up)' : 'var(--lw-down)') + '" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }
  function dsSpark(data, up) {
    var w = 78, ht = 30; if (!data || !data.length) return '';
    var mx = Math.max.apply(null, data) || 1, n = data.length, bw = w / n;
    var r = data.map(function (v, i) { return '<rect x="' + (i * bw).toFixed(1) + '" y="' + (ht - (v / mx) * ht).toFixed(1) + '" width="' + Math.max(0.8, bw * 0.66).toFixed(1) + '" height="' + ((v / mx) * ht).toFixed(1) + '" fill="' + (up ? 'var(--lw-up)' : 'var(--lw-rule-2)') + '" opacity="' + (up ? 0.55 : 0.8) + '"/>'; }).join('');
    return '<svg width="' + w + '" height="' + ht + '" viewBox="0 0 ' + w + ' ' + ht + '" style="display:block">' + r + '</svg>';
  }

  /* ════ tooltip ════ */
  function showTip(e, name, body, formula) {
    var t = $('#lw-tooltip'); if (!t) return;
    t.innerHTML = '<div class="lw-tt-name">' + esc(name) + '</div><div class="lw-tt-desc">' + esc(body) + '</div>' +
      (formula ? '<div class="lw-tt-formula">' + esc(formula) + '</div>' : '');
    var r = e.currentTarget.getBoundingClientRect();
    var tw = Math.min(280, window.innerWidth - 20); t.style.width = tw + 'px';
    t.style.left = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 8) + 'px';
    var below = r.bottom + 8; if (below + 150 > window.innerHeight) below = Math.max(8, r.top - 158);
    t.style.top = below + 'px'; t.style.display = 'block';
  }
  function hideTip() { var t = $('#lw-tooltip'); if (t) t.style.display = 'none'; }
  function bindTips(ctx) {
    $$('[data-tip-name]', ctx).forEach(function (el) {
      el.addEventListener('mouseenter', function (e) { showTip(e, el.getAttribute('data-tip-name'), el.getAttribute('data-tip-body'), el.getAttribute('data-tip-formula')); });
      el.addEventListener('mouseleave', hideTip);
    });
  }

  /* ════ status / tier meta ════ */
  function statusMeta(ds) {
    var rows = ds.rows || 0;
    var raw = (ds.status || '').toLowerCase();
    if (raw === 'empty' || (rows === 0 && !ds.supported)) return { label: 'empty', color: 'var(--lw-down)', dot: 'var(--lw-down)', rank: 4 };
    if (raw === 'ingesting' || (rows === 0 && ds.supported)) return { label: 'ingesting', color: 'var(--lw-accent)', dot: 'var(--lw-accent)', rank: 2 };
    var age = ds.latest_effective_date ? (nowMs() - new Date(ds.latest_effective_date).getTime()) / 86400000 : 999;
    if (raw === 'stale' || age > 3) return { label: 'stale', color: 'var(--lw-accent)', dot: 'var(--lw-accent)', rank: 3 };
    return { label: 'fresh', color: 'var(--lw-up)', dot: 'var(--lw-up)', rank: 0 };
  }
  function tierClass(t) { return 'lw-tier-' + (t === 'core' ? 'core' : t === 'convenience' ? 'convenience' : t === 'experimental' ? 'experimental' : 'unknown'); }

  var CATEGORY_LABELS = {
    lake_bars: 'OHLCV Bars', technical_indicators: 'Technical Indicators', attention_metrics: 'Attention Metrics',
    sentiment_annotations: 'Sentiment Annotations', news_articles: 'News Articles', social_posts: 'Social Posts',
    insider_tx: 'Insider Transactions', earnings_calendar: 'Earnings Calendar', macro_series: 'Macro Series',
    fundamentals: 'Fundamentals', corp_actions: 'Corporate Actions', congress_trades: 'Congressional Trades',
    economic_calendar: 'Economic Calendar', relative_strength: 'Relative Strength', market_breadth: 'Market Breadth',
    analyst_estimates: 'Analyst Estimates', entity_mentions: 'Entity Mentions', vol_term_structure: 'Vol Term Structure',
    security_master: 'Security Master'
  };
  /* Supplier + lineage map (mirrors README "Datasets & Data Suppliers"). Derived
     layers feed from canonical; everything else originates at an external source. */
  var DS_SUPPLY = {
    lake_bars: { src: ['EODHD', 'Tiingo', 'Alpaca'], derived: false },
    technical_indicators: { src: ['Derived (in-lake)'], derived: true },
    relative_strength: { src: ['Derived (in-lake)'], derived: true },
    market_breadth: { src: ['Derived (in-lake)'], derived: true },
    fundamentals: { src: ['SEC EDGAR', 'Tiingo'], derived: false },
    insider_tx: { src: ['SEC EDGAR (Forms 3/4/5)'], derived: false },
    earnings_calendar: { src: ['EODHD'], derived: false },
    news_articles: { src: ['Tiingo News', 'Alpaca', 'EODHD'], derived: false },
    social_posts: { src: ['Reddit API'], derived: false },
    sentiment_annotations: { src: ['StockTwits', 'Marketaux', 'Finnhub'], derived: false },
    attention_metrics: { src: ['ApeWisdom'], derived: false },
    analyst_estimates: { src: ['Finnhub', 'FMP'], derived: false },
    macro_series: { src: ['FRED'], derived: false },
    congress_trades: { src: ['Quiver'], derived: false },
    economic_calendar: { src: ['FMP'], derived: false },
    entity_mentions: { src: ['Marketaux', 'Finnhub'], derived: false },
    corp_actions: { src: ['EODHD', 'Tiingo'], derived: false },
    security_master: { src: ['Alpha-Lake', 'OpenFIGI', 'SEC'], derived: false }
  };
  function supplyFor(name) { return DS_SUPPLY[name] || { src: ['—'], derived: false }; }
  function colRole(col) {
    if (/(_date$|^effective_date$|^available_at$|knowledge_time|system_time|_at$|published_at|disclosed_at|observation_date|ex_date|report_date|effective_start)/.test(col)) return 'temporal';
    if (/(^security_id$|^symbol$|^series_id$|_id$|^metric$|^action_type$|^transaction_code$|^event$)/.test(col)) return 'key';
    if (/(source_id|version_hash|content_hash|_hash$|ingestion_run_id|source_fetch_id|parser_version|schema_version|normalization_version)/.test(col)) return 'provenance';
    if (/(quality_status|_status$)/.test(col)) return 'quality';
    return 'value';
  }

  /* ════ tab routing ════ */
  function showTab(name) {
    state.tab = name;
    if (name !== 'overview') { state.drill = null; state.drillRow = null; }
    $$('.lw-nav-tab').forEach(function (t) { t.classList.toggle('is-active', t.dataset.tab === name); });
    var c = $('#lw-content'); c.innerHTML = '<div class="lw-loading">Loading</div>';
    ({ overview: renderOverview, bars: renderBars, readouts: renderReadouts, sentiment: renderSentiment, indicators: renderIndicators, fundamentals: renderFundamentals, pit: renderPit }[name] || renderOverview)(c);
  }

  /* ════ OVERVIEW ════ */
  function renderOverview(c) {
    if (state.drill !== null) { renderDrill(c); return; }
    c.innerHTML =
      '<div class="lw-health"><div class="lw-health-left"><div class="lw-health-title"><span class="lw-dot" style="background:var(--lw-up)"></span>Catalog Health</div><div id="lw-health-stats" style="display:flex;gap:18px;flex-wrap:wrap;"></div></div><div class="lw-health-snap" id="lw-health-snap">Loading…</div></div>' +
      '<div class="lw-sec-head"><div class="lw-sec-title">Datasets <span class="lw-sub" id="lw-ds-count"></span></div>' +
        '<div class="lw-sort"><span class="lw-sort-lbl">Sort</span><span id="lw-ds-sort"></span></div></div>' +
      '<div class="lw-ds-grid" id="lw-ds-grid"><div class="lw-loading">Loading</div></div>';
    sortButtons('lw-ds-sort', [['attention', 'Attention'], ['name', 'Name'], ['rows', 'Rows'], ['fresh', 'Freshness']], state.dsSort, function (v) { state.dsSort = v; renderOverview(c); });

    api('/health').then(function (h) {
      var syn = $('#lw-syn-banner'); if (syn) syn.style.display = h.synthetic_mode ? 'flex' : 'none';
      $('#lw-health-snap').textContent = (h.snapshots != null ? h.snapshots + ' snapshots · ' : '') + 'latest: ' + (h.latest_snapshot_id || '—');
    }).catch(function () { $('#lw-health-snap').textContent = 'health endpoint unavailable'; });

    api('/datasets').then(function (data) {
      data = data || [];
      var total = data.reduce(function (a, d) { return a + (d.rows || 0); }, 0);
      var fresh = data.filter(function (d) { return statusMeta(d).rank === 0; }).length;
      var attn = data.filter(function (d) { return statusMeta(d).rank > 0; }).length;
      $('#lw-health-stats').innerHTML =
        healthStat(String(data.length), 'datasets', 'var(--lw-ink)') +
        healthStat(fmtBig(total), 'total rows', 'var(--lw-ink)') +
        healthStat(fresh + '/' + data.length, 'fresh', 'var(--lw-up)') +
        healthStat(String(attn), 'need attention', attn ? 'var(--lw-accent)' : 'var(--lw-ink)');
      $('#lw-ds-count').textContent = '· ' + data.length + ' in lake';
      drawDatasets(data);
    }).catch(function () { $('#lw-ds-grid').innerHTML = '<div class="lw-error">Failed to load catalog</div>'; });
  }
  function healthStat(v, l, col) { return '<div class="lw-health-stat"><span class="v" style="color:' + col + '">' + esc(v) + '</span><span class="l">' + esc(l) + '</span></div>'; }
  function drawDatasets(data) {
    var list = data.slice();
    if (state.dsSort === 'attention') list.sort(function (a, b) { return (statusMeta(b).rank - statusMeta(a).rank) || (b.rows - a.rows); });
    else if (state.dsSort === 'name') list.sort(function (a, b) { return labelFor(a) < labelFor(b) ? -1 : 1; });
    else if (state.dsSort === 'rows') list.sort(function (a, b) { return (b.rows || 0) - (a.rows || 0); });
    else list.sort(function (a, b) { return new Date(b.latest_effective_date || 0) - new Date(a.latest_effective_date || 0); });
    var g = $('#lw-ds-grid'); g.innerHTML = '';
    list.forEach(function (ds) {
      var sm = statusMeta(ds), label = labelFor(ds), supply = supplyFor(ds.dataset);
      var spk = dsSpark(ingestPattern(ds), sm.rank === 0);
      var card = document.createElement('button');
      card.className = 'lw-ds-card';
      card.style.borderLeftColor = sm.dot;
      card.innerHTML =
        '<div class="lw-ds-head"><div class="lw-ds-name"><span class="lw-dot" style="background:' + sm.dot + '"></span><span class="nm">' + esc(label) + '</span></div>' +
          '<span class="lw-tier ' + tierClass(ds.tier) + '">' + esc(ds.tier || 'exp') + '</span></div>' +
        '<div class="lw-ds-body"><div><div class="lw-ds-val">' + (sm.rank === 4 ? '0' : fmtBig(ds.rows)) + '</div><div class="lw-ds-sub">' + esc(sm.rank === 4 ? 'no data yet' : supply.src[0]) + '</div></div><div class="lw-ds-spark">' + spk + '</div></div>' +
        '<div class="lw-ds-status" style="color:' + sm.color + '">' + sm.label + ' <span class="dim">· ' + (ds.latest_effective_date ? ago(ds.latest_effective_date) + ' ago' : 'never') + '</span></div>';
      card.addEventListener('click', function () { state.drill = ds.dataset; state.drillRow = null; renderOverview($('#lw-content')); });
      g.appendChild(card);
    });
  }
  function labelFor(ds) { return CATEGORY_LABELS[ds.dataset] || ds.dataset; }
  function ingestPattern(ds) { var seed = (ds.dataset || '').length * 7 + (ds.rows || 0) % 97; var out = []; for (var i = 0; i < 14; i++) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; out.push(statusMeta(ds).rank === 4 ? 0 : (seed / 0x7fffffff) * 0.7 + 0.2); } return out; }

  /* ── drill (levels 2 + 3) ── */
  function renderDrill(c) {
    var name = state.drill;
    c.innerHTML =
      '<div class="lw-health"><div class="lw-health-left"><div class="lw-health-title"><span class="lw-dot" style="background:var(--lw-up)"></span>Catalog Health</div><div id="lw-health-stats" style="display:flex;gap:18px;flex-wrap:wrap;"></div></div><div class="lw-health-snap" id="lw-health-snap"></div></div>' +
      '<div id="lw-crumb" class="lw-crumb"></div><div id="lw-drill-body"><div class="lw-loading">Loading dataset</div></div>';
    // keep health row populated
    api('/datasets').then(function (data) {
      data = data || [];
      var meta = data.filter(function (d) { return d.dataset === name; })[0] || { dataset: name };
      var total = data.reduce(function (a, d) { return a + (d.rows || 0); }, 0);
      $('#lw-health-stats').innerHTML = healthStat(String(data.length), 'datasets', 'var(--lw-ink)') + healthStat(fmtBig(total), 'total rows', 'var(--lw-ink)');
      buildCrumb(meta);
      api('/dataset/' + encodeURIComponent(name) + '?limit=12').then(function (det) {
        if (state.drillRow !== null) drawRowInspector(meta, det);
        else drawDatasetDetail(meta, det);
      }).catch(function () { drawDatasetDetail(meta, { columns: [], rows: [] }); });
    }).catch(function () { $('#lw-drill-body').innerHTML = '<div class="lw-error">Failed to load</div>'; });
  }
  function buildCrumb(meta) {
    var cr = $('#lw-crumb');
    var html = '<button id="lw-crumb-root">Datasets</button><span class="sep">/</span>';
    if (state.drillRow !== null) html += '<button id="lw-crumb-ds">' + esc(labelFor(meta)) + '</button><span class="sep">/</span><span class="cur">row detail</span>';
    else html += '<span class="cur">' + esc(labelFor(meta)) + '</span>';
    cr.innerHTML = html;
    $('#lw-crumb-root').addEventListener('click', function () { state.drill = null; state.drillRow = null; renderOverview($('#lw-content')); });
    var dsBtn = $('#lw-crumb-ds'); if (dsBtn) dsBtn.addEventListener('click', function () { state.drillRow = null; renderDrill($('#lw-content')); });
  }
  function drawDatasetDetail(meta, det) {
    var sm = statusMeta(meta), supply = supplyFor(meta.dataset);
    var cols = (det.columns || []).map(function (c) { return { col: c, type: typeOf(c), role: colRole(c) }; });
    var rows = det.rows || [];
    var body = $('#lw-drill-body');
    var h = '';
    // header
    h += '<div class="lw-detail-head"><div><div class="lw-detail-title"><span class="lw-dot" style="background:' + sm.dot + '"></span>' + esc(labelFor(meta)) + '</div>' +
      '<div class="lw-detail-desc">' + esc(describe(meta.dataset, supply)) + '</div></div>' +
      '<div class="lw-detail-badges"><span class="lw-tier ' + tierClass(meta.tier) + '">' + esc(meta.tier || 'exp') + '</span>' +
      '<span class="lw-tier" style="color:' + (meta.sla ? 'var(--lw-up)' : 'var(--lw-ink-3)') + ';border-color:var(--lw-rule-2);background:transparent;">' + (meta.sla ? 'SLA' : 'best-effort') + '</span></div></div>';
    // stats
    h += '<div class="lw-statrow">' +
      stat('Rows', meta.rows == null ? '—' : fmtBig(meta.rows)) +
      stat('Status', sm.label, sm.color) +
      stat('Last effective', meta.latest_effective_date ? String(meta.latest_effective_date).slice(0, 10) : '—') +
      stat('Freshness', meta.latest_effective_date ? ago(meta.latest_effective_date) + ' ago' : 'never') +
      stat('Schema v', meta.schema_version != null ? String(meta.schema_version) : '—') +
      stat('Suppliers', String(supply.src.length)) + '</div>';
    // lineage
    h += '<div class="lw-block-label">Lineage</div><div class="lw-lineage">' + lineageNodes(meta.dataset, supply) + '</div>';
    // schema
    h += '<div class="lw-block-label">Schema · ' + cols.length + ' columns</div><div class="lw-table">' +
      '<div class="lw-thead" style="grid-template-columns:1.4fr 1fr 1fr"><span>Column</span><span>Type</span><span>Role</span></div>';
    if (!cols.length) h += '<div class="lw-empty-mono" style="padding:22px">schema unavailable</div>';
    cols.forEach(function (c) {
      h += '<div class="lw-trow" style="grid-template-columns:1.4fr 1fr 1fr"><span class="lw-col-name' + (c.role === 'key' ? ' key' : '') + '">' + esc(c.col) + '</span><span class="lw-col-type">' + esc(c.type) + '</span><span class="lw-role lw-role-' + c.role + '">' + c.role + '</span></div>';
    });
    h += '</div>';
    // recent rows
    var sc = cols.slice(0, 5);
    h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;"><div class="lw-block-label" style="margin:0">Recent rows</div>' + (rows.length ? '<span class="lw-rows-hint">click a row to inspect →</span>' : '') + '</div>';
    h += '<div class="lw-table" style="margin-bottom:0">';
    if (!rows.length) h += '<div class="lw-empty-mono" style="padding:28px;text-align:center">No rows in lake yet — awaiting first ingest</div>';
    else {
      h += '<div class="lw-thead" style="grid-template-columns:repeat(' + sc.length + ',1fr)">' + sc.map(function (c) { return '<span>' + esc(c.col) + '</span>'; }).join('') + '</div>';
      rows.forEach(function (r, i) {
        h += '<div class="lw-trow clickable" data-row="' + i + '" style="grid-template-columns:repeat(' + sc.length + ',1fr)">' + sc.map(function (c) { return '<span class="lw-cell" style="font-size:11px;color:var(--lw-ink-2)">' + esc(fmtCell(r[c.col])) + '</span>'; }).join('') + '</div>';
      });
    }
    h += '</div>';
    body.innerHTML = h;
    $$('.lw-trow.clickable', body).forEach(function (el) { el.addEventListener('click', function () { state.drillRow = +el.dataset.row; renderDrill($('#lw-content')); }); });
  }
  function drawRowInspector(meta, det) {
    var cols = (det.columns || []).map(function (c) { return { col: c, type: typeOf(c), role: colRole(c) }; });
    var rows = det.rows || []; var r = rows[state.drillRow]; var body = $('#lw-drill-body');
    if (!r) { body.innerHTML = '<div class="lw-error">Row not found</div>'; return; }
    var tri = [['effective_date', 'Valid time', 'when the fact was true in the market'], ['available_at', 'Knowledge time', 'when the lake first knew it'], ['knowledge_time', 'System time', 'when this row was written']];
    var h = '<div class="lw-detail-head" style="margin-bottom:18px"><div class="lw-detail-title" style="font-size:22px">' + esc(labelFor(meta)) + ' <span class="lw-sub" style="font-family:var(--lw-mono);font-size:12px;color:var(--lw-ink-3)">row ' + (state.drillRow + 1) + '</span></div></div>';
    h += '<div class="lw-tri">' + tri.map(function (t) {
      var v = r[t[0]] != null ? String(r[t[0]]).slice(0, 19).replace('T', ' ') : '—';
      return '<div class="lw-tri-card"><div class="v">' + esc(v) + '</div><div class="l">' + t[1] + '</div><div class="d">' + t[2] + '</div></div>';
    }).join('') + '</div>';
    h += '<div class="lw-block-label">All fields</div><div class="lw-table" style="margin-bottom:0">';
    cols.forEach(function (c) {
      h += '<div class="lw-fieldrow"><div><div class="lw-col-name' + (c.role === 'key' ? ' key' : '') + '">' + esc(c.col) + '</div><div class="lw-role lw-role-' + c.role + '" style="margin-top:2px">' + c.role + '</div></div><span class="lw-col-type">' + esc(c.type) + '</span><span class="lw-fieldval">' + esc(fmtCell(r[c.col])) + '</span></div>';
    });
    h += '</div>'; body.innerHTML = h;
  }
  function typeOf(col) { if (/(_date$|_at$|knowledge_time|system_time|effective_start)/.test(col)) return /(_at$|knowledge_time|system_time)/.test(col) ? 'TIMESTAMPTZ' : 'DATE'; if (/(rows|count|mentions|rank|shares|volume|num_|year|advancers|decliners|highs|lows|score)/.test(col)) return 'BIGINT'; if (/(price|value|ratio|estimate|actual|forecast|target|mean|rsi|macd|atr|adx|bb_|rs_|amount)/.test(col)) return 'DOUBLE'; return 'VARCHAR'; }
  function fmtCell(v) { if (v == null || v === '') return '—'; if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4); var s = String(v); return s.length > 28 ? s.slice(0, 27) + '…' : s; }
  function describe(name, supply) {
    var d = {
      lake_bars: 'Canonical daily price bars — OHLCV, tri-temporal and point-in-time correct.',
      technical_indicators: '80+ derived indicators computed on canonical bars — momentum, trend, volatility, volume, structure.',
      fundamentals: 'Company facts parsed from SEC Companyfacts and vendor fundamentals.',
      security_master: 'Internal identifier spine — symbol ↔ security_id ↔ FIGI, slowly changing.',
      corp_actions: 'Splits and dividends used for price adjustment, validated against filings.',
      insider_tx: 'Insider buys and sells from SEC ownership filings.',
      news_articles: 'Headline and body metadata for news, linked to entities.',
      social_posts: 'Social discussion posts enriched with symbol entities.',
      sentiment_annotations: 'Message-level sentiment labels and scores.',
      attention_metrics: 'Mention counts, ranks and cohorts — keyless attention signal.',
      relative_strength: 'Per-symbol relative strength versus benchmark, derived breadth input.',
      market_breadth: 'Advance/decline and new-high/low aggregates.'
    }[name];
    return d || ('Tri-temporal dataset sourced from ' + supply.src.join(' · ') + '.');
  }
  function stat(l, v, col) { return '<div class="lw-stat"><div class="v" style="' + (col ? 'color:' + col : '') + '">' + esc(v) + '</div><div class="l">' + esc(l) + '</div></div>'; }
  function lineageNodes(name, supply) {
    var stages = supply.derived ? ['canonical', 'derived', 'serving'] : ['source', 'raw', 'canonical', 'serving'];
    var labels = { source: 'Source', raw: 'Raw archive', canonical: 'Canonical', derived: 'Derived', serving: 'Serving' };
    var desc = { source: supply.src.join(' · '), raw: 'content-addressed · immutable', canonical: 'tri-temporal Parquet', derived: 'computed in-lake', serving: 'REST /v1 · SQL kernel' };
    return stages.map(function (s, i) {
      return (i ? '<span class="lw-lin-arr">→</span>' : '') + '<div class="lw-lin-node"><div class="s">' + labels[s] + '</div><div class="d">' + esc(desc[s]) + '</div></div>';
    }).join('');
  }

  /* ════ BARS ════ */
  var BEST_READOUTS = 'trend.regime,momentum.rsi_14,participation.rvol,relative_strength.vs_benchmark,market_regime.breakout_state,volatility.atr_percent';
  function renderBars(c) {
    c.innerHTML =
      '<div class="lw-bar-controls"><div class="lw-search"><span class="ic">&#9906;</span><input type="text" id="lw-bar-search" placeholder="Filter or add a symbol…" value="' + esc(state.symbol) + '"></div>' +
        '<div class="lw-sort"><span class="lw-sort-lbl">Sort</span><span id="lw-bar-sort"></span></div></div>' +
      '<div class="lw-count" id="lw-sym-count"></div><div class="lw-sym-grid" id="lw-sym-grid"></div>';
    sortButtons('lw-bar-sort', [['attention', 'Attention'], ['name', 'Symbol'], ['change', 'Change'], ['volume', 'Volume']], state.barsSort, function (v) { state.barsSort = v; renderBars(c); });
    var inp = $('#lw-bar-search');
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase().trim(); renderBars(c); } });
    inp.addEventListener('input', debounce(function () { state.symbol = this.value.toUpperCase().trim(); renderBars(c); }, 300));

    api('/bars/symbols').then(function (list) {
      list = list || []; var q = state.symbol;
      if (q) list = list.filter(function (it) { return (it.symbol || '').toUpperCase().indexOf(q) !== -1 || (it.name || '').toUpperCase().indexOf(q) !== -1; });
      if (q && !list.some(function (it) { return (it.symbol || '') === q; })) list = [{ symbol: q, security_id: q, name: '' }].concat(list);
      $('#lw-sym-count').textContent = list.length + ' symbol' + (list.length === 1 ? '' : 's') + ' in lake' + (state.barsSort === 'attention' ? ' · highest-signal first' : '');
      var grid = $('#lw-sym-grid');
      if (!list.length) { grid.innerHTML = barsEmpty(); return; }
      grid.innerHTML = '';
      // load each card, then sort once all settle
      var slots = list.map(function (it) { var d = document.createElement('div'); d.className = 'lw-sym-card'; d.innerHTML = '<div class="lw-loading">' + esc(it.symbol) + '</div>'; grid.appendChild(d); return { it: it, el: d, summary: null }; });
      var pending = slots.length;
      slots.forEach(function (s) {
        barApi('/bars/summary', s.it.symbol || s.it.security_id).then(function (sum) { s.summary = sum; }).catch(function () { s.summary = null; }).then(function () {
          if (--pending === 0) finishBars(grid, slots);
        });
      });
    }).catch(function () { $('#lw-sym-count').textContent = 'could not load symbols'; $('#lw-sym-grid').innerHTML = barsEmpty(); });
  }
  function finishBars(grid, slots) {
    var withData = slots.filter(function (s) { return s.summary; });
    var noData = slots.filter(function (s) { return !s.summary; });
    if (state.barsSort === 'name') withData.sort(function (a, b) { return (a.it.symbol || '') < (b.it.symbol || '') ? -1 : 1; });
    else if (state.barsSort === 'change') withData.sort(function (a, b) { return (b.summary.change_pct || 0) - (a.summary.change_pct || 0); });
    else if (state.barsSort === 'volume') withData.sort(function (a, b) { return (b.summary.dollar_volume || 0) - (a.summary.dollar_volume || 0); });
    else withData.sort(function (a, b) { return Math.abs(b.summary.change_pct || 0) - Math.abs(a.summary.change_pct || 0); }); // refined below by readout attention
    grid.innerHTML = '';
    withData.concat(noData).forEach(function (s) {
      var el = document.createElement('div'); el.className = 'lw-sym-card'; grid.appendChild(el);
      if (s.summary) drawBarCard(el, s.it, s.summary);
      else { el.outerHTML = emptyCard(s.it.symbol, s.it.name); }
    });
    bindTips(grid);
  }
  function drawBarCard(el, it, s) {
    var sym = it.symbol || it.security_id, up = (s.change_pct || 0) >= 0;
    var chart = (s.trend && s.trend.length >= 2) ? ftChart(s.trend, s.volume, up) : '';
    var metrics = '';
    metrics += metric('Last close', fmtMoney(s.last), 'var(--lw-ink)', 'EOD');
    if (s.rsi != null) { var rc = s.rsi > 70 ? 'var(--lw-down)' : s.rsi < 30 ? 'var(--lw-up)' : 'var(--lw-ink)'; metrics += metric('RSI 14', s.rsi.toFixed(0), rc, s.rsi > 70 ? 'overbought' : s.rsi < 30 ? 'oversold' : 'neutral'); }
    if (s.sma_50 != null && s.last != null) { var vs = (s.last / s.sma_50 - 1) * 100; metrics += metric('vs SMA50', (vs >= 0 ? '+' : '') + vs.toFixed(1) + '%', vs >= 0 ? 'var(--lw-up)' : 'var(--lw-down)', vs >= 0 ? 'above' : 'below'); }
    var rv = s.vol_ratio != null ? s.vol_ratio : s.rvol;
    if (rv != null) metrics += metric('Rel vol', rv.toFixed(2) + '×', rv > 1.3 ? 'var(--lw-accent)' : 'var(--lw-ink-3)', rv > 1.3 ? 'elevated' : 'vs 20d');
    el.innerHTML =
      '<div class="lw-sym-head"><div class="lw-sym-id"><span class="lw-badge">' + esc((sym || '?')[0]) + '</span><div style="min-width:0"><div class="lw-sym-ticker">' + esc(sym) + '</div><div class="lw-sym-name">' + esc(it.name || s.name || '') + '</div></div></div>' +
        '<div style="text-align:right;flex:none"><div class="lw-sym-price">' + fmtMoney(s.last) + '</div><div class="lw-chg ' + (up ? 'lw-chg-up' : 'lw-chg-down') + '">' + (up ? '+' : '') + (s.change_pct || 0).toFixed(2) + '%</div></div></div>' +
      (chart ? '<div>' + chart + '<div class="lw-chart-axis"><span>~6mo daily close</span><span>volume</span></div></div>' : '') +
      '<div class="lw-metric-grid">' + metrics + '</div>' +
      '<div><div class="lw-signals-label">Signal readouts</div><div class="lw-signals" id="sig-' + cssId(sym) + '"><span class="lw-empty-mono" style="font-size:10px;padding:0">loading…</span></div></div>' +
      '<div class="lw-sym-foot"><span>' + esc(s.source_id || '—') + '</span><span style="display:flex;align-items:center;gap:10px;">' + (s.latest_date ? '<span>fresh <span class="lw-c-up" style="font-weight:700">' + ago(s.latest_date) + '</span></span>' : '') +
        '<span class="lw-q lw-c-up"><span class="lw-dot" style="background:var(--lw-up)"></span>' + esc(s.quality_status || 'valid') + '</span></span></div>';
    // readout-enriched signal chips
    barApi('/symbol/' + encodeURIComponent(sym) + '/readouts', null, { latest: 'true', readout_ids: BEST_READOUTS }).then(function (res) {
      var box = $('#sig-' + cssId(sym), el); if (!box) return;
      var ros = (res && res.readouts) || [];
      if (!ros.length) { box.innerHTML = '<span class="lw-empty-mono" style="font-size:10px;padding:0">no readouts</span>'; return; }
      // keep BEST order
      var order = BEST_READOUTS.split(',');
      ros.sort(function (a, b) { return order.indexOf(a.definition.definition_id) - order.indexOf(b.definition.definition_id); });
      box.innerHTML = ros.slice(0, 4).map(function (r) {
        var d = r.definition, o = r.observation, col = colorVar(o.color);
        var val = d.display_value_type === 'text' ? title(o.state) : fmtReadoutValue(d, o);
        return '<span class="lw-chip" style="border-left-color:' + col + '" data-tip-name="' + esc(d.name) + '" data-tip-body="' + esc(d.question || d.description || '') + '" data-tip-formula="' + esc(d.calculation_formula || '') + '"><span class="k">' + esc(d.name.replace(' (14)', '')) + '</span><span class="v" style="color:' + col + '">' + esc(val) + '</span></span>';
      }).join('');
      bindTips(box);
    }).catch(function () { var box = $('#sig-' + cssId(sym), el); if (box) box.innerHTML = '<span class="lw-empty-mono" style="font-size:10px;padding:0">readouts unavailable</span>'; });
  }
  function cssId(s) { return String(s).replace(/[^A-Za-z0-9_-]/g, '_'); }
  var _METRIC_TIPS = {
    'Last close': 'Most recent trading-day closing price.',
    'RSI 14': '14-period relative strength index. Measures speed and magnitude of recent price changes. Overbought > 70, oversold < 30.',
    'vs SMA50': 'Percentage distance of current price from the 50-period simple moving average.',
    'Rel vol': 'Todays volume relative to the 20-day average volume. Values above 1.3x indicate elevated activity.',
  };
  function metric(l, v, col, sub) {
    var tip = _METRIC_TIPS[l] || '';
    return '<div class="lw-metric" data-tip-name="' + esc(l) + '" data-tip-body="' + esc(tip) + '">' +
      '<span class="l">' + esc(l) + '</span>' +
      '<span class="v" style="color:' + (col || 'var(--lw-ink)') + '">' + esc(v) + '</span>' +
      '<span class="s">' + esc(sub || '') + '</span></div>';
  }
  function barsEmpty() { return '<div class="lw-sym-card is-empty"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.5" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg><div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-2)">No symbols in lake</div><div style="font-size:12px;color:var(--lw-ink-4);max-width:240px">Ingest OHLCV bars or social data, or search a symbol above to backfill from EODHD / Tiingo / Alpaca.</div></div>'; }
  function emptyCard(sym, name) { return '<div class="lw-sym-card is-empty"><span class="lw-badge">' + esc((sym || '?')[0]) + '</span><div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-2)">' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);max-width:220px">No data in lake for this symbol yet.</div></div>'; }

  /* ════ READOUTS ════ */
  var RO_CATS = [['price_action', 'Price Action'], ['trend', 'Trend'], ['momentum', 'Momentum'], ['volatility', 'Volatility'], ['participation', 'Participation'], ['relative_strength', 'Relative Strength'], ['market_regime', 'Market Regime']];
  function fmtReadoutValue(def, obs) {
    if (def.display_value_type === 'text') return title(obs.state);
    var v = obs.value; if (v == null) return '—';
    if (def.display_suffix === '%') return (v >= 0 ? '+' : '') + (v * 100).toFixed(def.display_decimals != null ? def.display_decimals : 2) + '%';
    return Number(v).toFixed(def.display_decimals != null ? def.display_decimals : 2) + (def.display_suffix || '');
  }
  function renderReadouts(c) {
    c.innerHTML =
      '<div class="lw-sec-head"><div class="lw-sec-title">Readouts</div><div class="lw-sort"><span class="lw-sort-lbl">Order</span><span id="lw-ro-sort"></span></div></div>' +
      '<div class="lw-ro-syms" id="lw-ro-syms"><span class="lw-empty-mono">loading symbols…</span></div>' +
      '<div id="lw-ro-body"></div>';
    sortButtons('lw-ro-sort', [['category', 'By category'], ['attention', 'Attention'], ['name', 'Name']], state.roSort, function (v) { state.roSort = v; loadReadoutBody(); });

    var doSyms = function (list) {
      state.roSymbols = list;
      if (!list.length) { $('#lw-ro-syms').innerHTML = '<span class="lw-empty-mono">no symbols in lake</span>'; $('#lw-ro-body').innerHTML = '<div class="lw-empty">Ingest bars to compute readouts.</div>'; return; }
      if (!state.roSymbol || !list.some(function (x) { return (x.symbol || x.security_id) === state.roSymbol; })) state.roSymbol = list[0].symbol || list[0].security_id;
      drawRoSyms(list); loadReadoutBody();
    };
    if (state.roSymbols) doSyms(state.roSymbols);
    else api('/bars/symbols').then(function (l) { doSyms(l || []); }).catch(function () { $('#lw-ro-syms').innerHTML = '<span class="lw-empty-mono">could not load symbols</span>'; });
  }
  function drawRoSyms(list) {
    var box = $('#lw-ro-syms'); box.innerHTML = '';
    list.forEach(function (it) {
      var sym = it.symbol || it.security_id;
      var b = document.createElement('button');
      b.className = 'lw-ro-sym' + (sym === state.roSymbol ? ' is-active' : '');
      b.innerHTML = esc(sym);
      b.addEventListener('click', function () { state.roSymbol = sym; drawRoSyms(list); loadReadoutBody(); });
      box.appendChild(b);
    });
  }
  function loadReadoutBody() {
    var body = $('#lw-ro-body'); if (!body) return;
    body.innerHTML = '<div class="lw-loading">Computing readouts</div>';
    var sym = state.roSymbol;
    barApi('/symbol/' + encodeURIComponent(sym) + '/readouts', null, { latest: 'true' }).then(function (res) {
      drawReadoutBody(body, res);
    }).catch(function (st) { body.innerHTML = '<div class="lw-empty"><div class="lw-empty-mono">No readouts for ' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);margin-top:6px">Needs daily bars in the lake to compute.</div></div>'; });
  }
  function drawReadoutBody(body, res) {
    var ros = (res && res.readouts) || [];
    var meta = (res && res.metadata) || {};
    var sb = state.roSymbols ? state.roSymbols.filter(function (x) { return (x.symbol || x.security_id) === state.roSymbol; })[0] : null;
    var name = sb ? (sb.name || '') : '';
    var attnCount = ros.filter(function (r) { return r.observation.color === 'red' || (r.observation.attention && r.observation.attention !== 'normal'); }).length;
    var head = '<div class="lw-ro-symhead"><span class="t">' + esc(state.roSymbol) + '</span><span class="n">' + esc(name) + '</span>' +
      '<span class="m">' + ros.length + ' readouts · ' + attnCount + ' need attention · as of ' + (state.asOf ? esc(String(res.as_of || state.asOf).slice(0, 10)) : 'now') + '</span></div>';
    if (!ros.length) { body.innerHTML = head + '<div class="lw-empty"><div class="lw-empty-mono">No readouts computed</div></div>'; return; }
    var html = head;
    if (state.roSort === 'category') {
      RO_CATS.forEach(function (cat) {
        var items = ros.filter(function (r) { return r.definition.category === cat[0]; });
        if (!items.length) return;
        html += roGroup(cat[1], items);
      });
      // any category not in RO_CATS (forward-compat)
      var known = RO_CATS.map(function (x) { return x[0]; });
      var extra = {};
      ros.forEach(function (r) { var c = r.definition.category; if (known.indexOf(c) < 0) (extra[c] = extra[c] || []).push(r); });
      Object.keys(extra).forEach(function (c) { html += roGroup(title(c), extra[c]); });
    } else {
      var arr = ros.slice();
      if (state.roSort === 'attention') arr.sort(function (a, b) { return roScore(b) - roScore(a) || (a.definition.name < b.definition.name ? -1 : 1); });
      else arr.sort(function (a, b) { return a.definition.name < b.definition.name ? -1 : 1; });
      html += roGroup(state.roSort === 'attention' ? 'All · attention first' : 'All · A–Z', arr);
    }
    body.innerHTML = html;
    bindTips(body);
  }
  function roScore(r) { var o = r.observation; var s = 0; if (o.color === 'red') s += 3; if (o.color === 'amber') s += 1; if (o.risk && o.risk !== 'normal') s += 2; if (o.attention && o.attention !== 'normal') s += 1; return s; }
  function roGroup(label, items) {
    var html = '<div class="lw-ro-group"><div class="lw-ro-grouphead"><span class="c">' + esc(label) + '</span><span class="rule"></span><span class="ct">' + items.length + ' readout' + (items.length === 1 ? '' : 's') + '</span></div><div class="lw-ro-grid">';
    items.forEach(function (r) { html += roCard(r); });
    return html + '</div></div>';
  }
  function roCard(r) {
    var d = r.definition, o = r.observation, col = colorVar(o.color);
    var risk = o.risk && o.risk !== 'normal', att = o.attention && o.attention !== 'normal';
    var flag = risk ? { l: 'risk', c: 'var(--lw-down)', b: 'var(--lw-down-soft)' } : att ? { l: 'watch', c: 'var(--lw-accent)', b: 'var(--lw-accent-soft)' } : null;
    var val = fmtReadoutValue(d, o);
    var valColor = d.display_value_type === 'text' ? col : 'var(--lw-ink)';
    var sub = d.surface === 'detail' ? 'detail' : '';
    return '<div class="lw-ro-card" style="border-top-color:' + col + '" data-tip-name="' + esc(d.name) + '" data-tip-body="' + esc(d.question || d.description || '') + '" data-tip-formula="' + esc(d.calculation_formula || '') + '">' +
      '<div class="lw-ro-card-head"><span class="lw-ro-name">' + esc(d.name) + '</span>' + (flag ? '<span class="lw-ro-flag" style="color:' + flag.c + ';background:' + flag.b + '">' + flag.l + '</span>' : '') + '</div>' +
      '<div class="lw-ro-val" style="color:' + valColor + '">' + esc(val) + '</div>' +
      '<div class="lw-ro-foot"><span class="lw-ro-state" style="color:' + col + '"><span class="d" style="background:' + col + '"></span>' + esc(title(o.state)) + '</span>' + (sub ? '<span class="lw-ro-sub">' + sub + '</span>' : '') + '</div></div>';
  }

  /* ════ SENTIMENT ════ */
  function renderSentiment(c) {
    c.innerHTML =
      '<div class="lw-sec-head"><div class="lw-sec-title">Social Sentiment</div><span class="lw-mono" style="font-size:10px;letter-spacing:.06em;color:var(--lw-ink-3);text-transform:uppercase">most-mentioned · 24h</span></div>' +
      '<div class="lw-lead" id="lw-lead"><div class="lw-loading">Loading</div></div>' +
      '<div class="lw-mono" style="font-size:10px;color:var(--lw-ink-4);text-align:center;margin-top:9px">ApeWisdom attention + StockTwits sentiment</div>';
    api('/attention/leaderboard?limit=20').then(function (rows) {
      if (!rows || !rows.length) { $('#lw-lead').innerHTML = emptySentiment(); return; }
      _leaders = rows; drawLeaders();
    }).catch(function () { $('#lw-lead').innerHTML = emptySentiment(); });
  }
  var _leaders = [];
  function emptySentiment() { return '<div class="lw-empty" style="padding:36px 16px"><div class="lw-empty-mono">Awaiting attention data</div></div>'; }
  function drawLeaders() {
    var lead = $('#lw-lead');
    var html = '<div class="lw-lead-head"><span>Symbol</span><span>Mentions</span><span>Upvotes</span><span>Δ</span><span>Engage</span><span></span></div>';
    _leaders.forEach(function (l) {
      var hasSent = l.positive_ratio != null;
      var pos = hasSent ? Math.round(l.positive_ratio * 100) : 0;
      var has3 = hasSent && (l.neutral_ratio != null || l.negative_ratio != null);
      var neu, neg;
      if (has3) { neu = Math.round((l.neutral_ratio || 0) * 100); neg = Math.max(0, 100 - pos - neu); }
      else { neu = hasSent ? (100 - pos) : 0; neg = 0; }
      var d = l.mention_delta_pct;
      var deltaStr = d == null ? '—' : (d >= 0 ? '+' : '') + Math.round(d) + '%';
      var deltaCol = d == null ? 'var(--lw-ink-3)' : d >= 0 ? 'var(--lw-up)' : 'var(--lw-down)';
      var open = state.expanded === l.symbol;
      var trend = (l.trend || []).length >= 2 ? l.trend : [0, l.mentions || 1];
      var up = l.upvotes;
      var upStr = up == null ? '—' : fmtBig(up);
      var ur = l.upvote_ratio;
      var urStr = ur == null ? '—' : ur.toFixed(1) + '×';
      var urCol = ur == null ? 'var(--lw-ink-3)' : ur > 3 ? 'var(--lw-up)' : ur > 1 ? 'var(--lw-accent)' : 'var(--lw-ink-3)';
      var legend = '<span style="color:var(--lw-up)">●</span> ' + pos + '% <span style="color:var(--lw-ink-3)">●</span> ' + neu + '% <span style="color:var(--lw-down)">●</span> ' + neg + '%';
      var meanCol = l.mean_score == null ? 'var(--lw-ink-3)' : l.mean_score > 0 ? 'var(--lw-up)' : l.mean_score < 0 ? 'var(--lw-down)' : 'var(--lw-accent)';
      html += '<div class="lw-lead-item' + (open ? ' is-open' : '') + '" data-sym="' + esc(l.symbol) + '">' +
        '<div class="lw-lead-row">' +
          '<div class="lw-lead-id"><span class="lw-lead-badge">' + esc((l.symbol || '?')[0]) + '</span><div style="min-width:0"><div class="lw-lead-sym">' + esc(l.symbol) + '</div>' + (l.name ? '<div class="lw-sym-name" style="font-size:10px">' + esc(l.name) + '</div>' : '') + '</div></div>' +
          '<div class="lw-lead-mentions">' + fmtNum(l.mentions) + spark(trend, 52, 18, (d || 0) >= 0) + '</div>' +
          '<span class="lw-mono" style="font-size:12px;font-weight:700;color:var(--lw-ink)">' + upStr + '</span>' +
          '<span class="lw-mono" style="font-size:12px;font-weight:700;color:' + deltaCol + '">' + deltaStr + '</span>' +
          '<span class="lw-mono" style="font-size:11px;font-weight:700;color:' + urCol + '">' + urStr + '</span>' +
          '<span class="lw-caret">▾</span>' +
        '</div>' +
        '<div class="lw-lead-detail">' +
          '<div><div class="lw-detail-lbl">Mention trend · 30d</div>' + (ftChart(trend, null, (d || 0) >= 0, function (v) { return fmtBig(v); }) || '<div class="lw-c-dim" style="padding:16px 0">—</div>') + '</div>' +
          '<div style="display:flex;flex-direction:column;gap:11px">' +
            '<div style="display:flex;gap:20px"><div><div class="lw-detail-lbl">Sentiment split</div><div class="lw-mono" style="font-size:11px">' + legend + '</div></div></div>' +
            '<div><div class="lw-detail-lbl">Mean score</div><div class="lw-mono" style="font-size:15px;font-weight:700;color:' + meanCol + '">' + (l.mean_score != null ? l.mean_score.toFixed(3) : '—') + '</div></div>' +
            '<div style="display:flex;gap:20px"><div><div class="lw-detail-lbl">Messages</div><div class="lw-mono" style="font-size:13px;color:var(--lw-ink)">' + fmtNum(l.total_messages) + '</div></div>' + (l.cohort ? '<div><div class="lw-detail-lbl">Cohort</div><div class="lw-mono" style="font-size:13px;color:var(--lw-snap)">' + esc(l.cohort) + '</div></div>' : '') + '</div>' +
          '</div>' +
        '</div></div>';
    });
    lead.innerHTML = html;
    $$('.lw-lead-row', lead).forEach(function (row) { row.addEventListener('click', function () { var sym = row.parentNode.dataset.sym; state.expanded = state.expanded === sym ? null : sym; drawLeaders(); }); });
  }

  /* ════ INDICATORS ════ */
  var IND_DEFS = [
    { label: 'RSI', key: 'rsi', cat: 'Momentum', fmt: 'num1', gid: 'rsi' }, { label: 'SMA20', key: 'sma_20', cat: 'Trend', fmt: 'price', gid: 'sma' }, { label: 'SMA50', key: 'sma_50', cat: 'Trend', fmt: 'price', gid: 'sma' }, { label: 'SMA200', key: 'sma_200', cat: 'Trend', fmt: 'price', gid: 'sma' }, { label: 'EMA12', key: 'ema_12', cat: 'Trend', fmt: 'price', gid: 'ema' }, { label: 'EMA26', key: 'ema_26', cat: 'Trend', fmt: 'price', gid: 'ema' },
    { label: 'BB U', key: 'bb_upper', cat: 'Volatility', fmt: 'price', gid: 'bollinger' }, { label: 'BB M', key: 'bb_middle', cat: 'Volatility', fmt: 'price', gid: 'bollinger' }, { label: 'BB L', key: 'bb_lower', cat: 'Volatility', fmt: 'price', gid: 'bollinger' }, { label: 'ATR', key: 'atr', cat: 'Volatility', fmt: 'num2', gid: 'atr' }, { label: 'ATR%', key: 'atr_pct', cat: 'Volatility', fmt: 'pct', gid: 'atr_pct' },
    { label: 'VWAP', key: 'vwap', cat: 'Volume', fmt: 'price', gid: 'vwap' }, { label: 'MACD', key: 'macd', cat: 'Trend', fmt: 'num2', gid: 'macd' }, { label: 'MACDe', key: 'macd_ema', cat: 'Trend', fmt: 'num2', gid: 'macd' }, { label: 'MACh', key: 'macd_hist', cat: 'Trend', fmt: 'num2', gid: 'macd' }, { label: 'OBV', key: 'obv', cat: 'Volume', fmt: 'big', gid: 'obv' }, { label: 'RVol', key: 'rvol', cat: 'Volume', fmt: 'num2', gid: 'rvol' },
    { label: 'DolV', key: 'dollar_volume', cat: 'Volume', fmt: 'big', gid: 'dollar_volume' }, { label: 'aDol20', key: 'avg_dollar_volume_20', cat: 'Volume', fmt: 'big', gid: 'avg_dollar_volume' }, { label: 'R1d', key: 'return_1d', cat: 'Structure', fmt: 'pct', gid: 'return_1d' }, { label: 'R5d', key: 'return_5d', cat: 'Structure', fmt: 'pct', gid: 'return_5d' }, { label: 'R21d', key: 'return_21d', cat: 'Structure', fmt: 'pct', gid: 'return_21d' }, { label: 'R63d', key: 'return_63d', cat: 'Structure', fmt: 'pct', gid: 'return_63d' },
    { label: 'Gap%', key: 'gap_pct', cat: 'Structure', fmt: 'pct', gid: 'gap_pct' }, { label: '52wHi', key: 'pct_off_52w_high', cat: 'Structure', fmt: 'pct', gid: 'pct_off_52w_high' }, { label: '52wLo', key: 'pct_off_52w_low', cat: 'Structure', fmt: 'pct', gid: 'pct_off_52w_low' }, { label: 'RV21', key: 'realized_vol_21', cat: 'Volatility', fmt: 'pct', gid: 'realized_vol' }, { label: 'RV63', key: 'realized_vol_63', cat: 'Volatility', fmt: 'pct', gid: 'realized_vol' },
    { label: 'ADX', key: 'adx_14', cat: 'Trend', fmt: 'num2', gid: 'adx' }, { label: 'DI+', key: 'di_plus_14', cat: 'Trend', fmt: 'num2', gid: 'di_plus' }, { label: 'DI-', key: 'di_minus_14', cat: 'Trend', fmt: 'num2', gid: 'di_minus' }, { label: 'StochK', key: 'stoch_k_14', cat: 'Momentum', fmt: 'num1', gid: 'stoch_k' }, { label: 'Wm%R', key: 'williams_r_14', cat: 'Momentum', fmt: 'num1', gid: 'williams_r' }, { label: 'CCI', key: 'cci_20', cat: 'Momentum', fmt: 'num1', gid: 'cci' },
    { label: 'MFI', key: 'mfi_14', cat: 'Volume', fmt: 'num1', gid: 'mfi' }, { label: 'CMF', key: 'cmf_20', cat: 'Volume', fmt: 'num3', gid: 'cmf' }, { label: '%B', key: 'percent_b', cat: 'Volatility', fmt: 'num2', gid: 'percent_b' }, { label: 'Beta60', key: 'beta_60d', cat: 'Relative', fmt: 'num2', gid: 'beta' }, { label: 'RS20', key: 'rs_spy_20d', cat: 'Relative', fmt: 'pct', gid: 'rs_spy' }, { label: 'Corr', key: 'corr_spy', cat: 'Relative', fmt: 'num2', gid: 'corr_spy' },
    // ── Trend add-ons ──
    { label: 'ADL', key: 'ad_line', cat: 'Trend', fmt: 'big', gid: 'ad_line' }, { label: 'AronU', key: 'aroon_up_25', cat: 'Trend', fmt: 'num1', gid: 'aroon_up' }, { label: 'AronD', key: 'aroon_down_25', cat: 'Trend', fmt: 'num1', gid: 'aroon_down' }, { label: 'AronO', key: 'aroon_osc_25', cat: 'Trend', fmt: 'num1', gid: 'aroon_osc' },
    { label: 'KAMA', key: 'kama_10', cat: 'Trend', fmt: 'price', gid: 'kama' }, { label: 'WMA', key: 'wma_20', cat: 'Trend', fmt: 'price', gid: 'wma' },
    { label: 'LnSlp', key: 'linreg_slope_20', cat: 'Trend', fmt: 'num2', gid: 'linreg_slope' },
    { label: 'MS20', key: 'ma_slope_20', cat: 'Trend', fmt: 'num2', gid: 'ma_slope' }, { label: 'MS50', key: 'ma_slope_50', cat: 'Trend', fmt: 'num2', gid: 'ma_slope' }, { label: 'MS200', key: 'ma_slope_200', cat: 'Trend', fmt: 'num2', gid: 'ma_slope' },
    { label: 'MaStk', key: 'ma_stack', cat: 'Trend', fmt: 'num1', gid: 'ma_stack' },
    { label: 'DMA20', key: 'dist_to_ma_20', cat: 'Trend', fmt: 'pct', gid: 'dist_to_ma' }, { label: 'DMA50', key: 'dist_to_ma_50', cat: 'Trend', fmt: 'pct', gid: 'dist_to_ma' }, { label: 'DMA200', key: 'dist_to_ma_200', cat: 'Trend', fmt: 'pct', gid: 'dist_to_ma' },
    { label: 'TRIX', key: 'trix_15', cat: 'Trend', fmt: 'num2', gid: 'trix' }, { label: 'TSI', key: 'tsi_25_13', cat: 'Trend', fmt: 'num2', gid: 'tsi' },
    { label: 'DonU', key: 'donchian_upper', cat: 'Trend', fmt: 'price', gid: 'donchian_upper' }, { label: 'DonM', key: 'donchian_middle', cat: 'Trend', fmt: 'price', gid: 'donchian_middle' }, { label: 'DonL', key: 'donchian_lower', cat: 'Trend', fmt: 'price', gid: 'donchian_lower' },
    { label: 'KelU', key: 'keltner_upper', cat: 'Trend', fmt: 'price', gid: 'keltner_upper' }, { label: 'KelM', key: 'keltner_middle', cat: 'Trend', fmt: 'price', gid: 'keltner_mid' }, { label: 'KelL', key: 'keltner_lower', cat: 'Trend', fmt: 'price', gid: 'keltner_lower' },
    { label: 'LnU', key: 'linreg_channel_upper', cat: 'Trend', fmt: 'price', gid: 'linreg_channel' }, { label: 'LnM', key: 'linreg_channel_middle', cat: 'Trend', fmt: 'price', gid: 'linreg_channel' }, { label: 'LnL', key: 'linreg_channel_lower', cat: 'Trend', fmt: 'price', gid: 'linreg_channel' },
    // ── Momentum add-ons ──
    { label: 'RoC', key: 'roc_12', cat: 'Momentum', fmt: 'pct', gid: 'roc' }, { label: 'CMO', key: 'cmo_14', cat: 'Momentum', fmt: 'num1', gid: 'cmo' },
    { label: 'UO', key: 'ultimate_osc', cat: 'Momentum', fmt: 'num1', gid: 'ultimate_osc' }, { label: 'BoP', key: 'bop', cat: 'Momentum', fmt: 'num2', gid: 'bop' },
    { label: 'RSIdv', key: 'rsi_divergence', cat: 'Momentum', fmt: 'num1', gid: 'rsi_divergence' },
    { label: 'PPO', key: 'ppo', cat: 'Momentum', fmt: 'num2', gid: 'ppo' }, { label: 'PPOh', key: 'ppo_histogram', cat: 'Momentum', fmt: 'num2', gid: 'ppo_histogram' }, { label: 'PPOs', key: 'ppo_signal', cat: 'Momentum', fmt: 'num2', gid: 'ppo_signal' },
    { label: 'StoRSI', key: 'stoch_rsi_14', cat: 'Momentum', fmt: 'num1', gid: 'stoch_rsi' }, { label: 'StoD', key: 'stoch_d_3', cat: 'Momentum', fmt: 'num1', gid: 'stoch_d' },
    // ── Volatility add-ons ──
    { label: 'BBW', key: 'bandwidth', cat: 'Volatility', fmt: 'num4', gid: 'bandwidth' }, { label: 'BBsqz', key: 'bb_squeeze', cat: 'Volatility', fmt: 'bool', gid: 'bb_squeeze' },
    { label: 'StdDev', key: 'rolling_std_20', cat: 'Volatility', fmt: 'num2', gid: 'std_dev' }, { label: 'TR', key: 'true_range', cat: 'Volatility', fmt: 'num2', gid: 'true_range' },
    { label: 'RngEx', key: 'range_expansion', cat: 'Volatility', fmt: 'pct', gid: 'range_expansion' }, { label: 'CHOP', key: 'chop_14', cat: 'Volatility', fmt: 'num1', gid: 'chop' },
    // ── Volume add-ons ──
    { label: 'ChaikO', key: 'chaikin_osc', cat: 'Volume', fmt: 'big', gid: 'chaikin_osc' }, { label: 'EoM', key: 'eom_14', cat: 'Volume', fmt: 'num3', gid: 'eom' },
    { label: 'FI13', key: 'force_index_13', cat: 'Volume', fmt: 'big', gid: 'force_index' }, { label: 'OBVSlp', key: 'obv_slope_20', cat: 'Volume', fmt: 'big', gid: 'obv_slope' }, { label: 'VPT', key: 'vpt', cat: 'Volume', fmt: 'big', gid: 'vpt' },
    // ── Structure add-ons ──
    { label: 'Inside', key: 'inside_bar', cat: 'Structure', fmt: 'bool', gid: 'inside_bar' }, { label: 'Outsid', key: 'outside_bar', cat: 'Structure', fmt: 'bool', gid: 'outside_bar' },
    { label: 'GapFil', key: 'gap_fill', cat: 'Structure', fmt: 'bool', gid: 'gap_fill' }, { label: 'VolSpk', key: 'volume_spike', cat: 'Structure', fmt: 'bool', gid: 'volume_spike' },
    { label: 'LogR', key: 'log_return', cat: 'Structure', fmt: 'pct', gid: 'log_return' },
    { label: 'A20', key: 'above_ma_20', cat: 'Structure', fmt: 'bool', gid: 'above_ma' }, { label: 'A50', key: 'above_ma_50', cat: 'Structure', fmt: 'bool', gid: 'above_ma' }, { label: 'A200', key: 'above_ma_200', cat: 'Structure', fmt: 'bool', gid: 'above_ma' },
    { label: '52wH', key: 'is_new_52w_high', cat: 'Structure', fmt: 'bool', gid: 'is_new_52w_high' }, { label: '52wL', key: 'is_new_52w_low', cat: 'Structure', fmt: 'bool', gid: 'is_new_52w_low' },
    { label: 'R126', key: 'return_126', cat: 'Structure', fmt: 'pct', gid: 'return_126' },
    // ── Relative add-ons ──
    { label: 'Alpha', key: 'alpha', cat: 'Relative', fmt: 'num4', gid: 'alpha' }, { label: 'B20', key: 'beta_20d', cat: 'Relative', fmt: 'num2', gid: 'beta_20d' }, { label: 'RS60', key: 'rs_spy_60d', cat: 'Relative', fmt: 'pct', gid: 'rs_spy' }
  ];
  var pins = getJSON('lw_pins', {});
  function getPins(sym) { return pins[sym] || []; }
  function setPins(sym, arr) { pins[sym] = arr; setLS('lw_pins', JSON.stringify(pins)); }
  var _glossary = null, _glossaryReq = null;
  function fetchGlossary() { if (_glossary) return Promise.resolve(_glossary); if (!_glossaryReq) _glossaryReq = api('/indicators/glossary').then(function (g) { _glossary = g || {}; return _glossary; }).catch(function () { _glossary = {}; return _glossary; }); return _glossaryReq; }

  var _indCache = null;
  function renderIndicators(c) {
    c.innerHTML =
      '<div class="lw-sec-head"><div class="lw-sec-title">Indicators</div><div class="lw-sort"><span class="lw-sort-lbl">Order</span><span id="lw-ind-sort"></span></div></div>' +
      '<div class="lw-ro-syms" id="lw-ind-syms"><span class="lw-empty-mono">loading symbols…</span></div>' +
      '<div id="lw-ind-body"></div>';
    sortButtons('lw-ind-sort', [['category', 'By category'], ['name', 'Name']], state.indSort, function (v) { state.indSort = v; loadIndBody(); });
    var doSyms = function (list) {
      state.indSymbols = list;
      if (!list.length) { $('#lw-ind-syms').innerHTML = '<span class="lw-empty-mono">no symbols in lake</span>'; $('#lw-ind-body').innerHTML = '<div class="lw-empty">Ingest bars to compute indicators.</div>'; return; }
      if (!state.indSymbol || !list.some(function (x) { return (x.symbol || x.security_id) === state.indSymbol; })) state.indSymbol = list[0].symbol || list[0].security_id;
      drawIndSyms(list); loadIndBody();
    };
    if (state.indSymbols) doSyms(state.indSymbols);
    else api('/bars/symbols').then(function (l) { doSyms(l || []); }).catch(function () { $('#lw-ind-syms').innerHTML = '<span class="lw-empty-mono">could not load symbols</span>'; });
  }
  function drawIndSyms(list) {
    var box = $('#lw-ind-syms'); box.innerHTML = '';
    list.forEach(function (it) {
      var sym = it.symbol || it.security_id;
      var b = document.createElement('button'); b.className = 'lw-ro-sym' + (sym === state.indSymbol ? ' is-active' : ''); b.innerHTML = esc(sym);
      b.addEventListener('click', function () { state.indSymbol = sym; drawIndSyms(list); loadIndBody(); }); box.appendChild(b);
    });
  }
  function loadIndBody() {
    var body = $('#lw-ind-body'); if (!body) return;
    var sym = state.indSymbol;
    if (_indCache && _indCache[sym]) { drawIndBody(body, _indCache[sym]); return; }
    body.innerHTML = '<div class="lw-loading">Loading indicators</div>';
    barApi('/bars/summary', sym).then(function (s) { s._sym = sym; _indCache = _indCache || {}; _indCache[sym] = s; drawIndBody(body, s); })
      .catch(function () { body.innerHTML = '<div class="lw-empty"><div class="lw-empty-mono">No indicators for ' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);margin-top:6px">Needs daily bars in the lake to compute.</div></div>'; });
  }
  var IND_CAT_ORDER = [['Trend', 'Trend'], ['Momentum', 'Momentum'], ['Volatility', 'Volatility'], ['Volume', 'Volume'], ['Structure', 'Structure'], ['Relative', 'Relative']];
  function drawIndBody(body, s) {
    var sb = state.indSymbols ? state.indSymbols.filter(function (x) { return (x.symbol || x.security_id) === state.indSymbol; })[0] : null;
    var name = (sb && sb.name) || s.name || '';
    var up = (s.change_pct || 0) >= 0;
    var avail = IND_DEFS.filter(function (d) { return s[d.key] != null; }).length;
    var head = '<div class="lw-ro-symhead"><span class="t">' + esc(state.indSymbol) + '</span><span class="n">' + esc(name) + '</span>' +
      '<span class="m"><span style="font-weight:700;color:var(--lw-ink)">' + fmtMoney(s.last) + '</span> <span style="color:' + (up ? 'var(--lw-up)' : 'var(--lw-down)') + '">' + (up ? '+' : '') + (s.change_pct || 0).toFixed(2) + '%</span> · ' + avail + ' indicators · as of ' + (state.asOf ? esc(String(s.latest_date || '').slice(0, 10)) : 'now') + '</span></div>';
    var html = head;
    var pin = getPins(state.indSymbol);
    var byPin = function (arr) { return arr.slice().sort(function (a, b) { return (pin.indexOf(b.label) > -1) - (pin.indexOf(a.label) > -1); }); };
    if (state.indSort === 'name') {
      html += indGroup('All · A–Z', byPin(IND_DEFS.slice().sort(function (a, b) { return a.label < b.label ? -1 : 1; })), s);
    } else {
      IND_CAT_ORDER.forEach(function (cat) { var items = IND_DEFS.filter(function (d) { return d.cat === cat[0]; }); if (items.length) html += indGroup(cat[1], byPin(items), s); });
    }
    body.innerHTML = html;
    $$('.ind-tilecard', body).forEach(function (card) {
      card.addEventListener('mouseenter', function (e) { var gid = card.dataset.gid; fetchGlossary().then(function (g) { var en = g[gid]; if (!en) return; showTip(e, en.full_name || en.name || gid, en.description || '', en.formula || ''); }); });
      card.addEventListener('mouseleave', hideTip);
    });
    $$('.ind-pin', body).forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation(); hideTip();
        var sym = btn.getAttribute('data-sym'), label = btn.getAttribute('data-pin');
        var arr = getPins(sym); var i = arr.indexOf(label); if (i < 0) arr.push(label); else arr.splice(i, 1); setPins(sym, arr); loadIndBody();
      });
    });
  }
  function indGroup(label, items, s) {
    var html = '<div class="lw-ro-group"><div class="lw-ro-grouphead"><span class="c">' + esc(label) + '</span><span class="rule"></span><span class="ct">' + items.length + '</span></div><div class="lw-ro-grid">';
    items.forEach(function (d) { html += indCard(s, d); });
    return html + '</div></div>';
  }
  function indCard(s, d) {
    var raw = s[d.key], has = raw != null;
    var col = 'var(--lw-ink-4)';
    if (d.key === 'rsi' && has) col = raw > 70 ? 'var(--lw-down)' : raw < 30 ? 'var(--lw-up)' : 'var(--lw-snap)';
    else if (d.fmt === 'pct' && has) col = raw >= 0 ? 'var(--lw-up)' : 'var(--lw-down)';
    else if (has) col = 'var(--lw-snap)';
    var valColor = ((d.key === 'rsi' || d.fmt === 'pct') && has) ? col : 'var(--lw-ink)';
    var isP = getPins(s._sym).indexOf(d.label) !== -1;
    return '<div class="lw-ro-card ind-tilecard" style="border-top-color:' + col + '" data-sym="' + esc(s._sym) + '" data-gid="' + esc(d.gid) + '">' +
      '<div class="lw-ro-card-head"><span class="lw-ro-name">' + esc(d.label) + '</span>' +
        '<button class="ind-pin' + (isP ? ' on' : '') + '" data-sym="' + esc(s._sym) + '" data-pin="' + esc(d.label) + '" title="Pin indicator">' + (isP ? '★' : '☆') + '</button></div>' +
      '<div class="lw-ro-val" style="color:' + valColor + '">' + fmtInd(raw, d.fmt) + '</div>' +
      '<div class="lw-ro-foot"><span class="lw-ro-state" style="color:var(--lw-ink-3)"><span class="d" style="background:' + col + '"></span>' + esc(d.cat) + '</span></div></div>';
  }
  function fmtInd(v, t) { if (v == null) return '—'; if (t === 'bool') return v ? 'yes' : 'no'; if (t === 'pct') return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'; if (t === 'price') return fmtMoney(v); if (t === 'big') return fmtBig(v); if (t === 'num1') return Number(v).toFixed(1); if (t === 'num2') return Number(v).toFixed(2); if (t === 'num3') return Number(v).toFixed(3); return Number(v).toFixed(1); }

  /* ════ FUNDAMENTALS ════ */
  var FUND_CATS = [['Overview', 'Overview'], ['Valuation', 'Valuation'], ['Profitability', 'Profitability'], ['Growth', 'Growth'], ['Financial Health', 'Financial Health'], ['Cash Flow', 'Cash Flow'], ['Scale', 'Scale'], ['Estimates', 'Estimates']];
  var _fundPins = getJSON('lw_fund_pins', {});
  function getFundPins(sym) { return _fundPins[sym] || []; }
  function setFundPins(sym, arr) { _fundPins[sym] = arr; setLS('lw_fund_pins', JSON.stringify(_fundPins)); }
  var _fundGlossary = null, _fundGlossaryReq = null, _fundOverviewIds = [];
  function fetchFundGlossary() { if (_fundGlossary) return Promise.resolve(_fundGlossary); if (!_fundGlossaryReq) _fundGlossaryReq = api('/fundamentals/glossary').then(function (r) { var entries = (r && r.entries) || []; _fundGlossary = {}; entries.forEach(function (e) { _fundGlossary[e.metric_id] = e; }); _fundOverviewIds = (r && r.overview_ids) || []; return _fundGlossary; }).catch(function () { _fundGlossary = {}; return _fundGlossary; }); return _fundGlossaryReq; }
  var _fundCache = null;
  function renderFundamentals(c) {
    c.innerHTML =
      '<div class="lw-sec-head"><div class="lw-sec-title">Fundamentals</div>' +
        '<div style="display:flex;align-items:center;gap:10px"><label class="lw-mono" style="font-size:10px;color:var(--lw-ink-3);display:flex;align-items:center;gap:5px;cursor:pointer">' +
          '<input type="checkbox" id="lw-fund-latest"' + (state.fundLatest ? ' checked' : '') + '> Latest</label>' +
        '<div class="lw-sort"><span class="lw-sort-lbl">Order</span><span id="lw-fund-sort"></span></div></div></div>' +
      '<div class="lw-ro-syms" id="lw-fund-syms"><span class="lw-empty-mono">loading symbols…</span></div>' +
      '<div id="lw-fund-body"></div>';
    sortButtons('lw-fund-sort', [['category', 'By category'], ['name', 'Name']], state.fundSort, function (v) { state.fundSort = v; loadFundBody(); });
    $('#lw-fund-latest').addEventListener('change', function (e) { state.fundLatest = e.target.checked; loadFundBody(); });
    var doSyms = function (list) {
      state.fundSymbols = list;
      if (!list.length) { $('#lw-fund-syms').innerHTML = '<span class="lw-empty-mono">no symbols in lake</span>'; $('#lw-fund-body').innerHTML = '<div class="lw-empty">Ingest bars and fundamentals to compute metrics.</div>'; return; }
      if (!state.fundSymbol || !list.some(function (x) { return (x.symbol || x.security_id) === state.fundSymbol; })) state.fundSymbol = list[0].symbol || list[0].security_id;
      drawFundSyms(list); loadFundBody();
    };
    if (state.fundSymbols) doSyms(state.fundSymbols);
    else api('/bars/symbols').then(function (l) { doSyms(l || []); }).catch(function () { $('#lw-fund-syms').innerHTML = '<span class="lw-empty-mono">could not load symbols</span>'; });
  }
  function drawFundSyms(list) {
    var box = $('#lw-fund-syms'); box.innerHTML = '';
    list.forEach(function (it) {
      var sym = it.symbol || it.security_id;
      var b = document.createElement('button'); b.className = 'lw-ro-sym' + (sym === state.fundSymbol ? ' is-active' : ''); b.innerHTML = esc(sym);
      b.addEventListener('click', function () { state.fundSymbol = sym; drawFundSyms(list); loadFundBody(); }); box.appendChild(b);
    });
  }
  function loadFundBody() {
    var body = $('#lw-fund-body'); if (!body) return;
    var sym = state.fundSymbol, cacheKey = sym + '_' + state.fundLatest;
    if (_fundCache && _fundCache[cacheKey]) { drawFundBody(body, _fundCache[cacheKey]); return; }
    body.innerHTML = '<div class="lw-loading">Loading fundamentals</div>';
    var extra = state.fundLatest ? { latest: 'true' } : {};
    barApi('/symbol/' + encodeURIComponent(sym) + '/fundamentals', null, extra).then(function (res) {
      _fundCache = _fundCache || {}; _fundCache[cacheKey] = res; drawFundBody(body, res);
    }).catch(function () {
      body.innerHTML = '<div class="lw-empty"><div class="lw-empty-mono">No fundamentals for ' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);margin-top:6px">Needs canonical fundamentals data in the lake.</div></div>';
    });
  }
  function drawFundBody(body, res) {
    var metrics = (res && res.metrics) || [];
    var meta = (res && res.metadata) || {};
    var sb = state.fundSymbols ? state.fundSymbols.filter(function (x) { return (x.symbol || x.security_id) === state.fundSymbol; })[0] : null;
    var name = sb ? (sb.name || '') : '';
    var isLatest = meta.latest;
    var head = '<div class="lw-ro-symhead"><span class="t">' + esc(state.fundSymbol) + '</span><span class="n">' + esc(name) + '</span>' +
      (isLatest ? '<span class="lw-stale-badge" style="background:var(--lw-accent);font-size:8px">LATEST</span>' : '') +
      '<span class="m">' + metrics.length + ' metrics · as of ' + (state.asOf ? esc(String(res.as_of || state.asOf).slice(0, 10)) : String(res.as_of || '').slice(0,10) || 'now') + '</span></div>';
    if (!metrics.length) { body.innerHTML = head + '<div class="lw-empty"><div class="lw-empty-mono">No fundamental metrics available</div></div>'; return; }
    var html = head;
    var pin = getFundPins(state.fundSymbol);
    var byPin = function (arr) { return arr.slice().sort(function (a, b) { return (pin.indexOf(a.metric_id) > -1) - (pin.indexOf(b.metric_id) > -1); }); };
    if (state.fundSort === 'name') {
      var sorted = metrics.slice().sort(function (a, b) { return (a.name || a.metric_id) < (b.name || b.metric_id) ? -1 : 1; });
      html += fundGroup('All · A-Z', byPin(sorted));
    } else {
      var overviewItems = metrics.filter(function (m) { return _fundOverviewIds.indexOf(m.metric_id) !== -1; });
      if (overviewItems.length) html += fundGroup('Overview', byPin(overviewItems));
      FUND_CATS.forEach(function (cat) {
        if (cat[0] === 'Overview') return;
        var items = metrics.filter(function (m) { return m.category === cat[0]; });
        if (items.length) html += fundGroup(cat[1], byPin(items));
      });
      var known = FUND_CATS.map(function (x) { return x[0]; });
      var extra = {};
      metrics.forEach(function (m) { var c = m.category; if (known.indexOf(c) < 0) (extra[c] = extra[c] || []).push(m); });
      Object.keys(extra).forEach(function (c) { html += fundGroup(title(c), byPin(extra[c])); });
    }
    body.innerHTML = html;
    bindTips(body);
    $$('.ind-pin', body).forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation(); hideTip();
        var sym = btn.getAttribute('data-sym'), mid = btn.getAttribute('data-pin');
        var arr = getFundPins(sym); var i = arr.indexOf(mid); if (i < 0) arr.push(mid); else arr.splice(i, 1); setFundPins(sym, arr); loadFundBody();
      });
    });
  }
  function fundGroup(label, items) {
    var html = '<div class="lw-ro-group"><div class="lw-ro-grouphead"><span class="c">' + esc(label) + '</span><span class="rule"></span><span class="ct">' + items.length + '</span></div><div class="lw-ro-grid">';
    items.forEach(function (m) { html += fundCard(m); });
    return html + '</div></div>';
  }
  function fundCard(m) {
    var isUnavail = m.quality_status === 'unavailable' || m.quality_status === 'not_meaningful' || m.value == null;
    var col = isUnavail ? 'var(--lw-ink-4)' : m.tone === 'green' ? 'var(--lw-up)' : m.tone === 'red' ? 'var(--lw-down)' : m.tone === 'amber' ? 'var(--lw-accent)' : 'var(--lw-snap)';
    var borderCol = isUnavail ? 'var(--lw-rule-2)' : col;
    var valTxt = m.display_value || (m.value != null ? String(m.value) : '—');
    var valColor = isUnavail ? 'var(--lw-ink-3)' : col;
    var stateTxt = m.label || title(m.threshold_state || 'available');
    var isP = getFundPins(state.fundSymbol).indexOf(m.metric_id) !== -1;
    var g = _fundGlossary && _fundGlossary[m.metric_id];
    var tipBody = '';
    if (g) {
      if (g.what_it_answers) tipBody += esc(g.what_it_answers);
      if (g.formula) tipBody += '<br><br><b>Formula:</b> <code>' + esc(g.formula) + '</code>';
      if (g.inputs && g.inputs.length) tipBody += '<br><b>Inputs:</b> ' + esc(g.inputs.join(', '));
      if (g.basis) tipBody += '<br><b>Basis:</b> ' + esc(g.basis);
      if (m.unavailable_reason) tipBody += '<br><br><b>' + esc(m.unavailable_reason.replace(/_/g, ' ')) + '</b>';
    } else {
      if (m.unavailable_reason) tipBody = esc(m.unavailable_reason.replace(/_/g, ' '));
    }
    var tipFormula = g ? (g.formula || '') : '';
    return '<div class="lw-ro-card" style="border-top-color:' + borderCol + '" data-tip-name="' + esc(m.name) + '" data-tip-body="' + tipBody + '" data-tip-formula="' + esc(tipFormula) + '">' +
      '<div class="lw-ro-card-head"><span class="lw-ro-name">' + esc(m.name) + '</span>' +
        '<button class="ind-pin' + (isP ? ' on' : '') + '" data-sym="' + esc(state.fundSymbol) + '" data-pin="' + esc(m.metric_id) + '" title="Pin metric">' + (isP ? '★' : '☆') + '</button></div>' +
      '<div class="lw-ro-val" style="color:' + valColor + '">' + esc(valTxt) + '</div>' +
      '<div class="lw-ro-foot"><span class="lw-ro-state" style="color:' + col + '"><span class="d" style="background:' + col + '"></span>' + esc(stateTxt) + '</span>' +
        (m.period_kind ? '<span class="lw-ro-sub">' + esc(m.period_kind.toUpperCase()) + '</span>' : '') +
        (m.quality_status !== 'valid' && m.quality_status !== 'available' ? '<span class="lw-ro-flag" style="color:var(--lw-down);background:var(--lw-down-soft)">' + esc(m.quality_status.replace(/_/g, ' ')) + '</span>' : '') +
      '</div></div>';
  }

  /* ════ PIT ════ */
  function renderPit(c) {
    var live = !state.asOf;
    var asTxt = live ? 'now (live)' : new Date(state.asOf).toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
    var presets = [['Today', isoDaysAgo(1, 20)], ['1 week ago', isoDaysAgo(7, 20)], ['1 month ago', isoDaysAgo(30, 20)], ['Quarter ago', isoDaysAgo(91, 20)]];
    c.innerHTML =
      '<div class="lw-pit-card"><div class="lw-pit-title">Point-in-Time Playground</div>' +
        '<p class="lw-pit-p">Rewind <strong style="color:var(--lw-ink)">knowledge-time</strong> via the <strong style="color:var(--lw-claret)">AS OF</strong> control in the masthead to see exactly what the lake knew at any instant. Every read is bounded — no lookahead, ever.</p>' +
        '<div class="lw-pit-strip"><div class="lw-pit-line"></div><div class="lw-pit-fill" style="width:' + (live ? '100%' : '62%') + '"></div>' + (live ? '' : '<div class="lw-pit-dot" style="left:62%"></div>') + '<div class="lw-pit-now"></div></div>' +
        '<div class="lw-pit-labels"><span>past</span><span>reading as of: ' + esc(asTxt) + '</span><span>live</span></div>' +
        '<div class="lw-pit-presets" id="lw-pit-presets"></div></div>' +
      '<div class="lw-pit-card"><div class="lw-block-label" style="margin-bottom:12px">Tri-temporal guarantee</div><div class="lw-tt-grid">' +
        ttCard('Valid time', 'When a fact was true in the market — the trading day it describes.', 'var(--lw-snap)') +
        ttCard('Knowledge time', 'When the lake first knew it — bounded by your AS OF instant.', 'var(--lw-claret)') +
        ttCard('System time', 'When the row was physically written — full audit lineage.', 'var(--lw-up)') +
      '</div></div>';
    var pp = $('#lw-pit-presets');
    presets.forEach(function (p) { var b = document.createElement('button'); b.textContent = p[0]; b.addEventListener('click', function () { setAsOf(p[1]); }); pp.appendChild(b); });
    var lb = document.createElement('button'); lb.className = 'is-live'; lb.innerHTML = '⟲ Live'; lb.addEventListener('click', function () { setAsOf(null); }); pp.appendChild(lb);
  }
  function ttCard(t, d, col) { return '<div class="lw-tt-card" style="border-top-color:' + col + '"><div class="t" style="color:' + col + '">' + t + '</div><div class="d">' + d + '</div></div>'; }
  function isoDaysAgo(days, hour) { var d = new Date(); d.setUTCDate(d.getUTCDate() - days); d.setUTCHours(hour, 0, 0, 0); return d.toISOString().slice(0, 19); }

  /* ════ shared sort buttons ════ */
  function sortButtons(containerId, opts, current, onPick) {
    var box = document.getElementById(containerId); if (!box) return;
    box.innerHTML = ''; box.style.display = 'inline-flex'; box.style.gap = '5px';
    opts.forEach(function (o) {
      var b = document.createElement('button'); b.className = 'lw-sort-btn' + (o[0] === current ? ' is-active' : ''); b.textContent = o[1];
      b.addEventListener('click', function () { onPick(o[0]); }); box.appendChild(b);
    });
  }

  /* ════ AS OF control ════ */
  function setAsOf(v) { state.asOf = v; if (v) state.snapshotId = ''; closeAsof(); renderAsof(); showTab(state.tab); }
  function setSnapshot(id) { state.snapshotId = id; state.asOf = null; closeAsof(); renderAsof(); showTab(state.tab); }
  function closeAsof() { state.asofOpen = false; var p = $('#lw-asof-pop'); if (p) p.classList.remove('is-open'); var b = $('#lw-asof-btn'); if (b) b.setAttribute('aria-expanded', 'false'); }
  function renderAsof() {
    var live = !state.asOf && !state.snapshotId;
    $('#lw-asof-dot').className = 'lw-asof-dot' + (live ? '' : ' is-pit');
    $('#lw-asof-kicker').textContent = live ? 'Live' : (state.snapshotId ? 'Snapshot' : 'As of');
    $('#lw-asof-val').textContent = live ? 'Live' : (state.snapshotId ? shortSnap(state.snapshotId) : new Date(state.asOf).toISOString().slice(0, 16).replace('T', ' '));
    $('#lw-asof-hint').textContent = live ? 'reading live data' : 'point-in-time read';
    // presets
    var presets = [['Live', null], ['Today close', isoDaysAgo(1, 20)], ['Yesterday', isoDaysAgo(2, 20)], ['1 week ago', isoDaysAgo(7, 20)], ['1 month ago', isoDaysAgo(30, 20)], ['Quarter ago', isoDaysAgo(91, 20)]];
    var pe = $('#lw-asof-presets'); pe.innerHTML = '';
    presets.forEach(function (p) {
      var active = (p[1] === state.asOf) || (p[1] === null && live);
      var b = document.createElement('button'); if (active) b.className = 'is-active'; b.textContent = p[0];
      b.addEventListener('click', function () { setAsOf(p[1]); }); pe.appendChild(b);
    });
    var inp = $('#lw-asof-input'); inp.value = state.asOf ? String(state.asOf).slice(0, 19) : '';
  }
  function shortSnap(id) { return String(id).length > 16 ? String(id).slice(0, 15) + '…' : String(id); }
  function loadSnapshots() {
    api('/snapshots').then(function (snaps) {
      snaps = snaps || []; var box = $('#lw-asof-snaps'), lbl = $('#lw-snap-label');
      if (!snaps.length) { box.innerHTML = ''; lbl.style.display = 'none'; return; }
      lbl.style.display = 'block'; box.innerHTML = '';
      snaps.slice(0, 12).forEach(function (s) {
        var id = s.snapshot_id || s.id || s; var when = s.created_at || s.snapshot_at || '';
        var b = document.createElement('button'); if (id === state.snapshotId) b.className = 'is-active';
        b.innerHTML = esc(shortSnap(id)) + (when ? ' <span style="color:var(--lw-ink-4)">· ' + esc(String(when).slice(0, 10)) + '</span>' : '');
        b.addEventListener('click', function () { setSnapshot(id); }); box.appendChild(b);
      });
    }).catch(function () { });
  }

  /* ════ clock ════ */
  function tickClock() {
    var d = new Date(nowMs());
    var line = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase() + ' · ' + d.toISOString().slice(11, 16) + ' UTC';
    var el = $('#lw-header-time'); if (el) el.textContent = line;
  }

  /* ════ init ════ */
  function init() {
    applyTheme(theme);
    $('#lw-theme-btn').addEventListener('click', function () { applyTheme(theme === 'light' ? 'dark' : 'light'); });
    $$('.lw-nav-tab').forEach(function (t) { t.addEventListener('click', function () { showTab(t.dataset.tab); }); });
    var ab = $('#lw-asof-btn');
    ab.addEventListener('click', function (e) { e.stopPropagation(); state.asofOpen = !state.asofOpen; $('#lw-asof-pop').classList.toggle('is-open', state.asofOpen); ab.setAttribute('aria-expanded', state.asofOpen ? 'true' : 'false'); });
    $('#lw-asof-pop').addEventListener('click', function (e) { e.stopPropagation(); });
    document.addEventListener('click', function () { if (state.asofOpen) closeAsof(); });
    $('#lw-asof-input').addEventListener('change', function (e) { if (e.target.value) setAsOf(e.target.value); });
    $('#lw-golive').addEventListener('click', function () { setAsOf(null); });
    renderAsof(); loadSnapshots(); tickClock();
    setInterval(function () { if (!state.asOf) tickClock(); }, 30000);
    showTab('overview');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
