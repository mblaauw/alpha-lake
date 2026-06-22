/* Lake Watch — shell app.js, stubs for Phase 3 */
(function () {
  'use strict';

  const API = '/v1/dashboard';
  let asOf = null;
  let snapshotId = '';

  function api(path) {
    const url = new URL(API + path, location.origin);
    if (asOf) url.searchParams.set('as_of', asOf);
    if (snapshotId) url.searchParams.set('snapshot_id', snapshotId);
    return fetch(url).then(r => r.ok ? r.json() : Promise.reject(r.status));
  }

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  function showTab(name) {
    $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    const content = $('#content');
    content.innerHTML = '<div class="empty">Loading…</div>';
    switch (name) {
      case 'overview': renderOverview(content); break;
      case 'bars': renderBars(content); break;
      case 'datasets': renderDatasets(content); break;
      case 'securities': renderSecurities(content); break;
      case 'pit': renderPit(content); break;
    }
  }

  function renderOverview(container) {
    api('/datasets').then(data => {
      let html = '<div class="grid">';
      data.forEach(ds => {
        const tier = ds.tier || 'experimental';
        const rows = ds.rows || 0;
        const sla = ds.sla ? 'SLA' : 'no SLA';
        const staleness = ds.latest_effective_date || '—';
        const dot = rows > 0 ? 'green' : 'amber';
        html += `<div class="card">
          <div class="card-title"><span class="dot ${dot}"></span>${ds.dataset} <span class="badge ${tier}">${tier}</span> ${sla}</div>
          <div class="card-value">${rows.toLocaleString()} rows</div>
          <div style="font-size:12px;color:var(--text2);">latest: ${staleness}</div>
        </div>`;
      });
      html += '</div>';
      container.innerHTML = html;
    }).catch(() => { container.innerHTML = '<div class="error">Failed to load datasets</div>'; });
  }

  function renderBars(container) {
    container.innerHTML = '<div class="empty">Bars tab — coming in Phase 3</div>';
  }

  function renderDatasets(container) {
    container.innerHTML = '<div class="empty">Datasets tab — coming in Phase 3</div>';
  }

  function renderSecurities(container) {
    container.innerHTML = '<div class="empty">Securities tab — coming in Phase 3</div>';
  }

  function renderPit(container) {
    container.innerHTML = '<div class="empty">PIT tab — coming in Phase 3</div>';
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    $$('.tab').forEach(tab => {
      tab.addEventListener('click', () => showTab(tab.dataset.tab));
    });
    // as_of input
    const asOfInput = $('#asOfInput');
    if (asOfInput) {
      const now = new Date();
      now.setSeconds(0, 0);
      asOfInput.value = now.toISOString().slice(0, 16);
      asOfInput.addEventListener('change', () => {
        asOf = asOfInput.value ? new Date(asOfInput.value).toISOString() : null;
        showTab($('.tab.active').dataset.tab);
      });
    }
    // Snapshot dropdown
    const snap = $('#snapshotSelect');
    if (snap) {
      api('/snapshots').then(list => {
        list.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.snapshot_id || s.id || '';
          opt.textContent = s.snapshot_id || s.id || '';
          snap.appendChild(opt);
        });
      }).catch(() => {});
      snap.addEventListener('change', () => {
        snapshotId = snap.value;
        showTab($('.tab.active').dataset.tab);
      });
    }
    // Load overview
    showTab('overview');
  });
})();
