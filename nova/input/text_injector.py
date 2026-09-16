"""
Project NOVA - Win32 Keyboard Text Injector
Formats raw ASR transcription and injects text into the foreground control (FR-020).
Enforces monotonic generation invalidation (FR-022) and ephemeral in-memory processing (PRIV-002).
"""

import logging
import re
from typing import Optional

from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver

logger = logging.getLogger(__name__)

# Punctuation replacement patterns for natural voice dictation
PUNCTUATION_MAP = [
    (r"\bperiod\b", "."),
    (r"\bcomma\b", ","),
    (r"\bquestion mark\b", "?"),
    (r"\bexclamation point\b", "!"),
    (r"\bexclamation mark\b", "!"),
    (r"\bcolon\b", ":"),
    (r"\bsemicolon\b", ";"),
]


def format_dictated_text(raw_text: str, add_trailing_space: bool = True, is_sentence_start: bool = True) -> str:
    """
    Normalizes spoken text clauses into standard typed punctuation and capitalization.
    Substitutes spoken punctuation markers (e.g. 'period' -> '.', 'comma' -> ',').
    Only capitalizes leading character when is_sentence_start is True (FR-020).
    """
    if not raw_text:
        return ""

    text = raw_text.strip()

    # Apply spoken punctuation
    for pattern, replacement in PUNCTUATION_MAP:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Clean up whitespace before punctuation marks
    text = re.sub(r"\s+([.,?!:;])", r"\1", text)

    # Clean up multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    # Capitalize first character only if beginning of a sentence
    if is_sentence_start:
        text = text[0].upper() + text[1:]

    # Capitalize first character after sentence-terminating punctuation (. ? !)
    text = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)

    # Add trailing space if it ends with an alphanumeric character or punctuation
    if add_trailing_space and not text.endswith(" "):
        text += " "

    return text


class TextInjector:
    """
    Dispatches formatted text into the active focused control via InputDriver.
    Guarantees generation-gated execution to discard stale injections if an emergency halt occurred.
    """

    def __init__(
        self,
        driver: Optional[InputDriver] = None,
        state_machine: Optional[StateMachine] = None,
    ) -> None:
        self.driver = driver or InputDriver()
        self.state_machine = state_machine
        self._is_sentence_start = True

    def reset(self) -> None:
        """Reset sentence capitalization tracking."""
        self._is_sentence_start = True

    def inject_text(
        self,
        raw_text: str,
        action_generation: Optional[int] = None,
        add_trailing_space: bool = True,
    ) -> bool:
        """
        Format and inject text into the active focused control.
        Silently discards injection if action_generation is stale (FR-022).
        """
        if not raw_text:
            return False

        # Monotonic generation gate check (FR-022)
        if self.state_machine and action_generation is not None:
            current_gen = self.state_machine.current_generation
            if current_gen != action_generation:
                logger.warning(
                    "Dictation text injection aborted: generation changed (%d != %d).",
                    current_gen,
                    action_generation,
                )
                return False

        formatted = format_dictated_text(
            raw_text,
            add_trailing_space=add_trailing_space,
            is_sentence_start=self._is_sentence_start,
        )
        if not formatted:
            return False

        stripped = formatted.strip()
        if stripped and stripped[-1] in (".", "?", "!", "\n"):
            self._is_sentence_start = True
        else:
            self._is_sentence_start = False

        self.driver.type_text(formatted)
        return True

    def press_key(self, key_name: str, action_generation: Optional[int] = None) -> bool:
        """
        Dispatch special control key (e.g. 'enter', 'backspace') with generation gating.
        """
        if self.state_machine and action_generation is not None:
            if self.state_machine.current_generation != action_generation:
                return False

        self.driver.press_key(key_name)
        return True
