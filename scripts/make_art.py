"""Write the show cover and per-episode art: a changelog whose bullets are the cast's voice orbs.

Usage:
    <python with Pillow> scripts/make_art.py                          # episodes/cover.png
    <python with Pillow> scripts/make_art.py episodes/2026-09-22 ...  # <dir>/art.jpg per dir
    <python with Pillow> scripts/make_art.py --all                    # art for every episode dir

The concept is a diff read aloud. A commit rail runs down the left edge, every commit on it is a
molten voice orb in the palette of the voice that reads that segment, and each added line trails
off into a waveform in the same shades, so the art says "this changelog, spoken by these voices".
The cover draws the whole cast; each episode draws only the segments that aired that week, so the
feed varies per episode but reads as one show.

The orb palettes are parsed out of web/brand.css block 1 at runtime rather than copied here, for
the same reason web/orb.js probes the stylesheet: a second copy of the palette drifts. The orb
geometry and pose math are ported from web/orb.js and brand.css block 5, with each voice frozen at
its own clock the way idle orbs hold a pose on the site, so voices that share a palette (Brooke,
Kit, Miles, Cole) still get different shapes.

Pillow is the only non-stdlib import, and fonts come from a candidate list so the same script runs
on macOS (Helvetica Neue, Menlo) and in python:3.12-slim with fonts-dejavu-core.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import zlib
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from show import ATTRIBUTION_TEXT, SHOW
from cadence import CADENCE
from segments import PRODUCTS, SEGMENTS

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / 'episodes'
BRAND_CSS = ROOT / 'web' / 'brand.css'
CAST_JSON = ROOT / 'docs' / 'cast.json'

BLACK = (0, 0, 0)
INK = (251, 251, 255)        # --dg-ink-primary
MUTED = (148, 148, 152)      # --dg-ink-muted
ACCENT = (19, 239, 149)      # --dg-accent
ORB_GROUND = (16, 16, 20)    # the rgb(16,16,20) rect under every official orb

# Only used when brand.css is missing or a voice has no rule in it. Brooke's run.
FALLBACK_PALETTE = {'l': (161, 215, 253), 'm': (29, 157, 251), 'd': (61, 22, 143), 'g': (61, 22, 143)}

SMALL, BIG = SHOW['wordmark']
# A fork's art credits the voices; Deepgram's own show already says Deepgram in the wordmark.
CREDIT = ATTRIBUTION_TEXT if SHOW['attribution'] and 'Deepgram' not in SMALL + BIG else ''

RUNNING_ORDER = ['Intro', *SEGMENTS, 'Outro']
# Intro and Outro are canned and air every week, so they carry no information on the art.
CANNED = {'Intro', 'Outro'}
SHORT_NAMES = {'Breaking changes and action required': 'Breaking changes'}

SANS_BOLD = [('/System/Library/Fonts/HelveticaNeue.ttc', 1), ('/System/Library/Fonts/Helvetica.ttc', 1),
             ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 0)]
SANS_MEDIUM = [('/System/Library/Fonts/HelveticaNeue.ttc', 10), ('/System/Library/Fonts/Helvetica.ttc', 0),
               ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 0)]
MONO = [('/System/Library/Fonts/Menlo.ttc', 0), ('/System/Library/Fonts/SFNSMono.ttf', 0),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 0),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 0)]

_font_cache: dict[tuple[int, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_warned = False


def font(candidates: list[tuple[str, int]], size: int):
    key = (id(candidates), size)
    if key in _font_cache:
        return _font_cache[key]
    for path, index in candidates:
        if Path(path).exists():
            try:
                f = ImageFont.truetype(path, size, index=index)
                _font_cache[key] = f
                return f
            except OSError:
                continue
    global _warned
    if not _warned:
        print('no TrueType font found, falling back to the bitmap default')
        _warned = True
    f = ImageFont.load_default(size)
    _font_cache[key] = f
    return f


# ---- palettes ----------------------------------------------------------------------------------

def _hex(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def load_palettes(css_path: Path = BRAND_CSS) -> dict[str, dict[str, tuple[int, int, int]]]:
    """Every `[data-voice="..."] { --v-l; --v-m; --v-d; --v-g }` rule in brand.css, by voice id."""
    try:
        css = css_path.read_text(encoding='utf-8')
    except OSError as e:
        print(f'could not read {css_path}: {e}; using the fallback palette')
        return {}
    out = {}
    for m in re.finditer(r'\[data-voice="([^"]+)"\]\s*\{([^}]*)\}', css):
        body = m.group(2)
        vals = dict(re.findall(r'--v-([lmdg])\s*:\s*([^;]+);', body))
        try:
            g = tuple(int(x) for x in vals['g'].split(','))
            out[m.group(1)] = {'l': _hex(vals['l']), 'm': _hex(vals['m']), 'd': _hex(vals['d']),
                               'g': g if len(g) == 3 else _hex(vals['d'])}
        except (KeyError, ValueError):
            continue
    if not out:
        print(f'no [data-voice] palettes found in {css_path}; using the fallback palette')
    return out


def load_cast(path: Path = CAST_JSON) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'could not read {path}: {e}; every segment goes to the anchor')
        return {'anchor': {'name': 'Brooke', 'voice': 'flux-brooke-en'}, 'segments': {}}


def voice_for(segment: str, cast: dict) -> tuple[str, str]:
    seat = cast.get('segments', {}).get(segment) or cast.get('anchor', {})
    return seat.get('name', 'Brooke'), seat.get('voice', 'flux-brooke-en')


# ---- the orb -----------------------------------------------------------------------------------

# The site's molten orb (web/orb.js + brand.css block 5): three blurred ellipses in a 144px box on
# a near-black ground, light on the largest, deep on the smallest. (left, top, w, h, blur, shade).
ORB_ELLIPSES = [(4, 72, 135, 75, 9, 'l'), (9, 60, 124, 69, 8, 'm'), (40, 66, 66, 37, 7, 'd')]


def orb_phase(voice: str) -> float:
    """A fixed clock per voice, so each orb holds its own pose the way idle orbs do on the site."""
    return (zlib.crc32(voice.encode()) % 4000) / 100


def _pose(e: float, r: int) -> tuple[float, float, float, float, float]:
    """applyMolten from web/orb.js at envelope 0: translate x, y, rotate degrees, scale x, y."""
    i = e - r * 0.09
    a = math.sin(i * 0.311) * 20 + math.sin(i * 0.829) * 10 + math.cos(i * 0.173) * 6
    o = math.cos(i * 0.257) * 18 + math.sin(i * 0.691) * 9 + math.sin(i * 0.143) * 6 - 26
    s = math.sin(i * 0.19) * 130 + math.sin(i * 0.53) * 35
    c = 1.15 + 0.35 * math.sin(i * 0.47)
    ly = 1.15 + 0.35 * math.sin(i * 0.613 + 2.1)
    return a, o, s, c, ly


def render_orb(diameter: int, pal: dict[str, tuple[int, int, int]], phase: float = 0.0,
               halo: float = 0.45) -> Image.Image:
    """An RGBA orb plus its drop glow, on a canvas twice the diameter so the glow has room."""
    k = diameter / 144
    core = Image.new('RGB', (diameter, diameter), ORB_GROUND)
    for r, (left, top, w, h, blur, shade) in enumerate(ORB_ELLIPSES):
        a, o, s, sx, sy = _pose(phase, r)
        ew, eh = w * sx * k, h * sy * k
        pad = int(max(ew, eh) * 0.75 + blur * k * 3) + 2
        tile = Image.new('L', (pad * 2, pad * 2), 0)
        ImageDraw.Draw(tile).ellipse((pad - ew / 2, pad - eh / 2, pad + ew / 2, pad + eh / 2), fill=255)
        # CSS rotate() is clockwise on screen, PIL's is counterclockwise.
        tile = tile.rotate(-s, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur * k))
        cx, cy = (left + w / 2 + a) * k, (top + h / 2 + o) * k
        layer = Image.new('L', (diameter, diameter), 0)
        layer.paste(tile, (round(cx - pad), round(cy - pad)))
        core.paste(pal[shade], (0, 0), layer)

    # The inset glow, `inset 0 24px 84px rgba(g, 0.55)` in the large-orb rule: light pooled
    # inside the rim, heaviest at the top because the shadow is offset down.
    rim = Image.new('L', (diameter, diameter), 255)
    ImageDraw.Draw(rim).ellipse((0, 24 / 360 * diameter, diameter, diameter * (1 + 24 / 360)), fill=0)
    rim = rim.filter(ImageFilter.GaussianBlur(42 / 360 * diameter))
    core.paste(pal['g'], (0, 0), rim.point(lambda v: int(v * 0.55)))

    ss = 4
    clip = Image.new('L', (diameter * ss, diameter * ss), 0)
    ImageDraw.Draw(clip).ellipse((0, 0, diameter * ss - 1, diameter * ss - 1), fill=255)
    clip = clip.resize((diameter, diameter), Image.LANCZOS)

    canvas = diameter * 2
    off = diameter // 2
    out = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    if halo > 0:
        # The drop glow is the mid shade rather than the glow triple: most glow triples are deep
        # violets and greens that vanish on pure black.
        glow = Image.new('L', (canvas, canvas), 0)
        ImageDraw.Draw(glow).ellipse((off + diameter * 0.08, off + diameter * 0.16,
                                      off + diameter * 0.92, off + diameter * 1.0), fill=int(255 * halo))
        glow = glow.filter(ImageFilter.GaussianBlur(diameter * 0.2))
        tint = Image.new('RGBA', (canvas, canvas), pal['m'] + (0,))
        tint.putalpha(glow)
        out = Image.alpha_composite(out, tint)
    orb = core.convert('RGBA')
    orb.putalpha(clip)
    out.alpha_composite(orb, (off, off))
    return out


def place_orb(img: Image.Image, cx: float, cy: float, diameter: int, voice: str, palettes: dict,
              halo: float = 0.45) -> None:
    orb = render_orb(diameter, palettes.get(voice, FALLBACK_PALETTE), orb_phase(voice), halo)
    img.alpha_composite(orb, (round(cx - diameter), round(cy - diameter)))


# ---- shared drawing ----------------------------------------------------------------------------

# A diff's added-line highlight: the accent at about 7% on black.
BAND = (3, 19, 13)


def bands(d: ImageDraw.ImageDraw, x0: float, ys: list[float], h: float, right: int) -> None:
    """Full-bleed added-line bands behind each row, so the list reads as a diff, not a menu."""
    for y in ys:
        d.rectangle((x0, y - h / 2, right, y + h / 2), fill=BAND)


def waveform(img: Image.Image, x0: float, x1: float, y: float, h: float, bar: float,
             pal: dict[str, tuple[int, int, int]], seed: str) -> None:
    """The line being spoken: level-meter bars in the reader's shade, fading into the right edge."""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = zlib.crc32(seed.encode()) % 1000
    step = bar * 1.9
    n = int((x1 - x0) / step)
    for i in range(n):
        t = i + rnd
        amp = 0.25 + 0.75 * abs(math.sin(t * 0.37) * 0.6 + math.sin(t * 1.13) * 0.3 + math.sin(t * 2.71) * 0.25)
        bh = max(bar, h * min(1.0, amp))
        x = x0 + i * step
        alpha = int(255 * 0.85 * (1 - i / n) ** 1.4)
        # Loud bars run toward the light shade, quiet ones sit in the mid, so the deep-mid runs
        # (Elise's violet) still read on black and the mint runs read as mint.
        mix = min(1.0, amp) ** 2
        color = tuple(round(m + (lt - m) * mix) for m, lt in zip(pal['m'], pal['l']))
        d.rounded_rectangle((x, y - bh / 2, x + bar, y + bh / 2), radius=bar / 2, fill=color + (alpha,))
    img.alpha_composite(layer)


def rail(d: ImageDraw.ImageDraw, x: float, y0: float, y1: float, width: int, color) -> None:
    d.rounded_rectangle((x - width / 2, y0, x + width / 2, y1), radius=width / 2, fill=color)


def fit(text: str, candidates: list[tuple[str, int]], size: int, max_w: float):
    """The largest font no bigger than `size` that fits `text` in `max_w` pixels."""
    while size > 8:
        f = font(candidates, size)
        if f.getlength(text) <= max_w:
            return f
        size -= max(1, size // 40)
    return font(candidates, size)


def wordmark(d: ImageDraw.ImageDraw, x: float, y: float, small: int, big: int, max_w: float,
             gap: float) -> float:
    """The small wordmark line over the big one (show.json). Returns the bottom edge of the big line."""
    d.text((x, y), SMALL, font=fit(SMALL, SANS_MEDIUM, small, max_w), fill=INK, anchor='lt')
    f = fit(BIG, SANS_BOLD, big, max_w)
    top = y + small + gap
    d.text((x - f.size * 0.04, top), BIG, font=f, fill=INK, anchor='lt')
    bbox = d.textbbox((x, top), BIG, font=f, anchor='lt')
    return bbox[3]


# ---- the show cover ----------------------------------------------------------------------------

def make_cover(out: Path = EPISODES / 'cover.png') -> Path:
    size = 3000
    palettes = load_palettes()
    cast = load_cast()
    img = Image.new('RGBA', (size, size), BLACK + (255,))
    d = ImageDraw.Draw(img)

    margin = 230
    bottom = wordmark(d, margin, 250, 200, 600, size - 2 * margin, 60)

    # Breaking changes in the anchor's voice, then launches, then each product segment.
    rows = [('Breaking changes', 'Intro'), ('Launches', 'Launches')] + [(p['name'], p['name']) for p in PRODUCTS]
    top = bottom + 250
    end = size - 250
    pitch = (end - top) / (len(rows) - 1)
    orb_d = int(pitch * 0.86)
    rail_x = margin + orb_d / 2
    ys = [top + i * pitch for i in range(len(rows))]
    bands(d, rail_x + orb_d * 0.5 + 30, ys, pitch * 0.62, size)
    rail(d, rail_x, top - pitch * 0.55, end + pitch * 0.2, 16, (42, 42, 48))

    mono = font(MONO, int(orb_d * 0.36))
    text_x = rail_x + orb_d * 0.5 + 80
    for i, (label, segment) in enumerate(rows):
        y = top + i * pitch
        _, voice = voice_for(segment, cast)
        place_orb(img, rail_x, y, orb_d, voice, palettes)
        d.text((text_x, y), '+', font=mono, fill=ACCENT, anchor='lm')
        d.text((text_x + mono.getlength('+ '), y), label, font=mono, fill=INK, anchor='lm')
        wx = text_x + mono.getlength('+ ' + label) + 70
        waveform(img, wx, size, y, pitch * 0.34, 14, palettes.get(voice, FALLBACK_PALETTE), label)

    if CREDIT:
        d.text((size - margin, size - 110), CREDIT, font=font(SANS_MEDIUM, 64), fill=MUTED, anchor='rs')
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').save(out, optimize=True)
    return out


# ---- per-episode art ---------------------------------------------------------------------------

def _date_range(episode: dict) -> tuple[str, str]:
    """('Sep 13 to 19', '2026') from the window, falling back to the title."""
    try:
        s = date.fromisoformat(episode['window']['start'])
        e = date.fromisoformat(episode['window']['end'])
    except (KeyError, TypeError, ValueError):
        title = str(episode.get('title', '')).removeprefix('Week of ').strip()
        return (title or episode.get('release_date', '') or 'This week'), ''
    if CADENCE.name == 'monthly':
        return s.strftime('%B'), str(s.year)
    mon = lambda x: x.strftime('%b')
    if s.year != e.year:
        return f'{mon(s)} {s.day}, {s.year} to {mon(e)} {e.day}', str(e.year)
    if s.month != e.month:
        return f'{mon(s)} {s.day} to {mon(e)} {e.day}', str(s.year)
    return f'{mon(s)} {s.day} to {e.day}', str(s.year)


def _aired_segments(ep_dir: Path) -> list[str]:
    try:
        chapters = json.loads((ep_dir / 'chapters.json').read_text(encoding='utf-8'))['chapters']
    except (OSError, ValueError, KeyError, TypeError):
        return []
    seen = []
    for ch in chapters:
        t = str(ch.get('title', '')).strip() if isinstance(ch, dict) else ''
        if t and t not in CANNED and t not in seen:
            seen.append(t)
    order = {name: i for i, name in enumerate(RUNNING_ORDER)}
    return sorted(seen, key=lambda t: order.get(t, len(order)))


def make_episode_art(ep_dir: Path) -> Path:
    """Write <ep_dir>/art.jpg, 1400x1400: the week's date and one orb per segment that aired."""
    ep_dir = Path(ep_dir)
    episode = json.loads((ep_dir / 'episode.json').read_text(encoding='utf-8'))
    palettes = load_palettes()
    cast = load_cast()

    segments = _aired_segments(ep_dir)
    if segments:
        rows = [(SHORT_NAMES.get(s, s), *voice_for(s, cast)) for s in segments]
    else:
        # No chapters: the anchor alone, named after the host the episode says read it.
        anchor_name, anchor_voice = voice_for('', cast)
        rows = [('This week', episode.get('host') or anchor_name, episode.get('voice_id') or anchor_voice)]

    size = 1400
    img = Image.new('RGBA', (size, size), BLACK + (255,))
    d = ImageDraw.Draw(img)
    margin = 110

    # The same wordmark as the cover, set small, so a feed of these reads as one show.
    small_f = font(SANS_MEDIUM, 46)
    d.text((margin, 104), SMALL, font=small_f, fill=INK, anchor='lt')
    d.text((margin + small_f.getlength(SMALL + ' '), 104), BIG, font=font(SANS_BOLD, 46), fill=INK, anchor='lt')
    if CREDIT:
        d.text((size - margin, size - 56), CREDIT, font=font(SANS_MEDIUM, 30), fill=MUTED, anchor='rs')

    dates, year = _date_range(episode)
    fdate = fit(dates, SANS_BOLD, 150, size - 2 * margin)
    d.text((margin - fdate.size * 0.04, 196), dates, font=fdate, fill=INK, anchor='lt')
    date_bottom = d.textbbox((margin, 196), dates, font=fdate, anchor='lt')[3]
    if year:
        d.text((margin, date_bottom + 34), year, font=font(SANS_MEDIUM, 64), fill=MUTED, anchor='lt')
        date_bottom += 34 + 64

    top = date_bottom + 150
    end = size - 140
    n = len(rows)
    pitch = min(150, (end - top) / (n - 1)) if n > 1 else 0
    # Row height drives the band and waveform, so a lone fallback row still gets a full-size line.
    row_h = pitch if n > 1 else 150
    orb_d = int(min(118, pitch * 0.8)) if n > 1 else 220
    block = pitch * (n - 1)
    top = top + max(0, (end - top - block) / 2) if n > 1 else (top + end) / 2
    rail_x = margin + orb_d / 2
    reach = max(row_h * 0.6, orb_d / 2 + 90)
    bands(d, rail_x + orb_d / 2 + 16, [top + i * pitch for i in range(n)], min(row_h * 0.62, 84), size)
    rail(d, rail_x, top - reach, top + block + reach, 7, (42, 42, 48))

    label_f = font(MONO, int(min(54, orb_d * 0.44)))
    voice_f = font(MONO, int(min(40, orb_d * 0.32)))
    text_x = rail_x + orb_d / 2 + 44
    for i, (label, name, voice) in enumerate(rows):
        y = top + i * pitch
        place_orb(img, rail_x, y, orb_d, voice, palettes)
        d.text((text_x, y), '+', font=label_f, fill=ACCENT, anchor='lm')
        lx = text_x + label_f.getlength('+ ')
        d.text((lx, y), label, font=label_f, fill=INK, anchor='lm')
        vx = lx + label_f.getlength(label + '  ')
        d.text((vx, y), name, font=voice_f, fill=MUTED, anchor='lm')
        wx = vx + voice_f.getlength(name) + 34
        waveform(img, wx, size, y, min(row_h * 0.34, 46), 6, palettes.get(voice, FALLBACK_PALETTE), label)

    out = ep_dir / 'art.jpg'
    img.convert('RGB').save(out, quality=86, optimize=True, progressive=True, subsampling=0)
    return out


# ---- CLI ---------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description='Write the show cover, or per-episode art.')
    ap.add_argument('episodes', nargs='*', type=Path, help='episode dirs; none means the cover')
    ap.add_argument('--all', action='store_true', help='art for every episode dir with episode.json')
    args = ap.parse_args()

    dirs = list(args.episodes)
    if args.all:
        dirs += sorted(p.parent for p in EPISODES.glob('*/episode.json'))
    if not dirs:
        out = make_cover()
        print(f'wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)')
        return
    failed = 0
    for ep in dirs:
        ep = ep.resolve()
        if not (ep / 'episode.json').exists():
            print(f'skip {ep}: no episode.json')
            failed += 1
            continue
        try:
            out = make_episode_art(ep)
        except (OSError, ValueError) as e:
            print(f'failed {ep}: {e}')
            failed += 1
            continue
        try:
            shown = out.relative_to(ROOT)
        except ValueError:
            shown = out
        print(f'wrote {shown} ({out.stat().st_size // 1024} KB)')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
