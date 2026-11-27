"""ArqauQuat web platform: fall 2026 report material for the team (PDF)."""

import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether, NextPageTemplate, CondPageBreak)

OUT = sys.argv[1]
F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", F + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Oblique", F + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "DejaVuSansMono.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Oblique", boldItalic="Sans-Bold")

ACCENT = colors.HexColor("#FF3F10")
ACCENT_DARK = colors.HexColor("#D2370C")
INK = colors.HexColor("#222222")
MUTED = colors.HexColor("#6B6560")
PAPER = colors.HexColor("#F7F4F1")
LINE = colors.HexColor("#E4DED8")
TINT = colors.HexColor("#FFE9E2")
OK = colors.HexColor("#1F8A4C")

W, H = A4
M = 20 * mm
CW = W - 2 * M

ss = {}
ss["body"] = ParagraphStyle("body", fontName="Sans", fontSize=9.6, leading=14.2, textColor=INK, spaceAfter=6)
ss["small"] = ParagraphStyle("small", parent=ss["body"], fontSize=8.2, leading=11.4, textColor=MUTED, spaceAfter=4)
ss["cell"] = ParagraphStyle("cell", parent=ss["body"], fontSize=8.3, leading=11.2, spaceAfter=0)
ss["cellb"] = ParagraphStyle("cellb", parent=ss["cell"], fontName="Sans-Bold")
ss["head"] = ParagraphStyle("head", parent=ss["cell"], fontName="Sans-Bold", textColor=colors.white)
ss["h1"] = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=21, textColor=INK, spaceBefore=4, spaceAfter=8)
ss["h2"] = ParagraphStyle("h2", fontName="Sans-Bold", fontSize=11.5, leading=15, textColor=INK, spaceBefore=10, spaceAfter=4)
ss["label"] = ParagraphStyle("label", fontName="Sans-Bold", fontSize=7.6, leading=10, textColor=ACCENT, spaceAfter=2)
ss["bullet"] = ParagraphStyle("bullet", parent=ss["body"], leftIndent=12, bulletIndent=2, spaceAfter=3)
ss["caption"] = ParagraphStyle("caption", parent=ss["small"], fontName="Sans-Oblique", spaceBefore=3, spaceAfter=10)
ss["note"] = ParagraphStyle("note", parent=ss["body"], fontSize=9, leading=13, backColor=PAPER, borderPadding=(7, 9, 7, 9),
                            borderColor=LINE, borderWidth=0.6, spaceBefore=6, spaceAfter=12)
ss["code"] = ParagraphStyle("code", fontName="Mono", fontSize=7.8, leading=10.5, textColor=INK, backColor=PAPER,
                            borderPadding=(5, 7, 5, 7), spaceBefore=3, spaceAfter=9)

story = []
P = lambda t, s="body": story.append(Paragraph(t, ss[s]))
SP = lambda h=6: story.append(Spacer(1, h))


def H1(num, title):
    story.append(CondPageBreak(60 * mm))
    story.append(Paragraph(f"SECTION {num}", ss["label"]))
    story.append(Paragraph(title, ss["h1"]))


def H2(t):
    story.append(CondPageBreak(30 * mm))
    story.append(Paragraph(t, ss["h2"]))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, ss["bullet"], bulletText="•"))
    SP(3)


def table(rows, widths, head=True, zebra=True, bold_first=False):
    data = []
    for i, r in enumerate(rows):
        st = ss["head"] if (head and i == 0) else ss["cell"]
        data.append([Paragraph(str(c), ss["cellb"] if (bold_first and j == 0 and not (head and i == 0)) else st)
                     for j, c in enumerate(r)])
    t = Table(data, colWidths=[w * CW for w in widths], repeatRows=1 if head else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if head:
        style += [("BACKGROUND", (0, 0), (-1, 0), INK)]
    if zebra:
        for i in range(1 if head else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), PAPER))
    t.setStyle(TableStyle(style))
    story.append(t)
    SP(10)


def note(t):
    story.append(Paragraph(t, ss["note"]))


# --- drawing helpers -------------------------------------------------------------------------------

def box(d, x, y, w, h, title, sub=None, fill=colors.white, stroke=INK, tcolor=INK, size=8.2):
    d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
    if sub:
        d.add(String(x + w / 2, y + h / 2 + 2.5, title, fontName="Sans-Bold", fontSize=size, fillColor=tcolor,
                     textAnchor="middle"))
        d.add(String(x + w / 2, y + h / 2 - 8, sub, fontName="Sans", fontSize=size - 1.6, fillColor=MUTED if tcolor == INK else tcolor,
                     textAnchor="middle"))
    else:
        d.add(String(x + w / 2, y + h / 2 - 3, title, fontName="Sans-Bold", fontSize=size, fillColor=tcolor, textAnchor="middle"))


def arrow(d, x1, y1, x2, y2, label=None, color=INK, lx=0, ly=4, dash=None, both=False):
    ln = Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=0.9)
    if dash:
        ln.strokeDashArray = dash
    d.add(ln)
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    s = 5
    for (px, py, ang) in ([(x2, y2, a)] + ([(x1, y1, a + math.pi)] if both else [])):
        d.add(Polygon([px, py, px - s * math.cos(ang - 0.4), py - s * math.sin(ang - 0.4),
                       px - s * math.cos(ang + 0.4), py - s * math.sin(ang + 0.4)], fillColor=color, strokeColor=color))
    if label:
        d.add(String((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, fontName="Sans", fontSize=6.8, fillColor=MUTED,
                     textAnchor="middle"))


def fig_context():
    w, h = CW, 270
    d = Drawing(w, h)
    # outside
    box(d, 0, 190, 110, 44, "People", "browser, HTTPS")
    box(d, 0, 40, 110, 44, "Plants", "site kit, outbound 443")
    # gateway
    d.add(Rect(150, 30, 92, 214, rx=6, ry=6, fillColor=TINT, strokeColor=ACCENT, strokeWidth=1))
    d.add(String(196, 226, "Gateway", fontName="Sans-Bold", fontSize=9, fillColor=ACCENT_DARK, textAnchor="middle"))
    d.add(String(196, 215, "nginx, only 80/443", fontName="Sans", fontSize=6.8, fillColor=ACCENT_DARK, textAnchor="middle"))
    box(d, 158, 178, 76, 30, "web host", "server TLS", fill=colors.white, stroke=ACCENT, size=7.6)
    box(d, 158, 48, 76, 40, "sites host", "client certificate", fill=colors.white, stroke=ACCENT, size=7.6)
    d.add(String(196, 96, "+ CRL check", fontName="Sans", fontSize=6.6, fillColor=ACCENT_DARK, textAnchor="middle"))
    arrow(d, 110, 212, 158, 196, "HTTPS")
    arrow(d, 110, 62, 158, 66, "mTLS")
    # private network
    px = 262
    d.add(Rect(px, 10, w - px, 250, rx=6, ry=6, fillColor=PAPER, strokeColor=LINE, strokeWidth=0.8))
    d.add(String(px + 8, 248, "Private network (nothing published)", fontName="Sans-Bold", fontSize=7.6, fillColor=MUTED))
    bw = 92
    c1, c2 = px + 12, w - 12 - bw
    box(d, c1, 186, bw, 40, "Web app", "Next.js 15: pages")
    box(d, c1, 106, bw, 48, "API", "FastAPI: users + site API")
    box(d, c1, 22, bw, 40, "SuperLink", "Flower, TLS + node auth")
    box(d, c2, 186, bw, 40, "Central inference", "newest promoted model")
    box(d, c2, 110, bw, 40, "PostgreSQL", "17 tables")
    box(d, c2, 22, bw, 40, "Site CA", "plant certificates, CRL")
    arrow(d, 234, 196, c1, 206, "pages", ly=4)
    arrow(d, 234, 186, c1, 144, "/api", lx=-4, ly=-2)
    arrow(d, 234, 78, c1, 116, "/site-api", lx=-10, ly=4)
    arrow(d, 234, 56, c1, 42, "Fleet gRPC", lx=-8, ly=-10, dash=[2, 2])
    arrow(d, c1 + bw / 2, 106, c1 + bw / 2, 62, "Control API", lx=24, ly=0)
    arrow(d, c1 + bw, 140, c2, 196)
    arrow(d, c1 + bw, 130, c2, 130)
    arrow(d, c1 + bw, 118, c2, 52)
    return d


def fig_lifecycle():
    w, h = CW, 150
    d = Drawing(w, h)
    y = 85
    bw, bh = 82, 34
    xs = [0, 122, 252, 388]
    box(d, xs[0], y, bw, bh, "Registered", "operator, website")
    box(d, xs[1], y, bw, bh, "Approved", "admin; kit download")
    box(d, xs[2], y, bw + 14, bh, "Active", "enrolled; online/offline", fill=TINT, stroke=ACCENT)
    box(d, xs[3], y, bw, bh, "Suspended", "paused by admin")
    box(d, xs[0], 15, bw, bh, "Rejected", "with a reason")
    box(d, xs[3], 15, bw, bh, "Revoked", "final; cert in CRL")
    arrow(d, xs[0] + bw, y + bh / 2, xs[1], y + bh / 2, "approve")
    arrow(d, xs[1] + bw, y + bh / 2, xs[2], y + bh / 2, "enroll")
    arrow(d, xs[2] + bw + 14, y + bh / 2 + 6, xs[3], y + bh / 2 + 6, "suspend")
    arrow(d, xs[3], y + bh / 2 - 6, xs[2] + bw + 14, y + bh / 2 - 6, "resume", ly=-11)
    arrow(d, xs[0] + bw / 2, y, xs[0] + bw / 2, 15 + bh, "reject", lx=16, ly=-2)
    arrow(d, xs[2] + 50, y, xs[3] + 10, 15 + bh, "revoke", lx=-6, ly=-6)
    arrow(d, xs[2] + 30, y + bh, xs[1] + 50, y + bh, None, dash=[2, 2])
    d.add(Polygon([xs[1] + 50, y + bh, xs[1] + 50, y + bh + 18, xs[2] + 30, y + bh + 18, xs[2] + 30, y + bh],
                  fillColor=None, strokeColor=MUTED, strokeWidth=0.7, strokeDashArray=[2, 2]))
    d.add(String((xs[1] + xs[2] + 80) / 2, y + bh + 22, "re-issue kit (old credentials revoked)", fontName="Sans",
                 fontSize=6.8, fillColor=MUTED, textAnchor="middle"))
    return d


def fig_kit():
    w, h = CW, 190
    d = Drawing(w, h)
    d.add(Rect(0, 8, 300, 172, rx=6, ry=6, fillColor=PAPER, strokeColor=LINE))
    d.add(String(10, 167, "Plant server (Docker): docker compose up -d", fontName="Sans-Bold", fontSize=7.6, fillColor=MUTED))
    box(d, 12, 90, 110, 46, "agent", "enroll, heartbeat, store")
    box(d, 12, 20, 110, 46, "status page", "localhost:8080, read-only")
    box(d, 178, 90, 108, 46, "tunnel", "nginx, plant certificate", fill=TINT, stroke=ACCENT)
    box(d, 178, 20, 108, 46, "SuperNode", "Flower client, trains")
    arrow(d, 67, 90, 67, 66)
    arrow(d, 232, 66, 232, 90, "TLS", lx=10, ly=-2)
    arrow(d, 122, 100, 178, 52, "reads data/store", lx=30, ly=6)
    gx, gy, gw, gh = 360, 84, 120, 50
    box(d, gx, gy, gw, gh, "ArqauQuat gateway", "sites host :443", fill=TINT, stroke=ACCENT)
    arrow(d, 286, 113, gx, 109, "mTLS (Fleet gRPC)", ly=5)
    # agent -> gateway over the top, not through the tunnel
    for (x1, y1, x2, y2) in ((67, 136, 67, 150), (67, 150, gx + gw / 2, 150)):
        ln = Line(x1, y1, x2, y2, strokeColor=INK, strokeWidth=0.9)
        ln.strokeDashArray = [2, 2]
        d.add(ln)
    arrow(d, gx + gw / 2, 150, gx + gw / 2, gy + gh, None, dash=[2, 2])
    d.add(String(150, 154, "HTTPS site API: enroll, heartbeat, quality, forecast window", fontName="Sans", fontSize=6.8,
                 fillColor=MUTED))
    for i, t in enumerate(("Only status, counts, model updates", "and (with consent) one recent", "window leave the plant.")):
        d.add(String(gx + gw / 2, 66 - i * 9, t, fontName="Sans", fontSize=6.8, fillColor=MUTED, textAnchor="middle"))
    return d


def fig_forecast():
    w, h = CW, 120
    d = Drawing(w, h)
    steps = [("1  Choose", "energy, site, horizon"), ("2  GET /api/forecast", "validate (FR-26)"),
             ("3  Access check", "own plant / public"), ("4  Newest model", "promoted, per horizon"),
             ("5  Central inference", "shared window → values"), ("6  Power", "capacity, curve / PV"),
             ("7  Chart + model card", "forecast vs actual")]
    bw, gap = 86, 11
    for i, (t, s) in enumerate(steps):
        row, col = divmod(i, 4)
        x = col * (bw + gap + 22) if row == 0 else (col * (bw + gap + 22) + 54)
        y = 66 if row == 0 else 6
        box(d, x, y, bw + 12, 40, t, s, fill=TINT if i in (0, 6) else colors.white,
            stroke=ACCENT if i in (0, 6) else INK, size=7.4)
        if i < len(steps) - 1 and i != 3:
            nx = x + bw + 12
            arrow(d, nx, y + 20, x + bw + gap + 22, y + 20)
    arrow(d, 3 * (bw + gap + 22) + 49, 66, 54 + 49, 46, None, dash=[2, 2])
    return d


def figure(drawing, caption):
    story.append(KeepTogether([drawing, Paragraph(caption, ss["caption"])]))


# --- pages -----------------------------------------------------------------------------------------

def on_page(c, doc):
    c.saveState()
    c.setFont("Sans", 7.4)
    c.setFillColor(MUTED)
    c.drawString(M, 12 * mm, "ArqauQuat web platform · Fall 2026 report material")
    c.drawRightString(W - M, 12 * mm, str(doc.page))
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.4)
    c.line(M, H - 13 * mm, M + 18 * mm, H - 13 * mm)
    c.restoreState()


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(ACCENT)
    c.rect(0, H * 0.42, W, H * 0.58, stroke=0, fill=1)
    # mark: sun + turbine
    cx, cy = M + 14 * mm, H - 40 * mm
    c.setFillColor(colors.white)
    c.circle(cx + 9 * mm, cy + 6 * mm, 4.2 * mm, stroke=0, fill=1)
    c.setStrokeColor(colors.white)
    c.setLineWidth(2.2)
    c.line(cx, cy - 16 * mm, cx, cy)
    import math
    for k in range(3):
        a = math.radians(90 + k * 120)
        c.line(cx, cy, cx + 9 * mm * math.cos(a), cy + 9 * mm * math.sin(a))
    c.setFont("Sans-Bold", 30)
    c.drawString(M, H * 0.42 + 70 * mm, "ArqauQuat")
    c.setFont("Sans-Bold", 19)
    c.drawString(M, H * 0.42 + 56 * mm, "The web platform")
    c.setFont("Sans", 11.5)
    c.drawString(M, H * 0.42 + 44 * mm, "Material for the final report of the fall semester 2026")
    c.setFont("Sans", 9)
    c.drawString(M, H * 0.42 + 14 * mm, "Federated wind and solar forecasting for Kazakhstan · CSCI 408")
    c.setFillColor(INK)
    c.setFont("Sans-Bold", 10)
    c.drawString(M, H * 0.42 - 16 * mm, "What this document covers")
    c.setFont("Sans", 9.2)
    lines = [
        "The website and everything behind it: pages, user roles, plant registration and site kits,",
        "security, the API, the database, notifications, deployment and testing.",
        "",
        "The forecasting models (wind and solar architecture, training, results) are described in a",
        "separate document. Here they appear only where the website uses them.",
        "",
        "Every section is written so it can be copied into the report with light editing. Section 13",
        "lists the requirements the website covers; Section 17 lists the figures and screenshots to add.",
    ]
    y = H * 0.42 - 25 * mm
    for ln in lines:
        c.drawString(M, y, ln)
        y -= 13
    c.setFont("Sans", 8)
    c.setFillColor(MUTED)
    c.drawString(M, 20 * mm, "Status: November 2026, after the demo. Code names in the repository still say “fedwind”.")
    c.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=20 * mm, bottomMargin=20 * mm,
                      title="ArqauQuat web platform: fall 2026 report material", author="ArqauQuat team",
                      subject="Web application, API and site network")
frame = Frame(M, 20 * mm, CW, H - 40 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate("cover", [frame], onPage=on_cover), PageTemplate("main", [frame], onPage=on_page)])

story.append(NextPageTemplate("main"))
story.append(PageBreak())

# Contents
story.append(Paragraph("Contents", ss["h1"]))
toc = [("1", "Summary"), ("2", "The website's role in the system"), ("3", "Technology"), ("4", "Users, roles and accounts"),
       ("5", "Pages"), ("6", "Plants: from registration to training"), ("7", "Security"), ("8", "Forecasts on the website"),
       ("9", "Training from the website"), ("10", "Telegram alerts"), ("11", "API and data model"),
       ("12", "Deployment"), ("13", "Requirements covered"), ("14", "Testing"), ("15", "Design decisions"),
       ("16", "Limitations and spring work"), ("17", "Checklist for the report writers")]
table([[n, t] for n, t in toc], [0.08, 0.92], head=False, zebra=False)

# 1
H1(1, "Summary")
P("ArqauQuat is the web platform of our federated forecasting system. Wind and solar plant operators register their "
  "plants on the website, an administrator approves them, and each plant installs a small <b>site kit</b> that "
  "connects it to the federation without ever sending its measurement history. The website shows power forecasts "
  "made by the newest global model, lets researchers start and follow federated training runs, and gives "
  "administrators one place to approve plants, manage users and read the audit log.")
P("The fall work delivered the complete platform around the forecasting models:")
bullets([
    "a public website with a live map of the federation and a three-step forecast view (energy type, site, horizon);",
    "accounts with three roles (administrator, operator, viewer), sessions, CSRF protection and an audit log;",
    "the plant lifecycle: registration, approval, a personal site kit with a one-time token, enrollment with "
    "plant-generated keys and a certificate from our own site CA, live connection status, suspension, re-issue, revocation;",
    "a security design in layers: one public gateway, client certificates and a revocation list for plants, Flower "
    "node authentication, and no internal service reachable from outside;",
    "training control from the browser: start and stop runs, a live training dashboard, eligibility rules for plants, "
    "weekly scheduled runs and screening of suspicious model updates;",
    "a model registry: every finished run becomes a version; scheduled runs are promoted automatically when "
    "quality gates pass, with a 24-hour admin veto and one-click rollback;",
    "forecasts stored every hour for every plant, also for plants that keep their data and forecast locally, "
    "each with a short text summary (FR-25);",
    "operators pause training, change consents or leave the federation themselves;",
    "operations: certificate renewal, rate limits, backups and restore, a health page, kit update notices;",
    "Telegram alerts for operators and administrators;",
    "two deployments: the lab stack for experiments and the central-server stack for real plants, plus scripts "
    "for a 20-plant scale test and automated security checks;",
    "167 automated tests across the API, the site agent, inference and the ML core.",
])
table([["Item", "Count"],
       ["Website pages (routes)", "22 (plus 1 redirect)"],
       ["API endpoints (current platform)", "about 30 user endpoints, 4 site-agent endpoints"],
       ["Database tables", "19, created by 7 SQL migrations"],
       ["Automated tests", "167: API 93, ML core 39, inference 17, site agent 18"],
       ["Containers in the lab stack", "about 25 (web, API, database, SuperLink, 10 clients, inference)"]],
      [0.55, 0.45], bold_first=True)

# 2
H1(2, "The website's role in the system")
P("The federated system has three kinds of participants: <b>people</b> who use the website, <b>plants</b> that keep "
  "their data and train locally, and the <b>central server</b> that hosts the website, aggregates model updates and "
  "serves forecasts. The website is the front door of the central server. Figure 1 shows the central server as it "
  "is deployed for real plants.")
figure(fig_context(), "Figure 1. Central server. Only the gateway is reachable from the internet. People use the web "
       "host with normal HTTPS; plants use the sites host, which requires a client certificate signed by our site CA.")
P("Three principles shaped the design:")
bullets([
    "<b>Data stays at the plant.</b> During training only model updates leave a plant. For forecasts a plant may "
    "consent to share a short recent window (14 days) of one variable; the history never leaves.",
    "<b>One door.</b> Everything from outside goes through one gateway on port 443. The database, the Flower "
    "SuperLink, inference and the certificate authority are on a private network.",
    "<b>The platform is real; only the plant is simulated in the demo.</b> A simulated plant runs the same site kit "
    "as a real one; it just reads NASA POWER weather instead of SCADA exports. Nothing in the platform has a demo-only path.",
])

# 3
H1(3, "Technology")
table([["Layer", "Choice", "Why"],
       ["Web app", "Next.js 15, React 19, TypeScript, Tailwind CSS 4, Radix UI, Recharts",
        "Server and client rendering in one project; typed API client; accessible components; charts for forecasts and training curves."],
       ["API", "FastAPI (Python 3.12), Pydantic", "Same language as the ML code; request validation and OpenAPI docs for free."],
       ["Database", "PostgreSQL 16, plain SQL migrations (psycopg 3)", "Users, plants, credentials, heartbeats and the audit log need transactions and constraints."],
       ["Passwords", "argon2id", "Current recommended password hash."],
       ["Federation control", "Flower 1.25 CLI (flwr run / stop / ls, supernode register)", "The supported way to drive a SuperLink."],
       ["Certificates", "Python cryptography (site CA), nginx (gateway)", "A small CA we control; nginx verifies client certificates and the revocation list."],
       ["Alerts", "Telegram Bot API", "Operators already use Telegram; no app to install."],
       ["Deployment", "Docker Compose", "One command starts the whole system (NFR-08)."],
       ["Site agent", "Python, requests, cryptography (image of about 200 MB)", "Small enough for any plant server; no GPU needed for the agent."]],
      [0.15, 0.38, 0.47], bold_first=True)

# 4
H1(4, "Users, roles and accounts")
table([["Role", "Who", "Can do"],
       ["Visitor", "anyone", "Home, map, public forecasts (lab sites and plants that agreed to public forecasts), information pages, register."],
       ["Viewer", "registered user", "Everything a visitor can, logged in."],
       ["Operator", "staff of a plant's organization", "Register plants, edit them while waiting for approval, download the site kit, see their plants' status, data quality and private forecasts, Telegram alerts."],
       ["Administrator", "ArqauQuat team", "Approve, reject, suspend, resume, revoke plants; re-issue kits; manage users and roles; start, stop and promote training runs; read the audit log."]],
      [0.16, 0.24, 0.60], bold_first=True)
P("Accounts are stored in PostgreSQL. Passwords are hashed with argon2id. A login creates a session (a random token "
  "kept in an httpOnly, SameSite cookie, stored only as a hash, valid 12 hours) and a CSRF token that every "
  "state-changing request must send back. Failed logins are throttled per e-mail address. Registration creates an "
  "operator account together with its organization; administrators are created on the server with a command-line "
  "tool, never through the website.")
P("Every important action is written to an append-only <b>audit log</b>: logins, registrations, plant decisions, kit "
  "downloads, enrollments, revocations, run starts and stops, model promotions. Administrators can filter it by "
  "action and actor on the Audit page.")

# 5
H1(5, "Pages")
P("The website has a public part and an application part. Table 5.1 lists every page; the main ones are described below.")
table([["Page", "Path", "Who", "Purpose"],
       ["Home", "/", "everyone", "What the platform does, live federation map, call to action."],
       ["Forecast", "/forecast", "everyone*", "Energy type → site → horizon; forecast and actual on one chart, power, model card."],
       ["Training", "/training", "everyone", "List of training runs with status and results."],
       ["Run detail", "/training/[runId]", "everyone", "Live dashboard of one run; admins stop or promote it."],
       ["Experiments", "/experiments", "admin", "Configure and start a federated run."],
       ["Your plants", "/sites", "operator, admin", "Table of plants with status and last heartbeat."],
       ["Register a plant", "/sites/new", "operator", "Form: location, capacity, equipment, consents."],
       ["Plant page", "/sites/[siteId]", "owner, admin", "Progress, connection, data quality, kit download, history."],
       ["Admin overview", "/admin", "admin", "Counters, items needing attention, recent activity."],
       ["Approvals", "/admin/approvals", "admin", "Queue of plants waiting for a decision."],
       ["All sites", "/admin/sites", "admin", "Lab sites and plants; suspend, resume, revoke, re-issue."],
       ["Users", "/admin/users", "admin", "Roles, activate or deactivate accounts."],
       ["Audit log", "/admin/audit", "admin", "Filterable history of every important action."],
       ["Models", "/admin/models", "admin", "Model versions with gate reports; promote, veto, roll back."],
       ["Health", "/admin/health", "admin", "Services, certificate expiry, newest forecasts, backups."],
       ["Log in / Register", "/login, /register", "everyone", "Accounts; registration creates an operator and organization."],
       ["Information", "/about, /architecture, /data-source, /instructions, /solar", "everyone", "Project, system overview, data sources, user guide, solar notes."]],
      [0.15, 0.22, 0.14, 0.49], bold_first=True)
P("* Plant forecasts are private unless the plant agreed to public forecasts; lab-site forecasts are public.", "small")

H2("Home")
P("A bold landing page in the ArqauQuat style (orange, ink, warm paper; Geist and Instrument Serif fonts). Its centre "
  "is the <b>federation map</b>: an outline of Kazakhstan drawn from Natural Earth data with every site that may be "
  "shown. Lab sites and public plants are visible to everyone; administrators also see private plants and their live "
  "connection state. The animated logo (a turning wind turbine in front of the sun) appears in the navigation.")

H2("Forecast")
P("The forecast takes three choices (NFR-10): <b>energy type</b>, <b>site</b>, <b>horizon</b> (1 h, 72 h or 432 h). The "
  "chart shows the recent actual values and the forecast on one time axis (FR-23), in physical units (m/s or W/m²) "
  "and as power in kW or MW with the capacity factor. A <b>model card</b> under the chart names the promoted global "
  "model that produced the forecast: training run, strategy, sites and rounds, skill against persistence, and a "
  "label when the run used only part of the data. Operators see their own plants; plants that have not consented "
  "to central forecasting get a clear explanation instead of a chart.")

H2("Training and run detail")
P("The training list shows every run with its energy type, horizon, status and final skill. The run page is the "
  "<b>training dashboard</b> (FR-24): current round of the total, validation error per round (normalised and in "
  "physical units), and for each round which sites replied, which dropped out and which updates were rejected by "
  "the update checks, with the reason. It refreshes while the run is active. Administrators can stop a run and "
  "promote a finished run's best checkpoint; the page then shows the run as <i>currently serving</i>.")

H2("Experiments")
P("Administrators configure a run in the browser: energy type, sites (or every site that can train), strategy "
  "(FedAvg, FedProx and others), rounds, local epochs, horizon, model settings and the share of data to use for "
  "quick runs. For wind, a researcher can upload one CSV per site instead of the built-in data; the API validates "
  "every file before the run starts. One run runs at a time; a second start is refused with a clear message.")

H2("Plants and the plant page")
P("Operators register a plant with its name, energy type, coordinates (checked to be inside Kazakhstan), capacity, "
  "equipment (turbine model and hub height, or PV module, tilt and azimuth), contact and three consents: train with "
  "the federation (required), share a recent window for central forecasts, and show forecasts publicly. The plant "
  "page then follows it from registration to training: a progress stepper (registered, approved, kit installed, "
  "online), the live connection (last heartbeat, agent version, last data hour), seven days of data-quality counts, "
  "the kit download while it is available, why the plant can or cannot join training yet, and its full history.")

H2("Administration")
P("The overview counts waiting plants, active sites, plants online now and users, shows the active run, and lists "
  "what needs attention (plants waiting for approval, plants gone offline, failed runs). Approvals is a queue with "
  "approve and reject (a reason is required and shown to the operator). The sites page holds the other decisions: "
  "suspend, resume, revoke, re-issue kit. Users and the audit log complete the area.")

# 6
H1(6, "Plants: from registration to training")
figure(fig_lifecycle(), "Figure 2. Plant lifecycle. Every transition is made on the website (or by the site agent "
       "for enrollment), needs the right role, and is written to the audit log with its reason.")
H2("The site kit")
P("When a plant is approved, its operator downloads a zip with personal instructions, a Docker Compose file, settings "
  "without secrets, the public certificate of our site CA and a <b>one-time enrollment token</b> (valid 72 hours, "
  "stored on the server only as a hash). Running <font name='Mono'>docker compose up -d</font> on a plant server starts the kit:")
figure(fig_kit(), "Figure 3. Site kit at a plant. The tunnel exists because Flower's SuperNode cannot present a client "
       "certificate itself; it holds the plant certificate and connects to the gateway on the SuperNode's behalf.")
bullets([
    "<b>Enrollment (first start).</b> The agent creates two private keys on the plant server: one for its TLS "
    "certificate and one for its Flower node. It sends only a certificate signing request and the Flower public key "
    "together with the token. The API checks the token, signs a 90-day client certificate whose name is the site id, "
    "registers the Flower key with the SuperLink, and marks the token used. A token works once; any failure leaves it "
    "usable so the plant can retry.",
    "<b>Heartbeat.</b> Every minute or so the agent reports its status, last data hour and counts of rows and gaps. "
    "The answer tells it whether the plant is active or suspended. Three missed heartbeats show the plant as offline.",
    "<b>Data quality.</b> Once a day: rows, gaps, implausible values and curtailed hours for the last seven days. Counts only.",
    "<b>Training store.</b> The agent keeps the plant's hourly data in the format the Flower client reads, on the plant. "
    "It reports only the store's size.",
    "<b>Forecast window (with consent).</b> The last 14 days of the forecast variable, hourly, for central forecasting.",
    "<b>Status page.</b> A read-only page on the plant server (localhost:8080) shows what the agent knows.",
])
H2("Who may train")
P("A plant joins a training run only when it is active, has consented to training, has a registered Flower node, has "
  "sent a heartbeat in the last 10 minutes, runs agent 0.2 or newer and has at least 90 days of data in its training "
  "store. The website shows the reason when one of these is missing, for example “1 820 of 2 160 hours of training data”.")

# 7
H1(7, "Security")
P("Security follows the principle of defence in depth: each layer assumes the one in front of it may fail.")
table([["Layer", "Mechanism", "Stops"],
       ["Network", "Only the gateway publishes ports (80 for certificates, 443). SuperLink, database, API and inference are private.", "Port scans; direct access to internal services."],
       ["Gateway (mTLS)", "The sites host requires a client certificate from the ArqauQuat site CA, checked against the revocation list; only /site-api/ and the Flower Fleet API are routed.", "Anyone without an enrolled plant certificate."],
       ["Flower node auth", "The SuperLink accepts only SuperNodes whose public key was registered at enrollment.", "A stolen certificate alone; unregistered nodes."],
       ["Site identity", "The gateway forwards the certificate's name and serial with a shared secret; the API accepts them only if they match the plant's live certificate.", "One plant acting as another; forged headers."],
       ["Authorization", "Sessions, CSRF tokens and roles; operators see only their organization's plants.", "Users acting beyond their role."],
       ["Model safety", "Updates with NaN values, wrong shapes or a size far above the round's median are left out.", "Broken or poisoned updates."],
       ["Audit", "Append-only log of every important action.", "Silent misuse."]],
      [0.16, 0.52, 0.32], bold_first=True)
H2("Credentials")
table([["Credential", "Made where", "Lifetime", "Revoked by"],
       ["User password", "user", "until changed", "deactivating the account"],
       ["Enrollment token", "API, at kit download", "72 h, one use", "use, a newer kit, or expiry"],
       ["Plant certificate", "key at the plant; signed by the site CA", "90 days", "revocation list (gateway reloads within 30 s)"],
       ["Flower node key", "plant", "until the kit is re-issued", "unregistered on the SuperLink"],
       ["Site CA key", "central server, own volume", "5 years", "rotate the CA (re-enroll plants)"]],
      [0.2, 0.3, 0.2, 0.3], bold_first=True)
P("Private keys of a plant never leave it. Revoking a plant or re-issuing its kit puts its certificate on the "
  "revocation list and unregisters its Flower node at once; if the SuperLink is unreachable, the platform retries "
  "every hour until it succeeds. A deleted plant's certificate stays on the list until it expires.")
H2("What leaves a plant")
table([["Data", "When", "Who sees it"],
       ["Status and counts (rows, gaps, store size)", "every heartbeat, daily", "the plant's operators, administrators"],
       ["Model updates (trainable weights, sample count, loss)", "during training runs", "the SuperLink only"],
       ["Recent window of one variable (14 days)", "hourly, only with consent", "central inference; kept 30 days"],
       ["Measurement history, raw SCADA data, keys", "never", "nobody"]],
      [0.42, 0.26, 0.32], bold_first=True)

# 8
H1(8, "Forecasts on the website")
figure(fig_forecast(), "Figure 4. What happens when a user asks for a forecast.")
P("The REST endpoint <font name='Mono'>GET /api/forecast?energy_type=&amp;site=&amp;horizon=</font> returns the "
  "forecast as JSON (FR-22). It refuses unknown sites, horizons other than 1, 72 and 432 hours, and unknown energy "
  "types with a clear message (FR-26); a private plant answers like an unknown site so it does not reveal itself. "
  "The forecast always comes from the newest <b>promoted</b> global model for that energy type and horizon; an "
  "administrator promotes a finished run from its page, and the next request uses it.")
P("For plants, the central inference service forecasts from the window the plant shared and converts the forecast to "
  "power with the plant's own capacity and equipment: a turbine power curve for wind (zero below cut-in and above "
  "cut-out, never above rated power), a PV model for solar (zero at night). Power is never negative and never above "
  "capacity (DR-01 to DR-03). Lab sites, which have no real capacity, show the power of a reference 2 MW turbine or "
  "1 MW PV plant and say so. A new plant gets forecasts from the global model as soon as it has shared its first "
  "window, without any training of its own (FR-15, cold start). All timestamps are UTC (DR-09).")
P("Plant forecasts are made every hour and stored, so the page opens fast and shows when the forecast was made. "
  "Plants that do not share a window download the current model, forecast on their own server and send only the "
  "forecast back (local mode); the website shows those the same way. Each forecast carries a short summary (FR-25): "
  "the peak, the lowest output and any large drop, computed on the server and, when enabled, worded by Claude from "
  "those few numbers only.")
note("The model architecture, the training method and the accuracy results are in the separate model document. "
     "This section only describes how the website obtains and presents forecasts.")

# 9
H1(9, "Training from the website")
bullets([
    "<b>Starting a run.</b> The API checks the configuration, resolves the sites (named ones, or every site that can "
    "train now), checks that the federation is reachable with enough clients, creates the run folder and starts the "
    "run on the SuperLink with the Flower CLI. One run at a time.",
    "<b>Following a run.</b> The server application writes one line per round (loss, validation errors in physical "
    "units, per-site status, upload size) and a result file at the end. The dashboard reads them live (FR-21, FR-24).",
    "<b>Drop-outs.</b> A round finishes when the minimum number of clients has replied; missing sites are shown as "
    "dropped (FR-13).",
    "<b>Update checks.</b> Updates with non-finite values, wrong shapes, or a size more than five times the round's "
    "median are left out and shown as rejected with the reason.",
    "<b>Many plants.</b> With more than 30 eligible sites, each round trains on half of them.",
    "<b>Scheduled runs.</b> Weekly slots per energy type (for example Sunday 02:00 Almaty time). If too few plants "
    "can train or a run is active, the slot is retried every hour for six hours; every attempt is in the audit log.",
    "<b>Promotion.</b> An administrator promotes a finished run; its best checkpoint becomes the model that serves forecasts.",
])

# 10
H1(10, "Telegram alerts")
P("Users connect Telegram from their account menu: the website opens a one-time link to the ArqauQuat bot, the user "
  "presses Start, and the panel switches on by itself. Messages contain the plant, its new state and a link, never "
  "measurements.")
table([["Recipient", "Messages"],
       ["Operators", "Plant approved, rejected, suspended, resumed, revoked; new kit available; plant online, offline and back online."],
       ["Administrators (and a support chat)", "New plant waiting for approval; plant offline."]],
      [0.3, 0.7], bold_first=True)
P("Alerts are driven by the audit log: a background loop reads new entries, writes messages to an outbox and sends them "
  "with retries, so no alert is lost if Telegram is briefly unreachable. Online and offline changes are sent once per change.")

# 11
H1(11, "API and data model")
H2("Main endpoints")
table([["Endpoint", "Who", "Purpose"],
       ["POST /api/auth/register, /login, /logout; GET /api/auth/me", "everyone", "Accounts and sessions"],
       ["GET /api/sites; GET /api/my/sites[/{id}]", "public / operator", "Public site list; own plants with status"],
       ["POST /api/sites; PUT /api/my/sites/{id}", "operator", "Register a plant; edit while waiting"],
       ["POST /api/my/sites/{id}/kit", "owner, admin", "Download the site kit (new one-time token)"],
       ["POST /api/admin/sites/{id}/{action}", "admin", "approve, reject, suspend, resume, revoke"],
       ["POST /api/admin/sites/{id}/reissue-kit", "admin", "Revoke credentials, allow a new kit"],
       ["GET /api/admin/overview, /users, /audit; POST, PATCH users", "admin", "Overview, user management, audit log"],
       ["GET /api/forecast", "public / owner", "Forecast JSON with model card (FR-22, FR-26)"],
       ["GET /api/runs[/{id}]; POST /api/runs; POST /api/runs/{id}/stop", "public / admin", "Training runs"],
       ["GET /api/models; POST /api/models/promote", "public / admin", "Promoted models"],
       ["GET /api/federation", "public", "Is the SuperLink reachable, how many clients"],
       ["GET, POST, DELETE /api/me/telegram", "user", "Telegram alerts"],
       ["POST /site-api/enroll", "plant with token", "Certificate signing request + Flower key → certificate"],
       ["POST /site-api/heartbeat, /quality, /forecast-input", "plant certificate", "Status, daily counts, forecast window"]],
      [0.46, 0.17, 0.37])
H2("Database")
table([["Area", "Tables"],
       ["Accounts", "organizations, users, sessions, audit_log"],
       ["Plants", "sites (lab sites and plants, status, equipment, consents)"],
       ["Site connection", "enrollment_tokens, site_credentials, site_heartbeats, site_quality, forecast_inputs"],
       ["Certificates", "site_revocations (kept after a plant is deleted)"],
       ["Training", "training_schedule"],
       ["Alerts", "telegram_links, telegram_link_codes, notifications, notify_state, site_alert_state"]],
      [0.22, 0.78], bold_first=True)
P("Secrets are stored only as hashes (passwords with argon2id; session tokens, enrollment tokens and site keys with "
  "SHA-256). Training runs and model checkpoints are files in a shared volume, read by the API.")

# 12
H1(12, "Deployment")
table([["", "Lab stack", "Central server"],
       ["Purpose", "Experiments with ten lab sites (5 wind, 5 solar) on the lab GPU server", "Real plants connecting over the internet"],
       ["Start", "docker compose -f deploy/docker-compose.yml up -d", "docker compose -f deploy/central/docker-compose.yml up -d"],
       ["Federation", "SuperLink + one client container per lab site, each mounting only its own data", "SuperLink with TLS and node authentication; clients are the plants' site kits"],
       ["Published", "website and API on the host", "gateway only (80, 443)"],
       ["Certificates", "not needed (plants use a site key)", "Let's Encrypt for both host names; internal CA for the SuperLink; site CA for plants"],
       ["Forecasts", "per-site inference for lab sites, central inference for plants", "central inference"]],
      [0.14, 0.43, 0.43], bold_first=True)
P("Both stacks start with one command (NFR-08). For demonstrations we also shared the laptop deployment through a "
  "temporary public link (an SSH tunnel switched on and off with one script); it is not meant for real plants.")

# 13
H1(13, "Requirements covered")
P("Requirements from the requirements document that the website and API implement:")
table([["ID", "Requirement (short)", "How it is met", "Status"],
       ["FR-22", "REST API returns a forecast in JSON", "GET /api/forecast", "Done"],
       ["FR-23", "Choose energy type, site, horizon; forecast and actual on one chart", "Forecast page", "Done"],
       ["FR-24", "Training dashboard: round, validation error, clients", "Run detail page", "Done"],
       ["FR-26", "Reject invalid requests with a clear message", "422 with the reason; private plants answer like unknown sites", "Done"],
       ["FR-25", "LLM-generated text summary of the forecast (should)", "Summary from computed facts; worded by Claude when enabled", "Done"],
       ["FR-13", "Round finishes when clients drop out", "Shown per round on the dashboard", "Done"],
       ["FR-15", "New client gets forecasts without training (cold start)", "Plants get forecasts from the global model after sharing a window", "Done"],
       ["FR-18", "Experiment from one configuration", "Experiment page writes the run config", "Done"],
       ["FR-21", "Per-round log", "Dashboard reads the per-round metrics", "Done"],
       ["NFR-01", "Raw measurements never leave a client", "Site kit sends status, counts and model updates; window only with explicit consent", "Done (consented exception)"],
       ["NFR-03", "24 h forecast in under 5 s", "Central inference per request", "Measure for the report"],
       ["NFR-08", "One Docker Compose command", "Lab and central stacks", "Done"],
       ["NFR-09", "At least 20 simulated clients", "Platform supports dynamic plants; 20-plant run to be shown", "Measure for the report"],
       ["NFR-10", "Forecast in at most 3 steps", "Energy type → site → horizon", "Done"],
       ["DR-01–03", "Power curve, zero at night, within capacity", "Applied in central inference for plants", "Done"],
       ["DR-09", "UTC timestamps, local time zone as metadata", "All times UTC; each site keeps its time zone", "Done"]],
      [0.1, 0.33, 0.4, 0.17], bold_first=True)
note("Horizons changed from the requirements document (1 h, 6 h, 24 h) to 1 h, 72 h and 432 h during the semester; "
     "the website offers the new set. The design-document change belongs in the report's design changes section.")

# 14
H1(14, "Testing")
table([["Suite", "Tests", "What it covers"],
       ["API", "93", "Model versions, gates and veto, stored and local-mode forecasts, forecast summaries, participation (pause, consents, leave), health and operations; accounts and roles, plant registration and decisions, kits and enrollment, certificates and revocation, heartbeats and quality, forecasts and access rules, runs, the scheduler, Telegram alerts, demo reset. Runs against a throwaway PostgreSQL."],
       ["Site agent", "18", "Consent changes from the website, Enrollment with plant-made keys, heartbeat and suspension, quality counts, forecast window with consent, training store format, status page, mTLS mode."],
       ["Inference", "17", "Forecast windows, power conversion, solar zero at night."],
       ["ML core", "39", "Power errors by capacity and errors at 1, 6 and 24 h, Config consistency, data loading, solar, run logs, site-id clients, update screening, the agent's store read by the real loaders."],
       ["Frontend", "type check + production build", "TypeScript strict check (tsc) and next build."]],
      [0.14, 0.14, 0.72], bold_first=True)
P("The gateway configuration was also checked against stand-in services: no certificate is refused (403), a revoked "
  "certificate is refused (400), forged identity headers are replaced, internal Flower APIs are not routed (404), "
  "and a newly revoked certificate stops working within 30 seconds without a restart.")

# 15
H1(15, "Design decisions")
table([["Decision", "Alternative", "Reason"],
       ["Plain SQL migrations", "Alembic", "Six small migrations; no extra framework to learn."],
       ["Own site CA and client certificates", "API keys only", "Keys can be copied; certificates can be revoked at the gateway before anything reaches the platform."],
       ["nginx gateway", "Caddy, Envoy", "nginx supports client certificates with a revocation list and gRPC proxying; tested in a prototype."],
       ["Tunnel container at each plant", "SuperNode connecting directly", "Flower 1.25's SuperNode cannot present a client certificate."],
       ["Central forecasting with consent", "Forecasting at each plant", "Fast, uniform forecasts and cold start; plants that do not consent keep their data (local mode is spring work)."],
       ["Key made at the plant", "Server-generated keys in the kit", "Private keys never travel; a leaked kit is useless after enrollment."],
       ["Same-origin API through the web server", "Separate API domain", "No CORS setup; works on localhost and behind a public link with one build."],
       ["Simulated plants run the real kit", "A separate demo mode", "The demo exercises the real platform; only the data source is simulated."]],
      [0.27, 0.23, 0.5], bold_first=True)

# 16
H1(16, "Limitations and spring work")
bullets([
    "<b>Not yet run live:</b> the site-network features (certificates, gateway, site kits, model registry, stored "
    "forecasts, backups) are covered by automated tests but still need an end-to-end run on the lab server.",
    "<b>Scale and security results:</b> the 20-plant load test and the security-check script are ready; their "
    "results belong in the report once run.",
    "<b>Administrator two-factor login</b> was left out by decision.",
    "Published container images for plants (today the images are built locally).",
])

# 17
H1(17, "Checklist for the report writers")
H2("Figures to include")
bullets(["Figure 1 (system context), Figure 2 (plant lifecycle), Figure 3 (site kit), Figure 4 (forecast request) from this document.",
         "Screenshots: Home with the map; Forecast page with a wind plant and a solar plant; the model card; a run "
         "dashboard during training; the Experiments page; the plant registration form; a plant page showing Online "
         "and the quality chart; the admin overview; the approvals queue; the audit log; the Telegram panel and one "
         "Telegram message; the plant's local status page.",
         "Take screenshots at 1440 px width, light theme, with demo data (no real personal data)."])
H2("Numbers to measure and insert")
bullets(["Forecast response time for one site and the 72 h horizon (NFR-03), median of 20 requests.",
         "Time from kit download to the plant showing Online.",
         "Number of clicks from the home page to a forecast (NFR-10).",
         "Upload size per client per round, from the run dashboard (link to the model document for NFR-02).",
         "A run with 20 simulated plants: rounds, dropped and rejected updates (NFR-09)."])
H2("Suggested place in the report")
table([["Report chapter", "Sections of this document"],
       ["System design / architecture", "2, 3, 12, 15"],
       ["Implementation: web application", "4, 5, 8, 9, 10, 11"],
       ["Security and privacy", "6, 7"],
       ["Testing and evaluation", "13, 14, plus the measured numbers above"],
       ["Conclusion and future work", "16"]],
      [0.4, 0.6], bold_first=True)
H2("Glossary")
table([["Term", "Meaning"],
       ["Plant", "A real wind or solar power plant registered by an operator."],
       ["Lab site", "One of the ten built-in sites with public NASA POWER data, used for experiments."],
       ["Site kit", "The zip a plant installs: agent, tunnel and Flower client."],
       ["Site agent", "The program in the kit that enrolls, reports status and keeps the training store."],
       ["SuperLink / SuperNode", "Flower's server and client processes."],
       ["Site CA", "Our certificate authority that signs plant certificates."],
       ["CRL", "Certificate revocation list: certificates the gateway must refuse."],
       ["Promoted model", "The finished run whose model currently serves forecasts."],
       ["Model card", "The box under a forecast that names the model that made it."]],
      [0.25, 0.75], bold_first=True)

doc.build(story)
print("written", OUT)
