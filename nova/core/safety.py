"""
Project NOVA - Safety Subsystem & Monotonic Action Arbiter
Implements monotonic generation-gated action execution (FR-022),
secondary global physical emergency stop via Win32 RegisterHotKey (FR-023),
and clean unregistration and resource deallocation on exit (SEC-005).
"""

import ctypes
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Win32 Hotkey and Message Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

VK_ESCAPE = 0x1B
VK_Q = 0x51

HOTKEY_ID_ESCAPE = 1001
HOTKEY_ID_CTRL_SHIFT_Q = 1002


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_ulong),
        ("pt", POINT),
        ("lPrivate", ctypes.c_ulong),
    ]


@dataclass(frozen=True)
class ActionToken:
    """
    Immutable generation token issued to in-flight desktop actions (FR-022).
    Dispatched cursor moves, clicks, and text injections verify this token before execution.
    """
    token_id: int
    generation: int
    created_at: float
    action_type: str = "generic"


class ActionArbiter:
    """
    Centralized monotonic generation arbiter (FR-022).
    Guarantees thread-safe invalidation of in-flight actions upon halt, sleep, or escape.
    Zero persistent data or PII retained in audit records (PRIV-002).
    """

    def __init__(self, initial_generation: int = 0) -> None:
        self._lock = threading.RLock()
        self._generation: int = initial_generation
        self._token_counter: int = 0
        self._listeners: List[Callable[[int, str], None]] = []
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def current_generation(self) -> int:
        """Returns the current monotonic generation counter."""
        with self._lock:
            return self._generation

    @property
    def generation(self) -> int:
        """Property alias for current_generation."""
        return self.current_generation

    def bump_generation(self, reason: str = "") -> int:
        """
        Monotonically increment the generation counter to invalidate all pending actions.
        Synchronously notifies registered invalidation listeners.
        """
        with self._lock:
            self._generation += 1
            new_gen = self._generation
            now = time.monotonic()
            self._audit_log.append({
                "timestamp": now,
                "generation": new_gen,
                "reason": reason,
            })
            # Limit audit log size in memory (ephemeral)
            if len(self._audit_log) > 100:
                self._audit_log = self._audit_log[-100:]

            logger.info("Action generation bumped to %d (reason='%s')", new_gen, reason)
            listeners_snapshot = list(self._listeners)

        # Notify observers outside the state lock to avoid reentrancy deadlocks
        for listener in listeners_snapshot:
            try:
                listener(new_gen, reason)
            except Exception as exc:
                logger.exception("Error in action invalidation listener: %s", exc)

        return new_gen

    def is_valid(self, action_generation: int) -> bool:
        """Returns True if the specified generation matches the current generation."""
        with self._lock:
            return action_generation == self._generation

    def mint_token(self, action_type: str = "generic") -> ActionToken:
        """Mint a new generation token bound to the current generation."""
        with self._lock:
            self._token_counter += 1
            return ActionToken(
                token_id=self._token_counter,
                generation=self._generation,
                created_at=time.monotonic(),
                action_type=action_type,
            )

    def validate_token(self, token: ActionToken) -> bool:
        """Validate whether an ActionToken is still current."""
        if token is None:
            return False
        return self.is_valid(token.generation)

    def register_invalidation_listener(self, callback: Callable[[int, str], None]) -> Callable[[], None]:
        """
        Register a callback invoked whenever the generation counter is bumped.
        Returns an unregister function.
        """
        with self._lock:
            self._listeners.append(callback)

        def unregister() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return unregister

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return a snapshot copy of the in-memory generation invalidation log."""
        with self._lock:
            return list(self._audit_log)


class GlobalHotkeyManager:
    """
    Win32 Global Physical Emergency Stop Manager (FR-023, SEC-005).
    Intercepts global Escape and Ctrl+Shift+Q hotkeys via Win32 RegisterHotKey in a dedicated thread.
    Guarantees clean hotkey unregistration on application shutdown without orphaned hooks (SEC-005).
    """

    def __init__(
        self,
        on_emergency_hotkey: Optional[Callable[[int, str], None]] = None,
        headless: bool = False,
    ) -> None:
        self.on_emergency_hotkey = on_emergency_hotkey
        self.headless = headless or (os.name != "nt")

        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running: bool = False
        self._registered_ids: Set[int] = set()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> bool:
        """
        Register global hotkeys and start the Win32 message pump thread.
        In headless or non-Windows mode, operates in mock simulation mode.
        """
        with self._lock:
            if self._running:
                return True

            self._running = True

            if self.headless:
                self._registered_ids = {HOTKEY_ID_ESCAPE, HOTKEY_ID_CTRL_SHIFT_Q}
                logger.info("GlobalHotkeyManager started in headless/mock mode (hotkeys: ESC, CTRL+SHIFT+Q).")
                return True

            ready_event = threading.Event()
            self._thread = threading.Thread(
                target=self._message_pump_worker,
                args=(ready_event,),
                name="NovaGlobalHotkeyWorker",
                daemon=True,
            )
            self._thread.start()

        ready_event.wait(timeout=2.0)
        logger.info("GlobalHotkeyManager message pump thread initialized.")
        return True

    def _message_pump_worker(self, ready_event: threading.Event) -> None:
        """Native Win32 message loop to receive WM_HOTKEY notifications."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Register Escape hotkey (ID 1001)
        res_esc = user32.RegisterHotKey(None, HOTKEY_ID_ESCAPE, MOD_NOREPEAT, VK_ESCAPE)
        if res_esc:
            with self._lock:
                self._registered_ids.add(HOTKEY_ID_ESCAPE)
            logger.info("Global emergency hotkey ESCAPE registered successfully (ID=%d).", HOTKEY_ID_ESCAPE)
        else:
            err = kernel32.GetLastError()
            logger.warning("Failed to register global hotkey ESCAPE (Win32 Error: %d).", err)

        # Register Ctrl+Shift+Q hotkey (ID 1002)
        res_ctrl_shift_q = user32.RegisterHotKey(
            None,
            HOTKEY_ID_CTRL_SHIFT_Q,
            MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            VK_Q,
        )
        if res_ctrl_shift_q:
            with self._lock:
                self._registered_ids.add(HOTKEY_ID_CTRL_SHIFT_Q)
            logger.info("Global emergency hotkey CTRL+SHIFT+Q registered successfully (ID=%d).", HOTKEY_ID_CTRL_SHIFT_Q)
        else:
            err = kernel32.GetLastError()
            logger.warning("Failed to register global hotkey CTRL+SHIFT+Q (Win32 Error: %d).", err)

        ready_event.set()

        msg = MSG()
        try:
            while self._running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0 or msg.message == WM_QUIT:
                    break

                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    self._dispatch_hotkey(hotkey_id)
        except Exception as exc:
            logger.error("Exception in GlobalHotkeyManager message pump: %s", exc)
        finally:
            # Clean unregistration on thread exit (SEC-005)
            self._unregister_all_hotkeys_locked(user32)

    def _dispatch_hotkey(self, hotkey_id: int) -> None:
        """Route recognized hotkey ID to the registered emergency callback."""
        hotkey_name = "ESCAPE" if hotkey_id == HOTKEY_ID_ESCAPE else "CTRL_SHIFT_Q"
        logger.warning("Physical emergency stop triggered via hotkey: %s (ID=%d)", hotkey_name, hotkey_id)
        if self.on_emergency_hotkey:
            try:
                self.on_emergency_hotkey(hotkey_id, hotkey_name)
            except Exception as exc:
                logger.exception("Error in emergency hotkey handler: %s", exc)

    def simulate_hotkey(self, key_name_or_id: Union[str, int]) -> None:
        """
        Simulate a global physical emergency hotkey for automated tests and headless environments.
        """
        if isinstance(key_name_or_id, int):
            hid = key_name_or_id
        elif str(key_name_or_id).strip().lower() in ("escape", "esc"):
            hid = HOTKEY_ID_ESCAPE
        else:
            hid = HOTKEY_ID_CTRL_SHIFT_Q

        self._dispatch_hotkey(hid)

    def _unregister_all_hotkeys_locked(self, user32: Any) -> None:
        """Unregister all active hotkeys via Win32 UnregisterHotKey (SEC-005)."""
        with self._lock:
            for hid in list(self._registered_ids):
                try:
                    user32.UnregisterHotKey(None, hid)
                    logger.info("Unregistered global hotkey ID: %d", hid)
                except Exception as exc:
                    logger.warning("Error unregistering hotkey ID %d: %s", hid, exc)
            self._registered_ids.clear()

    def stop(self) -> None:
        """
        Stop the message pump thread and cleanly unregister all hotkeys (SEC-005).
        Safe to call multiple times (idempotent).
        """
        with self._lock:
            if not self._running:
                self._registered_ids.clear()
                return
            self._running = False
            thread = self._thread
            thread_id = self._thread_id

        if not self.headless and thread_id and os.name == "nt":
            try:
                ctypes.windll.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception as exc:
                logger.debug("Error posting WM_QUIT to hotkey thread: %s", exc)

        if thread and thread.is_alive():
            thread.join(timeout=1.0)

        # In case thread did not run or is headless, guarantee unregistration
        if not self.headless and os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                self._unregister_all_hotkeys_locked(user32)
            except Exception:
                pass
        else:
            with self._lock:
                self._registered_ids.clear()

        logger.info("GlobalHotkeyManager stopped cleanly.")


class SafetyCoordinator:
    """
    Central safety and emergency override coordinator (FR-021, FR-022, FR-023).
    Integrates ActionArbiter, GlobalHotkeyManager, StateMachine, and UI overlays
    to ensure immediate, fail-closed desktop state resets.
    """

    def __init__(
        self,
        arbiter: Optional[ActionArbiter] = None,
        hotkey_manager: Optional[GlobalHotkeyManager] = None,
        state_machine: Optional[Any] = None,
        on_halt_feedback: Optional[Callable[[str], None]] = None,
        headless: bool = False,
    ) -> None:
        self.arbiter = arbiter or ActionArbiter()
        self.state_machine = state_machine
        self.on_halt_feedback = on_halt_feedback
        self.headless = headless

        self._cancellation_hooks: List[Callable[[], None]] = []
        self._lock = threading.RLock()

        if hotkey_manager:
            self.hotkey_manager = hotkey_manager
            self.hotkey_manager.on_emergency_hotkey = self._on_physical_hotkey
        else:
            self.hotkey_manager = GlobalHotkeyManager(
                on_emergency_hotkey=self._on_physical_hotkey,
                headless=self.headless,
            )

    def register_cancellation_hook(self, hook: Callable[[], None]) -> None:
        """
        Register a cancellation hook for an active subsystem (e.g. dismiss HUD,
        hide crosshair, stop glider, halt scrolling, abort dictation).
        """
        with self._lock:
            self._cancellation_hooks.append(hook)

    def trigger_emergency_halt(
        self,
        source: str = "MANUAL",
        reset_to_standby: bool = False,
    ) -> int:
        """
        Execute an emergency halt across all subsystems:
        1. Monotonically increment action generation to invalidate in-flight actions (FR-022).
        2. Execute all cancellation hooks (HUD, crosshair, glider, scroller, dictation).
        3. Transition state machine to STANDBY or IDLE_ACTIVE based on halt severity.
        4. Provide local feedback.
        """
        with self._lock:
            # 1. Monotonic invalidation
            new_gen = self.arbiter.bump_generation(reason=source)
            hooks_snapshot = list(self._cancellation_hooks)

        # 2. Execute cancellation hooks
        for hook in hooks_snapshot:
            try:
                hook()
            except Exception as exc:
                logger.exception("Error executing cancellation hook during emergency halt: %s", exc)

        # 3. State transition
        if self.state_machine:
            try:
                from nova.core.enums import SystemState
                if reset_to_standby or self.state_machine.current_state == SystemState.STANDBY:
                    self.state_machine.transition_to(SystemState.STANDBY)
                else:
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
            except Exception as exc:
                logger.exception("Error transitioning state machine during emergency halt: %s", exc)

        # 4. Local feedback
        if self.on_halt_feedback:
            try:
                self.on_halt_feedback(source)
            except Exception as exc:
                logger.debug("Error in halt feedback callback: %s", exc)

        logger.warning("Emergency halt completed successfully (source='%s', new_gen=%d).", source, new_gen)
        return new_gen

    def _on_physical_hotkey(self, hotkey_id: int, hotkey_name: str) -> None:
        """Handler for Win32 global emergency hotkeys (Escape, Ctrl+Shift+Q)."""
        logger.warning("Handling physical emergency stop hotkey '%s'", hotkey_name)
        # Physical emergency stop forces a hard reset to STANDBY (FR-023, SRS.md FR-20)
        self.trigger_emergency_halt(source=f"HOTKEY_{hotkey_name}", reset_to_standby=True)

    def start(self) -> bool:
        """Start the safety coordinator and bind global hotkeys."""
        return self.hotkey_manager.start()

    def stop(self) -> None:
        """Stop the safety coordinator and release global hotkeys (SEC-005)."""
        self.hotkey_manager.stop()
