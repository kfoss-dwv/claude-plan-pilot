// claude-plan-pilot page runtime (l3-plan-render). Tabs + folds, then three stored parts:
//   answers/{qid}      Q/A boxes        page writes {choice, note, source:"page", updatedAt}
//   challenges/{cid}   Challenge cards  page writes {status, note, source:"page", updatedAt}
//   comments/{id}      Comment layer    page writes {md, node, quote, text, status, createdAt}
// Agents write the same rows (review, applied, resolution, reply) into X.state.json.
// Baseline = the state baked in at build (#plan-state). Served by serve.py, reads poll
// /__plan/state and writes POST /__plan/<coll>/<id>; the page reloads when the .md is rebuilt.
// As a claude.ai artifact with the db capability, the same calls go to window.claude db.
// Opened as file://, edits stay in this browser and the copy buttons are the way out.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const has = (v) => typeof v === 'string' && v.trim() !== '';
  const meta = (n) => { const m = document.querySelector(`meta[name="${n}"]`); return m ? m.content : ''; };
  const MD = meta('plan-md') || 'plan.md';
  const BUILD = meta('plan-build');
  const PAGE = encodeURIComponent(location.pathname);
  const when = (iso) => {
    const d = new Date(iso);
    if (!has(iso) || isNaN(d)) return null;
    const m = Math.round((Date.now() - d) / 60000);
    const ago = m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
    return { ago, full: d.toLocaleString() };
  };
  let baked = {};
  try { baked = JSON.parse(($('#plan-state') || {}).textContent || '{}') || {}; } catch (e) { baked = {}; }
  const draftKey = 'plan-pilot:' + location.pathname + ':' + MD;
  const loadDraft = () => { try { return JSON.parse(localStorage.getItem(draftKey) || '{}'); } catch (e) { return {}; } };
  const saveDraft = (d) => { try { localStorage.setItem(draftKey, JSON.stringify(d)); } catch (e) { /* storage blocked */ } };
  const copyText = (txt, msgEl, okText, fallbackPre) => {
    const fallback = () => {
      if (fallbackPre) { fallbackPre.hidden = false; fallbackPre.textContent = txt; const rg = document.createRange(); rg.selectNodeContents(fallbackPre); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(rg); }
      if (msgEl) msgEl.textContent = 'Copy was blocked.' + (fallbackPre ? ' The text is selected below.' : '');
    };
    try { navigator.clipboard.writeText(txt).then(() => { if (msgEl) msgEl.textContent = okText; }, fallback); } catch (e) { fallback(); }
  };

  // ---------- tabs + folds ----------
  const tabs = $$('.tabs [role="tab"]');
  const show = (id, focus) => {
    for (const t of tabs) {
      const on = t.getAttribute('aria-controls') === id;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      const p = document.getElementById(t.getAttribute('aria-controls'));
      if (p) p.hidden = !on;
      if (on && focus) t.focus();
    }
  };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => {
      const id = t.getAttribute('aria-controls');
      show(id);
      try { history.replaceState(null, '', '#' + id); } catch (e) { /* sandbox may refuse */ }
    });
    t.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      show(n.getAttribute('aria-controls'), true);
    });
  });
  const reveal = (el) => {
    const panel = el.closest('.panel');
    if (panel && tabs.length) show(panel.id);
    const own = el.matches('details') ? el : el.querySelector(':scope > details');
    if (own) own.open = true;
    for (let d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
    return panel;
  };
  const openHash = () => {
    const id = decodeURIComponent(location.hash.slice(1));
    const el = id && document.getElementById(id);
    if (!el) return;
    const panel = reveal(el);
    const go = () => { if (el === panel) window.scrollTo(0, 0); else el.scrollIntoView({ block: 'start' }); };
    requestAnimationFrame(go);
    if (document.readyState !== 'complete') window.addEventListener('load', () => setTimeout(go, 0), { once: true });
  };
  openHash();
  window.addEventListener('hashchange', openHash);
  for (const btn of $$('[data-fold-all]')) {
    btn.addEventListener('click', () => {
      const folds = $$('details.fold', btn.closest('.panel'));
      const open = folds.some((f) => !f.open);
      folds.forEach((f) => { f.open = open; });
      btn.textContent = open ? 'Collapse all' : 'Expand all';
    });
  }

  // ---------- store ----------
  // serve.py: GET /__plan/state?page=… -> {answers, challenges, comments, mtime, build, poll, file}
  function localStore(first) {
    const subs = {};
    let last = first, mtime = first.mtime, timer = null;
    const snap = (c) => ({ metadata: { fromCache: false }, docs: Object.entries(last[c] || {}).map(([id, v]) => ({ id, data: () => v })) });
    const fire = () => { for (const [c, list] of Object.entries(subs)) for (const s of list) s.cb(snap(c)); };
    const fail = (e) => { for (const list of Object.values(subs)) for (const s of list) if (s.err) s.err(e); };
    async function poll() {
      try {
        const r = await fetch('/__plan/state?page=' + PAGE, { cache: 'no-store' });
        if (!r.ok) throw { code: 'unavailable' };
        const d = await r.json();
        if (d.build && BUILD && d.build !== BUILD) { location.reload(); return; }
        if (d.mtime !== mtime) { mtime = d.mtime; last = d; fire(); }
        timer = setTimeout(poll, d.poll || 2500);
      } catch (e) { fail({ code: 'server_stopped' }); timer = setTimeout(poll, 5000); }
    }
    const coll = (c) => ({
      onSnapshot(cb, err) { (subs[c] = subs[c] || []).push({ cb, err }); setTimeout(() => cb(snap(c)), 0); if (!timer) timer = setTimeout(poll, 0); return () => {}; },
    });
    async function write(path, data) {
      const r = await fetch('/__plan/' + path + '?page=' + PAGE, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      if (!r.ok) throw { code: r.status === 404 ? 'invalid_argument' : 'unavailable' };
    }
    return { local: true, file: first.file, collection: coll, doc: (path) => ({ set: (d) => write(path, d), update: (d) => write(path, d) }) };
  }
  const dbReady = (async () => {
    try {
      const db = window.claude && window.claude.use ? await window.claude.use('db') : null;
      if (db) return db;
    } catch (e) { /* fall through to serve.py */ }
    if (!/^https?:$/.test(location.protocol)) return null;
    try {
      const r = await fetch('/__plan/state?page=' + PAGE, { cache: 'no-store' });
      const d = r.ok ? await r.json() : null;
      return d && d.answers ? localStore(d) : null;
    } catch (e) { return null; }
  })();
  const setSync = (el, s, text) => { if (el) { el.dataset.s = s; el.textContent = text; } };

  function makeWriter(db, collection, exists, onMsg, stamp) {
    const timers = {}, inflight = {}, pending = {};
    async function flush(id) {
      if (inflight[id]) { timers[id] = setTimeout(() => flush(id), 400); return; }
      const data = pending[id]; delete pending[id];
      if (!data) return;
      inflight[id] = true; onMsg(id, 'Saving…');
      try {
        const ref = db.doc(`${collection}/${id}`);
        if (exists.has(id)) await ref.update(data); else { await ref.set(data); exists.add(id); }
        onMsg(id, 'Saved');
      } catch (e) {
        onMsg(id, e && e.code === 'invalid_argument' ? "You can't save on this page." : "Didn't save. Try again in a moment.");
      } finally { inflight[id] = false; }
    }
    return (id, data, delay) => {
      pending[id] = { ...(pending[id] || {}), ...data, ...(stamp ? { source: 'page', agent: '', updatedAt: new Date().toISOString() } : {}) };
      clearTimeout(timers[id]);
      timers[id] = setTimeout(() => flush(id), delay);
      return () => inflight[id] || (!!timers[id] && !!pending[id]);
    };
  }
  function byline(el, row) {
    if (!el) return;
    el.replaceChildren();
    if (!row || !has(row.updatedAt)) return;
    const who = document.createElement('span');
    who.className = 'who';
    who.dataset.src = row.source === 'agent' ? 'agent' : 'page';
    who.textContent = row.source === 'agent' ? (has(row.agent) ? `agent · ${row.agent}` : 'agent') : 'on the page';
    const t = when(row.updatedAt);
    const ts = document.createElement('span');
    ts.textContent = t ? t.ago : '';
    ts.title = t ? t.full : '';
    el.append(who, ts);
  }
  function agentNote(host, cls, label, text, stale) {
    let box = $(cls === 'decided' ? ':scope > .decided' : `:scope > .agent-note.${cls}`, host);
    if (!has(text)) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement('div'); box.className = cls === 'decided' ? 'decided' : 'agent-note ' + cls; const row = $(':scope > .row', host); host.insertBefore(box, row || null); }
    box.replaceChildren();
    const k = document.createElement('span'); k.className = 'k'; k.textContent = label + (stale ? ' · answer changed since' : '');
    const p = document.createElement('span'); p.textContent = text;
    box.append(k, p);
  }
  const countFor = (card) => { const p = card.closest('.panel'); return p ? $(`.tabs [aria-controls="${p.id}"] .count`) : null; };

  // ---------- Q/A boxes ----------
  const qCards = $$('.q[data-q]');
  const qState = {};
  const qProgress = $('#q-progress');
  const qSync = $('#q-sync');
  const qAnswered = (id) => { const s = qState[id] || {}; return has(s.choice) || has(s.note); };
  function qApply(id) {
    const s = qState[id] || {};
    const card = $(`.q[data-q="${id}"]`);
    const note = $('textarea', card);
    if (note && document.activeElement !== note) note.value = s.note || '';
    $$('input[type="radio"]', card).forEach((r) => { r.checked = r.value === s.choice; });
    byline($('.by', card), s);
    const stale = has(s.reviewedAt) && has(s.updatedAt) && s.updatedAt > s.reviewedAt && s.source !== 'agent';
    agentNote(card, 'review', 'Agent review', s.review, stale);
    agentNote(card, 'decided', 'Applied to plan', s.applied, false);
    card.classList.toggle('done', qAnswered(id));
    const st = $('.state', card);
    if (st) st.textContent = qAnswered(id) ? 'Answered' : 'Open';
    const n = qCards.filter((c) => qAnswered(c.dataset.q)).length;
    if (qProgress) qProgress.textContent = `${n} of ${qCards.length} answered`;
    const badge = countFor(card);
    if (badge) badge.textContent = qCards.length - n ? String(qCards.length - n) : '';
  }
  const qDraft = loadDraft().answers || {};
  let qWrite = null;
  const qMsg = (id, text) => { const el = $(`.q[data-q="${id}"] .saved`); if (el) el.textContent = text; };
  const qLocal = () => { const d = loadDraft(); d.answers = qState; saveDraft(d); };
  for (const card of qCards) {
    const id = card.dataset.q;
    qState[id] = { ...((baked.answers || {})[id] || {}) };
    if (qDraft[id] && (qDraft[id].updatedAt || '') > (qState[id].updatedAt || '')) Object.assign(qState[id], { choice: qDraft[id].choice, note: qDraft[id].note });
    qApply(id);
    $$('input[type="radio"]', card).forEach((r) => r.addEventListener('change', () => {
      Object.assign(qState[id], { choice: r.value, source: 'page', agent: '', updatedAt: new Date().toISOString() });
      qApply(id); qLocal();
      if (qWrite) qWrite(id, { choice: r.value }, 0); else qMsg(id, 'Kept in this browser only.');
    }));
    const note = $('textarea', card);
    if (note) note.addEventListener('input', () => {
      Object.assign(qState[id], { note: note.value, source: 'page', agent: '', updatedAt: new Date().toISOString() });
      qApply(id); qLocal();
      if (qWrite) qWrite(id, { note: note.value }, 900); else qMsg(id, 'Kept in this browser only.');
    });
  }
  function answersText() {
    return qCards.map((card) => {
      const id = card.dataset.q;
      const s = qState[id] || {};
      const title = ($('.q-title', card) || {}).textContent || '';
      const r = s.choice && $(`input[value="${CSS.escape(s.choice)}"]`, card);
      const label = r ? ($('.opt-label', r.closest('.opt')) || {}).textContent : '';
      const parts = [label, (s.note || '').trim()].filter(Boolean);
      return `${id.toUpperCase()} ${title.trim()}\n  ${parts.length ? parts.join(' — ') : '(open)'}`;
    }).join('\n');
  }
  const qCopy = $('#q-copy');
  if (qCopy) qCopy.addEventListener('click', () => copyText(answersText(), $('#q-copy-msg'), 'Copied. Paste it into chat.', $('#q-copy-text')));

  // ---------- challenge cards ----------
  const STATUS = { open: 'Open', discussing: 'Discussing', accepted: 'Accepted', changed: 'Plan changed', rejected: 'Rejected' };
  const cCards = $$('.challenge[data-c]');
  const cState = {};
  const cSync = $('#c-sync');
  function cApply(id) {
    const s = cState[id] || {};
    const card = $(`.challenge[data-c="${id}"]`);
    const status = STATUS[s.status] ? s.status : 'open';
    card.dataset.status = status;
    const pill = $('.pill', card); if (pill) { pill.dataset.s = status; pill.textContent = STATUS[status]; }
    const sel = $('select', card); if (sel && document.activeElement !== sel) sel.value = status;
    const note = $('textarea', card); if (note && document.activeElement !== note) note.value = s.note || '';
    byline($('.by', card), s);
    agentNote($('.resp', card) || card, 'decided', 'Resolution', s.resolution, false);
    const open = cCards.filter((c) => ['open', 'discussing'].includes((cState[c.dataset.c] || {}).status || 'open')).length;
    const badge = countFor(card);
    if (badge && !qCards.some((q) => countFor(q) === badge)) badge.textContent = open ? String(open) : '';
  }
  const cDraft = loadDraft().challenges || {};
  let cWrite = null;
  const cMsg = (id, text) => { const el = $(`.challenge[data-c="${id}"] .saved`); if (el) el.textContent = text; };
  const cLocal = () => { const d = loadDraft(); d.challenges = cState; saveDraft(d); };
  for (const card of cCards) {
    const id = card.dataset.c;
    cState[id] = { status: 'open', ...((baked.challenges || {})[id] || {}) };
    if (cDraft[id] && (cDraft[id].updatedAt || '') > (cState[id].updatedAt || '')) Object.assign(cState[id], { status: cDraft[id].status, note: cDraft[id].note });
    cApply(id);
    const sel = $('select', card);
    if (sel) sel.addEventListener('change', () => {
      Object.assign(cState[id], { status: sel.value, source: 'page', agent: '', updatedAt: new Date().toISOString() });
      cApply(id); cLocal();
      if (cWrite) cWrite(id, { status: sel.value }, 0); else cMsg(id, 'Kept in this browser only.');
    });
    const note = $('textarea', card);
    if (note) note.addEventListener('input', () => {
      Object.assign(cState[id], { note: note.value, source: 'page', agent: '', updatedAt: new Date().toISOString() });
      cApply(id); cLocal();
      if (cWrite) cWrite(id, { note: note.value }, 900); else cMsg(id, 'Kept in this browser only.');
    });
  }

  // ---------- comments ----------
  // Row: {md: "42-47", node?, quote, text, status: "open"|"resolved", createdAt, reply?, agent?}
  const comments = { ...(baked.comments || {}) };
  for (const [id, c] of Object.entries(loadDraft().comments || {})) if (!comments[id]) comments[id] = c;
  let cmWrite = null;
  const page = $('.page');
  const ref = (c) => `${MD}:${c.md}${has(c.node) ? ` (node ${c.node})` : ''}`;
  const asText = (c) => `${ref(c)}\n${has(c.quote) ? c.quote.trim().split('\n').map((l) => '> ' + l).join('\n') + '\n' : ''}${(c.text || '').trim()}`;
  const blockFor = (c) => (has(c.node) ? $(`[data-node="${CSS.escape(c.node)}"]`) : null) || $(`[data-md="${CSS.escape(c.md)}"]`);
  const fab = document.createElement('button');
  fab.type = 'button'; fab.className = 'btn c-fab'; fab.innerHTML = 'Comments<span class="count"></span>';
  document.body.append(fab);
  let drawer = null;
  const openList = () => Object.entries(comments).filter(([, c]) => c.status !== 'resolved');
  function paintComments() {
    $$('.c-pin').forEach((p) => p.remove());
    $$('.has-comment').forEach((el) => el.classList.remove('has-comment'));
    const per = new Map();
    for (const [id, c] of openList()) {
      const el = blockFor(c);
      if (!el) continue;
      if (!per.has(el)) per.set(el, []);
      per.get(el).push(id);
    }
    for (const [el, ids] of per) {
      el.classList.add('has-comment');
      if (el.closest('svg')) continue;
      const pin = document.createElement('button');
      pin.type = 'button'; pin.className = 'c-pin'; pin.textContent = String(ids.length);
      pin.title = ids.length + ' open comment' + (ids.length > 1 ? 's' : '');
      pin.addEventListener('click', (e) => { e.stopPropagation(); showDrawer(ids[0]); });
      el.append(pin);
    }
    $('.count', fab).textContent = openList().length ? String(openList().length) : '';
    if (drawer) renderDrawer();
  }
  function commentItem(id, c) {
    const box = document.createElement('div');
    box.className = 'c-item'; box.dataset.status = c.status || 'open'; box.dataset.id = id;
    const r = document.createElement('a'); r.className = 'c-ref'; r.href = '#'; r.textContent = ref(c);
    r.addEventListener('click', (e) => { e.preventDefault(); const el = blockFor(c); if (el) { reveal(el); el.scrollIntoView({ block: 'center' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1300); } });
    box.append(r);
    if (has(c.quote)) { const q = document.createElement('blockquote'); q.textContent = c.quote; box.append(q); }
    const t = document.createElement('div'); t.textContent = c.text || ''; box.append(t);
    if (has(c.reply)) {
      const rp = document.createElement('div'); rp.className = 'c-reply';
      const k = document.createElement('span'); k.className = 'k'; k.textContent = 'Reply' + (has(c.agent) ? ' · ' + c.agent : '');
      const p = document.createElement('span'); p.textContent = c.reply;
      rp.append(k, p); box.append(rp);
    }
    const row = document.createElement('div'); row.className = 'row';
    const msg = document.createElement('span'); msg.className = 'saved';
    const cp = document.createElement('button'); cp.type = 'button'; cp.className = 'btn'; cp.textContent = 'Copy';
    cp.addEventListener('click', () => copyText(asText(c), msg, 'Copied.'));
    const st = document.createElement('button'); st.type = 'button'; st.className = 'btn';
    st.textContent = c.status === 'resolved' ? 'Reopen' : 'Resolve';
    st.addEventListener('click', () => { saveComment(id, { status: c.status === 'resolved' ? 'open' : 'resolved' }); });
    row.append(msg, cp, st); box.append(row);
    return box;
  }
  function renderDrawer(focusId) {
    drawer.replaceChildren();
    const head = document.createElement('header');
    const h = document.createElement('h2'); h.textContent = 'Comments';
    const tools = document.createElement('div'); tools.className = 'row';
    const msg = document.createElement('span'); msg.className = 'saved';
    const all = document.createElement('button'); all.type = 'button'; all.className = 'btn'; all.textContent = 'Copy all open';
    all.addEventListener('click', () => copyText(openList().map(([, c]) => asText(c)).join('\n\n'), msg, 'Copied. Paste it into chat.'));
    const x = document.createElement('button'); x.type = 'button'; x.className = 'btn'; x.textContent = 'Close';
    x.addEventListener('click', () => { drawer.remove(); drawer = null; });
    tools.append(msg, all, x); head.append(h, tools); drawer.append(head);
    const sync = document.createElement('p'); sync.className = 'sync muted';
    sync.textContent = cmWrite ? `Saved to ${MD.replace(/\.md$/, '')}.state.json; agents reply there.` : 'Not served: comments stay in this browser. Copy them into chat.';
    drawer.append(sync);
    const list = Object.entries(comments).sort(([, a], [, b]) => (a.status === 'resolved') - (b.status === 'resolved') || String(a.createdAt).localeCompare(String(b.createdAt)));
    if (!list.length) { const p = document.createElement('p'); p.className = 'muted'; p.textContent = 'No comments yet. Select text in any block, or click a chart node.'; drawer.append(p); }
    for (const [id, c] of list) {
      const item = commentItem(id, c);
      drawer.append(item);
      if (id === focusId) { item.classList.add('flash'); setTimeout(() => item.scrollIntoView({ block: 'nearest' }), 0); }
    }
  }
  function showDrawer(focusId) {
    if (!drawer) { drawer = document.createElement('aside'); drawer.className = 'c-drawer'; document.body.append(drawer); }
    renderDrawer(focusId);
  }
  fab.addEventListener('click', () => (drawer ? (drawer.remove(), drawer = null) : showDrawer()));
  const cmLocal = () => { const d = loadDraft(); d.comments = comments; saveDraft(d); };
  function saveComment(id, data) {
    comments[id] = { ...(comments[id] || {}), ...data };
    cmLocal(); paintComments();
    if (cmWrite) cmWrite(id, data, 0);
  }

  // selection / node click -> "Comment" button -> popover
  let addBtn = null, pop = null;
  const clearUI = () => { if (addBtn) addBtn.remove(); addBtn = null; };
  const closePop = () => { if (pop) pop.remove(); pop = null; };
  const anchorOf = (node) => {
    const el = node && (node.nodeType === 1 ? node : node.parentElement);
    if (!el || !page.contains(el) || el.closest('.q, .challenge, textarea, .c-pin, .tabs')) return null;
    const n = el.closest('[data-node]');
    if (n && n.dataset.md) return { el: n, md: n.dataset.md, node: n.dataset.node };
    const b = el.closest('[data-md]');
    return b ? { el: b, md: b.dataset.md } : null;
  };
  const placeAt = (box, x, y) => { box.style.left = Math.max(8, Math.min(x + scrollX, scrollX + innerWidth - box.offsetWidth - 8)) + 'px'; box.style.top = (y + scrollY + 8) + 'px'; };
  function openPop(a, quote, x, y) {
    closePop(); clearUI();
    pop = document.createElement('div'); pop.className = 'c-pop';
    const r = document.createElement('div'); r.className = 'c-ref'; r.textContent = ref({ md: a.md, node: a.node });
    pop.append(r);
    if (has(quote)) { const q = document.createElement('blockquote'); q.textContent = quote; pop.append(q); }
    const ta = document.createElement('textarea'); ta.placeholder = 'Comment for Claude'; ta.setAttribute('aria-label', 'Comment');
    const row = document.createElement('div'); row.className = 'row';
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn'; cancel.textContent = 'Cancel';
    const save = document.createElement('button'); save.type = 'button'; save.className = 'btn'; save.textContent = 'Save comment';
    cancel.addEventListener('click', closePop);
    save.addEventListener('click', () => {
      if (!has(ta.value)) { ta.focus(); return; }
      const id = 'cm-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      const row = { md: a.md, quote: quote || '', text: ta.value.trim(), status: 'open', createdAt: new Date().toISOString() };
      if (a.node) row.node = a.node;
      saveComment(id, row);
      closePop();
      showDrawer(id);
    });
    row.append(cancel, save);
    pop.append(ta, row);
    document.body.append(pop);
    placeAt(pop, x, y);
    ta.focus();
  }
  document.addEventListener('mouseup', (e) => {
    if ((pop && pop.contains(e.target)) || (addBtn && addBtn.contains(e.target)) || (drawer && drawer.contains(e.target))) return;
    setTimeout(() => {
      clearUI();
      const sel = getSelection();
      const text = sel && !sel.isCollapsed ? sel.toString().trim() : '';
      let a = null, x = e.clientX, y = e.clientY;
      if (text) {
        a = anchorOf(sel.anchorNode);
        const b = anchorOf(sel.focusNode);
        if (a && b && a.el !== b.el) {             // selection spans blocks: widen to the range
          const [s1, e1] = a.md.split('-').map(Number), [s2, e2] = b.md.split('-').map(Number);
          a = { el: a.el, md: `${Math.min(s1, s2)}-${Math.max(e1, e2)}` };
        }
        const rect = sel.getRangeAt(0).getBoundingClientRect();
        x = rect.left; y = rect.bottom;
      } else {
        const n = e.target.closest && e.target.closest('svg [data-node]');
        if (n && n.dataset.md) a = { el: n, md: n.dataset.md, node: n.dataset.node };
      }
      if (!a) return;
      addBtn = document.createElement('button');
      addBtn.type = 'button'; addBtn.className = 'c-add'; addBtn.textContent = 'Comment';
      const quote = text;
      addBtn.addEventListener('mousedown', (ev) => ev.preventDefault());
      addBtn.addEventListener('click', () => openPop(a, quote, x, y));
      document.body.append(addBtn);
      placeAt(addBtn, x, y);
    }, 0);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closePop(); clearUI(); } });
  paintComments();

  // ---------- connect ----------
  (async () => {
    const db = await dbReady;
    if (!db) {
      setSync(qSync, 'warn', 'Answers stay in this browser. Use "Copy answers as text" and paste them into chat.');
      setSync(cSync, 'warn', 'Replies stay in this browser.');
      return;
    }
    const syncs = [qSync, cSync].filter(Boolean);
    const stale = setTimeout(() => syncs.forEach((el) => setSync(el, 'warn', "Can't reach saved data yet. Edits save once it connects.")), 10000);
    const live = (el, text) => { clearTimeout(stale); setSync(el, 'live', text); };
    const fail = (el) => (e) => {
      clearTimeout(stale);
      setSync(el, 'warn', e && e.code === 'server_stopped' ? 'serve.py stopped. Edits stay in this browser until it runs again.' : `Saved data stopped (${e && e.code}). Reload to reconnect.`);
    };
    const follow = (coll, cards, state, apply, msg, el, text, assign) => {
      const exists = new Set();
      const busy = {};
      const w = makeWriter(db, coll, exists, msg, true);
      db.collection(coll).onSnapshot((snap) => {
        if (!snap.metadata.fromCache && el) live(el, text);
        for (const d of snap.docs) {
          exists.add(d.id);
          if (!state[d.id] || (busy[d.id] && busy[d.id]())) continue;
          state[d.id] = assign(state[d.id], d.data() || {});
          apply(d.id);
        }
      }, fail(el));
      return (id, data, delay) => { busy[id] = w(id, data, delay); };
    };
    if (qCards.length) qWrite = follow('answers', qCards, qState, (id) => { qApply(id); qLocal(); }, qMsg, qSync,
      db.local ? `Answers save as you type to ${db.file}. Agent edits to that file show up here.` : 'Answers save as you type.',
      (s, v) => ({ ...s, ...v, choice: v.choice || '', note: v.note || '' }));
    if (cCards.length) cWrite = follow('challenges', cCards, cState, (id) => { cApply(id); cLocal(); }, cMsg, cSync,
      db.local ? `Replies save as you type to ${db.file}.` : 'Replies save as you type.', (s, v) => ({ ...s, ...v }));
    const exists = new Set(Object.keys(baked.comments || {}));
    cmWrite = makeWriter(db, 'comments', exists, () => {}, false);
    db.collection('comments').onSnapshot((snap) => {
      for (const d of snap.docs) { exists.add(d.id); comments[d.id] = { ...(comments[d.id] || {}), ...(d.data() || {}) }; }
      cmLocal(); paintComments();
    }, () => {});
  })();
})();
