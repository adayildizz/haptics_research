"""Participant-facing numpad controls for the live experiment."""

from __future__ import annotations

from typing import Any, Literal

CONTINUE_LABEL = "NUMPAD ENTER"
EXIT_LABEL = "NUMPAD 0"
LEFT_LABEL = "NUMPAD 4"
RIGHT_LABEL = "NUMPAD 6"


def is_continue_key(key: int, pygame_module: Any) -> bool:
    return key == pygame_module.K_KP_ENTER


def is_exit_key(key: int, pygame_module: Any) -> bool:
    return key == pygame_module.K_KP0


def response_for_key(key: int, pygame_module: Any) -> Literal["left", "right"] | None:
    if key == pygame_module.K_KP4:
        return "left"
    if key == pygame_module.K_KP6:
        return "right"
    return None
