"""Tkinter GUI for controlling transcription workflow."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Optional

from file_writer import TranscriptFileWriter


class TranscriberGUI:
    def __init__(
        self,
        on_start: Callable[[str], None],
        on_stop: Callable[[], None],
    ) -> None:
        self.on_start = on_start
        self.on_stop = on_stop

        self.root = tk.Tk()
        self.root.title("Windows 系统音频日语转写工具")
        self.root.geometry("860x560")

        self._build_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def run(self) -> None:
        self.root.mainloop()

    def _build_widgets(self) -> None:
        frm_top = ttk.Frame(self.root, padding=10)
        frm_top.pack(fill=tk.X)

        ttk.Label(frm_top, text="保存路径:").pack(side=tk.LEFT)

        self.path_var = tk.StringVar(value=self._default_save_path())
        self.path_entry = ttk.Entry(frm_top, textvariable=self.path_var, width=70)
        self.path_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(frm_top, text="选择", command=self._choose_path).pack(side=tk.LEFT)

        frm_btn = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        frm_btn.pack(fill=tk.X)

        self.start_btn = ttk.Button(frm_btn, text="开始", command=self._start)
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(frm_btn, text="停止", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        self.status_var = tk.StringVar(value="状态：未启动")
        ttk.Label(frm_btn, textvariable=self.status_var).pack(side=tk.LEFT, padx=20)

        frm_text = ttk.Frame(self.root, padding=10)
        frm_text.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm_text, text="实时转写输出:").pack(anchor=tk.W)
        self.output_text = ScrolledText(frm_text, wrap=tk.WORD, font=("Consolas", 11))
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    def _default_save_path(self) -> str:
        filename = TranscriptFileWriter.default_filename()
        return str(Path.cwd() / filename)

    def _choose_path(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="选择保存路径",
            defaultextension=".txt",
            initialfile=TranscriptFileWriter.default_filename(),
            filetypes=[("Text", "*.txt")],
        )
        if file_path:
            self.path_var.set(file_path)

    def _start(self) -> None:
        target = self.path_var.get().strip()
        if not target:
            self.set_status("状态：请先选择保存路径")
            return

        self.on_start(target)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.set_status("状态：运行中")

    def _stop(self) -> None:
        self.on_stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.set_status("状态：已停止")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def append_text(self, line: str) -> None:
        self.output_text.insert(tk.END, line + "\n")
        self.output_text.see(tk.END)

    def _on_close(self) -> None:
        self.on_stop()
        self.root.destroy()

    def set_running_ui(self, running: bool) -> None:
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
