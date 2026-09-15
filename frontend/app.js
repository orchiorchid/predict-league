'use strict';

/* ------------------------------------------------------------------ helpers */

const $ = (sel, root = document) => root.querySelector(sel);

/** Build DOM nodes. Strings become text nodes, so user data is never parsed as HTML. */
function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'style') el.setAttribute('style', value);
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else el.setAttribute(key, value === true ? '' : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
const ICON_PATHS = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  up: 'M12 19V5M5.5 11.5 12 5l6.5 6.5',
  down: 'M12 5v14M5.5 12.5 12 19l6.5-6.5',
  share: 'M12 15V3M7.5 7.5 12 3l4.5 4.5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7',
  close: 'M6 6l12 12M18 6L6 18',
  star: 'M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z',
  clock: 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  chevron: 'M9 6l6 6-6 6',
};

function icon(name, cls = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) {
    try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* private mode */ }
  },
};

const fmtPts = (n) => (n === null || n === undefined ? '–' : Number.isInteger(n) ? String(n) : n.toFixed(1));
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const PICK_CODES = { H: 'Home', D: 'Draw', A: 'Away' };
const OUTCOME_SHORT = { Home: '1', Draw: 'X', Away: '2' };

function timeUntil(date) {
  const mins = Math.round((date - Date.now()) / 60000);
  if (mins <= 0) return 'now';
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `in ${hours}h ${String(mins % 60).padStart(2, '0')}m`;
  return `in ${Math.round(hours / 24)} days`;
}

function timeAgo(date) {
  const secs = Math.max(0, Math.round((Date.now() - date) / 1000));
  if (secs < 45) return 'just now';
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  return `${Math.round(secs / 3600)} h ago`;
}

const kickoffFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' });

/* ------------------------------------------------------------------ state */

const state = {
  data: null,
  players: new Map(),
  view: store.get('pl.view') === 'rounds' ? 'rounds' : 'standings',
  roundId: null,
  sort: 'total',
  filter: '',
  me: store.get('pl.me'),
  openPlayer: null,
  fetchedAt: 0,
  loading: false,
  failed: false,
  timer: null,
};

const roundById = (id) => state.data.rounds.find((r) => r.id === id);
const currentRound = () => roundById(state.data.current_round) || state.data.rounds[state.data.rounds.length - 1];

function picksFor(roundId, key) {
  const code = state.data.picks[roundId] && state.data.picks[roundId][key];
  return code ? [...code].map((c) => PICK_CODES[c] || null) : null;
}

/** correct | wrong | winning | losing | pending | void | none */
function pickState(pick, match) {
  if (!pick) return 'none';
  if (match.status === 'final') return match.outcome ? (pick === match.outcome ? 'correct' : 'wrong') : 'void';
  if (match.status === 'live' && match.outcome) return pick === match.outcome ? 'winning' : 'losing';
  if (match.status === 'postponed' || match.status === 'void') return 'void';
  return 'pending';
}

function pickLabel(pick, match) {
  if (!pick) return 'No pick';
  if (pick === 'Draw') return 'Draw';
  return (pick === 'Home' ? match.home : match.away) || pick;
}

const roundShort = (r) => `R${r.number}`;
const roundTitle = (r) => (r.stage ? `${r.competition} · ${r.stage}` : r.tag || `Round ${r.number}`);

const STATUS_LABELS = {
  final: 'Final',
  completed: 'Awaiting confirmation',
  live: 'Live',
  upcoming: 'Open',
  awaiting: 'Awaiting results',
};

function statusBadge(r) {
  return h('span', { class: `badge badge--${r.status}` }, r.status === 'live' ? h('span', { class: 'pulse' }) : null, STATUS_LABELS[r.status] || r.status);
}

function hasDraws(r) {
  return r.category !== 'cup' || r.matches.some((m) => m.dist.draw > 0);
}

/* ------------------------------------------------------------------ data */

async function load({ force = false } = {}) {
  if (state.loading) return;
  state.loading = true;
  renderSync();
  try {
    if (force) await fetch('/api/refresh', { method: 'POST' }).catch(() => null);
    const res = await fetch('/api/league', { cache: 'no-store' });
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
    const data = await res.json();
    state.data = data;
    state.players = new Map(data.players.map((p) => [p.key, p]));
    state.fetchedAt = Date.now() - (data.meta.age_seconds || 0) * 1000;
    state.failed = false;
    if (!state.roundId || !roundById(state.roundId)) state.roundId = data.current_round;
    if (state.me && !state.players.has(state.me)) state.me = null;
    renderAll();
  } catch (err) {
    state.failed = true;
    console.error(err);
    if (!state.data) renderFatal(err);
  } finally {
    state.loading = false;
    renderSync();
    schedule();
  }
}

function schedule() {
  clearTimeout(state.timer);
  if (document.hidden) return;
  let delay = 120000;
  const r = state.data && currentRound();
  if (r && r.status === 'live') delay = 30000;
  else if (r && r.first_kickoff && Math.abs(new Date(r.first_kickoff) - Date.now()) < 3 * 3600 * 1000) delay = 60000;
  if (state.failed) delay = 20000;
  state.timer = setTimeout(() => load(), delay);
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) return clearTimeout(state.timer);
  if (Date.now() - state.fetchedAt > 30000) load();
  else schedule();
});

/* ------------------------------------------------------------------ top bar & banners */

function renderSync() {
  const btn = $('#sync');
  const text = $('#sync-text');
  btn.classList.toggle('is-loading', state.loading);
  btn.classList.toggle('is-stale', state.failed || Boolean(state.data && state.data.meta.stale));
  if (state.loading && !state.data) text.textContent = 'Loading…';
  else if (state.loading) text.textContent = 'Updating…';
  else if (state.failed) text.textContent = 'Offline';
  else if (state.data) text.textContent = timeAgo(state.fetchedAt);
  if (state.data) btn.title = `Data updated ${timeAgo(state.fetchedAt)} — tap to refresh`;
}

function renderBanner() {
  const banner = $('#banner');
  const meta = state.data.meta;
  banner.replaceChildren();
  if (meta.stale) {
    banner.append(h('strong', { text: 'Could not reach the Google Sheet. ' }), `Showing data from ${timeAgo(state.fetchedAt)}.`);
  }
  banner.hidden = !meta.stale;
  for (const a of [$('#sheet-link'), $('#footer-sheet')]) a.href = meta.spreadsheet_url;
}

function renderFatal(err) {
  $('#current').replaceChildren(
    h('div', { class: 'empty empty--error' },
      h('p', { class: 'empty__title', text: 'The league data could not be loaded.' }),
      h('p', { text: 'The server may be waking up (this takes up to a minute on the free plan).' }),
      h('button', { class: 'btn', type: 'button', onclick: () => load(), text: 'Try again' })),
  );
  $('#view-standings').replaceChildren();
  console.warn(err);
}

/* ------------------------------------------------------------------ "me" card & search */

function movement(p, compact = false) {
  if (p.movement === null || p.movement === undefined) {
    return p.prev_rank === null && p.played === 1 ? h('span', { class: 'move move--new', text: 'new' }) : null;
  }
  if (p.movement === 0) return compact ? h('span', { class: 'move move--same', text: '–', 'aria-label': 'no change' }) : null;
  const up = p.movement > 0;
  return h('span', { class: `move move--${up ? 'up' : 'down'}`, title: `${up ? 'Up' : 'Down'} ${Math.abs(p.movement)} since last round` },
    icon(up ? 'up' : 'down', 'icon icon--xs'), Math.abs(p.movement));
}

function avatar(name, big = false) {
  const initial = (name.match(/[a-z0-9]/i) || ['?'])[0].toUpperCase();
  let hash = 0;
  for (const ch of name.toLowerCase()) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  return h('span', { class: `avatar${big ? ' avatar--big' : ''}`, style: `--hue:${hash}`, 'aria-hidden': 'true', text: initial });
}

function roundProgressLine(r, key) {
  const picks = picksFor(r.id, key);
  if (!picks) return r.status === 'upcoming' ? 'No picks for this round yet' : `Did not play ${roundShort(r)}`;
  const states = picks.map((p, i) => pickState(p, r.matches[i]));
  const count = (s) => states.filter((x) => x === s).length;
  const decided = count('correct') + count('wrong');
  if (!decided && !count('winning') && !count('losing')) return `${roundShort(r)} picks are in ✓`;
  const parts = [`${count('correct')}/${decided} correct in ${roundShort(r)}`];
  if (count('winning')) parts.push(`${count('winning')} winning live`);
  return parts.join(' · ');
}

function renderMe() {
  const card = $('#me-card');
  const p = state.me && state.players.get(state.me);
  card.hidden = !p;
  if (!p) return;
  const r = currentRound();
  card.replaceChildren(
    h('button', { class: 'me-card__main', type: 'button', onclick: () => openPlayer(p.key), 'aria-label': `Open your profile, ${p.name}` },
      avatar(p.name),
      h('span', { class: 'me-card__text' },
        h('span', { class: 'me-card__name' }, p.name, h('span', { class: 'you', text: 'you' })),
        h('span', { class: 'me-card__sub', text: roundProgressLine(r, p.key) })),
      h('span', { class: 'me-card__rank' },
        h('span', { class: 'me-card__pos' }, `#${p.rank}`, movement(p)),
        h('span', { class: 'me-card__pts', text: `${fmtPts(p.total)} pts` }))),
  );
}

function searchPlayers(query) {
  const q = query.trim().replace(/^\/?u\//i, '').toLowerCase();
  if (!q) return [];
  const hits = [];
  for (const p of state.data.players) {
    const names = [p.key, ...p.aliases.map((a) => a.toLowerCase())];
    const starts = names.some((n) => n.startsWith(q));
    if (starts || names.some((n) => n.includes(q))) hits.push({ p, starts });
  }
  hits.sort((a, b) => (b.starts - a.starts) || (a.p.rank - b.p.rank));
  return hits.slice(0, 8).map((x) => x.p);
}

function highlight(name, query) {
  const q = query.trim().replace(/^\/?u\//i, '');
  const i = name.toLowerCase().indexOf(q.toLowerCase());
  if (!q || i < 0) return name;
  return [name.slice(0, i), h('mark', { text: name.slice(i, i + q.length) }), name.slice(i + q.length)];
}

function setupSearch() {
  const input = $('#search-input');
  const list = $('#search-results');
  let active = -1;
  let results = [];

  const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; };
  const choose = (p) => { input.value = ''; close(); input.blur(); openPlayer(p.key); };
  const paint = () => {
    list.replaceChildren(...(results.length ? results.map((p, i) =>
      h('li', { role: 'option', id: `sr-${i}`, class: i === active ? 'is-active' : '', 'aria-selected': String(i === active),
                onmousedown: (e) => { e.preventDefault(); choose(p); } },
        avatar(p.name),
        h('span', { class: 'search__name' }, highlight(p.name, input.value)),
        h('span', { class: 'search__meta', text: `#${p.rank} · ${fmtPts(p.total)} pts` }))) :
      [h('li', { class: 'search__empty', text: 'No player with that name' })]));
    input.setAttribute('aria-activedescendant', active >= 0 ? `sr-${active}` : '');
  };

  input.addEventListener('input', () => {
    if (!state.data) return;
    results = searchPlayers(input.value);
    active = results.length ? 0 : -1;
    if (!input.value.trim()) return close();
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    paint();
  });
  input.addEventListener('keydown', (e) => {
    if (list.hidden) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
      paint();
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === 'Escape') {
      close();
    }
  });
  input.addEventListener('blur', () => setTimeout(close, 120));
}

/* ------------------------------------------------------------------ current round card */

function matchDots(r) {
  return h('div', { class: 'dots', 'aria-hidden': 'true' },
    r.matches.map((m) => h('span', { class: `dot dot--${m.status}`, title: `${m.title}: ${m.score || m.status}` })));
}

function currentSummary(r) {
  const finished = r.matches.filter((m) => m.status === 'final').length;
  const live = r.matches.filter((m) => m.status === 'live').length;
  if (r.status === 'upcoming') {
    const next = r.matches.map((m) => m.kickoff && new Date(m.kickoff)).filter((d) => d && d > Date.now()).sort((a, b) => a - b)[0];
    return next ? `First kick-off ${kickoffFmt.format(next)} · ${timeUntil(next)}` : 'Waiting for kick-off';
  }
  if (r.status === 'live') return `${finished} of ${r.matches.length} finished${live ? ` · ${live} in play` : ''}`;
  if (r.status === 'completed') return 'All matches finished · scores are unofficial until the organizer confirms';
  if (r.status === 'awaiting') return 'Round finished · waiting for the organizer to publish results';
  return `Average ${fmtPts(r.stats.average)} · top score ${fmtPts(r.stats.top)}`;
}

function renderCurrent() {
  const r = currentRound();
  const el = $('#current');
  if (!r) return el.replaceChildren();
  el.replaceChildren(
    h('button', { class: `current__card current__card--${r.status}`, type: 'button', onclick: () => { showRound(r.id); scrollToTabs(); } },
      h('span', { class: 'current__top' },
        h('span', { class: 'current__eyebrow', text: `Round ${r.number}` }),
        statusBadge(r)),
      h('span', { class: 'current__title', text: roundTitle(r) }),
      h('span', { class: 'current__sub', text: `${currentSummary(r)} · ${plural(r.entries, 'entry', 'entries')}` }),
      matchDots(r),
      h('span', { class: 'current__cta' }, 'Fixtures & picks', icon('chevron', 'icon icon--xs'))),
  );
}

/* ------------------------------------------------------------------ tabs */

function setView(view, { push = true } = {}) {
  state.view = view;
  store.set('pl.view', view);
  for (const btn of document.querySelectorAll('.tabs__btn')) btn.setAttribute('aria-selected', String(btn.dataset.view === view));
  $('#view-standings').hidden = view !== 'standings';
  $('#view-rounds').hidden = view !== 'rounds';
  if (push) syncUrl();
}

function showRound(id) {
  state.roundId = id;
  setView('rounds');
  renderRounds();
}

function scrollToTabs() {
  $('.tabs').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}

/* ------------------------------------------------------------------ standings */

const MAX_ROUND_COLUMNS = 10;

function scoredRounds() {
  return state.data.rounds.filter((r) => r.status !== 'upcoming' || r.id === state.data.current_round).slice(-MAX_ROUND_COLUMNS);
}

function renderStandings() {
  const view = $('#view-standings');
  const rounds = scoredRounds();
  const latest = [...state.data.rounds].reverse().find((r) => r.status !== 'upcoming') || currentRound();
  const q = state.filter.trim().toLowerCase();

  let rows = state.data.players;
  if (q) rows = rows.filter((p) => p.key.includes(q) || p.aliases.some((a) => a.toLowerCase().includes(q)));
  if (state.sort !== 'total') {
    rows = [...rows].sort((a, b) => ((b.rounds[state.sort] ?? -1) - (a.rounds[state.sort] ?? -1)) || a.rank - b.rank);
  }

  const sortBtn = (id, label, title) => h('button', {
    type: 'button', class: `th-sort${state.sort === id ? ' is-active' : ''}`, title,
    'aria-pressed': String(state.sort === id), onclick: () => { state.sort = state.sort === id ? 'total' : id; renderStandings(); },
  }, label);

  const head = h('div', { class: 'row row--head', role: 'row' },
    h('span', { class: 'c-rank', role: 'columnheader', text: '#' }),
    h('span', { class: 'c-name', role: 'columnheader', text: 'Player' }),
    rounds.map((r) => h('span', { class: `c-round${r.id === latest.id ? ' c-round--latest' : ''}`, role: 'columnheader' },
      sortBtn(r.id, roundShort(r), `${r.tag || ''} — sort by this round`))),
    h('span', { class: 'c-total', role: 'columnheader' }, sortBtn('total', 'Pts', 'Sort by total points')));

  const body = rows.map((p) => {
    const cells = rounds.map((r) => {
      const played = r.id in p.rounds;
      const pts = p.rounds[r.id];
      const live = r.id === state.data.current_round && p.live ? p.live : 0;
      return h('span', { class: `c-round${r.id === latest.id ? ' c-round--latest' : ''}${played ? '' : ' is-empty'}`, role: 'cell' },
        played ? fmtPts(pts) : '·',
        live ? h('sup', { class: 'live-pts', title: `${live} more if live scores hold`, text: `+${live}` }) : null);
    });
    return h('div', { class: `row${p.key === state.me ? ' is-me' : ''}`, role: 'row', dataset: { key: p.key } },
      h('span', { class: `c-rank rank-${p.rank <= 3 ? p.rank : 'n'}`, role: 'cell' }, h('b', { text: p.rank }), movement(p, true)),
      h('span', { class: 'c-name', role: 'rowheader' },
        h('button', { type: 'button', class: 'name-btn', onclick: () => openPlayer(p.key) },
          h('span', { class: 'name-btn__name' }, p.name, p.key === state.me ? h('span', { class: 'you', text: 'you' }) : null),
          h('span', { class: 'name-btn__meta', text: `${plural(p.played, 'round')}${p.accuracy !== null ? ` · ${p.accuracy}%` : ''}` }))),
      cells,
      h('span', { class: 'c-total', role: 'cell' }, h('b', { text: fmtPts(p.total) })));
  });

  const toolbar = h('div', { class: 'toolbar' },
    h('label', { class: 'filter' },
      h('span', { class: 'sr-only', text: 'Filter players' }),
      h('input', { type: 'search', placeholder: `Filter ${state.data.players.length} players`, value: state.filter, autocomplete: 'off',
                   oninput: (e) => { state.filter = e.target.value; renderStandings(); } })),
    state.me && state.players.has(state.me) ? h('button', { type: 'button', class: 'btn btn--ghost', onclick: jumpToMe, text: 'Find me' }) : null);

  const table = h('div', { class: 'table', role: 'table', 'aria-label': 'Overall standings', style: `--rounds:${rounds.length}` },
    head, body.length ? body : h('div', { class: 'empty', text: `No player matches “${state.filter}”` }));

  if (view.firstChild && view.querySelector('.toolbar')) {
    view.querySelector('.table').replaceWith(table);
  } else {
    view.replaceChildren(toolbar, table, h('p', { class: 'hint', text: 'Tap a round header to sort by it. Tap a name for picks and history.' }));
  }
}

function jumpToMe() {
  state.filter = '';
  const input = $('#view-standings .filter input');
  if (input) input.value = '';
  renderStandings();
  const row = $(`#view-standings .row[data-key="${CSS.escape(state.me)}"]`);
  if (row) {
    row.scrollIntoView({ block: 'center', behavior: 'smooth' });
    row.classList.add('flash');
    setTimeout(() => row.classList.remove('flash'), 1600);
  }
}

/* ------------------------------------------------------------------ rounds */

function distBar(r, m) {
  const d = m.dist;
  const total = d.total || 1;
  const segs = [['home', 'Home', OUTCOME_SHORT.Home], ['draw', 'Draw', OUTCOME_SHORT.Draw], ['away', 'Away', OUTCOME_SHORT.Away]]
    .filter(([k]) => k !== 'draw' || hasDraws(r));
  return h('div', { class: 'dist' },
    h('div', { class: 'dist__bar', role: 'img', 'aria-label': segs.map(([k, name]) => `${name} ${Math.round(100 * d[k] / total)}%`).join(', ') },
      segs.map(([k, name]) => d[k] ? h('span', {
        class: `dist__seg dist__seg--${k}${m.outcome === name && m.status !== 'scheduled' ? ' is-result' : ''}`,
        style: `flex-grow:${d[k]}`,
      }) : null)),
    h('div', { class: 'dist__legend' },
      segs.map(([k, name, short]) => h('span', { class: `dist__label${m.outcome === name && m.status !== 'scheduled' ? ' is-result' : ''}` },
        h('i', { class: `sw sw--${k}` }), `${short} ${Math.round(100 * d[k] / total)}%`))));
}

function matchStatus(m) {
  if (m.status === 'live') return h('span', { class: 'm-status m-status--live' }, h('span', { class: 'pulse' }), m.detail || 'Live');
  if (m.status === 'final') return h('span', { class: 'm-status', text: m.confirmed ? 'FT' : (m.detail || 'FT') });
  if (m.status === 'postponed') return h('span', { class: 'm-status m-status--warn', text: 'Postponed' });
  if (m.status === 'void') return h('span', { class: 'm-status m-status--warn', text: 'Void' });
  if (m.kickoff) {
    const d = new Date(m.kickoff);
    return h('span', { class: 'm-status', title: d.toLocaleString(), text: kickoffFmt.format(d) });
  }
  return h('span', { class: 'm-status', text: '—' });
}

const STATE_TEXT = { correct: 'Correct', wrong: 'Wrong', winning: 'Winning', losing: 'Losing', pending: 'Pending', void: 'Void', none: 'No pick' };

function pickChip(pick, m, withLabel = true) {
  const st = pickState(pick, m);
  const ic = { correct: 'check', wrong: 'x', winning: 'check', losing: 'x' }[st];
  return h('span', { class: `pick pick--${st}`, title: STATE_TEXT[st] },
    ic ? icon(ic, 'icon icon--xs') : null, withLabel ? pickLabel(pick, m) : null);
}

function fixture(r, m, myPicks) {
  const outcomeCls = (side) => (m.outcome && m.status !== 'scheduled' ? (m.outcome === side ? ' is-win' : '') : '');
  const pct = m.correct_pct !== null && m.correct_pct !== undefined
    ? `${m.correct_pct}% ${m.status === 'live' ? 'right so far' : 'got it'}`
    : null;
  return h('li', { class: `fx fx--${m.status}` },
    h('div', { class: 'fx__meta' },
      h('span', { class: 'fx__when' }, matchStatus(m), pct ? h('span', { class: 'fx__pct', text: pct }) : null),
      myPicks ? pickChip(myPicks[m.index], m) : null),
    h('div', { class: 'fx__line' },
      h('span', { class: `fx__team fx__team--home${outcomeCls('Home')}`, text: m.home || m.title }),
      h('span', { class: 'fx__score', text: m.score || 'v' }),
      h('span', { class: `fx__team fx__team--away${outcomeCls('Away')}`, text: m.away || '' })),
    distBar(r, m));
}

function roundStandings(r) {
  const entries = state.data.players
    .filter((p) => r.id in p.rounds)
    .map((p) => ({ p, pts: p.rounds[r.id], live: r.id === state.data.current_round ? p.live : 0, picks: picksFor(r.id, p.key) }));
  const scored = entries.some((e) => e.pts !== null);
  entries.sort((a, b) => (scored ? ((b.pts ?? -1) + b.live) - ((a.pts ?? -1) + a.live) : 0) || a.p.name.localeCompare(b.p.name, undefined, { sensitivity: 'base' }));

  let rank = 0; let prev = null;
  return h('div', { class: 'rtable', role: 'table', 'aria-label': `${roundShort(r)} results` },
    entries.map((e, i) => {
      const value = scored ? (e.pts ?? 0) + e.live : null;
      if (value !== prev) { rank = i + 1; prev = value; }
      return h('div', { class: `rrow${e.p.key === state.me ? ' is-me' : ''}`, role: 'row' },
        h('span', { class: 'rrow__rank', role: 'cell', text: scored ? rank : '' }),
        h('button', { type: 'button', class: 'rrow__name', role: 'cell', onclick: () => openPlayer(e.p.key) },
          e.p.name, e.p.key === state.me ? h('span', { class: 'you', text: 'you' }) : null),
        h('span', { class: 'rrow__grid', role: 'cell', 'aria-label': 'picks' },
          (e.picks || []).map((pick, idx) => h('i', { class: `sq sq--${pickState(pick, r.matches[idx])}`, title: `${r.matches[idx].title}: ${pickLabel(pick, r.matches[idx])}` }))),
        h('span', { class: 'rrow__pts', role: 'cell' },
          scored ? fmtPts(e.pts) : '–',
          e.live ? h('sup', { class: 'live-pts', text: `+${e.live}` }) : null));
    }));
}

function stat(label, value) {
  return h('div', { class: 'stat' }, h('span', { class: 'stat__value', text: value }), h('span', { class: 'stat__label', text: label }));
}

function renderRounds() {
  const view = $('#view-rounds');
  const r = roundById(state.roundId) || currentRound();
  const me = state.me && state.players.get(state.me);
  const myPicks = me ? picksFor(r.id, me.key) : null;

  const picker = h('div', { class: 'chips', role: 'listbox', 'aria-label': 'Choose a round' },
    [...state.data.rounds].reverse().map((x) => h('button', {
      type: 'button', role: 'option', class: `chip${x.id === r.id ? ' is-active' : ''}`, 'aria-selected': String(x.id === r.id),
      onclick: () => { state.roundId = x.id; renderRounds(); syncUrl(); },
    }, h('b', { text: roundShort(x) }), x.tag || '', x.status === 'live' ? h('span', { class: 'pulse' }) : null)));

  const stats = r.stats.average !== null
    ? [stat('Entries', r.entries), stat('Average', fmtPts(r.stats.average)), stat('Best', fmtPts(r.stats.top)), stat('Perfect', r.stats.perfect)]
    : [stat('Entries', r.entries), stat('Matches', r.matches.length), stat('Finished', r.matches.filter((m) => m.status === 'final').length), stat('Live', r.matches.filter((m) => m.status === 'live').length)];

  const myLine = me ? h('p', { class: 'round__mine', text: roundProgressLine(r, me.key) }) : null;

  view.replaceChildren(
    picker,
    h('header', { class: 'round__head' },
      h('div', { class: 'round__titles' },
        h('p', { class: 'round__eyebrow' }, `Round ${r.number}`, statusBadge(r)),
        h('h2', { class: 'round__title', text: roundTitle(r) }),
        h('p', { class: 'round__sub', text: currentSummary(r) }),
        myLine),
      h('div', { class: 'stats' }, stats)),
    h('h3', { class: 'section-title', text: 'Fixtures' }),
    h('ol', { class: 'fixtures' }, r.matches.map((m) => fixture(r, m, myPicks))),
    h('h3', { class: 'section-title' }, r.stats.average !== null ? 'Round table' : 'Entries', h('span', { class: 'section-title__count', text: r.entries })),
    r.entries ? roundStandings(r) : h('div', { class: 'empty', text: 'No picks submitted yet.' }),
  );
  const active = view.querySelector('.chip.is-active');
  if (active) active.scrollIntoView({ block: 'nearest', inline: 'center' });
}

/* ------------------------------------------------------------------ player sheet */

let lastFocus = null;

function openPlayer(key, { push = true } = {}) {
  const p = state.players.get(key);
  if (!p) return;
  state.openPlayer = key;
  lastFocus = document.activeElement;
  renderPlayer(p);
  const sheet = $('#sheet');
  sheet.hidden = false;
  document.body.classList.add('no-scroll');
  requestAnimationFrame(() => sheet.classList.add('is-open'));
  $('.sheet__panel').focus();
  if (push) syncUrl();
}

function closePlayer({ push = true } = {}) {
  const sheet = $('#sheet');
  if (sheet.hidden) return;
  state.openPlayer = null;
  sheet.classList.remove('is-open');
  document.body.classList.remove('no-scroll');
  setTimeout(() => { if (!state.openPlayer) sheet.hidden = true; }, 200);
  if (lastFocus && lastFocus.focus) lastFocus.focus();
  if (push) syncUrl();
}

function pointsChart(p) {
  const rounds = state.data.rounds;
  const max = Math.max(10, ...rounds.map((r) => r.matches.length));
  return h('div', { class: 'chart', role: 'img', 'aria-label': rounds.map((r) => `${roundShort(r)}: ${r.id in p.rounds ? fmtPts(p.rounds[r.id]) : 'did not play'}`).join(', ') },
    rounds.map((r) => {
      const played = r.id in p.rounds;
      const pts = p.rounds[r.id];
      const avg = r.stats.average;
      return h('button', { type: 'button', class: `chart__col${played ? '' : ' is-missing'}`, onclick: () => scrollToRound(r.id), title: roundTitle(r) },
        h('span', { class: 'chart__track' },
          avg !== null ? h('span', { class: 'chart__avg', style: `bottom:${(100 * avg) / max}%`, title: `Round average ${fmtPts(avg)}` }) : null,
          played && pts !== null ? h('span', { class: `chart__bar${r.official ? '' : ' is-unofficial'}`, style: `height:${Math.max(3, (100 * pts) / max)}%` }) : null),
        h('span', { class: 'chart__val', text: played ? fmtPts(pts) : '' }),
        h('span', { class: 'chart__label', text: roundShort(r) }));
    }));
}

function scrollToRound(id) {
  const el = $(`#sheet-body [data-round="${id}"]`);
  if (!el) return;
  el.open = true;
  el.scrollIntoView({ block: 'start', behavior: 'smooth' });
}

function playerRound(p, r, open) {
  const picks = picksFor(r.id, p.key);
  if (!picks) return null;
  const pts = p.rounds[r.id];
  const live = r.id === state.data.current_round ? p.live : 0;
  return h('details', { class: 'pr', dataset: { round: r.id }, open },
    h('summary', { class: 'pr__summary' },
      h('span', { class: 'pr__name' }, h('b', { text: roundShort(r) }), ` ${r.tag || ''}`),
      r.status !== 'final' ? statusBadge(r) : null,
      h('span', { class: 'pr__grid', 'aria-hidden': 'true' }, picks.map((pick, i) => h('i', { class: `sq sq--${pickState(pick, r.matches[i])}` }))),
      h('span', { class: 'pr__pts' }, `${fmtPts(pts)}`, live ? h('sup', { class: 'live-pts', text: `+${live}` }) : null, h('small', { text: ' pts' }))),
    h('ul', { class: 'pr__list' }, r.matches.map((m, i) => {
      const pick = picks[i];
      const share = pick && m.dist.total ? Math.round((100 * m.dist[pick.toLowerCase()]) / m.dist.total) : null;
      return h('li', { class: 'pr__item' },
        h('span', { class: 'pr__match' },
          h('span', { class: 'pr__teams', text: m.home ? `${m.home} v ${m.away}` : m.title }),
          h('span', { class: 'pr__result' }, m.score ? h('b', { text: m.score }) : null, m.status === 'live' ? ' live' : '', m.status !== 'final' && m.status !== 'live' && m.kickoff ? kickoffFmt.format(new Date(m.kickoff)) : '')),
        h('span', { class: 'pr__pick' },
          pickChip(pick, m),
          share !== null ? h('span', { class: `pr__share${share <= 20 ? ' is-bold' : ''}`, text: `${share}% picked` }) : null));
    })));
}

function renderPlayer(p) {
  const isMe = state.me === p.key;
  const best = p.best && roundById(p.best.round);
  const body = $('#sheet-body');
  const roundsDesc = [...state.data.rounds].reverse();
  const firstPlayed = roundsDesc.find((r) => picksFor(r.id, p.key));

  body.replaceChildren(
    h('div', { class: 'ph' },
      avatar(p.name, true),
      h('div', { class: 'ph__text' },
        h('h2', { id: 'sheet-title', class: 'ph__name', text: p.name }),
        p.aliases.length ? h('p', { class: 'ph__aliases', text: `Also as ${p.aliases.filter((a) => a !== p.name).join(', ')}` }) : null),
      h('div', { class: 'ph__actions' },
        h('button', { type: 'button', class: 'icon-btn', onclick: () => sharePlayer(p), 'aria-label': 'Share profile link', title: 'Share' }, icon('share')),
        h('button', { type: 'button', class: 'icon-btn', onclick: () => closePlayer(), 'aria-label': 'Close', title: 'Close' }, icon('close')))),
    h('div', { class: 'ph__stats' },
      h('div', { class: 'stat stat--hero' }, h('span', { class: 'stat__value' }, `#${p.rank}`, movement(p)), h('span', { class: 'stat__label', text: `of ${state.data.players.length}` })),
      stat('Points', fmtPts(p.total)),
      stat('Accuracy', p.accuracy !== null ? `${p.accuracy}%` : '–'),
      stat('Best round', best ? `${fmtPts(p.best.points)} · ${roundShort(best)}` : '–')),
    h('button', { type: 'button', class: `btn btn--me${isMe ? ' is-me' : ''}`, 'aria-pressed': String(isMe),
                  onclick: () => { setMe(isMe ? null : p.key); renderPlayer(p); } },
      icon(isMe ? 'check' : 'star', 'icon icon--sm'), isMe ? 'This is you' : 'This is me — pin to top'),
    h('h3', { class: 'section-title', text: 'Points per round' }),
    pointsChart(p),
    h('p', { class: 'hint', text: 'Line = round average. Faded bars are not confirmed by the organizer yet.' }),
    h('h3', { class: 'section-title', text: 'Picks' }),
    ...roundsDesc.map((r) => playerRound(p, r, r === firstPlayed)).filter(Boolean),
  );
}

async function sharePlayer(p) {
  const url = new URL(location.origin + location.pathname);
  url.searchParams.set('player', p.name);
  const data = { title: `${p.name} · Prediction League`, text: `${p.name} is #${p.rank} with ${fmtPts(p.total)} pts`, url: url.href };
  try {
    if (navigator.share && matchMedia('(pointer: coarse)').matches) return await navigator.share(data);
    await navigator.clipboard.writeText(url.href);
    toast('Link copied');
  } catch (err) {
    if (err && err.name !== 'AbortError') toast('Could not copy the link');
  }
}

function setMe(key) {
  state.me = key;
  store.set('pl.me', key);
  renderMe();
  if (state.data) { renderStandings(); renderRounds(); }
  toast(key ? 'Pinned — you will be highlighted everywhere' : 'Unpinned');
}

let toastTimer = null;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.classList.remove('is-visible'); setTimeout(() => { el.hidden = true; }, 200); }, 2200);
}

/* ------------------------------------------------------------------ URL state */

function syncUrl() {
  const url = new URL(location.href);
  url.search = '';
  if (state.view === 'rounds') url.searchParams.set('round', state.roundId);
  if (state.openPlayer) url.searchParams.set('player', state.players.get(state.openPlayer).name);
  if (url.href !== location.href) history.pushState(null, '', url);
}

function applyUrl() {
  const params = new URLSearchParams(location.search);
  const round = params.get('round');
  if (round && state.data && roundById(round)) {
    state.roundId = round;
    setView('rounds', { push: false });
    renderRounds();
  }
  const name = params.get('player') || params.get('user');
  const key = name && name.replace(/^\/?u\//i, '').trim().toLowerCase();
  if (key && state.players.has(key)) openPlayer(key, { push: false });
  else closePlayer({ push: false });
}

window.addEventListener('popstate', () => {
  const params = new URLSearchParams(location.search);
  setView(params.get('round') ? 'rounds' : 'standings', { push: false });
  if (params.get('round')) { state.roundId = params.get('round'); renderRounds(); }
  applyUrl();
});

/* ------------------------------------------------------------------ boot */

let firstRender = true;

function renderAll() {
  renderBanner();
  renderMe();
  renderCurrent();
  renderStandings();
  renderRounds();
  setView(state.view, { push: false });
  if (state.openPlayer && state.players.has(state.openPlayer)) renderPlayer(state.players.get(state.openPlayer));
  if (firstRender) {
    firstRender = false;
    applyUrl();
  }
}

function boot() {
  setupSearch();
  for (const btn of document.querySelectorAll('.tabs__btn')) btn.addEventListener('click', () => setView(btn.dataset.view));
  $('#sync').addEventListener('click', () => load({ force: true }));
  $('#sheet').addEventListener('click', (e) => { if (e.target.closest('[data-close]')) closePlayer(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.openPlayer) closePlayer();
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); $('#search-input').focus(); }
  });
  setInterval(() => { renderSync(); if (state.data && !document.hidden) renderCurrent(); }, 30000);
  setView(state.view, { push: false });
  load();
}

boot();
