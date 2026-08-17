from __future__ import annotations

import pygame

from experiment.input_keys import is_continue_key, is_exit_key, response_for_key


def test_space_regular_enter_and_numpad_enter_all_continue():
    assert is_continue_key(pygame.K_SPACE, pygame)
    assert is_continue_key(pygame.K_RETURN, pygame)
    assert is_continue_key(pygame.K_KP_ENTER, pygame)


def test_escape_and_numpad_zero_both_exit():
    assert is_exit_key(pygame.K_ESCAPE, pygame)
    assert is_exit_key(pygame.K_KP0, pygame)


def test_arrow_keys_and_numpad_four_and_six_map_to_left_and_right():
    assert response_for_key(pygame.K_LEFT, pygame) == "left"
    assert response_for_key(pygame.K_KP4, pygame) == "left"
    assert response_for_key(pygame.K_RIGHT, pygame) == "right"
    assert response_for_key(pygame.K_KP6, pygame) == "right"
