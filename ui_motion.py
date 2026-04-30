from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def animate_width(widget, start_width: int, end_width: int, duration_ms: int = 220, fps: int = 60):
    if hasattr(widget, "_width_animation_job") and widget._width_animation_job is not None:
        try:
            widget.after_cancel(widget._width_animation_job)
        except tk.TclError:
            pass

    frame_ms = max(1, int(1000 / fps))
    start_time = time.perf_counter()
    delta = end_width - start_width

    def step():
        elapsed = (time.perf_counter() - start_time) * 1000
        progress = min(1.0, elapsed / duration_ms)
        next_width = int(start_width + delta * ease_out_cubic(progress))
        try:
            widget.configure(width=next_width)
            widget.update_idletasks()
        except tk.TclError:
            return
        if progress >= 1.0:
            widget.configure(width=end_width)
            widget._width_animation_job = None
            return
        widget._width_animation_job = widget.after(frame_ms, step)

    step()


def animate_int_label(label, start_value: int, end_value: int, duration_ms: int = 420, fps: int = 60):
    if start_value == end_value:
        label.configure(text=str(end_value))
        return

    if hasattr(label, "_int_animation_job") and label._int_animation_job is not None:
        try:
            label.after_cancel(label._int_animation_job)
        except tk.TclError:
            pass

    frame_ms = max(1, int(1000 / fps))
    start_time = time.perf_counter()
    delta = end_value - start_value

    def step():
        elapsed = (time.perf_counter() - start_time) * 1000
        progress = min(1.0, elapsed / duration_ms)
        next_value = int(start_value + delta * ease_out_cubic(progress))
        try:
            label.configure(text=str(next_value))
        except tk.TclError:
            return
        if progress >= 1.0:
            label.configure(text=str(end_value))
            label._int_animation_job = None
            return
        label._int_animation_job = label.after(frame_ms, step)

    step()


def bind_hover(widget, normal_style: dict, hover_style: dict, pressed_style: dict | None = None):
    pressed_style = pressed_style or hover_style
    widget._hover_normal_style = dict(normal_style)
    widget._hover_style = dict(hover_style)
    widget._pressed_style = dict(pressed_style)

    def is_enabled():
        try:
            return str(widget.cget("state")) != "disabled"
        except tk.TclError:
            return False

    def apply(style):
        if is_enabled():
            widget.configure(**style)

    widget.configure(cursor="hand2")
    widget.bind("<Enter>", lambda _event: apply(widget._hover_style), add="+")
    widget.bind("<Leave>", lambda _event: apply(widget._hover_normal_style), add="+")
    widget.bind("<ButtonPress-1>", lambda _event: apply(widget._pressed_style), add="+")
    widget.bind("<ButtonRelease-1>", lambda _event: apply(widget._hover_style), add="+")
    return widget


def debounce(root, delay_ms: int, callback):
    job = {"id": None}

    def schedule(*_args, **_kwargs):
        if job["id"] is not None:
            try:
                root.after_cancel(job["id"])
            except tk.TclError:
                pass
        job["id"] = root.after(delay_ms, run)

    def run():
        job["id"] = None
        callback()

    return schedule


def run_background_task(root, task_fn, on_success, on_error=None):
    def dispatch(callback):
        try:
            root.after(0, callback)
        except (RuntimeError, tk.TclError):
            pass

    def worker():
        try:
            result = task_fn()
        except Exception as exc:
            if on_error is not None:
                dispatch(lambda error=exc: on_error(error))
            return
        dispatch(lambda: on_success(result))

    threading.Thread(target=worker, daemon=True).start()


def set_busy_state(root, busy: bool = True):
    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    for child in walk(root):
        try:
            if busy:
                if not hasattr(child, "_busy_prev_cursor"):
                    child._busy_prev_cursor = child.cget("cursor")
                child.configure(cursor="watch")
            elif hasattr(child, "_busy_prev_cursor"):
                child.configure(cursor=child._busy_prev_cursor)
                del child._busy_prev_cursor
        except tk.TclError:
            pass


def show_loading_feedback(parent, text: str):
    frame = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
    label = tk.Label(frame, text=text, bg="#FFFFFF", fg="#6B7280", font=("Segoe UI", 9, "bold"))
    label.pack(side="left", padx=(10, 8), pady=7)
    progress = ttk.Progressbar(frame, mode="indeterminate", length=110)
    progress.pack(side="left", padx=(0, 10), pady=7)
    progress.start(12)
    frame._progress = progress
    return frame


def hide_loading_feedback(frame):
    if frame is None:
        return
    try:
        frame._progress.stop()
        frame.destroy()
    except tk.TclError:
        pass
