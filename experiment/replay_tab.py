"""Tkinter replay panel embedded in the supervisor launcher."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from queue import Empty, SimpleQueue
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageTk

if TYPE_CHECKING:
    from .replay_data import ReplayAttempt, ReplaySession


class ReplayTab(ttk.Frame):
    """Browse recorded sessions and replay attempts without a second window."""

    FRAME_INTERVAL_MS = 33
    AUTO_NEXT_DELAY_MS = 500
    MIN_RENDER_SIZE = (480, 300)

    def __init__(self, notebook: ttk.Notebook, data_dir: Path) -> None:
        super().__init__(notebook, padding=10)
        self.data_dir = data_dir
        self._active = False
        self._loaded_once = False
        self._load_generation = 0
        self._trace_paths: list[Path] = []
        self._loading_path: Path | None = None
        self._load_results: SimpleQueue[tuple[int, Path, Any, str | None]] = SimpleQueue()
        self._pending_loads: set[int] = set()
        self._load_poll_job: str | None = None
        self._session: ReplaySession | None = None
        self._attempt_index: int | None = None
        self._playing = False
        self._playback_us = 0.0
        self._play_started_at = 0.0
        self._play_started_us = 0.0
        self._tick_job: str | None = None
        self._advance_job: str | None = None
        self._render_job: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._pygame: Any = None
        self._draw_attempt_frame: Any = None
        self._updating_timeline = False

        self.columnconfigure(0, weight=0, minsize=315)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_browser()
        self._build_player()
        notebook.add(self, text="Past Recordings")

    @property
    def attempt(self) -> ReplayAttempt | None:
        if self._session is None or self._attempt_index is None:
            return None
        if not 0 <= self._attempt_index < len(self._session.attempts):
            return None
        return self._session.attempts[self._attempt_index]

    def _build_browser(self) -> None:
        browser = ttk.Frame(self, padding=(0, 0, 10, 0))
        browser.grid(row=0, column=0, sticky="nsew")
        browser.columnconfigure(0, weight=1)
        browser.rowconfigure(1, weight=2)
        browser.rowconfigure(4, weight=3)

        heading = ttk.Frame(browser)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(heading, text="Recordings", font=("TkDefaultFont", 11, "bold")).pack(side="left")
        self.refresh_button = ttk.Button(heading, text="Refresh", command=self.refresh, width=9)
        self.refresh_button.pack(side="right")

        recording_frame = ttk.Frame(browser)
        recording_frame.grid(row=1, column=0, sticky="nsew")
        recording_frame.rowconfigure(0, weight=1)
        recording_frame.columnconfigure(0, weight=1)
        self.recording_tree = ttk.Treeview(
            recording_frame,
            columns=("modified",),
            show="tree headings",
            selectmode="browse",
            height=6,
        )
        self.recording_tree.heading("#0", text="Recording")
        self.recording_tree.heading("modified", text="Date")
        self.recording_tree.column("#0", width=185, minwidth=125)
        self.recording_tree.column("modified", width=105, minwidth=90, anchor="center")
        recording_scroll = ttk.Scrollbar(recording_frame, orient="vertical", command=self.recording_tree.yview)
        self.recording_tree.configure(yscrollcommand=recording_scroll.set)
        self.recording_tree.grid(row=0, column=0, sticky="nsew")
        recording_scroll.grid(row=0, column=1, sticky="ns")
        self.recording_tree.bind("<<TreeviewSelect>>", self._on_recording_selected)

        self.recording_status_var = tk.StringVar(value="Open the tab to load recordings.")
        ttk.Label(
            browser,
            textvariable=self.recording_status_var,
            wraplength=295,
            foreground="#666666",
        ).grid(row=2, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(browser, text="Attempts — chronological", font=("TkDefaultFont", 11, "bold")).grid(
            row=3, column=0, sticky="w", pady=(0, 5)
        )
        attempt_frame = ttk.Frame(browser)
        attempt_frame.grid(row=4, column=0, sticky="nsew")
        attempt_frame.rowconfigure(0, weight=1)
        attempt_frame.columnconfigure(0, weight=1)
        self.attempt_tree = ttk.Treeview(
            attempt_frame,
            columns=("attempt", "outcome", "result", "duration"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        self.attempt_tree.heading("attempt", text="Trial / Try")
        self.attempt_tree.heading("outcome", text="Outcome")
        self.attempt_tree.heading("result", text="Result")
        self.attempt_tree.heading("duration", text="Time")
        self.attempt_tree.column("attempt", width=82, minwidth=72, anchor="center")
        self.attempt_tree.column("outcome", width=72, minwidth=65, anchor="center")
        self.attempt_tree.column("result", width=78, minwidth=68, anchor="center")
        self.attempt_tree.column("duration", width=54, minwidth=48, anchor="e")
        self.attempt_tree.tag_configure("correct", foreground="#218739")
        self.attempt_tree.tag_configure("incorrect", foreground="#b3261e")
        self.attempt_tree.tag_configure("timeout", foreground="#a56100")
        attempt_scroll = ttk.Scrollbar(attempt_frame, orient="vertical", command=self.attempt_tree.yview)
        self.attempt_tree.configure(yscrollcommand=attempt_scroll.set)
        self.attempt_tree.grid(row=0, column=0, sticky="nsew")
        attempt_scroll.grid(row=0, column=1, sticky="ns")
        self.attempt_tree.bind("<<TreeviewSelect>>", self._on_attempt_selected)

    def _build_player(self) -> None:
        player = ttk.Frame(self)
        player.grid(row=0, column=1, sticky="nsew")
        player.columnconfigure(0, weight=1)
        player.rowconfigure(1, weight=1)

        self.session_info_var = tk.StringVar(value="Select a recording and an attempt.")
        ttk.Label(player, textvariable=self.session_info_var, anchor="w").grid(
            row=0, column=0, sticky="ew", pady=(0, 6)
        )

        self.preview = ttk.Label(
            player,
            text="No replay selected",
            anchor="center",
            justify="center",
            relief="sunken",
        )
        self.preview.grid(row=1, column=0, sticky="nsew")
        self.preview.bind("<Configure>", self._on_preview_configure)

        controls = ttk.Frame(player, padding=(0, 8, 0, 0))
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(3, weight=1)
        self.play_button = ttk.Button(controls, text="Play", command=self.toggle_play, state="disabled", width=9)
        self.play_button.grid(row=0, column=0, padx=(0, 6))
        self.restart_button = ttk.Button(
            controls, text="Restart", command=self.restart, state="disabled", width=9
        )
        self.restart_button.grid(row=0, column=1, padx=(0, 10))
        self.auto_next_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Auto-next", variable=self.auto_next_var).grid(
            row=0, column=2, padx=(0, 10)
        )
        self.timeline_var = tk.DoubleVar(value=0.0)
        self.timeline = ttk.Scale(
            controls,
            from_=0.0,
            to=1.0,
            variable=self.timeline_var,
            command=self._on_timeline_changed,
            state="disabled",
        )
        self.timeline.grid(row=0, column=3, sticky="ew")
        self.time_var = tk.StringVar(value="00.00 / 00.00 s")
        ttk.Label(controls, textvariable=self.time_var, width=17, anchor="e").grid(row=0, column=4, padx=(10, 0))

    def activate(self) -> None:
        """Enable the tab and lazily discover recordings."""
        self._active = True
        if not self._loaded_once:
            self._loaded_once = True
            self.refresh()
        elif self.attempt is not None:
            self._queue_render()

    def deactivate(self) -> None:
        """Pause replay and release scheduled GUI work when the tab is hidden."""
        self._active = False
        self._pause()
        self._cancel_job("_tick_job")
        self._cancel_job("_advance_job")
        self._cancel_job("_render_job")

    def close(self) -> None:
        self.deactivate()
        self._load_generation += 1
        self._cancel_job("_load_poll_job")

    def refresh(self) -> None:
        """Re-scan the data folder; trace modules are imported only on demand."""
        if not self._active:
            return
        self._pause()
        self.refresh_button.state(["disabled"])
        self.recording_status_var.set("Scanning recordings...")
        try:
            from .demo_trace import ensure_demo_trace
            from .replay_data import discover_trace_files

            self.data_dir.mkdir(parents=True, exist_ok=True)
            ensure_demo_trace(self.data_dir / "demo_replay_trace.sqlite3")
            self._trace_paths = discover_trace_files(self.data_dir)
        except Exception as exc:  # noqa: BLE001 -- presented in the replay panel
            self._trace_paths = []
            self.recording_status_var.set(f"Recordings could not be scanned: {exc}")
        finally:
            self.refresh_button.state(["!disabled"])

        self.recording_tree.delete(*self.recording_tree.get_children())
        self._clear_attempts()
        for index, path in enumerate(self._trace_paths):
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            label = path.stem.removesuffix("_trace")
            self.recording_tree.insert("", "end", iid=str(index), text=label, values=(modified,))

        if not self._trace_paths:
            self.recording_status_var.set("No trace recordings found.")
            self._clear_session()
            return
        self.recording_status_var.set(f"{len(self._trace_paths)} recording(s) found.")
        self.recording_tree.selection_set("0")
        self.recording_tree.focus("0")
        self.recording_tree.see("0")
        self._load_selected_recording(0)

    def _on_recording_selected(self, _event: tk.Event) -> None:
        selection = self.recording_tree.selection()
        if not selection:
            return
        self._load_selected_recording(int(selection[0]))

    def _load_selected_recording(self, index: int) -> None:
        if not 0 <= index < len(self._trace_paths):
            return
        path = self._trace_paths[index]
        if path == self._loading_path or (self._session is not None and path == self._session.path):
            return
        self._load_generation += 1
        generation = self._load_generation
        self._loading_path = path
        self._pending_loads.add(generation)
        self._pause()
        self._clear_attempts()
        self.recording_status_var.set(f"Loading {path.name}...")

        def load_worker() -> None:
            try:
                from .replay_data import load_trace

                session = load_trace(path)
                error = None
            except Exception as exc:  # noqa: BLE001 -- passed back to the GUI thread
                session = None
                error = str(exc)
            self._load_results.put((generation, path, session, error))

        threading.Thread(target=load_worker, name="replay-trace-loader", daemon=True).start()
        if self._load_poll_job is None:
            self._load_poll_job = self.after(25, self._poll_recording_loads)

    def _poll_recording_loads(self) -> None:
        self._load_poll_job = None
        while True:
            try:
                generation, path, session, error = self._load_results.get_nowait()
            except Empty:
                break
            self._pending_loads.discard(generation)
            self._finish_recording_load(generation, path, session, error)
        if self._pending_loads:
            self._load_poll_job = self.after(25, self._poll_recording_loads)

    def _finish_recording_load(
        self,
        generation: int,
        path: Path,
        session: ReplaySession | None,
        error: str | None,
    ) -> None:
        if generation != self._load_generation or not self.winfo_exists():
            return
        self._loading_path = None
        if error is not None or session is None:
            self._clear_session()
            self.recording_status_var.set(f"Could not load {path.name}: {error}")
            return

        self._session = session
        self._attempt_index = None
        self.recording_status_var.set(
            f"Participant {session.participant_id} • {len(session.attempts)} attempt(s)"
        )
        for index, attempt in enumerate(session.attempts):
            response_text = attempt.response.capitalize() if attempt.response is not None else "—"
            if attempt.correct is True:
                result_text = f"✓ {response_text}"
                row_tag = "correct"
            elif attempt.correct is False:
                result_text = f"✗ {response_text}"
                row_tag = "incorrect"
            else:
                result_text = "—"
                row_tag = attempt.outcome or ""
            self.attempt_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{attempt.trial_index} / {attempt.attempt_index}",
                    attempt.outcome or "open",
                    result_text,
                    f"{attempt.duration_us / 1_000_000:.1f}s",
                ),
                tags=(row_tag,),
            )
        if session.attempts:
            self.attempt_tree.selection_set("0")
            self.attempt_tree.focus("0")
            self.attempt_tree.see("0")
            self._select_attempt(0)
        else:
            self.session_info_var.set(f"{session.participant_id} • This recording has no attempts.")
            self.preview.configure(image="", text="No attempts in this recording")

    def _on_attempt_selected(self, _event: tk.Event) -> None:
        selection = self.attempt_tree.selection()
        if selection:
            self._select_attempt(int(selection[0]))

    def _select_attempt(self, index: int) -> None:
        if self._session is None or not 0 <= index < len(self._session.attempts):
            return
        if self._attempt_index == index:
            return
        self._cancel_job("_advance_job")
        self._pause()
        self._attempt_index = index
        self._playback_us = 0.0
        attempt = self._session.attempts[index]
        duration_s = attempt.duration_us / 1_000_000
        self.timeline.configure(to=max(duration_s, 0.001), state="normal")
        self.play_button.state(["!disabled"])
        self.restart_button.state(["!disabled"])
        self.session_info_var.set(
            f"{self._session.participant_id} • Trial {attempt.trial_index} • "
            f"Attempt {attempt.attempt_index} • {attempt.outcome or 'open'}"
        )
        self._set_timeline(0.0)
        self._queue_render()

    def toggle_play(self) -> None:
        self._cancel_job("_advance_job")
        attempt = self.attempt
        if attempt is None:
            return
        if self._playing:
            self._pause()
            self._set_timeline(self._playback_us / 1_000_000)
            self._queue_render()
            return
        if self._playback_us >= attempt.duration_us:
            self._playback_us = 0.0
        self._playing = True
        self._play_started_at = time.perf_counter()
        self._play_started_us = self._playback_us
        self.play_button.configure(text="Pause")
        self._schedule_tick()

    def restart(self) -> None:
        self._cancel_job("_advance_job")
        self._pause()
        self._playback_us = 0.0
        self._set_timeline(0.0)
        self._queue_render()

    def _pause(self) -> None:
        if self._playing:
            self._update_playback_clock()
        self._playing = False
        self.play_button.configure(text="Play")
        self._cancel_job("_tick_job")

    def _schedule_tick(self) -> None:
        self._cancel_job("_tick_job")
        if self._active and self._playing:
            self._tick_job = self.after(self.FRAME_INTERVAL_MS, self._tick)

    def _tick(self) -> None:
        self._tick_job = None
        attempt = self.attempt
        if not self._active or not self._playing or attempt is None:
            return
        self._update_playback_clock()
        if self._playback_us >= attempt.duration_us:
            self._playback_us = float(attempt.duration_us)
            self._playing = False
            self.play_button.configure(text="Play")
        self._set_timeline(self._playback_us / 1_000_000)
        self._render()
        if self._playback_us >= attempt.duration_us and self._has_next_attempt() and self.auto_next_var.get():
            self._advance_job = self.after(self.AUTO_NEXT_DELAY_MS, self._advance_to_next)
            return
        self._schedule_tick()

    def _has_next_attempt(self) -> bool:
        return (
            self._session is not None
            and self._attempt_index is not None
            and self._attempt_index + 1 < len(self._session.attempts)
        )

    def _advance_to_next(self) -> None:
        self._advance_job = None
        if not self._active or not self.auto_next_var.get() or not self._has_next_attempt():
            return
        assert self._attempt_index is not None
        next_index = self._attempt_index + 1
        item_id = str(next_index)
        self.attempt_tree.selection_set(item_id)
        self.attempt_tree.focus(item_id)
        self.attempt_tree.see(item_id)
        self._select_attempt(next_index)
        self.toggle_play()

    def _update_playback_clock(self) -> None:
        attempt = self.attempt
        if attempt is None:
            return
        elapsed_us = (time.perf_counter() - self._play_started_at) * 1_000_000
        self._playback_us = min(float(attempt.duration_us), self._play_started_us + elapsed_us)

    def _on_timeline_changed(self, value: str) -> None:
        if self._updating_timeline or self.attempt is None:
            return
        self._playback_us = float(value) * 1_000_000
        if self._playing:
            self._play_started_us = self._playback_us
            self._play_started_at = time.perf_counter()
        self._update_time_label()
        self._queue_render()

    def _set_timeline(self, seconds: float) -> None:
        self._updating_timeline = True
        try:
            self.timeline_var.set(seconds)
        finally:
            self._updating_timeline = False
        self._update_time_label()

    def _update_time_label(self) -> None:
        attempt = self.attempt
        if attempt is None:
            self.time_var.set("00.00 / 00.00 s")
            return
        self.time_var.set(
            f"{self._playback_us / 1_000_000:05.2f} / {attempt.duration_us / 1_000_000:05.2f} s"
        )

    def _on_preview_configure(self, _event: tk.Event) -> None:
        if self.attempt is not None:
            self._queue_render()

    def _queue_render(self) -> None:
        self._cancel_job("_render_job")
        if self._active:
            self._render_job = self.after(25, self._render)

    def _render(self) -> None:
        self._render_job = None
        attempt = self.attempt
        session = self._session
        if not self._active or attempt is None or session is None:
            return
        width = max(self.MIN_RENDER_SIZE[0], self.preview.winfo_width())
        height = max(self.MIN_RENDER_SIZE[1], self.preview.winfo_height())
        try:
            if self._pygame is None or self._draw_attempt_frame is None:
                import pygame

                from .replay_renderer import draw_attempt_frame

                self._pygame = pygame
                self._draw_attempt_frame = draw_attempt_frame
            surface = self._pygame.Surface((width, height))
            viewport = self._pygame.Rect(0, 0, width, height)
            self._draw_attempt_frame(surface, session, attempt, round(self._playback_us), viewport)
            rgb = self._pygame.image.tostring(surface, "RGB")
            frame = Image.frombytes("RGB", (width, height), rgb)
            self._photo = ImageTk.PhotoImage(frame)
            self.preview.configure(image=self._photo, text="")
        except Exception as exc:  # noqa: BLE001 -- replay failure must not crash the launcher
            self._pause()
            self.preview.configure(image="", text=f"Replay frame could not be rendered:\n{exc}")

    def _clear_attempts(self) -> None:
        self.attempt_tree.delete(*self.attempt_tree.get_children())
        self._session = None
        self._attempt_index = None
        self._playback_us = 0.0
        self.play_button.state(["disabled"])
        self.restart_button.state(["disabled"])
        self.timeline.configure(state="disabled")
        self._set_timeline(0.0)
        self.session_info_var.set("Select an attempt after the recording loads.")
        self._photo = None
        self.preview.configure(image="", text="Loading recording...")

    def _clear_session(self) -> None:
        self._clear_attempts()
        self.preview.configure(image="", text="No replay available")

    def _cancel_job(self, attribute: str) -> None:
        job = getattr(self, attribute)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            setattr(self, attribute, None)
