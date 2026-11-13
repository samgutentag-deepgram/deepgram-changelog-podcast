"""Render the README figures from docs/how-it-works.html.

Usage: python3 docs/render_figures.py

Each figure is one section of the guide (the pipeline is .overview, the architecture map is
.map), shown alone on the guide's own page color and screenshotted at 2x in the light and the
dark theme. The guide is the source: change the figure there, then run this. Output sizes are
fixed so the README layout never shifts:

    docs/images/pipeline-{light,dark}.png          2040 x 890
    docs/images/architecture-map-{light,dark}.png  2040 x 1494

Needs Playwright for Python and Google Chrome (`pip install playwright`); the brand fonts come
from Google Fonts, so it needs a network connection.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DOCS = Path(__file__).resolve().parent
GUIDE = DOCS / 'how-it-works.html'
OUT = DOCS / 'images'
SCALE = 2
WIDTH = 1020                     # CSS px; 2040 px at 2x
FIGURES = {                      # output name -> (section selector, CSS height)
    'pipeline': ('section.overview', 445),
    'architecture-map': ('section.map', 747),
}

ISOLATE = """
  body { margin: 0; }
  .wrap { max-width: none; width: %(w)dpx; padding: 0; margin: 0; }
  .wrap > * { display: none !important; }
  .wrap > %(sel)s {
    display: grid !important; align-content: center; box-sizing: border-box;
    width: %(w)dpx; height: %(h)dpx; padding: 0 62px; border-top: none;
  }
"""


async def render() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        try:
            for theme in ('light', 'dark'):
                ctx = await browser.new_context(viewport={'width': WIDTH, 'height': 900},
                                                device_scale_factor=SCALE, color_scheme=theme)
                page = await ctx.new_page()
                await page.goto(GUIDE.as_uri(), wait_until='networkidle')
                await page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
                await page.evaluate('document.fonts.ready')
                if not await page.evaluate("""() => document.fonts.check('600 16px "Work Sans"')
                                                  && document.fonts.check('16px "Azeret Mono"')"""):
                    raise SystemExit('brand fonts did not load (Google Fonts unreachable?)')
                for name, (sel, height) in FIGURES.items():
                    style = await page.add_style_tag(content=ISOLATE % {'w': WIDTH, 'h': height, 'sel': sel})
                    el = page.locator(sel)
                    # The section is a fixed box; if its content outgrew it, say so rather than clip.
                    need = await el.evaluate('e => e.scrollHeight')
                    if need > height:
                        raise SystemExit(f'{name}: content is {need}px tall, the figure is {height}px')
                    out = OUT / f'{name}-{theme}.png'
                    await el.screenshot(path=str(out))
                    print(f'wrote {out.relative_to(DOCS.parent)}')
                    await style.evaluate('s => s.remove()')
                await ctx.close()
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(render())
