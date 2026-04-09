#!/usr/bin/env python3
"""Simple Tkinter GUI for video transcription backend."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from transcribe_videos import ensure_ffmpeg, run_transcription_pipeline

MODEL_OPTIONS = ["tiny", "base", "small", "medium", "large"]
DEVICE_OPTIONS = ["cuda", "cpu"]
COMPUTE_OPTIONS = ["float16", "int8"]


class TranscriptionGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("视频批量转写工具 (faster-whisper)")
        self.root.geometry("900x620")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.model_var = tk.StringVar(value="small")
        self.device_var = tk.StringVar(value="cuda")
        self.compute_var = tk.StringVar(value="float16")

        self._build_ui()
        self._poll_logs()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        # Input folder row
        input_row = ttk.Frame(main)
        input_row.pack(fill="x", pady=4)
        ttk.Label(input_row, text="输入视频目录:", width=14).pack(side="left")
        ttk.Entry(input_row, textvariable=self.input_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(input_row, text="浏览...", command=self.choose_input_dir).pack(side="left")

        # Output folder row
        output_row = ttk.Frame(main)
        output_row.pack(fill="x", pady=4)
        ttk.Label(output_row, text="输出目录:", width=14).pack(side="left")
        ttk.Entry(output_row, textvariable=self.output_dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(output_row, text="浏览...", command=self.choose_output_dir).pack(side="left")

        # Options row
        options = ttk.Frame(main)
        options.pack(fill="x", pady=8)

        ttk.Label(options, text="模型:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        ttk.Combobox(options, textvariable=self.model_var, values=MODEL_OPTIONS, state="readonly", width=12).grid(
            row=0, column=1, padx=(0, 14), sticky="w"
        )

        ttk.Label(options, text="设备:").grid(row=0, column=2, padx=(0, 6), sticky="w")
        ttk.Combobox(options, textvariable=self.device_var, values=DEVICE_OPTIONS, state="readonly", width=12).grid(
            row=0, column=3, padx=(0, 14), sticky="w"
        )

        ttk.Label(options, text="计算类型:").grid(row=0, column=4, padx=(0, 6), sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.compute_var,
            values=COMPUTE_OPTIONS,
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="w")

        # Start button
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=4)
        self.start_button = ttk.Button(actions, text="开始转写", command=self.start_transcription)
        self.start_button.pack(side="left")

        # Log area
        ttk.Label(main, text="运行日志:").pack(anchor="w", pady=(10, 4))
        self.log_text = scrolledtext.ScrolledText(main, wrap="word", height=24, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def choose_input_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择输入视频目录")
        if selected:
            self.input_dir_var.set(selected)

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
        self.log_queue.put(message)

    def _poll_logs(self) -> None:
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.append_log(msg)
        self.root.after(100, self._poll_logs)

    def start_transcription(self) -> None:
        input_dir = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not input_dir:
            messagebox.showerror("错误", "请先选择输入视频目录。")
            return
        if not output_dir:
            messagebox.showerror("错误", "请先选择输出目录。")
            return

        try:
            ensure_ffmpeg()
        except Exception as exc:
            messagebox.showerror("ffmpeg 不可用", str(exc))
            self.append_log(f"[FATAL] {exc}")
            return

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "当前已有任务在运行，请等待完成。")
            return

        self.start_button.configure(state="disabled")
        self.append_log("=" * 80)
        self.append_log("开始转写任务...")

        self.worker_thread = threading.Thread(
            target=self._run_task,
            args=(Path(input_dir), Path(output_dir), self.model_var.get(), self.device_var.get(), self.compute_var.get()),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_task(
        self,
        input_dir: Path,
        output_dir: Path,
        model_size: str,
        device: str,
        compute_type: str,
    ) -> None:
        try:
            run_transcription_pipeline(
                input_dir=input_dir,
                output_dir=output_dir,
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                logger=self._queue_log,
                error_logger=self._queue_log,
            )
            self._queue_log("任务结束。")
        except Exception as exc:
            self._queue_log(f"[FATAL] {exc}")
            self._queue_log(traceback.format_exc())
        finally:
            self.root.after(0, lambda: self.start_button.configure(state="normal"))


def main() -> None:
    root = tk.Tk()
    app = TranscriptionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
