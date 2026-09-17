import os
import math
import fitz

OUTPUT_DIR = r"d:\NSBM\Projects 2.0\September18\Sep18ComptetionDev\Documentation\diagrams"
SCRATCH_DIR = r"C:\Users\Cyber_bot\.gemini\antigravity\brain\633938cb-3ec3-4588-b7cf-6a3a3fa4f725\scratch"

# ==============================================================================
# VECTOR GEOMETRY PRIMITIVES (Independent of SVG Markers)
# ==============================================================================

def svg_plate_text(x, y, text, font_size=11, font_weight="normal", anchor="middle", font_family="Arial, Helvetica, sans-serif", pad_x=6, pad_y=4, is_italic=False):
    style_tag = 'font-style="italic"' if is_italic else ''
    weight_tag = f'font-weight="{font_weight}"'
    clean_text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    approx_w = len(clean_text) * (font_size * 0.58) + (pad_x * 2)
    h = font_size + (pad_y * 2)
    rx = x - (approx_w / 2.0) if anchor == "middle" else (x if anchor == "start" else x - approx_w)
    ry = y - font_size + 1
    return f"""
    <rect x="{rx:.1f}" y="{ry:.1f}" width="{approx_w:.1f}" height="{h:.1f}" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="1" />
    <text x="{x}" y="{y}" font-family="{font_family}" font-size="{font_size}" {weight_tag} {style_tag} text-anchor="{anchor}" fill="#000000">{text}</text>
    """

def vector_arrow(x1, y1, x2, y2, arrow_type="solid", stroke_width=1.8, stroke_dash=None, size=10):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return ""
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux

    dash_attr = f'stroke-dasharray="{stroke_dash}"' if stroke_dash else ""

    if arrow_type == "solid":
        tip_x = x2
        tip_y = y2
        base_x = x2 - ux * size
        base_y = y2 - uy * size
        left_x = base_x + nx * (size * 0.5)
        left_y = base_y + ny * (size * 0.5)
        right_x = base_x - nx * (size * 0.5)
        right_y = base_y - ny * (size * 0.5)
        line_svg = f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{base_x:.1f}" y2="{base_y:.1f}" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />'
        poly_svg = f'<polygon points="{tip_x:.1f},{tip_y:.1f} {left_x:.1f},{left_y:.1f} {right_x:.1f},{right_y:.1f}" fill="#000000" stroke="#000000" stroke-width="1" />'
        return line_svg + "\n" + poly_svg
    elif arrow_type == "open":
        base_x = x2 - ux * size
        base_y = y2 - uy * size
        left_x = base_x + nx * (size * 0.5)
        left_y = base_y + ny * (size * 0.5)
        right_x = base_x - nx * (size * 0.5)
        right_y = base_y - ny * (size * 0.5)
        line_svg = f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />'
        path_svg = f'<path d="M {left_x:.1f} {left_y:.1f} L {x2:.1f} {y2:.1f} L {right_x:.1f} {right_y:.1f}" fill="none" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />'
        return line_svg + "\n" + path_svg

def vector_polyline_arrow(points, arrow_type="solid", stroke_width=1.8, stroke_dash=None, size=10):
    if len(points) < 2:
        return ""
    res = []
    dash_attr = f'stroke-dasharray="{stroke_dash}"' if stroke_dash else ""

    p_str = " ".join([f"{p[0]},{p[1]}" for p in points])
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return f'<polyline points="{p_str}" fill="none" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />'

    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux

    if arrow_type == "solid":
        base_x = x2 - ux * size
        base_y = y2 - uy * size
        pts_clipped = points[:-1] + [(base_x, base_y)]
        p_clip_str = " ".join([f"{p[0]:.1f},{p[1]:.1f}" for p in pts_clipped])
        res.append(f'<polyline points="{p_clip_str}" fill="none" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />')
        left_x = base_x + nx * (size * 0.5)
        left_y = base_y + ny * (size * 0.5)
        right_x = base_x - nx * (size * 0.5)
        right_y = base_y - ny * (size * 0.5)
        res.append(f'<polygon points="{x2:.1f},{y2:.1f} {left_x:.1f},{left_y:.1f} {right_x:.1f},{right_y:.1f}" fill="#000000" stroke="#000000" stroke-width="1" />')
    elif arrow_type in ("open", "navigable"):
        res.append(f'<polyline points="{p_str}" fill="none" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />')
        base_x = x2 - ux * size
        base_y = y2 - uy * size
        left_x = base_x + nx * (size * 0.5)
        left_y = base_y + ny * (size * 0.5)
        right_x = base_x - nx * (size * 0.5)
        right_y = base_y - ny * (size * 0.5)
        res.append(f'<path d="M {left_x:.1f} {left_y:.1f} L {x2:.1f} {y2:.1f} L {right_x:.1f} {right_y:.1f}" fill="none" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />')

    return "\n".join(res)

def vector_uml_relation(x1, y1, x2, y2, rel_type="composition", stroke_width=1.8, stroke_dash=None):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return ""
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux

    res = []
    dash_attr = f'stroke-dasharray="{stroke_dash}"' if stroke_dash else ""

    if rel_type in ("composition", "aggregation"):
        d_len = 16
        d_wid = 6
        p_start = f"{x1:.1f},{y1:.1f}"
        p_mid1 = f"{x1 + ux * (d_len/2) + nx * d_wid:.1f},{y1 + uy * (d_len/2) + ny * d_wid:.1f}"
        p_end = f"{x1 + ux * d_len:.1f},{y1 + uy * d_len:.1f}"
        p_mid2 = f"{x1 + ux * (d_len/2) - nx * d_wid:.1f},{y1 + uy * (d_len/2) - ny * d_wid:.1f}"
        fill_color = "#000000" if rel_type == "composition" else "#FFFFFF"
        res.append(f'<polygon points="{p_start} {p_mid1} {p_end} {p_mid2}" fill="{fill_color}" stroke="#000000" stroke-width="{stroke_width}" />')
        res.append(f'<line x1="{x1 + ux * d_len:.1f}" y1="{y1 + uy * d_len:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />')
    elif rel_type in ("navigable", "association_arrow"):
        res.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#000000" stroke-width="{stroke_width}" {dash_attr} />')
        a_len = 11
        a_wid = 5.5
        base_x = x2 - ux * a_len
        base_y = y2 - uy * a_len
        p1 = f"{base_x + nx * a_wid:.1f},{base_y + ny * a_wid:.1f}"
        p2 = f"{base_x - nx * a_wid:.1f},{base_y - ny * a_wid:.1f}"
        res.append(f'<path d="M {p1} L {x2:.1f} {y2:.1f} L {p2}" fill="none" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />')
    return "\n".join(res)

def vector_crows_foot(x1, y1, x2, y2, start_card="1", end_card="many", stroke_width=2):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return ""
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux

    res = []
    res.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#000000" stroke-width="{stroke_width}" />')

    def draw_card(cx, cy, u_dir_x, u_dir_y, n_dir_x, n_dir_y, card):
        bx = -u_dir_x
        by = -u_dir_y
        items = []
        if card in ("1", "mandatory_one"):
            for d in [8, 15]:
                mx = cx + bx * d
                my = cy + by * d
                items.append(f'<line x1="{mx + n_dir_x * 8:.1f}" y1="{my + n_dir_y * 8:.1f}" x2="{mx - n_dir_x * 8:.1f}" y2="{my - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
        elif card in ("0..1", "optional_one"):
            mx = cx + bx * 8
            my = cy + by * 8
            items.append(f'<line x1="{mx + n_dir_x * 8:.1f}" y1="{my + n_dir_y * 8:.1f}" x2="{mx - n_dir_x * 8:.1f}" y2="{my - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            circle_x = cx + bx * 18
            circle_y = cy + by * 18
            items.append(f'<circle cx="{circle_x:.1f}" cy="{circle_y:.1f}" r="5" fill="#FFFFFF" stroke="#000000" stroke-width="{stroke_width}" />')
        elif card in ("many", "1..N", "mandatory_many"):
            apex_x = cx + bx * 14
            apex_y = cy + by * 14
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx + n_dir_x * 9:.1f}" y2="{cy + n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx - n_dir_x * 9:.1f}" y2="{cy - n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            hx = cx + bx * 20
            hy = cy + by * 20
            items.append(f'<line x1="{hx + n_dir_x * 8:.1f}" y1="{hy + n_dir_y * 8:.1f}" x2="{hx - n_dir_x * 8:.1f}" y2="{hy - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
        elif card in ("0..N", "crows_foot_zero_many", "optional_many"):
            apex_x = cx + bx * 14
            apex_y = cy + by * 14
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx + n_dir_x * 9:.1f}" y2="{cy + n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx - n_dir_x * 9:.1f}" y2="{cy - n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            circle_x = cx + bx * 22
            circle_y = cy + by * 22
            items.append(f'<circle cx="{circle_x:.1f}" cy="{circle_y:.1f}" r="5" fill="#FFFFFF" stroke="#000000" stroke-width="{stroke_width}" />')
        return "\n".join(items)

    res.append(draw_card(x1, y1, -ux, -uy, nx, ny, start_card))
    res.append(draw_card(x2, y2, ux, uy, nx, ny, end_card))
    return "\n".join(res)

def vector_polyline_crows_foot(points, start_card="1", end_card="many", stroke_width=2):
    if len(points) < 2:
        return ""
    res = []
    p_str = " ".join([f"{p[0]},{p[1]}" for p in points])
    res.append(f'<polyline points="{p_str}" fill="none" stroke="#000000" stroke-width="{stroke_width}" />')

    # Start segment:
    x1, y1 = points[0]
    x2, y2 = points[1]
    dx = x2 - x1
    dy = y2 - y1
    l1 = math.hypot(dx, dy)
    ux1, uy1 = dx / l1, dy / l1
    nx1, ny1 = -uy1, ux1

    # End segment:
    xn1, yn1 = points[-2]
    xn, yn = points[-1]
    dxn = xn - xn1
    dyn = yn - yn1
    ln = math.hypot(dxn, dyn)
    uxn, uyn = dxn / ln, dyn / ln
    nxn, nyn = -uyn, uxn

    def draw_card(cx, cy, u_dir_x, u_dir_y, n_dir_x, n_dir_y, card):
        bx = -u_dir_x
        by = -u_dir_y
        items = []
        if card in ("1", "mandatory_one"):
            for d in [8, 15]:
                mx = cx + bx * d
                my = cy + by * d
                items.append(f'<line x1="{mx + n_dir_x * 8:.1f}" y1="{my + n_dir_y * 8:.1f}" x2="{mx - n_dir_x * 8:.1f}" y2="{my - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
        elif card in ("0..1", "optional_one"):
            mx = cx + bx * 8
            my = cy + by * 8
            items.append(f'<line x1="{mx + n_dir_x * 8:.1f}" y1="{my + n_dir_y * 8:.1f}" x2="{mx - n_dir_x * 8:.1f}" y2="{my - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            circle_x = cx + bx * 18
            circle_y = cy + by * 18
            items.append(f'<circle cx="{circle_x:.1f}" cy="{circle_y:.1f}" r="5" fill="#FFFFFF" stroke="#000000" stroke-width="{stroke_width}" />')
        elif card in ("many", "1..N", "mandatory_many"):
            apex_x = cx + bx * 14
            apex_y = cy + by * 14
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx + n_dir_x * 9:.1f}" y2="{cy + n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx - n_dir_x * 9:.1f}" y2="{cy - n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            hx = cx + bx * 20
            hy = cy + by * 20
            items.append(f'<line x1="{hx + n_dir_x * 8:.1f}" y1="{hy + n_dir_y * 8:.1f}" x2="{hx - n_dir_x * 8:.1f}" y2="{hy - n_dir_y * 8:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
        elif card in ("0..N", "crows_foot_zero_many", "optional_many"):
            apex_x = cx + bx * 14
            apex_y = cy + by * 14
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx + n_dir_x * 9:.1f}" y2="{cy + n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            items.append(f'<line x1="{apex_x:.1f}" y1="{apex_y:.1f}" x2="{cx - n_dir_x * 9:.1f}" y2="{cy - n_dir_y * 9:.1f}" stroke="#000000" stroke-width="{stroke_width}" stroke-linecap="round" />')
            circle_x = cx + bx * 22
            circle_y = cy + by * 22
            items.append(f'<circle cx="{circle_x:.1f}" cy="{circle_y:.1f}" r="5" fill="#FFFFFF" stroke="#000000" stroke-width="{stroke_width}" />')
        return "\n".join(items)

    res.append(draw_card(x1, y1, -ux1, -uy1, nx1, ny1, start_card))
    res.append(draw_card(xn, yn, uxn, uyn, nxn, nyn, end_card))
    return "\n".join(res)

def get_header(title, standard, doc_id, revision="v2.0-FINAL"):
    return f"""
    <!-- Top Header -->
    <rect x="60" y="35" width="1800" height="75" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="85" y="70" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="bold" fill="#000000">{title}</text>
    <text x="85" y="94" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#000000">SDLC Phase 2: Design Document &amp; Architectural Specification | Standard: {standard}</text>
    
    <!-- Doc Metadata Box -->
    <rect x="1500" y="45" width="340" height="55" fill="#FFFFFF" stroke="#000000" stroke-width="1" />
    <text x="1515" y="65" font-family="Consolas, monospace" font-size="11" fill="#000000">DOC ID: {doc_id}</text>
    <text x="1515" y="80" font-family="Consolas, monospace" font-size="10" fill="#000000">REV: {revision} | STATUS: APPROVED</text>
    <text x="1515" y="93" font-family="Consolas, monospace" font-size="10" fill="#000000">SPEC: ISO/IEC/IEEE 42010:2011</text>
    """

def get_footer(standard_notice):
    return f"""
    <!-- Bottom Footer -->
    <rect x="60" y="1025" width="1800" height="35" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="85" y="1047" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#000000">Nova Desktop Companion — Autonomous Acoustic-Driven Desktop Assistant | {standard_notice}</text>
    <text x="1620" y="1047" font-family="Consolas, monospace" font-size="11" fill="#000000">MONOCHROME MASTER | 1920x1080</text>
    """

# ==============================================================================
# 1. USE CASE DIAGRAM
# ==============================================================================
def generate_use_case_diagram():
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("UML 2.5 Use Case Diagram — System Actor Interaction &amp; Operational Boundaries", "OMG Unified Modeling Language (UML) v2.5.1", "NOVA-SDLC-UML-UC-01")}

    <!-- System Boundary -->
    <rect x="340" y="130" width="1240" height="870" fill="#FFFFFF" stroke="#000000" stroke-width="2.5" />
    <rect x="340" y="130" width="460" height="35" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="355" y="153" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="bold" fill="#000000">System Boundary: Nova Desktop Companion v2.0</text>

    <!-- ACTOR 1: Primary Operator (Left) -->
    <g transform="translate(160, 520)">
        <circle cx="0" cy="-45" r="22" fill="#FFFFFF" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="-23" x2="0" y2="28" stroke="#000000" stroke-width="2.5" />
        <line x1="-35" y1="-5" x2="35" y2="-5" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="28" x2="-26" y2="72" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="28" x2="26" y2="72" stroke="#000000" stroke-width="2.5" />
        <text x="0" y="102" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#000000">Operator / User</text>
        <text x="0" y="120" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">&lt;&lt;human primary&gt;&gt;</text>
    </g>

    <!-- ACTOR 2: Windows OS Subsystems (Right) -->
    <g transform="translate(1760, 520)">
        <circle cx="0" cy="-45" r="22" fill="#FFFFFF" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="-23" x2="0" y2="28" stroke="#000000" stroke-width="2.5" />
        <line x1="-35" y1="-5" x2="35" y2="-5" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="28" x2="-26" y2="72" stroke="#000000" stroke-width="2.5" />
        <line x1="0" y1="28" x2="26" y2="72" stroke="#000000" stroke-width="2.5" />
        <text x="0" y="102" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#000000">Windows 11 OS</text>
        <text x="0" y="120" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">&lt;&lt;system service&gt;&gt;</text>
        <text x="0" y="136" font-family="Arial, Helvetica, sans-serif" font-size="10" text-anchor="middle" fill="#000000">(UIA / User32 / WASAPI)</text>
    </g>

    <!-- ================= 4 ARCHITECTURAL TIERS ================= -->

    <!-- TIER 1: AUDIO ACQUISITION & ASR (y = 220) -->
    <!-- Col 1: UC-01 -->
    <ellipse cx="550" cy="220" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="550" y="215" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-01: Voice Command &amp; Wake</text>
    <text x="550" y="233" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Initiate acoustic capture session</text>

    <!-- Col 2: UC-06 -->
    <ellipse cx="960" cy="220" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="960" y="215" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-06: Continuous Ring Buffer</text>
    <text x="960" y="233" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">16kHz mono audio ring capture</text>

    <!-- Col 3: UC-07 -->
    <ellipse cx="1370" cy="220" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="1370" y="215" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-07: Vosk ASR Intent Parsing</text>
    <text x="1370" y="233" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Extract ActionToken from phonemes</text>

    <!-- Tier 1 Flows -->
    {vector_arrow(710, 220, 800, 220, "open", stroke_dash="6,4")}
    {svg_plate_text(755, 212, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    {vector_arrow(1120, 220, 1210, 220, "open", stroke_dash="6,4")}
    {svg_plate_text(1165, 212, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- TIER 2: ACOUSTIC IMPULSE DETECTION & CALIBRATION (y = 400..530) -->
    <!-- Col 1: UC-03 (Snap Click) -->
    <ellipse cx="550" cy="380" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="550" y="375" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-03: Acoustic Snap Click</text>
    <text x="550" y="393" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Execute click via finger snap</text>

    <!-- Col 1: UC-05 (Audio Calibration) -->
    <ellipse cx="550" cy="510" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="550" y="505" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-05: Audio Calibration</text>
    <text x="550" y="523" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Adjust impulse &amp; noise thresholds</text>

    <!-- Col 2: UC-08 (Impulse Detection) -->
    <ellipse cx="960" cy="380" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="960" y="375" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-08: Impulse Spike Detection</text>
    <text x="960" y="393" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Bandpass filter &amp; envelope spike</text>

    <!-- Tier 2 Flows -->
    {vector_arrow(710, 380, 800, 380, "open", stroke_dash="6,4")}
    {svg_plate_text(755, 372, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    {vector_arrow(695, 490, 825, 405, "open", stroke_dash="6,4")}
    {svg_plate_text(760, 442, "&lt;&lt;extend&gt;&gt;", font_size=10, is_italic=True)}

    <!-- TIER 3: ARBITRATION, TARGETING & DISPATCH (y = 660..780) -->
    <!-- Col 1: UC-02 (Target Desktop Element) -->
    <ellipse cx="550" cy="670" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="550" y="665" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-02: Target Desktop Element</text>
    <text x="550" y="683" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Resolve UI element from speech</text>

    <!-- Col 2: UC-09 (Action Arbitration Queue) -->
    <ellipse cx="960" cy="670" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="960" y="665" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-09: Action Arbitration Queue</text>
    <text x="960" y="683" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Correlate intent with acoustic snap</text>

    <!-- Col 3: UC-11 (Inspect Windows UIA Tree) -->
    <ellipse cx="1370" cy="530" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="1370" y="525" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-11: Inspect Windows UIA Tree</text>
    <text x="1370" y="543" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Traverse accessibility hierarchy</text>

    <!-- Col 3: UC-12 (Dispatch Win32 SendInput) -->
    <ellipse cx="1370" cy="670" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="1370" y="665" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-12: Dispatch Win32 SendInput</text>
    <text x="1370" y="683" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Inject synthetic clicks &amp; keys</text>

    <!-- Tier 3 Flows -->
    {vector_arrow(710, 670, 800, 670, "open", stroke_dash="6,4")}
    {svg_plate_text(755, 662, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- UC-07 (ASR) drops through corridor x=1145 to UC-09 (Arbitration) -->
    {vector_polyline_arrow([(1210, 220), (1145, 220), (1145, 642), (1080, 652)], "open", stroke_dash="6,4")}
    {svg_plate_text(1145, 330, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- UC-08 (Impulse) drops straight to UC-09 (Arbitration) -->
    {vector_arrow(960, 416, 960, 634, "open", stroke_dash="6,4")}
    {svg_plate_text(960, 525, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- UC-09 extends UC-11 (through corridor x=1185, strictly parallel, zero intersection) -->
    {vector_polyline_arrow([(1115, 655), (1185, 655), (1185, 530), (1210, 530)], "open", stroke_dash="6,4")}
    {svg_plate_text(1185, 592, "&lt;&lt;extend&gt;&gt;", font_size=10, is_italic=True)}

    <!-- UC-09 includes UC-12 -->
    {vector_arrow(1120, 670, 1210, 670, "open", stroke_dash="6,4")}
    {svg_plate_text(1165, 662, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- TIER 4: MASCOT HUD & VISUAL FEEDBACK (y = 830) -->
    <!-- Col 1: UC-04 -->
    <ellipse cx="550" cy="830" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="550" y="825" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-04: View Mascot HUD Status</text>
    <text x="550" y="843" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Observe reactive animated feedback</text>

    <!-- Col 2: UC-10 -->
    <ellipse cx="960" cy="830" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="960" y="825" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-10: Manage Mascot FSM</text>
    <text x="960" y="843" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Drive idle, listen, target, click states</text>

    <!-- Col 3: UC-13 -->
    <ellipse cx="1370" cy="830" rx="160" ry="36" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="1370" y="825" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">UC-13: Direct2D Overlay Render</text>
    <text x="1370" y="843" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">Draw transparent HUD &amp; crosshair</text>

    <!-- Tier 4 Flows -->
    {vector_arrow(710, 830, 800, 830, "open", stroke_dash="6,4")}
    {svg_plate_text(755, 822, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    {vector_arrow(960, 706, 960, 794, "open", stroke_dash="6,4")}
    {svg_plate_text(960, 750, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    {vector_arrow(1120, 830, 1210, 830, "open", stroke_dash="6,4")}
    {svg_plate_text(1165, 822, "&lt;&lt;include&gt;&gt;", font_size=10, is_italic=True)}

    <!-- Primary Operator Associations (Direct solid lines) -->
    <path d="M 195 490 L 310 240 L 390 225" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 195 505 L 390 380" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 195 520 L 390 510" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 195 535 L 390 670" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 195 550 L 310 810 L 390 830" fill="none" stroke="#000000" stroke-width="1.8" />

    <!-- OS Actor Associations (Direct solid lines) -->
    <path d="M 1725 510 L 1530 530" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 1725 530 L 1530 670" fill="none" stroke="#000000" stroke-width="1.8" />
    <path d="M 1725 550 L 1530 830" fill="none" stroke="#000000" stroke-width="1.8" />

    <!-- Legend (Bottom Left) -->
    <rect x="360" y="895" width="520" height="90" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="375" y="915" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="bold" fill="#000000">UML 2.5 Use Case Notation Legend</text>
    <line x1="380" y1="940" x2="440" y2="940" stroke="#000000" stroke-width="1.8" />
    <text x="450" y="944" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#000000">Actor Association (Solid line)</text>
    {vector_arrow(380, 968, 440, 968, "open", stroke_dash="6,4")}
    <text x="450" y="972" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#000000">&lt;&lt;include&gt;&gt; / &lt;&lt;extend&gt;&gt; Dependency</text>
    <ellipse cx="720" cy="955" rx="35" ry="16" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="770" y="959" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#000000">Use Case Entity</text>

    {get_footer("OMG UML 2.5 Standard Semantic Profile | Strict Pure Monochrome Rendering")}
</svg>"""
    return svg

# ==============================================================================
# 2. CLASS DIAGRAM
# ==============================================================================
def generate_class_diagram():
    def class_box(x, y, w, header_title, stereotype, fields, methods):
        line_h = 16
        header_h = 42
        fields_h = len(fields) * line_h + 10
        methods_h = len(methods) * line_h + 10
        total_h = header_h + fields_h + methods_h

        svg_box = f"""
        <rect x="{x}" y="{y}" width="{w}" height="{total_h}" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <rect x="{x}" y="{y}" width="{w}" height="{header_h}" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
        <text x="{x + w/2}" y="{y + 17}" font-family="Arial, Helvetica, sans-serif" font-size="10.5" font-style="italic" text-anchor="middle" fill="#000000">{stereotype}</text>
        <text x="{x + w/2}" y="{y + 34}" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">{header_title}</text>
        <line x1="{x}" y1="{y + header_h}" x2="{x + w}" y2="{y + header_h}" stroke="#000000" stroke-width="1.5" />
        """
        curr_y = y + header_h + 15
        for f in fields:
            svg_box += f'<text x="{x + 10}" y="{curr_y}" font-family="Consolas, monospace" font-size="10.5" fill="#000000">{f}</text>'
            curr_y += line_h

        div_y = y + header_h + fields_h
        svg_box += f'<line x1="{x}" y1="{div_y}" x2="{x + w}" y2="{div_y}" stroke="#000000" stroke-width="1.5" />'

        curr_y = div_y + 15
        for m in methods:
            svg_box += f'<text x="{x + 10}" y="{curr_y}" font-family="Consolas, monospace" font-size="10.5" fill="#000000">{m}</text>'
            curr_y += line_h
        return svg_box

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("UML 2.5 Class Diagram — Core Domain Entity &amp; Architectural Component Model", "OMG Unified Modeling Language (UML) v2.5.1", "NOVA-SDLC-UML-CD-02")}

    <!-- ================= ROW 1: FACADE ROOT ================= -->
    {class_box(720, 118, 480, "NovaDesktopCompanion", "&lt;&lt;facade / coordinator&gt;&gt;", [
        "+ is_running: bool = False",
        "+ sample_rate: int = 16000",
        "+ active_profile: ConfigProfile",
        "+ current_state: SystemState"
    ], [
        "+ initialize_subsystems() : void",
        "+ start_pipeline() : void",
        "+ stop_pipeline() : void",
        "+ handle_emergency_abort() : void"
    ])}

    <!-- ================= ROW 2: 4 ACOUSTIC SUBSYSTEMS + NOTATION LEGEND (y=370..560) ================= -->
    <!-- Col 1: AudioCaptureManager -->
    {class_box(80, 370, 320, "AudioCaptureManager", "&lt;&lt;boundary / audio&gt;&gt;", [
        "- _stream: sd.InputStream",
        "- _ring_buffer: RingBuffer",
        "+ sample_rate: int = 16000",
        "+ block_size: int = 1024"
    ], [
        "+ start_stream() : void",
        "+ stop_stream() : void",
        "+ read_chunk() : bytes",
        "+ get_recent_frames(n) : ndarray"
    ])}

    <!-- Col 2: AcousticImpulseDetector -->
    {class_box(440, 370, 320, "AcousticImpulseDetector", "&lt;&lt;control / dsp&gt;&gt;", [
        "- _threshold_ratio: float = 3.5",
        "- _energy_history: deque",
        "+ snap_detected_sig: Signal",
        "+ calibration_profile: AudioCal"
    ], [
        "+ process_frame(frame) : bool",
        "+ compute_energy(frame) : float",
        "+ set_threshold(value: float) : void",
        "+ reset_state() : void"
    ])}

    <!-- Col 3: VoskSpeechEngine -->
    {class_box(800, 370, 320, "VoskSpeechEngine", "&lt;&lt;control / asr&gt;&gt;", [
        "- _model: vosk.Model",
        "- _recognizer: vosk.KaldiRec",
        "+ grammar_rules: list[str]",
        "+ token_parsed_sig: Signal"
    ], [
        "+ feed_audio(pcm_data: bytes) : void",
        "+ extract_intent(json_res) : ActionToken",
        "+ reload_model(path: str) : void",
        "+ reset_grammar() : void"
    ])}

    <!-- Col 4: TagSnapCoordinator -->
    {class_box(1160, 370, 320, "TagSnapCoordinator", "&lt;&lt;control / temporal&gt;&gt;", [
        "- _snap_timestamp: float",
        "- _token_timestamp: float",
        "+ correlation_window_ms: int = 800",
        "+ is_correlated: bool = False"
    ], [
        "+ record_snap(ts: float) : void",
        "+ record_token(token: ActionToken) : void",
        "+ evaluate_pairing() : bool",
        "+ flush_stale_events() : void"
    ])}

    <!-- Col 5: UML 2.5 Class Notation Legend (Exact 320x190 alignment) -->
    <rect x="1520" y="370" width="320" height="190" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <rect x="1520" y="370" width="320" height="36" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="1680" y="393" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="bold" text-anchor="middle" fill="#000000">UML 2.5 Class Notation Legend</text>
    {vector_uml_relation(1535, 422, 1595, 422, "composition")}
    <text x="1605" y="426" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Composition (Strong Ownership)</text>
    {vector_uml_relation(1535, 455, 1595, 455, "navigable")}
    <text x="1605" y="459" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Navigable Association / Dependency</text>
    {vector_uml_relation(1535, 488, 1595, 488, "navigable", stroke_dash="5,3")}
    <text x="1605" y="492" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Asynchronous Stream Dependency</text>
    <text x="1535" y="524" font-family="Consolas, monospace" font-size="10.5" font-weight="bold" fill="#000000">1, 0..*, 1..N</text>
    <text x="1635" y="524" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Multiplicity Cardinality</text>
    <text x="1535" y="546" font-family="Consolas, monospace" font-size="10.5" fill="#000000">+ public   - private   # protected</text>

    <!-- ================= ROW 3: EXECUTION & PRESENTATION PIPELINE (y=660..850) ================= -->
    <!-- Col 1: InputDriver -->
    {class_box(80, 660, 320, "InputDriver", "&lt;&lt;boundary / win32&gt;&gt;", [
        "- _sendinput_fn: Win32Proc",
        "+ click_delay_ms: int = 50",
        "+ last_coords: tuple[int, int]",
        "+ is_active: bool = True"
    ], [
        "+ send_mouse_click(x, y) : bool",
        "+ send_key_combination(keys) : bool",
        "+ query_element_rect(target) : Rect",
        "+ move_cursor(x, y) : void"
    ])}

    <!-- Col 2: ActionArbiter -->
    {class_box(440, 660, 320, "ActionArbiter", "&lt;&lt;control / arbiter&gt;&gt;", [
        "- _execution_queue: PriorityQueue",
        "- _is_busy: bool = False",
        "+ state_transition_sig: Signal",
        "+ emergency_stop: bool = False"
    ], [
        "+ enqueue_action(token: ActionToken) : void",
        "+ arbitrate_next_action() : void",
        "+ dispatch_execution(token) : void",
        "+ abort_pending() : void"
    ])}

    <!-- Col 3: ActionToken -->
    {class_box(800, 660, 320, "ActionToken", "&lt;&lt;entity / value_object&gt;&gt;", [
        "+ token_id: UUID",
        "+ action_type: ActionType",
        "+ target_label: str",
        "+ bounding_box: Rect",
        "+ confidence: float"
    ], [
        "+ is_expired(timeout_ms) : bool",
        "+ validate() : bool",
        "+ to_json() : str"
    ])}

    <!-- Col 4: MascotWidget -->
    {class_box(1160, 660, 320, "MascotWidget", "&lt;&lt;boundary / ui&gt;&gt;", [
        "- _current_fsm_state: MascotState",
        "- _animation_timer: QTimer",
        "+ screen_position: QPoint",
        "+ sprite_sheet: QPixmap"
    ], [
        "+ transition_to(state: MascotState) : void",
        "+ update_animation_frame() : void",
        "+ show_targeting_crosshair(x, y) : void",
        "+ reset_to_idle() : void"
    ])}

    <!-- Col 5: HudOverlay -->
    {class_box(1520, 660, 320, "HudOverlay", "&lt;&lt;boundary / overlay&gt;&gt;", [
        "- _overlay_hwnd: HWND",
        "- _opacity: float = 0.85",
        "+ is_visible: bool = False",
        "+ overlay_rect: QRect"
    ], [
        "+ draw_crosshair(x, y, w, h) : void",
        "+ render_text_bubble(text) : void",
        "+ clear_overlay() : void",
        "+ set_transparency(alpha) : void"
    ])}

    <!-- ================= RELATIONSHIP WIRING ================= -->
    <!-- 1. Central Facade Composition Bus to Row 2 Subsystems -->
    <!-- Diamond attached at bottom of NovaDesktopCompanion (960, 308) -->
    {vector_uml_relation(960, 308, 960, 338, "composition")}
    <line x1="240" y1="338" x2="1320" y2="338" stroke="#000000" stroke-width="1.8" />
    <line x1="240" y1="338" x2="240" y2="370" stroke="#000000" stroke-width="1.8" />
    <text x="250" y="362" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    <line x1="600" y1="338" x2="600" y2="370" stroke="#000000" stroke-width="1.8" />
    <text x="610" y="362" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    <line x1="960" y1="338" x2="960" y2="370" stroke="#000000" stroke-width="1.8" />
    <text x="970" y="362" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    <line x1="1320" y1="338" x2="1320" y2="370" stroke="#000000" stroke-width="1.8" />
    <text x="1330" y="362" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>

    <!-- 2. Row 2 Internal: AudioCaptureManager feeds AcousticImpulseDetector -->
    {vector_uml_relation(400, 465, 440, 465, "navigable")}
    {svg_plate_text(420, 452, "feeds", font_size=9.5, is_italic=True)}

    <!-- 3. Row 2 to Row 3 Vertical Signals (Zero Crossings) -->
    <!-- AudioCaptureManager streams buffer to ActionArbiter -->
    {vector_polyline_arrow([(240, 560), (240, 610), (480, 610), (480, 660)], "navigable", stroke_dash="5,3")}
    {svg_plate_text(340, 600, "&lt;&lt;streams PCM buffer&gt;&gt;", font_size=9, is_italic=True)}

    <!-- AcousticImpulseDetector triggers impulse to ActionArbiter (Direct Column Drop) -->
    {vector_uml_relation(600, 560, 600, 660, "navigable")}
    {svg_plate_text(600, 610, "triggers impulse [0..*]", font_size=9.5, font_weight="bold")}

    <!-- VoskSpeechEngine generates ActionToken (Direct Column Drop) -->
    {vector_uml_relation(960, 560, 960, 660, "navigable")}
    {svg_plate_text(960, 610, "generates [0..*]", font_size=9.5, font_weight="bold")}

    <!-- TagSnapCoordinator synchronizes timing with ActionToken -->
    {vector_polyline_arrow([(1320, 560), (1320, 610), (1040, 610), (1040, 660)], "navigable")}
    {svg_plate_text(1180, 600, "correlates timing", font_size=9.5, font_weight="bold")}

    <!-- 4. Row 3 Direct Neighbor Pipeline Connections (Zero Crossings) -->
    <!-- ActionArbiter dispatches to InputDriver (West Neighbor) -->
    {vector_uml_relation(440, 755, 400, 755, "navigable")}
    <text x="415" y="745" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    {svg_plate_text(420, 770, "dispatches", font_size=9, is_italic=True)}

    <!-- ActionArbiter consumes ActionToken (East Neighbor) -->
    {vector_uml_relation(760, 755, 800, 755, "navigable")}
    <text x="770" y="745" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    <text x="788" y="745" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">0..*</text>
    {svg_plate_text(780, 770, "consumes", font_size=9, is_italic=True)}

    <!-- ActionToken notifies MascotWidget (East Neighbor) -->
    {vector_uml_relation(1120, 755, 1160, 755, "navigable")}
    <text x="1130" y="745" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    <text x="1148" y="745" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">1</text>
    {svg_plate_text(1140, 770, "notifies", font_size=9, is_italic=True)}

    <!-- MascotWidget renders HudOverlay (East Neighbor) -->
    {vector_uml_relation(1480, 755, 1520, 755, "composition")}
    <text x="1490" y="745" font-family="Consolas, monospace" font-size="10" font-weight="bold" fill="#000000">1</text>
    <text x="1510" y="745" font-family="Consolas, monospace" font-size="10" font-weight="bold" fill="#000000">1</text>
    {svg_plate_text(1500, 770, "renders", font_size=9, is_italic=True)}
    {get_footer("OMG UML 2.5 Standard Semantic Profile | Strict Pure Monochrome Rendering")}
</svg>"""
    return svg

# ==============================================================================
# 3. SEQUENCE DIAGRAM
# ==============================================================================
def generate_sequence_diagram():
    lifelines = [
        {"name": "Operator: User", "type": "&lt;&lt;actor&gt;&gt;", "x": 150},
        {"name": "AudioCapture", "type": "&lt;&lt;manager&gt;&gt;", "x": 410},
        {"name": "ImpulseDetector", "type": "&lt;&lt;dsp&gt;&gt;", "x": 670},
        {"name": "VoskEngine", "type": "&lt;&lt;asr&gt;&gt;", "x": 930},
        {"name": "ActionArbiter", "type": "&lt;&lt;core&gt;&gt;", "x": 1190},
        {"name": "Win32Subsystem", "type": "&lt;&lt;os_api&gt;&gt;", "x": 1450},
        {"name": "MascotWidget", "type": "&lt;&lt;ui&gt;&gt;", "x": 1710}
    ]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("UML 2.5 Sequence Diagram — Audio Trigger to Input Arbitration &amp; Mascot Feedback Execution", "OMG Unified Modeling Language (UML) v2.5.1", "NOVA-SDLC-UML-SD-03")}

    <!-- Lifelines Header & Vertical Dashed Lines -->
    """
    for ll in lifelines:
        x = ll["x"]
        svg += f"""
        <rect x="{x - 85}" y="130" width="170" height="50" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <text x="{x}" y="150" font-family="Arial, Helvetica, sans-serif" font-size="11" font-style="italic" text-anchor="middle" fill="#000000">{ll['type']}</text>
        <text x="{x}" y="168" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">{ll['name']}</text>
        <line x1="{x}" y1="180" x2="{x}" y2="990" stroke="#000000" stroke-width="1.5" stroke-dasharray="6,5" />
        """

    def message_call(y, x1, x2, label, is_return=False, label_offset_x=None):
        dash = "6,4" if is_return else None
        arr = "open" if is_return else "solid"
        arrow_svg = vector_arrow(x1, y, x2, y, arrow_type=arr, stroke_dash=dash)
        label_y = y - 6
        mid_x = label_offset_x if label_offset_x is not None else (x1 + x2) / 2.0
        return f"""
        {arrow_svg}
        {svg_plate_text(mid_x, label_y, label, font_size=11, font_weight="bold" if not is_return else "normal")}
        """

    def self_call(y, x, label):
        pts = [(x+7, y), (x+45, y), (x+45, y+22), (x+7, y+22)]
        arrow_svg = vector_polyline_arrow(pts, arrow_type="solid")
        return f"""
        {arrow_svg}
        {svg_plate_text(x+52, y+15, label, font_size=10.5, anchor="start")}
        """

    # --- STANDARD INTERACTION SEQUENCE ---
    svg += message_call(215, 157, 403, '1: Voice command ("click target")')
    svg += self_call(235, 410, "2: Read 16kHz PCM audio chunk")
    svg += message_call(275, 417, 663, "3: Stream audio buffer chunk")
    svg += self_call(300, 670, "4: Compute envelope spike &amp; energy ratio")
    svg += message_call(335, 417, 923, "5: Stream audio buffer chunk", label_offset_x=530)
    svg += message_call(380, 677, 1183, "6: Notify snap acoustic impulse (timestamped)", label_offset_x=800)
    svg += self_call(405, 930, "7: Recognize phoneme grammar")
    svg += message_call(445, 937, 1183, "8: Return ActionToken(CLICK, target)")
    svg += self_call(475, 1190, "9: Correlate snap window (Delta-T &lt; 800ms)")
    svg += message_call(515, 1197, 1703, "10: SetState(TargetingAnimation)", label_offset_x=1580)
    svg += self_call(540, 1710, "11: Render crosshair HUD overlay")
    svg += message_call(575, 1197, 1443, "12: QueryElementBounds(TargetLabel)")
    svg += message_call(615, 1443, 1197, "13: Return BoundingRect(x, y, w, h)", is_return=True)
    svg += message_call(660, 1197, 1443, "14: SendInput(MOUSEEVENTF_CLICK)")
    svg += message_call(700, 1443, 1197, "15: Win32 dispatch confirmed", is_return=True)
    svg += message_call(740, 1197, 1703, "16: SetState(SuccessFeedback -> Rest)", label_offset_x=1580)
    svg += self_call(765, 1710, "17: Restore resting mascot sprite")

    # --- ALT COMBINED FRAGMENT (Emergency Abort) ---
    svg += f"""
    <!-- alt Frame for Emergency Abort Key (Esc) -->
    <rect x="90" y="815" width="1700" height="160" fill="none" stroke="#000000" stroke-width="2" stroke-dasharray="8,4" />
    <polygon points="90,815 350,815 330,845 90,845" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
    <text x="110" y="836" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="bold" fill="#000000">alt [Emergency Abort Key (ESC)]</text>
    <line x1="90" y1="895" x2="1790" y2="895" stroke="#000000" stroke-width="1.5" stroke-dasharray="4,4" />
    {svg_plate_text(105, 910, "[Key Intercepted / Cancel Execution]", font_size=10, is_italic=True, anchor="start")}
    """
    svg += message_call(860, 157, 1183, "18: KeyDown(VK_ESCAPE) interrupt")
    svg += self_call(880, 1190, "19: AbortOperation() &amp; FlushQueue()")
    svg += message_call(930, 1197, 1703, "20: ShowEmergencyAlert(Status='Cancelled')", label_offset_x=1580)

    # Activation Bars (Rendered on top to guarantee unbroken borders)
    activations = [
        (150, 205, 25),    # Operator: Speech command
        (150, 850, 25),    # Operator: ESC abort interrupt
        (410, 200, 150),   # AudioCapture
        (670, 260, 130),   # ImpulseDetector
        (930, 320, 140),   # VoskEngine
        (1190, 380, 565),  # ActionArbiter (covers all actions through emergency alert dispatch)
        (1450, 560, 160),  # Win32Subsystem
        (1710, 500, 280),  # MascotWidget: targeting & click animation
        (1710, 920, 25)    # MascotWidget: emergency alert display
    ]
    for (ax, ay, ah) in activations:
        svg += f'<rect x="{ax - 7}" y="{ay}" width="14" height="{ah}" fill="#FFFFFF" stroke="#000000" stroke-width="1.8" />'

    svg += f"""
    {get_footer("OMG UML 2.5 Standard Semantic Profile | Strict Pure Monochrome Rendering")}
</svg>"""
    return svg

# ==============================================================================
# 4. DEPLOYMENT DIAGRAM (Clean Ports, Zero 3D-Wall Crossing)
# ==============================================================================
def generate_deployment_diagram():
    def node_3d(x, y, w, h, d, title, stereotype="&lt;&lt;device&gt;&gt;", subtitle=""):
        st = stereotype.replace("<", "&lt;").replace(">", "&gt;") if "<" in stereotype else stereotype
        p_top = f"{x},{y} {x+d},{y-d} {x+w+d},{y-d} {x+w},{y}"
        p_side = f"{x+w},{y} {x+w+d},{y-d} {x+w+d},{y+h-d} {x+w},{y+h}"
        return f"""
        <polygon points="{p_top}" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <polygon points="{p_side}" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <text x="{x + 15}" y="{y + 20}" font-family="Arial, Helvetica, sans-serif" font-size="10.5" font-style="italic" fill="#000000">{st}</text>
        <text x="{x + 15}" y="{y + 36}" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" fill="#000000">{title}</text>
        {f'<text x="{x + 15}" y="{y + 50}" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#000000">{subtitle}</text>' if subtitle else ''}
        """

    def component_box(x, y, w, h, name, stereotype="&lt;&lt;artifact&gt;&gt;", details=None):
        st = stereotype.replace("<", "&lt;").replace(">", "&gt;") if "<" in stereotype else stereotype
        details_svg = ""
        if details:
            dy = y + 54
            for d in details:
                details_svg += f'<text x="{x + 12}" y="{dy}" font-family="Consolas, monospace" font-size="10" fill="#000000">{d}</text>'
                dy += 15
        return f"""
        <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#000000" stroke-width="1.8" />
        <rect x="{x - 6}" y="{y + 8}" width="12" height="7" fill="#FFFFFF" stroke="#000000" stroke-width="1.2" />
        <rect x="{x - 6}" y="{y + 20}" width="12" height="7" fill="#FFFFFF" stroke="#000000" stroke-width="1.2" />
        <text x="{x + 15}" y="{y + 18}" font-family="Arial, Helvetica, sans-serif" font-size="9.5" font-style="italic" fill="#000000">{st}</text>
        <text x="{x + 15}" y="{y + 35}" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="bold" fill="#000000">{name}</text>
        {details_svg}
        """

    def port_box(x, y, label):
        return f"""
        <rect x="{x-8}" y="{y-8}" width="16" height="16" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        {svg_plate_text(x, y - 13, label, font_size=9, font_weight="bold", anchor="middle")}
        """

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("UML 2.5 Deployment Diagram — Physical Hardware Nodes, Execution Environments &amp; Artifacts", "OMG Unified Modeling Language (UML) v2.5.1", "NOVA-SDLC-UML-DD-04")}

    <!-- HOST NODE: Windows PC (Left) -->
    {node_3d(50, 135, 1040, 855, 20, "Client Workstation PC", "&lt;&lt;device&gt;&gt;", "x86-64 Architecture | Windows 11 Pro 64-bit | 16 GB RAM | Direct3D 11")}

    <!-- Execution Environment 1: Python 3.12 Runtime (Left Column) -->
    {node_3d(80, 210, 420, 755, 14, "Python 3.12 64-Bit Runtime", "&lt;&lt;execution environment&gt;&gt;", "Isolated Virtualenv (.venv) | CPython Interpreter")}

    <!-- Artifacts inside Python Runtime (y=275..903) -->
    {component_box(100, 275, 380, 78, "nova_desktop_companion.exe", "&lt;&lt;artifact / executable&gt;&gt;", [
        "PyInstaller Single-Binary Bundle (PyQt6 Core)",
        "EntryPoint: src/main.py"
    ])}

    {component_box(100, 385, 380, 78, "vosk-model-small-en-us-0.15", "&lt;&lt;component / acoustic_model&gt;&gt;", [
        "Kaldi Offline HMM-GMM Acoustic Model",
        "Vocabulary: 50k Words / Fixed Grammar Rules"
    ])}

    {component_box(100, 495, 380, 78, "AcousticImpulseDetector", "&lt;&lt;component / dsp_pipeline&gt;&gt;", [
        "Butterworth Bandpass Filter (2kHz - 6kHz)",
        "Sliding Window Energy Spike Ratio Engine"
    ])}

    {component_box(100, 605, 380, 78, "ActionArbiter &amp; TokenDispatcher", "&lt;&lt;component / core_logic&gt;&gt;", [
        "Temporal Correlation Queue (800ms window)",
        "Win32 Priority Arbitration Queue"
    ])}

    {component_box(100, 715, 380, 78, "PyQt6 Mascot GUI &amp; HUD Overlay", "&lt;&lt;component / presentation&gt;&gt;", [
        "Direct2D Hardware-Accelerated Viewport",
        "WS_EX_LAYERED Transparent Topmost Surface"
    ])}

    {component_box(100, 825, 380, 78, "SoundDevice / PortAudio C-Bindings", "&lt;&lt;artifact / dynamic_lib&gt;&gt;", [
        "portaudio_x64.dll C-Library Interface",
        "Low-Latency Ring Buffer Stream Handler"
    ])}

    <!-- Execution Environment 2: Windows 11 OS Subsystems (Right Column) -->
    {node_3d(610, 210, 440, 755, 14, "Windows 11 OS Subsystems", "&lt;&lt;execution environment&gt;&gt;", "Kernel32 / User32 / COM Infrastructure")}

    <!-- Subsystem Artifacts (Aligned to Peripheral Positions) -->
    {component_box(635, 275, 390, 78, "WASAPI Core Audio Endpoint", "&lt;&lt;subsystem / audio_engine&gt;&gt;", [
        "Windows Audio Session API (Exclusive/Shared)",
        "16kHz 16-bit Mono Real-Time Capture Stream"
    ])}

    {component_box(635, 431, 390, 78, "User32 Raw Input &amp; Event Queue", "&lt;&lt;subsystem / input_manager&gt;&gt;", [
        "NtUserSendInput C-API Dispatcher",
        "Synthetic Mouse Clicks &amp; Keyboard Injection"
    ])}

    {component_box(635, 551, 390, 78, "UI Automation (UIA) Provider Tree", "&lt;&lt;subsystem / accessibility&gt;&gt;", [
        "IUIAutomation COM Interface (uiautomation)",
        "Desktop Element Rectangles &amp; Control Patterns"
    ])}

    {component_box(635, 671, 390, 78, "Desktop Window Manager (DWM)", "&lt;&lt;subsystem / graphics_compositor&gt;&gt;", [
        "DirectX 11 Hardware Compositor",
        "Per-Pixel Alpha Blended Window Manager"
    ])}

    {component_box(635, 836, 390, 78, "WASAPI Audio Playback Engine", "&lt;&lt;service / audio_render&gt;&gt;", [
        "DirectSound / WASAPI Auditory Feedback Playback",
        "Chime &amp; Error Tone Audio Synthesis"
    ])}

    <!-- PC BOUNDARY HARDWARE PORTS (at x=1090 on bevel wall) -->
    {port_box(1090, 314, "USB Audio In")}
    {port_box(1090, 470, "USB HID Bus")}
    {port_box(1090, 710, "DisplayPort Out")}
    {port_box(1090, 875, "3.5mm Audio Out")}

    <!-- Lines from Windows Subsystems to PC Boundary Ports (Strictly Horizontal) -->
    <line x1="1025" y1="314" x2="1082" y2="314" stroke="#000000" stroke-width="1.8" stroke-dasharray="4,3" />
    <line x1="1025" y1="470" x2="1082" y2="470" stroke="#000000" stroke-width="1.8" stroke-dasharray="4,3" />
    <line x1="1025" y1="710" x2="1082" y2="710" stroke="#000000" stroke-width="1.8" stroke-dasharray="4,3" />
    <line x1="1025" y1="875" x2="1082" y2="875" stroke="#000000" stroke-width="1.8" stroke-dasharray="4,3" />

    <!-- PERIPHERAL HARDWARE NODES (Right Side, Perfectly Aligned) -->
    <!-- Peripheral 1: USB Microphone -->
    {node_3d(1420, 244, 440, 140, 18, "USB Microphone Hardware", "&lt;&lt;device&gt;&gt;", "Input Interface: USB 2.0 / 3.0 Audio Device Class | 16kHz Mono Audio Sensor")}

    <!-- Peripheral 2: HID Devices -->
    {node_3d(1420, 400, 440, 140, 18, "Human Interface Devices (HID)", "&lt;&lt;device&gt;&gt;", "Physical Keyboard &amp; Mouse Hardware | Target of Synthetic Input Dispatch")}

    <!-- Peripheral 3: Display Surface -->
    {node_3d(1420, 640, 440, 140, 18, "Display Surface (Monitor)", "&lt;&lt;device&gt;&gt;", "Primary Display: 1920x1080 @ 60Hz | 32-bit ARGB Framebuffer | HDMI / DisplayPort")}

    <!-- Peripheral 4: Audio Playback -->
    {node_3d(1420, 805, 440, 140, 18, "Audio Playback Interface", "&lt;&lt;device&gt;&gt;", "Stereo Speakers / Headphones | 3.5mm Analog / USB Audio Feedback Playback")}

    <!-- ================= EXTERNAL COMMUNICATION PATHS (Clean Horizontal Lines, 322px Span) ================= -->
    <!-- 1. Microphone to USB Audio In Port -->
    {vector_arrow(1420, 314, 1098, 314, "solid", stroke_width=2.2)}
    {svg_plate_text(1259, 301, "&lt;&lt;USB 2.0 Audio Class&gt;&gt; 16kHz PCM Stream", font_size=9.5, font_weight="bold")}

    <!-- 2. USB HID Bus to Physical HID -->
    {vector_arrow(1098, 470, 1420, 470, "solid", stroke_width=2.2)}
    {svg_plate_text(1259, 457, "&lt;&lt;OS Input Bus&gt;&gt; Synthetic Event Dispatch", font_size=9.5, font_weight="bold")}

    <!-- 3. DisplayPort Out to Display Monitor -->
    {vector_arrow(1098, 710, 1420, 710, "solid", stroke_width=2.2)}
    {svg_plate_text(1259, 697, "&lt;&lt;DisplayPort / HDMI&gt;&gt; 60Hz ARGB Direct Refresh", font_size=9.5, font_weight="bold")}

    <!-- 4. 3.5mm Audio Out to Audio Output -->
    {vector_arrow(1098, 875, 1420, 875, "solid", stroke_width=2.2)}
    {svg_plate_text(1259, 862, "&lt;&lt;DirectSound / 3.5mm&gt;&gt; Feedback Chime Stream", font_size=9.5, font_weight="bold")}

    <!-- Internal Python-to-OS Bindings (Through Channel x=480..635) -->
    <!-- SoundDevice to WASAPI -->
    {vector_polyline_arrow([(480, 864), (505, 864), (505, 314), (635, 314)], "solid", stroke_dash="6,4")}
    {svg_plate_text(595, 301, "&lt;&lt;IPC / WASAPI&gt;&gt;", font_size=8.5, font_weight="bold")}

    <!-- ActionArbiter to User32 SendInput -->
    {vector_polyline_arrow([(480, 644), (555, 644), (555, 470), (635, 470)], "solid", stroke_dash="5,3")}
    {svg_plate_text(595, 457, "&lt;&lt;Win32 SendInput&gt;&gt;", font_size=8.5, font_weight="bold")}

    <!-- ActionArbiter to UI Automation Provider Tree -->
    {vector_polyline_arrow([(480, 624), (530, 624), (530, 590), (635, 590)], "solid", stroke_dash="5,3")}
    {svg_plate_text(595, 577, "&lt;&lt;COM / UIA&gt;&gt;", font_size=8.5, font_weight="bold")}

    <!-- PyQt6 to DWM Compositor -->
    {vector_polyline_arrow([(480, 754), (575, 754), (575, 710), (635, 710)], "solid", stroke_dash="5,3")}
    {svg_plate_text(605, 697, "&lt;&lt;Direct2D HWND&gt;&gt;", font_size=8.5, font_weight="bold")}

    <!-- Legend (Bottom Left) -->
    <rect x="50" y="995" width="550" height="25" fill="#FFFFFF" stroke="#000000" stroke-width="1" />
    <text x="60" y="1012" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#000000">Legend: 3D Box = Device/Node | Inner Box = Execution Environment | Small Square = Hardware Port</text>

    {get_footer("OMG UML 2.5 Standard Semantic Profile | Strict Pure Monochrome Rendering")}
</svg>"""
    return svg

# ==============================================================================
# 5. DATA FLOW DIAGRAM (DFD Level 1)
# ==============================================================================
def generate_dfd_diagram():
    def process_box(x, y, w, h, p_num, p_name, p_sub):
        return f"""
        <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" ry="14" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <line x1="{x}" y1="{y + 32}" x2="{x + w}" y2="{y + 32}" stroke="#000000" stroke-width="1.5" />
        <text x="{x + 20}" y="{y + 22}" font-family="Consolas, monospace" font-size="13" font-weight="bold" fill="#000000">{p_num}</text>
        <text x="{x + w/2 + 10}" y="{y + 22}" font-family="Arial, Helvetica, sans-serif" font-size="11.5" font-style="italic" text-anchor="middle" fill="#000000">Process</text>
        <text x="{x + w/2}" y="{y + 58}" font-family="Arial, Helvetica, sans-serif" font-size="13.5" font-weight="bold" text-anchor="middle" fill="#000000">{p_name}</text>
        <text x="{x + w/2}" y="{y + 78}" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">{p_sub}</text>
        """

    def entity_box(x, y, w, h, e_id, e_name, e_sub):
        return f"""
        <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#000000" stroke-width="2.5" />
        <rect x="{x + 4}" y="{y + 4}" width="{w - 8}" height="{h - 8}" fill="#FFFFFF" stroke="#000000" stroke-width="1" />
        <text x="{x + w/2}" y="{y + 28}" font-family="Consolas, monospace" font-size="13" font-weight="bold" text-anchor="middle" fill="#000000">{e_id}</text>
        <text x="{x + w/2}" y="{y + 54}" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#000000">{e_name}</text>
        <text x="{x + w/2}" y="{y + 74}" font-family="Arial, Helvetica, sans-serif" font-size="11" text-anchor="middle" fill="#000000">{e_sub}</text>
        """

    def datastore_box(x, y, w, h, d_id, d_name, d_sub):
        return f"""
        <line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" stroke="#000000" stroke-width="2" />
        <line x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}" stroke="#000000" stroke-width="2" />
        <line x1="{x}" y1="{y}" x2="{x}" y2="{y + h}" stroke="#000000" stroke-width="2" />
        <line x1="{x + 55}" y1="{y}" x2="{x + 55}" y2="{y + h}" stroke="#000000" stroke-width="1.5" />
        <text x="{x + 28}" y="{y + h/2 + 5}" font-family="Consolas, monospace" font-size="14" font-weight="bold" text-anchor="middle" fill="#000000">{d_id}</text>
        <text x="{x + 70}" y="{y + 26}" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="bold" fill="#000000">{d_name}</text>
        <text x="{x + 70}" y="{y + 46}" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">{d_sub}</text>
        """

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("Data Flow Diagram (DFD Level 1) — Gane &amp; Sarson Information &amp; Signal Pipeline Model", "Gane &amp; Sarson Methodology / ISO 5807", "NOVA-SDLC-DFD-L1-05")}

    <!-- ================= 3x3 ARCHITECTURAL PIPELINE GRID ================= -->

    <!-- ROW 1: Audio Signal Acquisition & Buffer Store -->
    <!-- E2: Microphone Hardware -->
    {entity_box(70, 160, 240, 110, "E2", "USB Microphone", "Analog/Digital Sound Sensor")}

    <!-- Process 1.0: Audio Stream Acquisition -->
    {process_box(410, 160, 330, 120, "1.0", "Audio Stream Acquisition", "Capture 16kHz 16-bit Mono PCM Frames")}

    <!-- Data Store D1: Circular Ring Buffer -->
    {datastore_box(820, 185, 280, 70, "D1", "Circular Audio Buffer", "Sliding In-Memory PCM Buffer")}

    <!-- Process 2.0: Acoustic Impulse Detection -->
    {process_box(1180, 160, 340, 120, "2.0", "Acoustic Impulse Detection", "Bandpass Filter &amp; Energy Spike Analysis")}

    <!-- Row 1 Flows (Direct Horizontal) -->
    {vector_arrow(310, 215, 410, 215, "solid", stroke_width=2)}
    {svg_plate_text(360, 205, "Raw Audio Signal", font_size=10, font_weight="bold")}

    {vector_arrow(740, 220, 820, 220, "solid", stroke_width=2)}
    {svg_plate_text(780, 210, "16kHz PCM", font_size=10, font_weight="bold")}

    {vector_arrow(1100, 220, 1180, 220, "solid", stroke_width=2)}
    {svg_plate_text(1140, 210, "Sliding Audio", font_size=10, font_weight="bold")}

    <!-- ROW 2: Speech Recognition, Arbitration & OS Input -->
    <!-- E1: Operator / User -->
    {entity_box(70, 440, 240, 110, "E1", "Operator / User", "Human Voice &amp; Acoustic Actions")}

    <!-- Process 3.0: Speech Intent Recognition -->
    {process_box(410, 440, 330, 120, "3.0", "Speech Intent Recognition", "Vosk Offline Phoneme Extraction")}

    <!-- Process 4.0: Action Arbitration & Dispatch -->
    {process_box(1180, 440, 340, 120, "4.0", "Action Arbitration &amp; Dispatch", "Temporal Correlation &amp; Input Synthesis")}

    <!-- E3: Windows OS API -->
    {entity_box(1600, 440, 250, 110, "E3", "Windows 11 OS API", "User32 / UI Automation Tree")}

    <!-- Row 2 Flows -->
    {vector_arrow(310, 495, 410, 495, "solid", stroke_width=2)}
    {svg_plate_text(360, 485, "Spoken Utterance", font_size=10, font_weight="bold")}

    <!-- D1 to Process 3.0 (Read Buffered Chunks) -->
    {vector_polyline_arrow([(960, 255), (960, 340), (575, 340), (575, 440)], "solid", stroke_width=2)}
    {svg_plate_text(767, 330, "Buffered Audio Chunks (Read)", font_size=10, font_weight="bold")}

    <!-- Process 2.0 to Process 4.0 (Snap Event - Direct Vertical Drop) -->
    {vector_arrow(1350, 280, 1350, 440, "solid", stroke_width=2)}
    {svg_plate_text(1350, 360, "Impulse Timestamp Event", font_size=10, font_weight="bold")}

    <!-- Process 3.0 to Process 4.0 (Action Token - Direct Horizontal across open center) -->
    {vector_arrow(740, 500, 1180, 500, "solid", stroke_width=2)}
    {svg_plate_text(960, 490, "ActionToken (Parsed Intent)", font_size=10.5, font_weight="bold")}

    <!-- Process 4.0 to E3 (SendInput Click) -->
    {vector_arrow(1520, 475, 1600, 475, "solid", stroke_width=2)}
    {svg_plate_text(1560, 462, "SendInput(Click, Keys)", font_size=9.5, font_weight="bold")}

    <!-- E3 to Process 4.0 (UIA Element Bounds) -->
    {vector_arrow(1600, 530, 1520, 530, "solid", stroke_width=2)}
    {svg_plate_text(1560, 517, "UIA Element Coordinates", font_size=9.5, font_weight="bold")}

    <!-- ROW 3: Configuration, Presentation & Display Feedback -->
    <!-- Data Store D2: Config & Calibration Rules -->
    {datastore_box(410, 740, 330, 70, "D2", "Action &amp; Calibration Rules", "JSON Config / Grammar Token Mappings")}

    <!-- Process 5.0: Mascot HUD Rendering -->
    {process_box(1180, 720, 340, 120, "5.0", "Mascot HUD Rendering", "Direct2D Animation &amp; Crosshair Overlay")}

    <!-- E4: Desktop Window Manager -->
    {entity_box(1600, 720, 250, 110, "E4", "Desktop Window Manager", "DirectX Display Surface &amp; HUD")}

    <!-- Row 3 Flows -->
    <!-- D2 to Process 4.0 (Config Rules) -->
    {vector_polyline_arrow([(740, 775), (960, 775), (960, 540), (1180, 540)], "solid", stroke_width=2)}
    {svg_plate_text(960, 650, "Calibration &amp; Thresholds", font_size=10, font_weight="bold")}

    <!-- Process 4.0 to Process 5.0 (Target Coords & State - Direct Vertical Drop) -->
    {vector_arrow(1350, 560, 1350, 720, "solid", stroke_width=2)}
    {svg_plate_text(1350, 640, "Target Coords &amp; State", font_size=10, font_weight="bold")}

    <!-- Process 5.0 to E4 (Render Direct2D Frames) -->
    {vector_arrow(1520, 775, 1600, 775, "solid", stroke_width=2)}
    {svg_plate_text(1560, 765, "Direct2D Frames", font_size=9.5, font_weight="bold")}

    <!-- Process 5.0 Feedback to Operator E1 (Clean Bottom Channel y=865, Zero Collision) -->
    {vector_polyline_arrow([(1250, 840), (1250, 865), (190, 865), (190, 550)], "solid", stroke_width=2)}
    {svg_plate_text(520, 852, "Visual Mascot Feedback &amp; Audio Confirmation", font_size=10, font_weight="bold")}

    <!-- Legend (Bottom Left) -->
    <rect x="70" y="895" width="460" height="90" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="85" y="915" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="bold" fill="#000000">Gane &amp; Sarson DFD Notation Legend</text>
    <text x="85" y="935" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Double Rect: External Entity (E#) | Rounded Rect: Process Step (#.#)</text>
    <text x="85" y="955" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Open Parallel Lines: Data Store (D#)</text>
    {vector_arrow(85, 972, 145, 972, "solid", stroke_width=2)}
    <text x="155" y="976" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Information / Signal Data Flow Arrow</text>

    {get_footer("Gane &amp; Sarson DFD Methodology | Strict Pure Monochrome Rendering")}
</svg>"""
    return svg

# ==============================================================================
# 6. ENTITY-RELATIONSHIP DIAGRAM
# ==============================================================================
def generate_er_diagram():
    def table_box(x, y, w, h, name, pks, fks, attrs):
        header_h = 36
        svg_t = f"""
        <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#000000" stroke-width="2" />
        <rect x="{x}" y="{y}" width="{w}" height="{header_h}" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
        <text x="{x + w/2}" y="{y + 24}" font-family="Arial, Helvetica, sans-serif" font-size="13.5" font-weight="bold" text-anchor="middle" fill="#000000">{name}</text>
        """
        curr_y = y + header_h + 18
        for pk in pks:
            svg_t += f'<text x="{x + 10}" y="{curr_y}" font-family="Consolas, monospace" font-size="11" font-weight="bold" fill="#000000">PK  {pk}</text>'
            curr_y += 18
        for fk in fks:
            svg_t += f'<text x="{x + 10}" y="{curr_y}" font-family="Consolas, monospace" font-size="11" font-style="italic" fill="#000000">FK  {fk}</text>'
            curr_y += 18
        if pks or fks:
            svg_t += f'<line x1="{x}" y1="{curr_y - 8}" x2="{x + w}" y2="{curr_y - 8}" stroke="#000000" stroke-width="1" />'
            curr_y += 8
        for attr in attrs:
            svg_t += f'<text x="{x + 10}" y="{curr_y}" font-family="Consolas, monospace" font-size="10.5" fill="#000000">    {attr}</text>'
            curr_y += 18
        return svg_t

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
    <rect width="1920" height="1080" fill="#FFFFFF" />
    {get_header("Entity-Relationship (ER) Diagram — Crow's Foot Domain Data Architecture &amp; State Model", "Crow's Foot Notation / ISO/IEC 9075 SQL Standard", "NOVA-SDLC-ERD-CF-06")}

    <!-- ================= 4-COLUMN DOMAIN ENTITY MATRIX ================= -->

    <!-- COLUMN 1: Audio Signal Root (x=70, w=295) -->
    <!-- 1. AudioChunk -->
    {table_box(70, 175, 295, 210, "AudioChunk", ["chunk_id : UUID"], [], [
        "timestamp : Float",
        "sample_rate : Int = 16000",
        "channels : Int = 1",
        "duration_ms : Float",
        "raw_pcm : Bytes"
    ])}

    <!-- COLUMN 2: Acoustic Impulse & UI Target (x=540, w=295) -->
    <!-- 2. AcousticImpulseRecord (Row 1) -->
    {table_box(540, 175, 295, 210, "AcousticImpulseRecord", ["impulse_id : UUID"], ["chunk_id : UUID"], [
        "peak_amplitude : Float",
        "energy_ratio : Float",
        "is_snap_candidate : Bool",
        "detected_timestamp : Float"
    ])}

    <!-- 3. TargetElement (Row 2) -->
    {table_box(540, 480, 295, 230, "TargetElement", ["element_id : UUID"], ["token_id : UUID"], [
        "bounding_x : Int",
        "bounding_y : Int",
        "bounding_width : Int",
        "bounding_height : Int",
        "control_type : String"
    ])}

    <!-- COLUMN 3: Recognition, Action & Runtime Event Backbone (x=1010, w=295) -->
    <!-- 4. SpeechRecognitionResult (Row 1) -->
    {table_box(1010, 175, 295, 210, "SpeechRecognitionResult", ["recognition_id : UUID"], ["chunk_id : UUID"], [
        "raw_text : String",
        "confidence_score : Float",
        "latency_ms : Float",
        "is_final_transcription : Bool"
    ])}

    <!-- 5. ActionToken (Row 2) -->
    {table_box(1010, 480, 295, 230, "ActionToken", ["token_id : UUID"], ["recognition_id : UUID"], [
        "action_type : Enum",
        "target_label : String",
        "execution_status : Enum",
        "created_at : Float"
    ])}

    <!-- 6. SystemEvent (Row 3) -->
    {table_box(1010, 800, 295, 210, "SystemEvent", ["event_id : UUID"], ["token_id : UUID (Nullable)", "profile_id : UUID"], [
        "event_type : String",
        "severity : Enum",
        "payload_json : String",
        "timestamp : Float"
    ])}

    <!-- COLUMN 4: Profile, Calibration & Mascot State Hierarchy (x=1480, w=295) -->
    <!-- 7. ConfigurationProfile (Row 1) -->
    {table_box(1480, 175, 295, 210, "ConfigurationProfile", ["profile_id : UUID"], [], [
        "profile_name : String",
        "mic_device_index : Int",
        "overlay_opacity : Float",
        "is_active : Bool"
    ])}

    <!-- 8. AudioCalibrationProfile (Row 2) -->
    {table_box(1480, 480, 295, 230, "AudioCalibrationProfile", ["calibration_id : UUID"], ["profile_id : UUID"], [
        "impulse_threshold : Float",
        "silence_cutoff_db : Float",
        "frequency_lowpass_hz : Int",
        "updated_at : Float"
    ])}

    <!-- 9. MascotVisualState (Row 3) -->
    {table_box(1480, 800, 295, 210, "MascotVisualState", ["state_id : UUID"], ["event_id : UUID"], [
        "state_name : Enum",
        "current_frame_index : Int",
        "sprite_sheet_path : String",
        "screen_pos_x : Int",
        "screen_pos_y : Int"
    ])}

    <!-- ================= CROW'S FOOT RELATIONSHIP LINES (Explicit Vector Glyphs, 175px Corridor) ================= -->

    <!-- 1. AudioChunk (1) to AcousticImpulseRecord (0..N) - Direct Horizontal -->
    {vector_crows_foot(365, 280, 540, 280, "1", "0..N")}
    {svg_plate_text(452, 266, "evaluates (1 : 0..N)", font_size=9.5, font_weight="bold", pad_y=2)}

    <!-- 2. AudioChunk (1) to SpeechRecognitionResult (0..N) - Top Margin Route -->
    {vector_polyline_crows_foot([(217, 175), (217, 138), (1157, 138), (1157, 175)], "1", "0..N")}
    {svg_plate_text(687, 126, "transcribes (1 : 0..N)", font_size=9.5, font_weight="bold", pad_y=2)}

    <!-- 3. SpeechRecognitionResult (1) to ActionToken (0..1) - Direct Vertical -->
    {vector_crows_foot(1157, 385, 1157, 480, "1", "0..1")}
    {svg_plate_text(1157, 432, "produces (1 : 0..1)", font_size=9.5, font_weight="bold")}

    <!-- 4. ActionToken (1) to TargetElement (0..1) - Direct Horizontal -->
    {vector_crows_foot(1010, 595, 835, 595, "1", "0..1")}
    {svg_plate_text(922, 581, "resolves (1 : 0..1)", font_size=9.5, font_weight="bold", pad_y=2)}

    <!-- 5. ActionToken (1) to SystemEvent (0..N) - Direct Vertical -->
    {vector_crows_foot(1157, 710, 1157, 800, "1", "0..N")}
    {svg_plate_text(1157, 755, "triggers (1 : 0..N)", font_size=9.5, font_weight="bold")}

    <!-- 6. SystemEvent (1) to MascotVisualState (1..N) - Direct Horizontal -->
    {vector_crows_foot(1305, 905, 1480, 905, "1", "1..N")}
    {svg_plate_text(1392, 891, "drives (1 : 1..N)", font_size=9.5, font_weight="bold", pad_y=2)}

    <!-- 7. ConfigurationProfile (1) to AudioCalibrationProfile (1 : 1) - Direct Vertical -->
    {vector_crows_foot(1627, 385, 1627, 480, "1", "1")}
    {svg_plate_text(1627, 432, "configures (1 : 1)", font_size=9.5, font_weight="bold")}

    <!-- 8. ConfigurationProfile (1) to SystemEvent (0..N) - Channel x=1392 Route -->
    {vector_polyline_crows_foot([(1480, 310), (1392, 310), (1392, 850), (1305, 850)], "1", "0..N")}
    {svg_plate_text(1392, 755, "logs profile events (1 : 0..N)", font_size=9.5, font_weight="bold")}

    <!-- Legend (Bottom Left) -->
    <rect x="70" y="875" width="450" height="110" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" />
    <text x="85" y="895" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="bold" fill="#000000">Crow's Foot Notation &amp; Cardinality Legend</text>
    {vector_crows_foot(85, 925, 155, 925, "1", "1")}
    <text x="170" y="930" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">Exactly One to Exactly One (1 : 1)</text>
    {vector_crows_foot(85, 955, 155, 955, "1", "1..N")}
    <text x="170" y="960" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">One to Mandatory Many (1 : 1..N)</text>
    {vector_crows_foot(85, 975, 155, 975, "1", "0..N")}
    <text x="170" y="980" font-family="Arial, Helvetica, sans-serif" font-size="10.5" fill="#000000">One to Optional Many / Zero or More (1 : 0..N)</text>

    {get_footer("ISO/IEC 9075 Data Model Standard | Crow's Foot Physical Architecture")}
</svg>"""
    return svg

# ==============================================================================
# PIPELINE EXECUTION
# ==============================================================================
DIAGRAM_MAP = {
    "NOVA_Use_Case_Diagram": generate_use_case_diagram,
    "NOVA_Class_Diagram": generate_class_diagram,
    "NOVA_Sequence_Diagram": generate_sequence_diagram,
    "NOVA_Deployment_Diagram": generate_deployment_diagram,
    "NOVA_Data_Flow_Diagram_DFD": generate_dfd_diagram,
    "NOVA_Entity_Relationship_Diagram": generate_er_diagram
}

def generate_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    print("================================================================================")
    print("NOVA DESKTOP COMPANION — SDLC PHASE 2 DESIGN DIAGRAM GENERATOR")
    print("Strict Pure Monochrome Standard: #FFFFFF Background | #000000 Vector Lines")
    print("Zero-Marker Vector Engine: All Glyphs, Diamonds, Arrows & Crows Feet are True Vectors")
    print("================================================================================")

    for name, gen_fn in DIAGRAM_MAP.items():
        svg_content = gen_fn()
        svg_path = os.path.join(OUTPUT_DIR, f"{name}.svg")
        pdf_path = os.path.join(OUTPUT_DIR, f"{name}.pdf")
        png_scratch = os.path.join(SCRATCH_DIR, f"{name}.png")

        # 1. Write SVG
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"[OK] SVG Generated: {svg_path}")

        # 2. Render to Vector PDF via PyMuPDF
        doc = fitz.open()
        svg_bytes = svg_content.encode("utf-8")
        svg_doc = fitz.open(stream=svg_bytes, filetype="svg")
        pdf_bytes = svg_doc.convert_to_pdf()
        svg_doc.close()

        pdf_doc = fitz.open("pdf", pdf_bytes)
        doc.insert_pdf(pdf_doc)
        pdf_doc.close()
        doc.save(pdf_path)
        doc.close()
        print(f"[OK] PDF Generated: {pdf_path}")

        # 3. High-res verification PNG in scratch
        v_doc = fitz.open(pdf_path)
        page = v_doc[0]
        pix = page.get_pixmap(dpi=200)
        pix.save(png_scratch)
        v_doc.close()
        print(f"[OK] Scratch PNG Verified: {png_scratch}")

    print("================================================================================")
    print("All 6 SDLC Phase 2 Design Diagrams successfully regenerated & verified!")
    print("================================================================================")

if __name__ == "__main__":
    generate_all()
