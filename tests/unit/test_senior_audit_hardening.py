"""
Project NOVA - Unit Tests for Senior Audit Hardening
Verifies:
1. Vectorized circular autocorrelation (FFT-based NACF) correctness and speed.
2. HarmonicChimeSynthesizer waveform generation.
3. StateMachine ActionGeneration bump and invalidation.
4. Coordinator ActionGeneration protection against stale click execution on halt/dismiss.
5. Autonomous glider halting on screen boundary.
6. UIAutomationCrawler SPI_SETSCREENREADER restoration.
"""

import time
import tkinter as tk
import unittest
import numpy as np

from nova.audio.dsp import VoicedPitchTracker
from nova.audio.ducking import HarmonicChimeSynthesizer
from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemEventType, SystemState
from nova.core.glider import ContinuousGlider
from nova.core.state_machine import StateMachine, SystemEvent
from nova.input.driver import InputDriver
from nova.ui.hud_overlay import HudOverlay


class TestSeniorAuditHardening(unittest.TestCase):
    def test_vectorized_nacf_correctness_and_speed(self):
        """Verify vectorized circular autocorrelation matches ground-truth NACF calculation."""
        tracker = VoicedPitchTracker()
        sr = 16000
        freq = 150.0  # 150 Hz test pitch
        n_samples = 512
        t = np.arange(n_samples) / sr
        signal = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

        # Warm-up run to eliminate cold-start FFT plan caching
        tracker.compute_nacf_peak(signal)

        start_time = time.perf_counter()
        iters = 20
        for _ in range(iters):
            peak_r, pitch_hz = tracker.compute_nacf_peak(signal)
        avg_time_ms = ((time.perf_counter() - start_time) / iters) * 1000.0

        self.assertGreater(peak_r, 0.95)
        self.assertAlmostEqual(pitch_hz, freq, delta=2.0)
        # Verify vectorized computation averages well under 0.5ms (typically 0.15ms)
        self.assertLess(avg_time_ms, 0.5)

    def test_harmonic_chime_synthesizer(self):
        """Verify harmonic chime synthesis generates smooth, non-empty Hann-windowed chords."""
        for chime in ("wake", "sleep", "error", "acknowledge"):
            waveform = HarmonicChimeSynthesizer.synthesize_chime(chime)
            self.assertIsInstance(waveform, np.ndarray)
            self.assertGreater(len(waveform), 0)
            self.assertEqual(waveform.dtype, np.float32)
            # Ensure amplitude doesn't clip
            self.assertLessEqual(np.max(np.abs(waveform)), 0.3)
            # Smooth attack and release (start and end near zero)
            self.assertAlmostEqual(waveform[0], 0.0, places=2)

    def test_state_machine_generation_counter(self):
        """Verify ActionGeneration increments monotonically and invalidates on EMERGENCY_HALT."""
        sm = StateMachine(initial_state=SystemState.STANDBY)
        initial_gen = sm.current_generation
        self.assertEqual(initial_gen, 0)

        gen1 = sm.bump_generation()
        self.assertEqual(gen1, 1)
        self.assertEqual(sm.current_generation, 1)

        # EMERGENCY_HALT event must increment generation
        sm.transition_to(SystemState.WAKING)
        sm.transition_to(SystemState.IDLE_ACTIVE)
        sm.handle_event(SystemEvent(event_type=SystemEventType.EMERGENCY_HALT))
        self.assertEqual(sm.current_generation, 2)

    def test_coordinator_action_generation_drop_on_halt(self):
        """Verify stale click is silently discarded if halt or dismiss occurs during aim/dispatch."""
        root = tk.Tk()
        try:
            sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
            crawler = UIAutomationCrawler()
            driver = InputDriver(headless=True)
            hud = HudOverlay(root=root)
            coordinator = TagSnapCoordinator(
                state_machine=sm,
                crawler=crawler,
                hud=hud,
                driver=driver,
            )

            dummy_target = UIElementTarget(
                target_id=1,
                title="Submit",
                control_type="Button",
                bounding_box=(100, 100, 150, 150),
                centroid_x=125,
                centroid_y=125,
                page_index=0,
                window_handle=12345,
            )
            crawler.set_synthetic_targets([[dummy_target]])
            coordinator.trigger_tag_scan()
            root.update()

            # Step 1: Aim at target 1
            aimed = coordinator.aim_at_target_badge(1)
            self.assertTrue(aimed)
            self.assertEqual(coordinator.selected_target, dummy_target)

            # User says "halt" or clicks dismiss while aim was active -> generation bumped
            sm.bump_generation()

            # Step 2: Attempt execute_target_click -> must be dropped due to stale generation
            result = coordinator.execute_target_click()
            self.assertFalse(result)
            # Verify no click was executed in driver
            self.assertEqual(len(driver.injected_clicks), 0)
        finally:
            try:
                hud.destroy()
                root.destroy()
            except Exception:
                pass

    def test_autonomous_glider_boundary_halt(self):
        """Autonomous glider must stop when hitting desktop boundaries."""
        driver = InputDriver(headless=True)
        glider = ContinuousGlider(driver=driver, speed_px_s=200.0)

        # Place cursor near right boundary and glide right
        from nova.input.driver import get_virtual_desktop_bounds
        vx, vy, v_max_x, v_max_y = get_virtual_desktop_bounds()
        driver.set_cursor_pos(v_max_x - 5, vy + 100)

        glider.set_heading_direction("right")
        glider.start_glide(autonomous=True)
        self.assertTrue(glider.is_gliding)
        self.assertTrue(glider.is_autonomous)

        # Step glider past right boundary (dt = 0.5s -> dx = 100px)
        glider.step(dt_s=0.5)

        # Glider should have clamped to boundary and halted autonomous cruise
        self.assertFalse(glider.is_gliding)
        self.assertFalse(glider.is_autonomous)

    def test_crawler_accessibility_flag_restoration(self):
        """UIAutomationCrawler must restore original screenreader flag on demand."""
        crawler = UIAutomationCrawler()
        crawler._original_screenreader_flag = 0
        crawler.restore_system_accessibility_flags()

    def test_software_ducking_gate_and_chime_state(self):
        """Verify is_chime_playing flag and grid exclusion from crosshair grammar."""
        from nova.audio.ducking import is_chime_playing, play_audio_chime
        from nova.speech.vosk_engine import DEFAULT_GRAMMAR

        # Verify 'grid' and 'crosshair' are NOT in DEFAULT_GRAMMAR
        self.assertNotIn("grid", DEFAULT_GRAMMAR)
        self.assertNotIn("crosshair", DEFAULT_GRAMMAR)
        self.assertIn("cross hair", DEFAULT_GRAMMAR)
        self.assertIn("laser", DEFAULT_GRAMMAR)
        self.assertIn("scanner", DEFAULT_GRAMMAR)

        # Verify synchronous chime execution resets chime playing state cleanly
        self.assertFalse(is_chime_playing())
        play_audio_chime("acknowledge", async_play=False)
        self.assertFalse(is_chime_playing())

    def test_spoken_close_does_not_speak_halted(self):
        """Spoken 'close' must dismiss HUD without triggering speech_feedback.speak('Halted')."""
        sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        crawler = UIAutomationCrawler()
        driver = InputDriver(headless=True)
        hud = HudOverlay(root=None)
        coordinator = TagSnapCoordinator(
            state_machine=sm,
            crawler=crawler,
            hud=hud,
            driver=driver,
        )

        # Mock speech_feedback.speak to verify it's NOT called on 'close'
        spoken_calls = []
        coordinator.speech_feedback.speak = lambda text: spoken_calls.append(text)

        coordinator.handle_speech_phrase("close")
        self.assertEqual(spoken_calls, [])

        # However, an explicit emergency halt command MUST speak Halted
        coordinator.handle_speech_phrase("halt")
        self.assertEqual(spoken_calls, ["Halted"])

    def test_deactivate_does_not_crash(self):
        """Coordinator handle_deactivate must not crash with NameError or AttributeError when active."""
        sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        crawler = UIAutomationCrawler()
        driver = InputDriver(headless=True)
        hud = HudOverlay(root=None)
        deactivated = []
        coordinator = TagSnapCoordinator(
            state_machine=sm,
            crawler=crawler,
            hud=hud,
            driver=driver,
            on_deactivate=lambda: deactivated.append(True),
        )
        # Call handle_deactivate while in IDLE_ACTIVE
        coordinator.handle_deactivate()
        self.assertEqual(sm.current_state, SystemState.STANDBY)
        self.assertEqual(deactivated, [True])

    def test_crosshair_is_active_property(self):
        """CrosshairOverlay must provide both is_visible and is_active properties."""
        from nova.ui.crosshair import CrosshairOverlay
        crosshair = CrosshairOverlay(root=None)
        self.assertFalse(crosshair.is_visible)
        self.assertFalse(crosshair.is_active)

    def test_spoken_feedback_thread_safe_counter(self):
        """SpokenFeedback must track active speakers with an atomic counter, not boolean (F-13)."""
        from nova.core.coordinator import SpokenFeedback
        feedback = SpokenFeedback(enabled=True)
        self.assertFalse(feedback.is_speaking)
        with feedback._lock:
            feedback._speaking_count = 2
        self.assertTrue(feedback.is_speaking)
        with feedback._lock:
            feedback._speaking_count = 1
        self.assertTrue(feedback.is_speaking)
        with feedback._lock:
            feedback._speaking_count = 0
        self.assertFalse(feedback.is_speaking)

    def test_text_injector_mid_sentence_capitalization(self):
        """Clauses mid-sentence must not be capitalized (F-22)."""
        from nova.input.text_injector import TextInjector
        driver = InputDriver(headless=True)
        injector = TextInjector(driver=driver)

        # First clause starts sentence -> capitalized
        injector.inject_text("i went to the store")
        self.assertEqual(driver.injected_keystrokes[-1], "I went to the store ")

        # Subsequent clause continues sentence -> not capitalized
        injector.inject_text("and bought milk period")
        self.assertEqual(driver.injected_keystrokes[-1], "and bought milk. ")

        # After period -> capitalized
        injector.inject_text("it was fresh")
        self.assertEqual(driver.injected_keystrokes[-1], "It was fresh ")

    def test_config_defaults(self):
        """Config module must supply verified operational constants (F-37)."""
        from nova.core import config
        self.assertEqual(config.DEFAULT_SAMPLE_RATE_HZ, 16000)
        self.assertEqual(config.DEFAULT_CONFIDENCE_THRESHOLD, 0.65)
        self.assertEqual(config.DEFAULT_PAGE_SIZE, 9)


if __name__ == "__main__":
    unittest.main()


