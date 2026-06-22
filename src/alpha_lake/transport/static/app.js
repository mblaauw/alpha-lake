/* Lake Watch — warm-tone newsroom-style dashboard */
(function () {
  'use strict';

  const API = '/v1/dashboard';
  const WATCHLIST = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA'];
  const state = { asOf: null, snapshotId: '', priceMode: 'raw', tab: 'overview', symbol: '', dataset: '' };

  /* ── Theme ── */
  var themePref = (function () { try { return localStorage.getItem('lw_theme') || 'dark'; } catch (e) { return 'dark'; } })();
  function applyTheme(pref) { document.documentElement.dataset.theme = pref; themePref = pref; try { localStorage.setItem('lw_theme', pref); } catch (e) {} $$('.lw-theme-btn').forEach(function (b) { b.classList.toggle('is-active', b.dataset.theme === pref); }); }
  applyTheme(themePref);

  /* ── Helpers ── */
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
  function fmtDate(iso) { if (!iso) return '—'; return new Date(iso).toLocaleDateString(); }
  function fmtNum(n) { if (n == null) return '—'; return Number(n).toLocaleString(); }
  function ago(iso) { if (!iso) return '—'; var d = new Date(iso); var s = Math.floor((Date.now() - d) / 1000); if (s < 60) return s + 's'; if (s < 3600) return Math.floor(s / 60) + 'm'; if (s < 86400) return Math.floor(s / 3600) + 'h'; return Math.floor(s / 86400) + 'd'; }

  /* ── Sparkline SVG ── */
  function sparkline(data, w, h) {
    if (!data || data.length < 2) return '';
    var mn = Math.min.apply(null, data), mx = Math.max.apply(null, data);
    var rng = mx - mn || 1;
    var pts = data.map(function (v, i) { return (i / (data.length - 1)) * w + ',' + (h - ((v - mn) / rng) * (h - 2) - 1); }).join(' ');
    return '<svg class="lw-sparkline" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><polyline points="' + pts + '" fill="none" stroke="' + (data[data.length - 1] >= data[0] ? 'var(--lw-up)' : 'var(--lw-down)') + '" stroke-width="1.5"/></svg>';
  }

  /* ── Line chart SVG ── */
  function lineChart(bars, ind, w, h) {
    if (!bars || bars.length < 2) return '<div class="lw-empty">Not enough data</div>';
    var closes = bars.map(function (b) { return b.close; });
    var dates = bars.map(function (b) { return b.effective_date; });
    var mn = Math.min.apply(null, closes), mx = Math.max.apply(null, closes);
    var pad = (mx - mn) * 0.05 || 1;
    var rng = mx - mn + pad * 2;
    var cP = 50, rP = 20, cw = w - cP - rP, ch = h - 30 - 10;
    function x(i) { return cP + (i / (bars.length - 1)) * cw; }
    function y(v) { return 10 + ch - ((v - mn + pad) / rng) * ch; }
    var path = closes.map(function (v, i) { return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v).toFixed(1); }).join('');
    var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;height:auto;background:var(--lw-bg-2);border-radius:6px;">';
    svg += '<path d="' + path + '" fill="none" stroke="var(--lw-money)" stroke-width="2"/>';
    for (var g = 0; g <= 4; g++) { var gy = 10 + (ch / 4) * g; svg += '<line x1="' + cP + '" y1="' + gy + '" x2="' + (cw + cP) + '" y2="' + gy + '" stroke="var(--lw-rule)" stroke-width="0.5"/><text x="' + (cP - 4) + '" y="' + (gy + 3) + '" text-anchor="end" fill="var(--lw-ink-3)" font-size="10">' + (mn - pad + (rng / 4) * (4 - g)).toFixed(0) + '</text>'; }
    var step = Math.max(1, Math.floor(bars.length / 6));
    for (var li = 0; li < bars.length; li += step) { svg += '<text x="' + x(li) + '" y="' + (h - 4) + '" text-anchor="middle" fill="var(--lw-ink-3)" font-size="9">' + dates[li].slice(5) + '</text>'; }
    if (ind) {
      Object.keys(ind).forEach(function (k) {
        var arr = ind[k]; if (!arr || arr.length < 2) return;
        var p = arr.map(function (v, i) { if (v == null) return ''; return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v).toFixed(1); }).filter(Boolean).join('');
        svg += '<path d="' + p + '" fill="none" stroke="var(--lw-accent)" stroke-width="1" stroke-dasharray="4,2" opacity="0.7"/>';
      });
    }
    svg += '</svg>';
    return svg;
  }

  /* ── Tab routing ── */
  function showTab(name) {
    state.tab = name;
    $$('.lw-tab').forEach(function (t) { return t.classList.toggle('is-active', t.dataset.tab === name); });
    var content = $('#lw-content');
    content.innerHTML = '<div class="lw-loading">Loading</div>';
    switch (name) {
      case 'overview': renderOverview(content); break;
      case 'bars': renderBars(content); break;
      case 'datasets': renderDatasets(content); break;
      case 'securities': renderSecurities(content); break;
      case 'pit': renderPit(content); break;
    }
  }

  /* ── Overview ── */
  function renderOverview(container) {
    var healthHtml = '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-bottom:12px;"><div class="lw-card-title">Catalog Health <span id="lw-health-summary" class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">Loading…</span></div></div>';
    var gridHtml = '<div class="lw-health-grid" id="lw-ds-grid"></div>';
    container.innerHTML = healthHtml + gridHtml;

    api('/health').then(function (h) {
      $('#lw-health-summary').innerHTML = h.snapshots + ' snapshots &middot; latest: ' + (h.latest_snapshot_id || '—');
    }).catch(function () { $('#lw-health-summary').innerHTML = 'Failed to load'; });

    api('/datasets').then(function (data) {
      var g = $('#lw-ds-grid');
      data.forEach(function (ds) {
        var tier = ds.tier || 'experimental';
        var rows = ds.rows || 0;
        var dot = rows > 0 ? 'green' : (ds.supported ? 'amber' : 'red');
        var staleness = ds.latest_effective_date ? ago(ds.latest_effective_date) : '—';
        g.innerHTML += '<div class="lw-health-card" onclick="window.lwGoDataset && window.lwGoDataset(\'' + ds.dataset + '\')"><div class="lw-card-title"><span class="lw-dot lw-dot-' + dot + '"></span>' + ds.dataset + ' <span class="lw-pill lw-pill-' + tier + '">' + tier + '</span></div><div class="lw-card-value">' + fmtNum(rows) + '</div><div class="lw-card-sub">latest: ' + ds.latest_effective_date + ' (' + staleness + ' ago)</div></div>';
      });
    }).catch(function () { $('#lw-ds-grid').innerHTML = '<div class="lw-error">Failed to load</div>'; });
  }

  window.lwGoDataset = function (name) {
    state.dataset = name;
    showTab('datasets');
    setTimeout(function () {
      var picker = $('#lw-ds-picker');
      if (picker) { picker.value = name; renderDatasetDetail(name); }
    }, 100);
  };

  /* ── Bars ── */
  function renderBars(container) {
    container.innerHTML = '<div class="lw-search"><input type="text" id="lw-bar-symbol" placeholder="Search symbol…" value="' + state.symbol + '"></div><div id="lw-chart" class="lw-empty">Search a symbol above</div><div id="lw-watchlist"></div>';
    api('/securities?q=' + WATCHLIST[0] + '&limit=30').then(function () {
      var strip = $('#lw-watchlist');
      WATCHLIST.forEach(function (sym) {
        barApi('/bars', sym).then(function (bars) {
          if (!bars || bars.length === 0) return;
          var closes = bars.map(function (b) { return b.close; });
          var pill = document.createElement('span');
          pill.className = 'lw-ticker-pill';
          pill.innerHTML = '<span class="lw-ticker-mono">' + sym[0] + '</span>' + sym + ' ' + sparkline(closes, 50, 16);
          pill.addEventListener('click', function () { state.symbol = sym; $('#lw-bar-symbol').value = sym; loadChart(sym); });
          strip.appendChild(pill);
        }).catch(function () {});
      });
    }).catch(function () {});
    $('#lw-bar-symbol').addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase(); loadChart(state.symbol); } });
    if (state.symbol) { loadChart(state.symbol); }
  }

  function loadChart(sym) {
    var chart = $('#lw-chart');
    chart.innerHTML = '<div class="lw-loading">Loading ' + sym + '</div>';
    var end = new Date(); var start = new Date(end); start.setFullYear(start.getFullYear() - 1);
    var sp = start.toISOString().slice(0, 10), ep = end.toISOString().slice(0, 10);
    barApi('/bars/indicators?indicators=sma:50,rsi:14', sym, sp, ep).then(function (res) {
      if (!res || !res.close || res.close.length === 0) { chart.innerHTML = '<div class="lw-empty">No data for ' + sym + '</div>'; return; }
      var bars = res.close.map(function (c, i) { return { close: c, effective_date: res.effective_date[i] }; });
      var ind = {};
      if (res.sma) ind['SMA 50'] = res.sma;
      chart.innerHTML = lineChart(bars, ind, 800, 300);
      if (res.rsi) {
        var rsiDiv = document.createElement('div');
        rsiDiv.className = 'lw-card';
        rsiDiv.style.cssText = 'border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-top:8px;';
        rsiDiv.innerHTML = '<div class="lw-card-title">RSI (14) <span class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">Current: ' + res.rsi[res.rsi.length - 1].toFixed(1) + '</span></div>' + sparkline(res.rsi, 300, 30);
        chart.parentNode.appendChild(rsiDiv);
      }
    }).catch(function () { chart.innerHTML = '<div class="lw-error">Failed to load</div>'; });
  }

  /* ── Datasets ── */
  function renderDatasets(container) {
    container.innerHTML = '<div class="lw-search" style="margin-bottom:8px;"><select id="lw-ds-picker" style="width:100%;padding:8px 12px;background:var(--lw-bg-2);color:var(--lw-ink);border:1px solid var(--lw-rule);border-radius:999px;font-family:var(--lw-mono);font-size:var(--lw-size-small);"><option value="">— Choose dataset —</option></select></div><div id="lw-ds-detail"></div>';
    api('/datasets').then(function (list) {
      var picker = $('#lw-ds-picker');
      list.forEach(function (ds) { var o = document.createElement('option'); o.value = ds.dataset; o.textContent = ds.dataset + ' (' + fmtNum(ds.rows) + ' rows)'; picker.appendChild(o); });
      picker.addEventListener('change', function () { state.dataset = picker.value; renderDatasetDetail(picker.value); });
      if (state.dataset) { picker.value = state.dataset; renderDatasetDetail(state.dataset); }
    }).catch(function () {});
  }

  function renderDatasetDetail(name) {
    var content = $('#lw-ds-detail');
    if (!name) { content.innerHTML = ''; return; }
    content.innerHTML = '<div class="lw-loading">Loading</div>';
    api('/dataset/' + name + '?limit=50').then(function (res) {
      if (!res.rows || res.rows.length === 0) { content.innerHTML = '<div class="lw-empty">No rows in ' + name + '</div>'; return; }
      var cols = ['effective_date', 'available_at', 'source_id', 'quality_status', 'version_hash'];
      var extra = res.columns.filter(function (c) { return cols.indexOf(c) === -1; }).slice(0, 5);
      var show = cols.concat(extra);
      var h = '<div class="lw-table-wrap"><table class="lw-table"><thead><tr>' + show.map(function (c) { return '<th>' + c + '</th>'; }).join('') + '</tr></thead><tbody>';
      res.rows.slice(0, 30).forEach(function (r) {
        h += '<tr>' + show.map(function (c) { var v = r[c]; return '<td>' + (v == null ? '—' : String(v).slice(0, 28)) + '</td>'; }).join('') + '</tr>';
      });
      h += '</tbody></table></div>';
      content.innerHTML = h;
    }).catch(function () { content.innerHTML = '<div class="lw-error">Failed to load</div>'; });
  }

  /* ── Securities ── */
  function renderSecurities(container) {
    container.innerHTML = '<div class="lw-search"><input type="text" id="lw-sec-search" placeholder="Search symbol…" value="' + state.symbol + '"></div><div id="lw-sec-detail"></div>';
    var input = $('#lw-sec-search');
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.symbol = e.target.value.toUpperCase(); loadSecurity(state.symbol); } });
    if (state.symbol) { loadSecurity(state.symbol); }
  }

  function loadSecurity(sym) {
    var content = $('#lw-sec-detail');
    content.innerHTML = '<div class="lw-loading">Loading</div>';
    api('/security/' + sym).then(function (agg) {
      var h = '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-bottom:8px;"><div class="lw-card-title">' + sym + ' <span class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">' + agg.security_id + '</span></div><div class="lw-card-sub">as_of: ' + agg.as_of + '</div></div>';
      Object.keys(agg.datasets).forEach(function (ds) {
        var rows = agg.datasets[ds];
        h += '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:12px;margin-bottom:6px;"><div class="lw-card-title">' + ds + ' <span class="lw-dim" style="font-weight:400;text-transform:none;letter-spacing:0;">' + rows.length + ' rows</span></div>';
        rows.slice(0, 5).forEach(function (r) {
          var src = r.source_id || '—';
          var avail = r.available_at ? String(r.available_at).slice(0, 19) : '—';
          var qs = r.quality_status || '—';
          h += '<div class="lw-li-summary" style="border-bottom:1px solid var(--lw-rule);padding:6px 0;font-size:var(--lw-size-small);"><span class="lw-li-label">' + src + ' @ ' + avail + '</span><span class="lw-li-value lw-mono">' + qs + '</span></div>';
        });
        h += '</div>';
      });
      content.innerHTML = h;
    }).catch(function () { content.innerHTML = '<div class="lw-error">Symbol not found</div>'; });
  }

  /* ── PIT ── */
  function renderPit(container) {
    container.innerHTML = '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:14px;margin-bottom:10px;"><div class="lw-card-title">Point-in-Time Playground</div><p style="font-size:var(--lw-size-small);color:var(--lw-ink-3);margin-top:6px;">Move <strong>as_of</strong> in the header to rewind knowledge-time. Each read is bounded by <code>available_at &le; as_of</code> — no future revisions leak into past views.</p></div><div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:14px;margin-bottom:10px;"><div class="lw-card-title">Try This</div><div class="lw-pit-presets" id="lw-pit-presets"></div></div><div id="lw-snapshots"></div>';

    api('/snapshots').then(function (list) {
      if (!list || list.length === 0) return;
      var h = '<div class="lw-card" style="border:1px solid var(--lw-rule);border-radius:8px;padding:14px;"><div class="lw-card-title">Snapshots</div><table class="lw-table"><thead><tr><th>Snapshot</th><th>Timestamp</th></tr></thead><tbody>';
      list.slice(0, 15).forEach(function (s) { h += '<tr><td class="lw-mono">' + (s.snapshot_id || s.id || '—') + '</td><td>' + (s.timestamp || '—') + '</td></tr>'; });
      h += '</tbody></table></div>';
      $('#lw-snapshots').innerHTML = h;
    }).catch(function () {});

    var presets = $('#lw-pit-presets');
    var now = new Date();
    [7, 30, 90].forEach(function (d) {
      var btn = document.createElement('button');
      btn.textContent = 'Rewind ' + d + ' days';
      btn.addEventListener('click', function () {
        var dt = new Date(now); dt.setDate(dt.getDate() - d);
        var input = $('#lw-asof');
        if (input) { input.value = dt.toISOString().slice(0, 16); input.dispatchEvent(new Event('change')); }
      });
      presets.appendChild(btn);
    });
  }

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded', function () {
    /* Tabs */
    $$('.lw-tab').forEach(function (t) { t.addEventListener('click', function () { showTab(t.dataset.tab); }); });

    /* as_of */
    var asOfInput = $('#lw-asof');
    if (asOfInput) {
      var n = new Date(); n.setSeconds(0, 0);
      asOfInput.value = n.toISOString().slice(0, 16);
      asOfInput.addEventListener('change', function () {
        state.asOf = asOfInput.value ? new Date(asOfInput.value).toISOString() : null;
        showTab($('.lw-tab.is-active').dataset.tab);
      });
    }

    /* Snapshot */
    var snap = $('#lw-snapshot');
    if (snap) {
      api('/snapshots').then(function (list) {
        list.forEach(function (s) { var o = document.createElement('option'); o.value = s.snapshot_id || s.id || ''; o.textContent = s.snapshot_id || s.id || ''; snap.appendChild(o); });
      }).catch(function () {});
      snap.addEventListener('change', function () { state.snapshotId = snap.value; showTab($('.lw-tab.is-active').dataset.tab); });
    }

    /* Price mode */
    var pm = $('#lw-price-mode');
    if (pm) { pm.addEventListener('change', function () { state.priceMode = pm.value; if (state.tab === 'bars') showTab('bars'); }); }

    /* Theme buttons */
    $$('.lw-theme-btn').forEach(function (b) {
      b.addEventListener('click', function () { applyTheme(b.dataset.theme); });
    });

    /* Settings toggle */
    var settingsBtn = $('#lw-settings-btn');
    var settingsPop = $('#lw-settings-pop');
    if (settingsBtn && settingsPop) {
      settingsBtn.addEventListener('click', function (e) { e.stopPropagation(); settingsPop.classList.toggle('is-open'); });
      document.addEventListener('click', function () { settingsPop.classList.remove('is-open'); });
      settingsPop.addEventListener('click', function (e) { e.stopPropagation(); });
    }

    showTab('overview');
  });
})();
