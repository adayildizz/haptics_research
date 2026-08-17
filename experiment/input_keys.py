"""Cross-keyboard participant controls for the live experiment."""

from __future__ import annotations

from typing import Any, Literal

CONTINUE_LABEL = "SPACE / ENTER / NUMPAD ENTER"
EXIT_LABEL = "ESC / NUMPAD 0"
LEFT_LABEL = "LEFT ARROW / NUMPAD 4"
RIGHT_LABEL = "RIGHT ARROW / NUMPAD 6"


def is_continue_key(key: int, pygame_module: Any) -> bool:
    return key in (pygame_module.K_SPACE, pygame_module.K_RETURN, pygame_module.K_KP_ENTER)


def is_exit_key(key: int, pygame_module: Any) -> bool:
    return key in (pygame_module.K_ESCAPE, pygame_module.K_KP0)


def response_for_key(key: int, pygame_module: Any) -> Literal["left", "right"] | None:
    if key in (pygame_module.K_LEFT, pygame_module.K_KP4):
        return "left"
    if key in (pygame_module.K_RIGHT, pygame_module.K_KP6):
        return "right"
    return None
