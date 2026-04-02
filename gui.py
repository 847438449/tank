"""Tkinter GUI for Windows Japanese real-time transcription."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from file_writer import TranscriptFileWriter


class TranscriberGUI:
    def __init__(
        self,
        on_start: Callable[[str, bool], bool],
        on_stop: Callable[[], None],
    ) -> None:
        self.on_start = on_start
        self.on_stop = on_stop

        self.root = tk.Tk()
        self.root.title("Windows 系统音频日语实时转写（高精度）")
        self.root.geometry("980x700")

        self._build_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def run(self) -> None:
        self.root.mainloop()

    def _build_widgets(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="保存路径:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self._default_save_path())
        ttk.Entry(top, textvariable=self.path_var, width=74).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="选择", command=self._choose_path).pack(side=tk.LEFT)

        ctrl = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        ctrl.pack(fill=tk.X)

        self.start_btn = ttk.Button(ctrl, text="开始", command=self._start)
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(ctrl, text="停止", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        self.export_srt_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="可选导出 SRT", variable=self.export_srt_var).pack(side=tk.LEFT, padx=8)

        self.status_var = tk.StringVar(value="状态：未启动")
        ttk.Label(ctrl, textvariable=self.status_var).pack(side=tk.LEFT, padx=20)

        panes = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        realtime_frame = ttk.Labelframe(panes, text="实时预览（快速识别）")
        self.realtime_text = ScrolledText(realtime_frame, wrap=tk.WORD, font=("Consolas", 11), height=12)
        self.realtime_text.pack(fill=tk.BOTH, expand=True)
        panes.add(realtime_frame, weight=1)

        final_frame = ttk.Labelframe(panes, text="最终段落（高精度写入）")
        self.final_text = ScrolledText(final_frame, wrap=tk.WORD, font=("Consolas", 11), height=16)
        self.final_text.pack(fill=tk.BOTH, expand=True)
        panes.add(final_frame, weight=1)

    def _default_save_path(self) -> str:
        return str(Path.cwd() / TranscriptFileWriter.default_filename())

    def _choose_path(self) -> None:
        p = filedialog.asksaveasfilename(
            title="选择保存路径",
            defaultextension=".txt",
            initialfile=TranscriptFileWriter.default_filename(),
            filetypes=[("Text", "*.txt")],
        )
        if p:
            self.path_var.set(p)

    def _start(self) -> None:
        path = self.path_var.get().strip()
        if not path:
            self.set_status("状态：请先选择保存路径")
            return

        ok = self.on_start(path, self.export_srt_var.get())
        if ok:
            self.set_running_ui(True)
            self.set_status("状态：运行中")

    def _stop(self) -> None:
        self.on_stop()
        self.set_running_ui(False)
        self.set_status("状态：已停止")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def append_preview(self, timestamp: str, text: str) -> None:
        self.realtime_text.insert(tk.END, f"{timestamp}\n{text}\n\n")
        self.realtime_text.see(tk.END)

    def append_final(self, timestamp: str, text: str) -> None:
        self.final_text.insert(tk.END, f"{timestamp}\n{text}\n\n")
        self.final_text.see(tk.END)

    def set_running_ui(self, running: bool) -> None:
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    def _on_close(self) -> None:
        self.on_stop()
        self.root.destroy()
