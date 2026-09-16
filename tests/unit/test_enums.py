"""
Project NOVA - Unit Tests for Core Enums
"""

import unittest
from nova.core.enums import MascotVisualState, SystemEventType, SystemState


class TestCoreEnums(unittest.TestCase):
    def test_system_state_values(self):
        expected_states = {
            "STANDBY",
            "WAKING",
            "IDLE_ACTIVE",
            "LISTENING",
            "DICTATING",
            "TRACKING",
            "EXECUTING",
            "GLIDE_ACTIVE",
            "CROSSHAIR_ACTIVE",
            "ERROR",
        }
        actual_states = {state.value for state in SystemState}
        self.assertEqual(expected_states, actual_states)
        self.assertEqual(len(SystemState), 10)

    def test_mascot_visual_state_values(self):
        expected_visuals = {
            "SLEEPING",
            "WAKING",
            "LISTENING",
            "DICTATING",
            "TRACKING",
            "EXECUTING",
            "ERROR",
        }
        actual_visuals = {visual.value for visual in MascotVisualState}
        self.assertEqual(expected_visuals, actual_visuals)
        self.assertEqual(len(MascotVisualState), 7)

    def test_system_event_type_values(self):
        expected_events = {
            "WAKE_WORD_DETECTED",
            "SLEEP_TRIGGERED",
            "EMERGENCY_HALT",
            "COMMAND_DETECTED",
            "DICTATION_START",
            "DICTATION_END",
            "ACTION_COMMITTED",
            "IMPULSE_DETECTED",
            "GLIDE_START",
            "GLIDE_STOP",
            "CROSSHAIR_START",
            "CROSSHAIR_STOP",
            "ACTIVATE_TRIGGERED",
            "DEACTIVATE_TRIGGERED",
            "AUDIO_STREAM_ERROR",
            "AUDIO_STREAM_RESTORED",
        }
        actual_events = {event.value for event in SystemEventType}
        self.assertEqual(expected_events, actual_events)


    def test_enum_string_inheritance(self):
        self.assertTrue(isinstance(SystemState.STANDBY, str))
        self.assertEqual(SystemState.STANDBY, "STANDBY")
        self.assertEqual(MascotVisualState.SLEEPING, "SLEEPING")
        self.assertEqual(SystemEventType.WAKE_WORD_DETECTED, "WAKE_WORD_DETECTED")


if __name__ == "__main__":
    unittest.main()
