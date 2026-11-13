"""Record a ~25 second demo GIF of the web dashboard (dashboard/demo.gif).

Scripted tour in a headless browser: the five pages, a filter change and the discount-cap
slider. Frames are screenshots; ffmpeg turns them into a palette-optimised GIF.

    python scripts/make_demo_gif.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_dashboard import serve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "demo.gif"
FPS = 4


def main() -> int:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    srv, port = serve()
    frames = Path(tempfile.mkdtemp(prefix="scdd_gif_"))
    n = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 760}, device_scale_factor=1)

        def snap(seconds: float = 0.25):
            nonlocal n
            for _ in range(max(1, round(seconds * FPS))):
                page.screenshot(path=str(frames / f"f{n:04d}.png"))
                n += 1

        def goto(name: str):
            page.evaluate(f"location.hash = '#{name}'")
            page.wait_for_function("() => window.__dashboard && window.__dashboard.ready")
            page.wait_for_timeout(150)

        def scroll(y: int, hold: float):
            page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'instant'}})")
            page.wait_for_timeout(100)
            snap(hold)

        page.goto(f"http://127.0.0.1:{port}/#summary")
        page.wait_for_function("() => window.__dashboard && window.__dashboard.ready")
        page.wait_for_timeout(400)
        snap(3.0)
        scroll(420, 2.0)

        goto("delivery"); scroll(0, 2.5); scroll(560, 2.0); scroll(1150, 2.0)
        page.select_option("#pSecond", "3"); snap(0.75); page.select_option("#pSecond", "4"); snap(1.0)

        goto("discounts"); scroll(0, 2.0); scroll(820, 0.75)
        for v in (10, 8, 6, 4, 6, 8, 10, 13, 16, 13, 10):
            page.fill("#capSlider", str(v)); page.dispatch_event("#capSlider", "input"); snap(0.25)
        snap(1.0)

        goto("customers"); scroll(0, 2.0); scroll(600, 1.5)
        goto("products"); scroll(0, 2.0)
        page.select_option("#fMarket", label="Europe"); page.wait_for_timeout(150); scroll(0, 2.0)
        page.click("#resetBtn"); goto("summary"); scroll(0, 1.5)
        browser.close()
    srv.shutdown()

    palette = frames / "palette.png"
    common = ["-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%04d.png")]
    scale = "scale=960:-1:flags=lanczos"
    subprocess.run(["ffmpeg", *common, "-vf", f"{scale},palettegen=max_colors=128:stats_mode=diff", str(palette)], check=True)
    subprocess.run(["ffmpeg", *common, "-i", str(palette), "-lavfi",
                    f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", str(OUT)], check=True)
    shutil.rmtree(frames, ignore_errors=True)
    print(f"  {OUT.relative_to(ROOT)}: {n} frames, {n / FPS:.0f}s, {OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
