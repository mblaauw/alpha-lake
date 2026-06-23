/* Lake Watch — warm-tone newsroom-style dashboard.
   Data-reflecting visuals: symbol cards, sentiment leaderboard, catalog, PIT.
   Every fetch degrades gracefully — missing/empty endpoints render empty or
   loading states instead of breaking. */
(function () {
  'use strict';

  var API = '/v1/dashboard';
  var state = { asOf: null, snapshotId: '', priceMode: 'raw', tab: 'overview', symbol: '', dataset: '', expanded: null, indCat: 'All' };
  var _leaders = [];

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
  function debounce(fn, ms) { var t; return function () { var c = this, a = arguments; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }

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
      case 'indicators': renderIndicators(content); break;
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
      var banner = $('#lw-syn-banner');
      if (banner) banner.style.display = h.synthetic_mode ? 'flex' : 'none';
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
        card.innerHTML = head + body;
        g.appendChild(card);
      });
    }).catch(function () { $('#lw-cat-grid').innerHTML = '<div class="lw-error">Failed to load catalog</div>'; });
  }

  /* ── Meaning-coloring helpers: return {cls, sub} ── */
  function colorChange(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'gain' } : { cls: 'lw-c-down', sub: 'loss' }; }
  function colorRsi(v) { return v > 70 ? { cls: 'lw-c-down', sub: 'overbought' } : v < 30 ? { cls: 'lw-c-up', sub: 'oversold' } : { cls: 'lw-c-ink', sub: 'neutral' }; }
  function colorSma(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'above' } : { cls: 'lw-c-down', sub: 'below' }; }
  function colorMacd(v) { return v >= 0 ? { cls: 'lw-c-up', sub: 'bullish' } : { cls: 'lw-c-down', sub: 'bearish' }; }
  function metricTile(label, val, cls, sub) {
    return '<div class="lw-metric"><div class="lw-metric-label">' + esc(label) + '</div><div class="lw-metric-val ' + (cls || 'lw-c-ink') + '">' + esc(val) + '</div><div class="lw-metric-sub">' + esc(sub || '') + '</div></div>';
  }

  /* ── Bars: real-data symbol cards ── */
  function renderBars(container) {
    container.innerHTML = '<div class="lw-search" style="display:flex;align-items:center;gap:8px;"><input type="text" id="lw-bar-symbol" placeholder="Search symbol…" value="' + esc(state.symbol) + '"><span class="lw-mono" id="lw-sym-count" style="font-size:11px;color:var(--lw-ink-3);white-space:nowrap;"></span></div>' +
      '<div class="lw-sym-grid" id="lw-sym-grid"></div>';
    var inp = $('#lw-bar-symbol');
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase().trim(); showTab('bars'); } });
    inp.addEventListener('input', debounce(function () { state.symbol = this.value.toUpperCase().trim(); renderBars(container); }, 300));

    api('/bars/symbols').then(function (list) {
      var grid = $('#lw-sym-grid');
      list = list || [];
      /* filter by search query (case-insensitive prefix/substring on symbol and name) */
      var q = state.symbol;
      if (q) {
        list = list.filter(function (it) {
          return (it.symbol || '').toUpperCase().indexOf(q) !== -1 || (it.name || '').toUpperCase().indexOf(q) !== -1;
        });
      }
      /* if the user searched a symbol not already in the lake list, lead with it */
      if (state.symbol && !list.some(function (it) { return (it.symbol || '') === state.symbol; })) {
        list = [{ symbol: state.symbol, security_id: state.symbol, name: '' }].concat(list);
      }
      $('#lw-sym-count').textContent = list.length + ' symbol' + (list.length === 1 ? '' : 's') + ' in lake';
      if (!list.length) { grid.innerHTML = barsEmpty(); return; }
      list.forEach(function (item) { loadRealCard(grid, item.symbol || item.security_id, item.name || ''); });
    }).catch(function () { $('#lw-sym-count').textContent = 'could not load symbols'; $('#lw-sym-grid').innerHTML = barsEmpty(); });
  }

  function barsEmpty() {
    return '<div class="lw-sym-card is-empty"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.5" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' +
      '<div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-2);">No symbols in lake</div>' +
      '<div style="font-size:12px;color:var(--lw-ink-4);max-width:240px;">Ingest OHLCV bars or social data, or search a symbol above to backfill from EODHD / Tiingo / Alpaca.</div></div>';
  }

  var CARD_SIGNAL_DATASETS = 'insider_tx,sentiment_annotations,news_articles,attention_metrics';

  function loadRealCard(grid, sym, name) {
    var slot = document.createElement('div'); slot.className = 'lw-sym-card';
    slot.innerHTML = '<div class="lw-loading">Loading ' + esc(sym) + '</div>';
    grid.appendChild(slot);

    barApi('/bars/summary', sym).then(function (s) {
      /* enrich with cross-dataset signals — limited dataset scan keeps this cheap */
      api('/security/' + encodeURIComponent(sym) + '?datasets=' + CARD_SIGNAL_DATASETS).then(function (agg) {
        slot.innerHTML = barCard(sym, name, s, agg.datasets || {});
      }).catch(function () { slot.innerHTML = barCard(sym, name, s, {}); });
    }).catch(function () {
      /* no bars for this symbol — try a signals-only card, else empty */
      api('/security/' + encodeURIComponent(sym) + '?datasets=' + CARD_SIGNAL_DATASETS).then(function (agg) {
        var ds = agg.datasets || {};
        if (!Object.keys(ds).length) { slot.outerHTML = emptyCard(sym, name); return; }
        slot.innerHTML = signalsOnlyCard(sym, name, ds);
      }).catch(function () { slot.outerHTML = emptyCard(sym, name); });
    });
  }

  function symHead(sym, name, last, chg) {
    var price = (last != null)
      ? '<div style="text-align:right;flex:none;"><div class="lw-sym-price">' + fmtMoney(last) + '</div><div class="lw-chg ' + ((chg || 0) >= 0 ? 'lw-chg-up' : 'lw-chg-down') + '">' + ((chg || 0) >= 0 ? '+' : '') + (chg || 0).toFixed(2) + '%</div></div>'
      : '';
    return '<div class="lw-sym-head"><div class="lw-sym-id"><div class="lw-sym-badge">' + esc((sym || '?')[0]) + '</div><div style="min-width:0;"><div class="lw-sym-ticker">' + esc(sym) + '</div><div class="lw-sym-name">' + esc(name || '') + '</div></div></div>' + price + '</div>';
  }

  function symFoot(source, latest, quality) {
    var qOk = !quality || /valid|ok|pass/i.test(quality);
    return '<div class="lw-sym-foot"><span>' + esc(source || '—') + '</span><span style="display:flex;align-items:center;gap:10px;">' +
      (latest ? '<span>fresh <span class="lw-c-up" style="font-weight:700;">' + ago(latest) + ' ago</span></span>' : '') +
      '<span class="lw-q ' + (qOk ? 'lw-c-up' : 'lw-c-down') + '"><span class="lw-dot lw-dot-' + (qOk ? 'green' : 'red') + '"></span>' + esc(quality || 'valid') + '</span></span></div>';
  }

  function signalChip(label, value, color) {
    return '<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 9px;background:var(--lw-bg);border:1px solid var(--lw-rule);border-radius:999px;font-family:var(--lw-mono);font-size:10px;white-space:nowrap;">' +
      '<span style="color:var(--lw-ink-3);text-transform:uppercase;letter-spacing:.05em;">' + esc(label) + '</span>' +
      '<span style="font-weight:700;color:' + (color || 'var(--lw-ink)') + ';">' + esc(value) + '</span></span>';
  }

  function signalsRow(ds) {
    var chips = [];
    var insider = ds.insider_tx || [];
    if (insider.length) {
      var buys = insider.filter(function (r) { return r.transaction_code === 'P'; }).length;
      var sells = insider.filter(function (r) { return r.transaction_code === 'S'; }).length;
      chips.push(signalChip('Insider', buys + 'B / ' + sells + 'S', buys >= sells ? 'var(--lw-up)' : 'var(--lw-down)'));
    }
    var sent = ds.sentiment_annotations || [];
    if (sent.length) {
      var pos = sent.filter(function (r) { return (r.sentiment_score || 0) > 0; }).length;
      var neg = sent.filter(function (r) { return (r.sentiment_score || 0) < 0; }).length;
      chips.push(signalChip('Sentiment', pos + '\u25B2 ' + neg + '\u25BC', pos >= neg ? 'var(--lw-up)' : 'var(--lw-down)'));
    }
    var news = ds.news_articles || [];
    if (news.length) chips.push(signalChip('News', String(news.length), 'var(--lw-ink)'));
    var attn = ds.attention_metrics || [];
    if (attn.length) { var t = attn[0]; chips.push(signalChip('Mentions', String(t.mentions || 0), 'var(--lw-accent)')); }
    if (!chips.length) return '';
    return '<div style="display:flex;flex-wrap:wrap;gap:6px;">' + chips.join('') + '</div>';
  }

  function barCard(sym, name, s, ds) {
    var up = (s.change_pct || 0) >= 0;
    var chart = (s.trend && s.trend.length >= 2) ? areaChart(s.trend, up) : '';
    var vol = (s.volume && s.volume.length >= 2) ? volBars(s.volume) : '';
    var chartSection = chart ? '<div class="lw-sym-chart">' + chart + vol + '<div class="lw-chart-axis"><span>~6mo close</span><span>volume</span></div></div>' : '';

    var last = s.last, tiles = '';
    if (last != null) tiles += metricTile('Last close', fmtMoney(last), 'lw-c-ink', 'EOD');
    var cc = colorChange(s.change_pct || 0); tiles += metricTile('Day Δ', ((s.change_pct || 0) >= 0 ? '+' : '') + (s.change_pct || 0).toFixed(2) + '%', cc.cls, cc.sub);
    if (s.rsi != null) { var cr = colorRsi(s.rsi); tiles += metricTile('RSI 14', s.rsi.toFixed(1), cr.cls, cr.sub); }
    if (s.sma50 != null && last != null) { var vs = (last / s.sma50 - 1) * 100, csm = colorSma(vs); tiles += metricTile('vs SMA 50', (vs >= 0 ? '+' : '') + vs.toFixed(1) + '%', csm.cls, csm.sub); }
    if (s.atr != null && last != null) tiles += metricTile('ATR 14', s.atr.toFixed(2), 'lw-c-accent', (s.atr / last * 100).toFixed(1) + '% vol');
    if (s.macd != null) { var cm = colorMacd(s.macd); tiles += metricTile('MACD', (s.macd >= 0 ? '+' : '') + s.macd.toFixed(2), cm.cls, cm.sub); }
    if (s.vol_ratio != null) tiles += metricTile('Volume', s.vol_ratio.toFixed(2) + '×', s.vol_ratio > 1.1 ? 'lw-c-accent' : 'lw-c-dim', s.vol_ratio > 1.1 ? 'elevated' : 'vs 20d avg');

    return symHead(sym, name || s.name, last, s.change_pct) +
      chartSection +
      '<div class="lw-metric-grid">' + tiles + '</div>' +
      signalsRow(ds) +
      symFoot(s.source_id, s.latest_date, s.quality_status);
  }

  function signalsOnlyCard(sym, name, ds) {
    var row = signalsRow(ds);
    return symHead(sym, name, null, null) +
      (row || '<div class="lw-metric-grid"><div class="lw-metric" style="grid-column:1/-1;"><div class="lw-metric-label">Lake data</div><div class="lw-metric-val lw-c-ink">—</div><div class="lw-metric-sub">No price bars; signals only</div></div></div>');
  }

  function emptyCard(sym, name) {
    return '<div class="lw-sym-card is-empty"><div class="lw-sym-badge">' + esc((sym || '?')[0]) + '</div><div class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink-2);">' + esc(sym) + '</div><div style="font-size:12px;color:var(--lw-ink-4);max-width:220px;">No data in lake for this symbol yet.</div></div>';
  }

  /* ── Sentiment & Mentions leaderboard ── */
  function renderSentiment(container) {
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:12px;">' +
        '<span class="lw-card-title">Social Sentiment</span>' +
        '<span class="lw-mono" style="font-size:10px;color:var(--lw-ink-3);letter-spacing:.06em;">most-mentioned 24h</span>' +
      '</div>' +
      '<div class="lw-lead" id="lw-lead"></div>' +
      '<div class="lw-mono" style="font-size:10px;color:var(--lw-ink-4);text-align:center;margin-top:8px;">ApeWisdom attention + StockTwits sentiment</div>';

    api('/attention/leaderboard?limit=20').then(function (rows) {
      if (!rows || !rows.length) { $('#lw-lead').innerHTML = emptySentiment(); return; }
      _leaders = rows; drawLeaders();
    }).catch(function () { $('#lw-lead').innerHTML = emptySentiment(); });
  }

  function emptySentiment() {
    return '<div class="lw-empty" style="padding:36px 16px;">' +
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--lw-ink-4)" stroke-width="1.5" stroke-linecap="round"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M2 12a10 10 0 0 1 10-10"/><path d="M12 2v10l4 4"/></svg>' +
      '<div class="lw-mono" style="font-size:12px;color:var(--lw-ink-3);margin-top:8px;">Awaiting attention data</div></div>';
  }

  function drawLeaders() {
    var rows = _leaders;
    var lead = $('#lw-lead');
    lead.innerHTML = '<div class="lw-lead-head"><span>Symbol</span><span>Mentions</span><span>Δ</span><span>Bull / Neu / Bear</span><span></span></div>' +
      rows.map(function (l) {
        var hasSent = l.positive_ratio != null;
        var posP = hasSent ? Math.round(l.positive_ratio * 100) : 0;
        /* real 3-way split when the backend supplies it; otherwise show bull vs.
           an explicitly-muted remainder — never fabricate a neutral/bear ratio */
        var has3 = hasSent && (l.neutral_ratio != null || l.negative_ratio != null);
        var neuP, negP;
        if (has3) { neuP = Math.round((l.neutral_ratio || 0) * 100); negP = Math.max(0, 100 - posP - neuP); }
        else { neuP = hasSent ? (100 - posP) : 0; negP = 0; }

        var d = l.mention_delta_pct;
        var deltaStr = d == null ? '—' : (d >= 0 ? '+' : '') + Math.round(d) + '%';
        var deltaCls = d == null ? 'lw-c-dim' : d >= 0 ? 'lw-c-up' : 'lw-c-down';
        var open = state.expanded === l.symbol;
        var trend = (l.trend || []).length >= 2 ? l.trend : [0, l.mentions || 1];
        var spark = sparkline(trend, 56, 18, (d || 0) >= 0 ? 'var(--lw-money)' : 'var(--lw-down)');
        var badge = (l.symbol || '?')[0];

        var sentCell = hasSent
          ? '<div class="lw-sent-wrap" style="display:flex;align-items:center;gap:6px;"><span class="lw-sent-bar" style="width:70px;"><span class="lw-sent-pos" style="width:' + posP + '%"></span><span class="lw-sent-neu" style="width:' + neuP + '%"></span><span class="lw-sent-neg" style="width:' + negP + '%"></span></span><span class="lw-mono" style="font-size:11px;font-weight:700;color:var(--lw-up);">' + posP + '%</span></div>'
          : '<div class="lw-sent-wrap" style="display:flex;align-items:center;gap:6px;"><span class="lw-mono lw-c-dim" style="font-size:11px;">no sentiment</span></div>';

        var meanColor = l.mean_score > 0 ? 'var(--lw-up)' : l.mean_score < 0 ? 'var(--lw-down)' : 'var(--lw-ink-3)';
        var legend = hasSent
          ? (has3
            ? '<span class="lw-c-up" style="font-weight:700;">' + posP + '% bull</span> · <span class="lw-c-dim">' + neuP + '% neu</span> · <span class="lw-c-down" style="font-weight:700;">' + negP + '% bear</span>'
            : '<span class="lw-c-up" style="font-weight:700;">' + posP + '% bull</span> · <span class="lw-c-dim">' + (100 - posP) + '% neutral / bearish</span>')
          : '<span class="lw-c-dim">no labelled messages</span>';

        var detailHtml =
          '<div class="lw-lead-detail">' +
            '<div><div class="lw-detail-label">Mention trend</div>' + (areaChart(trend, (d || 0) >= 0) || '<div class="lw-dim" style="padding:16px 0;">—</div>') + '</div>' +
            '<div style="display:flex;flex-direction:column;gap:10px;">' +
              '<div><div class="lw-detail-label">Sentiment</div><div class="lw-mono" style="font-size:11px;margin-top:2px;">' + legend + '</div></div>' +
              '<div><div class="lw-detail-label">Mean score</div><div class="lw-mono" style="font-size:14px;font-weight:700;color:' + meanColor + ';">' + (l.mean_score != null ? l.mean_score.toFixed(3) : '—') + '</div></div>' +
              '<div style="display:flex;gap:18px;">' +
                '<div><div class="lw-detail-label">Messages</div><div class="lw-mono" style="font-size:13px;color:var(--lw-ink);">' + fmtNum(l.total_messages) + '</div></div>' +
                (l.cohort ? '<div><div class="lw-detail-label">Cohort</div><div class="lw-mono" style="font-size:13px;color:var(--lw-snap);">' + esc(l.cohort) + '</div></div>' : '') +
              '</div>' +
            '</div>' +
          '</div>';

        var nameLine = l.name ? '<div class="lw-sym-name" style="font-size:10px;">' + esc(l.name) + '</div>' : '';

        return '<div class="lw-lead-item' + (open ? ' is-open' : '') + '" data-sym="' + esc(l.symbol) + '">' +
          '<div class="lw-lead-row">' +
            '<div style="display:flex;align-items:center;gap:8px;min-width:0;"><span class="lw-lead-badge" style="width:26px;height:26px;border-radius:50%;font-size:10px;">' + esc(badge) + '</span><div style="min-width:0;"><span class="lw-mono" style="font-size:13px;font-weight:600;color:var(--lw-ink);">' + esc(l.symbol) + '</span>' + nameLine + '</div></div>' +
            '<div class="lw-lead-mentions" style="justify-content:flex-end;"><span class="lw-mono" style="font-size:13px;font-weight:700;color:var(--lw-ink);">' + fmtNum(l.mentions) + '</span>' + spark + '</div>' +
            '<span class="lw-mono ' + deltaCls + '" style="font-size:12px;font-weight:700;">' + deltaStr + '</span>' +
            sentCell +
            '<span class="lw-caret">▾</span>' +
          '</div>' +
          detailHtml +
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

  /* ── Indicator definitions with categories ── */
  var IND_DEFS = [
    { label: 'RSI', key: 'rsi', cat: 'Momentum', fmt: 'num' },
    { label: 'SMA20', key: 'sma_20', cat: 'Trend', fmt: 'price' },
    { label: 'SMA50', key: 'sma_50', cat: 'Trend', fmt: 'price' },
    { label: 'SMA200', key: 'sma_200', cat: 'Trend', fmt: 'price' },
    { label: 'EMA12', key: 'ema_12', cat: 'Trend', fmt: 'price' },
    { label: 'EMA26', key: 'ema_26', cat: 'Trend', fmt: 'price' },
    { label: 'BB U', key: 'bb_upper', cat: 'Volatility', fmt: 'price' },
    { label: 'BB M', key: 'bb_middle', cat: 'Volatility', fmt: 'price' },
    { label: 'BB L', key: 'bb_lower', cat: 'Volatility', fmt: 'price' },
    { label: 'ATR', key: 'atr', cat: 'Volatility', fmt: 'num' },
    { label: 'ATR%', key: 'atr_pct', cat: 'Volatility', fmt: 'pct' },
    { label: 'VWAP', key: 'vwap', cat: 'Volume', fmt: 'price' },
    { label: 'MACD', key: 'macd', cat: 'Trend', fmt: 'num' },
    { label: 'MACDe', key: 'macd_ema', cat: 'Trend', fmt: 'num' },
    { label: 'MACh', key: 'macd_hist', cat: 'Trend', fmt: 'num' },
    { label: 'OBV', key: 'obv', cat: 'Volume', fmt: 'big' },
    { label: 'RVol', key: 'rvol', cat: 'Volume', fmt: 'num2' },
    { label: 'DolV', key: 'dollar_volume', cat: 'Volume', fmt: 'big' },
    { label: 'aDol20', key: 'avg_dollar_volume_20', cat: 'Volume', fmt: 'big' },
    { label: 'R1d', key: 'return_1d', cat: 'Structure', fmt: 'pct' },
    { label: 'R5d', key: 'return_5d', cat: 'Structure', fmt: 'pct' },
    { label: 'R21d', key: 'return_21d', cat: 'Structure', fmt: 'pct' },
    { label: 'R63d', key: 'return_63d', cat: 'Structure', fmt: 'pct' },
    { label: 'Gap%', key: 'gap_pct', cat: 'Structure', fmt: 'pct' },
    { label: '52wHi', key: 'pct_off_52w_high', cat: 'Structure', fmt: 'pct' },
    { label: '52wLo', key: 'pct_off_52w_low', cat: 'Structure', fmt: 'pct' },
    { label: 'N52wH', key: 'is_new_52w_high', cat: 'Structure', fmt: 'bool' },
    { label: 'N52wL', key: 'is_new_52w_low', cat: 'Structure', fmt: 'bool' },
    { label: 'RV21', key: 'realized_vol_21', cat: 'Volatility', fmt: 'pct' },
    { label: 'RV63', key: 'realized_vol_63', cat: 'Volatility', fmt: 'pct' },
  ];
  /* Extra new indicators from sub-issues 3-7 — keep sorted by category */
  var IND_DEFS_EXTRA = [
    { label: 'ADX', key: 'adx_14', cat: 'Trend', fmt: 'num2' },
    { label: 'DI+', key: 'di_plus_14', cat: 'Trend', fmt: 'num2' },
    { label: 'DI-', key: 'di_minus_14', cat: 'Trend', fmt: 'num2' },
    { label: 'AroonU', key: 'aroon_up_25', cat: 'Trend', fmt: 'num' },
    { label: 'AroonD', key: 'aroon_down_25', cat: 'Trend', fmt: 'num' },
    { label: 'AroonO', key: 'aroon_osc_25', cat: 'Trend', fmt: 'num' },
    { label: 'PPO', key: 'ppo', cat: 'Trend', fmt: 'num2' },
    { label: 'PPOs', key: 'ppo_signal', cat: 'Trend', fmt: 'num2' },
    { label: 'PPOh', key: 'ppo_histogram', cat: 'Trend', fmt: 'num2' },
    { label: 'TRIX', key: 'trix_15', cat: 'Trend', fmt: 'num2' },
    { label: 'ROC', key: 'roc_12', cat: 'Momentum', fmt: 'pct' },
    { label: 'StochK', key: 'stoch_k_14', cat: 'Momentum', fmt: 'num' },
    { label: 'StochD', key: 'stoch_d_3', cat: 'Momentum', fmt: 'num' },
    { label: 'StRSI', key: 'stoch_rsi_14', cat: 'Momentum', fmt: 'num2' },
    { label: 'Wm%R', key: 'williams_r_14', cat: 'Momentum', fmt: 'num' },
    { label: 'CCI', key: 'cci_20', cat: 'Momentum', fmt: 'num' },
    { label: 'TSI', key: 'tsi_25_13', cat: 'Momentum', fmt: 'num2' },
    { label: 'UltO', key: 'ultimate_osc', cat: 'Momentum', fmt: 'num' },
    { label: 'CMO', key: 'cmo_14', cat: 'Momentum', fmt: 'num' },
    { label: 'BoP', key: 'bop', cat: 'Momentum', fmt: 'num2' },
    { label: 'CHOP', key: 'chop_14', cat: 'Momentum', fmt: 'num' },
    { label: '%B', key: 'percent_b', cat: 'Volatility', fmt: 'num2' },
    { label: 'BW', key: 'bandwidth', cat: 'Volatility', fmt: 'num4' },
    { label: 'Squeeze', key: 'bb_squeeze', cat: 'Volatility', fmt: 'bool' },
    { label: 'KeltU', key: 'keltner_upper', cat: 'Volatility', fmt: 'price' },
    { label: 'KeltM', key: 'keltner_middle', cat: 'Volatility', fmt: 'price' },
    { label: 'KeltL', key: 'keltner_lower', cat: 'Volatility', fmt: 'price' },
    { label: 'DonU', key: 'donchian_upper', cat: 'Volatility', fmt: 'price' },
    { label: 'DonM', key: 'donchian_middle', cat: 'Volatility', fmt: 'price' },
    { label: 'DonL', key: 'donchian_lower', cat: 'Volatility', fmt: 'price' },
    { label: 'RExp', key: 'range_expansion', cat: 'Volatility', fmt: 'num2' },
    { label: 'TR', key: 'true_range', cat: 'Volatility', fmt: 'num2' },
    { label: 'σ20', key: 'rolling_std_20', cat: 'Volatility', fmt: 'num2' },
    { label: 'WMA', key: 'wma_20', cat: 'Trend', fmt: 'price' },
    { label: 'KAMA', key: 'kama_10', cat: 'Trend', fmt: 'price' },
    { label: 'LinR', key: 'linreg_slope_20', cat: 'Trend', fmt: 'num4' },
    { label: 'LR Up', key: 'linreg_channel_upper', cat: 'Trend', fmt: 'price' },
    { label: 'LR Mid', key: 'linreg_channel_middle', cat: 'Trend', fmt: 'price' },
    { label: 'LR Lw', key: 'linreg_channel_lower', cat: 'Trend', fmt: 'price' },
    { label: 'PvtHi', key: 'pivot_high', cat: 'Structure', fmt: 'price' },
    { label: 'PvtLo', key: 'pivot_low', cat: 'Structure', fmt: 'price' },
    { label: 'InBar', key: 'inside_bar', cat: 'Structure', fmt: 'bool' },
    { label: 'OutBar', key: 'outside_bar', cat: 'Structure', fmt: 'bool' },
    { label: 'GFill', key: 'gap_fill', cat: 'Structure', fmt: 'bool' },
    { label: 'A/D', key: 'ad_line', cat: 'Volume', fmt: 'big' },
    { label: 'CMF', key: 'cmf_20', cat: 'Volume', fmt: 'num3' },
    { label: 'Chaik', key: 'chaikin_osc', cat: 'Volume', fmt: 'num2' },
    { label: 'MFI', key: 'mfi_14', cat: 'Volume', fmt: 'num' },
    { label: 'VPT', key: 'vpt', cat: 'Volume', fmt: 'big' },
    { label: 'Force', key: 'force_index_13', cat: 'Volume', fmt: 'num2' },
    { label: 'EOM', key: 'eom_14', cat: 'Volume', fmt: 'num4' },
    { label: 'OBVs', key: 'obv_slope_20', cat: 'Volume', fmt: 'num2' },
    { label: 'VSpike', key: 'volume_spike', cat: 'Volume', fmt: 'bool' },
    { label: 'LogR', key: 'log_return', cat: 'Structure', fmt: 'pct' },
    { label: 'MAStk', key: 'ma_stack', cat: 'Trend', fmt: 'num' },
    { label: 'MAS20', key: 'ma_slope_20', cat: 'Trend', fmt: 'num4' },
    { label: 'MAS50', key: 'ma_slope_50', cat: 'Trend', fmt: 'num4' },
    { label: 'MAS200', key: 'ma_slope_200', cat: 'Trend', fmt: 'num4' },
    { label: 'RSIDv', key: 'rsi_divergence', cat: 'Momentum', fmt: 'num' },
    { label: 'Beta20', key: 'beta_20d', cat: 'Relative', fmt: 'num2' },
    { label: 'Beta60', key: 'beta_60d', cat: 'Relative', fmt: 'num2' },
    { label: 'Alpha', key: 'alpha', cat: 'Relative', fmt: 'pct' },
    { label: 'RS20', key: 'rs_spy_20d', cat: 'Relative', fmt: 'pct' },
    { label: 'RS60', key: 'rs_spy_60d', cat: 'Relative', fmt: 'pct' },
    { label: 'Corr', key: 'corr_spy', cat: 'Relative', fmt: 'num2' },
    { label: 'R126d', key: 'return_126', cat: 'Structure', fmt: 'pct' },
    { label: 'R252d', key: 'return_252', cat: 'Structure', fmt: 'pct' },
  ];
  var IND_ALL = IND_DEFS.concat(IND_DEFS_EXTRA);
  var IND_CATS = ['All', 'Trend', 'Momentum', 'Volatility', 'Volume', 'Structure', 'Relative'];

  /* ── Glossary lookup: model key → glossary entry id ── */
  var GLOSSARY_ID_MAP = {
    'cmf_20': 'cmf', 'mfi_14': 'mfi',
    'force_index_13': 'force_index', 'eom_14': 'eom', 'obv_slope_20': 'obv_slope',
    'adx_14': 'adx', 'di_plus_14': 'di_plus', 'di_minus_14': 'di_minus',
    'aroon_up_25': 'aroon_up', 'aroon_down_25': 'aroon_down', 'aroon_osc_25': 'aroon_osc',
    'chop_14': 'chop', 'roc_12': 'roc', 'trix_15': 'trix',
    'stoch_k_14': 'stoch_k', 'stoch_d_3': 'stoch_d', 'stoch_rsi_14': 'stoch_rsi',
    'williams_r_14': 'williams_r', 'cci_20': 'cci', 'tsi_25_13': 'tsi',
    'cmo_14': 'cmo', 'keltner_middle': 'keltner_mid',
    'rolling_std_20': 'std_dev', 'wma_20': 'wma', 'kama_10': 'kama',
    'linreg_slope_20': 'linreg_slope', 'pivot_high': 'pivot_points',
    'pivot_low': 'pivot_points',
    'ma_slope_20': 'ma_slope', 'ma_slope_50': 'ma_slope', 'ma_slope_200': 'ma_slope',
    'rs_spy_20d': 'rs_spy', 'rs_spy_60d': 'rs_spy',
    'avg_dollar_volume_20': 'avg_dollar_volume',
    'donchian_middle': 'donchian_middle',
    'linreg_channel_upper': 'linreg_channel',
    'linreg_channel_middle': 'linreg_channel',
    'linreg_channel_lower': 'linreg_channel',
  };
  function gidForKey(key) { return GLOSSARY_ID_MAP[key] || key; }

  /* ── Indicators tab ── */
  function renderIndicators(container) {
    var cat = state.indCat || 'All';
    var catsHtml = '<div class="lw-ind-cats" id="lw-ind-cats">' +
      IND_CATS.map(function (c) { return '<button class="lw-ind-cat' + (c === cat ? ' is-active' : '') + '" data-cat="' + c + '">' + c + '</button>'; }).join('') +
      '</div>';
    container.innerHTML = '<div class="lw-loading">Loading indicators…</div>';

    api('/bars/symbols').then(function (list) {
      list = list || [];
      if (!list.length) {
        container.innerHTML = catsHtml + '<div class="lw-empty">No symbols in lake</div>';
        return;
      }
      var promises = list.map(function (item) {
        var sym = item.symbol || item.security_id;
        return barApi('/bars/summary', sym).then(function (s) {
          s._sym = sym;
          s._name = item.name || '';
          return s;
        }).catch(function () { return null; });
      });
      Promise.all(promises).then(function (results) {
        results = results.filter(function (r) { return r !== null; });
        var h = catsHtml;
        if (!results.length) {
          h += '<div class="lw-empty">No indicator data available</div>';
        } else {
          h += '<div class="lw-sym-grid">';
          results.forEach(function (s) { h += indicatorCard(s, cat); });
          h += '</div>';
        }
        container.innerHTML = h;
        /* bind category clicks */
        container.querySelectorAll('.lw-ind-cat').forEach(function (b) {
          b.addEventListener('click', function () {
            state.indCat = b.dataset.cat;
            renderIndicators(container);
          });
        });
        bindPins(container);
        bindHoverTooltip(container);
      });
    }).catch(function () {
      container.innerHTML = catsHtml + '<div class="lw-error">Failed to load symbols</div>';
    });
  }

  function indicatorCard(s, cat) {
    var stale = false;
    if (s.latest_date) {
      var ref = state.asOf ? new Date(state.asOf) : new Date();
      var daysAgo = (ref.getTime() - new Date(s.latest_date).getTime()) / 86400000;
      stale = daysAgo > 3;
    }
    var staleCls = stale ? ' lw-stale' : '';
    var staleBadge = stale ? '<span class="lw-stale-badge">stale</span>' : '';
    var chgCls = (s.change_pct || 0) >= 0 ? 'lw-c-up' : 'lw-c-down';
    var chgSign = (s.change_pct || 0) >= 0 ? '+' : '';
    var agoTxt = s.latest_date ? ago(s.latest_date) : '—';

    /* filter for this category + pinned */
    var sym = s.symbol || '';
    var pins = getPins(sym);
    var showAll = cat === 'All';
    var eligible = IND_ALL.filter(function (d) { return showAll || d.cat === cat; });

    /* pinned tiles — shown first regardless of category */
    var pinnedDefs = IND_ALL.filter(function (d) { return pins.indexOf(d.label) !== -1; });
    var catDefs = eligible.filter(function (d) { return pins.indexOf(d.label) === -1; });
    /* limit to 4 rows × 6 cols = 24 max */
    var displayDefs = catDefs.slice(0, 24);

    function buildTile(d) {
      var raw = s[d.key];
      var val = fmtIndVal(raw, d.fmt);
      var xtra = '';
      if (d.key === 'rsi' && raw != null) { xtra = raw > 70 ? ' lw-c-down' : raw < 30 ? ' lw-c-up' : ''; }
      else if (raw != null && (d.fmt === 'pct' || d.key.indexOf('return_') === 0 || d.key.indexOf('macd') === 0)) {
        xtra = raw >= 0 ? ' lw-c-up' : ' lw-c-down';
      }
      var pinned = pins.indexOf(d.label) !== -1;
      var gid = gidForKey(d.key);
      return '<div class="lw-ind-tile' + (pinned ? ' lw-ind-pinned' : '') + xtra + '" data-label="' + d.label + '" data-sym="' + sym + '" data-gid="' + gid + '">' +
        '<div class="lw-ind-tile-label"><span class="lw-ind-pin">' + (pinned ? '\u2605' : '\u2606') + '</span>' + esc(d.label) + '</div>' +
        '<div class="lw-ind-tile-val">' + val + '</div></div>';
    }

    var gridTiles = (pinnedDefs.map(buildTile).join('') + displayDefs.map(buildTile).join('')) || '<div class="lw-dim" style="padding:20px;text-align:center;grid-column:1/-1;">No indicators in this category</div>';

    return '<div class="lw-sym-card' + staleCls + '">' +
      '<div class="lw-ind-head">' +
        '<div style="display:flex;align-items:center;gap:8px;">' +
          '<span class="lw-card-title">' + esc(sym) + '</span>' +
          (s.name ? '<span class="lw-dim" style="font-size:11px;">' + esc(s.name) + '</span>' : '') +
          staleBadge +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:12px;">' +
          '<span class="lw-mono" style="font-weight:600;">' + fmtMoney(s.last) + '</span>' +
          '<span class="' + chgCls + '" style="font-size:12px;">' + chgSign + (s.change_pct || 0).toFixed(2) + '%</span>' +
          '<span class="lw-dim" style="font-size:11px;">' + esc(s.latest_date || '') + ' · ' + agoTxt + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="lw-ind-pinned-section" id="lw-pins-' + sym + '"><div class="lw-ind-grid">' + gridTiles + '</div></div>' +
    '</div>';
  }

  /* ── Pin helpers ── */
  function getPins(sym) {
    try {
      var all = JSON.parse(localStorage.getItem('lw_ind_pins') || '{}');
      return all[sym] || [];
    } catch (e) { return []; }
  }
  function setPins(sym, arr) {
    try {
      var all = JSON.parse(localStorage.getItem('lw_ind_pins') || '{}');
      all[sym] = arr;
      localStorage.setItem('lw_ind_pins', JSON.stringify(all));
    } catch (e) {}
  }

  /* ── Bind pin clicks (called after render) ── */
  function bindPins(container) {
    container.querySelectorAll('.lw-ind-tile').forEach(function (tile) {
      tile.addEventListener('click', function () {
        var sym = tile.dataset.sym;
        var label = tile.dataset.label;
        if (!sym || !label) return;
        var pins = getPins(sym);
        var idx = pins.indexOf(label);
        if (idx === -1) { pins.push(label); } else { pins.splice(idx, 1); }
        setPins(sym, pins);
        renderIndicators(container);
      });
    });
  }

  /* ── Glossary tooltip ── */
  var _glossaryPromise = null;
  var _glossaryCache = null;
  var _tooltipEl = null;
  var _hoveredGid = null;

  function getTooltip() {
    if (!_tooltipEl) {
      _tooltipEl = document.createElement('div');
      _tooltipEl.className = 'lw-gloss-tip';
      _tooltipEl.style.display = 'none';
      document.body.appendChild(_tooltipEl);
    }
    return _tooltipEl;
  }

  function fetchGlossary() {
    if (_glossaryCache) return Promise.resolve(_glossaryCache);
    if (!_glossaryPromise) {
      _glossaryPromise = api('/indicators/glossary').then(function (data) {
        _glossaryCache = data || {};
        return _glossaryCache;
      }).catch(function () { _glossaryCache = {}; return _glossaryCache; });
    }
    return _glossaryPromise;
  }

  function bindHoverTooltip(container) {
    container.querySelectorAll('.lw-ind-tile').forEach(function (tile) {
      tile.addEventListener('mouseenter', function () {
        var gid = tile.dataset.gid;
        if (!gid) return;
        _hoveredGid = gid;
        var _tile = tile;
        fetchGlossary().then(function (glossary) {
          if (_hoveredGid !== gid) return;
          var entry = glossary[gid];
          if (!entry) return;
          var tip = getTooltip();
          tip.innerHTML = '<div class="lw-gloss-tip-name">' + esc(entry.full_name || entry.name || gid) + '</div>' +
            '<div class="lw-gloss-tip-desc">' + esc(entry.description || '') + '</div>' +
            (entry.formula ? '<div class="lw-gloss-tip-formula">' + esc(entry.formula) + '</div>' : '');
          var rect = _tile.getBoundingClientRect();
          tip.style.left = Math.min(rect.left + rect.width / 2 - 140, window.innerWidth - 300) + 'px';
          tip.style.top = (rect.bottom + 6) + 'px';
          tip.style.display = 'block';
        });
      });
      tile.addEventListener('mouseleave', function () {
        _hoveredGid = null;
        var tip = getTooltip();
        tip.style.display = 'none';
      });
    });
  }

  function fmtIndVal(val, type) {
    if (val == null) return '—';
    if (type === 'bool') return val ? '<span style="color:var(--lw-money);font-weight:700;">yes</span>' : '<span style="color:var(--lw-ink-4);">no</span>';
    if (type === 'pct') return (val >= 0 ? '+' : '') + (val * 100).toFixed(2) + '%';
    if (type === 'price') return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (type === 'big') return fmtRows(val);
    if (type === 'num2') return Number(val).toFixed(2);
    if (type === 'num3') return Number(val).toFixed(3);
    if (type === 'num4') return Number(val).toFixed(4);
    return Number(val).toFixed(1);
  }

  /* ── Securities ── */
  /* ── Securities ── */
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
      /* list_snapshots() returns snapshot_id / timestamp / changes — no row count */
      var h = '<div class="lw-cat-list"><div class="lw-cat-cols" style="grid-template-columns:1.6fr 1.4fr 1fr;"><span>Snapshot</span><span>Timestamp</span><span style="text-align:right;">Changes</span></div>';
      list.slice(0, 15).forEach(function (s) {
        h += '<div class="lw-cat-row" style="grid-template-columns:1.6fr 1.4fr 1fr;"><span class="lw-cat-ds"><span class="lw-dot" style="background:var(--lw-snap);"></span><span class="lw-cat-name">' + esc(s.snapshot_id || s.id || '—') + '</span></span><span class="lw-mono" style="font-size:11px;color:var(--lw-ink-3);">' + esc(s.timestamp || '—') + '</span><span class="lw-mono" style="font-size:10px;color:var(--lw-ink-3);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(s.changes || '—') + '</span></div>';
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

    /* register the service worker (was never registered before, so the PWA
       layer and offline cache did nothing). Secure-context only; failures are
       non-fatal. */
    if ('serviceWorker' in navigator) {
      try { navigator.serviceWorker.register('/service-worker.js').catch(function () {}); } catch (e) {}
    }

    showTab('overview');
  });
})();
