"""Interactive browser for recorded cursor traces."""

from __future__ import annotations

import argparse
from pathlib import Path

import pygame

from .data_logger import DATA_DIR
from .demo_trace import ensure_demo_trace
from .replay_data import ReplaySession, discover_trace_files, load_trace
from .replay_renderer import BACKGROUND, MUTED, TEXT, draw_attempt_frame

WINDOW_SIZE = (1400, 820)
SIDEBAR_WIDTH = 410
ACCENT = (77, 163, 255)
SELECTED = (46, 70, 98)
ROW = (29, 35, 44)
ROW_ALT = (34, 40, 50)
SUCCESS = (72, 187, 120)
TIMEOUT = (230, 160, 65)
ABORTED = (220, 90, 90)


class ReplayBrowser:
    def __init__(self, screen: pygame.Surface, trace_paths: list[Path]) -> None:
        if not trace_paths:
            raise ValueError("no trace recordings found")
        self.screen = screen
        self.trace_paths = trace_paths
        self.session_index = 0
        self.session_scroll = 0
        self.session: ReplaySession = load_trace(trace_paths[0])
        self.attempt_index = 0
        self.attempt_scroll = 0
        self.playing = False
        self.playback_us = 0.0
        self.session_hits: list[tuple[pygame.Rect, int]] = []
        self.attempt_hits: list[tuple[pygame.Rect, int]] = []
        self.play_button = pygame.Rect(0, 0, 0, 0)
        self.restart_button = pygame.Rect(0, 0, 0, 0)
        self.timeline = pygame.Rect(0, 0, 0, 0)
        pygame.font.init()
        self.title_font = pygame.font.SysFont("Arial", 26, bold=True)
        self.section_font = pygame.font.SysFont("Arial", 17, bold=True)
        self.body_font = pygame.font.SysFont("Arial", 16)
        self.small_font = pygame.font.SysFont("Arial", 14)

    @property
    def attempt(self):
        if not self.session.attempts:
            return None
        return self.session.attempts[self.attempt_index]

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            dt_s = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        self._toggle_play()
                    elif event.key == pygame.K_r:
                        self._restart()
                    elif event.key == pygame.K_LEFT:
                        self._seek_relative(-1_000_000)
                    elif event.key == pygame.K_RIGHT:
                        self._seek_relative(1_000_000)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    if pygame.mouse.get_pos()[1] < 260:
                        max_scroll = max(0, len(self.trace_paths) - 4)
                        self.session_scroll = min(max_scroll, max(0, self.session_scroll - event.y))
                    else:
                        self.attempt_scroll = max(0, self.attempt_scroll - event.y)

            attempt = self.attempt
            if self.playing and attempt is not None:
                self.playback_us += dt_s * 1_000_000
                if self.playback_us >= attempt.duration_us:
                    self.playback_us = float(attempt.duration_us)
                    self.playing = False
            self.draw()
            pygame.display.flip()

    def draw(self) -> None:
        self.screen.fill(BACKGROUND)
        width, height = self.screen.get_size()
        sidebar = pygame.Rect(0, 0, SIDEBAR_WIDTH, height)
        pygame.draw.rect(self.screen, (20, 24, 31), sidebar)
        pygame.draw.line(self.screen, (65, 73, 85), (SIDEBAR_WIDTH, 0), (SIDEBAR_WIDTH, height), 1)
        self._draw_sidebar(sidebar)

        replay_view = pygame.Rect(SIDEBAR_WIDTH + 1, 0, width - SIDEBAR_WIDTH - 1, height - 86)
        attempt = self.attempt
        if attempt is None:
            message = self.title_font.render("No attempts in this recording", True, MUTED)
            self.screen.blit(message, message.get_rect(center=replay_view.center))
        else:
            draw_attempt_frame(self.screen, self.session, attempt, round(self.playback_us), replay_view)
        self._draw_controls(pygame.Rect(SIDEBAR_WIDTH + 1, height - 86, width - SIDEBAR_WIDTH - 1, 86))

    def _draw_sidebar(self, sidebar: pygame.Rect) -> None:
        self.session_hits = []
        self.attempt_hits = []
        title = self.title_font.render("Experiment Replay", True, TEXT)
        self.screen.blit(title, (18, 16))

        label = self.section_font.render("RECORDINGS", True, MUTED)
        self.screen.blit(label, (18, 62))
        y = 88
        for visible_index, path in enumerate(self.trace_paths[self.session_scroll:self.session_scroll + 4]):
            index = self.session_scroll + visible_index
            rect = pygame.Rect(12, y, SIDEBAR_WIDTH - 24, 42)
            color = SELECTED if index == self.session_index else ROW
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            text = self.body_font.render(path.stem.replace("_trace", ""), True, TEXT)
            self.screen.blit(text, (rect.left + 10, rect.top + 11))
            self.session_hits.append((rect, index))
            y += 47

        attempts_top = 290
        label = self.section_font.render("ATTEMPTS — chronological", True, MUTED)
        self.screen.blit(label, (18, attempts_top - 28))
        available_height = sidebar.height - attempts_top - 18
        visible_count = max(1, available_height // 52)
        max_scroll = max(0, len(self.session.attempts) - visible_count)
        self.attempt_scroll = min(self.attempt_scroll, max_scroll)
        for visible_index, attempt in enumerate(
            self.session.attempts[self.attempt_scroll:self.attempt_scroll + visible_count]
        ):
            index = self.attempt_scroll + visible_index
            rect = pygame.Rect(12, attempts_top + visible_index * 52, SIDEBAR_WIDTH - 24, 46)
            color = SELECTED if index == self.attempt_index else (ROW if index % 2 == 0 else ROW_ALT)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            main_text = self.body_font.render(
                f"Trial {attempt.trial_index:02d}   Attempt {attempt.attempt_index:02d}",
                True,
                TEXT,
            )
            outcome_color = {
                "answered": SUCCESS,
                "timeout": TIMEOUT,
                "aborted": ABORTED,
            }.get(attempt.outcome, MUTED)
            outcome = self.small_font.render(
                f"{attempt.outcome or 'open'}   {attempt.duration_us / 1_000_000:.1f}s",
                True,
                outcome_color,
            )
            self.screen.blit(main_text, (rect.left + 10, rect.top + 6))
            self.screen.blit(outcome, (rect.left + 10, rect.top + 26))
            self.attempt_hits.append((rect, index))

    def _draw_controls(self, controls: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (20, 24, 31), controls)
        self.play_button = pygame.Rect(controls.left + 20, controls.top + 20, 105, 44)
        self.restart_button = pygame.Rect(controls.left + 137, controls.top + 20, 105, 44)
        pygame.draw.rect(self.screen, ACCENT, self.play_button, border_radius=7)
        pygame.draw.rect(self.screen, ROW_ALT, self.restart_button, border_radius=7)
        play_text = self.section_font.render("PAUSE" if self.playing else "PLAY", True, TEXT)
        restart_text = self.section_font.render("RESTART", True, TEXT)
        self.screen.blit(play_text, play_text.get_rect(center=self.play_button.center))
        self.screen.blit(restart_text, restart_text.get_rect(center=self.restart_button.center))

        self.timeline = pygame.Rect(controls.left + 270, controls.centery - 5, controls.width - 300, 10)
        pygame.draw.rect(self.screen, (70, 78, 90), self.timeline, border_radius=5)
        attempt = self.attempt
        if attempt is not None and attempt.duration_us > 0:
            progress = min(1.0, self.playback_us / attempt.duration_us)
            filled = self.timeline.copy()
            filled.width = round(self.timeline.width * progress)
            pygame.draw.rect(self.screen, ACCENT, filled, border_radius=5)
            handle_x = self.timeline.left + round(self.timeline.width * progress)
            pygame.draw.circle(self.screen, TEXT, (handle_x, self.timeline.centery), 8)

    def _handle_click(self, pos: tuple[int, int]) -> None:
        for rect, index in self.session_hits:
            if rect.collidepoint(pos):
                self.session_index = index
                self.session = load_trace(self.trace_paths[index])
                self.attempt_index = 0
                self.attempt_scroll = 0
                self._restart()
                return
        for rect, index in self.attempt_hits:
            if rect.collidepoint(pos):
                self.attempt_index = index
                self._restart()
                return
        if self.play_button.collidepoint(pos):
            self._toggle_play()
        elif self.restart_button.collidepoint(pos):
            self._restart()
        elif self.timeline.collidepoint(pos) and self.attempt is not None:
            ratio = (pos[0] - self.timeline.left) / self.timeline.width
            self.playback_us = ratio * self.attempt.duration_us

    def _toggle_play(self) -> None:
        attempt = self.attempt
        if attempt is None:
            return
        if self.playback_us >= attempt.duration_us:
            self.playback_us = 0.0
        self.playing = not self.playing

    def _restart(self) -> None:
        self.playing = False
        self.playback_us = 0.0

    def _seek_relative(self, delta_us: int) -> None:
        if self.attempt is None:
            return
        self.playback_us = min(max(0.0, self.playback_us + delta_us), float(self.attempt.duration_us))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browse and replay recorded experiment traces.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--trace", type=Path, action="append", help="Open only this trace database (repeatable).")
    parser.add_argument("--no-demo", action="store_true", help="Do not create/list the built-in demo recording.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_demo:
        ensure_demo_trace(args.data_dir / "demo_replay_trace.sqlite3")
    trace_paths = [path.resolve() for path in args.trace] if args.trace else discover_trace_files(args.data_dir)
    if args.no_demo and not args.trace:
        trace_paths = [path for path in trace_paths if path.name != "demo_replay_trace.sqlite3"]
    if not trace_paths:
        raise SystemExit("No trace recordings found.")

    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption("Experiment Replay Browser")
    try:
        ReplayBrowser(screen, trace_paths).run()
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
