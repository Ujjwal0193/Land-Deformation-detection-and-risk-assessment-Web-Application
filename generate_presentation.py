"""
MineGuard — Product Pitch Presentation Generator (v3)
12 slides — rich context, screenshot placeholder for every app page.
Structure:
  Slide  1 : Title
  Slides 2-4 : Product Specification (Intro / Design / Use Cases)
  Slides 5-7 : Product Detail (Horizontal Displacement / 3D Space / Science)
  Slide  8 : Workflow overview
  Slides 9-12: Work Done — Pages 1+2, Pages 3+4, Pages 5+6, Pages 7+8
  Slide 12   : Conclusion
"""

import logging
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Logging ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename=PROJECT_ROOT / "logs" / "presentation_v3.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Colour Palette ────────────────────────────────────────────────────────────
BG_DARK  = RGBColor(0x09, 0x12, 0x1F)   # deep navy
BG_CARD  = RGBColor(0x13, 0x1E, 0x35)   # card surface
BG_DEEP  = RGBColor(0x06, 0x0D, 0x17)   # darkest bg (screenshot box)
BLUE_VIV = RGBColor(0x00, 0xB4, 0xFF)   # brand blue
AMBER    = RGBColor(0xF5, 0xA6, 0x23)   # accent amber
GREEN_OK = RGBColor(0x39, 0xD3, 0x53)   # success green
RED_CRIT = RGBColor(0xFF, 0x4C, 0x5E)   # danger red
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
MUTED    = RGBColor(0x8E, 0x9E, 0xB0)   # secondary text
LITE_BLU = RGBColor(0xB3, 0xE5, 0xFC)   # light blue text

TOTAL = 14  # update if slide count changes

# 16:9 widescreen
W = Inches(13.33)
H = Inches(7.5)


# ── Primitive helpers ─────────────────────────────────────────────────────────

def _blank(prs: Presentation) -> object:
    """Return a new blank slide."""
    return prs.slides.add_slide(prs.slide_layouts[6])


def bg(slide: object, color: RGBColor) -> None:
    """Fill slide background with a solid colour."""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def rect(slide: object,
         l: float, t: float, w: float, h: float,
         fill: RGBColor,
         line: RGBColor | None = None,
         line_pt: float = 0.75) -> object:
    """Add a filled rectangle. Coordinates in inches."""
    shp = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_pt)
    else:
        shp.line.fill.background()
    return shp


def txt(slide: object,
        text: str,
        l: float, t: float, w: float, h: float,
        size: float,
        bold: bool = False,
        italic: bool = False,
        color: RGBColor = WHITE,
        align: PP_ALIGN = PP_ALIGN.LEFT,
        wrap: bool = True) -> object:
    """Add a single-run text box."""
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf  = box.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    p.alignment = align
    r   = p.add_run()
    r.text           = text
    r.font.size      = Pt(size)
    r.font.bold      = bold
    r.font.italic    = italic
    r.font.color.rgb = color
    return box


def bullets_box(slide: object,
                items: list[tuple[str, str]],
                l: float, t: float, w: float, h: float,
                label_color: RGBColor = AMBER,
                body_color: RGBColor  = WHITE,
                size: float = 11.5,
                spacing: float = 8.0) -> None:
    """
    Render a list of (label, body) pairs in one text box.
    Label rendered bold in label_color; body in body_color.
    """
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf  = box.text_frame
    tf.word_wrap = True
    for i, (label, body) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(spacing)
        if label:
            r1 = p.add_run()
            r1.text           = f"▸ {label}  "
            r1.font.size      = Pt(size)
            r1.font.bold      = True
            r1.font.color.rgb = label_color
        r2 = p.add_run()
        r2.text           = body
        r2.font.size      = Pt(size)
        r2.font.color.rgb = body_color


def accent_bar(slide: object,
               color: RGBColor = BLUE_VIV,
               h: float = 0.07) -> None:
    """Thin full-width colour strip at top."""
    rect(slide, 0, 0, 13.33, h, color)


def slide_num(slide: object, n: int) -> None:
    """Bottom-right page counter."""
    txt(slide, f"{n} / {TOTAL}",
        l=12.1, t=7.14, w=1.1, h=0.28,
        size=8, color=MUTED, align=PP_ALIGN.RIGHT)


def section_tag(slide: object, label: str,
                color: RGBColor = BLUE_VIV) -> None:
    """Small ALL-CAPS section label, top-left."""
    txt(slide, label,
        l=0.45, t=0.1, w=10, h=0.3,
        size=8, bold=True, color=color)


def screenshot_box(slide: object,
                   page_label: str,
                   l: float, t: float, w: float, h: float,
                   border: RGBColor = BLUE_VIV) -> None:
    """
    A clearly delineated screenshot placeholder.
    Dashed inner area + centred instruction text.
    """
    # Outer border rect
    rect(slide, l, t, w, h, BG_DEEP, border, 1.5)
    # Inner subtle frame
    rect(slide, l + 0.08, t + 0.08, w - 0.16, h - 0.16, BG_DEEP, MUTED, 0.4)
    # Icon
    txt(slide, "📷",
        l=l + w / 2 - 0.4, t=t + h / 2 - 0.55,
        w=0.8, h=0.55, size=22,
        color=MUTED, align=PP_ALIGN.CENTER)
    # Label
    txt(slide, page_label,
        l=l + 0.1, t=t + h / 2 + 0.05, w=w - 0.2, h=0.45,
        size=9, bold=True, italic=True,
        color=border, align=PP_ALIGN.CENTER)
    txt(slide, "Insert screenshot here",
        l=l + 0.1, t=t + h / 2 + 0.48, w=w - 0.2, h=0.32,
        size=8, italic=True, color=MUTED, align=PP_ALIGN.CENTER)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════════════════════

def slide_title(prs: Presentation) -> None:
    """Slide 1 — Product name hero card."""
    log.info("Building Slide 1 — Title")
    s = _blank(prs)
    bg(s, BG_DARK)

    # Vertical left stripe
    rect(s, 0, 0, 0.6, 7.5, BLUE_VIV)

    # Giant product name
    txt(s, "Mine", l=0.9, t=0.85, w=11.5, h=2.1,
        size=100, bold=True, color=WHITE)
    txt(s, "Guard", l=0.9, t=2.85, w=11.5, h=2.1,
        size=100, bold=True, color=BLUE_VIV)

    # Divider line under name
    rect(s, 0.9, 5.05, 10.0, 0.05, MUTED)

    # Tagline
    txt(s,
        "Satellite-powered ground subsidence monitoring — "
        "designed for every mine site engineer.",
        l=0.9, t=5.2, w=11.2, h=0.65,
        size=16, italic=True, color=MUTED)

    # Tech pill row
    tags = [
        ("React + TypeScript", BLUE_VIV),
        ("Python FastAPI", AMBER),
        ("SNAP InSAR Engine", GREEN_OK),
        ("Sentinel-1  ASC+DSC", BLUE_VIV),
    ]
    px = 0.9
    for tag, clr in tags:
        rect(s, px, 6.0, 2.6, 0.42, BG_CARD, clr, 0.8)
        txt(s, tag, l=px + 0.05, t=6.02, w=2.5, h=0.38,
            size=9, bold=True, color=clr, align=PP_ALIGN.CENTER)
        px += 2.75

    # University badge
    txt(s, "Final Project  •  ECE Department  •  NIT Rourkela  •  Ujjwal Rawat (225EC6010)",
        l=0.9, t=6.85, w=12.0, h=0.35,
        size=8.5, color=MUTED, align=PP_ALIGN.LEFT)

    slide_num(s, 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDES 2-4 — PRODUCT SPECIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def slide_intro(prs: Presentation) -> None:
    """Slide 2 — Introduction: what is MineGuard and why it exists."""
    log.info("Building Slide 2 — Introduction")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, BLUE_VIV)
    section_tag(s, "PRODUCT SPECIFICATION  ›  INTRODUCTION")

    txt(s, "What is MineGuard?",
        l=0.45, t=0.48, w=12.5, h=0.85,
        size=36, bold=True, color=WHITE)

    txt(s,
        "MineGuard is a full-stack web application that uses free Sentinel-1 satellite radar "
        "data to automatically detect and track ground subsidence at active mine sites — "
        "with no programming or satellite expertise required.",
        l=0.45, t=1.38, w=12.4, h=0.85,
        size=13.5, italic=True, color=LITE_BLU)

    # Three information columns
    cols = [
        (BLUE_VIV, "🌍  Why It Matters",
         [("Problem", "Mining excavations cause ground to sink and slide — often undetected until too late."),
          ("Cost", "Traditional ground sensors are expensive, local, and require specialist teams."),
          ("Gap", "No affordable, automated tool existed for non-technical mine site engineers.")]),
        (AMBER, "📡  What It Uses",
         [("Satellite", "Free Sentinel-1 SAR images from the European Space Agency (ESA) Copernicus programme."),
          ("Engine", "SNAP (Sentinel Application Platform) for professional InSAR interferogram processing."),
          ("Stack", "React TypeScript frontend + Python FastAPI backend — runs entirely in a web browser.")]),
        (GREEN_OK, "✅  What It Delivers",
         [("Output", "Millimetre-precision ground displacement measurements at user-selected hotspot locations."),
          ("Report", "Automated geotechnical risk assessment: Low / Medium / High / Critical per hotspot."),
          ("Access", "Any mine on Earth, any timeframe from 2014–present, zero cost satellite data.")]),
    ]
    cx = 0.45
    for clr, heading, items in cols:
        rect(s, cx, 2.5, 4.06, 4.7, BG_CARD, clr, 1.2)
        txt(s, heading, l=cx + 0.18, t=2.68, w=3.7, h=0.55,
            size=13, bold=True, color=clr)
        rect(s, cx + 0.18, 3.28, 3.7, 0.04, clr)
        bullets_box(s, items,
                    l=cx + 0.18, t=3.38, w=3.72, h=3.6,
                    label_color=clr, body_color=WHITE,
                    size=11, spacing=6)
        cx += 4.3

    slide_num(s, 2)


def slide_design(prs: Presentation) -> None:
    """Slide 3 — Design philosophy: built for non-technical users."""
    log.info("Building Slide 3 — Design Philosophy")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, AMBER)
    section_tag(s, "PRODUCT SPECIFICATION  ›  USER EXPERIENCE", AMBER)

    txt(s, "Built for the Field Engineer",
        l=0.45, t=0.48, w=12.0, h=0.85,
        size=36, bold=True, color=WHITE)
    txt(s,
        "Every design decision was made for mine site engineers who have no computer science "
        "background. The application guides users through every step without jargon.",
        l=0.45, t=1.38, w=12.4, h=0.65,
        size=13, italic=True, color=MUTED)

    features = [
        ("📋", "Step-by-Step\nInstructions",
         "Every page opens with a clearly numbered instruction panel explaining exactly what "
         "to do next. The user never wonders what a button does."),
        ("🎨", "Purpose-Built\nDark Theme",
         "A high-contrast dark colour scheme reduces eye fatigue during long monitoring sessions. "
         "Key actions are highlighted in vivid blue."),
        ("📊", "Plain-English\nGraph Captions",
         "Each displacement chart is accompanied by an auto-generated sentence explaining what "
         "the graph shows — no data science knowledge needed."),
        ("🔒", "Boundary-Safe\nInputs",
         "Click-safety guards prevent users from placing hotspot markers outside the crop "
         "boundary, and warn before any destructive action is taken."),
        ("⚡", "Live Status\nFeedback",
         "The processing dashboard updates every 3 seconds so engineers always know which "
         "satellite pairs are running, complete, or waiting."),
    ]

    bx = 0.3
    for icon, title, desc in features:
        rect(s, bx, 2.25, 2.38, 4.95, BG_CARD, AMBER, 1.0)
        txt(s, icon, l=bx + 0.15, t=2.42, w=2.1, h=0.7,
            size=26, color=WHITE, align=PP_ALIGN.CENTER)
        txt(s, title, l=bx + 0.1, t=3.22, w=2.2, h=0.75,
            size=12, bold=True, color=AMBER, align=PP_ALIGN.CENTER)
        txt(s, desc, l=bx + 0.1, t=4.1, w=2.22, h=2.9,
            size=10.5, color=MUTED, wrap=True)
        bx += 2.56

    slide_num(s, 3)


def slide_usecases(prs: Presentation) -> None:
    """Slide 4 — Use cases: who uses MineGuard and how."""
    log.info("Building Slide 4 — Use Cases")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, GREEN_OK)
    section_tag(s, "PRODUCT SPECIFICATION  ›  USE CASES", GREEN_OK)

    txt(s, "Who Uses MineGuard?",
        l=0.45, t=0.48, w=12.0, h=0.85,
        size=36, bold=True, color=WHITE)
    txt(s,
        "MineGuard is designed as a universal tool — from daily operational safety checks "
        "to long-term academic subsidence research.",
        l=0.45, t=1.38, w=12.4, h=0.55,
        size=13, italic=True, color=MUTED)

    cases = [
        (GREEN_OK, "⛏  Mine Site Engineer",
         [("Daily Task", "Open the app, select the mine, and check if any hotspot crossed a risk threshold overnight."),
          ("Value", "Replaces expensive GPS survey teams. Results available within hours of satellite pass."),
          ("Ease", "No training needed beyond basic web browsing. The app instructs the user at every step.")]),
        (BLUE_VIV, "🏗  Geotechnical Consultant",
         [("Task", "Import a client's mine, define the crop area, and run a multi-year displacement analysis."),
          ("Value", "Generates a professional, printable risk report automatically — ready to hand to the client."),
          ("Ease", "All complex InSAR maths is automated; the consultant only interprets the final charts.")]),
        (AMBER, "🎓  Research / Academia",
         [("Task", "Study long-term subsidence trends across multiple mine sites using Sentinel-1 archives."),
          ("Value", "Free satellite data from 2014 onwards provides a decade-long deformation record."),
          ("Ease", "Export-ready CSV displacement values and publication-quality matplotlib charts.")]),
    ]
    cx = 0.45
    for clr, heading, items in cases:
        rect(s, cx, 2.1, 4.06, 5.15, BG_CARD, clr, 1.5)
        txt(s, heading, l=cx + 0.18, t=2.28, w=3.7, h=0.55,
            size=13, bold=True, color=clr)
        rect(s, cx + 0.18, 2.88, 3.7, 0.04, clr)
        bullets_box(s, items,
                    l=cx + 0.18, t=2.98, w=3.72, h=4.1,
                    label_color=clr, body_color=WHITE,
                    size=11, spacing=6)
        cx += 4.3

    slide_num(s, 4)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDES 5-7 — PRODUCT DETAIL: HORIZONTAL DISPLACEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def slide_why_horizontal(prs: Presentation) -> None:
    """Slide 5 — Why East-West horizontal displacement is the critical metric."""
    log.info("Building Slide 5 — Why Horizontal Displacement")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, RED_CRIT)
    section_tag(s, "PRODUCT DETAIL  ›  THE CORE PROBLEM", RED_CRIT)

    txt(s, "Ground Doesn't Just Sink — It Slides.",
        l=0.45, t=0.48, w=12.5, h=0.85,
        size=34, bold=True, color=WHITE)
    txt(s,
        "East–West horizontal displacement is the earliest warning signal of mine-slope "
        "failure — yet it is invisible to conventional vertical sensors.",
        l=0.45, t=1.38, w=12.4, h=0.65,
        size=13.5, italic=True, color=RED_CRIT)

    # Left: the problem
    rect(s, 0.45, 2.2, 5.9, 5.0, BG_CARD, RED_CRIT, 1.8)
    txt(s, "❌  Without East–West Detection",
        l=0.65, t=2.38, w=5.5, h=0.52,
        size=12.5, bold=True, color=RED_CRIT)
    bullets_box(s,
        [("Hidden Hazard",
          "Horizontal sliding begins weeks before the ground visibly sinks — giving a false "
          "sense of stability on vertical-only monitors."),
         ("Wrong Metric",
          "A sensor measuring only depth cannot distinguish whether a mine wall is sliding "
          "laterally outward or simply compressing downward."),
         ("Late Warning",
          "By the time vertical settlement becomes measurable, the lateral failure has already "
          "progressed to a point where intervention is difficult."),
         ("Industry Gap",
          "Most traditional InSAR tools report only vertical or line-of-sight displacement, "
          "omitting the critical East–West component entirely.")],
        l=0.65, t=3.0, w=5.5, h=4.05,
        label_color=RED_CRIT, body_color=MUTED, size=11, spacing=7)

    # Right: the solution
    rect(s, 6.8, 2.2, 6.15, 5.0, BG_CARD, BLUE_VIV, 1.8)
    txt(s, "✅  MineGuard — Horizontal First",
        l=7.0, t=2.38, w=5.7, h=0.52,
        size=12.5, bold=True, color=BLUE_VIV)
    bullets_box(s,
        [("True E–W Measurement",
          "Combines Ascending and Descending satellite passes to mathematically isolate the "
          "pure East–West component of ground movement."),
         ("mm-Level Precision",
          "Sentinel-1 C-band radar resolves displacements as small as 1–3 mm, detecting "
          "lateral shifts months before they become dangerous."),
         ("Early Intervention",
          "Knowing the direction of movement allows geotechnical teams to install targeted "
          "support structures before a critical failure event."),
         ("Proven Science",
          "2D ASC+DSC InSAR decomposition is the standard method used in professional mine "
          "subsidence monitoring worldwide (e.g., Anglo American, BHP site surveys).")],
        l=7.0, t=3.0, w=5.7, h=4.05,
        label_color=BLUE_VIV, body_color=WHITE, size=11, spacing=7)

    slide_num(s, 5)


def slide_3d_space(prs: Presentation) -> None:
    """Slide 6 — 3D vector space: how MineGuard visualises displacement."""
    log.info("Building Slide 6 — 3D Vector Space")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, AMBER)
    section_tag(s, "PRODUCT DETAIL  ›  3D VISUALISATION", AMBER)

    txt(s, "Displacement Mapped into 3D Space",
        l=0.45, t=0.48, w=12.5, h=0.85,
        size=34, bold=True, color=WHITE)
    txt(s,
        "MineGuard plots every hotspot's complete deformation history on three orthogonal "
        "axes — so engineers can see exactly how, where, and when each point is moving.",
        l=0.45, t=1.38, w=12.4, h=0.65,
        size=13, italic=True, color=MUTED)

    # Axis cards
    axes = [
        (BLUE_VIV, "X  —  HORIZONTAL (East ↔ West)",
         "Measures true East–West ground displacement in millimetres per epoch.",
         "Positive (+) means the ground moved Eastward. Negative (−) means Westward sliding.",
         "Example: P2 drifted −283 mm westward by 2021 — the strongest lateral movement on site."),
        (GREEN_OK, "Y  —  VERTICAL (Subsidence)",
         "Measures true vertical ground settlement in millimetres (downward is negative).",
         "Derived from the same ASC+DSC decomposition as horizontal — both axes share one calculation.",
         "Example: P1 settled −159 mm vertically over 4 years — moderate but steady subsidence."),
        (AMBER, "Z  —  TIME  (Year Axis)",
         "The temporal axis converts calendar dates to decimal years (e.g., June 2018 = 2018.42).",
         "Time is shown continuously so acceleration or deceleration of movement is immediately visible.",
         "Example: P5 was stable until 2018 then showed a sudden −210 mm lateral event in one epoch."),
    ]
    ay = 2.2
    for clr, heading, line1, line2, example in axes:
        rect(s, 0.45, ay, 12.43, 1.5, BG_CARD, clr, 1.2)
        rect(s, 0.45, ay, 0.22, 1.5, clr)  # left accent bar
        txt(s, heading, l=0.78, t=ay + 0.1, w=12.0, h=0.45,
            size=12.5, bold=True, color=clr)
        txt(s, f"{line1}  |  {line2}",
            l=0.78, t=ay + 0.55, w=9.5, h=0.38,
            size=11.5, color=WHITE)
        txt(s, f"↳ {example}",
            l=0.78, t=ay + 0.95, w=11.8, h=0.38,
            size=10.5, italic=True, color=MUTED)
        ay += 1.65

    # Insight note
    rect(s, 0.45, 7.05, 12.43, 0.28, BG_CARD)
    txt(s,
        "★  Diverging 3D paths across hotspots confirm spatially heterogeneous deformation — "
        "different parts of the mine are failing by different mechanisms simultaneously.",
        l=0.6, t=7.07, w=12.2, h=0.24,
        size=9.5, italic=True, color=AMBER)

    slide_num(s, 6)


def slide_science(prs: Presentation) -> None:
    """Slide 7 — Dual-orbit 2D decomposition science in plain language."""
    log.info("Building Slide 7 — The Science")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, BLUE_VIV)
    section_tag(s, "PRODUCT DETAIL  ›  HOW WE MEASURE HORIZONTAL DISPLACEMENT")

    txt(s, "Two Satellite Passes. One Precise Answer.",
        l=0.45, t=0.48, w=12.5, h=0.85,
        size=34, bold=True, color=WHITE)
    txt(s,
        "A single satellite pass measures ground movement only along its line-of-sight — "
        "a mixture of horizontal and vertical. Two opposite-direction passes let us "
        "mathematically separate both components.",
        l=0.45, t=1.38, w=12.4, h=0.75,
        size=13, italic=True, color=MUTED)

    # Ascending card
    rect(s, 0.45, 2.3, 4.7, 4.9, BG_CARD, BLUE_VIV, 1.5)
    txt(s, "🛰  Ascending Pass (ASC)",
        l=0.65, t=2.48, w=4.3, h=0.52, size=13, bold=True, color=BLUE_VIV)
    bullets_box(s,
        [("Direction", "Satellite flies Northward along an inclined orbit track."),
         ("Look angle", "Radar beam points East toward ground, ~40° from vertical."),
         ("Measures", "LOS displacement = blend of eastward shift + vertical settlement."),
         ("Coverage", "Four ASC interferometric pairs acquired over 2017–2021.")],
        l=0.65, t=3.08, w=4.3, h=3.9,
        label_color=BLUE_VIV, body_color=WHITE, size=11, spacing=7)

    # Descending card
    rect(s, 5.6, 2.3, 4.7, 4.9, BG_CARD, AMBER, 1.5)
    txt(s, "🛰  Descending Pass (DSC)",
        l=5.8, t=2.48, w=4.3, h=0.52, size=13, bold=True, color=AMBER)
    bullets_box(s,
        [("Direction", "Satellite flies Southward — the opposite track to ASC."),
         ("Look angle", "Radar beam points West toward ground, ~35° from vertical."),
         ("Measures", "LOS displacement from the opposite side — the other equation."),
         ("Coverage", "Four DSC interferometric pairs matched within ≤12 days of ASC.")],
        l=5.8, t=3.08, w=4.3, h=3.9,
        label_color=AMBER, body_color=WHITE, size=11, spacing=7)

    # Result column
    rect(s, 10.7, 2.3, 2.28, 4.9, BG_CARD, GREEN_OK, 1.5)
    txt(s, "✅  Result",
        l=10.85, t=2.52, w=2.0, h=0.45,
        size=13, bold=True, color=GREEN_OK, align=PP_ALIGN.CENTER)
    txt(s,
        "ASC\n\n+\n\nDSC\n\n↓\n\nTrue E/W\n&\nVertical",
        l=10.85, t=3.1, w=2.0, h=3.8,
        size=13.5, bold=True, color=GREEN_OK, align=PP_ALIGN.CENTER)

    txt(s,
        "Formula: d_LOS = −sin(θ)·cos(α)·d_E + cos(θ)·d_U  — solved simultaneously for ASC & DSC using Cramer's Rule.",
        l=0.45, t=7.07, w=12.4, h=0.3,
        size=9, italic=True, color=MUTED)

    slide_num(s, 7)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDE 8 — METHODOLOGY
# ═══════════════════════════════════════════════════════════════════════════════

def slide_methodology(prs: Presentation) -> None:
    """Slide 8 — End-to-end methodology: 5 processing stages."""
    log.info("Building Slide 8 — Methodology")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, AMBER)
    section_tag(s, "WORK DONE  ›  METHODOLOGY", AMBER)

    txt(s, "How MineGuard Processes Satellite Data",
        l=0.45, t=0.48, w=12.5, h=0.78,
        size=32, bold=True, color=WHITE)
    txt(s,
        "Five sequential processing stages transform raw radar images into millimetre-precision "
        "ground displacement measurements and an automated risk report.",
        l=0.45, t=1.3, w=12.4, h=0.55,
        size=12.5, italic=True, color=MUTED)

    stages = [
        (
            BLUE_VIV, "01",
            "Data Acquisition",
            [
                ("Source",
                 "Free Sentinel-1 C-band SAR images retrieved from the ESA Copernicus "
                 "Data Space Ecosystem (CDSE) via the OData REST API."),
                ("Selection",
                 "Both Ascending (ASC) and Descending (DSC) orbit passes are queried "
                 "for the user-defined ROI, timeframe, and IW-SLC product type."),
                ("Pairs",
                 "Images are automatically matched into interferometric pairs within a "
                 "≤12-day temporal baseline to maintain coherence."),
            ],
        ),
        (
            AMBER, "02",
            "InSAR Pre-Processing (SNAP)",
            [
                ("Co-registration",
                 "Master and slave SLC images are precisely aligned at sub-pixel accuracy "
                 "using a cross-correlation-based co-registration graph in ESA SNAP."),
                ("Interferogram",
                 "Phase difference between the two acquisitions is computed; flat-earth "
                 "and topographic phase are removed using a DEM."),
                ("Filtering + Unwrapping",
                 "Goldstein adaptive phase filter reduces noise; Snaphu phase unwrapping "
                 "converts wrapped phase (−π to π) to absolute phase."),
            ],
        ),
        (
            GREEN_OK, "03",
            "LOS Displacement Extraction",
            [
                ("Conversion",
                 "Unwrapped phase is converted to Line-of-Sight (LOS) displacement in mm: "
                 "d_LOS = (λ / 4π) × Δφ, where λ = 5.55 cm for Sentinel-1."),
                ("Geocoding",
                 "The displacement map is terrain-corrected and projected to WGS-84 "
                 "geographic coordinates for spatial analysis."),
                ("Sampling",
                 "LOS displacement values are sampled at each user-selected hotspot "
                 "pixel coordinate for time-series construction."),
            ],
        ),
        (
            RED_CRIT, "04",
            "2D ASC+DSC Decomposition",
            [
                ("System",
                 "One ASC LOS and one matched DSC LOS measurement form a 2×2 linear "
                 "system: d_LOS = −sin(θ)cos(α)·d_E + cos(θ)·d_U."),
                ("Solution",
                 "The system is solved analytically using Cramer's Rule to yield true "
                 "East–West (d_E) and true Vertical (d_U) displacement per epoch."),
                ("Output",
                 "Cumulative E/W and Vertical time-series are computed by summing "
                 "incremental epoch values from the start of the monitoring period."),
            ],
        ),
        (
            LITE_BLU, "05",
            "Risk Classification & Reporting",
            [
                ("Thresholds",
                 "Cumulative displacement is compared against geotechnical severity "
                 "bands: LOW < 30 mm | MEDIUM < 80 mm | HIGH < 150 mm | CRITICAL ≥ 150 mm."),
                ("Report",
                 "An automated natural-language executive summary and colour-coded "
                 "risk table are generated per hotspot without manual intervention."),
                ("Actions",
                 "Engineering recommendations (e.g., install inclinometers, evacuate "
                 "zone) are ranked and output in order of severity."),
            ],
        ),
    ]

    # Layout: 5 equal columns
    col_w = 2.5
    cx = 0.27
    for clr, num, title, items in stages:
        # Column card
        rect(s, cx, 2.02, col_w, 5.25, BG_CARD, clr, 1.2)
        # Stage number badge
        rect(s, cx, 2.02, col_w, 0.48, clr)
        txt(s, f"Stage {num}",
            l=cx + 0.08, t=2.06, w=col_w - 0.16, h=0.38,
            size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        # Stage title
        txt(s, title,
            l=cx + 0.1, t=2.58, w=col_w - 0.2, h=0.62,
            size=11.5, bold=True, color=clr, wrap=True)
        # Bullet items
        bullets_box(s, items,
                    l=cx + 0.1, t=3.28, w=col_w - 0.18, h=3.82,
                    label_color=clr, body_color=WHITE,
                    size=9.5, spacing=5)
        # Arrow to next stage
        if cx + col_w + 0.08 < 13.0:
            txt(s, "▶",
                l=cx + col_w + 0.02, t=4.35, w=0.28, h=0.38,
                size=11, color=MUTED, align=PP_ALIGN.CENTER)
        cx += col_w + 0.16

    slide_num(s, 8)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDE 9 — APP WORKFLOW OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def slide_workflow(prs: Presentation) -> None:
    """Slide 8 — The complete 8-page workflow map."""
    log.info("Building Slide 8 — Workflow")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, GREEN_OK)
    section_tag(s, "WORK DONE  ›  COMPLETE APPLICATION WORKFLOW", GREEN_OK)

    txt(s, "8 Pages. One Seamless Pipeline.",
        l=0.45, t=0.48, w=9.0, h=0.85,
        size=34, bold=True, color=WHITE)
    txt(s,
        "The app guides the engineer through eight sequential pages — from mine selection "
        "to automated risk report — each page building on the output of the one before it.",
        l=0.45, t=1.38, w=12.4, h=0.6,
        size=12.5, italic=True, color=MUTED)

    steps = [
        (BLUE_VIV, "1", "Search Mine",
         "Type mine name → global geocoding → satellite map centres automatically."),
        (BLUE_VIV, "2", "Crop Area",
         "Draw a bounding box on the map to define the exact monitoring zone."),
        (BLUE_VIV, "3", "Timeline",
         "Select start/end year + frequency. App estimates data size & compute time."),
        (BLUE_VIV, "4", "Data Download",
         "App queries ESA Copernicus and downloads Sentinel-1 SLC files automatically."),
        (AMBER,    "5", "Processing",
         "SNAP engine generates interferograms. Live progress dashboard updates every 3s."),
        (AMBER,    "6", "Pick Hotspots",
         "Click up to 10 danger zones on the satellite map. Coordinates sent to engine."),
        (GREEN_OK, "7", "Results",
         "Three scientific plots: E/W drift, LOS displacement, and 3D trajectory."),
        (GREEN_OK, "8", "Risk Report",
         "Automated geotechnical summary with risk ratings and engineering actions."),
    ]

    # Row 1: steps 1-4
    sx = 0.3
    for i in range(4):
        clr, num, name, desc = steps[i]
        rect(s, sx, 2.2, 3.0, 2.5, BG_CARD, clr, 1.5)
        txt(s, num, l=sx + 0.12, t=2.3, w=0.5, h=0.38,
            size=9.5, bold=True, color=clr)
        txt(s, name, l=sx + 0.12, t=2.72, w=2.8, h=0.52,
            size=12.5, bold=True, color=WHITE)
        txt(s, desc, l=sx + 0.12, t=3.32, w=2.8, h=1.25,
            size=10, color=MUTED, wrap=True)
        if i < 3:
            txt(s, "▶", l=sx + 3.05, t=3.25, w=0.35, h=0.38,
                size=11, color=MUTED, align=PP_ALIGN.CENTER)
        sx += 3.3

    # Wrap arrow
    txt(s, "↙  continues", l=11.0, t=4.9, w=2.1, h=0.38,
        size=9, italic=True, color=MUTED)

    # Row 2: steps 5-8 (right to left arrow direction, rendered left-right)
    sx = 0.3
    for i in range(4, 8):
        clr, num, name, desc = steps[i]
        rect(s, sx, 5.15, 3.0, 2.12, BG_CARD, clr, 1.5)
        txt(s, num, l=sx + 0.12, t=5.24, w=0.5, h=0.38,
            size=9.5, bold=True, color=clr)
        txt(s, name, l=sx + 0.12, t=5.64, w=2.8, h=0.48,
            size=12.5, bold=True, color=WHITE)
        txt(s, desc, l=sx + 0.12, t=6.18, w=2.8, h=0.95,
            size=10, color=MUTED, wrap=True)
        if i < 7:
            txt(s, "▶", l=sx + 3.05, t=6.05, w=0.35, h=0.38,
                size=11, color=MUTED, align=PP_ALIGN.CENTER)
        sx += 3.3

    slide_num(s, 9)


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDES 9-12 — WORK DONE: EACH PAGE WITH SCREENSHOT SPACE
# ═══════════════════════════════════════════════════════════════════════════════

def _two_page_slide(prs: Presentation,
                    slide_n: int,
                    bar_color: RGBColor,
                    section: str,
                    heading: str,
                    intro: str,
                    left_page: str,
                    left_title: str,
                    left_bullets: list[tuple[str, str]],
                    right_page: str,
                    right_title: str,
                    right_bullets: list[tuple[str, str]],
                    left_border: RGBColor = BLUE_VIV,
                    right_border: RGBColor = AMBER) -> None:
    """
    Generic builder for a 2-page-per-slide layout.
    Top: large screenshot placeholder for each page.
    Bottom: rich description bullets for each page.
    """
    log.info(f"Building Slide {slide_n} — {heading}")
    s = _blank(prs)
    bg(s, BG_DARK)
    accent_bar(s, bar_color)
    section_tag(s, section, bar_color)

    txt(s, heading,
        l=0.35, t=0.48, w=12.6, h=0.75,
        size=28, bold=True, color=WHITE)
    txt(s, intro,
        l=0.35, t=1.28, w=12.6, h=0.5,
        size=11.5, italic=True, color=MUTED)

    # ── LEFT PAGE ──
    # Screenshot placeholder
    screenshot_box(s, left_page, l=0.35, t=1.88, w=6.2, h=3.18, border=left_border)
    # Page title label
    rect(s, 0.35, 5.1, 6.2, 0.38, left_border)
    txt(s, left_title, l=0.42, t=5.13, w=6.0, h=0.32,
        size=10, bold=True, color=WHITE)
    # Description card
    rect(s, 0.35, 5.52, 6.2, 1.78, BG_CARD, left_border, 0.7)
    bullets_box(s, left_bullets,
                l=0.5, t=5.57, w=6.0, h=1.72,
                label_color=left_border, body_color=WHITE,
                size=10.5, spacing=4)

    # ── RIGHT PAGE ──
    screenshot_box(s, right_page, l=6.82, t=1.88, w=6.18, h=3.18, border=right_border)
    rect(s, 6.82, 5.1, 6.18, 0.38, right_border)
    txt(s, right_title, l=6.9, t=5.13, w=6.0, h=0.32,
        size=10, bold=True, color=WHITE)
    rect(s, 6.82, 5.52, 6.18, 1.78, BG_CARD, right_border, 0.7)
    bullets_box(s, right_bullets,
                l=6.97, t=5.57, w=6.0, h=1.72,
                label_color=right_border, body_color=WHITE,
                size=10.5, spacing=4)

    slide_num(s, slide_n)


def slide_pages_1_2(prs: Presentation) -> None:
    """Slide 9 — Page 1: Search Mine & Page 2: Crop Area."""
    _two_page_slide(
        prs, slide_n=10,
        bar_color=BLUE_VIV,
        section="WORK DONE  ›  PAGE 1 & PAGE 2",
        heading="Step 1: Find Your Mine   |   Step 2: Define the Zone",
        intro=(
            "The first two pages establish where and what to monitor — "
            "transforming a mine name into precise geographical coordinates."
        ),
        left_page="Page 1 — Search Mine",
        left_title="PAGE 1  —  Search Mine  (Entry Point)",
        left_bullets=[
            ("What the user does",
             "Types the name of the mine (e.g., 'Jharia Coal Field') into a search bar."),
            ("What happens",
             "The Nominatim OpenStreetMap API geocodes the name in real-time and returns "
             "GPS coordinates as the user types — no manual lat/lon entry needed."),
            ("Map response",
             "An interactive Leaflet satellite map (Esri World Imagery) instantly recentres "
             "and zooms to the mine location for visual confirmation."),
            ("Design note",
             "A live dropdown shows ranked results so users can distinguish between "
             "similarly named mines in different countries."),
        ],
        right_page="Page 2 — Crop Area (ROI)",
        right_title="PAGE 2  —  Crop / Region of Interest",
        right_bullets=[
            ("What the user does",
             "Clicks four corner points directly on the satellite map to draw a tight "
             "bounding box around the specific mine area to monitor."),
            ("Alternative input",
             "Manual coordinate fields (North/South/East/West) allow precise numerical "
             "entry for users who already know their ROI boundaries."),
            ("Why it matters",
             "The ROI boundary is sent to the backend for all satellite queries — a tight "
             "crop reduces download size by 60–80 % vs. a default wide area."),
            ("Safety",
             "Coordinates are immediately validated and stored in React Context, "
             "persisting across all downstream pages without any re-entry."),
        ],
        left_border=BLUE_VIV,
        right_border=AMBER,
    )


def slide_pages_3_4(prs: Presentation) -> None:
    """Slide 10 — Page 3: Timeline & Page 4: Data Download."""
    _two_page_slide(
        prs, slide_n=11,
        bar_color=AMBER,
        section="WORK DONE  ›  PAGE 3 & PAGE 4",
        heading="Step 3: Set the Timeframe   |   Step 4: Retrieve Satellite Data",
        intro=(
            "These two pages configure the temporal scope of the analysis and "
            "automatically retrieve multi-gigabyte satellite datasets from ESA."
        ),
        left_page="Page 3 — Timeline Selection",
        left_title="PAGE 3  —  Timeline Configuration",
        left_bullets=[
            ("What the user does",
             "Selects a Start Year, End Year, and analysis frequency (e.g., Monthly, "
             "Quarterly) using simple dropdown menus."),
            ("Smart estimator",
             "The app dynamically calculates the total Sentinel-1 data volume "
             "(in GB) and estimated SNAP processing time for the chosen period."),
            ("Value",
             "Engineers can budget bandwidth and compute time before committing — "
             "avoiding accidental 200 GB downloads on a slow connection."),
            ("Output",
             "The selected timeframe is passed to the CDSE OData API query for "
             "building the interferometric pair schedule."),
        ],
        right_page="Page 4 — Data Download",
        right_title="PAGE 4  —  Sentinel-1 Data Download",
        right_bullets=[
            ("What the user does",
             "Clicks 'Start Download'. The app queries the ESA Copernicus Data Space "
             "Ecosystem API and fetches matching Sentinel-1 SLC scenes."),
            ("Background processing",
             "Downloads run asynchronously — the web UI remains fully responsive "
             "while 7 GB files transfer in the background."),
            ("Local Directory Link",
             "Users who already have the SLC files saved locally can click "
             "'Link Local Directory' to bypass downloading entirely — saving hours."),
            ("Integrity check",
             "Each file is verified before the pipeline advances: if any file is "
             "corrupt or missing, the user is warned before processing begins."),
        ],
        left_border=BLUE_VIV,
        right_border=GREEN_OK,
    )


def slide_pages_5_6(prs: Presentation) -> None:
    """Slide 11 — Page 5: Processing & Page 6: Hotspot Selection."""
    _two_page_slide(
        prs, slide_n=12,
        bar_color=GREEN_OK,
        section="WORK DONE  ›  PAGE 5 & PAGE 6",
        heading="Step 5: Process InSAR   |   Step 6: Select Hotspots",
        intro=(
            "The most technically intensive stage — generating interferograms with SNAP — "
            "and then targeting the specific danger zones to monitor."
        ),
        left_page="Page 5 — Processing / SNAP Engine",
        left_title="PAGE 5  —  SNAP InSAR Processing Dashboard",
        left_bullets=[
            ("What happens",
             "The app launches Python workers that run the ESA SNAP graph for each "
             "ASC and DSC interferometric pair (8 pairs total)."),
            ("Live queue",
             "A colour-coded dashboard updates every 3 seconds: Pending (grey), "
             "Processing (amber spinner), Complete (green badge with elapsed time)."),
            ("Smart pre-scan",
             "On restart, the app scans output folders and automatically skips any pair "
             "whose .dim file and .data directory already exist — no redundant compute."),
            ("Worker control",
             "A 'Start Processing' button begins the queue; a 'Stop Worker' button "
             "cancels at any time without corrupting completed outputs."),
        ],
        right_page="Page 6 — Hotspot Selection",
        right_title="PAGE 6  —  Interactive Hotspot Targeting",
        right_bullets=[
            ("What the user does",
             "Clicks directly on the satellite map to place numbered monitoring "
             "markers (P1–P10) over specific high-risk zones such as pit walls."),
            ("Boundary guard",
             "The app prevents markers from being placed outside the ROI defined "
             "in Page 2 — a yellow warning appears if the user clicks outside."),
            ("Precision",
             "Each marker's exact GPS latitude and longitude is captured and "
             "displayed next to its label for field-team cross-reference."),
            ("Handoff",
             "Saved hotspot coordinates are passed directly to the Python analysis "
             "engine for pixel-level time-series extraction from the interferograms."),
        ],
        left_border=AMBER,
        right_border=BLUE_VIV,
    )


def slide_pages_7_8(prs: Presentation) -> None:
    """Slide 12 — Page 7: Results & Page 8: Automated Risk Report."""
    _two_page_slide(
        prs, slide_n=13,
        bar_color=RED_CRIT,
        section="WORK DONE  ›  PAGE 7 & PAGE 8  (RESULTS)",
        heading="Step 7: Analyse Results   |   Step 8: Automated Risk Report",
        intro=(
            "The final two pages transform raw InSAR numbers into three scientific "
            "charts and a complete geotechnical safety verdict."
        ),
        left_page="Page 7 — Results & Charts",
        left_title="PAGE 7  —  Advanced Displacement Analysis",
        left_bullets=[
            ("Chart 1 — E/W Displacement",
             "Cumulative East–West displacement time-series for all hotspots. "
             "Positive = Eastward; Negative = Westward sliding."),
            ("Chart 2 — LOS Displacement",
             "Two-panel chart: grouped bar chart of per-pair raw LOS values, "
             "and a cumulative line chart showing net settlement over time."),
            ("Chart 3 — 3D Trajectory",
             "Dark-background 3D scatter plot: X = E/W, Y = Vertical, Z = Time. "
             "Each hotspot traces its full unique deformation path in space."),
            ("Plain-English Captions",
             "Below every chart, an auto-generated sentence explains the key finding "
             "in non-technical language for site managers."),
        ],
        right_page="Page 8 — Geotechnical Summary Report",
        right_title="PAGE 8  —  Automated Geotechnical Risk Assessment",
        right_bullets=[
            ("Risk Classification",
             "Calculates cumulative displacement per hotspot and assigns: "
             "LOW (<30 mm) / MEDIUM (<80 mm) / HIGH (<150 mm) / CRITICAL (>150 mm)."),
            ("Executive Summary",
             "Auto-generates a site-wide natural-language paragraph describing the "
             "overall deformation pattern and dominant failure direction."),
            ("Hotspot Risk Table",
             "Colour-coded table (green → red) listing each hotspot's peak displacement, "
             "trend direction, and individual risk verdict."),
            ("Engineering Actions",
             "Produces a ranked list of recommended actions (e.g., 'Install inclinometers "
             "at P2') scaled automatically to the detected severity level."),
        ],
        left_border=AMBER,
        right_border=RED_CRIT,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  SLIDE 13 — CONCLUSION
# ═══════════════════════════════════════════════════════════════════════════════

def slide_conclusion(prs: Presentation) -> None:
    """Slide 13 — Conclusion and thank-you."""
    log.info("Building Slide 13 — Conclusion")
    s = _blank(prs)
    bg(s, BG_DARK)
    rect(s, 0, 0, 13.33, 0.12, GREEN_OK)

    txt(s, "MineGuard",
        l=0.6, t=0.35, w=12.0, h=1.1,
        size=54, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # Value pillars
    for i, (word, clr) in enumerate(
        [("Affordable", GREEN_OK), ("Automated", BLUE_VIV), ("Accurate", AMBER)]
    ):
        bx = 0.8 + i * 4.0
        rect(s, bx, 1.65, 3.6, 0.82, BG_CARD, clr, 1.2)
        txt(s, word, l=bx + 0.1, t=1.78, w=3.4, h=0.58,
            size=21, bold=True, color=clr, align=PP_ALIGN.CENTER)

    txt(s, "Any mine. Any continent. No satellite expertise required.",
        l=0.6, t=2.65, w=12.0, h=0.55,
        size=17, italic=True, color=MUTED, align=PP_ALIGN.CENTER)

    rect(s, 2.5, 3.42, 8.33, 0.05, BLUE_VIV)

    # Achievement cards
    achievements = [
        (BLUE_VIV, "🛰  InSAR Pipeline",
         "Fully automated SNAP interferometric processing for ASC & DSC Sentinel-1 pairs."),
        (AMBER, "📐  2D Decomposition",
         "True East–West and Vertical displacement separated by solving a 2×2 linear system."),
        (GREEN_OK, "🌐  8-Page Web App",
         "React TypeScript frontend + Python FastAPI backend; runs entirely in a browser."),
        (RED_CRIT, "📋  Auto Risk Report",
         "Threshold-based geotechnical risk classification with engineering action recommendations."),
    ]
    ay = 3.62
    for clr, title, desc in achievements:
        rect(s, 0.55, ay, 12.23, 0.68, BG_CARD, clr, 0.8)
        rect(s, 0.55, ay, 0.18, 0.68, clr)
        txt(s, title, l=0.88, t=ay + 0.1, w=3.5, h=0.48,
            size=11.5, bold=True, color=clr)
        txt(s, desc, l=4.4, t=ay + 0.12, w=8.3, h=0.44,
            size=11, color=WHITE)
        ay += 0.82

    # Big thank you
    rect(s, 2.0, 6.72, 9.33, 0.6, BLUE_VIV)
    txt(s, "Thank You  —  Questions & Discussion",
        l=2.0, t=6.76, w=9.33, h=0.52,
        size=19, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    txt(s, "Ujjwal Rawat  •  225EC6010  •  ECE Department  •  NIT Rourkela",
        l=0.6, t=7.22, w=12.0, h=0.2,
        size=8, color=MUTED, align=PP_ALIGN.CENTER)

    slide_num(s, 14)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Build and save the MineGuard product-pitch presentation (v3)."""
    output = PROJECT_ROOT / "MineGuard_Presentation.pptx"
    log.info("=== MineGuard Presentation v3 — Starting ===")

    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H

    slide_title(prs)           #  1 — Product Name
    slide_intro(prs)           #  2 — Introduction
    slide_design(prs)          #  3 — Design Philosophy
    slide_usecases(prs)        #  4 — Use Cases
    slide_why_horizontal(prs)  #  5 — Why Horizontal Displacement
    slide_3d_space(prs)        #  6 — 3D Vector Space
    slide_science(prs)         #  7 — The Science
    slide_methodology(prs)     #  8 — Methodology
    slide_workflow(prs)        #  9 — App Workflow
    slide_pages_1_2(prs)       # 10 — Pages 1 & 2
    slide_pages_3_4(prs)       # 11 — Pages 3 & 4
    slide_pages_5_6(prs)       # 12 — Pages 5 & 6
    slide_pages_7_8(prs)       # 13 — Pages 7 & 8
    slide_conclusion(prs)      # 14 — Conclusion

    prs.save(str(output))
    log.info(f"Saved → {output}")
    print(f"✅  Presentation saved → {output}")


if __name__ == "__main__":
    main()
