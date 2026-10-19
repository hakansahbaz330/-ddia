"""Düzen denetimi: iPhone çentik payı (safe-area) emüle edilerek bülten kartlarındaki kutuların kaymadığını/kesilmediğini doğrular.
Neden: headless Chrome'da safe-area 0'dır; `top: env(safe-area-inset-top)` içeren bir kural yanlışlıkla kutulara uygulanınca
yalnızca gerçek telefonda kutular aşağı kayıp `overflow: hidden` ile kesiliyordu (sınıf adı çakışması: .top).
Kullanım: python mobile/check_layout.py mobile/dist/oran-arsivi.html [chromium_yolu]   (playwright gerekir)"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

JS = """() => { const res = {cells: 0, clipped: 0, shifted: 0};
  document.querySelectorAll('#wkList .mc').forEach(card => { const cr = card.getBoundingClientRect();
    card.querySelectorAll('.mc-cell').forEach(c => { res.cells++; const r = c.getBoundingClientRect();
      if (r.bottom > cr.bottom + 1 || r.top < cr.top - 1) res.clipped++;
      const g = c.parentElement.getBoundingClientRect(); if (Math.abs(r.top - g.top) > 12) res.shifted++; }); });
  return res; }"""


async def main(html: Path, chrome: str | None) -> int:
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=chrome, args=["--no-sandbox"]) if chrome else await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = await ctx.new_page()
        cdp = await ctx.new_cdp_session(pg)
        await cdp.send("Emulation.setSafeAreaInsetsOverride", {"insets": {"top": 47, "bottom": 34, "left": 0, "right": 0}})
        await pg.goto(html.resolve().as_uri())
        await pg.wait_for_selector("#wkList .mc", timeout=20000)
        res = await pg.evaluate(JS)
        await b.close()
    print(res)
    return 1 if res["clipped"] or res["shifted"] or not res["cells"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)))
