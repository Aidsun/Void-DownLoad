"""
Void-DownLoad 主窗口
====================
蓝白色调, 瀑布流卡片列表, 全选/单选/分类筛选
"""
import sys
import asyncio
import os
import time
from pathlib import Path
from functools import partial

from PySide6.QtCore import Qt, QSize, QTimer, QUrl, QPoint, QEvent, Signal
from PySide6.QtGui import (
    QAction, QDesktopServices, QIcon, QFont, QFontDatabase,
    QColor, QPixmap, QPainter, QPen, QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QFileDialog, QScrollArea, QListWidget, QListWidgetItem,
    QProgressBar, QStatusBar, QMessageBox, QSizePolicy,
    QGraphicsDropShadowEffect, QButtonGroup, QToolButton,
    QSpacerItem, QAbstractItemView, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from .core import (
    MediaItem, kind_label, detect_media_kind, KIND_LABELS,
    download_simple, find_chromium_exe,
)
from .workers import ExtractWorker, DownloadWorker
from .widgets import MediaItemWidget, KIND_ICON, TitleBar


CATEGORY_FILTERS = [
    ("all",     "📦 全部"),
    ("video",   "🎬 视频"),
    ("image",   "🖼️ 图片"),
    ("pdf",     "📕 PDF"),
    ("doc",     "📝 文档"),
    ("audio",   "🎵 音频"),
    ("archive", "📦 压缩包"),
]


# ============== 下载进度弹窗 ==============
class DownloadProgressDialog(QDialog):
    """点击底部状态栏时弹出, 实时显示每个文件的下载进度 + 速度."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载进度")
        self.resize(720, 420)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowStaysOnTopHint
        )
        self._tasks: dict[str, dict] = {}  # url -> {name, total, done, started, last_done, last_t}
        # 表
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "进度", "速度", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(2, 220)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # 关闭按钮
        btn = QPushButton("关闭")
        btn.clicked.connect(self.close)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self.table)
        lay.addWidget(btn)
        # 1Hz 刷新速度
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh_speeds)
        self._timer.start()
        self._closed = False

    def closeEvent(self, e):
        self._closed = True
        self._timer.stop()
        super().closeEvent(e)

    def add_task(self, url: str, name: str, total: int):
        if url in self._tasks:
            return
        # 如果有占位行, 先清空
        if self.table.rowCount() == 1:
            first = self.table.item(0, 0)
            if first and first.text() == "(暂无下载任务)":
                self.table.removeRow(0)
        self._tasks[url] = {
            "name": name,
            "total": total,
            "done": 0,
            "started": time.time(),
            "last_done": 0,
            "last_t": time.time(),
            "speed_bps": 0.0,
            "status": "进行中",
        }
        row = self.table.rowCount()
        self.table.insertRow(row)
        item_name = QTableWidgetItem(name)
        item_name.setData(Qt.UserRole, url)  # 用 url 定位行
        self.table.setItem(row, 0, item_name)
        self.table.setItem(row, 1, QTableWidgetItem(self._fmt_size(total)))
        self.table.setItem(row, 2, QTableWidgetItem("0%"))
        self.table.setItem(row, 3, QTableWidgetItem("-"))
        self.table.setItem(row, 4, QTableWidgetItem("进行中"))

    def update_progress(self, url: str, done: int, total: int):
        t = self._tasks.get(url)
        if not t:
            return
        t["done"] = done
        t["total"] = total or t["total"]
        # 找行
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0) and self.table.item(row, 0).data(Qt.UserRole) == url:
                pct = (done / total * 100) if total else 0
                self.table.item(row, 2).setText(f"{done//1024}/{total//1024} KB  ({pct:.0f}%)")
                break

    def finish_task(self, url: str, ok: bool, msg: str = ""):
        t = self._tasks.get(url)
        if not t:
            return
        t["status"] = "完成" if ok else f"失败: {msg}"
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0) and self.table.item(row, 0).data(Qt.UserRole) == url:
                self.table.item(row, 4).setText(t["status"])
                if ok and t["total"]:
                    self.table.item(row, 2).setText(f"{t['total']//1024}/{t['total']//1024} KB  (100%)")
                self.table.item(row, 3).setText("-")
                break

    def _refresh_speeds(self):
        if self._closed:
            return
        now = time.time()
        for url, t in self._tasks.items():
            if t["status"] != "进行中":
                continue
            dt = now - t["last_t"]
            if dt > 0:
                inst_bps = (t["done"] - t["last_done"]) / dt
                # 指数平滑
                t["speed_bps"] = t["speed_bps"] * 0.6 + inst_bps * 0.4 if t["speed_bps"] else inst_bps
                t["last_done"] = t["done"]
                t["last_t"] = now
            # 写表
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0) and self.table.item(row, 0).data(Qt.UserRole) == url:
                    self.table.item(row, 3).setText(self._fmt_speed(t["speed_bps"]))
                    break

    def _fmt_size(self, n: int) -> str:
        if n <= 0:
            return "?"
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {u}"
            n /= 1024
        return f"{n:.1f} TB"

    def _fmt_speed(self, bps: float) -> str:
        if bps <= 0:
            return "-"
        for u in ("B/s", "KB/s", "MB/s", "GB/s"):
            if bps < 1024:
                return f"{bps:.1f} {u}"
            bps /= 1024
        return f"{bps:.1f} TB/s"

    def show_for_task(self, url: str, name: str, total: int):
        self.add_task(url, name, total)
        self.show()
        self.raise_()
        self.activateWindow()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("快抓 — 宝宝专用的资源下载器")
        # Frameless: 内部自定义标题栏
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(900, 640)
        self.resize(1280, 800)   # 默认非最大化, 给个合理初始尺寸
        self._radius = 14       # 圆角半径

        # 数据
        self.all_items: list[MediaItem] = []
        self.shown_items: list[MediaItem] = []
        self._extract_worker: ExtractWorker | None = None
        self._download_workers: list[DownloadWorker] = []
        self._download_progress_dialog: DownloadProgressDialog | None = None
        # url -> worker 映射 (用于查询)
        self._url_to_worker: dict[str, DownloadWorker] = {}
        # 下载统计
        self._dl_total = 0
        self._dl_done = 0
        self._dl_failed = 0
        self._dl_running = False

        # 加载 QSS
        qss_path = Path(__file__).parent / "style.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

        self._build_ui()
        # 首次启动同步预热 chromium
        self._warmup_chromium()
        # 状态
        self._set_status("已就绪 — 粘贴 URL 并点 [开始抓取]")

    # ============== 窗口操作 ==============
    def toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            maximized = self.isMaximized()
            # 全屏时关闭透明背景 + 设置实色背景, 避免露出桌面
            self.setAttribute(Qt.WA_TranslucentBackground, not maximized)
            # 让 QSS [maximized="true"] 选择器生效
            central = self.centralWidget()
            if central:
                central.setProperty("maximized", maximized)
                central.style().unpolish(central)
                central.style().polish(central)
                # 同步 bodyWidget
                for child in central.findChildren(QWidget):
                    if child.objectName() == "bodyWidget":
                        child.setProperty("maximized", maximized)
                        child.style().unpolish(child)
                        child.style().polish(child)
                        break
            self.repaint()
            # 同步标题栏按钮图标
            if hasattr(self, "title_bar"):
                if maximized:
                    self.title_bar.max_btn.setText("❐")
                    self.title_bar.max_btn.setToolTip("还原")
                else:
                    self.title_bar.max_btn.setText("☐")
                    self.title_bar.max_btn.setToolTip("最大化")
        super().changeEvent(e)

    # ============== UI 构建 ==============
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)  # frameless, 标题栏自己处理
        root.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar()
        self.title_bar.attach_window(self)
        root.addWidget(self.title_bar)

        # 主体容器 (留 padding)
        body = QWidget()
        body.setObjectName("bodyWidget")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 0, 12, 12)
        body_lay.setSpacing(0)
        root.addWidget(body, 1)

        # 输入卡片
        self._build_input_card(body_lay)

        # 工具条
        self._build_toolbar(body_lay)

        # 结果区
        self._build_results_area(body_lay)

        # 状态栏 (可点击)
        self._build_status_bar(body_lay)

    def _build_input_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("inputCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴 Bosch-PT / Cliplister 产品页 URL, 回车开始抓取")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.returnPressed.connect(self.start_extract)

        self.extract_btn = QPushButton("🔍 开始抓取")
        self.extract_btn.setObjectName("primaryBtn")
        self.extract_btn.setCursor(Qt.PointingHandCursor)
        self.extract_btn.setFixedWidth(120)
        self.extract_btn.clicked.connect(self.start_extract)

        lay.addWidget(self.url_input, 1)
        lay.addWidget(self.extract_btn)
        parent_layout.addWidget(card)

    def _build_toolbar(self, parent_layout):
        card = QFrame()
        card.setObjectName("toolbarCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        # 分类
        lab1 = QLabel("分类")
        lab1.setStyleSheet("color: #677888; font-size: 12px;")
        self.category_combo = QComboBox()
        for k, lbl in CATEGORY_FILTERS:
            self.category_combo.addItem(lbl, k)
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(lab1)
        lay.addWidget(self.category_combo)
        lay.addSpacing(20)

        # 全选
        self.select_all_cb = QCheckBox("全选")
        self.select_all_cb.setCursor(Qt.PointingHandCursor)
        self.select_all_cb.stateChanged.connect(self._on_select_all_changed)
        lay.addWidget(self.select_all_cb)
        lay.addSpacing(20)

        # 计数
        self.count_lbl = QLabel("0 / 0 项")
        self.count_lbl.setStyleSheet("color: #1E88E5; font-size: 12px; font-weight: 600;")
        lay.addWidget(self.count_lbl)
        lay.addStretch(1)

        # 下载按钮
        self.download_btn = QPushButton("⬇ 下载")
        self.download_btn.setObjectName("primaryBtn")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.start_batch_download)
        lay.addWidget(self.download_btn)

        parent_layout.addWidget(card)

        # 保存路径行
        path_card = QFrame()
        path_card.setObjectName("toolbarCard")
        path_lay = QHBoxLayout(path_card)
        path_lay.setContentsMargins(16, 8, 16, 8)
        path_lay.setSpacing(10)
        lab2 = QLabel("💾 保存到")
        lab2.setStyleSheet("color: #677888; font-size: 12px; font-weight: 600;")
        self.save_path_lbl = QLabel(str(self._get_download_dir()))
        self.save_path_lbl.setStyleSheet(
            "color: #1E88E5; font-size: 13px; font-weight: 500;"
            "background: #F0F5FF; border-radius: 6px; padding: 4px 10px;"
        )
        self.save_path_lbl.setCursor(Qt.PointingHandCursor)
        self.save_path_lbl.setToolTip("点击更换保存目录")
        self.save_path_lbl.mousePressEvent = lambda e: self._browse_save_dir()
        btn_browse = QPushButton("📂 浏览…")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setFixedWidth(90)
        btn_browse.clicked.connect(self._browse_save_dir)
        self.clear_dl_btn = QPushButton("📁 打开目录")
        self.clear_dl_btn.setCursor(Qt.PointingHandCursor)
        self.clear_dl_btn.setFixedWidth(100)
        self.clear_dl_btn.clicked.connect(self._open_download_dir)
        path_lay.addWidget(lab2)
        path_lay.addWidget(self.save_path_lbl, 1)
        path_lay.addWidget(btn_browse)
        path_lay.addWidget(self.clear_dl_btn)
        parent_layout.addWidget(path_card)

    def _build_results_area(self, parent_layout):
        card = QFrame()
        card.setObjectName("resultsCard")
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setObjectName("resultsScroll")

        self.items_host = QWidget()
        self.items_layout = QVBoxLayout(self.items_host)
        self.items_layout.setContentsMargins(12, 12, 12, 12)
        self.items_layout.setSpacing(8)
        self.items_layout.addStretch(1)

        # 空态
        self.empty_lbl = QLabel("📭  还没有抓取到资源\n\n粘贴 URL 并点 [开始抓取]")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color: #AABBCC; font-size: 14px; padding: 80px;")
        self.items_layout.addWidget(self.empty_lbl, 0, Qt.AlignCenter)

        self.scroll.setWidget(self.items_host)
        v.addWidget(self.scroll)
        parent_layout.addWidget(card, 1)

    def _build_status_bar(self, parent_layout):
        """底部状态栏: 点击打开下载进度弹窗."""
        card = QFrame()
        card.setObjectName("statusCard")
        card.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        # 状态行 (可点击)
        self.status_btn = QPushButton("⚡ 就绪")
        self.status_btn.setObjectName("statusBtn")
        self.status_btn.setFlat(True)
        self.status_btn.setCursor(Qt.PointingHandCursor)
        self.status_btn.setToolTip("点击查看下载进度")
        self.status_btn.clicked.connect(self._open_download_dialog)

        # 进度条 (下载时显示)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(16)
        self.progress.setMinimumWidth(200)
        self.progress.setObjectName("dlProgress")

        lay.addWidget(self.status_btn)
        lay.addStretch(1)
        lay.addWidget(self.progress)
        parent_layout.addWidget(card)

    # ============== 保存路径管理 ==============
    def _get_download_dir(self) -> Path:
        """获取当前下载目录，默认桌面/VoidDownloader/"""
        saved = getattr(self, '_download_dir', None)
        if saved:
            return saved
        default = Path.home() / "Desktop" / "VoidDownloader"
        default.mkdir(parents=True, exist_ok=True)
        self._download_dir = default
        return default

    def _browse_save_dir(self, _=None):
        chosen = QFileDialog.getExistingDirectory(
            self, "选择下载保存目录",
            str(self._get_download_dir()),
        )
        if chosen:
            self._download_dir = Path(chosen)
            self.save_path_lbl.setText(str(self._download_dir))

    def _open_download_dir(self, _=None):
        try:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._get_download_dir()))
            )
        except Exception:
            pass

    def start_extract(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先粘贴 URL")
            return
        if self._extract_worker and self._extract_worker.isRunning():
            QMessageBox.information(self, "提示", "正在抓取中, 请稍候")
            return

        self.extract_btn.setEnabled(False)
        self.extract_btn.setText("⏳ 抓取中…")
        self._set_status(f"正在抓取: {url[:60]}…")
        self._clear_items()

        self._extract_worker = ExtractWorker(url)
        self._extract_worker.progress.connect(self._on_extract_progress)
        self._extract_worker.log.connect(self._on_extract_log)
        self._extract_worker.finished_with_items.connect(self._on_extract_finished)
        self._extract_worker.failed.connect(self._on_extract_failed)
        self._extract_worker.start()

    def _on_extract_progress(self, msg: str):
        self._set_status(msg)

    def _on_extract_log(self, msg: str):
        pass  # silent

    def _on_extract_finished(self, items: list):
        self.extract_btn.setEnabled(True)
        self.extract_btn.setText("🔍 开始抓取")
        self._clear_items()
        self.all_items = items
        # 自动选中第一个视频 (方便用户)
        videos = [i for i in items if i.kind == "video"]
        if videos:
            for it in videos:
                it.selected = True
        self._refresh_view()
        self._update_count_lbl()
        if items:
            self._set_status(f"✓ 提取完成: {len(items)} 个资源")
        else:
            self._set_status("⚠ 未提取到资源, 检查 URL 或网络")

    def _on_extract_failed(self, err: str):
        self.extract_btn.setEnabled(True)
        self.extract_btn.setText("🔍 开始抓取")
        self._set_status(f"✗ 抓取失败: {err}")

    def _on_filter_changed(self, _idx: int):
        self._refresh_view()

    def _on_select_all_changed(self, state: int):
        """全选 checkbox 变化: 同步当前筛选下所有 item 的 selected 状态."""
        # state: 0=Unchecked, 1=PartiallyChecked, 2=Checked
        # 如果是部分选, 不改变所有项 (避免误取消)
        if int(state) == 1:  # PartiallyChecked -> 不动
            return
        checked = (int(state) == 2)  # 2=Checked
        # 同步数据层
        for it in self.shown_items:
            it.selected = checked
        # 同步 UI (emit=False 避免循环)
        for i in range(self.items_layout.count()):
            w = self.items_layout.itemAt(i).widget()
            if isinstance(w, MediaItemWidget):
                w.set_selected(checked, emit=False)
        self._update_count_lbl()

    def _on_item_toggled(self, item: MediaItem, checked: bool):
        """单个 item 状态变化: 同步全选 checkbox + 计数 + 按钮."""
        item.selected = checked
        # 全选 checkbox 状态
        all_sel = bool(self.shown_items) and all(i.selected for i in self.shown_items)
        any_sel = any(i.selected for i in self.shown_items)
        self.select_all_cb.blockSignals(True)
        if all_sel:
            self.select_all_cb.setCheckState(Qt.Checked)
        elif any_sel:
            self.select_all_cb.setCheckState(Qt.PartiallyChecked)
        else:
            self.select_all_cb.setCheckState(Qt.Unchecked)
        self.select_all_cb.blockSignals(False)
        self._update_count_lbl()

    # ============== 视图刷新 ==============
    def _refresh_view(self):
        # 清空 (除了 stretch 和 empty)
        for i in reversed(range(self.items_layout.count())):
            w = self.items_layout.itemAt(i).widget()
            if w is None or w is self.empty_lbl:
                continue
            self.items_layout.removeWidget(w)
            w.deleteLater()

        # 当前 filter
        idx = self.category_combo.currentIndex()
        cat = self.category_combo.itemData(idx) if idx >= 0 else "all"
        if cat == "all":
            self.shown_items = list(self.all_items)
        else:
            self.shown_items = [i for i in self.all_items if i.kind == cat]

        if not self.all_items:
            self.empty_lbl.setVisible(True)
            self.empty_lbl.setText("📭  还没有抓取到资源\n\n粘贴 URL 并点 [开始抓取]")
        elif not self.shown_items:
            self.empty_lbl.setVisible(True)
            self.empty_lbl.setText("(当前分类下没有资源)")
        else:
            self.empty_lbl.setVisible(False)
            for it in self.shown_items:
                w = MediaItemWidget(it)
                w.toggled.connect(self._on_item_toggled)
                # 数据层 selected → UI 同步 (emit=False, GUI 手动调 _on_item_toggled)
                if it.selected:
                    w.set_selected(True, emit=False)
                # 插入到 stretch 之前
                self.items_layout.insertWidget(self.items_layout.count() - 1, w)
        # 全选 checkbox 同步
        all_sel = bool(self.shown_items) and all(i.selected for i in self.shown_items)
        any_sel = any(i.selected for i in self.shown_items)
        self.select_all_cb.blockSignals(True)
        if all_sel:
            self.select_all_cb.setCheckState(Qt.Checked)
        elif any_sel:
            self.select_all_cb.setCheckState(Qt.PartiallyChecked)
        else:
            self.select_all_cb.setCheckState(Qt.Unchecked)
        self.select_all_cb.blockSignals(False)

    def _clear_items(self):
        self.all_items.clear()
        self.shown_items.clear()
        self._refresh_view()
        self._update_count_lbl()

    def _update_count_lbl(self):
        sel = sum(1 for i in self.all_items if i.selected)
        total = len(self.all_items)
        # 计数
        self.count_lbl.setText(f"已选 {sel} / {total} 项")
        # 按钮文案
        if sel == 0:
            self.download_btn.setText("⬇ 下载")
            self.download_btn.setEnabled(False)
        elif sel >= 1:
            self.download_btn.setText(f"⬇ 批量下载 ({sel})" if sel > 1 else "⬇ 下载")
            self.download_btn.setEnabled(True)

    # ============== 下载 ==============
    def start_batch_download(self):
        selected = [i for i in self.all_items if i.selected]
        if not selected:
            return
        dest_dir = self._get_download_dir()

        # 弹进度窗
        if not self._download_progress_dialog:
            self._download_progress_dialog = DownloadProgressDialog(self)
        for it in selected:
            size = it.size or 0
            self._download_progress_dialog.add_task(it.url, it.display_name(), size)
        self._download_progress_dialog.show()
        self._download_progress_dialog.raise_()
        self._download_progress_dialog.activateWindow()

        # 并发 3 worker
        self._pending = list(selected)
        self._dl_total = len(selected)
        self._dl_done = 0
        self._dl_failed = 0
        self._dl_running = True
        self._dl_max_concurrent = 3
        self._dl_active = 0
        self._set_status(f"⏳ 开始下载 {self._dl_total} 个文件 (并发 3)…")
        self.progress.setVisible(True)
        self.progress.setRange(0, self._dl_total)
        self.progress.setValue(0)
        self.download_btn.setEnabled(False)
        # 启动最多 3 个
        for _ in range(self._dl_max_concurrent):
            if not self._download_next():
                break

    def _download_next(self) -> bool:
        """启动下一个下载. 返回 True 表示启动了, False 表示没任务了."""
        if not self._pending:
            return False
        it = self._pending.pop(0)
        dest_dir = self._get_download_dir()
        w = DownloadWorker(it, dest_dir)
        w.progress.connect(partial(self._on_dl_progress, url=it.url))
        w.finished_with_path.connect(self._on_dl_done)
        w.failed.connect(self._on_dl_failed)
        # 完成后自动从 worker 列表里移除
        w.finished.connect(lambda: self._download_workers.remove(w) if w in self._download_workers else None)
        self._download_workers.append(w)
        self._url_to_worker[it.url] = w
        self._dl_active += 1
        w.start()
        return True

    def _on_dl_progress(self, done: int, total: int, url: str):
        if self._download_progress_dialog:
            self._download_progress_dialog.update_progress(url, done, total)

    def _on_dl_done(self, url: str, dest: str):
        self._dl_done += 1
        self._dl_active -= 1
        self.progress.setValue(self._dl_done)
        self._set_status(f"⏳ 进度: {self._dl_done}/{self._dl_total} (失败 {self._dl_failed})")
        if self._download_progress_dialog:
            self._download_progress_dialog.finish_task(url, ok=True)
        self._url_to_worker.pop(url, None)
        # 启动下一个 (或结束)
        if not self._download_next():
            if self._dl_active == 0:
                self._on_all_downloads_done()

    def _on_dl_failed(self, url: str, err: str):
        self._dl_failed += 1
        self._dl_done += 1
        self._dl_active -= 1
        self.progress.setValue(self._dl_done)
        self._set_status(f"⏳ 进度: {self._dl_done}/{self._dl_total} (失败 {self._dl_failed})")
        if self._download_progress_dialog:
            self._download_progress_dialog.finish_task(url, ok=False, msg=err)
        self._url_to_worker.pop(url, None)
        if not self._download_next():
            if self._dl_active == 0:
                self._on_all_downloads_done()

    def _on_all_downloads_done(self):
        self._dl_running = False
        self.progress.setVisible(False)
        if self._dl_failed == 0:
            self._set_status(f"✓ 下载完成: {self._dl_done} 个文件")
        else:
            self._set_status(f"⚠ 下载结束: {self._dl_done-self._dl_failed} 成功, {self._dl_failed} 失败")
        self.download_btn.setEnabled(True)
        self._update_count_lbl()
        # 自动打开下载目录
        self._open_download_dir()

    # ============== 状态栏 / 弹窗 ==============
    def _open_download_dialog(self):
        """点击状态栏: 打开下载进度弹窗 (即使没有任务也显示, 让用户看到状态)."""
        if not self._download_progress_dialog:
            self._download_progress_dialog = DownloadProgressDialog(self)
        d = self._download_progress_dialog
        if not d._tasks:
            # 空状态: 提示一下
            d.table.setRowCount(1)
            d.table.setItem(0, 0, QTableWidgetItem("(暂无下载任务)"))
            for c in range(1, 5):
                d.table.setItem(0, c, QTableWidgetItem(""))
        d.show()
        d.raise_()
        d.activateWindow()

    def _set_status(self, msg: str):
        self.status_btn.setText(f"⚡ {msg}")
        if self._dl_running:
            self.status_btn.setStyleSheet("color: #FFA000; font-size: 12px; font-weight: 600; text-align: left;")
        elif msg.startswith("✓"):
            self.status_btn.setStyleSheet("color: #43A047; font-size: 12px; font-weight: 600; text-align: left;")
        elif msg.startswith("✗") or msg.startswith("⚠"):
            self.status_btn.setStyleSheet("color: #E53935; font-size: 12px; font-weight: 600; text-align: left;")
        else:
            self.status_btn.setStyleSheet("color: #455A64; font-size: 12px; text-align: left;")

    # ============== 启动 / 设置 ==============
    def _warmup_chromium(self):
        try:
            find_chromium_exe()
        except Exception:
            pass

    def _restore_settings(self):
        pass

    def paintEvent(self, e):
        """绘制圆角矩形背景 (非全屏时)."""
        if not self.isMaximized():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            color = QColor("#F4F8FD")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            r = self.rect()
            painter.drawRoundedRect(r, self._radius, self._radius)
            painter.end()
        super().paintEvent(e)

    def closeEvent(self, e):
        # 杀掉下载线程
        for w in self._download_workers:
            try:
                w.cancel()
                w.wait(2000)
            except Exception:
                pass
        if self._download_progress_dialog:
            self._download_progress_dialog.close()
        super().closeEvent(e)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("快抓")
    app.setOrganizationName("Aidsun")
    f = QFont("Microsoft YaHei", 10)
    app.setFont(f)
    qss = Path(__file__).parent / "style.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
