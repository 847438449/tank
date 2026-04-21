#!/usr/bin/env python3
"""Tkinter GUI for local audio or URL transcription."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from transcribe_videos import (
    ensure_ffmpeg,
    ensure_yt_dlp,
    run_transcription_pipeline,
)

MODEL_OPTIONS = ["tiny", "base", "small", "medium", "large"]
DEVICE_OPTIONS = ["cuda", "cpu"]
COMPUTE_OPTIONS = ["float16", "int8"]
INPUT_MODES = ["Local audio file", "URL"]
AUDIO_FILETYPES = [
    (
        "Audio files",
        "*.mp3 *.wav *.m4a *.flac *.aac *.ogg",
    ),
    ("All files", "*.*"),
]


class TranscriptionGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("日语转写工具 (faster-whisper)")
        self.root.geometry("950x680")

        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self.input_mode_var = tk.StringVar(value=INPUT_MODES[0])
        self.local_file_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.model_var = tk.StringVar(value="small")
        self.device_var = tk.StringVar(value="cuda")
        self.compute_var = tk.StringVar(value="float16")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.local_row: ttk.Frame | None = None
        self.url_row: ttk.Frame | None = None

        self._build_ui()
        self._update_input_mode_widgets()
        self._poll_events()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        mode_row = ttk.Frame(main)
        mode_row.pack(fill="x", pady=4)
        ttk.Label(mode_row, text="输入模式:", width=14).pack(side="left")
        mode_combo = ttk.Combobox(
            mode_row,
            textvariable=self.input_mode_var,
            values=INPUT_MODES,
            state="readonly",
            width=20,
        )
        mode_combo.pack(side="left")
        mode_combo.bind("<<ComboboxSelected>>", lambda _: self._update_input_mode_widgets())

        self.local_row = ttk.Frame(main)
        ttk.Label(self.local_row, text="本地音频文件:", width=14).pack(side="left")
        ttk.Entry(self.local_row, textvariable=self.local_file_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(self.local_row, text="浏览...", command=self.choose_local_file).pack(side="left")

        self.url_row = ttk.Frame(main)
        ttk.Label(self.url_row, text="视频 URL:", width=14).pack(side="left")
        ttk.Entry(self.url_row, textvariable=self.url_var).pack(
            side="left", fill="x", expand=True, padx=6
        )

        output_row = ttk.Frame(main)
        output_row.pack(fill="x", pady=4)
        ttk.Label(output_row, text="输出目录:", width=14).pack(side="left")
        ttk.Entry(output_row, textvariable=self.output_dir_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(output_row, text="浏览...", command=self.choose_output_dir).pack(side="left")

        options = ttk.Frame(main)
        options.pack(fill="x", pady=8)

        ttk.Label(options, text="模型:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        ttk.Combobox(
            options, textvariable=self.model_var, values=MODEL_OPTIONS, state="readonly", width=12
        ).grid(row=0, column=1, padx=(0, 14), sticky="w")

        ttk.Label(options, text="设备:").grid(row=0, column=2, padx=(0, 6), sticky="w")
        ttk.Combobox(
            options, textvariable=self.device_var, values=DEVICE_OPTIONS, state="readonly", width=12
        ).grid(row=0, column=3, padx=(0, 14), sticky="w")

        ttk.Label(options, text="计算类型:").grid(row=0, column=4, padx=(0, 6), sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.compute_var,
            values=COMPUTE_OPTIONS,
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="w")

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=6)
        self.start_button = ttk.Button(actions, text="开始转写", command=self.start_transcription)
        self.start_button.pack(side="left")

        progress_row = ttk.Frame(main)
        progress_row.pack(fill="x", pady=(2, 6))
        ttk.Label(progress_row, text="进度:", width=14).pack(side="left")
        self.progressbar = ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progressbar.pack(side="left", fill="x", expand=True)
        self.progress_label = ttk.Label(progress_row, text="0%")
        self.progress_label.pack(side="left", padx=(8, 0))

        ttk.Label(main, text="运行日志:").pack(anchor="w", pady=(6, 4))
        self.log_text = scrolledtext.ScrolledText(main, wrap="word", height=26, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _update_input_mode_widgets(self) -> None:
        if self.local_row is None or self.url_row is None:
            return

        self.local_row.pack_forget()
        self.url_row.pack_forget()
        if self.input_mode_var.get() == "Local audio file":
            self.local_row.pack(fill="x", pady=4)
        else:
            self.url_row.pack(fill="x", pady=4)

    def choose_local_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择本地音频文件",
            filetypes=AUDIO_FILETYPES,
        )
        if selected:
            self.local_file_var.set(selected)

    def choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            self.output_dir_var.set(selected)

    def append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _queue_log(self, message: str) -> None:
        self.event_queue.put(("log", message))

    def _queue_progress(self, value: int) -> None:
        self.event_queue.put(("progress", max(0, min(100, int(value)))))

    def _poll_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self.append_log(str(payload))
            elif event_type == "progress":
                progress = int(payload)
                self.progress_var.set(progress)
                self.progress_label.config(text=f"{progress}%")

        self.root.after(100, self._poll_events)

    def start_transcription(self) -> None:
        mode_label = self.input_mode_var.get()
        output_dir = self.output_dir_var.get().strip()

        if not output_dir:
            messagebox.showerror("错误", "请先选择输出目录。")
            return

        if mode_label == "Local audio file":
            input_mode = "local"
            input_value = self.local_file_var.get().strip()
            if not input_value:
                messagebox.showerror("错误", "请先选择本地音频文件。")
                return
        else:
            input_mode = "url"
            input_value = self.url_var.get().strip()
            if not input_value:
                messagebox.showerror("错误", "请先输入视频 URL。")
                return

        try:
            ensure_ffmpeg()
            if input_mode == "url":
                ensure_yt_dlp()
        except Exception as exc:
            title = "ffmpeg 不可用" if "ffmpeg" in str(exc) else "依赖缺失"
            messagebox.showerror(title, str(exc))
            self.append_log(f"[FATAL] {exc}")
            return

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "当前已有任务在运行，请等待完成。")
            return

        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.start_button.configure(state="disabled")
        self.append_log("=" * 80)
        self.append_log("开始转写任务...")

        self.worker_thread = threading.Thread(
            target=self._run_task,
            args=(
                input_mode,
                input_value,
                Path(output_dir),
                self.model_var.get(),
                self.device_var.get(),
                self.compute_var.get(),
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_task(
        self,
        input_mode: str,
        input_value: str,
        output_dir: Path,
        model_size: str,
        device: str,
        compute_type: str,
    ) -> None:
        try:
            run_transcription_pipeline(
                input_mode=input_mode,
                input_value=input_value,
                output_dir=output_dir,
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                logger=self._queue_log,
                error_logger=self._queue_log,
                progress_callback=self._queue_progress,
            )
            self._queue_log("任务结束。")
        except Exception as exc:
            self._queue_log(f"[FATAL] {exc}")
            self._queue_log(traceback.format_exc())
        finally:
            self.root.after(0, lambda: self.start_button.configure(state="normal"))


def main() -> None:
    root = tk.Tk()
    _app = TranscriptionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
