#!/usr/bin/env python3
"""LecturePipe GUI — YouTube URL 입력 창"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lecturepipe import load_config, process_single


class LecturePipeGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LecturePipe")
        self.root.resizable(False, False)

        # 창 크기 & 중앙 배치
        w, h = 520, 420
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 3
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.config = load_config()
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill='both', expand=True)

        # URL 입력
        ttk.Label(frame, text="YouTube URL:").pack(anchor='w')
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(frame, textvariable=self.url_var, width=60)
        url_entry.pack(fill='x', pady=(2, 8))
        url_entry.focus()
        url_entry.bind('<Return>', lambda e: self._run())

        # 옵션 체크박스
        opt_frame = ttk.Frame(frame)
        opt_frame.pack(fill='x', pady=(0, 8))

        self.no_translate = tk.BooleanVar()
        self.no_summary = tk.BooleanVar()
        self.no_visual = tk.BooleanVar()
        self.terminal_only = tk.BooleanVar()

        ttk.Checkbutton(opt_frame, text="번역 안 함", variable=self.no_translate).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(opt_frame, text="요약 안 함", variable=self.no_summary).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(opt_frame, text="캡처 안 함", variable=self.no_visual).pack(side='left', padx=(0, 12))
        ttk.Checkbutton(opt_frame, text="터미널만 출력", variable=self.terminal_only).pack(side='left')

        # 실행 버튼
        self.run_btn = ttk.Button(frame, text="실행", command=self._run)
        self.run_btn.pack(fill='x', pady=(0, 8))

        # 로그 출력
        ttk.Label(frame, text="진행 상황:").pack(anchor='w')
        self.log = scrolledtext.ScrolledText(frame, height=14, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True)

    def _log(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
        self.log.config(state='normal')
        self.log.insert('end', msg + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def _run(self):
        url = self.url_var.get().strip()
        if not url:
            return

        self.run_btn.config(state='disabled')
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')

        # 백그라운드 스레드에서 실행
        thread = threading.Thread(target=self._process, args=(url,), daemon=True)
        thread.start()

    def _process(self, url: str):
        # stderr를 로그로 리다이렉트
        old_stderr = sys.stderr
        sys.stderr = LogWriter(self._log)

        try:
            success = process_single(
                url, self.config,
                terminal_only=self.terminal_only.get(),
                no_translate=self.no_translate.get(),
                no_summary=self.no_summary.get(),
                no_visual=self.no_visual.get(),
            )
            if success:
                self._log("\n완료!")
            else:
                self._log("\n처리 실패.")
        except Exception as e:
            self._log(f"\n오류: {e}")
        finally:
            sys.stderr = old_stderr
            self.root.after(0, lambda: self.run_btn.config(state='normal'))

    def run(self):
        self.root.mainloop()


class LogWriter:
    """stderr 출력을 GUI 로그로 전달하는 래퍼."""
    def __init__(self, callback):
        self.callback = callback
        self.buffer = ''

    def write(self, msg):
        self.buffer += msg
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.strip():
                self.callback(line.strip())

    def flush(self):
        if self.buffer.strip():
            self.callback(self.buffer.strip())
            self.buffer = ''


if __name__ == '__main__':
    LecturePipeGUI().run()
