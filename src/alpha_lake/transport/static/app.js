/* Lake Watch — data-validation dashboard */
(function () {
  'use strict';

  const API = '/v1/dashboard';
  const WATCHLIST = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA'];
  const state = { asOf: null, snapshotId: '', priceMode: 'raw', tab: 'overview', symbol: '', dataset: '', loading: false };

  /* ── API ── */
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
  function html(str) { var d = document.createElement('div'); d.innerHTML = str; return d.firstElementChild; }

  /* ── Formatters ── */
  function fmtDate(iso) { if (!iso) return '—'; return new Date(iso).toLocaleDateString(); }
  function fmtNum(n) { if (n == null) return '—'; return Number(n).toLocaleString(); }
  function fmtFloat(n) { if (n == null) return '—'; return Number(n).toFixed(2); }
  function ago(iso) { if (!iso) return '—'; var d = new Date(iso); var s = Math.floor((Date.now() - d) / 1000); if (s < 60) return s + 's'; if (s < 3600) return Math.floor(s / 60) + 'm'; if (s < 86400) return Math.floor(s / 3600) + 'h'; return Math.floor(s / 86400) + 'd'; }

  /* ── SVG Charts ── */
  function sparkline(data, w, h) {
    if (!data || data.length < 2) return '';
    var mn = Math.min.apply(null, data), mx = Math.max.apply(null, data);
    var rng = mx - mn || 1;
    var pts = data.map(function (v, i) { return (i / (data.length - 1)) * w + ',' + (h - ((v - mn) / rng) * (h - 2) - 1); }).join(' ');
    return '<svg class="sparkline" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><polyline points="' + pts + '" fill="none" stroke="' + (data[data.length - 1] >= data[0] ? 'var(--green)' : 'var(--red)') + '" stroke-width="1.5"/></svg>';
  }

  function lineChart(bars, ind, w, h) {
    if (!bars || bars.length < 2) return '<div class="empty">Not enough data</div>';
    var closes = bars.map(function (b) { return b.close; });
    var dates = bars.map(function (b) { return b.effective_date; });
    var mn = Math.min.apply(null, closes), mx = Math.max.apply(null, closes);
    var pad = (mx - mn) * 0.05 || 1;
    var rng = mx - mn + pad * 2;
    var cPad = 50, rPad = 20, cw = w - cPad - rPad, ch = h - 30 - 10;
    function x(i) { return cPad + (i / (bars.length - 1)) * cw; }
    function y(v) { return 10 + ch - ((v - mn + pad) / rng) * ch; }
    var path = closes.map(function (v, i) { return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v).toFixed(1); }).join('');
    var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;height:auto;background:var(--surface);border-radius:8px;">';
    svg += '<path d="' + path + '" fill="none" stroke="var(--blue)" stroke-width="2"/>';
    /* gridlines */
    for (var g = 0; g <= 4; g++) { var gy = 10 + (ch / 4) * g; svg += '<line x1="' + cPad + '" y1="' + gy + '" x2="' + (cw + cPad) + '" y2="' + gy + '" stroke="var(--border)" stroke-width="0.5"/><text x="' + (cPad - 4) + '" y="' + (gy + 3) + '" text-anchor="end" fill="var(--text2)" font-size="10">' + fmtFloat(mn - pad + (rng / 4) * (4 - g)) + '</text>'; }
    /* x labels */
    var step = Math.max(1, Math.floor(bars.length / 6));
    for (var li = 0; li < bars.length; li += step) { svg += '<text x="' + x(li) + '" y="' + (h - 4) + '" text-anchor="middle" fill="var(--text2)" font-size="9">' + dates[li].slice(5) + '</text>'; }
    /* indicator overlays */
    if (ind) {
      Object.keys(ind).forEach(function (k) {
        var arr = ind[k]; if (!arr || arr.length < 2) return;
        var p = arr.map(function (v, i) { if (v == null) return ''; return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v).toFixed(1); }).filter(Boolean).join('');
        svg += '<path d="' + p + '" fill="none" stroke="var(--amber)" stroke-width="1" stroke-dasharray="4,2" opacity="0.7"/>';
      });
    }
    svg += '</svg>';
    return svg;
  }

  /* ── Ticker pill ── */
  function tickerPill(sym, cls) {
    var g = sym[0] || '?';
    return '<span class="ticker-pill' + (cls ? ' ' + cls : '') + '" data-symbol="' + sym + '"><span class="ticker-mono">' + g + '</span>' + sym + '</span>';
  }

  /* ── iOS cell ── */
  function iosCell(label, value, detail) {
    var id = 'cell-' + Math.random().toString(36).slice(2, 8);
    var d = detail ? '<div class="cell-detail">' + detail + '</div>' : '';
    return '<div class="cell" onclick="document.getElementById(\'' + id + '\').classList.toggle(\'expanded\')" id="' + id + '"><span class="cell-label">' + label + '</span><span class="cell-value">' + value + '</span><span class="cell-chevron">›</span></div>' + d;
  }

  /* ── Tab routing ── */
  function showTab(name) {
    state.tab = name;
    $$('.tab').forEach(function (t) { return t.classList.toggle('active', t.dataset.tab === name); });
    var content = $('#content');
    content.innerHTML = '<div class="empty">Loading…</div>';
    switch (name) {
      case 'overview': renderOverview(content); break;
      case 'bars': renderBars(content); break;
      case 'datasets': renderDatasets(content); break;
      case 'securities': renderSecurities(content); break;
      case 'pit': renderPit(content); break;
    }
  }

  /* ── Overview tab ── */
  function renderOverview(container) {
    var healthHtml = '<div class="card"><div class="card-title">Catalog Health</div><div id="healthContent" class="empty">Loading…</div></div>';
    var gridHtml = '<div class="grid" id="dsGrid"></div>';
    container.innerHTML = healthHtml + gridHtml;

    api('/health').then(function (h) {
      $('#healthContent').innerHTML = 'Snapshots: <strong>' + h.snapshots + '</strong> &middot; Latest: <strong>' + (h.latest_snapshot_id || '—') + '</strong>';
    }).catch(function () { $('#healthContent').innerHTML = 'Failed to load health'; });

    api('/datasets').then(function (data) {
      var g = $('#dsGrid');
      data.forEach(function (ds) {
        var tier = ds.tier || 'experimental';
        var rows = ds.rows || 0;
        var dot = rows > 0 ? 'green' : (ds.supported ? 'amber' : 'red');
        var staleness = ds.latest_effective_date ? ago(ds.latest_effective_date) : '—';
        g.innerHTML += '<div class="card" onclick="showTab(\'datasets\');setTimeout(function(){document.querySelector(\'#dsPicker\').value=\'' + ds.dataset + '\';renderDatasetDetail(\'' + ds.dataset + '\')},100)"><div class="card-title"><span class="dot ' + dot + '"></span>' + ds.dataset + ' <span class="badge ' + tier + '">' + tier + '</span></div><div class="card-value">' + fmtNum(rows) + ' rows</div><div style="font-size:12px;color:var(--text2);">latest: ' + ds.latest_effective_date + ' (' + staleness + ' ago)</div></div>';
      });
    }).catch(function () { $('#dsGrid').innerHTML = '<div class="error">Failed to load datasets</div>'; });
  }

  /* ── Bars tab ── */
  function renderBars(container) {
    container.innerHTML = '<div class="bar-search"><input type="text" id="barSymbol" placeholder="Search symbol..." value="' + state.symbol + '"></div><div id="barChart" class="empty">Search a symbol above</div><div id="barIndToggles"></div><div id="watchlistStrip"></div>';

    /* Watchlist */
    api('/securities?q=' + WATCHLIST[0] + '&limit=30').then(function () {
      var strip = $('#watchlistStrip');
      WATCHLIST.forEach(function (sym) {
        barApi('/bars', sym).then(function (bars) {
          if (!bars || bars.length === 0) return;
          var closes = bars.map(function (b) { return b.close; });
          var pill = html(tickerPill(sym));
          pill.innerHTML += sparkline(closes, 60, 20);
          pill.addEventListener('click', function () { state.symbol = sym; $('#barSymbol').value = sym; loadBarsChart(sym); });
          strip.appendChild(pill);
        }).catch(function () {});
      });
    }).catch(function () {});

    /* Symbol autocomplete */
    var input = $('#barSymbol');
    input.addEventListener('input', function () {
      var q = input.value.toUpperCase();
      if (q.length < 1) return;
      state.symbol = q;
      api('/securities?q=' + q + '&limit=8').then(function (results) {
        if (!results || results.length === 0) return;
        var found = results.find(function (r) { return r.symbol === q; });
        if (found) { loadBarsChart(q); }
      }).catch(function () {});
    });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = input.value.toUpperCase(); loadBarsChart(state.symbol); } });
    if (state.symbol) { loadBarsChart(state.symbol); }
  }

  function loadBarsChart(sym) {
    var chart = $('#barChart');
    chart.innerHTML = '<div class="empty">Loading ' + sym + '…</div>';
    var end = new Date(); var start = new Date(end); start.setFullYear(start.getFullYear() - 1);
    var sp = start.toISOString().slice(0, 10), ep = end.toISOString().slice(0, 10);
    barApi('/bars/indicators?indicators=sma:50,rsi:14', sym, sp, ep).then(function (res) {
      if (!res || !res.close || res.close.length === 0) { chart.innerHTML = '<div class="empty">No data for ' + sym + '</div>'; return; }
      var bars = res.close.map(function (c, i) { return { close: c, effective_date: res.effective_date[i] }; });
      var ind = {};
      if (res.sma) ind['SMA 50'] = res.sma;
      chart.innerHTML = lineChart(bars, ind, 800, 300);
      /* RSI indicator */
      if (res.rsi) {
        var rsiDiv = html('<div class="card"><div class="card-title">RSI (14)</div>' + sparkline(res.rsi, 200, 40) + ' <span style="font-size:12px;color:var(--text2);">Current: ' + fmtFloat(res.rsi[res.rsi.length - 1]) + '</span></div>');
        chart.parentNode.appendChild(rsiDiv);
      }
    }).catch(function () { chart.innerHTML = '<div class="error">Failed to load bars</div>'; });
  }

  /* ── Datasets tab ── */
  function renderDatasets(container) {
    container.innerHTML = '<div class="card"><div class="card-title">Select dataset</div><select id="dsPicker" style="width:100%;padding:8px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;font-size:14px;"><option value="">— choose —</option></select></div><div id="dsContent"></div>';
    api('/datasets').then(function (list) {
      var picker = $('#dsPicker');
      list.forEach(function (ds) { var opt = document.createElement('option'); opt.value = ds.dataset; opt.textContent = ds.dataset + ' (' + fmtNum(ds.rows) + ' rows)'; picker.appendChild(opt); });
      picker.addEventListener('change', function () { state.dataset = picker.value; renderDatasetDetail(picker.value); });
      if (state.dataset) { picker.value = state.dataset; renderDatasetDetail(state.dataset); }
    }).catch(function () {});
  }

  function renderDatasetDetail(name) {
    var content = $('#dsContent');
    if (!name) { content.innerHTML = ''; return; }
    content.innerHTML = '<div class="empty">Loading ' + name + '…</div>';
    api('/dataset/' + name + '?limit=50').then(function (res) {
      if (!res.rows || res.rows.length === 0) { content.innerHTML = '<div class="empty">No rows in ' + name + '</div>'; return; }
      var cols = ['effective_date', 'available_at', 'source_id', 'quality_status', 'version_hash'];
      var extra = res.columns.filter(function (c) { return cols.indexOf(c) === -1; }).slice(0, 6);
      var showCols = cols.concat(extra);
      var html = '<div class="card" style="overflow-x:auto;"><table><thead><tr>' + showCols.map(function (c) { return '<th>' + c + '</th>'; }).join('') + '</tr></thead><tbody>';
      res.rows.slice(0, 30).forEach(function (r) {
        html += '<tr>' + showCols.map(function (c) { var v = r[c]; return '<td>' + (v == null ? '—' : String(v).slice(0, 30)) + '</td>'; }).join('') + '</tr>';
      });
      html += '</tbody></table></div><div style="font-size:11px;color:var(--text2);text-align:right;">fetched at ' + res.fetched_at + '</div>';
      content.innerHTML = html;
    }).catch(function () { content.innerHTML = '<div class="error">Failed to load ' + name + '</div>'; });
  }

  /* ── Securities tab ── */
  function renderSecurities(container) {
    container.innerHTML = '<div class="bar-search"><input type="text" id="secSearch" placeholder="Search symbol..." value="' + state.symbol + '"></div><div id="secResults"></div>';
    var input = $('#secSearch');
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { state.symbol = input.value.toUpperCase(); loadSecurity(state.symbol); }
    });
    if (state.symbol) { loadSecurity(state.symbol); }
  }

  function loadSecurity(sym) {
    var container = $('#secResults');
    container.innerHTML = '<div class="empty">Loading ' + sym + '…</div>';
    api('/security/' + sym).then(function (agg) {
      var html = '<div class="card"><div class="card-title">' + sym + ' <span style="font-size:12px;color:var(--text2);">' + agg.security_id + '</span></div><div style="font-size:12px;color:var(--text2);">as_of: ' + agg.as_of + '</div></div>';
      Object.keys(agg.datasets).forEach(function (ds) {
        var rows = agg.datasets[ds];
        html += '<div class="card"><div class="card-title">' + ds + ' <span style="font-size:11px;color:var(--text2);">' + rows.length + ' rows</span></div>';
        rows.slice(0, 5).forEach(function (r) {
          var src = r.source_id || '—';
          var avail = r.available_at ? String(r.available_at).slice(0, 19) : '—';
          var qs = r.quality_status || '—';
          html += iosCell(src + ' @ ' + avail, qs, JSON.stringify(r, null, 2).slice(0, 200));
        });
        html += '</div>';
      });
      container.innerHTML = html;
    }).catch(function () { container.innerHTML = '<div class="error">Symbol not found or failed to load</div>'; });
  }

  /* ── PIT / Snapshots tab ── */
  function renderPit(container) {
    container.innerHTML = '<div class="card"><div class="card-title">Point-in-Time Playground</div><p style="font-size:13px;color:var(--text2);margin-bottom:8px;">Move the <strong>as_of</strong> slider in the header to see how data changes when you rewind knowledge-time. Each read is bounded by <code>available_at &le; as_of</code> — no future revisions leak into past views.</p></div><div class="card"><div class="card-title">Try This</div><div id="pitPresets"></div></div><div id="pitSnapshots"></div>';

    api('/snapshots').then(function (list) {
      if (!list || list.length === 0) return;
      var html = '<div class="card"><div class="card-title">Snapshots</div><table><thead><tr><th>Snapshot</th><th>Timestamp</th></tr></thead><tbody>';
      list.slice(0, 20).forEach(function (s) {
        html += '<tr><td>' + (s.snapshot_id || s.id || '—') + '</td><td>' + (s.timestamp || '—') + '</td></tr>';
      });
      html += '</tbody></table></div>';
      $('#pitSnapshots').innerHTML = html;
    }).catch(function () {});

    var presets = $('#pitPresets');
    var now = new Date();
    var presetsList = [
      { label: 'Rewind 7 days', days: 7 },
      { label: 'Rewind 30 days', days: 30 },
      { label: 'Rewind 90 days', days: 90 },
    ];
    presetsList.forEach(function (p) {
      var btn = document.createElement('button');
      btn.textContent = p.label;
      btn.style.cssText = 'margin:4px;padding:6px 12px;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;font-size:13px;cursor:pointer;';
      btn.addEventListener('click', function () {
        var d = new Date(now); d.setDate(d.getDate() - p.days);
        var input = $('#asOfInput');
        if (input) { input.value = d.toISOString().slice(0, 16); input.dispatchEvent(new Event('change')); }
      });
      presets.appendChild(btn);
    });
  }

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded', function () {
    /* Tabs */
    $$('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () { showTab(tab.dataset.tab); });
    });

    /* as_of */
    var asOfInput = $('#asOfInput');
    if (asOfInput) {
      var n = new Date(); n.setSeconds(0, 0);
      asOfInput.value = n.toISOString().slice(0, 16);
      asOfInput.addEventListener('change', function () {
        state.asOf = asOfInput.value ? new Date(asOfInput.value).toISOString() : null;
        showTab($('.tab.active').dataset.tab);
      });
    }

    /* Snapshot dropdown */
    var snap = $('#snapshotSelect');
    if (snap) {
      api('/snapshots').then(function (list) {
        list.forEach(function (s) {
          var opt = document.createElement('option');
          opt.value = s.snapshot_id || s.id || '';
          opt.textContent = s.snapshot_id || s.id || '';
          snap.appendChild(opt);
        });
      }).catch(function () {});
      snap.addEventListener('change', function () { state.snapshotId = snap.value; showTab($('.tab.active').dataset.tab); });
    }

    /* Price mode */
    var pm = $('#priceModeSelect');
    if (pm) {
      pm.addEventListener('change', function () { state.priceMode = pm.value; if (state.tab === 'bars') showTab('bars'); });
    }

    showTab('overview');
  });
})();
