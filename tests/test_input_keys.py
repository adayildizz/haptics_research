from __future__ import annotations

import pygame

from experiment.input_keys import is_continue_key, is_exit_key, response_for_key


def test_numpad_enter_continues_and_numpad_zero_exits():
    assert is_continue_key(pygame.K_KP_ENTER, pygame)
    assert not is_continue_key(pygame.K_RETURN, pygame)
    assert is_exit_key(pygame.K_KP0, pygame)
    assert not is_exit_key(pygame.K_ESCAPE, pygame)


def test_numpad_four_and_six_map_to_left_and_right():
    assert response_for_key(pygame.K_KP4, pygame) == "left"
    assert response_for_key(pygame.K_KP6, pygame) == "right"
    assert response_for_key(pygame.K_LEFT, pygame) is None
    assert response_for_key(pygame.K_RIGHT, pygame) is None
