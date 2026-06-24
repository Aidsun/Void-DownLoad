"""
后台任务线程
============
放在独立模块避免 QObject 跨线程坑
"""
import asyncio
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .core import (
    MediaItem, extract_via_playwright, download_simple,
    find_chromium_exe,
)


class ExtractWorker(QThread):
    """后台提取资源."""
    log = Signal(str)
    progress = Signal(str)
    finished_with_items = Signal(list)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.progress.emit("正在启动 headless Chromium…")
            chrome = find_chromium_exe()
            if chrome:
                self.log.emit(f"chromium: {chrome}")
            self.progress.emit("正在打开页面并触发 jwplayer…")
            items = asyncio.run(extract_via_playwright(self.url, log=lambda s: self.log.emit(s)))
            self.progress.emit(f"✓ 提取完成: {len(items)} 个资源")
            self.finished_with_items.emit(items)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class DownloadWorker(QThread):
    """单文件下载."""
    progress = Signal(int, int)         # done, total
    finished_with_path = Signal(str, str)  # (item_url, dest_path)
    failed = Signal(str, str)           # (item_url, err)

    def __init__(self, item: MediaItem, dest_dir: Path, parent=None):
        super().__init__(parent)
        self.item = item
        self.dest_dir = dest_dir
        self._cancelled = False
        # 节流 progress 回调 (避免 GUI 卡顿)
        self._last_emit = 0.0

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
            name = self.item.display_name()
            if not Path(name).suffix and self.item.kind == "video":
                name += ".mp4"
            dest = self.dest_dir / name
            i = 1
            while dest.exists():
                stem, suf = dest.stem, dest.suffix
                dest = self.dest_dir / f"{stem}({i}){suf}"
                i += 1

            def cb(done, total):
                # 节流: 100ms 一次
                now = time.time()
                if not self._cancelled and (now - self._last_emit) > 0.1:
                    self.progress.emit(done, total)
                    self._last_emit = now

            download_simple(
                self.item.url, dest,
                referer=self.item.source_page,
                progress_cb=cb,
            )
            # 结束时再发一次完整进度
            if not self._cancelled:
                self.progress.emit(self.item.size or 0, self.item.size or 0)
            self.finished_with_path.emit(self.item.url, str(dest))
        except Exception as e:
            self.failed.emit(self.item.url, f"{type(e).__name__}: {e}")


class DownloadPool(QObject if False else object):
    """并发下载池: 3 worker 同时跑, 一个完成立即启动下一个.

    信号:
        progress(url, done, total)
        item_done(url, dest)
        item_failed(url, err)
        pool_done(success_count, failed_count)
    """
    # 不用 QObject, 用简单的 thread-safe 队列
    pass
