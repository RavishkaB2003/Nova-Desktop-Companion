"""
Project NOVA - Control Panel & Command Cheat Sheet Window
Provides a sleek, accessible, high-contrast dashboard displaying live system status,
quick user settings, and a categorized voice command cheat sheet.
Triggerable via spoken 'menu', 'help', 'commands', or mascot double-click.
"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Design tokens matching DESIGN.md
BG_COLOR = "#0A0E17"          # Deep obsidian background
SURFACE_COLOR = "#121824"     # Card surface
CARD_BORDER = "#1E293B"       # Subtle border
ACCENT_CYAN = "#00F0FF"       # Neon cyan
ACCENT_GREEN = "#00FF9D"      # Neon emerald
TEXT_PRIMARY = "#FFFFFF"      # High-contrast white
TEXT_SECONDARY = "#94A3B8"    # Muted slate text
TEXT_MUTED = "#64748B"        # Dim description text
TAG_BG = "#1A2234"            # Chip background


COMMAND_CATEGORIES = [
    {
        "title": "💤 Wake & Sleep Commands",
        "color": "#A78BFA",
        "commands": [
            ("activate", "Pop up companion from background tray (stands by sleeping)"),
            ("hey nova / wake up", "Awaken companion to active listening mode"),
            ("sleep / go to sleep", "Put companion into low-power standby mode"),
            ("deactivate", "Auto-sleep and hide companion back to background tray"),
        ],
    },

    {
        "title": "🎯 Targeting & Badges ('Tag & Snap')",
        "color": ACCENT_CYAN,
        "commands": [
            ("tag / scan", "Project numbered badges over all clickable UI elements"),
            ("one .. nine (1-9)", "Snap cursor directly to target badge and click"),
            ("next / more / back", "Navigate forward or backward through target pages"),
            ("close tags / dismiss", "Close target badges without clicking"),
        ],
    },
    {
        "title": "🖱️ Mouse Clicks & Modifiers",
        "color": ACCENT_GREEN,
        "commands": [
            ("click", "Immediate left mouse click at current cursor position"),
            ("double click", "Execute left double-click at current position"),
            ("right click", "Execute right-click (opens context menu)"),
        ],
    },
    {
        "title": "🔴 Dual-Axis Laser Crosshair",
        "color": "#FF5C5C",
        "commands": [
            ("laser / cross hair", "Launch dual-axis high-visibility scanning laser"),
            ("lock", "Freeze horizontal Y-sweep; start vertical X-sweep"),
            ("hit", "Freeze vertical sweep, snap cursor to reticle, and click"),
        ],
    },
    {
        "title": "🧭 Continuous Cursor Glider",
        "color": "#38BDF8",
        "commands": [
            ("glide / move", "Start continuous cursor motion at 200 px/sec"),
            ("left / right / up / down", "Dynamically change glider movement heading"),
            ("stop / halt", "Immediately freeze cursor glider motion"),
        ],
    },
    {
        "title": "📜 Fluid Mouse Wheel Scrolling",
        "color": "#FBBF24",
        "commands": [
            ("scroll down / scroll", "Start continuous gentle downward page scroll"),
            ("scroll up", "Start continuous gentle upward page scroll"),
            ("faster / slower", "Dynamically adjust scrolling velocity"),
            ("stop / halt", "Immediately freeze page scrolling"),
        ],
    },
    {
        "title": "✍️ Free-Text Voice Dictation",
        "color": "#F472B6",
        "commands": [
            ("type / dictate", "Enter unconstrained voice-to-text typing mode"),
            ("<spoken words>", "Inserts recognized speech into focused text field"),
            ("space / enter / delete", "Inject space, newline, or backspace keystroke"),
            ("done", "Finish voice dictation and return to command mode"),
        ],
    },
    {
        "title": "🚀 Applications & Window Shortcuts",
        "color": "#34D399",
        "commands": [
            ("open browser", "Launch default web browser (Edge / Chrome)"),
            ("open paint", "Launch MS Paint canvas"),
            ("open explorer", "Launch Windows File Explorer (This PC)"),
            ("open youtube", "Open YouTube homepage"),
            ("play on youtube <query>", "Search YouTube for specified search query"),
            ("switch window", "Alt + Tab between open application windows"),
            ("close window", "Alt + F4 close currently active window"),
            ("show desktop", "Win + D minimize all windows to reveal desktop"),
        ],
    },
    {
        "title": "📍 Precision Cursor Nudges",
        "color": "#60A5FA",
        "commands": [
            ("nudge up / down / left / right", "Micro-step cursor by 18 pixels"),
            ("step up / down / left / right", "Standard step cursor by 65 pixels"),
            ("jump up / down / left / right", "Large leap cursor by 160 pixels"),
        ],
    },
    {
        "title": "🛑 Safety & Emergency Overrides",
        "color": "#EF4444",
        "commands": [
            ("halt / cancel", "Instant voice cancellation across all subsystems"),
            ("Escape (Physical Key)", "Global hardware emergency stop -> Sleep"),
            ("Ctrl + Shift + Q (Key)", "Secondary global emergency reset to Standby"),
        ],
    },
]


class ControlPanel:
    """
    Project NOVA Main Application Control Panel and Keyword Cheatsheet window.
    Runs on the main Tkinter thread.
    """

    def __init__(
        self,
        root: tk.Tk,
        on_close: Optional[Callable[[], None]] = None,
        on_feedback_toggle: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self.root = root
        self.on_close_callback = on_close
        self.on_feedback_toggle = on_feedback_toggle

        self._window: Optional[tk.Toplevel] = None
        self._tts_toggle_btn: Optional[tk.Button] = None
        self._is_visible = False
        self._voice_feedback_enabled = True
        self._status_var = tk.StringVar(value="Active: IDLE_ACTIVE")

    def toggle_feedback(self) -> bool:
        """Toggle spoken audio TTS feedback on/off."""
        self._voice_feedback_enabled = not self._voice_feedback_enabled
        if self._tts_toggle_btn is not None:
            try:
                if self._voice_feedback_enabled:
                    self._tts_toggle_btn.config(text="🔊 Voice TTS: ON", fg=TEXT_PRIMARY, bg="#1E293B")
                else:
                    self._tts_toggle_btn.config(text="🔇 Voice TTS: OFF", fg=TEXT_MUTED, bg="#0F172A")
            except Exception:
                pass
        if self.on_feedback_toggle:
            self.on_feedback_toggle(self._voice_feedback_enabled)
        return self._voice_feedback_enabled

    _toggle_feedback = toggle_feedback

    @property
    def is_visible(self) -> bool:
        return self._is_visible and self._window is not None

    def update_status(self, state_name: str) -> None:
        """Update live system state display."""
        clean_name = state_name.replace("SystemState.", "")
        self._status_var.set(f"System State: {clean_name}")

    def show(self) -> None:
        """Display the Control Panel window."""
        if self._window is not None:
            try:
                self._window.deiconify()
                self._window.lift()
                self._window.focus_force()
                self._is_visible = True
                return
            except Exception:
                self._window = None

        self._create_window()
        self._is_visible = True

    def hide(self) -> None:
        """Hide the Control Panel window."""
        if self._window is not None:
            try:
                self._window.withdraw()
            except Exception:
                pass
        self._is_visible = False
        if self.on_close_callback:
            self.on_close_callback()

    def toggle(self) -> None:
        """Toggle visibility between shown and hidden."""
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def _create_window(self) -> None:
        """Build and style the Control Panel UI."""
        win = tk.Toplevel(self.root)
        self._window = win
        win.title("Project NOVA — Control Panel & Command Cheat Sheet")
        win.geometry("780x680")
        win.minsize(640, 520)
        win.configure(bg=BG_COLOR)

        # Intercept window close button [X]
        win.protocol("WM_DELETE_WINDOW", self.hide)
        # Bind Escape key to close
        win.bind("<Escape>", lambda e: self.hide())

        # Center on screen
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"+{x}+{y}")

        # --- Top Header Bar ---
        header_frame = tk.Frame(win, bg=BG_COLOR, padx=24, pady=16)
        header_frame.pack(fill=tk.X)

        title_row = tk.Frame(header_frame, bg=BG_COLOR)
        title_row.pack(fill=tk.X)

        logo_label = tk.Label(
            title_row,
            text="PROJECT NOVA",
            font=("Segoe UI", 16, "bold"),
            fg=ACCENT_CYAN,
            bg=BG_COLOR,
        )
        logo_label.pack(side=tk.LEFT)

        badge_label = tk.Label(
            title_row,
            text=" ASSISTIVE DESKTOP COMPANION ",
            font=("Segoe UI", 9, "bold"),
            fg="#0A0E17",
            bg=ACCENT_GREEN,
            padx=6,
            pady=2,
        )
        badge_label.pack(side=tk.LEFT, padx=12)

        close_btn = tk.Button(
            title_row,
            text=" ✕ ",
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_SECONDARY,
            bg=SURFACE_COLOR,
            activeforeground=TEXT_PRIMARY,
            activebackground="#E11D48",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=self.hide,
        )
        close_btn.pack(side=tk.RIGHT)

        subtitle_label = tk.Label(
            header_frame,
            text="Voice Command Reference & Runtime Settings. Say 'close menu' or press Esc to dismiss.",
            font=("Segoe UI", 10),
            fg=TEXT_SECONDARY,
            bg=BG_COLOR,
        )
        subtitle_label.pack(anchor=tk.W, pady=(4, 0))

        # --- Status & Quick Settings Bar ---
        status_bar = tk.Frame(win, bg=SURFACE_COLOR, padx=24, pady=10, relief=tk.FLAT, highlightbackground=CARD_BORDER, highlightthickness=1)
        status_bar.pack(fill=tk.X, padx=20, pady=(0, 12))

        status_display = tk.Label(
            status_bar,
            textvariable=self._status_var,
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT_GREEN,
            bg=SURFACE_COLOR,
        )
        status_display.pack(side=tk.LEFT)

        tts_toggle_btn = tk.Button(
            status_bar,
            text="🔊 Voice TTS: ON",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_PRIMARY,
            bg="#1E293B",
            activebackground="#334155",
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
        )

        self._tts_toggle_btn = tts_toggle_btn
        tts_toggle_btn.config(command=self.toggle_feedback)
        tts_toggle_btn.pack(side=tk.RIGHT)

        # --- Scrollable Command Cheatsheet Area ---
        container = tk.Frame(win, bg=BG_COLOR)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 12))

        canvas = tk.Canvas(container, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_content = tk.Frame(canvas, bg=BG_COLOR)

        scroll_content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas_frame = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfig(canvas_frame, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(xscrollcommand=None, yscrollcommand=scrollbar.set)

        # Mousewheel scrolling scoped cleanly to canvas hover (F-19)
        def _on_mousewheel(event: tk.Event) -> None:
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _bind_mousewheel(event: tk.Event) -> None:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event: tk.Event) -> None:
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Populate Categorized Cards ---
        for cat in COMMAND_CATEGORIES:
            card = tk.Frame(
                scroll_content,
                bg=SURFACE_COLOR,
                padx=16,
                pady=12,
                highlightbackground=CARD_BORDER,
                highlightthickness=1,
            )
            card.pack(fill=tk.X, pady=6)

            cat_title = tk.Label(
                card,
                text=cat["title"],
                font=("Segoe UI", 11, "bold"),
                fg=cat["color"],
                bg=SURFACE_COLOR,
            )
            cat_title.pack(anchor=tk.W, pady=(0, 8))

            for phrase, desc in cat["commands"]:
                row = tk.Frame(card, bg=SURFACE_COLOR)
                row.pack(fill=tk.X, pady=3)

                chip = tk.Label(
                    row,
                    text=f'  "{phrase}"  ',
                    font=("Consolas", 10, "bold"),
                    fg=ACCENT_CYAN,
                    bg=TAG_BG,
                    padx=4,
                    pady=2,
                )
                chip.pack(side=tk.LEFT)

                desc_label = tk.Label(
                    row,
                    text=f"—  {desc}",
                    font=("Segoe UI", 9),
                    fg=TEXT_SECONDARY,
                    bg=SURFACE_COLOR,
                )
                desc_label.pack(side=tk.LEFT, padx=8)

        # --- Bottom Action Footer ---
        footer_frame = tk.Frame(win, bg=BG_COLOR, padx=24, pady=12)
        footer_frame.pack(fill=tk.X)

        dismiss_btn = tk.Button(
            footer_frame,
            text="Close Cheatsheet (Esc)",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_PRIMARY,
            bg="#2563EB",
            activebackground="#1D4ED8",
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            command=self.hide,
        )
        dismiss_btn.pack(side=tk.RIGHT)

        hint_label = tk.Label(
            footer_frame,
            text="Tip: Say 'Menu' or double-click the mascot anytime to view this screen.",
            font=("Segoe UI", 9, "italic"),
            fg=TEXT_MUTED,
            bg=BG_COLOR,
        )
        hint_label.pack(side=tk.LEFT)
