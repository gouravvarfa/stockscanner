"""
PDF of the Weekly Sectors report (2026-11-21, premium + interactive redesign).

Look: a quiet, editorial layout - white pages, one navy ink with a thin gold accent, hairline rules instead of filled
boxes, colour only on the numbers that carry meaning (gains, losses, verdicts).

Smart parts (all real PDF links, they work in any PDF viewer):
- a Contents page of buttons (every section, and every sector with its verdict and 1W return),
- a CONTENTS button at the top of every page, and a bookmarks sidebar,
- sector names everywhere (rankings, scorecard, momentum map, leaders, buckets) jump to that sector,
- every stock symbol opens its chart on TradingView; a Chart button beside each sector opens its index,
- a momentum map (each sector's 1W and 1M return against the Nifty 50, in four quadrants) and
  breadth bars (how many stocks in each sector lead, turn up, fade or lag).

Pages: cover, contents, at a glance, rankings + breadth, scorecard + momentum map, every sector flowing one after the
other, leaders, laggards, study buckets, method + disclaimer. Built with reportlab from the report the page shows.
"""
from __future__ import annotations

import datetime as dt
import io
import os
from xml.sax.saxutils import escape as esc
from urllib.parse import quote
from xml.sax.saxutils import quoteattr

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

W, H = A4
M = 18 * mm
CONTENT_W = W - 2 * M
TOP = 24 * mm      # room for the running header
BOTTOM = 20 * mm   # room for the footer

NAVY = colors.HexColor("#0B1F3A")       # cover
NAVY_2 = colors.HexColor("#1C3359")     # bars
GOLD = colors.HexColor("#B8955A")       # the one accent: kickers and thin rules
INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
FAINT = colors.HexColor("#9CA3AF")
HAIR = colors.HexColor("#E5E7EB")
AXIS = colors.HexColor("#CBD5E1")
TINT = colors.HexColor("#F7F8FA")
POS, POS_BG = colors.HexColor("#0F7B4F"), colors.HexColor("#E9F6EF")
NEG, NEG_BG = colors.HexColor("#B42318"), colors.HexColor("#FCEEEC")
AMB, AMB_BG = colors.HexColor("#A15C07"), colors.HexColor("#FDF3E1")
BLU, BLU_BG = colors.HexColor("#1D4E89"), colors.HexColor("#EAF1FA")
SIGNALS = ["Leader", "Turning up", "Fading", "Laggard"]
SIGNAL = {"Leader": POS, "Turning up": BLU, "Fading": AMB, "Laggard": NEG, "N/A": FAINT}
VERDICT = {"STRONG": (POS_BG, POS), "MIXED": (AMB_BG, AMB), "WEAK": (NEG_BG, NEG), "N/A": (TINT, MUTED)}
BREADTH_STYLE = {"Broad": (POS_BG, POS), "Moderate": (AMB_BG, AMB), "Narrow": (NEG_BG, NEG)}



def _style(name, size=10, leading=None, color=INK, bold=False, align=TA_LEFT, space_after=0):
    return ParagraphStyle(name, fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.38, textColor=color, alignment=align, spaceAfter=space_after)


S_TITLE = _style("title", 21, leading=25, color=INK, bold=True)
S_SUB = _style("sub", 9.5, color=MUTED)
S_BODY = _style("body", 9.8, leading=14.5, color=INK)
S_SMALL = _style("small", 8, leading=11, color=MUTED)
S_CELL = _style("cell", 8.8, color=INK)
S_CELL_M = _style("cellm", 8, color=MUTED)
S_NUM = _style("num", 8.8, align=TA_RIGHT)
S_H3 = _style("h3", 13, leading=16, color=INK, bold=True)
S_LABEL = _style("label", 7, leading=9, color=MUTED, bold=True)
S_INS_T = _style("inst", 10.5, leading=14, color=INK, bold=True)
S_INS = _style("ins", 9.5, leading=13.5, color=MUTED)


def pct(v, digits=2) -> str:
    return "n/a" if v is None else f"{v:+.{digits}f}"


def pctp(v) -> str:
    """A return with its % sign, or n/a."""
    return "n/a" if v is None else f"{v:+.2f}%"


def rank(v) -> str:
    return f"#{v}" if v else ""


def nice_date(iso, fmt="%d %b %Y") -> str:
    try:
        return dt.date.fromisoformat(iso).strftime(fmt)
    except (TypeError, ValueError):
        return str(iso)


def colour_of(v) -> colors.Color:
    return MUTED if v is None else POS if v > 0 else NEG if v < 0 else INK


def hexof(c: colors.Color) -> str:
    return "#" + c.hexval()[2:]


def num(v, suffix="", bold=False) -> str:
    """A coloured number for a Paragraph (green up, red down)."""
    txt = f"{pct(v)}{suffix if v is not None else ''}"
    return f"<font color='{hexof(colour_of(v))}'>{'<b>' + txt + '</b>' if bold else txt}</font>"


def sec_key(key: str) -> str:
    return f"sec_{key}"


def sector_link(label: str, key: str | None, bold: bool = True) -> str:
    """A sector name that jumps to its section (plain text when there is no section to jump to)."""
    text = f"<b>{esc(label)}</b>" if bold else esc(label)
    return f"<a href='#{sec_key(key)}' color='{hexof(INK)}'>{text}</a>" if key else text


def tv_url(symbol: str) -> str:
    """TradingView chart of an NSE stock ("PNB") or a full TradingView symbol ("NSE:NIFTY_HEALTHCARE")."""
    s = symbol if ":" in symbol else "NSE:" + symbol.replace("&", "_").replace("-", "_")
    return "https://www.tradingview.com/chart/?symbol=" + quote(s, safe=":")


def stock_link(symbol: str, bold: bool = True) -> str:
    """A stock symbol that opens its chart on TradingView."""
    text = f"<b>{esc(symbol)}</b>" if bold else esc(symbol)
    return f"<a href={quoteattr(tv_url(symbol))} color='{hexof(INK)}'>{text}</a>"


def spaced(canvas, x, y, text, font="Helvetica-Bold", size=7, color=MUTED, space=1.3, right=False) -> float:
    """Letter-spaced label text on the canvas; returns its width."""
    width = stringWidth(text, font, size) + space * (len(text) - 1)
    t = canvas.beginText(x - width if right else x, y)
    t.setFont(font, size)
    t.setCharSpace(space)
    t.setFillColor(color)
    t.textOut(text)
    t.setCharSpace(0)  # the PDF text state outlives the text object: reset it, or every later string is spaced too
    canvas.drawText(t)
    return width


def _fit(text: str, font: str, size: float, max_w: float) -> str:
    """Shorten text with an ellipsis until it fits `max_w` points."""
    if stringWidth(text, font, size) <= max_w:
        return text
    while len(text) > 2 and stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


# ---- flowables ----------------------------------------------------------------------------------------------------

class Anchor(Flowable):
    """An invisible jump target, also listed in the PDF's bookmarks sidebar when `title` is given."""

    def __init__(self, key: str, title: str | None = None, level: int = 0):
        super().__init__()
        self.key, self.title, self.level = key, title, level

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        self.canv.bookmarkHorizontal(self.key, 0, 14)
        if self.title:
            self.canv.addOutlineEntry(self.title, self.key, level=self.level, closed=self.key == "sectors")


class Kicker(Flowable):
    """A short gold rule and a letter-spaced label above a section title."""

    def __init__(self, text: str, color=GOLD):
        super().__init__()
        self.text, self.color = text.upper(), color

    def wrap(self, aw, ah):
        return aw, 12

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(1.2)
        self.canv.line(0, 4.2, 9 * mm, 4.2)
        spaced(self.canv, 11.5 * mm, 1.8, self.text, size=7, color=self.color, space=1.4)


class Button(Flowable):
    """A rounded, clickable button: jumps inside the PDF (`dest`) or opens a web page (`url`)."""

    def __init__(self, width: float, height: float, title: str, *, dest: str | None = None, url: str | None = None,
                 meta: str | None = None, value: str | None = None, value_color=INK, accent=None, small: bool = False):
        super().__init__()
        self.width, self.height = width, height
        self.title, self.dest, self.url, self.meta = title, dest, url, meta
        self.value, self.value_color, self.accent, self.small = value, value_color, accent, small

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, w, h = self.canv, self.width, self.height
        r = 2.2 if self.small else 3
        c.setFillColor(colors.white if self.small else TINT)
        c.setStrokeColor(AXIS if self.small else HAIR)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, w, h, r, stroke=1, fill=1)
        x = 3.2 * mm
        if self.accent is not None:
            c.setFillColor(self.accent)
            c.roundRect(0, 0, 1.6 * mm, h, r, stroke=0, fill=1)
            c.rect(0.9 * mm, 0, 0.7 * mm, h, stroke=0, fill=1)  # square off the inner edge of the accent strip
            x = 4.2 * mm
        if self.small:
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 6.6)
            c.drawCentredString(w / 2, h / 2 - 2.3, self.title)
        else:
            title_y = h / 2 + (1.2 if self.meta else -3.2)
            value_w = stringWidth(self.value, "Helvetica-Bold", 9.2) + 3 * mm if self.value else 0
            if self.value:
                c.setFillColor(self.value_color)
                c.setFont("Helvetica-Bold", 9.2)
                c.drawRightString(w - 3.2 * mm, title_y, self.value)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 9.2)
            c.drawString(x, title_y, _fit(self.title, "Helvetica-Bold", 9.2, w - x - 3.2 * mm - value_w))
            if self.meta:
                c.setFillColor(MUTED)
                c.setFont("Helvetica", 7)
                c.drawString(x, h / 2 - 8.2, _fit(self.meta, "Helvetica", 7, w - x - 3.2 * mm))
        if self.dest:
            c.linkRect("", self.dest, (0, 0, w, h), relative=1, thickness=0)
        elif self.url:
            c.linkURL(self.url, (0, 0, w, h), relative=1, thickness=0)


class Bar(Flowable):
    """A thin horizontal bar around a zero line (negative values grow to the left)."""

    def __init__(self, value: float | None, max_abs: float, width: float, zero_at: float, height: float = 2.6 * mm):
        super().__init__()
        self.value, self.max_abs, self.width, self.zero_at, self.height = value, max_abs or 1, width, zero_at, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        zero = self.width * self.zero_at
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.6)
        c.line(zero, -1.2, zero, self.height + 1.2)
        if self.value is None:
            return
        pos_span, neg_span = self.width - zero, zero
        if self.value >= 0:
            c.setFillColor(NAVY_2)
            c.roundRect(zero, 0, max(self.value / self.max_abs * pos_span, 1.2), self.height, 1, stroke=0, fill=1)
        else:
            length = min(abs(self.value) / self.max_abs * pos_span, neg_span)
            c.setFillColor(NEG)
            c.roundRect(zero - length, 0, max(length, 1.2), self.height, 1, stroke=0, fill=1)


class StackBar(Flowable):
    """One sector's breadth: Leader / Turning up / Fading / Laggard counts as one bar split by colour."""

    def __init__(self, counts: dict, width: float, height: float = 3.4 * mm):
        super().__init__()
        self.counts, self.width, self.height = counts or {}, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        vals = [(self.counts.get(s, 0) or 0, SIGNAL[s]) for s in SIGNALS]
        total = sum(v for v, _ in vals)
        c.setFillColor(TINT)
        c.roundRect(0, 0, self.width, self.height, 1.2, stroke=0, fill=1)
        if not total:
            return
        x = 0.0
        for v, col in vals:
            if not v:
                continue
            seg = v / total * self.width
            c.setFillColor(col)
            c.rect(x, 0, seg, self.height, stroke=0, fill=1)
            if seg >= 9:
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 6.5)
                c.drawCentredString(x + seg / 2, self.height / 2 - 2.2, str(v))
            x += seg
        c.setStrokeColor(colors.white)  # hairline gaps between the segments
        c.setLineWidth(0.8)
        x = 0.0
        for v, _ in vals[:-1]:
            x += v / total * self.width
            if v and x < self.width - 0.5:
                c.line(x, 0, x, self.height)


class Legend(Flowable):
    """A row of small coloured squares with labels."""

    def __init__(self, items: list[tuple[str, colors.Color]], size: float = 7.4):
        super().__init__()
        self.items, self.size = items, size

    def wrap(self, aw, ah):
        return aw, 10

    def draw(self):
        c = self.canv
        x = 0.0
        for label, col in self.items:
            c.setFillColor(col)
            c.roundRect(x, 1.2, 6, 6, 1.2, stroke=0, fill=1)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", self.size)
            c.drawString(x + 9, 1.6, label)
            x += 9 + stringWidth(label, "Helvetica", self.size) + 14


class MomentumMap(Flowable):
    """Every sector by its 1M (x) and 1W (y) return against the Nifty 50, in four quadrants. Points jump to sectors."""

    def __init__(self, sectors: list[dict], bench: dict, width: float, height: float = 86 * mm):
        super().__init__()
        self.width, self.height = width, height
        b1w, b1m = bench.get("r1w"), bench.get("r1m")
        self.relative = b1w is not None and b1m is not None
        self.points, self.paths = [], {}
        for s in sectors:
            trail = [(t["rel_1m"], t["rel_1w"]) for t in s.get("trail") or [] if t.get("rel_1m") is not None and t.get("rel_1w") is not None]
            if trail and (s.get("trail") or [])[-1].get("date") == s.get("end_date"):
                x, y = trail[-1]  # this week's point is the end of its 4-week path
            elif s.get("r1w") is not None and s.get("r1m") is not None:
                x, y = s["r1m"] - (b1m if self.relative else 0), s["r1w"] - (b1w if self.relative else 0)
                trail = []
            else:
                continue
            self.points.append((s["label"], s.get("key"), x, y, s.get("verdict") or "N/A"))
            # the path only for the STRONG sectors: 20 paths at once are unreadable (quadrant changes are listed in
            # "At a glance" and on each sector's line)
            if len(trail) > 1 and s.get("verdict") == "STRONG":
                self.paths[s.get("key")] = (trail, s.get("verdict") or "N/A")

    def wrap(self, *_):
        return self.width, self.height

    @staticmethod
    def _step(span: float) -> float:
        for st in (0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100):
            if span / st <= 3:
                return st
        return 200

    def draw(self):
        c = self.canv
        left, right, bottom, top = 12 * mm, 3 * mm, 10 * mm, 4 * mm
        pw, ph = self.width - left - right, self.height - bottom - top
        xs = [p[2] for p in self.points] + [x for path, _ in self.paths.values() for x, _ in path] or [1]
        ys = [p[3] for p in self.points] + [y for path, _ in self.paths.values() for _, y in path] or [1]
        xmax = max(1.0, max(abs(v) for v in xs) * 1.18)
        ymax = max(1.0, max(abs(v) for v in ys) * 1.18)

        def px(v):
            return left + (v + xmax) / (2 * xmax) * pw

        def py(v):
            return bottom + (v + ymax) / (2 * ymax) * ph

        x0, y0 = px(0), py(0)
        quads = [((x0, y0, left + pw, bottom + ph), colors.HexColor("#F2F9F5"), "LEADING", "right-top"),
                 ((left, y0, x0, bottom + ph), colors.HexColor("#F4F7FC"), "IMPROVING", "left-top"),
                 ((x0, bottom, left + pw, y0), colors.HexColor("#FDF8EF"), "WEAKENING", "right-bottom"),
                 ((left, bottom, x0, y0), colors.HexColor("#FDF5F4"), "LAGGING", "left-bottom")]
        label_boxes: list[tuple[float, float, float, float]] = []
        for (ax, ay, bx, by), fill, label, corner in quads:
            c.setFillColor(fill)
            c.rect(ax, ay, bx - ax, by - ay, stroke=0, fill=1)
        for (ax, ay, bx, by), fill, label, corner in quads:
            lw = stringWidth(label, "Helvetica-Bold", 6.4) + 1.3 * (len(label) - 1)
            if bx - ax < lw + 6 * mm or by - ay < 7 * mm:
                continue  # a quadrant too thin to hold its name
            tx = bx - 2.5 * mm if corner.startswith("right") else ax + 2.5 * mm
            ty = by - 4.2 * mm if corner.endswith("top") else ay + 2.2 * mm
            spaced(c, tx, ty, label, size=6.4, color=FAINT, space=1.3, right=corner.startswith("right"))
            x1 = tx - lw if corner.startswith("right") else tx
            label_boxes.append((x1 - 1, ty - 1.5, x1 + lw + 1, ty + 7))

        # grid ticks
        c.setFont("Helvetica", 6.6)
        c.setFillColor(FAINT)
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.4)
        sx, sy = self._step(xmax), self._step(ymax)
        k = 1
        while k * sx < xmax:
            for v in (k * sx, -k * sx):
                c.line(px(v), bottom, px(v), bottom + ph)
                c.drawCentredString(px(v), bottom - 9, f"{v:+g}")
            k += 1
        k = 1
        while k * sy < ymax:
            for v in (k * sy, -k * sy):
                c.line(left, py(v), left + pw, py(v))
                c.drawRightString(left - 3, py(v) - 2.2, f"{v:+g}")
            k += 1
        c.drawCentredString(x0, bottom - 9, "0")
        c.drawRightString(left - 3, y0 - 2.2, "0")
        c.setStrokeColor(AXIS)
        c.setLineWidth(0.9)
        c.line(x0, bottom, x0, bottom + ph)
        c.line(left, y0, left + pw, y0)
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.6)
        c.rect(left, bottom, pw, ph, stroke=1, fill=0)

        what = "vs Nifty 50, pp" if self.relative else "%"
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(left + pw / 2, 0.5, f"1-month return ({what})")
        c.saveState()
        c.translate(2.6 * mm, bottom + ph / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, f"1-week return ({what})")
        c.restoreState()

        # the paths (oldest week first, faint), then this week's points, then labels where they collide with nothing
        for key, (path, verdict) in self.paths.items():
            ink = VERDICT.get(verdict, VERDICT["N/A"])[1]
            c.saveState()
            c.setStrokeColor(ink)
            c.setFillColor(ink)
            c.setStrokeAlpha(0.38)
            c.setFillAlpha(0.38)
            c.setLineWidth(0.9)
            pts = [(px(x), py(y)) for x, y in path]
            line = c.beginPath()
            line.moveTo(*pts[0])
            for q in pts[1:]:
                line.lineTo(*q)
            c.drawPath(line, stroke=1, fill=0)
            for q in pts[:-1]:
                c.circle(q[0], q[1], 1.3, stroke=0, fill=1)
            c.restoreState()
        placed = [(label, key, px(xv), py(yv), verdict) for label, key, xv, yv, verdict in self.points]
        boxes = list(label_boxes) + [(cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5) for _, _, cx, cy, _ in placed]
        for label, key, cx, cy, verdict in placed:
            c.setFillColor(VERDICT.get(verdict, VERDICT["N/A"])[1])
            c.setStrokeColor(colors.white)
            c.setLineWidth(0.9)
            c.circle(cx, cy, 3.1, stroke=1, fill=1)
        c.setFont("Helvetica-Bold", 7.2)
        for label, key, cx, cy, verdict in sorted(placed, key=lambda p: (p[3], p[2])):
            tw = stringWidth(label, "Helvetica-Bold", 7.2)
            options = [(cx + 5, cy - 2.4), (cx - 5 - tw, cy - 2.4), (cx - tw / 2, cy + 5), (cx - tw / 2, cy - 10.5),
                       (cx + 5, cy + 4), (cx + 5, cy - 9), (cx - 5 - tw, cy + 4), (cx - 5 - tw, cy - 9),
                       (cx + 5, cy + 10), (cx + 5, cy - 15), (cx - 5 - tw, cy + 10), (cx - 5 - tw, cy - 15)]
            chosen = None
            for tx, ty in options:
                box = (tx - 1, ty - 1.5, tx + tw + 1, ty + 7)
                inside = box[0] >= left + 1 and box[2] <= left + pw - 1 and box[1] >= bottom + 1 and box[3] <= bottom + ph - 1
                if inside and not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in boxes):
                    chosen = (tx, ty, box)
                    break
            if chosen is None:  # very crowded: keep it inside the plot, next to its point
                tx = min(max(cx + 5, left + 2), left + pw - tw - 2)
                ty = min(max(cy - 2.4, bottom + 2), bottom + ph - 8)
                chosen = (tx, ty, (tx - 1, ty - 1.5, tx + tw + 1, ty + 7))
            tx, ty, box = chosen
            boxes.append(box)
            c.setFillColor(INK)
            c.drawString(tx, ty, label)
            if key:
                c.linkRect("", sec_key(key), (min(cx - 4, box[0]), min(cy - 4, box[1]), max(cx + 4, box[2]), max(cy + 4, box[3])),
                           relative=1, thickness=0)


# ---- building blocks ----------------------------------------------------------------------------------------------

def section(kicker: str, title: str, subtitle: str | None = None, anchor: str | None = None, outline: str | None = None) -> list:
    out: list = [Anchor(anchor, outline)] if anchor else []
    out += [Kicker(kicker), Spacer(1, 5), Paragraph(title, S_TITLE)]
    if subtitle:
        out += [Spacer(1, 3), Paragraph(subtitle, S_SUB)]
    return out + [Spacer(1, 12)]


def pill(text: str, bg, ink, width: float = 19 * mm) -> Table:
    t = Table([[Paragraph(f"<b>{esc(text)}</b>", _style("pill", 7.2, leading=8.5, color=ink, align=TA_CENTER))]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return t


def verdict_pill(v: str | None) -> Table:
    bg, ink = VERDICT.get(v or "N/A", VERDICT["N/A"])
    return pill(v or "N/A", bg, ink)


def signal_txt(sig: str) -> Paragraph:
    c = hexof(SIGNAL.get(sig, FAINT))
    return Paragraph(f"<font color='{c}' size=11>•</font> <font color='{c}'><b>{esc(sig)}</b></font>", _style("sig", 8.6))


def kpis(items: list[tuple[str, str, str]]) -> Table:
    """Headline numbers: a thin ink rule on top, a small label, a large value and a quiet note."""
    gap = 5 * mm
    n = len(items)
    cw = (CONTENT_W - gap * (n - 1)) / n
    row, widths = [], []
    for i, (label, value, note) in enumerate(items):
        if i:
            row.append("")
            widths.append(gap)
        row.append([Paragraph(label.upper(), S_LABEL), Spacer(1, 4), Paragraph(value, _style("kv", 17, leading=20, bold=True)),
                    Spacer(1, 2), Paragraph(note, S_SMALL)])
        widths.append(cw)
    t = Table([row], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for i in range(0, len(row), 2):
        style.append(("LINEABOVE", (i, 0), (i, 0), 1.1, INK))
    t.setStyle(TableStyle(style))
    return t


def table(rows: list[list], widths: list[float], extra: list | None = None, right_from: int = 1, left_cols: tuple = (),
          pad: float = 4.6) -> Table:
    """Hairline table: small muted header over an ink rule, hairlines between rows, numbers right-aligned
    (columns from `right_from` on, except `left_cols`)."""
    head = [Paragraph(str(h).upper(), _style("th", 6.8, leading=8.5, color=MUTED, bold=True,
                                             align=TA_RIGHT if i >= right_from and i not in left_cols else TA_LEFT))
            if isinstance(h, str) else h for i, h in enumerate(rows[0])]
    t = Table([head] + rows[1:], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 1), (-1, -1), 8.8), ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.4, HAIR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (right_from, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
    ] + (extra or [])))
    return t


def quiet_box(html: str) -> Table:
    t = Table([[Paragraph(html, _style("qb", 8.8, leading=13, color=MUTED))]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEBEFORE", (0, 0), (0, -1), 1.6, GOLD),
                           ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return t


def button_grid(buttons: list[Button], cols: int, gap: float = 4 * mm) -> Table:
    widths: list[float] = []
    for c in range(cols):
        if c:
            widths.append(gap)
        widths.append((CONTENT_W - gap * (cols - 1)) / cols)
    rows = []
    for i in range(0, len(buttons), cols):
        row: list = []
        for j, b in enumerate(buttons[i:i + cols]):
            if j:
                row.append("")
            row.append(b)
        while len(row) < len(widths):
            row.append("")
        rows.append(row)
    t = Table(rows or [[""] * len(widths)], colWidths=widths)
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), gap * 0.75),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def insights(report: dict) -> list[tuple[str, str]]:
    secs = report.get("sectors", [])
    s = report.get("summary", {})
    b = report.get("benchmark", {}) or {}
    out: list[tuple[str, str]] = []
    strong = s.get("strong_sectors") or []
    if strong:
        out.append((f"{len(strong)} sector{'s are' if len(strong) > 1 else ' is'} STRONG on RSI",
                    f"{', '.join(strong)}: daily, weekly and monthly RSI(14) all above 60."))
    else:
        out.append(("No sector is STRONG on RSI", "No sector index has its daily, weekly and monthly RSI all above 60 this week."))
    ch = report.get("changes") or {}
    if ch.get("new_strong") or ch.get("dropped_strong"):
        parts = []
        if ch.get("new_strong"):
            parts.append(f"newly STRONG: {', '.join(ch['new_strong'])}")
        if ch.get("dropped_strong"):
            parts.append(f"no longer STRONG: {', '.join(ch['dropped_strong'])}")
        text = "; ".join(parts)
        out.append(("Changed since last week", text[0].upper() + text[1:] + "."))
    if ch.get("risers") or ch.get("fallers"):
        up = ", ".join(f"{x['label']} #{x['from']} to #{x['to']}" for x in ch.get("risers") or [])
        down = ", ".join(f"{x['label']} #{x['from']} to #{x['to']}" for x in ch.get("fallers") or [])
        out.append(("Rank moves on 1W", "; ".join(t for t in (f"up: {up}" if up else "", f"down: {down}" if down else "") if t) + "."))
    narrow = [x for x in secs if x.get("verdict") == "STRONG" and (x.get("breadth") or {}).get("label") == "Narrow"]
    if narrow:
        out.append((f"STRONG but narrow: {', '.join(x['label'] for x in narrow)}",
                    "Fewer than 40% of its stocks are above their 50-day average: the index is carried by a few heavyweights."))
    ranked = [x for x in secs if x.get("rank_1w") and x.get("rank_1m")]
    if ranked:
        top = min(ranked, key=lambda x: (x["rank_1w"] + x["rank_1m"]) / 2)
        both = " - #1 on both 1W and 1M" if top["rank_1w"] == 1 and top["rank_1m"] == 1 else ""
        out.append((f"{top['label']} leads{both}",
                    f"{top['label']} returned {pctp(top['r1w'])} over the week (#{top['rank_1w']}) and {pctp(top['r1m'])} over the month (#{top['rank_1m']})."))
        if b.get("r1w") is not None and b.get("r1m") is not None:
            beat = [x["label"] for x in ranked if x["r1w"] > b["r1w"] and x["r1m"] > b["r1m"]]
            out.append((f"{len(beat)} of {len(ranked)} sectors beat the Nifty 50 on both horizons",
                        (f"{', '.join(beat)} returned more than the Nifty 50 ({pctp(b['r1w'])} 1W, {pctp(b['r1m'])} 1M) over the week and the month."
                         if beat else f"No sector beat the Nifty 50 ({pctp(b['r1w'])} 1W, {pctp(b['r1m'])} 1M) over both the week and the month.")))
        swing = max(ranked, key=lambda x: abs(x["rank_1w"] - x["rank_1m"]))
        if abs(swing["rank_1w"] - swing["rank_1m"]) >= 4:
            better = "the week" if swing["rank_1w"] < swing["rank_1m"] else "the month"
            out.append((f"{swing['label']}: a split picture",
                        f"#{swing['rank_1w']} on 1W but #{swing['rank_1m']} on 1M - stronger over {better}. Check both horizons."))
        last = max(ranked, key=lambda x: (x["rank_1w"] + x["rank_1m"]) / 2)
        out.append((f"{last['label']} is the weakest",
                    f"{pctp(last['r1w'])} on the week (#{last['rank_1w']}) and {pctp(last['r1m'])} on the month (#{last['rank_1m']})."))
    movers = report.get("top_movers") or []
    if movers:
        a = movers[0]
        txt = f"{a['symbol']} beats {a['sector']} by {pct(a['vs1w'])}pp (1W) and {pct(a['vs1m'])}pp (1M)"
        if len(movers) > 1:
            m2 = movers[1]
            txt += f"; {m2['symbol']} beats {m2['sector']} by {pct(m2['vs1w'])}pp and {pct(m2['vs1m'])}pp"
        out.append(("Stock-level edge", txt + "."))
    out = [(esc(t), esc(x)) for t, x in out]
    out.append(("Breadth", f"{s.get('leaders')} of {s.get('rows')} stock rows beat their sector on both 1W and 1M; "
                            f"{s.get('laggards')} trail it on both."))
    return out


# ---- page furniture -----------------------------------------------------------------------------------------------

def _cover(canvas, doc, report: dict) -> None:
    s = report.get("summary", {})
    b = report.get("benchmark", {}) or {}
    secs = report.get("sectors", [])
    c = canvas
    c.saveState()
    c.showOutline()
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    x = M + 2
    spaced(c, x, H - 30 * mm, "SCANNER", size=8, color=GOLD, space=2.2)
    spaced(c, W - M, H - 30 * mm, "WEEKLY", size=8, color=colors.HexColor("#8EA3C4"), space=2.2, right=True)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 38)
    c.drawString(x, H * 0.60, "Weekly Sector")
    c.drawString(x, H * 0.60 - 44, "Report")
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.line(x, H * 0.60 - 66, x + 26 * mm, H * 0.60 - 66)
    c.setFillColor(colors.HexColor("#C9D4E6"))
    c.setFont("Helvetica", 13)
    c.drawString(x, H * 0.60 - 90, "Sector and stock relative strength")
    end = report.get("end_date") or report.get("as_of")
    c.drawString(x, H * 0.60 - 108, f"Week ending {nice_date(end, '%d %B %Y')}")

    # an "open contents" button on the cover
    label = "OPEN CONTENTS"
    lw = stringWidth(label, "Helvetica-Bold", 7.4) + 1.6 * (len(label) - 1)
    bw, bh, by = lw + 14 * mm, 10 * mm, H * 0.60 - 150
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.9)
    c.roundRect(x, by, bw, bh, bh / 2, stroke=1, fill=0)
    spaced(c, x + (bw - lw) / 2, by + bh / 2 - 2.6, label, size=7.4, color=colors.white, space=1.6)
    c.linkRect("", "contents", (x, by, x + bw, by + bh), relative=0, thickness=0)

    # three headline numbers along the bottom
    rated = [z for z in secs if z.get("verdict") not in (None, "N/A")]
    stats = [("TOP SECTOR", str(s.get("top_sector") or "n/a"), f"{pctp(s.get('top_sector_r1w'))} 1W  |  {pctp(s.get('top_sector_r1m'))} 1M"),
             ("STRONG ON RSI", f"{len(s.get('strong_sectors') or [])} of {len(rated)}", "sectors with D, W, M RSI above 60"),
             ("NIFTY 50", f"{pctp(b.get('r1w'))}", f"1W  |  {pctp(b.get('r1m'))} 1M")]
    y = 62 * mm
    col = (W - 2 * M) / 3
    c.setStrokeColor(colors.HexColor("#2A4470"))
    c.setLineWidth(0.6)
    c.line(x, y + 16 * mm, W - M, y + 16 * mm)
    for i, (label, value, note) in enumerate(stats):
        cx = x + i * col
        spaced(c, cx, y + 8 * mm, label, size=7, color=GOLD, space=1.6)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 17)
        value_txt = value
        while stringWidth(value_txt, "Helvetica-Bold", 17) > col - 6 * mm and len(value_txt) > 4:
            value_txt = value_txt[:-2].rstrip() + "…"
        c.drawString(cx, y, value_txt)
        c.setFillColor(colors.HexColor("#8EA3C4"))
        c.setFont("Helvetica", 8.5)
        c.drawString(cx, y - 5.5 * mm, note)

    c.setFillColor(colors.HexColor("#7F93B5"))
    c.setFont("Helvetica", 7.5)
    c.drawString(x, 20 * mm, "For educational purposes only. Not investment advice, and not a recommendation to buy, sell or hold any security.")
    c.drawString(x, 20 * mm - 10, "Data: Angel One daily closes. Sector lists: NSE index constituents. Method and disclaimer on the last page.")
    c.restoreState()


def _page(canvas, doc, report: dict) -> None:
    c = canvas
    c.saveState()
    end = nice_date(report.get("end_date") or report.get("as_of"), "%d %b %Y").upper()
    y = H - 13 * mm
    wd = spaced(c, M, y, "WEEKLY SECTOR REPORT", size=6.8, color=INK, space=1.5)
    spaced(c, M + wd + 10, y, f"WEEK ENDING {end}", size=6.8, color=FAINT, space=1.5)
    # CONTENTS button, top right of every page
    label = "CONTENTS"
    lw = stringWidth(label, "Helvetica-Bold", 6.4) + 1.4 * (len(label) - 1)
    bw, bh = lw + 7 * mm, 5 * mm
    bx, by = W - M - bw, y - 1.7 * mm
    c.setFillColor(TINT)
    c.setStrokeColor(AXIS)
    c.setLineWidth(0.6)
    c.roundRect(bx, by, bw, bh, bh / 2, stroke=1, fill=1)
    spaced(c, bx + (bw - lw) / 2, by + bh / 2 - 2.2, label, size=6.4, color=INK, space=1.4)
    c.linkRect("", "contents", (bx, by, bx + bw, by + bh), relative=0, thickness=0)
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.5)
    c.line(M, H - 16.5 * mm, W - M, H - 16.5 * mm)
    c.line(M, 13.5 * mm, W - M, 13.5 * mm)
    c.setFillColor(FAINT)
    c.setFont("Helvetica", 7)
    c.drawString(M, 9.5 * mm, "Scanner  ·  For education only, not investment advice")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(W - M, 9.5 * mm, f"{doc.page:02d}")
    c.restoreState()


# ---- the document -------------------------------------------------------------------------------------------------

def _sector_block(x: dict) -> list:
    stocks = x.get("stocks", [])
    n = len(stocks)
    rsi = x.get("rsi") or {}
    rsi_txt = "n/a" if rsi.get("d") is None else f"{rsi['d']:.0f} / {rsi['w']:.0f} / {rsi['m']:.0f}"
    line = "Equal-weight line of its stocks" if x.get("equal_weight") else esc(str(x.get("index_label")))
    tv = x.get("tv_symbol")
    chart = Button(15 * mm, 5.2 * mm, "CHART", url=tv_url(tv), small=True) if tv else ""
    head = Table([[Paragraph(esc(x["label"]), S_H3), chart, verdict_pill(x.get("verdict"))]],
                 colWidths=[CONTENT_W - 38 * mm, 18 * mm, 20 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
                              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    meta = Paragraph(
        f"{line}  ·  1W {num(x.get('r1w'), '%', True)} <font color='{hexof(FAINT)}'>{rank(x.get('rank_1w'))}</font>"
        f"  ·  1M {num(x.get('r1m'), '%', True)} <font color='{hexof(FAINT)}'>{rank(x.get('rank_1m'))}</font>"
        f"  ·  RSI D/W/M <b>{rsi_txt}</b>  ·  beat the sector: {x.get('beat_1w')}/{n} on 1W, {x.get('beat_1m')}/{n} on 1M"
        + (f"  ·  <b>{esc(x['quadrant'])}</b>" + (f" (last week {esc(x['prev']['quadrant'])})" if (x.get('prev') or {}).get('quadrant')
                                                     and x['prev']['quadrant'] != x['quadrant'] else "") if x.get("quadrant") else "")
        + (f"  ·  breadth <b>{esc((x.get('breadth') or {}).get('label'))}</b>, {(x.get('breadth') or {}).get('above_50dma')}% above the 50-day average"
           if (x.get("breadth") or {}).get("label") else ""),
        _style("meta", 8.4, leading=12, color=MUTED))
    out: list = [CondPageBreak(55 * mm), Anchor(sec_key(x["key"]), x["label"], level=1), head, Spacer(1, 3), meta, Spacer(1, 7)]
    if n:
        rows = [["Stock", "1W %", "1M %", "vs sector 1W", "vs sector 1M", "Signal"]]
        for st in stocks:
            rows.append([Paragraph(stock_link(st["symbol"]), S_CELL), Paragraph(num(st["r1w"]), S_NUM), Paragraph(num(st["r1m"]), S_NUM),
                         Paragraph(num(st["vs1w"], "", True), S_NUM), Paragraph(num(st["vs1m"], "", True), S_NUM), signal_txt(st["signal"])])
        out.append(table(rows, [44 * mm, 22 * mm, 22 * mm, 27 * mm, 27 * mm, CONTENT_W - 142 * mm],
                         [("ALIGN", (5, 0), (5, -1), "LEFT"), ("LEFTPADDING", (5, 0), (5, -1), 12)], right_from=1, left_cols=(5,)))
    else:
        out.append(Paragraph("No stock data for this sector this week.", S_SMALL))
    leaders = [st["symbol"] for st in stocks if st["signal"] == "Leader"]
    laggards = [st["symbol"] for st in stocks if st["signal"] == "Laggard"]
    take = (f"<b>Leads on both horizons:</b> {esc(', '.join(leaders[:8])) or 'none'}"
            + (f"   <b>Trails on both:</b> {esc(', '.join(laggards[:6]))}" if laggards else ""))
    out += [Spacer(1, 6), Paragraph(take, _style("take", 8.4, leading=12, color=MUTED)), Spacer(1, 16)]
    return out


def build_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=TOP, bottomMargin=BOTTOM,
                          title="Weekly Sector Report", author="Scanner",
                          subject="Sector and stock relative strength (education only)")
    frame = Frame(M, BOTTOM, CONTENT_W, H - TOP - BOTTOM, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=lambda c, d: _cover(c, d, report)),
        PageTemplate(id="page", frames=[frame], onPage=lambda c, d: _page(c, d, report)),
    ])
    secs = report.get("sectors", [])
    s = report.get("summary", {})
    b = report.get("benchmark", {}) or {}
    by_label = {x["label"]: x["key"] for x in secs}
    story: list = [Spacer(1, 1), NextPageTemplate("page"), PageBreak()]

    # ---- contents: every section and every sector as a button ----
    story += section("Navigate", "Contents", "Every button is a link. The CONTENTS button at the top of each page brings you back here.",
                     anchor="contents", outline="Contents")
    story += [Paragraph("THE REPORT", S_LABEL), Spacer(1, 6)]
    report_buttons = [("At a glance", "glance", "Headline numbers, findings"), ("Rankings", "rankings", "1W and 1M, with breadth"),
                      ("Scorecard", "scorecard", "RSI verdicts, momentum map"), ("Sector by sector", "sectors", "Every stock vs its sector"),
                      ("Leaders", "leaders", "Beat their sector on both"), ("Laggards", "laggards", "Trail their sector on both"),
                      ("Study buckets", "buckets", "Four lists to study"), ("Method", "method", "Calculation and disclaimer")]
    bw4 = (CONTENT_W - 3 * 4 * mm) / 4
    story += [button_grid([Button(bw4, 12.5 * mm, t, dest=d, meta=m) for t, d, m in report_buttons], 4), Spacer(1, 10)]
    story += [Paragraph("SECTORS  ·  STRONGEST VERDICT FIRST", S_LABEL), Spacer(1, 6)]
    bw3 = (CONTENT_W - 2 * 4 * mm) / 3
    sec_buttons = []
    for x in secs:
        v = x.get("verdict") or "N/A"
        ranks = f"#{x.get('rank_1w')} on 1W  ·  #{x.get('rank_1m')} on 1M" if x.get("rank_1w") else "no index data"
        sec_buttons.append(Button(bw3, 12.5 * mm, x["label"], dest=sec_key(x["key"]), meta=f"{v}  ·  {ranks}",
                                  value=f"{pctp(x.get('r1w'))}" if x.get("r1w") is not None else None,
                                  value_color=colour_of(x.get("r1w")), accent=VERDICT.get(v, VERDICT["N/A"])[1]))
    story += [button_grid(sec_buttons, 3), Spacer(1, 8)]
    story.append(quiet_box("<b><font color='#111827'>Tips.</font></b> The coloured strip on a sector button is its verdict "
                           "(green STRONG, amber MIXED, red WEAK) and the number is its 1-week return. In the tables, tap a "
                           "<b>stock symbol</b> to open its chart on TradingView, a <b>sector name</b> to jump to that sector, "
                           "and <b>CHART</b> beside a sector to open its index. The bookmarks panel of your PDF viewer lists "
                           "every section too."))
    story.append(PageBreak())

    # ---- at a glance ----
    story += section("This week", "At a glance",
                     f"Week ending {nice_date(report.get('end_date'))}. Returns over one week (1W) and one month (1M); "
                     f"Nifty 50 {pctp(b.get('r1w'))} 1W and {pctp(b.get('r1m'))} 1M.", anchor="glance", outline="At a glance")
    top_key = by_label.get(s.get("top_sector"))
    story.append(kpis([
        ("Top sector", sector_link(str(s.get("top_sector")), top_key, bold=False), f"{pctp(s.get('top_sector_r1w'))} 1W  ·  {pctp(s.get('top_sector_r1m'))} 1M"),
        ("Beat their sector", f"<font color='{hexof(POS)}'>{s.get('leaders')}</font>", f"of {s.get('rows')} stock rows, on 1W and 1M"),
        ("Trail their sector", f"<font color='{hexof(NEG)}'>{s.get('laggards')}</font>", f"of {s.get('rows')} stock rows, on 1W and 1M"),
    ]))
    story.append(Spacer(1, 16))
    for i, (title, text) in enumerate(insights(report), start=1):
        row = Table([[Paragraph(f"{i:02d}", _style("no", 10, color=GOLD, bold=True)),
                      [Paragraph(title, S_INS_T), Spacer(1, 2), Paragraph(text, S_INS)]]], colWidths=[11 * mm, CONTENT_W - 11 * mm])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIR)]))
        story.append(KeepTogether([row]))
    story.append(Spacer(1, 14))
    story.append(quiet_box("<b><font color='#111827'>How to read.</font></b> <b>vs sector</b> = the stock's return minus its "
                           "sector's return, in percentage points (pp). <b>Signal:</b> Leader beats the sector on 1W and 1M, "
                           "Turning up on 1W only, Fading on 1M only, Laggard on neither. <b>Verdict:</b> STRONG when the sector "
                           "index's daily, weekly and monthly RSI(14) are all above 60, WEAK when all are below 40, otherwise MIXED."))
    story.append(PageBreak())

    # ---- rankings side by side, then breadth ----
    story += section("Rankings", "Sector returns", "Every sector on the same dates; bars to scale within each column. The small green or red "
                     "number is how many places the sector moved since last week. Tap a sector to open it.",
                     anchor="rankings", outline="Rankings")
    half = (CONTENT_W - 8 * mm) / 2

    def ranking(key: str, title: str) -> list:
        ordered = sorted((x for x in secs if x.get(key) is not None), key=lambda x: -x[key])
        max_abs = max((abs(x[key]) for x in ordered), default=1) or 1
        neg_share = max((abs(x[key]) for x in ordered if x[key] < 0), default=0) / max_abs
        zero_at = min(0.4, max(0.06, neg_share / (1 + neg_share)))
        rows = [["#", "Sector", "Return", ""]]
        move_key = "rank_change_1w" if key == "r1w" else "rank_change_1m"
        for i, x in enumerate(ordered, start=1):
            mv = x.get(move_key)
            mv_txt = "" if not mv else f" <font size=6.6 color='{hexof(POS if mv > 0 else NEG)}'>{'+' if mv > 0 else ''}{mv}</font>"
            rows.append([Paragraph(f"<font color='{hexof(FAINT)}'>{i}</font>{mv_txt}", S_CELL), Paragraph(sector_link(x["label"], x["key"]), S_CELL),
                         Paragraph(num(x[key], "%"), S_NUM), Bar(x[key], max_abs, half - 68 * mm, zero_at)])
        t = table(rows, [10 * mm, 32 * mm, 17 * mm, half - 59 * mm], [("LEFTPADDING", (3, 0), (3, -1), 9), ("RIGHTPADDING", (3, 0), (3, -1), 0)],
                  right_from=2, pad=3.2)
        return [Paragraph(title, _style("rt", 10.5, bold=True)), Spacer(1, 6), t]

    pair = Table([[ranking("r1w", "One week"), "", ranking("r1m", "One month")]], colWidths=[half, 8 * mm, half])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [pair, Spacer(1, 6),
              Paragraph("Capital Market has no index on Angel One: its line is the equal-weight average of its stocks.", S_SMALL),
              Spacer(1, 12)]

    breadth_rows = [["Sector", "Signals", "> 50 DMA", "> 200 DMA", "RSI > 60", "52w highs", Paragraph("<b>BREADTH</b>", _style("th", 6.8, leading=8.5, color=MUTED, align=TA_CENTER))]]
    for x in secs:
        br = x.get("breadth") or {}
        pct_cell = lambda v: Paragraph("n/a" if v is None else f"{v}%", S_NUM)  # noqa: E731
        lab = br.get("label")
        breadth_rows.append([Paragraph(sector_link(x["label"], x["key"]), S_CELL), StackBar(x.get("counts", {}), CONTENT_W - 128 * mm),
                             pct_cell(br.get("above_50dma")), pct_cell(br.get("above_200dma")), pct_cell(br.get("rsi_above_60")),
                             Paragraph(str(br.get("new_52w_highs", 0)), S_NUM),
                             pill(lab, *BREADTH_STYLE[lab], width=17 * mm) if lab else Paragraph("n/a", S_NUM)])
    story.append(KeepTogether([
        Paragraph("Breadth inside each sector", _style("bh", 12.5, leading=15, bold=True)), Spacer(1, 3),
        Paragraph("Signals: how many stocks lead, turn up, fade or lag against their own sector line. Then the share of the "
                  "sector's stocks above their 50- and 200-day average and with a daily RSI above 60, and the new 52-week highs "
                  "made this week. Breadth: Broad when 70%+ are above the 50-day average, Moderate 40-70%, Narrow below 40% "
                  "(the index is carried by a few stocks).", S_SMALL), Spacer(1, 7),
        Legend([(sig, SIGNAL[sig]) for sig in SIGNALS]), Spacer(1, 5),
        table(breadth_rows, [34 * mm, CONTENT_W - 124 * mm, 18 * mm, 19 * mm, 17 * mm, 16 * mm, 20 * mm],
              [("LEFTPADDING", (1, 0), (1, -1), 4), ("ALIGN", (6, 0), (6, -1), "CENTER")], right_from=2, left_cols=(1,), pad=2.7),
    ]))
    story.append(PageBreak())

    # ---- scorecard, then the momentum map ----
    score = section("Scorecard", "Sector verdicts", "From each sector index's daily, weekly and monthly RSI(14). Green above 60, red below 40.",
                    anchor="scorecard", outline="Scorecard")
    rows = [["Sector", "1W %", "#", "1M %", "#", "RSI D", "RSI W", "RSI M", "Beat 1W / 1M",
             Paragraph("<b>VERDICT</b>", _style("th", 6.8, leading=8.5, color=MUTED, align=TA_CENTER))]]

    def rsi_cell(v):
        if v is None:
            return Paragraph(f"<font color='{hexof(FAINT)}'>n/a</font>", S_NUM)
        c = POS if v > 60 else NEG if v < 40 else INK
        txt = f"{v:.1f}" if c is INK else f"<b>{v:.1f}</b>"
        return Paragraph(f"<font color='{hexof(c)}'>{txt}</font>", S_NUM)

    for x in secs:
        n = len(x.get("stocks", []))
        rsi = x.get("rsi") or {}
        rows.append([Paragraph(sector_link(x["label"], x["key"]), S_CELL), Paragraph(num(x.get("r1w")), S_NUM),
                     Paragraph(f"<font color='{hexof(FAINT)}'>{x.get('rank_1w') or ''}</font>", S_NUM),
                     Paragraph(num(x.get("r1m")), S_NUM),
                     Paragraph(f"<font color='{hexof(FAINT)}'>{x.get('rank_1m') or ''}</font>", S_NUM),
                     rsi_cell(rsi.get("d")), rsi_cell(rsi.get("w")), rsi_cell(rsi.get("m")),
                     f"{x.get('beat_1w')}/{n}  ·  {x.get('beat_1m')}/{n}", verdict_pill(x.get("verdict"))])
    story.append(KeepTogether(score + [table(rows, [35 * mm, 15 * mm, 8 * mm, 15 * mm, 8 * mm, 14 * mm, 14 * mm, 14 * mm, 25 * mm, CONTENT_W - 148 * mm],
                                             [("ALIGN", (9, 0), (9, -1), "CENTER")], right_from=1, pad=3.9)]))
    story.append(Spacer(1, 16))
    rel = b.get("r1w") is not None and b.get("r1m") is not None
    story.append(KeepTogether([
        Paragraph("Momentum map", _style("mh", 12.5, leading=15, bold=True)), Spacer(1, 3),
        Paragraph(("Each sector's 1-week and 1-month return minus the Nifty 50's. Top right leads the market on both; "
                   "top left is improving; bottom right is weakening; bottom left lags. The faint line is the path of each "
                   "STRONG sector over the last 4 weeks; the dot is this week. Tap a point to open the sector.")
                  if rel else "Each sector's 1-week and 1-month return. Tap a point to open the sector.", S_SMALL), Spacer(1, 6),
        Legend([("STRONG", POS), ("MIXED", AMB), ("WEAK", NEG), ("no verdict", FAINT)]), Spacer(1, 4),
        MomentumMap(secs, b, CONTENT_W, height=118 * mm),
    ]))
    story.append(PageBreak())

    # ---- every sector, flowing ----
    story += section("Sectors", "Sector by sector", "Each stock against its own sector line, strongest verdicts first. "
                     "Tap a stock symbol for its chart.", anchor="sectors", outline="Sector by sector")
    for x in secs:
        story += _sector_block(x)

    # ---- leaders and laggards (flow on from the last sector) ----
    def movers(kicker: str, title: str, sub: str, src: list[dict], anchor: str, outline: str) -> list:
        rows = [["Stock", "Sector", "1W %", "1M %", "vs sector 1W", "vs sector 1M"]]
        for st in src:
            rows.append([Paragraph(stock_link(st["symbol"]), S_CELL),
                         Paragraph(sector_link(st["sector"], by_label.get(st["sector"]), bold=False), _style("cs", 8, color=MUTED)),
                         Paragraph(num(st["r1w"]), S_NUM), Paragraph(num(st["r1m"]), S_NUM),
                         Paragraph(num(st["vs1w"], "", True), S_NUM), Paragraph(num(st["vs1m"], "", True), S_NUM)])
        body = table(rows, [34 * mm, 40 * mm, 21 * mm, 21 * mm, 29 * mm, CONTENT_W - 145 * mm], right_from=2) if src else Paragraph("None this week.", S_SMALL)
        return [KeepTogether(section(kicker, title, sub, anchor=anchor, outline=outline) + [body]), Spacer(1, 24)]

    story += movers("Leaders", f"{s.get('leaders')} stocks beat their sector on both horizons",
                    "The top 15 by combined outperformance (1W + 1M). A stock in two sectors can appear twice.",
                    report.get("top_movers", []), "leaders", "Leaders")
    story += movers("Laggards", f"{s.get('laggards')} stocks trail their sector on both horizons",
                    "The 15 deepest gaps first.", report.get("laggards", []), "laggards", "Laggards")

    # ---- study buckets, 2 x 2 ----
    meta = [("strength_leaders", "Strength leaders", "Leaders in strong sectors", POS),
            ("watch", "Watch", "Near-leaders and pullbacks in strong sectors", BLU),
            ("stock_specific", "Stock-specific", "Leaders outside the strong sectors", AMB),
            ("relative_weakness", "Relative weakness", "Laggards and bounce-only in strong sectors", NEG)]
    half_b = (CONTENT_W - 8 * mm) / 2
    cards = []
    for key, title, sub, ink in meta:
        items = (report.get("buckets", {}).get(key) or {}).items()
        body = [Paragraph(f"{sector_link(sec, by_label.get(sec))}  {', '.join(stock_link(sym, bold=False) for sym in syms)}",
                          _style("bb", 8.8, leading=13, color=MUTED)) for sec, syms in items] or [Paragraph("None this week.", S_SMALL)]
        cards.append([Paragraph(f"<font color='{hexof(ink)}'><b>{title}</b></font>", _style("bt", 12, leading=15)),
                      Paragraph(sub, S_SMALL), Spacer(1, 6)] + body)
    grid2 = Table([[cards[0], "", cards[1]], [cards[2], "", cards[3]]], colWidths=[half_b, 8 * mm, half_b])
    gstyle = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
              ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 18)]
    for (r, cidx), (_, _, _, ink) in zip([(0, 0), (0, 2), (1, 0), (1, 2)], meta):
        gstyle.append(("LINEABOVE", (cidx, r), (cidx, r), 1.6, ink))
    grid2.setStyle(TableStyle(gstyle))
    story.append(KeepTogether(section("Study list", "Four study buckets",
                                      "From 1W and 1M returns against each stock's own sector. For learning only; not a buy or sell list.",
                                      anchor="buckets", outline="Study buckets") + [grid2]))
    story.append(PageBreak())

    # ---- method & disclaimer ----
    story += section("Method", "Notes on the numbers",
                     esc(f"Angel One daily closes up to {nice_date(report.get('end_date'))}. Sector lists: {report.get('constituents_source', 'NSE')}."),
                     anchor="method", outline="Method and disclaimer")
    notes = [
        ("One set of dates", "1W is the last close against the last close on or before 7 days earlier; 1M against one calendar month earlier. "
                             "Every sector and every stock uses the same dates, so a stock has one return wherever it appears."),
        ("Sector verdict", "STRONG when the sector index's daily, weekly and monthly RSI(14) are all above 60; WEAK when all three are "
                           "below 40; otherwise MIXED. Weekly and monthly RSI include the week and month in progress."),
        ("Momentum map", "Each sector's 1W and 1M return minus the Nifty 50's, in percentage points; the quadrant tells whether the sector "
                         "is ahead of the market on both horizons, only on one, or on neither."),
        ("Last week and rotation", "Every figure is also worked out one week earlier (the close on or before 7 days before), so the "
                                   "report shows the rank moves and the verdicts that changed. The quadrant compares the sector's 1W and 1M "
                                   "return with the Nifty 50's: Leading (ahead on both), Improving (the week only), Weakening (the month "
                                   "only), Lagging (neither); the map draws the last 4 weeks."),
        ("Breadth", "Share of a sector's stocks above their 50-day and 200-day average and with a daily RSI(14) above 60, and how many "
                    "made a new 52-week high this week (stocks with less than a year of history are left out of the last two). "
                    "Broad: 70%+ above the 50-day average; Moderate: 40-70%; Narrow: below 40%."),
        ("Groups", "Near-leader: beats the sector on one horizon and is within 1.5pp on the other. Bounce-only: beats the sector "
                   "this week but trails it by more than 1.5pp on the month."),
        ("Coverage", "Sector members are NSE's current index constituents. Capital Market has no index on Angel One, so its sector line "
                     "is the equal-weight average of its stocks and it has no RSI verdict."
                     + (f" No data this week for: {esc(', '.join(report['missing']))}." if report.get("missing") else "")),
    ]
    for t, txt in notes:
        story.append(KeepTogether([Paragraph(t, _style("nt", 10, bold=True)), Spacer(1, 2), Paragraph(txt, S_BODY), Spacer(1, 9)]))
    story += [Spacer(1, 8)] + section("Disclaimer", "Important information")
    for t, txt in (
        ("Purpose.", "Generated by Scanner for personal market learning and education only."),
        ("Not a recommendation.", "Nothing here is a recommendation, offer or solicitation to buy, sell or hold any security, or investment, "
                                  "trading, tax or legal advice. Stocks and sectors are shown only as examples."),
        ("Not a SEBI research report.", "This is not a research report or investment advice under the SEBI (Research Analysts) or (Investment "
                                        "Advisers) Regulations. Consult a SEBI-registered professional before acting."),
        ("Market risk.", "Investments in securities markets are subject to market risks. Past performance does not indicate future results."),
        ("Data and method.", "Built automatically from Angel One price data and NSE index lists; it may contain delays, gaps or errors. "
                             "Rankings use only 1W and 1M price returns and RSI, and ignore valuation, earnings, liquidity, news and risk. "
                             "Chart links open TradingView, a third-party site."),
    ):
        story.append(Paragraph(f"<font color='#111827'><b>{t}</b></font> {txt}", _style("disc", 8.6, leading=12.5, color=MUTED, space_after=5)))

    doc.build(story)
    return buf.getvalue()
