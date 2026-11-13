"""Load the web dashboard in a headless browser and check that the numbers it computes
for the default view match the sql/analysis/ queries (dashboard/web/data/reference.json).
Also saves a screenshot of every page to dashboard/screenshots/.

    python scripts/check_dashboard.py              # check + screenshots (light)
    python scripts/check_dashboard.py --dark       # screenshots in dark mode too

Needs Playwright with Chromium: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "dashboard" / "web"
SHOTS = ROOT / "dashboard" / "screenshots"
PAGES = ["summary", "delivery", "discounts", "customers", "products", "definitions"]


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.func.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def close(a: float, b: float, rel: float = 1e-4, abs_: float = 1e-6) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dark", action="store_true")
    args = ap.parse_args()
    ref = json.loads((WEB / "data" / "reference.json").read_text(encoding="utf-8"))
    srv, port = serve()
    SHOTS.mkdir(parents=True, exist_ok=True)
    failures, checks = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        for name in PAGES:
            page.goto(f"http://127.0.0.1:{port}/#{name}")
            page.wait_for_function("() => window.__dashboard && window.__dashboard.ready", timeout=20000)
            page.wait_for_timeout(300)
            page.screenshot(path=str(SHOTS / f"{PAGES.index(name) + 1}_{name}.png"), full_page=True)
        d = page.evaluate("() => window.__dashboard")

        def check(label, got, want, rel=1e-4):
            nonlocal checks
            checks += 1
            if not close(float(got), float(want), rel=rel):
                failures.append(f"{label}: dashboard {got} vs SQL {want}")

        kpi = next(r for r in ref["p1_kpi_cards"] if r["period"] == "window")
        t = d["summary"]["totals"]
        check("revenue", t["rev"], kpi["revenue"])
        check("profit", t["prof"], kpi["profit"])
        check("margin", t["margin"], kpi["profit_margin"])
        check("late rate", t["lateRate"], kpi["late_rate"])
        check("orders", t["orders"], kpi["orders"])
        check("avg order value", t["aov"], kpi["avg_order_value"])
        for m in ref["p2_late_by_mode"]:
            got = next(x for x in d["delivery"]["modes"] if x["name"] == m["shipping_mode"])
            check(f"late rate {m['shipping_mode']}", got["lateRate"], m["late_rate"])
        for b in ref["p3_margin_by_band"]:
            got = next(x for x in d["discounts"]["bands"] if x["name"] == b["discount_band"])
            check(f"margin {b['discount_band']}", got["margin"], b["profit_margin"])
            check(f"units {b['discount_band']}", got["avgQty"], b["avg_quantity"])
        cap = next(r for r in ref["p3_whatif_cap"] if abs(r["cap"] - 0.10) < 1e-9)
        check("cap 10% high / yr", d["discounts"]["cap10"]["hi"], cap["profit_recovered_per_year"], rel=1e-3)
        check("cap 10% items", d["discounts"]["cap10"]["items"], cap["items_above_cap"])
        check("cap 10% break-even", d["discounts"]["cap10"]["breakeven"], cap["breakeven_volume_loss"], rel=1e-3)
        check("month-3 retention", d["customers"]["m3"], ref["p4_month3_retention"][0]["month3_retention"])
        for s in ref["p4_segment_summary"]:
            got = next(x for x in d["customers"]["segRows"] if x["name"] == s["rfm_segment"])
            check(f"customers {s['rfm_segment']}", got["n"], s["customers"])
            check(f"revenue share {s['rfm_segment']}", got["revShare"], s["revenue_share"])
        p5 = ref["p5_kpis"][0]
        check("top 20% profit share", d["products"]["topProfShare"], p5["top_20pct_profit_share"])
        check("top 20% revenue share", d["products"]["topRevShare"], p5["top_20pct_revenue_share"])
        check("loss-making products", d["products"]["losers"], p5["loss_making_products"])

        # filters, what-if and theme interactions don't throw
        page.goto(f"http://127.0.0.1:{port}/#discounts")
        page.wait_for_function("() => window.__dashboard && window.__dashboard.ready")
        page.select_option("#fMarket", label="Europe")
        page.fill("#capSlider", "5")
        page.dispatch_event("#capSlider", "input")
        page.select_option("#fSegment", label="Corporate")
        page.click("#resetBtn")
        if args.dark:
            page.emulate_media(color_scheme="dark")
            page.goto(f"http://127.0.0.1:{port}/#summary")
            page.wait_for_function("() => window.__dashboard && window.__dashboard.ready")
            page.wait_for_timeout(200)
            page.screenshot(path=str(SHOTS / "dark_1_summary.png"), full_page=True)
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.goto(f"http://127.0.0.1:{port}/#summary")
        mobile.wait_for_function("() => window.__dashboard && window.__dashboard.ready")
        overflow = mobile.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        mobile.screenshot(path=str(SHOTS / "mobile_summary.png"), full_page=True)
        if overflow > 1:
            failures.append(f"horizontal page scroll at 390px width: {overflow}px")
        browser.close()
    srv.shutdown()
    for e in errors:
        failures.append(f"browser error: {e}")
    print(f"{checks} numbers checked against sql/analysis/; {len(failures)} problem(s). Screenshots in {SHOTS.relative_to(ROOT)}")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
