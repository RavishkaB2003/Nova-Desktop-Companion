#!/usr/bin/env python3
"""
scripts/generate_architecture_diagrams.py
Project NOVA - Architectural Diagram Generator (ISO/IEC/IEEE 42010 & C4 Model Standards)

Generates 3 publication-grade vector architectural diagrams in 16:9 Widescreen (1920x1080):
1. C4 Level 1: System Context Diagram (High-Level Architecture for Executives & General Public)
2. C4 Level 2/3: Container & Concurrency Component Diagram (System Architecture for Engineers)
3. C4 Dynamic & UML 2.5: Component Workings & Operational Dataflow Pipeline Diagram

Compiles both raw .svg files and native vector .pdf files using PyMuPDF (fitz) into Documentation/diagrams/.
"""

import os
import re
from pathlib import Path
import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "Documentation" / "diagrams"
MASCOT_DIR = REPO_ROOT / "assets" / "mascot"

# NOVA High-Contrast Obsidian Cyberpunk Color Tokens (WCAG 2.2 AAA Compliant)
C_BG = "#060A12"              # Canvas deep obsidian
C_CARD_BG = "#0B111E"         # Primary card background
C_CARD_SURFACE = "#121A2B"    # Inner container surface
C_BORDER_SUBTLE = "#1E2A40"   # Neutral border
C_CYAN = "#00F0FF"            # Primary system accent
C_CYAN_GLOW = "#00F0FF33"     # Subtle glow
C_EMERALD = "#00FF9D"         # Hardware / Active state accent
C_AMBER = "#FFB800"           # Warning / Transition / Gating accent
C_PURPLE = "#A78BFA"          # Concurrency / Thread accent
C_ROSE = "#FB7185"            # Safety / Emergency accent
C_TEXT_WHITE = "#FFFFFF"      # High-contrast primary text
C_TEXT_MUTED = "#94A3B8"      # Secondary descriptive text
C_TEXT_DIM = "#64748B"        # Micro metadata text

FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, sans-serif"
FONT_MONO = "Cascadia Code, Consolas, Courier New, monospace"


def extract_mascot_svg_content(filename: str) -> str:
    """Extract inner SVG nodes from an asset mascot SVG file for clean embedding."""
    svg_path = MASCOT_DIR / filename
    if not svg_path.exists():
        return ""
    content = svg_path.read_text(encoding="utf-8")
    # Remove XML declaration and outer <svg> wrapper to embed inside a <g>
    content = re.sub(r"<\?xml.*?\?>", "", content)
    content = re.sub(r"<!DOCTYPE.*?>", "", content)
    m = re.search(r"<svg[^>]*>(.*?)</svg>", content, re.DOTALL)
    if m:
        return m.group(1)
    return ""


def build_header_svg(title: str, subtitle: str, standard_tag: str, doc_id: str) -> str:
    """Build standardized ISO/IEC/IEEE 42010 header with C4 classification."""
    return f"""
    <!-- Master Header -->
    <rect x="40" y="30" width="1840" height="90" rx="12" fill="{C_CARD_BG}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    
    <!-- Title & Subtitle -->
    <text x="70" y="68" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="24" font-weight="700" letter-spacing="0.5">PROJECT NOVA</text>
    <text x="245" y="68" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="24" font-weight="600">| {title}</text>
    <text x="70" y="98" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="14">{subtitle}</text>
    
    <!-- Standards & Metadata Badges -->
    <g transform="translate(1420, 48)">
      <rect x="0" y="0" width="220" height="28" rx="6" fill="#132338" stroke="{C_CYAN}" stroke-width="1" />
      <text x="110" y="19" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="11" font-weight="600" text-anchor="middle">{standard_tag}</text>
      
      <rect x="235" y="0" width="195" height="28" rx="6" fill="#182232" stroke="{C_BORDER_SUBTLE}" stroke-width="1" />
      <text x="332" y="19" fill="{C_TEXT_MUTED}" font-family="{FONT_MONO}" font-size="11" text-anchor="middle">DOC: {doc_id} | v1.0.0</text>
    </g>
    """


def build_legend_svg(x: int, y: int, items: list) -> str:
    """Build standardized C4/UML visual notation legend in bottom corner."""
    width = 460
    height = 36 + len(items) * 22
    lines = [
        f'<g transform="translate({x}, {y})">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="10" fill="{C_CARD_BG}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />',
        f'<text x="20" y="24" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="12" font-weight="700" letter-spacing="0.5">NOTATION &amp; ARCHITECTURAL KEY</text>',
    ]
    cur_y = 46
    for shape, color, label in items:
        if shape == "person":
            lines.append(f'<circle cx="28" cy="{cur_y-4}" r="5" fill="none" stroke="{color}" stroke-width="2"/>')
            lines.append(f'<path d="M 20 {cur_y+6} C 20 {cur_y+1}, 36 {cur_y+1}, 36 {cur_y+6}" fill="none" stroke="{color}" stroke-width="2"/>')
        elif shape == "rect":
            lines.append(f'<rect x="20" y="{cur_y-9}" width="16" height="12" rx="2" fill="{color}" opacity="0.8"/>')
        elif shape == "rect_border":
            lines.append(f'<rect x="20" y="{cur_y-9}" width="16" height="12" rx="2" fill="none" stroke="{color}" stroke-width="2"/>')
        elif shape == "dashed_border":
            lines.append(f'<rect x="20" y="{cur_y-9}" width="16" height="12" rx="2" fill="none" stroke="{color}" stroke-width="1.5" stroke-dasharray="3 2"/>')
        elif shape == "arrow":
            lines.append(f'<line x1="18" y1="{cur_y-3}" x2="38" y2="{cur_y-3}" stroke="{color}" stroke-width="2" marker-end="url(#arrow_{color.replace("#","")})"/>')
        lines.append(f'<text x="48" y="{cur_y}" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">{label}</text>')
        cur_y += 22
    lines.append('</g>')
    return "\n".join(lines)


def generate_diagram_1_svg() -> str:
    """Generate C4 Level 1 System Context Diagram (High-Level Architecture)."""
    mascot_svg = extract_mascot_svg_content("mascot_listening.svg")
    
    legend_items = [
        ("person", C_CYAN, "[Person] Hands-Free Human Operator"),
        ("rect_border", C_CYAN, "[Software System] Project NOVA Secure Edge Boundary"),
        ("rect", C_CARD_SURFACE, "[Container / Engine] Internal Processing Subsystem"),
        ("rect_border", C_BORDER_SUBTLE, "[External System / Host] Windows OS & Applications"),
        ("arrow", C_CYAN, "Natural Language / Hardware Input Vector"),
        ("arrow", C_EMERALD, "Win32 Control & UIAutomation Inspection Vector"),
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
  <defs>
    <linearGradient id="bg_grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050811" />
      <stop offset="100%" stop-color="#080E1A" />
    </linearGradient>
    <linearGradient id="system_grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0D1626" />
      <stop offset="100%" stop-color="#080D17" />
    </linearGradient>
    <marker id="arrow_cyan" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_CYAN}" />
    </marker>
    <marker id="arrow_emerald" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_EMERALD}" />
    </marker>
    <marker id="arrow_amber" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_AMBER}" />
    </marker>
    <marker id="arrow_00F0FF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_CYAN}" />
    </marker>
    <marker id="arrow_00FF9D" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_EMERALD}" />
    </marker>
  </defs>

  <!-- Canvas Background -->
  <rect width="1920" height="1080" fill="url(#bg_grad)" />

  {build_header_svg(
      "High-Level Architecture (C4 Context Model)",
      "Executive &amp; Systems Context: 100% Offline Edge Appliance Boundary, Multi-Modal Input, and Windows Desktop Ecosystem",
      "C4 MODEL: LEVEL 1 SYSTEM CONTEXT",
      "C4-CTX-001"
  )}

  <!-- ==================== LEFT COLUMN: HUMAN OPERATOR ==================== -->
  <g transform="translate(60, 160)">
    <!-- Actor Box -->
    <rect x="0" y="0" width="360" height="660" rx="16" fill="{C_CARD_BG}" stroke="{C_CYAN}" stroke-width="2" />
    <rect x="20" y="20" width="130" height="26" rx="6" fill="#0E2838" />
    <text x="85" y="37" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">[PERSON : ACTOR]</text>
    <text x="24" y="80" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="22" font-weight="700">Hands-Free Operator</text>
    <text x="24" y="106" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="13">Individual with severe motor impairment requiring complete hands-free desktop navigation</text>

    <!-- Modality Card 1: Spoken Speech -->
    <rect x="20" y="150" width="320" height="130" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <circle cx="50" cy="180" r="14" fill="#0C2538" stroke="{C_CYAN}" stroke-width="1.5"/>
    <text x="50" y="185" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700" text-anchor="middle">🎙️</text>
    <text x="75" y="184" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">Natural Voice Commands</text>
    <text x="32" y="215" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">50+ commands ("Tag", "Click", "Crosshair", "Type", "Scroll", "Open Browser")</text>
    <text x="32" y="245" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">Latency: ~50-80ms | 16kHz PCM</text>

    <!-- Modality Card 2: Acoustic Impulses -->
    <rect x="20" y="300" width="320" height="130" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <circle cx="50" cy="330" r="14" fill="#0B2B28" stroke="{C_EMERALD}" stroke-width="1.5"/>
    <text x="50" y="335" fill="{C_EMERALD}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700" text-anchor="middle">💥</text>
    <text x="75" y="334" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">Acoustic Mouth Clicks</text>
    <text x="32" y="365" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">High-frequency (>3kHz) tongue pops and non-verbal clicks for instant cursor halt &amp; lock</text>
    <text x="32" y="395" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">Latency: &lt;25ms | Plosive Gated</text>

    <!-- Modality Card 3: Emergency Physical Stop -->
    <rect x="20" y="450" width="320" height="120" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <circle cx="50" cy="480" r="14" fill="#32141D" stroke="{C_ROSE}" stroke-width="1.5"/>
    <text x="50" y="485" fill="{C_ROSE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700" text-anchor="middle">🛑</text>
    <text x="75" y="484" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">Physical Emergency Stop</text>
    <text x="32" y="515" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Global Win32 hardware keys: ESC or Ctrl+Shift+Q</text>
    <text x="32" y="542" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11">Fail-Closed: Monotonic Invalidation</text>

    <!-- Status badge -->
    <rect x="20" y="595" width="320" height="42" rx="8" fill="#101828" stroke="{C_CYAN}" stroke-width="1" stroke-dasharray="3 2" />
    <text x="180" y="621" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="12" font-weight="600" text-anchor="middle">Zero Hands, Keyboard or Mouse Required</text>
  </g>

  <!-- ==================== CENTER SYSTEM BOUNDARY (PROJECT NOVA) ==================== -->
  <g transform="translate(490, 160)">
    <!-- Boundary Box -->
    <rect x="0" y="0" width="870" height="850" rx="20" fill="url(#system_grad)" stroke="{C_CYAN}" stroke-width="2.5" />
    <rect x="28" y="-14" width="380" height="28" rx="6" fill="#0C1B2F" stroke="{C_CYAN}" stroke-width="1.5" />
    <text x="218" y="5" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="12" font-weight="700" text-anchor="middle">[SOFTWARE SYSTEM : 100% OFFLINE EDGE FORTRESS]</text>
    
    <text x="40" y="48" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="24" font-weight="800">Project NOVA Desktop Companion</text>
    <text x="40" y="74" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="13">Zero Network Egress | RAM-Only Ephemeral Processing | Local Vosk Kaldi ASR Engine | Monotonic Safety Arbiter</text>

    <!-- Sub-container 1: Audio DSP & Speech Engine -->
    <rect x="35" y="100" width="480" height="220" rx="14" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="55" y="130" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="16" font-weight="700">1. Offline Speech &amp; DSP Core</text>
    <text x="55" y="152" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Zero-Cloud, Embedded Kaldi &amp; Scipy Pipeline</text>
    
    <rect x="55" y="170" width="205" height="65" rx="8" fill="#0A111F" stroke="{C_BORDER_SUBTLE}" stroke-width="1" />
    <text x="65" y="193" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Vosk Kaldi Engine</text>
    <text x="65" y="212" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="10">80+ Token Grammar Model</text>
    <text x="65" y="226" fill="{C_TEXT_MUTED}" font-family="{FONT_MONO}" font-size="10">Sub-80ms Spotting Latency</text>

    <rect x="280" y="170" width="215" height="65" rx="8" fill="#0A111F" stroke="{C_BORDER_SUBTLE}" stroke-width="1" />
    <text x="290" y="193" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Acoustic DSP Core</text>
    <text x="290" y="212" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">3-8kHz Bandpass Filter</text>
    <text x="290" y="226" fill="{C_TEXT_MUTED}" font-family="{FONT_MONO}" font-size="10">&lt;25ms Transient Click Detector</text>

    <rect x="55" y="245" width="440" height="58" rx="8" fill="#0A111F" stroke="{C_AMBER}" stroke-width="1" stroke-dasharray="2 2" />
    <text x="70" y="268" fill="{C_AMBER}" font-family="{FONT_FAMILY}" font-size="12" font-weight="700">Acoustic Playback Ducking Gate (Anti-Self-Triggering)</text>
    <text x="70" y="286" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Mutes microphone stream during TTS/Chime audio feedback to eliminate echo loops</text>

    <!-- Sub-container 2: State Coordinator & Safety Arbiter -->
    <rect x="535" y="100" width="300" height="220" rx="14" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="555" y="130" fill="{C_PURPLE}" font-family="{FONT_FAMILY}" font-size="16" font-weight="700">2. Safety &amp; State Arbiter</text>
    <text x="555" y="152" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Monotonic Action Generation Invalidation</text>
    
    <rect x="555" y="170" width="260" height="60" rx="8" fill="#141028" stroke="{C_PURPLE}" stroke-width="1" />
    <text x="570" y="193" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">10-State Thread-Safe FSM</text>
    <text x="570" y="214" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11">STANDBY -> IDLE -> TRACKING</text>

    <rect x="555" y="240" width="260" height="65" rx="8" fill="#1F0D15" stroke="{C_ROSE}" stroke-width="1" />
    <text x="570" y="262" fill="{C_ROSE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Monotonic ActionArbiter</text>
    <text x="570" y="281" fill="{C_TEXT_WHITE}" font-family="{FONT_MONO}" font-size="10">Generation Token Check (FR-022)</text>
    <text x="570" y="295" fill="{C_TEXT_MUTED}" font-family="{FONT_MONO}" font-size="10">Atomic Invalidation on Halt / ESC</text>

    <!-- Sub-container 3: Multi-Modal Output & Glanceable HUD Presentation -->
    <rect x="35" y="340" width="800" height="480" rx="14" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="55" y="375" fill="{C_EMERALD}" font-family="{FONT_FAMILY}" font-size="18" font-weight="700">3. Multi-Modal Visual Output &amp; Assistance Surfaces</text>
    <text x="55" y="398" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="13">Non-intrusive, Per-Monitor-V2 DPI transparent overlays projecting actionable guidance onto the Windows desktop</text>

    <!-- UI Surface A: Target Snapping Badges -->
    <rect x="55" y="420" width="350" height="180" rx="10" fill="#0A111F" stroke="{C_CYAN}" stroke-width="1.5" />
    <text x="75" y="450" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">🎯 Tag &amp; Snap Overlay</text>
    <text x="75" y="475" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Spoken "Tag" crawls foreground window elements</text>
    
    <!-- Mini Badges 1, 2, 3 Illustration -->
    <g transform="translate(75, 495)">
      <rect x="0" y="0" width="44" height="28" rx="4" fill="#050811" stroke="{C_CYAN}" stroke-width="2" />
      <text x="22" y="20" fill="#FFFFFF" font-family="{FONT_FAMILY}" font-size="16" font-weight="800" text-anchor="middle">1</text>
      
      <rect x="55" y="0" width="44" height="28" rx="4" fill="#050811" stroke="{C_CYAN}" stroke-width="2" />
      <text x="77" y="20" fill="#FFFFFF" font-family="{FONT_FAMILY}" font-size="16" font-weight="800" text-anchor="middle">2</text>
      
      <rect x="110" y="0" width="44" height="28" rx="4" fill="#050811" stroke="{C_AMBER}" stroke-width="2" />
      <text x="132" y="20" fill="#FFFFFF" font-family="{FONT_FAMILY}" font-size="16" font-weight="800" text-anchor="middle">3</text>
      <text x="170" y="20" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="11">← Aimed</text>
    </g>
    <text x="75" y="550" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Numbered badges (1-9) over buttons, inputs, links</text>
    <text x="75" y="570" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">18.5:1 Contrast Ratio (WCAG AAA)</text>

    <!-- UI Surface B: Dual-Axis Laser Crosshair -->
    <rect x="425" y="420" width="390" height="180" rx="10" fill="#0A111F" stroke="{C_EMERALD}" stroke-width="1.5" />
    <text x="445" y="450" fill="{C_EMERALD}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">🔴 Dual-Axis Laser Crosshair</text>
    <text x="445" y="475" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Pixel-precision targeting for legacy canvas &amp; games</text>
    
    <!-- Mini Crosshair Grid Illustration -->
    <g transform="translate(445, 495)">
      <rect x="0" y="0" width="130" height="85" rx="6" fill="#050811" stroke="{C_BORDER_SUBTLE}" stroke-width="1"/>
      <line x1="0" y1="42" x2="130" y2="42" stroke="{C_EMERALD}" stroke-width="2" stroke-dasharray="4 2"/>
      <line x1="65" y1="0" x2="65" y2="85" stroke="{C_EMERALD}" stroke-width="2"/>
      <circle cx="65" cy="42" r="8" fill="none" stroke="{C_CYAN}" stroke-width="2"/>
      <text x="145" y="30" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="11" font-weight="600">Phase 1: Lock Y</text>
      <text x="145" y="50" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="11" font-weight="600">Phase 2: Lock X &amp; Hit</text>
      <text x="145" y="70" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">Sweep: 180 px/sec</text>
    </g>

    <!-- UI Surface C: Mascot Desktop Companion (Embedded Vector Graphic) -->
    <rect x="55" y="620" width="760" height="180" rx="10" fill="#0E182A" stroke="{C_CYAN}" stroke-width="1.5" />
    
    <!-- Embedded SVG Mascot Preview -->
    <g transform="translate(70, 610) scale(0.65)">
      {mascot_svg}
    </g>
    
    <g transform="translate(250, 635)">
      <text x="0" y="24" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="18" font-weight="800">Glanceable Desktop Companion ("Nova")</text>
      <text x="0" y="48" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13">256×256 Transparent Floating Canvas at Bottom-Right of Desktop Screen</text>
      <text x="0" y="72" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Provides constant, non-intrusive peripheral awareness of system listening, tracking, and executing states</text>
      <g transform="translate(0, 95)">
        <rect x="0" y="0" width="80" height="24" rx="4" fill="#132338" stroke="{C_CYAN}" stroke-width="1"/>
        <text x="40" y="16" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="10" font-weight="600" text-anchor="middle">SLEEPING</text>
        
        <rect x="90" y="0" width="80" height="24" rx="4" fill="#132820" stroke="{C_EMERALD}" stroke-width="1"/>
        <text x="130" y="16" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10" font-weight="600" text-anchor="middle">LISTENING</text>
        
        <rect x="180" y="0" width="80" height="24" rx="4" fill="#2E2010" stroke="{C_AMBER}" stroke-width="1"/>
        <text x="220" y="16" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="10" font-weight="600" text-anchor="middle">TRACKING</text>
        
        <rect x="270" y="0" width="85" height="24" rx="4" fill="#2B1020" stroke="{C_ROSE}" stroke-width="1"/>
        <text x="312" y="16" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="10" font-weight="600" text-anchor="middle">EXECUTING</text>
        
        <rect x="365" y="0" width="80" height="24" rx="4" fill="#1D1230" stroke="{C_PURPLE}" stroke-width="1"/>
        <text x="405" y="16" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="10" font-weight="600" text-anchor="middle">DICTATING</text>
      </g>
    </g>
  </g>

  <!-- ==================== RIGHT COLUMN: HOST & TARGET SYSTEMS ==================== -->
  <g transform="translate(1420, 160)">
    <!-- External Boundary Box -->
    <rect x="0" y="0" width="440" height="520" rx="16" fill="{C_CARD_BG}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <rect x="20" y="20" width="220" height="26" rx="6" fill="#1A2436" />
    <text x="130" y="37" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">[EXTERNAL HOST ENVIRONMENT]</text>
    <text x="24" y="80" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="20" font-weight="700">Windows 10 / 11 64-bit</text>
    <text x="24" y="104" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="13">Host Operating System, Desktop Subsystems &amp; Target Applications</text>

    <!-- External Node 1: Audio Input Driver -->
    <rect x="20" y="130" width="400" height="90" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="40" y="158" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Audio Hardware &amp; Driver Layer</text>
    <text x="40" y="180" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">Microphone Array / USB Input via WASAPI &amp; PortAudio</text>
    <text x="40" y="202" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">Standard 16kHz 16-bit Mono PCM Streams</text>

    <!-- External Node 2: Win32 OS Subsystems -->
    <rect x="20" y="240" width="400" height="120" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="40" y="268" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Windows Subsystem APIs</text>
    <text x="40" y="292" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Windows UIAutomation COM Tree Client</text>
    <text x="40" y="312" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Win32 SendInput Hardware Cursor Injection</text>
    <text x="40" y="332" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• RegisterHotKey Global Keyboard Hooks</text>
    <text x="40" y="350" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">Per-Monitor-V2 DPI Coordinate Transformation</text>

    <!-- External Node 3: Target Applications -->
    <rect x="20" y="380" width="400" height="115" rx="10" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5" />
    <text x="40" y="408" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Target Desktop Applications</text>
    <text x="40" y="432" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Web Browsers (Chrome / Edge with pre-warmed DOM)</text>
    <text x="40" y="452" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Desktop Productivity (File Explorer, Office, Terminal)</text>
    <text x="40" y="472" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Canvas &amp; Game Interfaces (via Crosshair &amp; Glider)</text>
  </g>

  <!-- ==================== INTER-SYSTEM CONNECTORS & ARROWS ==================== -->
  <!-- User to Audio HW -->
  <path d="M 420 220 L 490 220" fill="none" stroke="{C_CYAN}" stroke-width="2.5" marker-end="url(#arrow_cyan)"/>
  <text x="455" y="210" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">Voice</text>

  <path d="M 420 365 L 490 365" fill="none" stroke="{C_EMERALD}" stroke-width="2.5" marker-end="url(#arrow_emerald)"/>
  <text x="455" y="355" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">Clicks</text>

  <path d="M 420 510 L 490 510" fill="none" stroke="{C_ROSE}" stroke-width="2.5" marker-end="url(#arrow_amber)"/>
  <text x="455" y="500" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">ESC</text>

  <!-- NOVA to Windows OS -->
  <path d="M 1360 480 L 1420 480" fill="none" stroke="{C_EMERALD}" stroke-width="2.5" marker-end="url(#arrow_emerald)"/>
  <text x="1390" y="470" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">Clicks</text>

  <path d="M 1360 300 L 1420 300" fill="none" stroke="{C_CYAN}" stroke-width="2.5" marker-end="url(#arrow_cyan)"/>
  <text x="1390" y="290" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">UIA Tree</text>

  <!-- ==================== LEGEND ==================== -->
  {build_legend_svg(1420, 710, legend_items)}

</svg>"""


def generate_diagram_2_svg() -> str:
    """Generate C4 Level 2/3 Container & Concurrency Component Diagram (System Architecture)."""
    legend_items = [
        ("rect_border", C_CYAN, "[Container Boundary] nova.exe Python 3.10 x64 Process"),
        ("dashed_border", C_PURPLE, "[Concurrency Lane] Thread Isolation Boundary"),
        ("rect", C_CARD_SURFACE, "[Modular Component] Subsystem Class / Controller"),
        ("arrow", C_CYAN, "Asynchronous Thread-Safe Inter-Thread Queue"),
        ("arrow", C_EMERALD, "Win32 OS Native API Bridge (SendInput, UIA COM)"),
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
  <defs>
    <linearGradient id="bg_grad2" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050811" />
      <stop offset="100%" stop-color="#080E1A" />
    </linearGradient>
    <marker id="arrow_c2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_CYAN}" />
    </marker>
    <marker id="arrow_e2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_EMERALD}" />
    </marker>
    <marker id="arrow_p2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_PURPLE}" />
    </marker>
  </defs>

  <rect width="1920" height="1080" fill="url(#bg_grad2)" />

  {build_header_svg(
      "System-Level Concurrency & Component Architecture",
      "C4 Level 2/3 &amp; UML 2.5: 3-Thread Concurrency Topology, Hardware Audio Ingestion, MTA COM Worker, and Win32 Subsystems",
      "C4 MODEL: LEVEL 2/3 CONTAINER &amp; COMPONENT",
      "C4-SYS-002"
  )}

  <!-- Top Hardware & Win32 Integration Bar -->
  <g transform="translate(60, 140)">
    <rect x="0" y="0" width="1800" height="60" rx="10" fill="{C_CARD_BG}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
    <text x="30" y="35" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">Windows 10/11 x64 Subsystem &amp; Hardware Layer:</text>
    
    <rect x="420" y="14" width="280" height="32" rx="6" fill="#141E30" stroke="{C_CYAN}" stroke-width="1"/>
    <text x="560" y="35" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="12" text-anchor="middle">WASAPI / PortAudio (16kHz Mono)</text>
    
    <rect x="730" y="14" width="290" height="32" rx="6" fill="#15241E" stroke="{C_EMERALD}" stroke-width="1"/>
    <text x="875" y="35" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="12" text-anchor="middle">UIAutomation COM (Foreground Tree)</text>

    <rect x="1050" y="14" width="280" height="32" rx="6" fill="#201524" stroke="{C_PURPLE}" stroke-width="1"/>
    <text x="1190" y="35" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="12" text-anchor="middle">Win32 SendInput (Hardware Cursor)</text>

    <rect x="1360" y="14" width="280" height="32" rx="6" fill="#241518" stroke="{C_ROSE}" stroke-width="1"/>
    <text x="1500" y="35" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="12" text-anchor="middle">RegisterHotKey (ESC / Ctrl+Shift+Q)</text>
  </g>

  <!-- ==================== CONTAINER: nova.exe ==================== -->
  <g transform="translate(60, 220)">
    <rect x="0" y="0" width="1800" height="740" rx="16" fill="#080D18" stroke="{C_CYAN}" stroke-width="2" />
    <rect x="30" y="-14" width="340" height="28" rx="6" fill="#0E1D30" stroke="{C_CYAN}" stroke-width="1.5" />
    <text x="200" y="5" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="12" font-weight="700" text-anchor="middle">[CONTAINER : nova.exe Python 3.10 x64 Process]</text>

    <!-- ==================== LANE 1: THREAD 1 (AUDIO STREAM) ==================== -->
    <g transform="translate(30, 30)">
      <rect x="0" y="0" width="460" height="680" rx="12" fill="{C_CARD_BG}" stroke="{C_CYAN}" stroke-width="1.5" stroke-dasharray="4 2"/>
      <rect x="20" y="16" width="420" height="30" rx="6" fill="#0E2232" />
      <text x="230" y="36" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700" text-anchor="middle">THREAD 1: AUDIO STREAM (Hardware Priority)</text>
      <text x="230" y="65" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11" text-anchor="middle">sounddevice / PortAudio Callback @ 16kHz | 100ms Chunks</text>

      <!-- Component 1.1: AudioCaptureManager -->
      <rect x="20" y="85" width="420" height="135" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="112" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">AudioCaptureManager</text>
      <text x="40" y="132" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">nova.audio.capture</text>
      <text x="40" y="156" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Selects physical microphone array (filters virtual drivers)</text>
      <text x="40" y="174" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Manages ring buffer queue (maxsize=50 chunks / 5.0s)</text>
      <text x="40" y="192" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Ephemeral RAM-only ingestion (zero disk persistence)</text>

      <!-- Component 1.2: AcousticImpulseDetector -->
      <rect x="20" y="235" width="420" height="145" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="262" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">AcousticImpulseDetector</text>
      <text x="40" y="282" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">nova.audio.dsp (Sub-25ms Transient Click)</text>
      <text x="40" y="306" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Scipy Butterworth 3kHz-8kHz 2nd order bandpass</text>
      <text x="40" y="324" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Exponential Moving Average (EMA) noise floor tracking</text>
      <text x="40" y="342" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Plosive Gating: 150ms post-vocal mute window</text>
      <text x="40" y="360" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Refractory debounce: 100ms click suppression</text>

      <!-- Component 1.3: VoicedPitchTracker -->
      <rect x="20" y="395" width="420" height="120" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="422" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">VoicedPitchTracker</text>
      <text x="40" y="442" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11">nova.audio.dsp (Continuous Vowel Gliding)</text>
      <text x="40" y="466" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Normalized Autocorrelation Function (NACF) 80-500Hz</text>
      <text x="40" y="484" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Correlation threshold r_max >= 0.65; sustained >150ms</text>
      <text x="40" y="502" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Active strictly during SystemState.GLIDE_ACTIVE</text>

      <!-- Component 1.4: AudioDuckingManager -->
      <rect x="20" y="530" width="420" height="125" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_AMBER}" stroke-width="1" stroke-dasharray="2 2"/>
      <text x="40" y="557" fill="{C_AMBER}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">AudioDuckingManager &amp; Synthesizer</text>
      <text x="40" y="577" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="11">nova.audio.ducking (Core Audio COM)</text>
      <text x="40" y="601" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Windows IAudioEndpointVolume master audio attenuation</text>
      <text x="40" y="619" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• HarmonicChimeSynthesizer (Hann envelope without clicks)</text>
      <text x="40" y="637" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Drops mic chunks when SAPI5/Chime is speaking</text>
    </g>

    <!-- ==================== LANE 2: THREAD 2 (WORKER & COORDINATOR) ==================== -->
    <g transform="translate(520, 30)">
      <rect x="0" y="0" width="680" height="680" rx="12" fill="{C_CARD_BG}" stroke="{C_EMERALD}" stroke-width="1.5" stroke-dasharray="4 2"/>
      <rect x="20" y="16" width="640" height="30" rx="6" fill="#0C261C" />
      <text x="340" y="36" fill="{C_EMERALD}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700" text-anchor="middle">THREAD 2: WORKER &amp; COORDINATOR (MTA COM Apartment)</text>
      <text x="340" y="65" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11" text-anchor="middle">CoInitializeEx(COINIT_MULTITHREADED) | Zero Windows Message Pump Deadlock</text>

      <!-- Component 2.1: Speech Engines -->
      <rect x="20" y="85" width="310" height="150" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="35" y="112" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">VoskSpeechEngine</text>
      <text x="35" y="132" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">nova.speech.vosk_engine</text>
      <text x="35" y="156" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Kaldi grammar-constrained ASR</text>
      <text x="35" y="174" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• 80+ spoken commands decoded</text>
      <text x="35" y="192" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Word confidence gating (>=0.65)</text>
      <text x="35" y="210" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Instant partial spotting for "Halt"</text>

      <rect x="350" y="85" width="310" height="150" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="365" y="112" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">DictationPipeline</text>
      <text x="365" y="132" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11">nova.speech.dictation_pipeline</text>
      <text x="365" y="156" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Unconstrained Kaldi language model</text>
      <text x="365" y="174" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Silence-pause detector (>3.0s)</text>
      <text x="365" y="192" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• 1.5s arming grace period</text>
      <text x="365" y="210" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• In-flight text injection via SendInput</text>

      <!-- Component 2.2: TagSnapCoordinator -->
      <rect x="20" y="250" width="640" height="180" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_EMERALD}" stroke-width="1.5"/>
      <text x="40" y="278" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="15" font-weight="700">TagSnapCoordinator</text>
      <text x="40" y="298" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">nova.core.coordinator (Central Intent Router &amp; Action Dispatcher)</text>
      <text x="40" y="324" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Routes spoken phrases into action intents: Tag, Crosshair, Glider, Scroller, Shortcuts</text>
      <text x="40" y="344" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Manages target badge pagination (pages of 9 targets) with modifier debounce</text>
      <text x="40" y="364" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Executes pre-click target re-validation (window handle and bounding box &lt;= 5px tolerance)</text>
      <text x="40" y="384" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Integrates SAPI5 speech synthesis voice feedback ("Tagging", "Locked", "Ready")</text>
      <text x="40" y="404" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="12">• Marshals UI and cursor updates to Thread 3 via thread-safe root.after() callbacks</text>

      <!-- Component 2.3: UIAutomationCrawler & SystemShortcutManager -->
      <rect x="20" y="445" width="310" height="210" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="35" y="472" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">UIAutomationCrawler</text>
      <text x="35" y="492" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">nova.automation.crawler</text>
      <text x="35" y="516" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• &lt;35ms foreground UIA tree walker</text>
      <text x="35" y="534" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Chromium DOM activation wake-up</text>
      <text x="35" y="552" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Filters non-clickable elements</text>
      <text x="35" y="570" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Calculates high-precision centroids</text>
      <text x="35" y="588" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Caches active pages of targets</text>
      <text x="35" y="606" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Tier-2 Vision contour fallback</text>

      <!-- Component 2.4: SafetyCoordinator & ActionArbiter -->
      <rect x="350" y="445" width="310" height="210" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_ROSE}" stroke-width="1.5"/>
      <text x="365" y="472" fill="{C_ROSE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Safety &amp; Action Arbiter</text>
      <text x="365" y="492" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11">nova.core.safety</text>
      <text x="365" y="516" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="11">• ActionArbiter (Monotonic Generation G)</text>
      <text x="365" y="534" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• ActionToken minting &amp; validation</text>
      <text x="365" y="552" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Stale token rejection before click</text>
      <text x="365" y="570" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Multi-subsystem cancellation hooks</text>
      <text x="365" y="588" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Emergency halt forces reset to STANDBY</text>
      <text x="365" y="606" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Zero persistent PII retention (PRIV-002)</text>
    </g>

    <!-- ==================== LANE 3: THREAD 3 (GUI & WIN32 LOOP) ==================== -->
    <g transform="translate(1230, 30)">
      <rect x="0" y="0" width="540" height="680" rx="12" fill="{C_CARD_BG}" stroke="{C_PURPLE}" stroke-width="1.5" stroke-dasharray="4 2"/>
      <rect x="20" y="16" width="500" height="30" rx="6" fill="#20122E" />
      <text x="270" y="36" fill="{C_PURPLE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700" text-anchor="middle">THREAD 3: GUI &amp; MESSAGE LOOP (Tkinter Single STA)</text>
      <text x="270" y="65" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11" text-anchor="middle">Single root.mainloop() | Per-Monitor-V2 DPI Context | Win32 GDI Overlays</text>

      <!-- Component 3.1: MascotWidget & HudOverlay -->
      <rect x="20" y="85" width="500" height="135" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="112" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">MascotWidget &amp; Overlays (Tkinter Canvas)</text>
      <text x="40" y="132" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">nova.ui.mascot &amp; nova.ui.hud_overlay</text>
      <text x="40" y="156" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• MascotWidget: 256×256 colorkey #010203 transparency, 7 vector SVG states</text>
      <text x="40" y="174" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• HudOverlay: Fullscreen WS_EX_LAYERED | WS_EX_TRANSPARENT target badges</text>
      <text x="40" y="192" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• CrosshairOverlay: Sweeping dual-axis #00FF9D laser reticle (180 px/s)</text>

      <!-- Component 3.2: InputDriver -->
      <rect x="20" y="235" width="500" height="145" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_PURPLE}" stroke-width="1.5"/>
      <text x="40" y="262" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">InputDriver (Win32 SendInput Bridge)</text>
      <text x="40" y="282" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11">nova.input.driver</text>
      <text x="40" y="306" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• 78ms non-blocking cursor glide (5 steps x ~15.6ms native WM_TIMER ticks)</text>
      <text x="40" y="324" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Virtual desktop metric bounds checking (SM_CXVIRTUALSCREEN)</text>
      <text x="40" y="342" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Executes click modifiers: Left, Right, Double, Triple, Middle click</text>
      <text x="40" y="360" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Monotonic generation token verification before click commit</text>

      <!-- Component 3.3: Motion & Wheel Controllers -->
      <rect x="20" y="395" width="500" height="120" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="422" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">ContinuousGlider &amp; ScrollController</text>
      <text x="40" y="442" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">nova.core.glider &amp; nova.input.scroll_controller</text>
      <text x="40" y="466" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• ContinuousGlider: 200 px/s heading vector motion with boundary clamping</text>
      <text x="40" y="484" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• ScrollController: 25 FPS fluid mouse wheel injection (15 delta units/tick)</text>
      <text x="40" y="502" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Voice velocity modulation: "Faster", "Slower", "Up", "Down", "Stop"</text>

      <!-- Component 3.4: GlobalHotkeyManager & Tray -->
      <rect x="20" y="530" width="500" height="125" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.5"/>
      <text x="40" y="557" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">GlobalHotkeyManager &amp; NovaTrayIcon</text>
      <text x="40" y="577" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11">nova.core.safety &amp; nova.ui.tray</text>
      <text x="40" y="601" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Native Win32 message loop intercepting global ESC and Ctrl+Shift+Q</text>
      <text x="40" y="619" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• Unregisters all hotkeys cleanly on exit without orphaned hooks (SEC-005)</text>
      <text x="40" y="637" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">• pystray notification area daemon for background dormant operation</text>
    </g>

    <!-- Inter-Thread Queues & Communication Visuals -->
    <path d="M 490 150 L 520 150" fill="none" stroke="{C_CYAN}" stroke-width="2.5" marker-end="url(#arrow_c2)"/>
    <text x="505" y="140" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">PCM</text>

    <path d="M 490 280 L 520 280" fill="none" stroke="{C_EMERALD}" stroke-width="2.5" marker-end="url(#arrow_e2)"/>
    <text x="505" y="270" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">Click</text>

    <path d="M 1200 340 L 1230 340" fill="none" stroke="{C_PURPLE}" stroke-width="2.5" marker-end="url(#arrow_p2)"/>
    <text x="1215" y="330" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="10" text-anchor="middle">UI Task</text>
  </g>

  <!-- Legend -->
  {build_legend_svg(1390, 970, legend_items)}

</svg>"""


def generate_diagram_3_svg() -> str:
    """Generate C4 Dynamic & UML 2.5 Operational Pipeline Diagram (Component Workings)."""
    legend_items = [
        ("rect", "#0E1A2C", "Pipeline Swimlane / Functional Sequence Boundary"),
        ("rect_border", C_CYAN, "Step Action Block with Sequence Order (e.g. 1.0 -> 1.8)"),
        ("arrow", C_CYAN, "Primary Dataflow / Asynchronous Action Sequence"),
        ("arrow", C_EMERALD, "Hardware Execution / State Modification Commit"),
        ("arrow", C_ROSE, "Emergency Override / Invalidation Circuit"),
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
  <defs>
    <linearGradient id="bg_grad3" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#050811" />
      <stop offset="100%" stop-color="#080E1A" />
    </linearGradient>
    <marker id="arrow_d3" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_CYAN}" />
    </marker>
    <marker id="arrow_e3" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_EMERALD}" />
    </marker>
    <marker id="arrow_r3" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
      <polygon points="0 1, 7 4, 0 7" fill="{C_ROSE}" />
    </marker>
  </defs>

  <rect width="1920" height="1080" fill="url(#bg_grad3)" />

  {build_header_svg(
      "Component Workings &amp; End-to-End Operational Pipelines",
      "C4 Dynamic &amp; UML 2.5 Sequence: Step-by-Step Dataflows Across All 5 Execution Pipelines (Tag &amp; Snap, Crosshair, Glider, Ducking, Safety)",
      "C4 DYNAMIC &amp; UML 2.5 RUNTIME VIEW",
      "C4-DYN-003"
  )}

  <!-- ==================== PIPELINE 1: TAG & SNAP ==================== -->
  <g transform="translate(60, 140)">
    <rect x="0" y="0" width="1800" height="150" rx="12" fill="{C_CARD_BG}" stroke="{C_CYAN}" stroke-width="1.5"/>
    <rect x="20" y="-12" width="310" height="24" rx="4" fill="#0E2334" stroke="{C_CYAN}" stroke-width="1"/>
    <text x="175" y="4" fill="{C_CYAN}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">PIPELINE 1: TAG &amp; SNAP TARGET NAVIGATION</text>

    <!-- Steps 1.0 to 1.6 -->
    <!-- 1.0 Spoken Tag -->
    <rect x="25" y="25" width="200" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="35" y="48" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.0 User Trigger</text>
    <text x="35" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Spoken "Tag" / "Scan"</text>
    <text x="35" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Captured via WASAPI 16kHz</text>
    <text x="35" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Vosk spots keyword</text>

    <path d="M 225 77 L 260 77" fill="none" stroke="{C_CYAN}" stroke-width="2" marker-end="url(#arrow_d3)"/>

    <!-- 1.1 UIA Crawl -->
    <rect x="260" y="25" width="225" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="270" y="48" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.1 UIA Crawl (&lt;35ms)</text>
    <text x="270" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">UIAutomation Scan</text>
    <text x="270" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Wakes Chromium DOM tree</text>
    <text x="270" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Gathers actionable centroids</text>

    <path d="M 485 77 L 520 77" fill="none" stroke="{C_CYAN}" stroke-width="2" marker-end="url(#arrow_d3)"/>

    <!-- 1.2 HUD Projection -->
    <rect x="520" y="25" width="225" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="530" y="48" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.2 HUD Overlay Projection</text>
    <text x="530" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Badges 1–9 Overlaid</text>
    <text x="530" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">High-contrast obsidian badges</text>
    <text x="530" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">State transitions to TRACKING</text>

    <path d="M 745 77 L 780 77" fill="none" stroke="{C_CYAN}" stroke-width="2" marker-end="url(#arrow_d3)"/>

    <!-- 1.3 Target Selection -->
    <rect x="780" y="25" width="225" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="790" y="48" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.3 Spoken Digit ("3")</text>
    <text x="790" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Target Aimed &amp; Amber</text>
    <text x="790" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Badge 3 locks amber (#FFB800)</text>
    <text x="790" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Audio chime confirmation</text>

    <path d="M 1005 77 L 1040 77" fill="none" stroke="{C_CYAN}" stroke-width="2" marker-end="url(#arrow_d3)"/>

    <!-- 1.4 Pre-Click Revalidation -->
    <rect x="1040" y="25" width="225" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="1050" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.4 Pre-Click Re-validation</text>
    <text x="1050" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Stale Target Check</text>
    <text x="1050" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Re-verifies HWND &amp; centroid</text>
    <text x="1050" y="110" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">Pass: Delta &lt;= 5px tolerance</text>

    <path d="M 1265 77 L 1300 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 1.5 78ms Glide & SendInput -->
    <rect x="1300" y="25" width="240" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="1310" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.5 78ms Non-Blocking Glide</text>
    <text x="1310" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Win32 SendInput Click</text>
    <text x="1310" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">5-step smooth interpolation</text>
    <text x="1310" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Fires Left/Right/Double click</text>

    <path d="M 1540 77 L 1575 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 1.6 Feedback & Dismiss -->
    <rect x="1575" y="25" width="200" height="105" rx="8" fill="#0D201A" stroke="{C_EMERALD}" stroke-width="1.5"/>
    <text x="1585" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">1.6 Feedback &amp; Reset</text>
    <text x="1585" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Mascot Nod &amp; Clear</text>
    <text x="1585" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Badges dismissed</text>
    <text x="1585" y="110" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">Return to IDLE_ACTIVE</text>
  </g>

  <!-- ==================== PIPELINE 2: DUAL-AXIS CROSSHAIR ==================== -->
  <g transform="translate(60, 310)">
    <rect x="0" y="0" width="1800" height="150" rx="12" fill="{C_CARD_BG}" stroke="{C_EMERALD}" stroke-width="1.5"/>
    <rect x="20" y="-12" width="340" height="24" rx="4" fill="#0C251C" stroke="{C_EMERALD}" stroke-width="1"/>
    <text x="190" y="4" fill="{C_EMERALD}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">PIPELINE 2: DUAL-AXIS CROSSHAIR LASER SCANNER</text>

    <!-- 2.0 Trigger -->
    <rect x="25" y="25" width="250" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="35" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">2.0 Spoken Trigger</text>
    <text x="35" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">"Crosshair" / "Laser"</text>
    <text x="35" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Transitions to CROSSHAIR_ACTIVE</text>
    <text x="35" y="110" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Mascot enters TRACKING</text>

    <path d="M 275 77 L 320 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 2.1 Phase 1 Horizontal Sweep -->
    <rect x="320" y="25" width="310" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="330" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">2.1 Phase 1: Horizontal Laser Sweep</text>
    <text x="330" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Y-Axis Sweeping at 180 px/s</text>
    <text x="330" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Full virtual desktop height traversal</text>
    <text x="330" y="110" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">Spoken "Up" / "Down" reverses direction</text>

    <path d="M 630 77 L 675 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 2.2 Lock Y -->
    <rect x="675" y="25" width="280" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="685" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">2.2 Vocal "Lock" / Mouth Click</text>
    <text x="685" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Y Coordinate Frozen</text>
    <text x="685" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">&lt;25ms acoustic impulse detector</text>
    <text x="685" y="110" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">Horizontal line fixed; Phase 2 armed</text>

    <path d="M 955 77 L 1000 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 2.3 Phase 2 Vertical Sweep -->
    <rect x="1000" y="25" width="310" height="105" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="1010" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">2.3 Phase 2: Vertical Laser Sweep</text>
    <text x="1010" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">X-Axis Sweeping across Screen</text>
    <text x="1010" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Vertical laser line sweeps across display</text>
    <text x="1010" y="110" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">Spoken "Left" / "Right" reverses direction</text>

    <path d="M 1310 77 L 1355 77" fill="none" stroke="{C_EMERALD}" stroke-width="2" marker-end="url(#arrow_e3)"/>

    <!-- 2.4 Lock X & Magnetic Snap -->
    <rect x="1355" y="25" width="420" height="105" rx="8" fill="#0D201A" stroke="{C_EMERALD}" stroke-width="1.5"/>
    <text x="1370" y="48" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11" font-weight="700">2.4 Vocal "Hit" / Click -&gt; Snap &amp; Commit</text>
    <text x="1370" y="70" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Magnetic Snap &amp; Primary Click</text>
    <text x="1370" y="92" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Magnetic snap pulls to nearest clickable element within 65px gravity radius</text>
    <text x="1370" y="110" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">Win32 SendInput clicks target; Overlays dismiss cleanly</text>
  </g>

  <!-- ==================== PIPELINE 3: CONTINUOUS GLIDER ==================== -->
  <g transform="translate(60, 480)">
    <rect x="0" y="0" width="1800" height="140" rx="12" fill="{C_CARD_BG}" stroke="{C_PURPLE}" stroke-width="1.5"/>
    <rect x="20" y="-12" width="340" height="24" rx="4" fill="#1C1428" stroke="{C_PURPLE}" stroke-width="1"/>
    <text x="190" y="4" fill="{C_PURPLE}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">PIPELINE 3: CONTINUOUS CURSOR GLIDER &amp; NUDGING</text>

    <!-- 3.0 Spoken Glide -->
    <rect x="25" y="22" width="320" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="35" y="44" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">3.0 Glide Activation</text>
    <text x="35" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">"Glide [Direction]" or Vowel Hum</text>
    <text x="35" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Sets heading vector (0°/90°/180°/270°)</text>
    <text x="35" y="104" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Arms pitch tracker (NACF 80-500Hz)</text>

    <path d="M 345 71 L 390 71" fill="none" stroke="{C_PURPLE}" stroke-width="2" marker-end="url(#arrow_p2)"/>

    <!-- 3.1 200px/s Vector Motion -->
    <rect x="390" y="22" width="360" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="400" y="44" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">3.1 Continuous Vector Motion</text>
    <text x="400" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Smooth 200 px/s Velocity</text>
    <text x="400" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Tkinter animation loop (16ms ticks / ~60 FPS)</text>
    <text x="400" y="104" fill="{C_CYAN}" font-family="{FONT_MONO}" font-size="11">Spoken "Left"/"Right"/"Up"/"Down" steers heading</text>

    <path d="M 750 71 L 795 71" fill="none" stroke="{C_PURPLE}" stroke-width="2" marker-end="url(#arrow_p2)"/>

    <!-- 3.2 Kinetic Momentum -->
    <rect x="795" y="22" width="340" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="805" y="44" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">3.2 Kinetic Momentum Nudging</text>
    <text x="805" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Discrete Voice Steps &amp; Multipliers</text>
    <text x="805" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">"Nudge" (18px), Step (65px), "Jump" (160px)</text>
    <text x="805" y="104" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11">Repeated words stack momentum: 1.0x -> 2.0x -> 3.5x</text>

    <path d="M 1135 71 L 1180 71" fill="none" stroke="{C_PURPLE}" stroke-width="2" marker-end="url(#arrow_p2)"/>

    <!-- 3.3 Halt & Click -->
    <rect x="1180" y="22" width="595" height="98" rx="8" fill="#1B1228" stroke="{C_PURPLE}" stroke-width="1.5"/>
    <text x="1195" y="44" fill="{C_PURPLE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">3.3 Instant Halt / Boundary Clamp</text>
    <text x="1195" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="14" font-weight="700">Mouth Click or "Stop" -> Immediate Halt</text>
    <text x="1195" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Virtual screen boundary clamping prevents cursor escape on multi-monitor setups</text>
    <text x="1195" y="104" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="11">Spoken "Hit" or mouth click halts and immediately executes primary mouse click</text>
  </g>

  <!-- ==================== PIPELINE 4: AUDIO DUCKING & ECHO GATE ==================== -->
  <g transform="translate(60, 640)">
    <rect x="0" y="0" width="880" height="140" rx="12" fill="{C_CARD_BG}" stroke="{C_AMBER}" stroke-width="1.5"/>
    <rect x="20" y="-12" width="310" height="24" rx="4" fill="#2E2010" stroke="{C_AMBER}" stroke-width="1"/>
    <text x="175" y="4" fill="{C_AMBER}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">PIPELINE 4: AUDIO DUCKING &amp; ECHO GATE</text>

    <rect x="20" y="22" width="260" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="30" y="44" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="11" font-weight="700">4.0 Audio Playback Trigger</text>
    <text x="30" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">TTS / Chime Active</text>
    <text x="30" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">SAPI5 speech or harmonic chime</text>
    <text x="30" y="104" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Sets is_speaking = True</text>

    <path d="M 280 71 L 310 71" fill="none" stroke="{C_AMBER}" stroke-width="2" marker-end="url(#arrow_c2)"/>

    <rect x="310" y="22" width="260" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="320" y="44" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="11" font-weight="700">4.1 Ducking Gate Engaged</text>
    <text x="320" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Microphone Ingestion Mute</text>
    <text x="320" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Audio pipeline drops PCM chunks</text>
    <text x="320" y="104" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="10">Prevents acoustic self-triggering</text>

    <path d="M 570 71 L 600 71" fill="none" stroke="{C_AMBER}" stroke-width="2" marker-end="url(#arrow_c2)"/>

    <rect x="600" y="22" width="260" height="98" rx="8" fill="#1C160B" stroke="{C_AMBER}" stroke-width="1.5"/>
    <text x="610" y="44" fill="{C_AMBER}" font-family="{FONT_MONO}" font-size="11" font-weight="700">4.2 Clean Restoration</text>
    <text x="610" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Vosk Recognizer Reset</text>
    <text x="610" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Discards partial audio artifacts</text>
    <text x="610" y="104" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">Restores listening cleanly</text>
  </g>

  <!-- ==================== PIPELINE 5: FAIL-CLOSED SAFETY CIRCUIT ==================== -->
  <g transform="translate(980, 640)">
    <rect x="0" y="0" width="880" height="140" rx="12" fill="{C_CARD_BG}" stroke="{C_ROSE}" stroke-width="1.5"/>
    <rect x="20" y="-12" width="340" height="24" rx="4" fill="#2E1018" stroke="{C_ROSE}" stroke-width="1"/>
    <text x="190" y="4" fill="{C_ROSE}" font-family="{FONT_FAMILY}" font-size="11" font-weight="700" text-anchor="middle">PIPELINE 5: FAIL-CLOSED MONOTONIC SAFETY CIRCUIT</text>

    <rect x="20" y="22" width="260" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="30" y="44" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">5.0 Emergency Trigger</text>
    <text x="30" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Vocal "Halt" or ESC Key</text>
    <text x="30" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">Partial Vosk match or RegisterHotKey</text>
    <text x="30" y="104" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="10">Highest priority system intercept</text>

    <path d="M 280 71 L 310 71" fill="none" stroke="{C_ROSE}" stroke-width="2" marker-end="url(#arrow_r3)"/>

    <rect x="310" y="22" width="260" height="98" rx="8" fill="{C_CARD_SURFACE}" stroke="{C_BORDER_SUBTLE}" stroke-width="1.2"/>
    <text x="320" y="44" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">5.1 Monotonic Bump</text>
    <text x="320" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Generation G -> G+1</text>
    <text x="320" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">ActionArbiter invalidates all tokens</text>
    <text x="320" y="104" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="10">Pending cursor/click tasks dropped</text>

    <path d="M 570 71 L 600 71" fill="none" stroke="{C_ROSE}" stroke-width="2" marker-end="url(#arrow_r3)"/>

    <rect x="600" y="22" width="260" height="98" rx="8" fill="#240D15" stroke="{C_ROSE}" stroke-width="1.5"/>
    <text x="610" y="44" fill="{C_ROSE}" font-family="{FONT_MONO}" font-size="11" font-weight="700">5.2 Immediate Reset</text>
    <text x="610" y="66" fill="{C_TEXT_WHITE}" font-family="{FONT_FAMILY}" font-size="13" font-weight="700">Dismiss All Overlays</text>
    <text x="610" y="86" fill="{C_TEXT_MUTED}" font-family="{FONT_FAMILY}" font-size="11">HUD, Crosshair, Glider cancelled</text>
    <text x="610" y="104" fill="{C_EMERALD}" font-family="{FONT_MONO}" font-size="10">State resets to STANDBY / IDLE</text>
  </g>

  <!-- ==================== LEGEND ==================== -->
  {build_legend_svg(1390, 800, legend_items)}

</svg>"""


def compile_svg_to_pdf(svg_content: str, output_pdf_path: Path, output_svg_path: Path):
    """Save the raw SVG and compile it into a pristine vector PDF using PyMuPDF."""
    output_svg_path.write_text(svg_content, encoding="utf-8")
    print(f"[+] Saved SVG: {output_svg_path.name} ({output_svg_path.stat().st_size} bytes)")

    svg_doc = fitz.open("svg", svg_content.encode("utf-8"))
    pdf_bytes = svg_doc.convert_to_pdf()
    pdf_doc = fitz.open("pdf", pdf_bytes)
    pdf_doc.save(output_pdf_path)
    pdf_doc.close()
    svg_doc.close()
    print(f"[+] Compiled Vector PDF: {output_pdf_path.name} ({output_pdf_path.stat().st_size} bytes)")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("Project NOVA - Architecture Diagram & Vector PDF Generation")
    print("Standards: C4 Model (Levels 1-3), ISO/IEC/IEEE 42010, UML 2.5")
    print("=" * 70)

    # 1. Diagram 1: High-Level C4 System Context
    d1_svg = generate_diagram_1_svg()
    compile_svg_to_pdf(
        d1_svg,
        OUTPUT_DIR / "NOVA_High_Level_Architecture.pdf",
        OUTPUT_DIR / "NOVA_High_Level_Architecture.svg",
    )

    # 2. Diagram 2: System-Level C4 Container & Concurrency Component
    d2_svg = generate_diagram_2_svg()
    compile_svg_to_pdf(
        d2_svg,
        OUTPUT_DIR / "NOVA_System_Architecture.pdf",
        OUTPUT_DIR / "NOVA_System_Architecture.svg",
    )

    # 3. Diagram 3: Component Workings C4 Dynamic & UML 2.5 Operational Pipeline
    d3_svg = generate_diagram_3_svg()
    compile_svg_to_pdf(
        d3_svg,
        OUTPUT_DIR / "NOVA_Component_Workings.pdf",
        OUTPUT_DIR / "NOVA_Component_Workings.svg",
    )

    print("=" * 70)
    print(f"All 3 architectural diagrams and PDFs successfully generated in: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
