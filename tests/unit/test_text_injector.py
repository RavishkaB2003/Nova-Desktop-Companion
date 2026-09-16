"""
Project NOVA - Unit Tests for Text Injector and Dictation Formatter (FR-020, FR-022, PRIV-002)
"""

import unittest
from nova.core.state_machine import StateMachine
from nova.core.enums import SystemState
from nova.input.driver import InputDriver
from nova.input.text_injector import TextInjector, format_dictated_text


class TestTextInjector(unittest.TestCase):
    def setUp(self):
        self.driver = InputDriver(headless=True)
        self.sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        self.injector = TextInjector(driver=self.driver, state_machine=self.sm)

    def test_format_dictated_text_punctuation(self):
        # Period
        self.assertEqual(format_dictated_text("hello world period"), "Hello world. ")
        # Comma and Question Mark
        self.assertEqual(format_dictated_text("hello comma how are you question mark"), "Hello, how are you? ")
        # Exclamation Point
        self.assertEqual(format_dictated_text("watch out exclamation point"), "Watch out! ")
        # Colon and Semicolon
        self.assertEqual(format_dictated_text("agenda colon task one semicolon next"), "Agenda: task one; next ")

    def test_format_dictated_text_capitalization_and_whitespace(self):
        self.assertEqual(format_dictated_text("welcome to project nova"), "Welcome to project nova ")
        # No trailing space when explicitly requested
        self.assertEqual(format_dictated_text("no trailing space", add_trailing_space=False), "No trailing space")
        # Empty string handling
        self.assertEqual(format_dictated_text(""), "")
        self.assertEqual(format_dictated_text("   "), "")

    def test_inject_text_success(self):
        gen = self.sm.current_generation
        success = self.injector.inject_text("hello nova period", action_generation=gen)
        self.assertTrue(success)
        self.assertEqual(self.driver.injected_keystrokes, ["Hello nova. "])

    def test_inject_text_stale_generation_aborted(self):
        stale_gen = self.sm.current_generation
        # Bump generation (simulating emergency halt or state transition)
        self.sm.bump_generation()
        self.assertNotEqual(self.sm.current_generation, stale_gen)

        # Attempt to inject with stale generation
        success = self.injector.inject_text("stale dictation text", action_generation=stale_gen)
        self.assertFalse(success)
        # Verify driver received nothing
        self.assertEqual(len(self.driver.injected_keystrokes), 0)

    def test_press_key_success(self):
        gen = self.sm.current_generation
        res1 = self.injector.press_key("enter", action_generation=gen)
        res2 = self.injector.press_key("backspace", action_generation=gen)
        self.assertTrue(res1)
        self.assertTrue(res2)
        self.assertEqual(
            self.driver.injected_keystrokes,
            ["<ENTER>", "<BACKSPACE>"],
        )

    def test_press_key_stale_generation_aborted(self):
        stale_gen = self.sm.current_generation
        self.sm.bump_generation()

        res = self.injector.press_key("enter", action_generation=stale_gen)
        self.assertFalse(res)
        self.assertEqual(len(self.driver.injected_keystrokes), 0)


if __name__ == "__main__":
    unittest.main()
