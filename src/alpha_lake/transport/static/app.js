/* Lake Watch — warm-tone newsroom-style dashboard.
   Data-reflecting visuals: symbol cards, sentiment leaderboard, catalog, PIT.
   Every fetch degrades gracefully — missing/empty endpoints render empty or
   loading states instead of breaking. */
(function () {
  'use strict';

  var API = '/v1/dashboard';
  var WATCHLIST = ['SPY', 'NVDA'];
  var state = { asOf: null, snapshotId: '', priceMode: 'raw', tab: 'overview', symbol: '', dataset: '', expanded: null };

  /* ── Theme ── */
  var themePref = (function () { try { return localStorage.getItem('lw_theme') || 'dark'; } catch (e) { return 'dark'; } })();
  function applyTheme(pref) { document.documentElement.dataset.theme = pref; themePref = pref; try { localStorage.setItem('lw_theme', pref); } catch (e) {} $$('.lw-theme-btn').forEach(function (b) { b.classList.toggle('is-active', b.dataset.theme === pref); }); }
  applyTheme(themePref);

  /* ── Fetch helpers (graceful: reject → caught by callers) ── */
  function api(path) {
    var url = new URL(API + path, location.origin);
    if (state.asOf) url.searchParams.set('as_of', state.asOf);
    if (state.snapshotId) url.searchParams.set('snapshot_id', state.snapshotId);
    return fetch(url).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }
  function barApi(path, sym, start, end) {
    var url = new URL(API + path, location.origin);
    if (state.asOf) url.searchParams.set('as_of', state.asOf);
    if (state.snapshotId) url.searchParams.set('snapshot_id', state.snapshotId);
    url.searchParams.set('symbol', sym);
    if (start) url.searchParams.set('start', start);
    if (end) url.searchParams.set('end', end);
    if (state.priceMode && state.priceMode !== 'raw') url.searchParams.set('price_mode', state.priceMode);
    return fetch(url).then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmtNum(n) { if (n == null) return '—'; return Number(n).toLocaleString(); }
  function fmtRows(x) { if (x == null) return '—'; x = +x; return x >= 1e6 ? (x / 1e6).toFixed(2) + 'M' : x >= 1e3 ? (x / 1e3).toFixed(1) + 'K' : String(x); }
  function fmtMoney(n, d) { return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d }); }
  function ago(iso) { if (!iso || iso === '—') return '—'; var d = new Date(iso); var s = Math.floor((Date.now() - d) / 1000); if (s < 60) return s + 's'; if (s < 3600) return Math.floor(s / 60) + 'm'; if (s < 86400) return Math.floor(s / 3600) + 'h'; return Math.floor(s / 86400) + 'd'; }
  function lastVal(arr) { if (!arr) return null; for (var i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i]; return null; }
  function avg(arr) { var s = 0, n = 0; for (var i = 0; i < arr.length; i++) if (arr[i] != null) { s += arr[i]; n++; } return n ? s / n : null; }

  /* ── SVG builders ── */
  function sparkline(data, w, h, stroke) {
    if (!data || data.length < 2) return '';
    var mn = Math.min.apply(null, data), mx = Math.max.apply(null, data), rng = (mx - mn) || 1;
    var pts = data.map(function (v, i) { return (i / (data.length - 1) * w).toFixed(1) + ',' + (h - 2 - ((v - mn) / rng) * (h - 4)).toFixed(1); }).join(' ');
    var col = stroke || (data[data.length - 1] >= data[0] ? 'var(--lw-money)' : 'var(--lw-down)');
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="overflow:visible"><polyline points="' + pts + '" fill="none" stroke="' + col + '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }
  function areaChart(closes, up) {
    var w = 320, h = 92, pad = 6;
    if (!closes || closes.length < 2) return '';
    var mn = Math.min.apply(null, closes), mx = Math.max.apply(null, closes), rng = (mx - mn) || 1;
    var X = function (i) { return (i / (closes.length - 1) * w); };
    var Y = function (v) { return (h - pad - ((v - mn) / rng) * (h - 2 * pad)); };
    var line = closes.map(function (v, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1); }).join(' ');
    var area = line + ' L' + w + ',' + h + ' L0,' + h + ' Z';
    var stroke = up ? 'var(--lw-money)' : 'var(--lw-down)';
    var fill = up ? 'rgba(127,198,154,0.13)' : 'rgba(229,131,115,0.13)';
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" style="height:88px;overflow:visible">' +
      '<path d="' + area + '" fill="' + fill + '" stroke="none"/>' +
      '<path d="' + line + '" fill="none" stroke="' + stroke + '" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>';
  }
  function volBars(vols) {
    var w = 320, h = 26;
    if (!vols || !vols.length) return '';
    var slice = vols.slice(-40), mx = Math.max.apply(null, slice) || 1, gap = w / slice.length, bw = gap * 0.62;
    var rects = slice.map(function (v, i) { var bh = (v / mx) * h; return '<rect x="' + (i * gap).toFixed(1) + '" y="' + (h - bh).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + bh.toFixed(1) + '" fill="var(--lw-rule-2)"/>'; }).join('');
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" style="height:24px;margin-top:3px">' + rects + '</svg>';
  }

  /* ── Tab routing ── */
  function showTab(name) {
    state.tab = name;
    $$('.lw-tab').forEach(function (t) { t.classList.toggle('is-active', t.dataset.tab === name); });
    var content = $('#lw-content');
    content.innerHTML = '<div class="lw-loading">Loading</div>';
    switch (name) {
      case 'overview': renderOverview(content); break;
      case 'bars': renderBars(content); break;
      case 'sentiment': renderSentiment(content); break;
      case 'datasets': renderCatalog(content); break;
      case 'securities': renderSecurities(content); break;
      case 'pit': renderPit(content); break;
    }
  }

  /* ── Status classification (shared) ── */
  function tierMeta(tier) {
    if (tier === 'core') return { cls: 'lw-pill-core' };
    if (tier === 'convenience') return { cls: 'lw-pill-convenience' };
    return { cls: 'lw-pill-experimental' };
  }
  function statusMeta(ds) {
    var rows = ds.rows || 0;
    if (rows === 0) return ds.supported ? { dot: 'amber', color: 'lw-c-accent', label: 'ingesting', state: 'loading' }
      : { dot: 'red', color: 'lw-c-down', label: 'empty', state: 'empty' };
    var age = ds.latest_effective_date ? (Date.now() - new Date(ds.latest_effective_date)) / 86400000 : 999;
    if (age <= 3) return { dot: 'green', color: 'lw-c-up', label: 'fresh', state: 'ok' };
    return { dot: 'amber', color: 'lw-c-accent', label: 'stale', state: 'ok' };
  }

  /* friendly category labels for the overview */
  var CATEGORY_LABELS = {
    lake_bars: 'OHLCV bars', technical_indicators: 'Indicators', attention_metrics: 'Attention',
    sentiment_annotations: 'Sentiment', news_articles: 'News', social_posts: 'Social posts',
    insider_tx: 'Insider tx', earnings_calendar: 'Earnings', macro_series: 'Macro series',
    fundamentals: 'Fundamentals', corp_actions: 'Corp actions', congress_trades: 'Congress',
    economic_calendar: 'Econ calendar', relative_strength: 'Rel. strength', market_breadth: 'Breadth',
    analyst_estimates: 'Estimates', entity_mentions: 'Entity mentions', vol_term_structure: 'Vol term'
  };

  /* ── Overview ── */
  function renderOverview(container) {
    container.innerHTML =
      '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:10px;padding:14px 18px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">' +
        '<div style="display:flex;align-items:center;gap:10px;"><span class="lw-dot lw-dot-green"></span><span class="lw-card-title">Catalog Health</span></div>' +
        '<div class="lw-mono" id="lw-health-summary" style="font-size:12px;color:var(--lw-ink-3);">Loading…</div>' +
      '</div>' +
      '<div class="lw-cat-grid" id="lw-cat-grid"></div>';

    api('/health').then(function (h) {
      $('#lw-health-summary').innerHTML = esc((h.snapshots || 0) + ' snapshots · latest: ' + (h.latest_snapshot_id || '—'));
    }).catch(function () { $('#lw-health-summary').textContent = 'health endpoint unavailable'; });

    api('/datasets').then(function (data) {
      var g = $('#lw-cat-grid');
      g.innerHTML = '';
      data.forEach(function (ds) {
        var sm = statusMeta(ds), tm = tierMeta(ds.tier);
        var label = CATEGORY_LABELS[ds.dataset] || ds.dataset;
        var head = '<div class="lw-cat-head"><div style="display:flex;align-items:center;gap:7px;min-width:0;"><span class="lw-dot lw-dot-' + sm.dot + '"></span><span class="lw-card-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + esc(label) + '</span></div><span class="lw-pill ' + tm.cls + '">' + esc(ds.tier || 'exp') + '</span></div>';
        var body;
        if (sm.state === 'ok') {
          body = '<div class="lw-cat-body"><div><div class="lw-cat-value">' + fmtRows(ds.rows) + '</div><div class="lw-cat-sub">' + esc(ds.latest_effective_date || '—') + '</div></div></div>' +
            '<div class="lw-cat-metric ' + sm.color + '">' + sm.label + ' <span class="lw-c-dim" style="font-weight:500;">· ' + ago(ds.latest_effective_date) + ' ago</span></div>';
        } else if (sm.state === 'loading') {
          body = '<div class="lw-cat-loading"><div class="lw-skel" style="height:22px;width:60%;"></div><div class="lw-skel" style="height:11px;width:85%;"></div><div class="lw-mono lw-ingesting" style="font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--lw-ink-4);">ingesting…</div></div>';
        } else {
          body = '<div class="lw-cat-empty"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.6" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 4-5"/></svg><div class="lw-cat-sub">No data in lake yet</div><div class="lw-mono" style="font-size:10px;color:var(--lw-ink-4);">awaiting first ingest</div></div>';
        }
        var card = document.createElement('div');
        card.className = 'lw-cat-card';
        card.style.cursor = 'pointer';
        card.innerHTML = head + body;
        card.addEventListener('click', function () { window.lwGoDataset && window.lwGoDataset(ds.dataset); });
        g.appendChild(card);
      });
    }).catch(function () { $('#lw-cat-grid').innerHTML = '<div class="lw-error">Failed to load catalog</div>'; });
  }

  window.lwGoDataset = function (name) {
    state.dataset = name; showTab('datasets');
    setTimeout(function () { var p = $('#lw-ds-picker'); if (p) { p.value = name; renderDatasetDetail(name); } }, 120);
  };

  /* ── Bars: per-symbol data cards ── */
  function renderBars(container) {
    container.innerHTML =
      '<div class="lw-search" style="display:flex;align-items:center;gap:8px;"><input type="text" id="lw-bar-symbol" placeholder="Search symbol…" value="' + esc(state.symbol) + '"><span class="lw-mono" id="lw-sym-count" style="font-size:11px;color:var(--lw-ink-3);white-space:nowrap;"></span></div>' +
      '<div class="lw-sym-grid" id="lw-sym-grid"></div>';
    var grid = $('#lw-sym-grid');
    var syms = []; WATCHLIST.concat(state.symbol ? [state.symbol] : []).forEach(function (s) { if (s && syms.indexOf(s) < 0) syms.push(s); });
    $('#lw-sym-count').textContent = syms.length + ' symbol' + (syms.length === 1 ? '' : 's') + ' in lake';
    syms.forEach(function (sym) { loadSymCard(grid, sym); });
    grid.insertAdjacentHTML('beforeend',
      '<div class="lw-sym-card is-empty">' +
        '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.5" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' +
        '<div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-3);">Add a symbol</div>' +
        '<div style="font-size:12px;color:var(--lw-ink-4);max-width:220px;">Symbols ingest OHLCV bars on first request. Search above to backfill from EODHD / Tiingo / Alpaca.</div>' +
      '</div>');
    $('#lw-bar-symbol').addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase().trim(); showTab('bars'); } });
  }

  function loadSymCard(grid, sym) {
    var slot = document.createElement('div'); slot.className = 'lw-sym-card'; slot.innerHTML = '<div class="lw-loading">Loading ' + esc(sym) + '</div>'; grid.appendChild(slot);
    var end = new Date(), start = new Date(end); start.setFullYear(start.getFullYear() - 1);
    var sp = start.toISOString().slice(0, 10), ep = end.toISOString().slice(0, 10);
    /* prefer the lightweight summary endpoint; fall back to /bars/indicators (always present) */
    barApi('/bars/summary', sym).then(function (s) {
      slot.innerHTML = symCardFromSummary(sym, s);
    }).catch(function () {
      barApi('/bars/indicators?indicators=sma:50,rsi:14,atr:14,macd', sym, sp, ep).then(function (res) {
        if (!res || !res.close || !res.close.length) { slot.outerHTML = emptySymCard(sym); return; }
        slot.innerHTML = symCardFromSeries(sym, res);
      }).catch(function () { slot.outerHTML = emptySymCard(sym); });
    });
  }

  function emptySymCard(sym) {
    return '<div class="lw-sym-card is-empty"><div class="lw-sym-badge">' + esc(sym[0]) + '</div><div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-2);">' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);max-width:220px;">No bars in lake for this symbol yet.</div></div>';
  }

  /* meaning-coloring: returns {cls, sub} */
  function colorChange(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'gain' } : { cls: 'lw-c-down', sub: 'loss' }; }
  function colorRsi(v) { return v > 70 ? { cls: 'lw-c-down', sub: 'overbought' } : v < 30 ? { cls: 'lw-c-up', sub: 'oversold' } : { cls: 'lw-c-ink', sub: 'neutral' }; }
  function colorSma(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'above' } : { cls: 'lw-c-down', sub: 'below' }; }
  function colorMacd(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'bullish' } : { cls: 'lw-c-down', sub: 'bearish' }; }
  function metricTile(label, val, cls, sub) {
    return '<div class="lw-metric"><div class="lw-metric-label">' + esc(label) + '</div><div class="lw-metric-val ' + (cls || 'lw-c-ink') + '">' + esc(val) + '</div><div class="lw-metric-sub">' + esc(sub || '') + '</div></div>';
  }
  function symCardShell(sym, name, last, chg, chartHtml, tiles, source, latest, quality) {
    var cc = colorChange(chg);
    var qOk = !quality || /valid|ok|pass/i.test(quality);
    return '<div class="lw-sym-head"><div class="lw-sym-id"><div class="lw-sym-badge">' + esc(sym) + '</div><div style="min-width:0;"><div class="lw-sym-ticker">' + esc(sym) + '</div><div class="lw-sym-name">' + esc(name || '') + '</div></div></div>' +
        '<div style="text-align:right;flex:none;"><div class="lw-sym-price">' + fmtMoney(last) + '</div><div class="lw-chg ' + (chg >= 0 ? 'lw-chg-up' : 'lw-chg-down') + '">' + (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%</div></div></div>' +
      '<div class="lw-sym-chart">' + chartHtml + '<div class="lw-chart-axis"><span>1y close</span><span>volume</span></div></div>' +
      '<div class="lw-metric-grid">' + tiles + '</div>' +
      '<div class="lw-sym-foot"><span>' + esc(source || '—') + '</span><span style="display:flex;align-items:center;gap:10px;"><span>fresh <span class="lw-c-up" style="font-weight:700;">' + ago(latest) + ' ago</span></span><span class="lw-q ' + (qOk ? 'lw-c-up' : 'lw-c-down') + '"><span class="lw-dot lw-dot-' + (qOk ? 'green' : 'red') + '"></span>' + esc(quality || 'valid') + '</span></span></div>';
  }

  function symCardFromSeries(sym, res) {
    var close = res.close, vol = res.volume || [], n = close.length;
    var last = lastVal(close), prev = close[n - 2] != null ? close[n - 2] : last;
    var chg = prev ? (last / prev - 1) * 100 : 0;
    var sma = lastVal(res.sma), vsSma = sma ? (last / sma - 1) * 100 : null;
    var rsi = lastVal(res.rsi);
    var atr = lastVal(res.atr), atrPct = atr ? atr / last * 100 : null;
    var macd = lastVal(res.macd_macd != null ? res.macd_macd : res.macd);
    var vlast = lastVal(vol), vavg = avg(vol.slice(-20)), vr = (vlast && vavg) ? vlast / vavg : null;
    var quality = res.quality_status ? lastVal(res.quality_status) : null;
    var source = res.source_id ? lastVal(res.source_id) : null;
    var latest = res.effective_date ? lastVal(res.effective_date) : null;
    var up = chg >= 0;
    var tiles = '';
    tiles += metricTile('Last close', fmtMoney(last), 'lw-c-ink', 'EOD');
    var cc = colorChange(chg); tiles += metricTile('Day Δ', (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%', cc.cls, cc.sub);
    if (rsi != null) { var cr = colorRsi(rsi); tiles += metricTile('RSI 14', rsi.toFixed(1), cr.cls, cr.sub); } else tiles += metricTile('RSI 14', '—', 'lw-c-dim', 'n/a');
    if (vsSma != null) { var cs = colorSma(vsSma); tiles += metricTile('vs SMA 50', (vsSma >= 0 ? '+' : '') + vsSma.toFixed(1) + '%', cs.cls, cs.sub); } else tiles += metricTile('vs SMA 50', '—', 'lw-c-dim', 'n/a');
    if (atr != null) tiles += metricTile('ATR 14', atr.toFixed(2), 'lw-c-accent', (atrPct != null ? atrPct.toFixed(1) + '% vol' : '')); else tiles += metricTile('ATR 14', '—', 'lw-c-dim', 'n/a');
    if (macd != null) { var cm = colorMacd(macd); tiles += metricTile('MACD', (macd >= 0 ? '+' : '') + macd.toFixed(2), cm.cls, cm.sub); } else tiles += metricTile('MACD', '—', 'lw-c-dim', 'n/a');
    if (vr != null) tiles += metricTile('Volume', vr.toFixed(2) + '×', vr > 1.1 ? 'lw-c-accent' : 'lw-c-dim', vr > 1.1 ? 'elevated' : 'vs 20d avg'); else tiles += metricTile('Volume', '—', 'lw-c-dim', 'n/a');
    var chart = areaChart(close.filter(function (x) { return x != null; }).slice(-260), up) + volBars(vol);
    return symCardShell(sym, '', last, chg, chart, tiles, source, latest, quality);
  }

  /* if you build the /bars/summary endpoint, this renders directly from its fields */
  function symCardFromSummary(sym, s) {
    var last = s.last, chg = s.change_pct || 0, up = chg >= 0;
    var tiles = '';
    tiles += metricTile('Last close', fmtMoney(last), 'lw-c-ink', 'EOD');
    var cc = colorChange(chg); tiles += metricTile('Day Δ', (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%', cc.cls, cc.sub);
    if (s.rsi != null) { var cr = colorRsi(s.rsi); tiles += metricTile('RSI 14', s.rsi.toFixed(1), cr.cls, cr.sub); }
    if (s.sma50 != null) { var v = (last / s.sma50 - 1) * 100, cs = colorSma(v); tiles += metricTile('vs SMA 50', (v >= 0 ? '+' : '') + v.toFixed(1) + '%', cs.cls, cs.sub); }
    if (s.atr != null) tiles += metricTile('ATR 14', s.atr.toFixed(2), 'lw-c-accent', (s.atr / last * 100).toFixed(1) + '% vol');
    if (s.macd != null) { var cm = colorMacd(s.macd); tiles += metricTile('MACD', (s.macd >= 0 ? '+' : '') + s.macd.toFixed(2), cm.cls, cm.sub); }
    if (s.vol_ratio != null) tiles += metricTile('Volume', s.vol_ratio.toFixed(2) + '×', s.vol_ratio > 1.1 ? 'lw-c-accent' : 'lw-c-dim', s.vol_ratio > 1.1 ? 'elevated' : 'vs 20d avg');
    var chart = areaChart(s.trend || [], up);
    return symCardShell(sym, s.name || '', last, chg, chart, tiles, s.source_id, s.latest_date, s.quality_status);
  }

  /* ── Sentiment & Mentions leaderboard ── */
  function renderSentiment(container) {
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:14px;">' +
        '<div style="display:flex;align-items:center;gap:7px;"><span class="lw-card-title">Attention &amp; Sentiment</span><span class="lw-mono" style="font-size:11px;color:var(--lw-ink-3);">· 24h · most-mentioned</span></div>' +
      '</div>' +
      '<div class="lw-lead-cols"><span>#</span><span>Symbol</span><span>Mentions 24h</span><span>Δ</span><span>Bullish / neutral / bearish</span><span></span></div>' +
      '<div class="lw-lead" id="lw-lead"></div>' +
      '<div class="lw-mono" style="font-size:10px;color:var(--lw-ink-4);text-align:center;letter-spacing:.04em;margin-top:10px;">source: ApeWisdom attention + Reddit / StockTwits sentiment</div>';

    api('/attention/leaderboard?limit=20').then(function (rows) {
      if (!rows || !rows.length) { $('#lw-lead').innerHTML = emptySentiment(); return; }
      window.__leaders = rows; drawLeaders();
    }).catch(function () { $('#lw-lead').innerHTML = emptySentiment(); });
  }

  function emptySentiment() {
    return '<div class="lw-empty" style="padding:36px 16px;">' +
      '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:10px;"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>' +
      '<div class="lw-mono" style="font-size:12px;color:var(--lw-ink-2);font-weight:700;">No attention data</div>' +
      '<div style="font-size:12px;margin-top:6px;">Enable <code class="lw-mono" style="color:var(--lw-accent);">/v1/dashboard/attention/leaderboard</code> over <code class="lw-mono" style="color:var(--lw-accent);">attention_metrics</code> + <code class="lw-mono" style="color:var(--lw-accent);">sentiment_annotations</code> to populate this view.</div></div>';
  }

  function drawLeaders() {
    var rows = window.__leaders || [];
    var lead = $('#lw-lead');
    lead.innerHTML = rows.map(function (l, i) {
      var pos = Math.round((l.positive_ratio != null ? l.positive_ratio : 0.5) * 100);
      var neu = l.neutral_ratio != null ? Math.round(l.neutral_ratio * 100) : Math.max(0, Math.round((1 - (l.positive_ratio || 0.5)) * 0.4 * 100));
      var neg = Math.max(0, 100 - pos - neu);
      var mean = l.mean_score != null ? l.mean_score : 0;
      var meanCls = mean > 0.05 ? 'lw-c-up' : mean < -0.05 ? 'lw-c-down' : 'lw-c-ink';
      var meanPct = ((mean + 1) / 2 * 100).toFixed(1);
      var d = l.mention_delta_pct;
      var deltaStr = d == null ? '—' : (d >= 0 ? '+' : '') + Math.round(d) + '%';
      var deltaCls = d == null ? 'lw-c-dim' : d >= 0 ? 'lw-c-up' : 'lw-c-down';
      var open = state.expanded === l.symbol;
      var spark = sparkline(l.trend || [], 70, 22, d >= 0 ? 'var(--lw-money)' : 'var(--lw-down)');
      var meanColor = mean > 0.05 ? 'var(--lw-up)' : mean < -0.05 ? 'var(--lw-down)' : 'var(--lw-ink-2)';
      return '<div class="lw-lead-item' + (open ? ' is-open' : '') + '" data-sym="' + esc(l.symbol) + '">' +
        '<div class="lw-lead-row">' +
          '<span class="lw-lead-rank">' + (i + 1) + '</span>' +
          '<div class="lw-lead-sym"><span class="lw-lead-badge">' + esc(l.symbol) + '</span><div style="min-width:0;"><div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink);">' + esc(l.symbol) + '</div><div class="lw-sym-name">' + esc(l.name || '') + '</div></div></div>' +
          '<div class="lw-lead-mentions">' + fmtNum(l.mentions) + spark + '</div>' +
          '<span class="lw-mono ' + deltaCls + '" style="font-size:12px;font-weight:700;">' + deltaStr + '</span>' +
          '<div class="lw-sent-wrap" style="display:flex;align-items:center;gap:8px;"><span class="lw-sent-bar"><span class="lw-sent-pos" style="width:' + pos + '%"></span><span class="lw-sent-neu" style="width:' + neu + '%"></span><span class="lw-sent-neg" style="width:' + neg + '%"></span></span><span class="lw-mono lw-c-up" style="font-size:11px;font-weight:700;">' + pos + '%</span></div>' +
          '<span class="lw-caret">▾</span>' +
        '</div>' +
        '<div class="lw-lead-detail">' +
          '<div><div class="lw-detail-label">Mention trend</div>' + (areaChart(l.trend || [], (d || 0) >= 0)) +
            '<div style="display:flex;gap:18px;margin-top:12px;" class="lw-mono">' +
              '<div><div class="lw-detail-label" style="margin:0;">Annotated msgs</div><div style="font-size:14px;font-weight:700;color:var(--lw-ink);margin-top:2px;">' + fmtNum(l.total_messages != null ? l.total_messages : l.samples) + '</div></div>' +
              '<div><div class="lw-detail-label" style="margin:0;">Top cohort</div><div style="font-size:14px;font-weight:700;color:var(--lw-snap);margin-top:2px;">' + esc(l.cohort || '—') + '</div></div>' +
            '</div></div>' +
          '<div style="display:flex;flex-direction:column;gap:14px;">' +
            '<div><div class="lw-detail-label">Sentiment split</div><div class="lw-sent-bar" style="height:14px;border-radius:4px;"><span class="lw-sent-pos" style="width:' + pos + '%"></span><span class="lw-sent-neu" style="width:' + neu + '%"></span><span class="lw-sent-neg" style="width:' + neg + '%"></span></div>' +
              '<div style="display:flex;justify-content:space-between;margin-top:7px;" class="lw-mono"><span class="lw-c-up" style="font-size:10px;font-weight:700;">' + pos + '% bull</span><span class="lw-c-dim" style="font-size:10px;">' + neu + '% neu</span><span class="lw-c-down" style="font-size:10px;font-weight:700;">' + neg + '% bear</span></div></div>' +
            '<div><div class="lw-detail-label">Mean score <span style="color:' + meanColor + ';">' + (mean >= 0 ? '+' : '') + mean.toFixed(2) + '</span></div>' +
              '<div class="lw-score-track"><span class="lw-score-mark" style="left:' + meanPct + '%;background:' + meanColor + ';"></span></div>' +
              '<div style="display:flex;justify-content:space-between;margin-top:6px;" class="lw-mono lw-c-dim"><span style="font-size:9px;">−1.0 bearish</span><span style="font-size:9px;">+1.0 bullish</span></div></div>' +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');
    $$('.lw-lead-row', lead).forEach(function (row) {
      row.addEventListener('click', function () {
        var sym = row.parentNode.dataset.sym;
        state.expanded = state.expanded === sym ? null : sym;
        drawLeaders();
      });
    });
  }

  /* ── Catalog (datasets) ── */
  function renderCatalog(container) {
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:12px;"><span class="lw-card-title">Dataset Catalog</span>' +
      '<select id="lw-ds-picker" style="padding:7px 12px;background:var(--lw-bg-2);color:var(--lw-ink);border:1px solid var(--lw-rule);border-radius:999px;font-family:var(--lw-mono);font-size:var(--lw-size-small);"><option value="">— inspect rows —</option></select></div>' +
      '<div class="lw-cat-cols"><span>Dataset</span><span style="text-align:right;">Rows</span><span>Latest · fresh</span></div>' +
      '<div class="lw-cat-list" id="lw-cat-list"></div>' +
      '<div id="lw-ds-detail" style="margin-top:14px;"></div>';

    api('/datasets').then(function (list) {
      var picker = $('#lw-ds-picker');
      list.forEach(function (ds) { var o = document.createElement('option'); o.value = ds.dataset; o.textContent = ds.dataset + ' (' + fmtRows(ds.rows) + ')'; picker.appendChild(o); });
      picker.addEventListener('change', function () { state.dataset = picker.value; renderDatasetDetail(picker.value); });
      var listEl = $('#lw-cat-list');
      listEl.innerHTML = list.map(function (ds) {
        var sm = statusMeta(ds), tm = tierMeta(ds.tier);
        var freshTxt = ds.latest_effective_date ? esc(ds.latest_effective_date) + ' <span class="lw-c-dim">· ' + ago(ds.latest_effective_date) + '</span>' : '<span class="lw-c-dim">—</span>';
        return '<div class="lw-cat-row" data-ds="' + esc(ds.dataset) + '" style="cursor:pointer;">' +
          '<div class="lw-cat-ds"><span class="lw-dot lw-dot-' + sm.dot + '"></span><span class="lw-cat-name">' + esc(ds.dataset) + '</span><span class="lw-pill ' + tm.cls + '" style="font-size:8.5px;padding:2px 6px;">' + esc(ds.tier || 'exp') + '</span><span class="lw-cat-status ' + sm.color + '">' + sm.label + '</span></div>' +
          '<span class="lw-cat-rows">' + fmtRows(ds.rows) + '</span>' +
          '<span class="lw-mono" style="font-size:11px;color:var(--lw-ink-3);">' + freshTxt + '</span>' +
        '</div>';
      }).join('');
      $$('.lw-cat-row', listEl).forEach(function (r) { r.addEventListener('click', function () { var n = r.dataset.ds; picker.value = n; state.dataset = n; renderDatasetDetail(n); }); });
      if (state.dataset) { picker.value = state.dataset; renderDatasetDetail(state.dataset); }
    }).catch(function () { $('#lw-cat-list').innerHTML = '<div class="lw-error">Failed to load catalog</div>'; });
  }

  function renderDatasetDetail(name) {
    var content = $('#lw-ds-detail');
    if (!content) return;
    if (!name) { content.innerHTML = ''; return; }
    content.innerHTML = '<div class="lw-loading">Loading ' + esc(name) + '</div>';
    api('/dataset/' + name + '?limit=50').then(function (res) {
      if (!res.rows || res.rows.length === 0) { content.innerHTML = '<div class="lw-empty">No rows in ' + esc(name) + '</div>'; return; }
      var cols = ['effective_date', 'available_at', 'source_id', 'quality_status', 'version_hash'];
      var extra = res.columns.filter(function (c) { return cols.indexOf(c) === -1; }).slice(0, 5);
      var show = cols.concat(extra);
      var h = '<div class="lw-table-wrap"><table class="lw-table"><thead><tr>' + show.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>';
      res.rows.slice(0, 30).forEach(function (r) { h += '<tr>' + show.map(function (c) { var v = r[c]; return '<td>' + (v == null ? '—' : esc(String(v).slice(0, 28))) + '</td>'; }).join('') + '</tr>'; });
      content.innerHTML = h + '</tbody></table></div>';
    }).catch(function () { content.innerHTML = '<div class="lw-error">Failed to load</div>'; });
  }

  /* ── Securities (unchanged behavior) ── */
  function renderSecurities(container) {
    container.innerHTML = '<div class="lw-search"><input type="text" id="lw-sec-search" placeholder="Search symbol…" value="' + esc(state.symbol) + '"></div><div id="lw-sec-detail"></div>';
    var input = $('#lw-sec-search');
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase(); loadSecurity(state.symbol); } });
    if (state.symbol) loadSecurity(state.symbol);
  }
  function loadSecurity(sym) {
    var content = $('#lw-sec-detail');
    content.innerHTML = '<div class="lw-loading">Loading</div>';
    api('/security/' + sym).then(function (agg) {
      var h = '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-bottom:8px;"><div class="lw-card-title">' + esc(sym) + ' <span class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">' + esc(agg.security_id) + '</span></div><div class="lw-card-sub">as_of: ' + esc(agg.as_of) + '</div></div>';
      Object.keys(agg.datasets).forEach(function (ds) {
        var rows = agg.datasets[ds];
        h += '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-bottom:6px;"><div class="lw-card-title">' + esc(ds) + ' <span class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">' + rows.length + ' rows</span></div>';
        rows.slice(0, 5).forEach(function (r) {
          var src = r.source_id || '—', avail = r.available_at ? String(r.available_at).slice(0, 19) : '—', qs = r.quality_status || '—';
          h += '<div class="lw-li-summary" style="border-bottom:1px solid var(--lw-rule);padding:6px 0;font-size:var(--lw-size-small);"><span class="lw-li-label">' + esc(src) + ' @ ' + esc(avail) + '</span><span class="lw-li-value lw-mono">' + esc(qs) + '</span></div>';
        });
        h += '</div>';
      });
      content.innerHTML = h;
    }).catch(function () { content.innerHTML = '<div class="lw-error">Symbol not found</div>'; });
  }

  /* ── PIT ── */
  function renderPit(container) {
    container.innerHTML =
      '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:12px;padding:16px 18px;margin-bottom:14px;"><div class="lw-card-title">Point-in-Time Playground</div>' +
        '<p style="font-size:13px;color:var(--lw-ink-3);margin-top:8px;max-width:640px;">Rewind <strong style="color:var(--lw-ink-2);">knowledge-time</strong> via <strong>as_of</strong> in the header to see exactly what the lake knew as of any instant. Every read is bounded by <code style="font-family:var(--lw-mono);color:var(--lw-accent);background:var(--lw-bg-3);padding:1px 5px;border-radius:4px;">available_at ≤ as_of</code>.</p>' +
        '<div class="lw-pit-presets" id="lw-pit-presets"></div></div>' +
      '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:12px;padding:16px 18px;margin-bottom:14px;"><div class="lw-detail-label">Knowledge-time axis · snapshots</div><div class="lw-kt-strip" id="lw-kt-strip"><div class="lw-kt-line"></div><div class="lw-kt-fill" style="width:88%"></div><div class="lw-kt-now"></div></div><div class="lw-kt-labels"><span id="lw-kt-first">—</span><span>now · live</span></div></div>' +
      '<div id="lw-snapshots"></div>';

    api('/snapshots').then(function (list) {
      if (!list || !list.length) { $('#lw-snapshots').innerHTML = '<div class="lw-empty">No snapshots yet</div>'; return; }
      var strip = $('#lw-kt-strip'), n = list.length;
      list.forEach(function (s, i) { var dot = document.createElement('span'); dot.className = 'lw-kt-dot'; dot.style.left = ((n - 1 - i) / Math.max(1, n - 1) * 88).toFixed(1) + '%'; strip.appendChild(dot); });
      $('#lw-kt-first').textContent = (list[list.length - 1].timestamp || '').slice(0, 10) || '—';
      var h = '<div class="lw-cat-list"><div class="lw-cat-cols" style="grid-template-columns:1.6fr 1.4fr 80px;"><span>Snapshot</span><span>Timestamp</span><span style="text-align:right;">Rows</span></div>';
      list.slice(0, 15).forEach(function (s) {
        h += '<div class="lw-cat-row" style="grid-template-columns:1.6fr 1.4fr 80px;"><span class="lw-cat-ds"><span class="lw-dot" style="background:var(--lw-snap);"></span><span class="lw-cat-name">' + esc(s.snapshot_id || s.id || '—') + '</span></span><span class="lw-mono" style="font-size:11px;color:var(--lw-ink-3);">' + esc(s.timestamp || '—') + '</span><span class="lw-cat-rows">' + (s.rows != null ? fmtRows(s.rows) : '—') + '</span></div>';
      });
      $('#lw-snapshots').innerHTML = h + '</div>';
    }).catch(function () { $('#lw-snapshots').innerHTML = '<div class="lw-error">Failed to load snapshots</div>'; });

    var presets = $('#lw-pit-presets'), now = new Date();
    [7, 30, 90].forEach(function (dys) {
      var btn = document.createElement('button'); btn.textContent = 'Rewind ' + dys + ' days';
      btn.addEventListener('click', function () { var dt = new Date(now); dt.setDate(dt.getDate() - dys); var input = $('#lw-asof'); if (input) { input.value = dt.toISOString().slice(0, 16); input.dispatchEvent(new Event('change')); } });
      presets.appendChild(btn);
    });
  }

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded', function () {
    $$('.lw-tab').forEach(function (t) { t.addEventListener('click', function () { showTab(t.dataset.tab); }); });

    var hdr = $('#lw-header-time');
    if (hdr) hdr.textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();

    var asOfInput = $('#lw-asof');
    if (asOfInput) {
      var n = new Date(); n.setSeconds(0, 0);
      asOfInput.value = n.toISOString().slice(0, 16);
      asOfInput.addEventListener('change', function () { state.asOf = asOfInput.value ? new Date(asOfInput.value).toISOString() : null; showTab(state.tab); });
    }

    var snap = $('#lw-snapshot');
    if (snap) {
      api('/snapshots').then(function (list) { list.forEach(function (s) { var o = document.createElement('option'); o.value = s.snapshot_id || s.id || ''; o.textContent = s.snapshot_id || s.id || ''; snap.appendChild(o); }); }).catch(function () {});
      snap.addEventListener('change', function () { state.snapshotId = snap.value; showTab(state.tab); });
    }

    var pm = $('#lw-price-mode');
    if (pm) pm.addEventListener('change', function () { state.priceMode = pm.value; if (state.tab === 'bars') showTab('bars'); });

    $$('.lw-theme-btn').forEach(function (b) { b.addEventListener('click', function () { applyTheme(b.dataset.theme); }); });

    var settingsBtn = $('#lw-settings-btn'), settingsPop = $('#lw-settings-pop');
    if (settingsBtn && settingsPop) {
      settingsBtn.addEventListener('click', function (e) { e.stopPropagation(); settingsPop.classList.toggle('is-open'); });
      document.addEventListener('click', function () { settingsPop.classList.remove('is-open'); });
      settingsPop.addEventListener('click', function (e) { e.stopPropagation(); });
    }

    showTab('overview');
  });
})();
