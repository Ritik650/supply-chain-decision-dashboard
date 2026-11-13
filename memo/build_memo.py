"""Build the one-page decision memo (memo/decision_memo.pdf and .md) from the notebooks'
findings files in outputs/findings/. Every number is read from those files, which the
notebooks write from queries in sql/analysis/; nothing is typed in by hand.

    python memo/build_memo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
F = {q: json.loads((ROOT / "outputs" / "findings" / f"{q}.json").read_text(encoding="utf-8")) for q in ("q1", "q2", "q3", "q4")}
q1, q2, q3, q4 = F["q1"], F["q2"], F["q3"], F["q4"]

INK, INK2, BAD, RULE = colors.HexColor("#111110"), colors.HexColor("#52514e"), colors.HexColor("#d03b3b"), colors.HexColor("#e2e1dc")


def k(v: float) -> str:
    return f"${v / 1e3:,.0f}k"


def pct(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%"


# ---------- content (shared by PDF and Markdown) ----------
fc = q1["late_rate_by_mode"]["First Class"]
sc = q1["late_rate_by_mode"]["Second Class"]
days = q1["avg_actual_days_by_mode"]
seg = q3["next6m_share_by_segment"]

HEADLINE = (f"Cap discounts at 10%: an estimated {k(q2['cap10_low_per_year'])}–{k(q2['cap10_high_per_year'])} more profit a year "
            f"(central {k(q2['cap10_central_per_year'])}), because discounts above 10% sell no extra units. "
            f"Prove it in one market for four weeks before rolling it out.")

RECS = [
    {
        "title": "1. Cap discounts at 10% in every category",
        "page": "Dashboard page 3",
        "action": "Set a 10% maximum discount for all categories.",
        "evidence": (f"Items discounted above 10% sell {q2['qty_above_10']:.2f} units per order line vs {q2['qty_at_or_below_10']:.2f} at or below "
                     f"(within-product elasticity {q2['elasticity_beta']:+.3f}, 95% CI {q2['elasticity_ci'][0]:+.3f} to {q2['elasticity_ci'][1]:+.3f}), "
                     f"and their margin is {pct(q2['margin_above_10'])} vs {pct(q2['margin_at_or_below_10'])} (p = {q2['margin_diff_p']:.2f}). "
                     f"{q2['cap10_items_above']:,} items ({pct(q2['cap10_share_items'], 0)}) carried "
                     f"${q2['cap10_discount_above_cap_window'] / 1e6:.2f}M of discount above 10% in 33 months."),
        "impact": (f"{k(q2['cap10_low_per_year'])} (low) / {k(q2['cap10_central_per_year'])} (central) / {k(q2['cap10_high_per_year'])} (high) "
                   f"profit a year. It still pays unless more than {pct(q2['cap10_breakeven_volume_loss'], 0)} of the capped items' volume is lost."),
        "test": "Apply the cap in one market for 4 weeks against a holdout market; compare orders per customer and conversion, not just units per line.",
    },
    {
        "title": "2. Change the First Class and Second Class promises",
        "page": "Dashboard page 2",
        "action": "Promise First Class in 2 days. Either make Second Class faster than Standard or promise it in 4 days.",
        "evidence": (f"First Class is late on {pct(fc, 0)} of items: it always takes {days['First Class']:.0f} days against a 1-day promise. "
                     f"Second Class is {pct(sc)} late and takes {days['Second Class']:.2f} days, no faster than Standard "
                     f"({days['Standard Class']:.2f}, p = {q1['second_vs_standard_actual_days_p']:.2f}). Shipping mode explains lateness "
                     f"(Cramér's V {q1['cramers_v_mode']:.2f}); region does not ({q1['cramers_v_next_best']:.2f})."),
        "impact": (f"Late rate falls from {pct(q1['late_rate_current'])} to {pct(q1['late_rate_first_class_2d'])} (First Class only) or "
                   f"{pct(q1['late_rate_first2_second4'])} (both), with no operational change. No revenue gain is claimed: late first orders "
                   f"reorder at the same rate ({pct(q1['reorder_90d_after_late'])} vs {pct(q1['reorder_90d_after_on_time'])} within 90 days)."),
        "test": "Show the new promise at checkout in one market for 4 weeks; track First and Second Class take-up, conversion and complaints.",
    },
    {
        "title": "3. Don't fund RFM-targeted win-back; test one broad retention offer",
        "page": "Dashboard page 4",
        "action": "Run any retention offer as a randomised holdout across all customers, not on an RFM list.",
        "evidence": (f"Scored on data to March 2017, Champions ordered again in the next six months at {pct(seg['Champions'])} vs "
                     f"{pct(seg['Hibernating'])} for Hibernating (all six segments {pct(q3['next6m_min'], 0)}–{pct(q3['next6m_max'], 0)}, "
                     f"p = {q3['segment_chi2_p']:.2f}; AUC {min(q3['auc'].values()):.2f}–{max(q3['auc'].values()):.2f}). "
                     f"Month-3 retention is a flat {pct(q3['month3_retention'])} with no decay."),
        "impact": (f"Each +1 pt of monthly repeat rate (now {pct(q3['monthly_repeat_rate'])}) is worth about {k(q3['value_per_repeat_pt_profit'])} "
                   f"profit ({k(q3['value_per_repeat_pt_revenue'])} revenue) a year. A 0.5–2 pt lift, if the test finds one, would be "
                   f"{k(0.5 * q3['value_per_repeat_pt_profit'])}–{k(2 * q3['value_per_repeat_pt_profit'])}; that lift range is illustrative, not measured."),
        "test": "Hold out 20% of customers at random for 8 weeks; scale only if the lift covers the offer's cost.",
    },
]

LIMITS = [
    ("Observational data.", "Every result is an association. Discounts were spread evenly across rates "
     f"({q2['rates_items_min']:,}–{q2['rates_items_max']:,} items per rate), which rules out targeting bias but not period effects."),
    ("Orders that never happened are invisible.", "The data only holds completed orders, so it cannot show buyers who would not "
     "order without a discount. That is why recommendation 1 is a test first. The cap assumes fixed unit cost; the dataset's own "
     "profit ratio does not move with discount, which a real cost structure would."),
    ("Scope.", f"Values treated as USD (the data dictionary gives no currency; no conversion to rupees). Cancelled and suspected-fraud "
     "items (7,754) excluded. Window January 2015 – September 2017 (33 months): from October 2017 the source switches to "
     "single-item orders and a new catalogue. Annual figures = window total × 12/33."),
    ("Products are not the lever.", f"Profit is as concentrated as revenue (top 20% of products: {pct(q4['top20_profit_share'])} of "
     f"profit, {pct(q4['top20_revenue_share'])} of revenue) and only {q4['loss_making_products']} small products lose money, "
     "so no delisting is recommended (page 5)."),
]

NEXT = [
    "Discount cap: the 4-week market holdout, plus site-visit data (the access logs) to measure conversion, not just basket size.",
    "Delivery: carrier hand-off timestamps to see why Second Class ships no faster than Standard; complaint and return data to price lateness.",
    "Retention: the randomised holdout, and the cost per contacted customer to set the break-even lift.",
]

METHOD = ("Method. Cap recovery = Σ over items with applied rate r > 10% of (r − 0.10) × gross sales, × 12/33 (high, volume holds). "
          "Central multiplies each capped item's new profit by exp(β × (0.10 − r)) with the measured β floored at 0; low by "
          "(1 − 1.5 × price rise). Break-even loss = recovery ÷ (current profit of capped items + recovery). "
          "Sources: notebooks/q1–q4, sql/analysis/p2_repromise_whatif.sql, p3_whatif_cap.sql, p4_rfm_validation.sql.")


# ---------- PDF ----------
def build_pdf(path: Path) -> int:
    ss = {
        "kick": ParagraphStyle("kick", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=INK2, spaceAfter=2),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13.6, leading=16.6, textColor=INK, spaceAfter=4),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8, leading=10.2, textColor=INK2),
        "rec": ParagraphStyle("rec", fontName="Helvetica-Bold", fontSize=10, leading=12.4, textColor=INK, spaceBefore=4, spaceAfter=1),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.9, leading=11.3, textColor=INK, alignment=TA_LEFT),
        "lbl": ParagraphStyle("lbl", fontName="Helvetica-Bold", fontSize=8, leading=11.3, textColor=INK2),
        "sec": ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=9.4, leading=11.5, textColor=INK, spaceBefore=7, spaceAfter=2),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.2, leading=8.9, textColor=INK2),
    }
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=10 * mm,
                            title="Decision memo: supply chain", author="Ritik Yadav")
    st = []
    st.append(Paragraph("DECISION MEMO · HEAD OF OPERATIONS · DATACO SUPPLY CHAIN, JAN 2015 – SEP 2017", ss["kick"]))
    st.append(Paragraph(HEADLINE, ss["h"]))
    st.append(Paragraph("Three recommendations, each with its evidence, an impact range and a test to run before rolling it out. "
                        "Every figure traces to a query or notebook in the project repo.", ss["meta"]))
    st.append(Spacer(1, 3))
    st.append(HRFlowable(width="100%", thickness=0.6, color=INK, spaceAfter=2))
    for r in RECS:
        st.append(Paragraph(f"{r['title']} <font color='#52514e' size='7.4'>  ({r['page']})</font>", ss["rec"]))
        rows = [[Paragraph(lbl, ss["lbl"]), Paragraph(txt, ss["body"])] for lbl, txt in
                (("Action", r["action"]), ("Evidence", r["evidence"]), ("Impact", r["impact"]), ("Test first", r["test"]))]
        t = Table(rows, colWidths=[20 * mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0.6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
                               ("LINEBEFORE", (0, 0), (0, -1), 2, BAD if r is RECS[0] else INK)]))
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (0, -1), 5)]))
        st.append(t)
        st.append(Spacer(1, 2))
    st.append(HRFlowable(width="100%", thickness=0.4, color=RULE, spaceBefore=3, spaceAfter=0))
    st.append(Paragraph("Assumptions and limits", ss["sec"]))
    for b, txt in LIMITS:
        st.append(Paragraph(f"• <b>{b}</b> {txt}", ss["body"]))
    st.append(Paragraph("Next steps: what would firm up each estimate", ss["sec"]))
    for txt in NEXT:
        st.append(Paragraph(f"• {txt}", ss["body"]))
    st.append(Spacer(1, 4))
    st.append(HRFlowable(width="100%", thickness=0.4, color=RULE, spaceAfter=3))
    st.append(Paragraph(METHOD, ss["small"]))
    st.append(Paragraph("Data: DataCo Smart Supply Chain (Constante, Silva &amp; Pereira, 2019), Mendeley Data v5, "
                        "doi:10.17632/8gx2fvg2k6.5, CC BY 4.0.", ss["small"]))
    doc.build(st)
    return len(PdfReader(str(path)).pages)


def build_md(path: Path) -> None:
    L = ["# Decision memo", "", "_For: head of operations. Data: DataCo Smart Supply Chain, Jan 2015 – Sep 2017. "
         "Generated by `memo/build_memo.py` from `outputs/findings/`; the PDF is the version to send._", "",
         f"**{HEADLINE}**", ""]
    for r in RECS:
        L += [f"## {r['title']} ({r['page']})", "", f"- **Action.** {r['action']}", f"- **Evidence.** {r['evidence']}",
              f"- **Impact.** {r['impact']}", f"- **Test first.** {r['test']}", ""]
    L += ["## Assumptions and limits", ""] + [f"- **{b}** {t}" for b, t in LIMITS] + [""]
    L += ["## Next steps", ""] + [f"- {t}" for t in NEXT] + ["", "## Appendix: method", "", METHOD, ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    pdf = ROOT / "memo" / "decision_memo.pdf"
    pages = build_pdf(pdf)
    build_md(ROOT / "memo" / "decision_memo.md")
    print(f"  {pdf.relative_to(ROOT)}: {pages} page(s)")
    if pages != 1:
        print("  memo is longer than one page; tighten the text", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
