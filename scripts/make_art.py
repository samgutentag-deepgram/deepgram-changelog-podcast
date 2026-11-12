"""Write the show cover and per-episode art: the week on Deepgram felt, read by its cast.

Usage:
    <python with Pillow> scripts/make_art.py                          # episodes/cover.png
    <python with Pillow> scripts/make_art.py episodes/2026-09-22 ...  # <dir>/art.jpg per dir
    <python with Pillow> scripts/make_art.py --all                    # art for every episode dir

The look is the Deepgram 2026 brand kit, the same as the site. The ground is one of the kit's five
felt colorways (web/brand/art/), picked by release week with the same rule web/felt.js uses, so an
episode's art matches the page it opens. The cast that read that week sits in a group bubble, each
voice its official voice-card object on its tile (web/brand/avatars/), the same cluster the site
puts on the play button. The date is set large in Work Sans, and the segments that aired run down
the bottom left in Azeret Mono with the voice that read each one.

Every asset is read from web/, which stage_site.py ships to Fly, so the weekly run in the container
draws the same art as a local run. Pillow is the only non-stdlib import.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from show import ATTRIBUTION_TEXT, SHOW
from cadence import CADENCE
from segments import SEGMENTS

ROOT = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get('EPISODES_DIR', ROOT / 'episodes'))
WEB = ROOT / 'web'
FELT = WEB / 'brand' / 'art'
AVATARS = WEB / 'brand' / 'avatars'
FONTS = WEB / 'fonts'
CAST_JSON = ROOT / 'docs' / 'cast.json'

# The kit's colors, mirrored from web/brand.css block 0.
OFF_WHITE = (252, 250, 248)
OFF_BLACK = (29, 29, 29)
LIGHT_GRAY = (196, 196, 196)
FUCHSIA = (224, 66, 255)
TILES = {
    'bakelite': (250, 129, 0), 'led': (127, 57, 255), 'brass': (247, 243, 0), 'glass': (0, 178, 255),
    'fuchsia': (224, 66, 255), 'clay': (235, 42, 46), 'phosphor': (124, 217, 65),
}
NEUTRAL_TILE = LIGHT_GRAY
# Which tile each voice card sits on, from the official card set (web/brand/avatars/voices.json).
VOICE_TILE = {
    'colin': 'bakelite', 'gemma': 'bakelite', 'alexis': 'led', 'brittany': 'led',
    'haley': 'brass', 'kit': 'brass', 'sean': 'brass', 'sienna': 'brass',
    'kai': 'glass', 'miles': 'glass', 'cliff': 'glass', 'brooke': 'glass',
    'meena': 'fuchsia', 'bree': 'fuchsia', 'cole': 'clay', 'hannah': 'clay', 'heather': 'phosphor',
}
COLORWAYS = 5

# Bubble seats as fractions of the cluster: x, y, diameter. One to four mirror web/cluster.js;
# five and six only appear on the show cover.
LAYOUTS = {
    1: [(0.50, 0.50, 0.72)],
    2: [(0.38, 0.40, 0.50), (0.65, 0.64, 0.42)],
    3: [(0.40, 0.38, 0.50), (0.72, 0.56, 0.36), (0.42, 0.74, 0.32)],
    4: [(0.37, 0.37, 0.46), (0.71, 0.37, 0.33), (0.65, 0.69, 0.40), (0.32, 0.69, 0.30)],
    5: [(0.38, 0.36, 0.42), (0.72, 0.33, 0.30), (0.74, 0.64, 0.32), (0.45, 0.72, 0.32), (0.18, 0.58, 0.22)],
    6: [(0.36, 0.34, 0.40), (0.70, 0.29, 0.28), (0.79, 0.58, 0.26), (0.57, 0.76, 0.30), (0.27, 0.69, 0.30),
        (0.57, 0.52, 0.20)],
}

SMALL, BIG = SHOW['wordmark']
SHOW_NAME = f'{SMALL} {BIG}'.strip()
# A fork's art credits the voices; Deepgram's own show already says Deepgram in the wordmark.
CREDIT = ATTRIBUTION_TEXT if SHOW['attribution'] and 'Deepgram' not in SHOW_NAME else ''

RUNNING_ORDER = ['Intro', *SEGMENTS, 'Outro']
# Intro and Outro are canned and air every week, so they carry no information on the art.
CANNED = {'Intro', 'Outro'}
SHORT_NAMES = {'Breaking changes and action required': 'Breaking changes'}


# ---- fonts -------------------------------------------------------------------------------------

FALLBACK_SANS = ['/System/Library/Fonts/HelveticaNeue.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
FALLBACK_MONO = ['/System/Library/Fonts/Menlo.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
_font_cache: dict[tuple[str, int, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_warned = False


def font(family: str, size: int, weight: int = 400):
    """Work Sans ('sans') or Azeret Mono ('mono') from web/fonts at a weight, with system fallbacks."""
    global _warned
    key = (family, size, weight)
    if key in _font_cache:
        return _font_cache[key]
    own = FONTS / ('WorkSans-Variable.ttf' if family == 'sans' else 'AzeretMono-Variable.ttf')
    f = None
    if own.exists():
        try:
            f = ImageFont.truetype(str(own), size)
            try:
                f.set_variation_by_axes([weight])
            except (OSError, ValueError, AttributeError):
                pass   # a Pillow built without variation support draws the default weight
        except OSError:
            f = None
    if f is None:
        for path in (FALLBACK_SANS if family == 'sans' else FALLBACK_MONO):
            if Path(path).exists():
                try:
                    f = ImageFont.truetype(path, size)
                    break
                except OSError:
                    continue
    if f is None:
        if not _warned:
            print('no TrueType font found, falling back to the bitmap default')
            _warned = True
        f = ImageFont.load_default(size)
    _font_cache[key] = f
    return f


def fit(text: str, family: str, size: int, weight: int, max_w: float):
    """The largest font no bigger than `size` that fits `text` in `max_w` pixels."""
    while size > 8:
        f = font(family, size, weight)
        if f.getlength(text) <= max_w:
            return f
        size -= max(1, size // 40)
    return font(family, size, weight)


# ---- cast --------------------------------------------------------------------------------------

def load_cast(path: Path = CAST_JSON) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'could not read {path}: {e}; every segment goes to the anchor')
        return {'anchor': {'name': 'Brooke', 'voice': 'flux-brooke-en'}, 'segments': {}}


def voice_for(segment: str, cast: dict) -> tuple[str, str]:
    seat = cast.get('segments', {}).get(segment) or cast.get('anchor', {})
    return seat.get('name', 'Brooke'), seat.get('voice', 'flux-brooke-en')


def voice_key(name_or_voice: str) -> str:
    """'Brooke' or 'flux-brooke-en' -> 'brooke'."""
    k = str(name_or_voice or '').strip().lower()
    if k.startswith('flux-'):
        k = k[5:]
    if len(k) > 3 and k[-3] == '-':
        k = k[:-3]
    return k


# ---- felt --------------------------------------------------------------------------------------

def colorway(day: date) -> int:
    """1 to 5: the kit colorway for the week holding `day`. Same rule as web/felt.js."""
    days = (day - date(1970, 1, 1)).days
    return ((days + 3) // 7) % COLORWAYS + 1


def felt(size: int, style: int, image: str = 'd') -> Image.Image:
    path = FELT / f'{image}{style}.jpg'
    try:
        im = Image.open(path).convert('RGB')
    except OSError as e:
        print(f'no felt at {path}: {e}; drawing on off-black')
        return Image.new('RGBA', (size, size), OFF_BLACK + (255,))
    return im.resize((size, size), Image.LANCZOS).convert('RGBA')


def scrim(img: Image.Image, top: float, bottom: float, left: float) -> None:
    """Darken the felt where the type sits: washes down from the top, up from the bottom, and in from
    the left, so off-white type clears 4.5:1 on every colorway. Built small and scaled up."""
    w, h = img.size
    n = 200
    mask = Image.new('L', (n, n), 0)
    px = mask.load()
    for y in range(n):
        fy = y / n
        v = max(0.0, 1 - fy / 0.45) * top + max(0.0, (fy - 0.5) / 0.5) * bottom
        for x in range(n):
            a = v + max(0.0, 1 - (x / n) / 0.6) * left
            px[x, y] = min(255, int(255 * a))
    shade = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    shade.putalpha(mask.resize((w, h), Image.BILINEAR))
    img.alpha_composite(shade)


# ---- the group bubble --------------------------------------------------------------------------

def _tile(d: int, color: tuple[int, int, int]) -> Image.Image:
    """A round voice-card tile: the color down to 42%, then fading to off-white at the bottom."""
    grad = Image.new('RGBA', (d, d))
    gp = ImageDraw.Draw(grad)
    for y in range(d):
        t = max(0.0, (y / d - 0.42) / 0.58)
        c = tuple(round(a + (b - a) * t) for a, b in zip(color, OFF_WHITE))
        gp.line([(0, y), (d, y)], fill=c + (255,))
    mask = Image.new('L', (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    grad.putalpha(mask)
    return grad


def _bubble(name: str, d: int, ringed: bool) -> Image.Image:
    k = voice_key(name)
    tile = _tile(d, TILES.get(VOICE_TILE.get(k, ''), NEUTRAL_TILE))
    src = AVATARS / f'{k}.webp'
    drawn = False
    if src.exists():
        try:
            obj = Image.open(src).convert('RGBA')
            obj.thumbnail((int(d * 0.8), int(d * 0.8)), Image.LANCZOS)
            tile.alpha_composite(obj, ((d - obj.width) // 2, (d - obj.height) // 2))
            drawn = True
        except OSError:
            pass
    if not drawn:
        ImageDraw.Draw(tile).text((d / 2, d / 2), (k[:1] or '?').upper(),
                                  font=font('sans', int(d * 0.42), 600), fill=OFF_BLACK, anchor='mm')
    if ringed:
        w = max(3, d // 36)
        ring = Image.new('RGBA', (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((w // 2, w // 2, d - 1 - w // 2, d - 1 - w // 2),
                                     outline=FUCHSIA + (255,), width=w)
        tile.alpha_composite(ring)
    return tile


def _soft_shadow(img: Image.Image, box: tuple[float, float, float, float], alpha: int, blur: float) -> None:
    pad = int(blur * 3)
    x0, y0, x1, y1 = (int(v) for v in box)
    layer = Image.new('RGBA', (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((pad, pad, pad + x1 - x0, pad + y1 - y0), fill=(0, 0, 0, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)), (x0 - pad, y0 - pad))


def cluster(img: Image.Image, cx: float, cy: float, diameter: int, names: list[str]) -> None:
    """The cast as one group bubble: a frosted glass disc, the host in the largest seat, ringed."""
    seen, cast = set(), []
    for n in names:
        k = voice_key(n)
        if k and k not in seen:
            seen.add(k)
            cast.append(n)
    # Only voices with an official card get a seat. The host keeps theirs regardless (as an
    # initial if they have no card), so the bubble is never empty. Same rule as cluster.js's
    # cardsOnly; the run of show beside the bubble still names everyone who read.
    cast = [n for i, n in enumerate(cast) if i == 0 or (AVATARS / f'{voice_key(n)}.webp').exists()]
    cast = cast[:6] or ['Brooke']
    x0, y0 = int(cx - diameter / 2), int(cy - diameter / 2)

    _soft_shadow(img, (x0, y0 + diameter * 0.04, x0 + diameter, y0 + diameter * 1.04), 120, diameter * 0.05)
    # Frosted glass: the felt under the disc, blurred and darkened, clipped round.
    region = img.crop((x0, y0, x0 + diameter, y0 + diameter)).filter(ImageFilter.GaussianBlur(diameter * 0.04))
    region.alpha_composite(Image.new('RGBA', region.size, OFF_BLACK + (120,)))
    mask = Image.new('L', region.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    region.putalpha(mask)
    img.alpha_composite(region, (x0, y0))
    edge = Image.new('RGBA', (diameter, diameter), (0, 0, 0, 0))
    ImageDraw.Draw(edge).ellipse((0, 0, diameter - 1, diameter - 1), outline=OFF_WHITE + (80,),
                                 width=max(2, diameter // 220))
    img.alpha_composite(edge, (x0, y0))

    seats = LAYOUTS[len(cast)]
    # The host goes on last, so their ring sits over any neighbor it touches.
    for i in list(range(1, len(cast))) + [0]:
        fx, fy, fd = seats[i]
        d = int(diameter * fd)
        bx, by = int(x0 + fx * diameter - d / 2), int(y0 + fy * diameter - d / 2)
        _soft_shadow(img, (bx, by + d * 0.05, bx + d, by + d * 1.05), 90, d * 0.05)
        img.alpha_composite(_bubble(cast[i], d, ringed=(i == 0)), (bx, by))


# ---- the show cover ----------------------------------------------------------------------------

def make_cover(out: Path = EPISODES / 'cover.png') -> Path:
    """3000x3000: the show name over felt, and the whole fixed cast in one bubble."""
    size = 3000
    cast = load_cast()
    # The felt's grain is what makes it felt, but at 3000px a lossless PNG of it runs past 10 MB,
    # and podcast apps fetch this on every directory listing. Softening the grain before anything
    # sharp goes on top, then quantizing on save, keeps the cover near 1 MB and reading the same.
    img = felt(size, 1, 'a').filter(ImageFilter.GaussianBlur(5))
    scrim(img, top=0.6, bottom=0.45, left=0.25)
    d = ImageDraw.Draw(img)
    margin = 230

    d.text((margin, 250), 'WEEKLY  ·  EVERY TUESDAY', font=font('mono', 78, 500), fill=OFF_WHITE, anchor='lt')
    small = fit(SMALL, 'sans', 230, 500, size - 2 * margin)
    big = fit(BIG, 'sans', 520, 600, size - 2 * margin)
    d.text((margin, 420), SMALL, font=small, fill=OFF_WHITE, anchor='lt')
    d.text((margin - big.size * 0.04, 420 + small.size * 1.1), BIG, font=big, fill=OFF_WHITE, anchor='lt')

    names = [cast.get('anchor', {}).get('name', 'Brooke')]
    names += [s.get('name', '') for s in cast.get('segments', {}).values()]
    cluster(img, size - margin - 700, size - margin - 700, 1400, names)

    d.text((margin, size - margin), 'READ BY', font=font('mono', 70, 500), fill=LIGHT_GRAY, anchor='ls')
    d.text((margin, size - margin + 100), 'DEEPGRAM FLUX', font=font('mono', 70, 500), fill=OFF_WHITE, anchor='ls')
    if CREDIT:
        d.text((size - margin, size - 110), CREDIT, font=font('sans', 64), fill=LIGHT_GRAY, anchor='rs')
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) \
        .save(out, optimize=True)
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
        return f"{s:%B} {s.year}", ''  # 'September 2026' on one line
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


def _release_day(episode: dict, ep_dir: Path) -> date:
    for raw in (episode.get('release_date'), episode.get('id'), ep_dir.name):
        try:
            return date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
    return datetime.now(timezone.utc).date()


def make_episode_art(ep_dir: Path) -> Path:
    """Write <ep_dir>/art.jpg, 1400x1400: the week's date over its felt, the cast's group bubble,
    and the segments that aired with who read each one."""
    ep_dir = Path(ep_dir)
    episode = json.loads((ep_dir / 'episode.json').read_text(encoding='utf-8'))
    cast = load_cast()

    segments = _aired_segments(ep_dir)
    if segments:
        rows = [(SHORT_NAMES.get(s, s), voice_for(s, cast)[0]) for s in segments]
    else:
        rows = [('This week', episode.get('host') or voice_for('', cast)[0])]

    host = episode.get('host') or voice_for('', cast)[0]
    names = [host] + [n for n in (episode.get('hosts') or []) if n != host]
    names += [n for _, n in rows if n not in names]

    size = 1400
    img = felt(size, colorway(_release_day(episode, ep_dir)), 'd')
    scrim(img, top=0.62, bottom=0.55, left=0.3)
    d = ImageDraw.Draw(img)
    margin = 104

    d.text((margin, 96), SHOW_NAME.upper(), font=font('mono', 34, 500), fill=OFF_WHITE, anchor='lt')
    if CREDIT:
        d.text((size - margin, size - 56), CREDIT, font=font('sans', 30), fill=LIGHT_GRAY, anchor='rs')

    dates, year = _date_range(episode)
    fdate = fit(dates, 'sans', 190, 600, size - 2 * margin)
    d.text((margin - fdate.size * 0.05, 168), dates, font=fdate, fill=OFF_WHITE, anchor='lt')
    date_bottom = d.textbbox((margin, 168), dates, font=fdate, anchor='lt')[3]
    if year:
        d.text((margin, date_bottom + 30), year, font=font('mono', 56, 400), fill=OFF_WHITE, anchor='lt')

    bubble_d = 640
    cluster(img, size - margin - bubble_d / 2 + 30, size - margin - bubble_d / 2 + 20, bubble_d, names[:4])

    # The run of show, bottom left: one line per segment that aired, with who read it.
    label_f = font('mono', 32, 500)
    voice_f = font('mono', 28, 400)
    pitch = 58
    y = size - margin - pitch * (len(rows) - 1)
    for label, name in rows:
        d.text((margin, y), '+', font=label_f, fill=FUCHSIA, anchor='ls')
        lx = margin + label_f.getlength('+ ')
        d.text((lx, y), label.upper(), font=label_f, fill=OFF_WHITE, anchor='ls')
        d.text((lx + label_f.getlength(label.upper() + '  '), y), name, font=voice_f, fill=LIGHT_GRAY, anchor='ls')
        y += pitch

    out = ep_dir / 'art.jpg'
    img.convert('RGB').save(out, quality=86, optimize=True, progressive=True, subsampling=0)
    return out


# ---- CLI ---------------------------------------------------------------------------------------

def _shown(path: Path) -> Path:
    """The path relative to the repo when it is inside it, else as given (EPISODES_DIR on Fly)."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


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
        print(f'wrote {_shown(out)} ({out.stat().st_size // 1024} KB)')
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
        print(f'wrote {_shown(out)} ({out.stat().st_size // 1024} KB)')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
