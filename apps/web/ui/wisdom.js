/* SETUPS wisdom layer — always-on reminder panel.
 *
 * UX principles:
 *   - NEVER overlap the page's own topbar or right-side floating controls.
 *   - NEVER vanish after dismiss - a floating lightbulb button always stays.
 *   - Bottom-left, slim 340px, low chroma - peripheral attention only.
 *   - Preference (open/collapsed) persists per-device via localStorage.
 *   - Works on every page via route auto-detect + /api/wisdom/for-page.
 */
(function () {
  'use strict';

  var API_BASE = '';
  var LS_COLLAPSED = 'setups_wisdom_collapsed';
  var LS_REGIME = 'setups_market_regime';

  function detectPage() {
    var p = (location.pathname || '/').toLowerCase();
    if (p.indexOf('/board') === 0)   return 'board';
    if (p.indexOf('/breadth') === 0) return 'breadth';
    if (p.indexOf('/sector') === 0)  return 'sector';
    if (p.indexOf('/trades') === 0)  return 'trades';
    if (p.indexOf('watchlist') >= 0) return 'watchlist';
    if (p.indexOf('journal') >= 0)   return 'journal';
    if (p.indexOf('analytics') >= 0) return 'analytics';
    return 'home';
  }

  function currentRegime() {
    try {
      var v = localStorage.getItem(LS_REGIME);
      if (v === 'bull' || v === 'bear' || v === 'neutral') return v;
    } catch (_) {}
    return 'unknown';
  }

  function isCollapsed() {
    try { return localStorage.getItem(LS_COLLAPSED) === 'yes'; }
    catch (_) { return false; }
  }

  function setCollapsed(v) {
    try { localStorage.setItem(LS_COLLAPSED, v ? 'yes' : 'no'); } catch (_) {}
  }

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (k === 'style' && typeof attrs[k] === 'object') {
          Object.assign(el.style, attrs[k]);
        } else if (k.indexOf('on') === 0 && typeof attrs[k] === 'function') {
          el.addEventListener(k.slice(2), attrs[k]);
        } else {
          el.setAttribute(k, attrs[k]);
        }
      }
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }

  function renderQuote(q, opts) {
    opts = opts || {};
    var tagPills = (q.tags || []).slice(0, 3).map(function (t) {
      return h('span', {'class': 'swp-tag'}, [t]);
    });
    var meta = opts.primary && q.date
      ? h('span', {'class': 'swp-date'}, [q.date])
      : h('span', {'class': 'swp-ctx'}, [(opts.ctx || '').toString()]);
    return h('div', {
      'class': 'swp-quote' + (opts.primary ? ' swp-primary' : '')
    }, [
      h('div', {'class': 'swp-auth'}, [
        h('span', {}, [q.author || 'system']),
        meta
      ]),
      h('div', {'class': 'swp-text'}, ['\u201C' + (q.text || '') + '\u201D']),
      h('div', {'class': 'swp-tags'}, tagPills)
    ]);
  }

  var CSS_LINES = [
    '.setups-wisdom-root{position:fixed;left:14px;bottom:14px;z-index:9980;pointer-events:none;font:500 12px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif;color:#e6e9ef}',
    '.setups-wisdom-toggle{pointer-events:auto;width:42px;height:42px;border-radius:999px;background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid rgba(147,197,253,.38);box-shadow:0 6px 18px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform .18s ease,box-shadow .18s ease;font-size:20px;line-height:1;user-select:none;position:relative}',
    '.setups-wisdom-toggle:hover{transform:translateY(-2px) scale(1.05);box-shadow:0 10px 26px rgba(59,130,246,.35)}',
    '.setups-wisdom-panel{pointer-events:auto;position:absolute;left:0;bottom:52px;width:340px;max-width:calc(100vw - 28px);max-height:min(70vh,520px);background:rgba(13,18,28,.96);border:1px solid rgba(59,130,246,.30);border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.6);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);display:flex;flex-direction:column;overflow:hidden;transform-origin:bottom left;transform:scale(.96) translateY(6px);opacity:0;transition:transform .22s ease,opacity .18s ease}',
    '.setups-wisdom-root.open .setups-wisdom-panel{transform:scale(1) translateY(0);opacity:1}',
    '.setups-wisdom-root:not(.open) .setups-wisdom-panel{display:none}',
    '.swp-head{display:flex;align-items:center;gap:8px;padding:10px 12px 8px;border-bottom:1px solid rgba(59,130,246,.18);background:linear-gradient(90deg,rgba(59,130,246,.10),rgba(139,92,246,.06))}',
    '.swp-head .swp-title{font-weight:800;color:#e2e8f0;font-size:12px;letter-spacing:.3px;flex:1}',
    '.swp-head .swp-title .swp-sub{color:#64748b;font-weight:500;margin-left:6px;font-size:10.5px;text-transform:capitalize}',
    '.swp-head button{pointer-events:auto;background:transparent;border:1px solid rgba(147,197,253,.35);color:#cbd5e1;font-size:11px;padding:3px 8px;border-radius:6px;cursor:pointer;transition:background .15s,border-color .15s}',
    '.swp-head button:hover{background:rgba(147,197,253,.12);border-color:rgba(147,197,253,.65)}',
    '.swp-head .swp-x{padding:3px 8px;color:#94a3b8}',
    '.swp-body{overflow-y:auto;padding:10px 12px 12px;display:flex;flex-direction:column;gap:10px}',
    '.swp-quote{padding:9px 11px;border:1px solid rgba(59,130,246,.18);border-left:3px solid #3b82f6;border-radius:8px;background:rgba(15,23,42,.55)}',
    '.swp-quote.swp-primary{border-left-color:#a5b4fc;background:linear-gradient(180deg,rgba(165,180,252,.10),rgba(59,130,246,.04))}',
    '.swp-auth{display:flex;justify-content:space-between;align-items:baseline;gap:8px;color:#a5b4fc;font-weight:700;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}',
    '.swp-auth .swp-ctx,.swp-auth .swp-date{color:#64748b;font-weight:600;text-transform:none;letter-spacing:0;font-size:10px}',
    '.swp-text{color:#e2e8f0;font-size:12.5px;line-height:1.55}',
    '.swp-tags{margin-top:5px;display:flex;flex-wrap:wrap;gap:4px}',
    '.swp-tag{font-size:9px;padding:1px 6px;border-radius:10px;background:rgba(59,130,246,.14);color:#93c5fd;text-transform:uppercase;letter-spacing:.4px}',
    '.swp-foot{padding:8px 12px;border-top:1px solid rgba(59,130,246,.15);font-size:10px;color:#64748b}',
    '@media (prefers-reduced-motion:reduce){.setups-wisdom-toggle,.setups-wisdom-panel{transition:none}}'
  ];

  function injectStyle() {
    if (document.getElementById('setups-wisdom-css')) return;
    var s = document.createElement('style');
    s.id = 'setups-wisdom-css';
    s.textContent = CSS_LINES.join('\n');
    document.head.appendChild(s);
  }

  function fetchJson(url) {
    // Cache-bust every request so a stray CDN / Safari cache can't serve
    // yesterday's nudges.  The server already sends no-store headers, but
    // belt-and-suspenders keeps the panel feeling alive.
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    var bust = sep + '_=' + Date.now();
    return fetch(url + bust, {cache: 'no-store'}).then(function (r) {
      return r.ok ? r.json() : null;
    }).catch(function () { return null; });
  }

  function fetchQotd() {
    return fetchJson(API_BASE + '/api/wisdom/quote-of-the-day');
  }

  function fetchPageNudges(page, regime, count) {
    var u = API_BASE + '/api/wisdom/for-page?page=' +
      encodeURIComponent(page) + '&regime=' + encodeURIComponent(regime) +
      '&count=' + count;
    return fetchJson(u).then(function (d) { return (d && d.items) || []; });
  }

  function fetchRandom() {
    return fetchJson(API_BASE + '/api/wisdom/random');
  }

  var rootEl = null;
  var panelBodyEl = null;
  var qotdState = null;
  var pageState = {page: 'home', regime: 'unknown', items: []};

  function rebuildBody() {
    if (!panelBodyEl) return;
    panelBodyEl.innerHTML = '';
    if (qotdState) {
      panelBodyEl.appendChild(renderQuote(qotdState, {primary: true}));
    }
    (pageState.items || []).forEach(function (q) {
      panelBodyEl.appendChild(renderQuote(q, {
        ctx: pageState.page + (pageState.regime !== 'unknown'
          ? ' \u00B7 ' + pageState.regime : '')
      }));
    });
    if (!qotdState && !(pageState.items || []).length) {
      panelBodyEl.appendChild(h('div', {
        style: {color: '#64748b', padding: '12px', textAlign: 'center', fontSize: '11px'}
      }, ['Wisdom bank unreachable - check the API.']));
    }
  }

  function refreshAll() {
    return Promise.all([
      fetchQotd(),
      fetchPageNudges(pageState.page, pageState.regime, 3)
    ]).then(function (results) {
      var qotd = results[0];
      var items = results[1];
      if (qotd) qotdState = qotd;
      pageState.items = items || [];
      rebuildBody();
    });
  }

  function rotateQotd() {
    return fetchRandom().then(function (q) {
      if (q) { qotdState = q; rebuildBody(); }
    });
  }

  function setOpen(open) {
    if (!rootEl) return;
    rootEl.classList.toggle('open', open);
    setCollapsed(!open);
  }

  function boot() {
    injectStyle();
    pageState.page = detectPage();
    pageState.regime = currentRegime();

    rootEl = h('div', {
      'class': 'setups-wisdom-root',
      'aria-label': 'Trading wisdom'
    });

    var toggle = h('div', {
      'class': 'setups-wisdom-toggle',
      'role': 'button',
      'tabindex': '0',
      'title': 'Trading wisdom - click or press W',
      'onclick': function () {
        setOpen(!rootEl.classList.contains('open'));
      },
      'onkeydown': function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setOpen(!rootEl.classList.contains('open'));
        }
      }
    }, ['\uD83D\uDCA1']);

    panelBodyEl = h('div', {'class': 'swp-body'});

    var panel = h('div', {
      'class': 'setups-wisdom-panel',
      'role': 'dialog',
      'aria-label': 'Trading wisdom panel'
    }, [
      h('div', {'class': 'swp-head'}, [
        h('div', {'class': 'swp-title'}, [
          'Wisdom',
          h('span', {'class': 'swp-sub'}, [pageState.page])
        ]),
        h('button', {
          'title': 'Rotate to a different quote',
          'onclick': function (e) { e.stopPropagation(); rotateQotd(); }
        }, ['\u21BB']),
        h('button', {
          'class': 'swp-x',
          'title': 'Collapse - the lightbulb button stays',
          'onclick': function (e) { e.stopPropagation(); setOpen(false); }
        }, ['\u00D7'])
      ]),
      panelBodyEl,
      h('div', {'class': 'swp-foot'}, [
        'Subconscious reinforcement. Press W to toggle.'
      ])
    ]);

    rootEl.appendChild(panel);
    rootEl.appendChild(toggle);
    document.body.appendChild(rootEl);

    if (!isCollapsed()) setOpen(true);
    refreshAll();

    // Tab came back to the foreground after a while? pull a fresh mix so
    // the user sees movement even without navigation.
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') refreshAll();
    });

    document.addEventListener('keydown', function (e) {
      if (e.defaultPrevented) return;
      var t = e.target;
      var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
                         t.isContentEditable === true);
      if (typing) return;
      if (e.key === 'w' || e.key === 'W') {
        setOpen(!rootEl.classList.contains('open'));
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.SETUPS_WISDOM = {
    open:    function () { setOpen(true); },
    close:   function () { setOpen(false); },
    toggle:  function () { setOpen(!rootEl.classList.contains('open')); },
    rotate:  function () { return rotateQotd(); },
    refresh: function () { return refreshAll(); },
    page:    function () { return pageState.page; },
    regime:  function () { return pageState.regime; }
  };
})();

