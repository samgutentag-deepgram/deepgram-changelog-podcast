// Back catalog: every weekly episode, planned or published, as one table with the segments each
// one has and what each rendered episode cost. Reads /episodes/catalog.json, which
// scripts/build_catalog.py writes, and re-reads it every minute so the page fills in while the
// backfill renders.
//
// No build step, native ES module. Everything goes in through textContent, so nothing needs esc.
import { usd, count } from './format.js'

(function () {
  var POLL_MS = 60 * 1000
  var DASH = '–'
  var state = { data: null, year: 'all', open: {}, checkedAt: null, error: null }

  var figures = document.getElementById('bc-figures')
  var years = document.getElementById('bc-years')
  var status = document.getElementById('bc-status')
  var head = document.getElementById('bc-head')
  var body = document.getElementById('bc-body')

  function el(tag, cls, text) {
    var n = document.createElement(tag)
    if (cls) n.className = cls
    if (text != null) n.textContent = text
    return n
  }

  // Changelog headings carry markdown code spans ("`@deepgram/react` 0.2.0"). Render them as code
  // rather than printing the backticks.
  function inline(parent, text) {
    String(text).split('`').forEach(function (part, i) {
      if (!part) return
      parent.appendChild(i % 2 ? el('code', null, part) : document.createTextNode(part))
    })
    return parent
  }

  function plain(text) { return String(text).replace(/`/g, '') }

  function changelogUrl(iso) {
    var p = iso.split('-')
    return 'https://developers.deepgram.com/changelog/' + p[0] + '/' + Number(p[1]) + '/' + Number(p[2])
  }

  function when(d) {
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  function load() {
    return fetch('/episodes/catalog.json', { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('catalog.json returned ' + r.status)
      return r.json()
    }).then(function (d) {
      if (!d || !Array.isArray(d.episodes)) throw new Error('catalog.json has no episodes list')
      state.data = d
      state.error = null
      state.checkedAt = new Date()
      render()
    }).catch(function (e) {
      state.error = e
      state.checkedAt = new Date()
      if (!state.data) {
        body.innerHTML = ''
        var tr = el('tr'); var td = el('td', 'bc-error', 'Could not load the catalog: ' + e.message)
        td.colSpan = 13; tr.appendChild(td); body.appendChild(tr)
      }
      renderStatus()
    })
  }

  function render() {
    renderFigures(state.data)
    renderYears(state.data.episodes)
    renderHead(state.data)
    renderRows(state.data)
    renderStatus()
  }

  function renderStatus() {
    status.textContent = ''
    status.classList.toggle('bc-error', !!state.error)
    if (state.error) {
      status.textContent = 'Could not refresh the catalog (' + state.error.message + ').'
        + (state.data ? ' Showing the copy loaded earlier.' : '') + ' Trying again in a minute.'
      return
    }
    var built = state.data.generated_at ? new Date(state.data.generated_at) : null
    status.textContent = 'Updated ' + (built && !isNaN(built) ? when(built) : 'at an unknown time')
      + ' · checked ' + when(state.checkedAt) + ', and every minute while this page is open.'
  }

  function renderFigures(d) {
    var t = d.totals || {}
    var planned = t.planned != null ? t.planned : (t.episodes || 0) - (t.published || 0)
    var remainder = t.avg_cost_usd != null ? planned * t.avg_cost_usd : null
    var cells = [
      { value: count(t.episodes), label: 'episodes in the catalog' },
      { value: count(t.published), label: 'published so far' },
      { cls: 'cost-figure-money', value: usd(t.cost_usd_published, 2), label: 'of Flux TTS spent on them' },
      { value: t.writer_tracked ? usd(t.writer_usd_published, 2) : DASH,
        label: t.writer_tracked
          ? 'of Claude script writing across ' + count(t.writer_tracked) + ' episodes'
            + (t.writer_estimated ? ', ' + usd(t.writer_usd_estimated, 2) + ' of it estimated (≈)' : '')
          : 'of Claude script writing' },
      { value: remainder != null ? usd(remainder, 2) : DASH,
        label: remainder != null
          ? 'estimated for the other ' + count(planned) + ', at the ' + usd(t.avg_cost_usd, 4) + ' average'
          : 'estimated once one episode is published' }
    ]
    figures.innerHTML = ''
    cells.forEach(function (f) {
      var c = el('div', 'cost-figure' + (f.cls ? ' ' + f.cls : ''))
      c.appendChild(el('span', 'cost-value', f.value))
      c.appendChild(el('span', 'cost-label', f.label))
      figures.appendChild(c)
    })
  }

  function yearOf(e) { return String(e.start || e.release || e.id).slice(0, 4) }

  function renderYears(eps) {
    var counts = {}
    eps.forEach(function (e) { var y = yearOf(e); counts[y] = (counts[y] || 0) + 1 })
    if (state.year !== 'all' && !counts[state.year]) state.year = 'all'
    var opts = [{ y: 'all', label: 'All', n: eps.length }].concat(
      Object.keys(counts).sort().reverse().map(function (y) { return { y: y, label: y, n: counts[y] } }))
    years.innerHTML = ''
    opts.forEach(function (o) {
      var b = el('button', 'preset-btn' + (o.y === state.year ? ' active' : ''))
      b.type = 'button'
      b.setAttribute('aria-pressed', String(o.y === state.year))
      b.appendChild(document.createTextNode(o.label + ' '))
      b.appendChild(el('span', 'bc-year-n', String(o.n)))
      b.addEventListener('click', function () { state.year = o.y; renderYears(state.data.episodes); applyFilter() })
      years.appendChild(b)
    })
  }

  function applyFilter() {
    body.querySelectorAll('tr[data-year]').forEach(function (tr) {
      var show = state.year === 'all' || tr.getAttribute('data-year') === state.year
      tr.hidden = !show || (tr.classList.contains('bc-detail') && !state.open[tr.getAttribute('data-id')])
    })
  }

  function renderHead(d) {
    var segCounts = (d.totals && d.totals.segments) || {}
    var tr = el('tr')
    tr.appendChild(el('th', 'bc-ep', 'Episode'))
    tr.appendChild(el('th', 'bc-nw', 'Date range'))
    tr.appendChild(el('th', 'bc-nw', 'Release'))
    tr.appendChild(el('th', 'bc-n', 'Entries'))
    d.segments.forEach(function (s) {
      var th = el('th', 'bc-c', s.short)
      th.title = s.name
      th.appendChild(el('span', 'bc-th-n', count(segCounts[s.name] || 0)))
      tr.appendChild(th)
    })
    tr.appendChild(el('th', 'bc-n', 'TTS cost'))
    tr.appendChild(el('th', 'bc-n', 'Writer cost'))
    head.innerHTML = ''
    head.appendChild(tr)
  }

  function headlines(e, segName) {
    var items = e.segments[segName] || []
    if (!items.length) return e.published ? 'Aired' : 'No public headline yet'
    return items.map(function (it) {
      return (it.date ? it.date + ': ' : '') + plain(it.title) + (it.part ? ' (part of a roll-up)' : '')
    }).join('\n')
  }

  function renderRows(d) {
    var cols = 6 + d.segments.length
    body.innerHTML = ''
    d.episodes.forEach(function (e) {
      var detailId = 'bc-d-' + e.id
      var tr = el('tr', 'bc-row' + (e.published ? ' is-published' : ''))
      tr.setAttribute('data-year', yearOf(e))
      tr.setAttribute('data-id', e.id)

      var first = el('td', 'bc-ep')
      var cell = el('div', 'bc-ep-inner')
      first.appendChild(cell)
      var toggle = el('button', 'bc-toggle')
      toggle.type = 'button'
      toggle.setAttribute('aria-expanded', String(!!state.open[e.id]))
      toggle.setAttribute('aria-controls', detailId)
      toggle.setAttribute('aria-label', 'Show headlines for ' + e.title)
      toggle.appendChild(el('span', 'bc-chev', '▸')).setAttribute('aria-hidden', 'true')
      cell.appendChild(toggle)
      var name = el('span', 'bc-name')
      if (e.published && e.url) {
        var a = el('a', null, e.title); a.href = e.url; name.appendChild(a)
      } else {
        name.textContent = e.title
      }
      cell.appendChild(name)
      cell.appendChild(el('span', 'bc-tag' + (e.published ? ' is-published' : ''), e.published ? 'Published' : 'Planned'))
      tr.appendChild(first)

      tr.appendChild(el('td', 'bc-nw', (e.start || DASH) + ' to ' + (e.end || DASH)))
      tr.appendChild(el('td', 'bc-nw', e.release ? 'Tue ' + e.release : DASH))
      tr.appendChild(el('td', 'bc-n', e.entries != null ? count(e.entries) : DASH))
      d.segments.forEach(function (s) {
        var td = el('td', 'bc-c')
        if (e.segments[s.name]) {
          td.title = s.name + '\n' + headlines(e, s.name)
          var mark = el('span', 'bc-check', '✓')
          mark.setAttribute('role', 'img')
          mark.setAttribute('aria-label', s.name + ': yes')
          td.appendChild(mark)
        }
        tr.appendChild(td)
      })
      var cost = el('td', 'bc-n bc-cost', e.cost_usd != null ? usd(e.cost_usd, 4) : DASH)
      if (e.cost_usd == null) cost.title = e.published ? 'Cost not recorded' : 'Known once the episode is rendered'
      tr.appendChild(cost)
      // An estimate gets a leading ≈ as well as a tooltip, so it never reads as a measured bill.
      var wcost = el('td', 'bc-n bc-cost' + (e.writer_estimated ? ' is-estimate' : ''),
        e.writer_usd != null ? (e.writer_estimated ? '≈' : '') + usd(e.writer_usd, 4) : DASH)
      if (e.writer_estimated) {
        wcost.title = 'Estimated: written before usage was recorded. Rebuilt prompt and output tokens, thinking share calibrated on measured episodes.'
      } else if (e.writer_usd == null) {
        wcost.title = e.published ? 'Hand-written, no writer cost' : 'Known once the script is written'
      }
      tr.appendChild(wcost)
      body.appendChild(tr)

      var det = el('tr', 'bc-detail' + (e.published ? ' is-published' : ''))
      det.id = detailId
      det.setAttribute('data-year', yearOf(e))
      det.setAttribute('data-id', e.id)
      var td = el('td'); td.colSpan = cols
      td.appendChild(detail(e, d.segments))
      det.appendChild(td)
      body.appendChild(det)

      toggle.addEventListener('click', function () {
        state.open[e.id] = !state.open[e.id]
        toggle.setAttribute('aria-expanded', String(state.open[e.id]))
        applyFilter()
      })
    })
    applyFilter()
  }

  function detail(e, segments) {
    var box = el('div', 'bc-detail-inner')
    var present = segments.filter(function (s) { return e.segments[s.name] })
    if (!present.length) box.appendChild(el('p', 'muted', 'No segments recorded for this week.'))
    present.forEach(function (s) {
      box.appendChild(el('p', 'bc-seg-h', s.name))
      var items = e.segments[s.name]
      if (!items.length) {
        box.appendChild(el('p', 'bc-seg-empty', e.published ? 'Aired, no show-note links.' : 'No public headline yet.'))
        return
      }
      var ul = el('ul')
      items.forEach(function (it) {
        var li = el('li')
        if (it.date) li.appendChild(el('span', 'bc-date', it.date))
        var a = el('a')
        a.href = it.url || changelogUrl(it.date)
        a.target = '_blank'; a.rel = 'noopener'
        inline(a, it.title)
        li.appendChild(a)
        if (it.part) li.appendChild(el('span', 'bc-part', 'part of a roll-up'))
        ul.appendChild(li)
      })
      box.appendChild(ul)
    })
    if (e.published && e.url) {
      var p = el('p', 'bc-listen')
      var a = el('a', null, 'Listen, with the script and every docs link'); a.href = e.url
      p.appendChild(a)
      box.appendChild(p)
    }
    return box
  }

  load()
  setInterval(function () { if (!document.hidden) load() }, POLL_MS)
  // A tab left in the background catches up the moment it is looked at again.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && state.checkedAt && Date.now() - state.checkedAt.getTime() > POLL_MS) load()
  })
})()
