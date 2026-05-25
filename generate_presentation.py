#!/usr/bin/env python3
"""
generate_presentation.py
Creates presentation.pdf — visual, sparse, talk-driven.
Run from repo root: python3 generate_presentation.py
"""

import os, math
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import Paragraph, Table, TableStyle, Image

# ── Geometry ──────────────────────────────────────────────────────────────────
W, H = 960, 540

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1B3A5C")
DKNAV   = colors.HexColor("#0F2236")
ORANGE  = colors.HexColor("#E07B39")
BLUE    = colors.HexColor("#2E86AB")
LTBLUE  = colors.HexColor("#E8F4FB")
LTGRAY  = colors.HexColor("#F5F7FA")
MGRAY   = colors.HexColor("#C8D2DC")
DKTEXT  = colors.HexColor("#1C1C2E")
MUTED   = colors.HexColor("#6A7482")
WHITE   = colors.white
GREEN   = colors.HexColor("#27AE60")
RED     = colors.HexColor("#C0392B")
PURPLE  = colors.HexColor("#6C3483")

HEADER_H = 64
FOOTER_H = 26
ML = 52
MR = 52
CW = W - ML - MR
CT = H - HEADER_H - 12   # content top
CB = FOOTER_H + 10        # content bottom

FIG_DIR       = os.path.join(os.path.dirname(__file__), "results", "cross_comparison")
OUT           = os.path.join(os.path.dirname(__file__), "presentation.pdf")
TOTAL_SLIDES  = 15

# ── Style factory ─────────────────────────────────────────────────────────────
def ps(name, fn="Helvetica", sz=13, ld=None, col=DKTEXT, align=TA_LEFT,
       li=0, sb=0, sa=0, bold=False):
    if bold and "Bold" not in fn:
        fn += "-Bold"
    return ParagraphStyle(name, fontName=fn, fontSize=sz,
                          leading=ld or round(sz * 1.38),
                          textColor=col, alignment=align,
                          leftIndent=li, spaceBefore=sb, spaceAfter=sa)

BODY    = ps("body",  sz=13, ld=20)
SMALL   = ps("sm",    sz=11, ld=17)
BOLD    = ps("bold",  sz=13, ld=20, bold=True)
CENTR   = ps("cen",   sz=13, ld=20, align=TA_CENTER)
WBODY   = ps("wb",    sz=13, ld=20, col=WHITE)
WBOLD   = ps("wbb",   sz=14, ld=21, col=WHITE, bold=True)
NBOLD   = ps("nb",    sz=13, ld=20, col=NAVY,   bold=True)
OBOLD   = ps("ob",    sz=12, ld=18, col=ORANGE, bold=True)
TBLHDR  = ps("th",    sz=11, ld=16, col=WHITE, bold=True, align=TA_CENTER)
TBLCL   = ps("td",    sz=11, ld=16, col=DKTEXT)
TBLCLS  = ps("tds",   sz=11, ld=16, col=DKTEXT, align=TA_CENTER)
CAPTION = ps("cap",   sz=9,  ld=13, col=MUTED,  align=TA_CENTER)

# ── Base helpers ──────────────────────────────────────────────────────────────
def draw_base(c, title, n, section=None):
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    # Header
    c.setFillColor(NAVY)
    c.rect(0, H - HEADER_H, W, HEADER_H, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(0, H - HEADER_H, 6, HEADER_H, stroke=0, fill=1)
    # Title in header
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 20)
    ty = H - HEADER_H + (HEADER_H - 20) / 2 + 2
    if section:
        ty = H - HEADER_H + HEADER_H * 0.64
    c.drawString(ML + 8, ty, title)
    if section:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#8AAEC8"))
        c.drawString(ML + 8, H - HEADER_H + HEADER_H * 0.24, section.upper())
    # Footer
    c.setFillColor(LTGRAY)
    c.rect(0, 0, W, FOOTER_H, stroke=0, fill=1)
    c.setFillColor(MGRAY)
    c.rect(0, FOOTER_H - 1, W, 1, stroke=0, fill=1)
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(ML, 8, "Staugaityte & Poggi  ·  IT-Universitetet i København  ·  May 2026")
    c.drawRightString(W - MR, 8, f"{n} / {TOTAL_SLIDES}")

def pdraw(c, text, style, x, y, width):
    p = Paragraph(text, style)
    _, ph = p.wrapOn(c, width, 9999)
    p.drawOn(c, x, y - ph)
    return y - ph

def fig(c, fname, x, y, max_w, max_h, caption=None):
    path = os.path.join(FIG_DIR, fname)
    img = Image(path)
    scale = min(max_w / img.imageWidth, max_h / img.imageHeight)
    dw, dh = img.imageWidth * scale, img.imageHeight * scale
    img.drawWidth, img.drawHeight = dw, dh
    img.drawOn(c, x + (max_w - dw) / 2, y - dh)
    fy = y - dh
    if caption:
        cp = Paragraph(caption, CAPTION)
        _, ch = cp.wrapOn(c, max_w, 9999)
        cp.drawOn(c, x + (max_w - dw) / 2, fy - ch - 2)
        fy -= ch + 6
    return fy

def callout(c, text, x, y, w, h, bg=LTBLUE, border=BLUE, style=None, pad=12):
    c.setFillColor(bg)
    c.setStrokeColor(border)
    c.setLineWidth(1.5)
    c.roundRect(x, y - h, w, h, 6, stroke=1, fill=1)
    p = Paragraph(text, style or BODY)
    _, ph = p.wrapOn(c, w - 2 * pad, 9999)
    p.drawOn(c, x + pad, y - pad - ph + (h - 2 * pad - ph) / 2)

def big_label(c, text, x, y, w, sz=42, col=NAVY, bold=True):
    """Single large centred number or word."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, sz)
    c.setFillColor(col)
    c.drawCentredString(x + w / 2, y - sz, text)
    return y - sz - 4

def hline(c, y, x=ML, w=CW, col=MGRAY, lw=0.6):
    c.setStrokeColor(col)
    c.setLineWidth(lw)
    c.line(x, y, x + w, y)

def card(c, x, y, w, h, title, title_col=NAVY, bg=LTGRAY, radius=6):
    """Draw a card with coloured header stripe."""
    c.setFillColor(bg)
    c.roundRect(x, y - h, w, h, radius, stroke=0, fill=1)
    c.setFillColor(title_col)
    c.roundRect(x, y - 28, w, 28, radius, stroke=0, fill=1)
    # Square off bottom of header
    c.rect(x, y - 28, w, 14, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x + w / 2, y - 20, title)
    return y - 32  # content starts here


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def slide_title(c, n):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    # Subtle gradient feel — dark band at bottom
    c.setFillColor(DKNAV)
    c.rect(0, 0, W, 80, stroke=0, fill=1)
    # Orange accent bar
    c.setFillColor(ORANGE)
    c.rect(0, H * 0.38 - 3, W, 4, stroke=0, fill=1)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(W / 2, H * 0.62, "Concurrent Hash Table Performance")
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(W / 2, H * 0.62 - 46, "Across ARM Hardware Tiers")

    c.setFillColor(colors.HexColor("#A8C4DC"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(W / 2, H * 0.29, "Vaiva Staugaityte  &  Elias Illeris Poggi")
    c.setFont("Helvetica", 12)
    c.drawCentredString(W / 2, H * 0.29 - 22, "Supervised by Peter Sestoft")
    c.setFillColor(colors.HexColor("#6A96B8"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, H * 0.29 - 44,
                        "IT-Universitetet i København  ·  May 26, 2026")
    # Footer
    c.setFillColor(DKNAV)
    c.rect(0, 0, W, FOOTER_H, stroke=0, fill=1)
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#4A7AA0"))
    c.drawRightString(W - MR, 8, f"{n} / {TOTAL_SLIDES}")


def slide_motivation(c, n):
    draw_base(c, "Why Does This Matter?", n, section="Background")

    # Big research question — centred, prominent
    q_h = 70
    q_y = CT - 10
    callout(c,
            "<para align='center'><b>Does the performance hierarchy of concurrent hash maps<br/>"
            "transfer from high-end to resource-constrained ARM hardware?</b></para>",
            ML, q_y, CW, q_h,
            bg=LTBLUE, border=BLUE,
            style=ps("rq", sz=16, ld=24, col=NAVY, bold=True, align=TA_CENTER))

    y = q_y - q_h - 28

    # Three columns: prior work | gap | target hardware
    cw3 = (CW - 40) / 3
    xs  = [ML, ML + cw3 + 20, ML + 2 * (cw3 + 20)]
    labels = ["Prior work", "The gap", "Our target hardware"]
    cols   = [BLUE, ORANGE, NAVY]
    icons  = ["x86 servers\nApple Silicon\nHigh-end ARM", "?", "IoT · Wearables\nBedside diagnostics\nEdge nodes"]
    sz_i   = [13, 48, 13]

    for i, (x, lbl, col, icon, sz) in enumerate(zip(xs, labels, cols, icons, sz_i)):
        # Card background
        bh = 140
        c.setFillColor(LTGRAY)
        c.roundRect(x, y - bh, cw3, bh, 6, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(x, y - 26, cw3, 26, 6, stroke=0, fill=1)
        c.rect(x, y - 26, cw3, 13, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + cw3 / 2, y - 18, lbl)

        # Icon / text inside card
        c.setFont("Helvetica-Bold" if sz > 20 else "Helvetica", sz)
        c.setFillColor(col)
        if "\n" in icon:
            lines = icon.split("\n")
            ly = y - 52
            for line in lines:
                c.setFont("Helvetica", 12)
                c.drawCentredString(x + cw3 / 2, ly, line)
                ly -= 18
        else:
            c.drawCentredString(x + cw3 / 2, y - 68, icon)

    # Arrow between cards
    for ax in [xs[0] + cw3 + 4, xs[1] + cw3 + 4]:
        c.setStrokeColor(MGRAY)
        c.setFillColor(MGRAY)
        c.setLineWidth(2)
        mid_y = y - 85
        c.line(ax + 2, mid_y, ax + 14, mid_y)
        # arrowhead
        c.triangle = None
        p_arr = c.beginPath()
        p_arr.moveTo(ax + 16, mid_y)
        p_arr.lineTo(ax + 10, mid_y + 5)
        p_arr.lineTo(ax + 10, mid_y - 5)
        p_arr.close()
        c.drawPath(p_arr, stroke=0, fill=1)

    y -= 158
    pdraw(c,
          "ARM-based embedded hardware shares an ISA with our HPC node — "
          "but not cores, cache, or bandwidth. "
          "<b>Do the same algorithms win?</b>",
          ps("mot", sz=12, ld=19, col=MUTED, align=TA_CENTER),
          ML, y, CW)


def slide_hardware(c, n):
    draw_base(c, "Two ARM Machines, One Large Gap", n, section="Background")

    y = CT - 4

    # Two big cards side by side
    cw2 = (CW - 30) / 2
    rx  = ML + cw2 + 30

    def hw_card(x, title, col, specs):
        bh = y - CB - 4
        c.setFillColor(col)
        c.roundRect(x, CB + 4, cw2, bh, 8, stroke=0, fill=1)
        # Header
        c.setFillColor(colors.HexColor("#0F2236") if col == NAVY else colors.HexColor("#7A3500"))
        c.roundRect(x, y - 52, cw2, 52, 8, stroke=0, fill=1)
        c.rect(x, y - 52, cw2, 26, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(x + cw2 / 2, y - 32, title)

        sy = y - 72
        for key, val, highlight in specs:
            c.setFillColor(WHITE if not highlight else colors.HexColor("#FFE8D0"))
            c.roundRect(x + 12, sy - 22, cw2 - 24, 22, 4, stroke=0, fill=1)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(x + 20, sy - 8, key)
            c.setFillColor(DKNAV if not highlight else ORANGE)
            c.setFont("Helvetica-Bold", 13)
            c.drawRightString(x + cw2 - 20, sy - 8, val)
            sy -= 28

    hw_card(ML, "Raspberry Pi 5", NAVY, [
        ("Architecture",   "ARM Cortex-A76", False),
        ("Physical cores", "4",              True),
        ("Clock speed",    "~2.4 GHz",       False),
        ("L3 cache",       "2 MB",           True),
        ("DRAM",           "8 GB LPDDR4X",  False),
        ("Threads tested", "1 · 2 · 4 · 8", False),
    ])
    hw_card(rx, "NVIDIA DGX Spark (HPC)", colors.HexColor("#7A3F00"), [
        ("Architecture",   "ARMv9.2-A (aarch64)",       False),
        ("SoC",            "NVIDIA GB10",                False),
        ("Physical cores", "20  (10×X925 + 10×A725)",   True),
        ("L3 cache",       "24 MiB aggregate",           True),
        ("DRAM",           "128 GB LPDDR5X",             False),
        ("Mem bandwidth",  "~273 GB/s",                  False),
    ])

    # "Same ISA" callout at top between cards
    c.setFillColor(ORANGE)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W / 2, y - 6, "⟵  both  aarch64  ⟶")


def slide_implementations_overview(c, n):
    draw_base(c, "8 Implementations · 3 Families", n, section="Experiments")

    y = CT - 6
    cw3 = (CW - 66) / 4
    gap = 22

    families = [
        ("COARSE", MUTED, [("SynchronizedMap", "Single global lock")],
         "One lock\nserialises all"),
        ("FINE-GRAINED", BLUE, [
            ("StripedMap",            "reads + writes lock"),
            ("StripedMapPadded",      "+ cache-line padding"),
            ("StripedWriteMap",       "reads lock-free"),
            ("StripedWriteMapPadded", "+ cache-line padding"),
            ("StripedLevelWriteMap",  "per-stripe resize"),
        ], "32 independent\nstripe locks"),
        ("LOCK-FREE", PURPLE, [
            ("HashTrieMap",           "CAS-based Ctrie"),
        ], "No locks — \nCAS only"),
        ("JDK", colors.HexColor("#27AE60"), [
            ("WrapConcurrentHashMap", "production baseline"),
        ], "Fine-grained locks\n+ CAS internally"),
    ]

    for i, (fname, col, impls, subtitle) in enumerate(families):
        x = ML + i * (cw3 + gap)
        bh = y - CB - 4

        # Card background
        c.setFillColor(colors.HexColor("#F0F4F8") if col != MUTED else colors.HexColor("#F4F4F4"))
        c.roundRect(x, CB + 4, cw3, bh, 8, stroke=0, fill=1)

        # Header
        c.setFillColor(col)
        hh = 44
        c.roundRect(x, y - hh, cw3, hh, 8, stroke=0, fill=1)
        c.rect(x, y - hh, cw3, hh // 2, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + cw3 / 2, y - 28, fname)

        # Subtitle (italicised descriptor)
        c.setFillColor(col)
        c.setFont("Helvetica-Oblique", 10)
        for li, line in enumerate(subtitle.split("\n")):
            c.drawCentredString(x + cw3 / 2, y - hh - 16 - li * 14, line)

        # Impl list
        iy = y - hh - 14 - len(subtitle.split("\n")) * 14 - 10
        for iname, idesc in impls:
            # Name
            c.setFillColor(WHITE)
            c.roundRect(x + 10, iy - 38, cw3 - 20, 38, 4, stroke=0, fill=1)
            c.setFillColor(col)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x + 18, iy - 14, iname)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(x + 18, iy - 28, idesc)
            iy -= 46


def slide_false_sharing(c, n):
    draw_base(c, "False Sharing & Cache-Line Padding", n, section="Experiments")

    y = CT - 10
    mid = W / 2
    bw  = 380   # diagram width each side
    lx  = ML
    rx  = mid + 20

    # ── Left: UNPADDED ──────────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(lx, y, "Without padding")
    y1 = y - 20

    # Cache line rectangle
    cl_w, cl_h = bw, 34
    c.setFillColor(colors.HexColor("#E8ECF0"))
    c.setStrokeColor(MGRAY)
    c.setLineWidth(1)
    c.rect(lx, y1 - cl_h, cl_w, cl_h, stroke=1, fill=1)

    # 4 lock boxes packed tightly inside
    lock_w = 56
    lock_h = 24
    lock_gap = 6
    lx0 = lx + 8
    for li in range(4):
        lc = RED if li == 0 else colors.HexColor("#9EB3C8")
        c.setFillColor(lc)
        c.roundRect(lx0 + li * (lock_w + lock_gap), y1 - cl_h + 5, lock_w, lock_h, 3,
                    stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(lx0 + li * (lock_w + lock_gap) + lock_w / 2,
                            y1 - cl_h + 14, f"lock {li}")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(lx + cl_w / 2, y1 - cl_h - 10, "← 64-byte cache line →")

    y1 -= cl_h + 30

    # Invalidation explosion
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(lx, y1, "Thread A writes lock 0  →")
    y1 -= 18
    c.setFillColor(RED)
    c.setFont("Helvetica", 11)
    c.drawString(lx, y1, "  entire cache line invalidated on every other core")
    y1 -= 16
    c.drawString(lx, y1, "  — even cores working on lock 1, 2, 3")

    y1 -= 24
    callout(c, "This is <b>false sharing</b>: cores pay coherence traffic for data "
               "they don't share.",
            lx, y1, bw - 10, 40,
            bg=colors.HexColor("#FEF0EC"), border=RED,
            style=ps("fs", sz=11, ld=16))

    # ── Right: PADDED ───────────────────────────────────────────────────────
    y2 = y - 20
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(rx, y + 0, "With padding  (stride = 16 slots)")

    # Two separate cache line rectangles
    pcl_w = 130
    for pi in range(2):
        px = rx + pi * (pcl_w + 30)
        c.setFillColor(colors.HexColor("#E8F5F0"))
        c.setStrokeColor(GREEN)
        c.setLineWidth(1)
        c.rect(px, y2 - cl_h, pcl_w, cl_h, stroke=1, fill=1)
        lc = GREEN if pi == 0 else colors.HexColor("#9EB3C8")
        c.setFillColor(lc)
        c.roundRect(px + 12, y2 - cl_h + 5, lock_w, lock_h, 3, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(px + 12 + lock_w / 2, y2 - cl_h + 14, f"lock {pi}")
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawCentredString(px + pcl_w / 2, y2 - cl_h - 10, "64 bytes")

    # Dots between
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 14)
    c.drawCentredString(rx + 2 * pcl_w + 10, y2 - cl_h / 2 + 2, "···")

    y2 -= cl_h + 30
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(rx, y2, "Thread A writes lock 0  →")
    y2 -= 18
    c.setFillColor(GREEN)
    c.setFont("Helvetica", 11)
    c.drawString(rx, y2, "  only lock 0's cache line affected")
    y2 -= 16
    c.drawString(rx, y2, "  lock 1, 2, 3 untouched on other cores")

    y2 -= 24
    callout(c, "Effect is strongest at <b>high thread counts</b> on many-core hardware: "
               "64 simultaneous writers → constant coherence traffic without padding.",
            rx, y2, bw - 10, 40,
            bg=LTBLUE, border=BLUE,
            style=ps("pad", sz=11, ld=16))

    # Divider
    c.setStrokeColor(MGRAY)
    c.setLineWidth(0.8)
    c.line(mid + 8, CT - 4, mid + 8, CB + 4)


def slide_workload(c, n):
    draw_base(c, "18 Workload Configurations per Implementation", n, section="Experiments")

    # Big centred formula
    y = CT - 18
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(NAVY)
    c.drawCentredString(W / 2, y - 48, "3  ×  2  ×  3  =  18")
    y -= 62

    c.setFont("Helvetica", 13)
    c.setFillColor(MUTED)
    c.drawCentredString(W / 2, y, "read ratios × key ranges × distributions")
    y -= 36

    # Three axis boxes
    axes = [
        ("Read ratio", ["0.8  read-heavy", "0.5  balanced", "0.2  write-heavy"],
         BLUE, "Tests whether lock-free reads pay off where it matters"),
        ("Key range",  ["1,000  fits in RPi L3", "1,000,000  exceeds RPi L3"],
         ORANGE, "Separates contention-bound from memory-bound regimes"),
        ("Distribution", ["Uniform", "Zipfian-0.5  mild skew", "Zipfian-0.99  heavy skew"],
         PURPLE, "Real workloads are skewed — Zipf's law holds broadly"),
    ]
    cw3 = (CW - 40) / 3
    for i, (title, vals, col, why) in enumerate(axes):
        x = ML + i * (cw3 + 20)
        bh = y - CB - 4
        c.setFillColor(LTGRAY)
        c.roundRect(x, CB + 4, cw3, bh, 6, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(x, y - 28, cw3, 28, 6, stroke=0, fill=1)
        c.rect(x, y - 28, cw3, 14, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + cw3 / 2, y - 19, title)

        vy = y - 50
        for v in vals:
            c.setFillColor(col)
            c.circle(x + 18, vy + 4, 3, stroke=0, fill=1)
            c.setFillColor(DKTEXT)
            c.setFont("Helvetica", 11)
            c.drawString(x + 28, vy, v)
            vy -= 20

        # WHY line
        wy = CB + 22
        p = Paragraph(f"<i>{why}</i>", ps("why", sz=9, ld=13, col=MUTED, align=TA_CENTER))
        _, ph = p.wrapOn(c, cw3 - 16, 9999)
        p.drawOn(c, x + 8, wy - ph)


def slide_jmh(c, n):
    draw_base(c, "JMH: Getting Honest Numbers from the JVM", n, section="Experiments")

    y = CT - 8

    # One-liner top
    pdraw(c, "The JVM's JIT compiler will optimise away your benchmark unless you stop it.",
          ps("jt", sz=14, ld=21, col=NAVY, bold=True, align=TA_CENTER),
          ML, y, CW)
    y -= 36

    # Four mechanism cards in a 2×2 grid
    mechs = [
        ("Warmup  (5 × 2 s)",
         "Let the JIT compile and stabilise before recording anything.",
         BLUE),
        ("Fork  (2 fresh JVMs)",
         "JIT profiles don't bleed between implementations.",
         NAVY),
        ("Blackhole",
         "Forces the compiler to treat return values as observable — "
         "prevents get() from being eliminated as dead code.",
         ORANGE),
        ("Scope.Benchmark vs Scope.Thread",
         "One shared map across all threads (correct concurrent model). "
         "Each thread gets its own Random.",
         PURPLE),
    ]
    cw2 = (CW - 24) / 2
    ch  = (y - CB - 10) / 2 - 8

    for i, (title, body, col) in enumerate(mechs):
        row, col_i = divmod(i, 2)
        mx = ML + col_i * (cw2 + 24)
        my = y - row * (ch + 12)

        c.setFillColor(LTGRAY)
        c.roundRect(mx, my - ch, cw2, ch, 6, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(mx, my - 30, cw2, 30, 6, stroke=0, fill=1)
        c.rect(mx, my - 30, cw2, 15, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(mx + cw2 / 2, my - 21, title)

        p = Paragraph(body, ps("jb", sz=11, ld=17, col=DKTEXT))
        _, ph = p.wrapOn(c, cw2 - 20, 9999)
        p.drawOn(c, mx + 10, my - 36 - ph)


def slide_geomean(c, n):
    draw_base(c, "Summarising Across Configurations: Geometric Mean", n, section="Experiments")

    y = CT - 16

    # The core insight large
    pdraw(c,
          "Our throughput values span <b>two orders of magnitude</b>. "
          "Arithmetic mean is dominated by the fast end and masks the slow end.",
          ps("gi", sz=14, ld=22, col=DKTEXT, align=TA_CENTER),
          ML, y, CW)
    y -= 52

    # Visual comparison: two bars
    col_w = (CW - 60) / 2
    rx = ML + col_w + 60

    def draw_comparison(x, label, vals, mean_fn, mean_label, bar_col):
        # Label
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(NAVY)
        c.drawCentredString(x + col_w / 2, y, label)
        by = y - 22

        max_v = 220
        bar_area_w = col_w - 60

        for v, name in vals:
            bw = (v / max_v) * bar_area_w
            c.setFillColor(colors.HexColor("#D0DCEA"))
            c.rect(x + 50, by - 14, bar_area_w, 14, stroke=0, fill=1)
            c.setFillColor(bar_col)
            c.rect(x + 50, by - 14, bw, 14, stroke=0, fill=1)
            c.setFont("Helvetica", 9)
            c.setFillColor(MUTED)
            c.drawRightString(x + 46, by - 4, name)
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(DKTEXT)
            c.drawString(x + 50 + bw + 3, by - 4, f"{v}")
            by -= 22

        # Mean line
        mean_v = mean_fn([v for v, _ in vals])
        mean_x = x + 50 + (mean_v / max_v) * bar_area_w
        c.setStrokeColor(RED)
        c.setLineWidth(2)
        c.line(mean_x, by + 12, mean_x, y - 14)
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(mean_x, by + 2, f"mean ≈ {mean_v:.0f}")

    vals = [(4, "SyncMap"), (40, "Striped"), (68, "WrapCHM"), (211, "WrapCHM t=64")]

    def arith(vs): return sum(vs) / len(vs)
    def geom(vs):
        import math
        return math.exp(sum(math.log(v) for v in vs) / len(vs))

    draw_comparison(ML, "Arithmetic mean", vals, arith, "", BLUE)
    draw_comparison(rx, "Geometric mean", vals, geom, "", GREEN)

    y2 = CB + 44
    callout(c,
            "Geometric mean gives <b>equal weight to equal relative changes</b>. "
            "A 2× improvement is a 2× improvement regardless of the baseline. "
            "Formally: <i>exp( mean( log(x₁) … log(xₙ) ) )</i>.",
            ML, y2, CW, 42,
            bg=LTBLUE, border=BLUE,
            style=ps("gm", sz=12, ld=18))


def slide_fig1_rankings(c, n):
    draw_base(c, "Finding 1 — Rankings Transfer Across Hardware", n, section="Findings")

    y = CT
    fig_w = CW * 0.47
    txt_x = ML + fig_w + 28
    txt_w = CW - fig_w - 28

    fig(c, "fig1_performance_overview.png", ML, y, fig_w, y - CB,
        caption="Rank on RPi (left) vs HPC (right), Zipfian-0.99, peak thread count")

    # Big headline
    y2 = y - 6
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(NAVY)
    c.drawString(txt_x, y2 - 30, "The hierarchy holds.")
    y2 -= 50

    items = [
        (WHITE, GREEN,  "WrapCHM  →  #1 on both"),
        (WHITE, RED,    "SyncMap  →  last on both"),
        (WHITE, ORANGE, "HashTrieMap — the exception"),
    ]
    for bg, col, text in items:
        c.setFillColor(LTGRAY)
        c.roundRect(txt_x, y2 - 30, txt_w, 30, 4, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(txt_x, y2 - 30, 6, 30, 4, stroke=0, fill=1)
        c.rect(txt_x + 3, y2 - 30, 3, 30, stroke=0, fill=1)
        c.setFillColor(DKTEXT)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(txt_x + 16, y2 - 18, text)
        y2 -= 38

    y2 -= 6
    callout(c,
            "A crossing line in the chart means rank changed. "
            "Most lines run parallel — the ordering is stable.",
            txt_x, y2, txt_w, 48,
            bg=LTBLUE, border=BLUE,
            style=ps("r1", sz=11, ld=17))


def slide_hashtrie_outlier(c, n):
    draw_base(c, "Finding 2 — The Central Outlier", n, section="Findings")

    y = CT - 4

    # THE BIG RESULT
    bh = 68
    c.setFillColor(colors.HexColor("#FFF3EC"))
    c.setStrokeColor(ORANGE)
    c.setLineWidth(2)
    c.roundRect(ML, y - bh, CW, bh, 8, stroke=1, fill=1)
    c.setFillColor(ORANGE)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(W / 2, y - 38, "HashTrieMap: #7 on RPi ·  #2 on HPC")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 12)
    c.drawCentredString(W / 2, y - 56, "Same code. Same benchmark. Different hardware.")
    y -= bh + 22

    # Two column explanation
    cw2 = (CW - 24) / 2
    rx  = ML + cw2 + 24

    # Left — why fails on RPi
    c.setFillColor(colors.HexColor("#FDECEC"))
    c.roundRect(ML, y - (y - CB - 4), cw2, y - CB - 4, 6, stroke=0, fill=1)
    c.setFillColor(RED)
    c.roundRect(ML, y - 30, cw2, 30, 6, stroke=0, fill=1)
    c.rect(ML, y - 30, cw2, 15, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(ML + cw2 / 2, y - 20, "Why it fails on RPi 5")

    rpi_pts = [
        ("Pointer-chasing", "INode→CNode→SNode hops frequently\nmiss the 2 MB L3 cache"),
        ("GC pressure", "Every mutation allocates new nodes.\nGC competes with 4 benchmark threads."),
    ]
    py = y - 48
    for title, body in rpi_pts:
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(ML + 12, py, title)
        py -= 16
        c.setFillColor(DKTEXT)
        c.setFont("Helvetica", 10)
        for line in body.split("\n"):
            c.drawString(ML + 20, py, line)
            py -= 14
        py -= 8

    # Right — why excels on HPC
    c.setFillColor(colors.HexColor("#ECFDF5"))
    c.roundRect(rx, y - (y - CB - 4), cw2, y - CB - 4, 6, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.roundRect(rx, y - 30, cw2, 30, 6, stroke=0, fill=1)
    c.rect(rx, y - 30, cw2, 15, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(rx + cw2 / 2, y - 20, "Why it excels on HPC")

    hpc_pts = [
        ("24 MiB L3 cache", "Trie nodes stay resident.\nPointer-chasing cost vanishes."),
        ("20 cores", "GC competes less with benchmark threads.\nLock-free CAS scales at high thread counts."),
    ]
    py2 = y - 48
    for title, body in hpc_pts:
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(rx + 12, py2, title)
        py2 -= 16
        c.setFillColor(DKTEXT)
        c.setFont("Helvetica", 10)
        for line in body.split("\n"):
            c.drawString(rx + 20, py2, line)
            py2 -= 14
        py2 -= 8


def slide_fig2_ceiling(c, n):
    draw_base(c, "Finding 3 — The Hardware Ceiling", n, section="Findings")

    y = CT
    fig_w = CW * 0.63
    txt_x = ML + fig_w + 22
    txt_w = CW - fig_w - 22

    fig(c, "fig2_scalability.png", ML, y, fig_w, y - CB,
        caption="Thread-count scaling (ops/μs). Top: 1K keys. Bottom: 1M keys.")

    y2 = y - 6
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(RED)
    c.drawString(txt_x, y2 - 28, "RPi saturates at 4 threads.")
    y2 -= 48

    c.setFont("Helvetica", 12)
    c.setFillColor(DKTEXT)
    for line in [
        "Every implementation flatlines.",
        "Algorithm choice barely matters.",
        "",
        "→ Use the simplest correct option.",
    ]:
        if line:
            c.drawString(txt_x, y2, line)
        y2 -= 20

    y2 -= 10
    hline(c, y2, txt_x, txt_w)
    y2 -= 18

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(GREEN)
    c.drawString(txt_x, y2, "HPC keeps scaling to t=64.")
    y2 -= 20
    c.setFont("Helvetica", 12)
    c.setFillColor(DKTEXT)
    c.drawString(txt_x, y2, "Algorithm choice matters here.")


def slide_fig4_zipfian(c, n):
    draw_base(c, "Finding 4 — Same Skew, Opposite Effects", n, section="Findings")

    y = CT
    fh = (y - CB) * 0.65

    fig(c, "fig4_distribution_sensitivity.png", ML, y, CW, fh,
        caption="% throughput change: uniform → Zipfian-0.99, at peak thread count. "
                "Positive bar = skew hurts.")

    y2 = y - fh - 16
    cw2 = (CW - 24) / 2
    rx  = ML + cw2 + 24

    callout(c,
            "<b>1K keys (in RPi L3):</b> hot keys pile onto the same stripe lock. "
            "Skew hurts both platforms — HPC more, because more threads contend.",
            ML, y2, cw2, 58, bg=colors.HexColor("#FEF0EC"), border=RED,
            style=ps("z1", sz=11, ld=17))

    callout(c,
            "<b>1M keys (exceeds RPi L3):</b> RPi benefits from skew — hot keys stay in L1/L2. "
            "HPC is hurt — cache was already warm, skew only adds contention.",
            rx, y2, cw2, 58, bg=LTBLUE, border=BLUE,
            style=ps("z2", sz=11, ld=17))


def slide_fig3_heatmap(c, n):
    draw_base(c, "Finding 5 — How Much Faster Is the HPC?", n, section="Findings")

    y = CT
    fig_w = CW * 0.55
    txt_x = ML + fig_w + 24
    txt_w = CW - fig_w - 24

    fig(c, "fig3_hardware_advantage.png", ML, y, fig_w, y - CB,
        caption="log₂(HPC / RPi) speedup. Geometric mean across 18 configurations.")

    y2 = y - 8
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(NAVY)
    c.drawCentredString(txt_x + txt_w / 2, y2 - 42, "~2×")
    c.setFont("Helvetica", 14)
    c.setFillColor(MUTED)
    c.drawCentredString(txt_x + txt_w / 2, y2 - 62, "faster at matched thread counts")
    y2 -= 90

    c.setFont("Helvetica", 12)
    c.setFillColor(DKTEXT)
    pts = [
        "Clock: ~4.0 GHz vs ~2.4 GHz",
        "Bandwidth: LPDDR5X vs LPDDR4X",
        "No algorithmic outliers in heatmap",
    ]
    for pt in pts:
        c.setFillColor(ORANGE)
        c.circle(txt_x + 6, y2 + 4, 3, stroke=0, fill=1)
        c.setFillColor(DKTEXT)
        c.drawString(txt_x + 16, y2, pt)
        y2 -= 22

    y2 -= 8
    callout(c,
            "At low thread counts, the gap is a hardware property, not an algorithmic one.",
            txt_x, y2, txt_w, 44,
            bg=LTGRAY, border=MGRAY,
            style=ps("hw", sz=11, ld=17))


def slide_guidelines(c, n):
    draw_base(c, "Practical Guidelines", n, section="Conclusions")

    y = CT - 4
    cw2 = (CW - 24) / 2
    rx  = ML + cw2 + 24
    bh  = y - CB - 52

    # Left card — RPi
    c.setFillColor(LTBLUE)
    c.roundRect(ML, CB + 48, cw2, bh, 8, stroke=0, fill=1)
    c.setFillColor(BLUE)
    c.roundRect(ML, y - 44, cw2, 44, 8, stroke=0, fill=1)
    c.rect(ML, y - 44, cw2, 22, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(ML + cw2 / 2, y - 28, "Few-core · small-cache")
    c.setFont("Helvetica", 10)
    c.drawCentredString(ML + cw2 / 2, y - 44, "(RPi 5 profile)")

    rpi = [
        ("✓", GREEN,  "Use StripedWriteMap"),
        ("✗", RED,    "Avoid HashTrieMap"),
        ("→", ORANGE, "Saturates at #cores — don't overengineer"),
    ]
    ry = y - 62
    for sym, col, txt in rpi:
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(ML + 16, ry, sym)
        c.setFillColor(DKTEXT)
        c.setFont("Helvetica", 12)
        c.drawString(ML + 34, ry, txt)
        ry -= 26

    # Right card — HPC
    c.setFillColor(colors.HexColor("#EDFAF3"))
    c.roundRect(rx, CB + 48, cw2, bh, 8, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.roundRect(rx, y - 44, cw2, 44, 8, stroke=0, fill=1)
    c.rect(rx, y - 44, cw2, 22, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(rx + cw2 / 2, y - 28, "Many-core · large-cache")
    c.setFont("Helvetica", 10)
    c.drawCentredString(rx + cw2 / 2, y - 44, "(HPC/server profile)")

    hpc = [
        ("✓", GREEN,  "WrapCHM or HashTrieMap"),
        ("✓", GREEN,  "Padded variants reduce false sharing"),
        ("✗", RED,    "Never SynchronizedMap in production"),
    ]
    hy = y - 62
    for sym, col, txt in hpc:
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(rx + 16, hy, sym)
        c.setFillColor(DKTEXT)
        c.setFont("Helvetica", 12)
        c.drawString(rx + 34, hy, txt)
        hy -= 26

    # Bottom synthesis
    callout(c,
            "<b>No universally optimal map.</b>  "
            "The right choice depends on core count and last-level cache size — "
            "both knowable at runtime.",
            ML, CB + 48, CW, 44,
            bg=colors.HexColor("#FFF8EC"), border=ORANGE,
            style=ps("syn", sz=12, ld=19))


def slide_future_work(c, n):
    draw_base(c, "Future Work", n, section="Conclusions")

    y = CT - 10
    items = [
        (BLUE,   "Hardware-level profiling",
                 "Run perf stat counters — convert our inferences about cache misses and CAS retries into direct evidence."),
        (ORANGE, "Latency distribution",
                 "We measured throughput. Tail latency matters for real-time applications. JMH's SampleTime mode would capture it."),
        (PURPLE, "Hardware-adaptive implementation",
                 "Query availableProcessors() and LLC size at startup, select the backing implementation automatically."),
        (NAVY,   "Broader hardware coverage",
                 "BeagleBone Black (no L3 at all), single-core devices, and a systematic literature review."),
    ]
    item_h = (y - CB - 8) / len(items) - 8
    for i, (col, title, body) in enumerate(items):
        iy = y - i * (item_h + 8)
        c.setFillColor(LTGRAY)
        c.roundRect(ML, iy - item_h, CW, item_h, 6, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(ML, iy - item_h, 6, item_h, 6, stroke=0, fill=1)
        c.rect(ML + 3, iy - item_h, 3, item_h, stroke=0, fill=1)

        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(ML + 18, iy - 20, title)
        p = Paragraph(body, ps(f"fw{i}", sz=11, ld=16, col=MUTED))
        _, ph = p.wrapOn(c, CW - 28, 9999)
        p.drawOn(c, ML + 18, iy - item_h + (item_h - 20 - ph) / 2)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    c = rl_canvas.Canvas(OUT, pagesize=(W, H))
    c.setTitle("Concurrent Hash Table Performance Across ARM Hardware Tiers")
    c.setAuthor("Staugaityte & Poggi — ITU Copenhagen 2026")

    slides = [
        slide_title,
        slide_motivation,
        slide_hardware,
        slide_implementations_overview,
        slide_false_sharing,
        slide_workload,
        slide_jmh,
        slide_geomean,
        slide_fig1_rankings,
        slide_hashtrie_outlier,
        slide_fig2_ceiling,
        slide_fig4_zipfian,
        slide_fig3_heatmap,
        slide_guidelines,
        slide_future_work,
    ]

    for i, fn in enumerate(slides, 1):
        fn(c, i)
        c.showPage()

    c.save()
    print(f"Saved → {OUT}")

if __name__ == "__main__":
    main()
