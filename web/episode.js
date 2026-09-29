// Episode page: the player, the chapter strip, the cost receipt, and the script grouped by
// segment with each segment's show-note links under it. Adapted from HN Radio's web/app.js (github.com/samgutentag-deepgram/hn-radio),
// minus plays and recasts. Multi-voice episodes label each row and move the orb to the speaker.
//
// Reads the JSON that scripts/render_episode.py writes. No build step, native ES module.
import { mmss, usd, count } from './format.js'

(function () {
  var params = new URLSearchParams(location.search)
  // Two ways in: episode.html?id=<id>, and the short /e/<id> that serve.py fills with unfurl tags.
  var short = location.pathname.match(/^\/e\/([^/]+)\/?$/)
  var id = params.get('id') || (short ? decodeURIComponent(short[1]) : null)
  if (!id) { document.getElementById('title').textContent = 'No episode id'; return }

  var base = '/episodes/' + encodeURIComponent(id) + '/'

  Promise.all([
    fetch(base + 'episode.json').then(function (r) { if (!r.ok) throw new Error('episode.json ' + r.status); return r.json() }),
    fetch(base + 'script.json').then(function (r) { if (!r.ok) throw new Error('script.json ' + r.status); return r.json() }),
    fetch(base + 'chapters.json').then(function (r) { return r.ok ? r.json() : null }).catch(function () { return null })
  ]).then(function (res) {
    render(res[0], res[1], (res[2] && res[2].chapters) || [])
  }).catch(function (e) {
    document.getElementById('title').textContent = 'Could not load episode'
    document.getElementById('meta').textContent = String(e)
  })

  function el(tag, cls, text) {
    var n = document.createElement(tag)
    if (cls) n.className = cls
    if (text != null) n.textContent = text
    return n
  }

  function renderChapterStrip(chapters, player) {
    if (!chapters.length) return
    var strip = el('div', 'chapter-strip')
    strip.appendChild(el('span', 'chapter-strip-label', chapters.length + ' segments'))
    chapters.forEach(function (c, i) {
      var dot = el('button', 'chapter-dot', String(i + 1))
      dot.type = 'button'
      var name = (i + 1) + '. ' + c.title + ' (' + mmss(c.startTime) + ')'
      dot.title = name
      dot.setAttribute('aria-label', 'Jump to ' + name)
      dot.setAttribute('data-start', String(c.startTime))
      dot.addEventListener('click', function () {
        // Seek without starting playback that was not already running.
        player.currentTime = c.startTime
        var head = document.getElementById('ch-' + i)
        if (head) head.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
      strip.appendChild(dot)
    })
    document.getElementById('chapters').appendChild(strip)
  }

  // Formatting only. Every figure was computed by render_episode.py, and the outro says the same
  // number out loud, so the page must not compute a second answer.
  function renderCost(ep) {
    var c = ep.cost || {}
    if (!c.characters) return
    var figures = [
      { cls: 'cost-figure-money', value: usd(c.usd, 4), label: 'of Deepgram Flux TTS' },
      { value: count(c.characters), label: 'characters of script' },
      { value: usd(c.year_usd, 2), label: 'for a year of weekly episodes (' + c.episodes_per_year + ')' },
      { value: count(c.episodes_per_credit), label: 'episodes on the ' + usd(c.credit_usd, 0) + ' signup credit' }
    ]
    var grid = document.getElementById('cost-figures')
    figures.forEach(function (f) {
      var cell = el('div', 'cost-figure' + (f.cls ? ' ' + f.cls : ''))
      cell.appendChild(el('span', 'cost-value', f.value))
      cell.appendChild(el('span', 'cost-label', f.label))
      grid.appendChild(cell)
    })
    var fine = document.getElementById('cost-fine')
    fine.textContent = 'Text-to-speech only, at list price: ' + usd(c.rate_usd_per_1k, 4)
      + ' per 1,000 characters on the pay-as-you-go plan, as published on ' + (c.pricing_as_of || 'the pricing page')
      + '. It leaves out the Flux TTS credit match, which returns the same amount in bonus credits on paid'
      + ' Flux TTS usage through December 31, 2026. '
    var link = el('a', null, 'Deepgram pricing')
    link.href = c.pricing_url || 'https://deepgram.com/pricing'
    link.target = '_blank'; link.rel = 'noopener'
    fine.appendChild(link)
    document.getElementById('cost').hidden = false
  }

  // "Join Brooke, Drew, and Kit as they cover the week: ..." Hosts are in speaking order.
  function joinLine(ep) {
    var h = ep.hosts && ep.hosts.length ? ep.hosts : [ep.host]
    var names = h.length < 3 ? h.join(' and ') : h.slice(0, -1).join(', ') + ', and ' + h[h.length - 1]
    return 'Join ' + names + ' as they cover the week: '
  }

  function render(ep, rows, chapters) {
    document.title = 'The Deepgram Changelog: ' + ep.title
    document.getElementById('title').textContent = ep.title
    var multi = !!(ep.cast && ep.cast.length)
    document.getElementById('meta').textContent = 'Hosted by ' + ep.host
      + (multi ? ' with ' + (ep.hosts || ep.cast).filter(function (n) { return n !== ep.host }).join(', ') : '') + ' · '
      + mmss(ep.duration_seconds) + ' · released ' + ep.release_date

    var player = document.getElementById('player')
    player.src = base + 'episode.mp3'
    if (ep.summary) document.getElementById('notes').appendChild(el('p', 'summary', joinLine(ep) + ep.summary))
    renderChapterStrip(chapters, player)
    renderCost(ep)

    var scriptEl = document.getElementById('script')
    var starts = []

    function row(seg) {
      var r = el('div', 'seg host')
      r.setAttribute('data-voice', seg.voice_id)
      var ctrl = el('div', 'ctrl')
      var b = el('button', 'icon', '▶')
      b.type = 'button'
      b.title = 'Play from ' + mmss(seg.start_seconds)
      b.addEventListener('click', function () { player.currentTime = seg.start_seconds; player.play() })
      ctrl.appendChild(b)
      ctrl.appendChild(el('span', 'ts', mmss(seg.start_seconds)))
      var body = el('div', 'body')
      if (multi) {
        var who = el('div', 'who', seg.speaker_key + ' ')
        who.appendChild(el('span', 'voice', seg.voice_id))
        body.appendChild(who)
      }
      body.appendChild(el('div', 'text', seg.text))
      r.appendChild(ctrl); r.appendChild(body)
      starts.push({ el: r, start: seg.start_seconds })
      return r
    }

    function heading(c, i) {
      var h = el('div', 'chapter-head')
      h.id = 'ch-' + i
      var b = el('button', 'icon', '▶')
      b.type = 'button'
      b.title = 'Play from ' + mmss(c.startTime)
      b.addEventListener('click', function () { player.currentTime = c.startTime; player.play() })
      h.appendChild(b)
      h.appendChild(el('span', 'ts', mmss(c.startTime)))
      h.appendChild(el('span', 'chapter-head-title', c.title))
      return h
    }

    function links(c) {
      if (!c.links || !c.links.length) return null
      var wrap = el('div', 'seg-links')
      wrap.appendChild(el('p', 'seg-links-h', 'Links'))
      var ul = el('ul')
      c.links.forEach(function (l) {
        var li = el('li')
        var a = el('a', null, l.label)
        a.href = l.url
        if (!/^mailto:/.test(l.url)) { a.target = '_blank'; a.rel = 'noopener' }
        li.appendChild(a); ul.appendChild(li)
      })
      wrap.appendChild(ul)
      return wrap
    }

    if (!chapters.length) {
      rows.forEach(function (s) { scriptEl.appendChild(row(s)) })
    } else {
      chapters.forEach(function (c, i) {
        scriptEl.appendChild(heading(c, i))
        var block = el('div', 'chapter-block')
        rows.filter(function (s) { return s.chapter === c.title }).forEach(function (s) { block.appendChild(row(s)) })
        var l = links(c)
        if (l) block.appendChild(l)
        scriptEl.appendChild(block)
      })
    }

    player.addEventListener('timeupdate', function () {
      var t = player.currentTime, active = null
      for (var i = 0; i < starts.length; i++) { if (starts[i].start <= t + 0.02) active = starts[i]; else break }
      starts.forEach(function (s) { s.el.classList.toggle('active', s === active) })
      var dots = document.querySelectorAll('.chapter-dot'), cur = null
      for (var j = 0; j < dots.length; j++) {
        if (parseFloat(dots[j].getAttribute('data-start')) <= t + 0.02) cur = dots[j]; else break
      }
      for (var k = 0; k < dots.length; k++) {
        dots[k].classList.toggle('active', dots[k] === cur)
        if (dots[k] === cur) dots[k].setAttribute('aria-current', 'true'); else dots[k].removeAttribute('aria-current')
      }
    })

    wireTransport(player, chapters, ep.voice_id, multi)
    followAlong(player)
  }

  function wireTransport(player, chapters, voiceId, multi) {
    var transport = document.getElementById('transport')
    var mark = document.getElementById('transport-mark')
    var timeEl = document.getElementById('transport-time')
    var scrub = document.getElementById('transport-scrub')
    var bar = document.getElementById('transport-bar')
    var ticks = document.getElementById('transport-ticks')
    var analyser = null
    var orb = (window.HNOrb && window.HNOrb.attach) ? window.HNOrb.attach(transport, { observe: false }) : null
    // One host, so the orb wears their palette from the start instead of waiting for playback.
    if (orb) orb.setSpeaker(voiceId, null, true)

    function connect() {
      if (analyser) return
      var AC = window.AudioContext || window.webkitAudioContext
      if (!AC) return
      try {
        var ac = new AC()
        var src = ac.createMediaElementSource(player)
        analyser = ac.createAnalyser()
        analyser.fftSize = 1024
        src.connect(analyser)
        analyser.connect(ac.destination)
        if (orb) orb.setEnvSource(window.HNOrb.envelope(analyser))
        if (ac.state === 'suspended') ac.resume()
      } catch (e) {
        analyser = null   // never let the visual break playback
      }
    }

    function placeTicks() {
      if (!ticks || !isFinite(player.duration) || player.duration <= 0) return
      ticks.innerHTML = ''
      chapters.forEach(function (c) {
        if (!c.startTime) return
        var t = el('div', 'transport-tick')
        t.style.left = (c.startTime / player.duration * 100) + '%'
        ticks.appendChild(t)
      })
    }

    function syncTime() {
      timeEl.textContent = mmss(player.currentTime) + ' / ' + mmss(player.duration)
      if (isFinite(player.duration) && player.duration > 0) {
        var frac = Math.min(1, Math.max(0, player.currentTime / player.duration))
        bar.style.width = (frac * 100) + '%'
        scrub.setAttribute('aria-valuenow', Math.round(frac * 100))
      }
    }

    scrub.addEventListener('click', function (ev) {
      if (!isFinite(player.duration) || player.duration <= 0) return
      var r = scrub.getBoundingClientRect()
      player.currentTime = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)) * player.duration
      syncTime()
    })
    scrub.addEventListener('keydown', function (ev) {
      if (!isFinite(player.duration) || player.duration <= 0) return
      var step = ev.shiftKey ? 30 : 5, to = null
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowUp') to = player.currentTime + step
      else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowDown') to = player.currentTime - step
      else if (ev.key === 'Home') to = 0
      else if (ev.key === 'End') to = player.duration
      if (to === null) return
      ev.preventDefault()
      player.currentTime = Math.min(player.duration, Math.max(0, to))
      syncTime()
    })

    transport.addEventListener('click', function () {
      if (player.paused) { connect(); player.play() } else { player.pause() }
    })
    player.addEventListener('play', function () {
      mark.innerHTML = '&#10073;&#10073;'
      transport.setAttribute('aria-label', 'Pause')
      connect()
      if (orb) orb.setLive(true)
    })
    player.addEventListener('pause', function () {
      mark.innerHTML = '&#9654;'
      transport.setAttribute('aria-label', 'Play')
      if (orb) orb.setLive(false)
    })
    // With a cast, the orb takes on whoever is speaking, so a handoff is visible as well as audible.
    var lastVoice = voiceId
    function followSpeaker() {
      if (!orb || !multi) return
      var row = document.querySelector('.seg.active')
      var v = row && row.getAttribute('data-voice')
      if (!v || v === lastVoice) return
      lastVoice = v
      orb.setSpeaker(v, null, false)
    }
    player.addEventListener('timeupdate', function () { syncTime(); followSpeaker() })
    player.addEventListener('loadedmetadata', function () { syncTime(); placeTicks() })
    player.addEventListener('seeked', syncTime)
    syncTime()
  }

  // Keep the paragraph being read in view, but back off for five seconds after the reader
  // scrolls or types so the page never fights them.
  function followAlong(player) {
    var suspendUntil = 0, last = null
    ;['wheel', 'touchmove', 'keydown'].forEach(function (evt) {
      window.addEventListener(evt, function () { suspendUntil = Date.now() + 5000 }, { passive: true })
    })
    player.addEventListener('timeupdate', function () {
      if (player.paused || Date.now() < suspendUntil) return
      var cur = document.querySelector('.seg.active')
      if (!cur || cur === last) return
      last = cur
      cur.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }
})()
