"""
PDF of the Weekly Sectors report, laid out like the weekly market-education report the user shares: a navy cover,
"this week at a glance" with automatically written insights, sector rankings with bars, a scorecard with the
daily / weekly / monthly RSI verdict, one page per sector with colour-coded signals, top movers, laggards, the four
study buckets and the method + disclaimer. Built with reportlab from the report the page already shows.
"""
from __future__ import annotations

import datetime as dt
import io
from xml.sax.saxutils import escape as esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

W, H = A4
M = 16 * mm
CONTENT_W = W - 2 * M

NAVY = colors.HexColor("#15315A")
NAVY_SUB = colors.HexColor("#9DB1D1")
INK = colors.HexColor("#1B2638")
MUTED = colors.HexColor("#5B677D")
LINE = colors.HexColor("#D9DFE8")
SOFT = colors.HexColor("#EEF1F6")
GREEN, GREEN_BG, GREEN_INK = colors.HexColor("#1E9E5A"), colors.HexColor("#E3F3E6"), colors.HexColor("#17703A")
RED, RED_BG, RED_INK = colors.HexColor("#D2453D"), colors.HexColor("#FBE3E1"), colors.HexColor("#A42A22")
AMBER, AMBER_BG, AMBER_INK = colors.HexColor("#E0A12B"), colors.HexColor("#FBF0D3"), colors.HexColor("#8A5A00")
BLUE, BLUE_BG, BLUE_INK = colors.HexColor("#2F6DB5"), colors.HexColor("#DCE8F7"), colors.HexColor("#1F4E8C")
SIGNAL = {"Leader": (GREEN_BG, GREEN_INK), "Turning up": (BLUE_BG, BLUE_INK), "Fading": (AMBER_BG, AMBER_INK),
          "Laggard": (RED_BG, RED_INK), "N/A": (SOFT, MUTED)}
VERDICT = {"STRONG": (GREEN_BG, GREEN_INK), "MIXED": (AMBER_BG, AMBER_INK), "WEAK": (RED_BG, RED_INK), "N/A": (SOFT, MUTED)}
FOOTER = "A Group Scanner  |  Weekly Sector Report  |  Educational only, not investment advice"


def _style(name, size=10, leading=None, color=INK, bold=False, align=TA_LEFT, space_after=0):
    return ParagraphStyle(name, fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.32, textColor=color, alignment=align, spaceAfter=space_after)


S_BODY = _style("body", 10.5, color=INK)
S_SMALL = _style("small", 8.5, color=MUTED)
S_CELL = _style("cell", 9, color=INK)
S_CELL_B = _style("cellb", 9, color=INK, bold=True)
S_H2 = _style("h2", 12.5, color=NAVY, bold=True, space_after=4)
S_INSIGHT_T = _style("it", 12, color=NAVY, bold=True)
S_INSIGHT = _style("ib", 10.5, color=INK)


def pct(v, digits=2) -> str:
    return "n/a" if v is None else f"{v:+.{digits}f}"


def nice_date(iso) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(iso)


def colour_of(v) -> colors.Color:
    return MUTED if v is None else GREEN_INK if v > 0 else RED_INK if v < 0 else INK


class Bar(Flowable):
    """A horizontal bar for the ranking tables (negative values grow to the left of a zero line)."""

    def __init__(self, value: float | None, max_abs: float, fill, width: float = 70 * mm, height: float = 3.2 * mm):
        super().__init__()
        self.value, self.max_abs, self.fill, self.width, self.height = value, max_abs or 1, fill, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        if self.value is None:
            return
        zero = self.width * 0.18
        span = self.width - zero
        length = abs(self.value) / self.max_abs * span
        self.canv.setFillColor(self.fill)
        if self.value >= 0:
            self.canv.rect(zero, 0, max(length, 1.5), self.height, stroke=0, fill=1)
        else:
            self.canv.rect(zero - min(length, zero), 0, min(length, zero), self.height, stroke=0, fill=1)


def header_bar(title: str, subtitle: str | None = None) -> Table:
    content = [Paragraph(title, _style("hb", 16, color=colors.white, bold=True))]
    if subtitle:
        content.append(Paragraph(subtitle, _style("hs", 9.5, color=NAVY_SUB)))
    t = Table([[content]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return t


def kpi_strip(items: list[tuple[str, str, colors.Color]]) -> Table:
    cells = [[Paragraph(label, _style("kl", 8, color=MUTED)), Paragraph(value, _style("kv", 15, color=col, bold=True))]
             for label, value, col in items]
    t = Table([cells], colWidths=[CONTENT_W / len(items)] * len(items))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def note_box(html: str) -> Table:
    t = Table([[Paragraph(html, S_BODY)]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return t


def grid(rows: list[list], widths: list[float], extra: list | None = None, zebra: bool = False) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]))
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def insights(report: dict) -> list[tuple[str, str]]:
    secs = report.get("sectors", [])
    s = report.get("summary", {})
    out: list[tuple[str, str]] = []
    strong = s.get("strong_sectors") or []
    if strong:
        out.append((f"{len(strong)} sector{'s are' if len(strong) > 1 else ' is'} STRONG on RSI",
                    f"{', '.join(strong)}: daily, weekly and monthly RSI(14) all above 60."))
    else:
        out.append(("No sector is STRONG on RSI", "No sector index has its daily, weekly and monthly RSI all above 60 this week."))
    ranked = [x for x in secs if x.get("rank_1w") and x.get("rank_1m")]
    if ranked:
        top = min(ranked, key=lambda x: (x["rank_1w"] + x["rank_1m"]) / 2)
        both = " - #1 on both 1W and 1M" if top["rank_1w"] == 1 and top["rank_1m"] == 1 else ""
        out.append((f"{top['label']} leads{both}",
                    f"{top['label']} returned {pct(top['r1w'])}% over the week (#{top['rank_1w']}) and {pct(top['r1m'])}% over the month (#{top['rank_1m']})."))
        swing = max(ranked, key=lambda x: abs(x["rank_1w"] - x["rank_1m"]))
        if abs(swing["rank_1w"] - swing["rank_1m"]) >= 4:
            better = "the week" if swing["rank_1w"] < swing["rank_1m"] else "the month"
            out.append((f"{swing['label']}: a split picture",
                        f"#{swing['rank_1w']} on 1W but #{swing['rank_1m']} on 1M - stronger over {better}. Check both horizons."))
        last = max(ranked, key=lambda x: (x["rank_1w"] + x["rank_1m"]) / 2)
        out.append((f"{last['label']} is the weakest",
                    f"{pct(last['r1w'])}% on the week (#{last['rank_1w']}) and {pct(last['r1m'])}% on the month (#{last['rank_1m']})."))
    movers = report.get("top_movers") or []
    if movers:
        a = movers[0]
        txt = f"{a['symbol']} beats {a['sector']} by {pct(a['vs1w'])}pp (1W) and {pct(a['vs1m'])}pp (1M)"
        if len(movers) > 1:
            b = movers[1]
            txt += f"; {b['symbol']} beats {b['sector']} by {pct(b['vs1w'])}pp and {pct(b['vs1m'])}pp"
        out.append(("Stock-level edge", txt + "."))
    out = [(esc(t), esc(x)) for t, x in out]
    out.append(("Breadth", f"{s.get('leaders')} of {s.get('rows')} stock rows beat their sector on both 1W and 1M; "
                            f"{s.get('laggards')} trail it on both."))
    return out


def _cover(canvas, doc, report: dict) -> None:
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, stroke=0, fill=1)
    x = M + 4
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 34)
    for i, line in enumerate(["Sector & Stock", "Relative Strength", "Report"]):
        canvas.drawString(x, H * 0.66 - i * 42, line)
    canvas.setFillColor(NAVY_SUB)
    canvas.setFont("Helvetica", 15)
    end = report.get("end_date") or report.get("as_of")
    try:
        end_txt = dt.date.fromisoformat(end).strftime("%d %b %Y")
    except (TypeError, ValueError):
        end_txt = str(end)
    canvas.drawString(x, H * 0.66 - 3 * 42 - 6, "Weekly market education report")
    canvas.drawString(x, H * 0.66 - 3 * 42 - 26, f"Week ending {end_txt}")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(x, H * 0.36, "A Group Scanner")
    canvas.setFillColor(NAVY_SUB)
    canvas.setFont("Helvetica", 9.5)
    labels = " · ".join(s["label"] for s in report.get("sectors", []))
    words, line, y = labels.split(" "), "", H * 0.36 - 20
    for w_ in words:
        if canvas.stringWidth(line + " " + w_, "Helvetica", 9.5) > CONTENT_W - 8:
            canvas.drawString(x, y, line.strip())
            y -= 13
            line = ""
        line += " " + w_
    canvas.drawString(x, y, line.strip())
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(x, M + 18, "For educational purposes only. Not investment advice, and not a recommendation to buy, sell or hold")
    canvas.drawString(x, M + 6, "any security. Data: Angel One daily closes; sector lists: NSE. See the method and disclaimer at the end.")
    canvas.restoreState()


def _page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, H - 5, W, 5, stroke=0, fill=1)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, 10 * mm, FOOTER)
    canvas.drawRightString(W - M, 10 * mm, str(doc.page))
    canvas.restoreState()


def build_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=18 * mm,
                          title="Weekly Sector & Stock Relative Strength", author="A Group Scanner")
    frame = Frame(M, 18 * mm, CONTENT_W, H - M - 18 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=lambda c, d: _cover(c, d, report)),
        PageTemplate(id="page", frames=[frame], onPage=_page),
    ])
    secs = report.get("sectors", [])
    s = report.get("summary", {})
    b = report.get("benchmark", {})
    story: list = [Spacer(1, 1)]
    from reportlab.platypus import NextPageTemplate
    story += [NextPageTemplate("page"), PageBreak()]

    # ---- at a glance ----
    story.append(header_bar("This week at a glance", f"Week ending {nice_date(report.get('end_date'))} | 1-week and 1-month returns | Nifty 50: {pct(b.get('r1w'))}% 1W, {pct(b.get('r1m'))}% 1M"))
    story.append(Spacer(1, 8))
    story.append(kpi_strip([
        ("Top sector (1W + 1M rank)", f"{esc(str(s.get('top_sector')))}<br/><font size=9 color='#5B677D'>{pct(s.get('top_sector_r1w'))}% | {pct(s.get('top_sector_r1m'))}%</font>", NAVY),
        ("Beat their sector on 1W and 1M", f"{s.get('leaders')} of {s.get('rows')}", GREEN_INK),
        ("Trail their sector on 1W and 1M", f"{s.get('laggards')} of {s.get('rows')}", RED_INK),
    ]))
    story.append(Spacer(1, 12))
    for i, (title, text) in enumerate(insights(report), start=1):
        story.append(KeepTogether([Paragraph(f"{i}. {title}", S_INSIGHT_T), Paragraph(text, S_INSIGHT), Spacer(1, 7)]))
    story.append(Spacer(1, 4))
    story.append(note_box("<b>How to read:</b> vs 1W / vs 1M = stock return minus its sector's return, in percentage points (pp). "
                          "<b>Signal:</b> Leader = beats the sector on 1W and 1M; Turning up = 1W only; Fading = 1M only; Laggard = neither. "
                          "<b>Sector verdict:</b> STRONG = daily, weekly and monthly RSI all above 60; WEAK = all below 40; otherwise MIXED."))
    story.append(PageBreak())

    # ---- rankings ----
    story.append(header_bar("Sector rankings", "Every sector on the same dates; bars to scale"))
    for key, title in (("r1w", "1-week ranking"), ("r1m", "1-month ranking")):
        story.append(Spacer(1, 8))
        story.append(Paragraph(title, S_H2))
        ordered = sorted((x for x in secs if x.get(key) is not None), key=lambda x: -x[key])
        max_abs = max((abs(x[key]) for x in ordered), default=1)
        n = len(ordered)
        rows = [["#", "Sector", "Return %", ""]]
        extra = []
        for i, x in enumerate(ordered, start=1):
            tier = GREEN if i <= 3 else AMBER if i > n - 2 else BLUE
            rows.append([str(i), Paragraph(f"<b>{esc(x['label'])}</b>", S_CELL), pct(x[key]), Bar(x[key], max_abs, tier)])
            extra.append(("TEXTCOLOR", (2, i), (2, i), colour_of(x[key])))
        story.append(grid(rows, [10 * mm, 50 * mm, 24 * mm, CONTENT_W - 84 * mm], extra + [("ALIGN", (3, 0), (3, -1), "LEFT")]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Green = top 3, blue = middle, amber = bottom 2. Capital Market has no index on Angel One: its line is the equal-weight average of its stocks.", S_SMALL))
    story.append(PageBreak())

    # ---- scorecard ----
    story.append(header_bar("Sector scorecard", "Verdict from the sector index's daily, weekly and monthly RSI(14)"))
    story.append(Spacer(1, 8))
    rows = [["Sector", "1W %", "#", "1M %", "#", "RSI D", "RSI W", "RSI M", "Beat 1W | 1M", "Verdict"]]
    extra = []
    for i, x in enumerate(secs, start=1):
        n = len(x.get("stocks", []))
        rsi = x.get("rsi") or {}
        rows.append([Paragraph(f"<b>{esc(x['label'])}</b>", S_CELL), pct(x.get("r1w")), f"#{x.get('rank_1w')}", pct(x.get("r1m")), f"#{x.get('rank_1m')}",
                     *("n/a" if rsi.get(k) is None else f"{rsi[k]:.1f}" for k in ("d", "w", "m")),
                     f"{x.get('beat_1w')}/{n} | {x.get('beat_1m')}/{n}", x.get("verdict")])
        bg, ink = VERDICT.get(x.get("verdict"), VERDICT["N/A"])
        extra += [("BACKGROUND", (9, i), (9, i), bg), ("TEXTCOLOR", (9, i), (9, i), ink), ("FONTNAME", (9, i), (9, i), "Helvetica-Bold"),
                  ("TEXTCOLOR", (1, i), (1, i), colour_of(x.get("r1w"))), ("TEXTCOLOR", (3, i), (3, i), colour_of(x.get("r1m")))]
        for j, k in zip((5, 6, 7), ("d", "w", "m")):
            v = rsi.get(k)
            if v is not None:
                extra.append(("TEXTCOLOR", (j, i), (j, i), GREEN_INK if v > 60 else RED_INK if v < 40 else AMBER_INK))
    story.append(grid(rows, [36 * mm, 16 * mm, 10 * mm, 17 * mm, 10 * mm, 14 * mm, 14 * mm, 14 * mm, 25 * mm, 22 * mm], extra))
    story.append(Spacer(1, 10))
    story.append(note_box("<b>How to use:</b> study the STRONG sectors first, then the stocks that beat their own sector on both horizons. "
                          "Ranks compare every sector on the same dates; each stock is compared with its own sector line."))
    story.append(PageBreak())

    # ---- one section per sector ----
    for x in secs:
        n = len(x.get("stocks", []))
        rsi = x.get("rsi") or {}
        rsi_txt = "n/a" if rsi.get("d") is None else f"{rsi['d']:.0f} / {rsi['w']:.0f} / {rsi['m']:.0f}"
        story.append(header_bar(esc(f"{x['label']}: {x.get('verdict')} - #{x.get('rank_1w')} on 1W, #{x.get('rank_1m')} on 1M"),
                                "Equal-weight line of its stocks" if x.get("equal_weight") else esc(f"{x.get('index_label')} index line")))
        story.append(Spacer(1, 6))
        story.append(kpi_strip([
            ("Sector 1W", f"{pct(x.get('r1w'))}%", colour_of(x.get("r1w"))), ("Sector 1M", f"{pct(x.get('r1m'))}%", colour_of(x.get("r1m"))),
            ("RSI D / W / M", rsi_txt, NAVY), ("Beat sector 1W", f"{x.get('beat_1w')} of {n}", NAVY), ("Beat sector 1M", f"{x.get('beat_1m')} of {n}", NAVY),
        ]))
        story.append(Spacer(1, 6))
        rows = [["Stock", "1W %", "1M %", "vs 1W", "vs 1M", "Signal"]]
        extra = []
        for i, st in enumerate(x.get("stocks", []), start=1):
            rows.append([Paragraph(f"<b>{esc(st['symbol'])}</b>", S_CELL), pct(st["r1w"]), pct(st["r1m"]), pct(st["vs1w"]), pct(st["vs1m"]), st["signal"]])
            sb, si = SIGNAL.get(st["signal"], SIGNAL["N/A"])
            extra += [("TEXTCOLOR", (1, i), (1, i), colour_of(st["r1w"])), ("TEXTCOLOR", (2, i), (2, i), colour_of(st["r1m"])),
                      ("BACKGROUND", (3, i), (3, i), GREEN_BG if st["vs1w"] > 0 else RED_BG), ("TEXTCOLOR", (3, i), (3, i), GREEN_INK if st["vs1w"] > 0 else RED_INK),
                      ("BACKGROUND", (4, i), (4, i), GREEN_BG if st["vs1m"] > 0 else RED_BG), ("TEXTCOLOR", (4, i), (4, i), GREEN_INK if st["vs1m"] > 0 else RED_INK),
                      ("FONTNAME", (3, i), (4, i), "Helvetica-Bold"),
                      ("BACKGROUND", (5, i), (5, i), sb), ("TEXTCOLOR", (5, i), (5, i), si), ("FONTNAME", (5, i), (5, i), "Helvetica-Bold")]
        if n:
            story.append(grid(rows, [44 * mm, 22 * mm, 22 * mm, 26 * mm, 26 * mm, CONTENT_W - 140 * mm], extra))
        else:
            story.append(Paragraph("No stock data for this sector.", S_SMALL))
        leaders = [st["symbol"] for st in x.get("stocks", []) if st["signal"] == "Leader"]
        laggards = [st["symbol"] for st in x.get("stocks", []) if st["signal"] == "Laggard"]
        c = x.get("counts", {})
        story.append(Spacer(1, 6))
        story.append(note_box(f"<b>Takeaway:</b> {esc(', '.join(leaders[:6])) or 'no stock'} lead{'s' if len(leaders) == 1 else ''} the sector on both horizons"
                              + (f"; {esc(', '.join(laggards[:5]))} trail on both." if laggards else ".")))
        story.append(Paragraph(f"Signals: Leader {c.get('Leader', 0)} | Turning up {c.get('Turning up', 0)} | Fading {c.get('Fading', 0)} | Laggard {c.get('Laggard', 0)}. vs = percentage points vs the sector line.", S_SMALL))
        story.append(PageBreak())

    # ---- leaders and laggards ----
    def stock_table(title: str, sub: str, rows_src: list[dict], good: bool) -> None:
        story.append(header_bar(title, sub))
        story.append(Spacer(1, 8))
        rows = [["Stock", "Sector", "1W %", "1M %", "vs 1W", "vs 1M"]]
        extra = []
        for i, st in enumerate(rows_src, start=1):
            rows.append([Paragraph(f"<b>{esc(st['symbol'])}</b>", S_CELL), Paragraph(esc(st["sector"]), _style("sec", 8.5, color=MUTED)),
                         pct(st["r1w"]), pct(st["r1m"]), pct(st["vs1w"]), pct(st["vs1m"])])
            extra += [("TEXTCOLOR", (2, i), (2, i), colour_of(st["r1w"])), ("TEXTCOLOR", (3, i), (3, i), colour_of(st["r1m"])),
                      ("BACKGROUND", (4, i), (5, i), GREEN_BG if good else RED_BG), ("TEXTCOLOR", (4, i), (5, i), GREEN_INK if good else RED_INK),
                      ("FONTNAME", (4, i), (5, i), "Helvetica-Bold")]
        story.append(grid(rows, [36 * mm, 40 * mm, 22 * mm, 22 * mm, 30 * mm, CONTENT_W - 150 * mm], extra))
        story.append(PageBreak())

    stock_table(f"{s.get('leaders')} stock rows beat their sector on 1W and 1M", "Top 15 by combined outperformance (1W + 1M); a stock in two sectors can appear twice",
                report.get("top_movers", []), True)
    stock_table(f"{s.get('laggards')} stock rows trail their sector on 1W and 1M", "The deepest gaps first", report.get("laggards", []), False)

    # ---- study buckets ----
    story.append(header_bar("Four study buckets", "From 1W and 1M returns vs each stock's sector. For learning only; not a buy or sell list."))
    story.append(Spacer(1, 8))
    meta = {"strength_leaders": ("Strength leaders", "Leaders in strong sectors", GREEN_BG, GREEN_INK),
            "watch": ("Watch", "Near-leaders and pullbacks in strong sectors", BLUE_BG, BLUE_INK),
            "stock_specific": ("Stock-specific", "Leaders outside the strong sectors", AMBER_BG, AMBER_INK),
            "relative_weakness": ("Relative weakness", "Laggards and bounce-only in strong sectors", RED_BG, RED_INK)}
    for key, (title, sub, bg, ink) in meta.items():
        head = Table([[Paragraph(f"<font size=13><b>{title}</b></font>  <font size=9>{sub}</font>", _style("bk", 10, color=ink))]], colWidths=[CONTENT_W])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        body = [Paragraph(f"<b>{esc(sec)}:</b> {esc(', '.join(syms))}", S_BODY) for sec, syms in (report.get("buckets", {}).get(key) or {}).items()]
        story.append(KeepTogether([head, Spacer(1, 4)] + (body or [Paragraph("None this week.", S_SMALL)]) + [Spacer(1, 10)]))
    story.append(PageBreak())

    # ---- method & disclaimer ----
    story.append(header_bar("Notes on the numbers", esc(f"Angel One daily closes up to {nice_date(report.get('end_date'))}; sector lists: {report.get('constituents_source', 'NSE')}")))
    story.append(Spacer(1, 8))
    notes = [
        ("One set of dates", "1W = the last close vs the last close on or before 7 days earlier; 1M = vs 1 calendar month earlier. "
                             "Every sector and every stock uses the same dates, so a stock has one return wherever it appears."),
        ("Sector verdict", "STRONG when the sector index's daily, weekly and monthly RSI(14) are all above 60; WEAK when all three are "
                           "below 40; otherwise MIXED. Weekly and monthly RSI include the period in progress."),
        ("Groups", "Near-leader = beats the sector on one horizon and is within 1.5pp on the other. Bounce-only = beats the sector "
                   "this week but trails it by more than 1.5pp on the month."),
        ("Coverage", "Sector members are NSE's current index constituents. Capital Market has no index on Angel One, so its sector line "
                     "is the equal-weight average of its stocks and it has no RSI verdict."
                     + (f" No data this week for: {esc(', '.join(report['missing']))}." if report.get("missing") else "")),
    ]
    for t, txt in notes:
        story.append(KeepTogether([Paragraph(t, S_H2), Paragraph(txt, S_BODY), Spacer(1, 6)]))
    story.append(Spacer(1, 6))
    story.append(header_bar("Disclaimer"))
    story.append(Spacer(1, 6))
    for t, txt in (
        ("Purpose.", "Generated by A Group Scanner for personal market learning and education only."),
        ("Not a recommendation.", "Nothing here is a recommendation, offer or solicitation to buy, sell or hold any security, or investment, "
                                  "trading, tax or legal advice. Stocks and sectors are shown only as examples."),
        ("Not a SEBI research report.", "This is not a research report or investment advice under the SEBI (Research Analysts) or (Investment "
                                        "Advisers) Regulations. Consult a SEBI-registered professional before acting."),
        ("Market risk.", "Investments in securities markets are subject to market risks. Past performance does not indicate future results."),
        ("Data and method.", "Built automatically from Angel One price data and NSE index lists; it may contain delays, gaps or errors. "
                             "Rankings use only 1W and 1M price returns and RSI, and ignore valuation, earnings, liquidity, news and risk."),
    ):
        story.append(Paragraph(f"<b>{t}</b> {txt}", _style("disc", 9.5, color=INK, space_after=5)))

    doc.build(story)
    return buf.getvalue()
