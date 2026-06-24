"""
Void-DownLoad 自定义控件
=========================
"""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QSizePolicy,
    QGraphicsDropShadowEffect, QWidget, QSpacerItem, QToolButton,
)

from .core import MediaItem, kind_label


# 各类资源的 emoji icon
KIND_ICON = {
    "video":   "🎬",
    "image":   "🖼️",
    "audio":   "🎵",
    "pdf":     "📕",
    "doc":     "📝",
    "archive": "📦",
    "web":     "🌐",
    "other":   "🔗",
}


class MediaItemWidget(QFrame):
    """单条资源卡片 (列表项).

    交互模式 (仿 macOS Finder):
    - 点 checkbox 区域 -> 切换该条选中
    - 点卡片其它区域 -> 同样切换该条选中
    - 在全选状态下点已选中项 -> 取消该条
    - 外层 set_selected(sel, emit=True/False) 可强制设状态 (全选时用 emit=False)
    """
    toggled = Signal(object, bool)  # (MediaItem, checked)

    def __init__(self, item: MediaItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._selected = False
        self.setObjectName("mediaCard")
        self.setProperty("selected", False)
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(30, 136, 229, 25))
        self.setGraphicsEffect(shadow)

        # 布局: [icon] [name+url] [kind] [size] [checkbox]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        # icon
        self.icon_lbl = QLabel(KIND_ICON.get(item.kind, "🔗"))
        self.icon_lbl.setObjectName("itemIcon")
        self.icon_lbl.setFixedWidth(34)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 名字 + URL
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        self.name_lbl = QLabel(item.display_name())
        self.name_lbl.setObjectName("itemName")
        self.url_lbl = QLabel(item.url[:90] + ("..." if len(item.url) > 90 else ""))
        self.url_lbl.setObjectName("itemUrl")
        self.name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.url_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        name_col.addWidget(self.name_lbl)
        name_col.addWidget(self.url_lbl)

        # 类型
        self.kind_lbl = QLabel(kind_label(item.kind))
        self.kind_lbl.setObjectName("itemKind")
        self.kind_lbl.setFixedWidth(110)
        self.kind_lbl.setAlignment(Qt.AlignCenter)
        self.kind_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 大小
        self.size_lbl = QLabel(item.size_str())
        self.size_lbl.setObjectName("itemSize")
        self.size_lbl.setFixedWidth(90)
        self.size_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.size_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # checkbox
        self.cb = QCheckBox()
        self.cb.setFixedSize(22, 22)
        self.cb.setCursor(Qt.PointingHandCursor)
        self.cb.toggled.connect(self._on_cb_toggled)

        lay.addWidget(self.icon_lbl)
        lay.addLayout(name_col, 1)
        lay.addWidget(self.kind_lbl)
        lay.addWidget(self.size_lbl)
        lay.addWidget(self.cb)

    def set_selected(self, sel: bool, emit: bool = True):
        """设置选中状态. emit=False 用于全选按钮批量设置, 不触发 toggled 信号."""
        if self._selected == sel:
            return
        self._selected = sel
        self.setProperty("selected", sel)
        # 重设样式
        self.style().unpolish(self)
        self.style().polish(self)
        # 同步 checkbox (blockSignals 避免循环)
        if self.cb.isChecked() != sel:
            self.cb.blockSignals(True)
            self.cb.setChecked(sel)
            self.cb.blockSignals(False)
        if emit:
            self.toggled.emit(self.item, sel)

    def is_selected(self) -> bool:
        return self._selected

    def _on_cb_toggled(self, checked: bool):
        # checkbox 触发: 同步 _selected 和样式, 通知 GUI
        if self._selected == checked:
            return
        self._selected = checked
        self.setProperty("selected", checked)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.emit(self.item, checked)

    def mousePressEvent(self, e: QMouseEvent):
        # 点空白也切换选中 (点 checkbox 时让 cb 自己处理)
        if e.button() == Qt.LeftButton and not self.cb.underMouse():
            self.set_selected(not self._selected, emit=True)
        super().mousePressEvent(e)


class CategoryButton(QCheckBox):
    """带计数的类别按钮 (替代 dropdown 也能用, 此处用 dropdown)."""
    pass


# ============== 自定义标题栏 ==============
class WindowButton(QToolButton):
    """标题栏上的系统按钮 (minimize / maximize / close)."""
    def __init__(self, text: str, hover_color: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setFixedSize(40, 32)
        self.setCursor(Qt.PointingHandCursor)
        self._hover_color = hover_color
        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: white;
                font-size: 14px;
                border: none;
                font-family: "Segoe UI Symbol", "Microsoft YaHei";
            }}
            QToolButton:hover {{
                background: {hover_color};
            }}
            QToolButton:pressed {{
                background: {hover_color};
            }}
        """)


class TitleBar(QFrame):
    """自定义标题栏: 拖动窗口 + 最小化/最大化/关闭 + 居中标题."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self.setFixedHeight(48)
        self.setObjectName("titleBar")
        self._drag_pos = None
        self._is_dragging = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 8, 0)
        lay.setSpacing(0)

        # logo
        self.icon_lbl = QLabel("⚡")
        self.icon_lbl.setStyleSheet("font-size: 22px; color: white; background: transparent;")
        self.icon_lbl.setFixedWidth(34)
        self.icon_lbl.setAlignment(Qt.AlignCenter)

        # 标题
        self.title_lbl = QLabel("Void Downloader")
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: white; background: transparent; padding-left: 6px;")
        self.sub_lbl = QLabel("Bosch-PT / Cliplister 资源提取")
        self.sub_lbl.setStyleSheet("font-size: 10px; color: rgba(255,255,255,0.7); background: transparent; padding-left: 6px;")
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.sub_lbl)

        lay.addWidget(self.icon_lbl)
        lay.addLayout(title_col)
        lay.addStretch(1)

        # 系统按钮
        self.min_btn = WindowButton("─", "rgba(255,255,255,40)")
        self.max_btn = WindowButton("☐", "rgba(255,255,255,40)")
        self.close_btn = WindowButton("✕", "#E81123")
        self.min_btn.setToolTip("最小化")
        self.max_btn.setToolTip("最大化/还原")
        self.close_btn.setToolTip("关闭")

        lay.addWidget(self.min_btn)
        lay.addWidget(self.max_btn)
        lay.addWidget(self.close_btn)

    def attach_window(self, win: QWidget):
        """绑定主窗口信号."""
        self._parent_window = win
        self.min_btn.clicked.connect(win.showMinimized)
        self.max_btn.clicked.connect(win.toggle_maximized)
        self.close_btn.clicked.connect(win.close)
        # 监听窗口状态变化更新按钮图标
        if hasattr(win, "windowStateChanged"):
            win.windowStateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, state):
        if state & Qt.WindowMaximized:
            self.max_btn.setText("❐")
            self.max_btn.setToolTip("还原")
        else:
            self.max_btn.setText("☐")
            self.max_btn.setToolTip("最大化")

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._parent_window is not None:
            # 排除系统按钮区域
            if not (self.min_btn.underMouse() or self.max_btn.underMouse() or self.close_btn.underMouse()):
                self._drag_pos = e.globalPosition().toPoint() - self._parent_window.frameGeometry().topLeft()
                self._is_dragging = True
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._is_dragging and self._drag_pos and self._parent_window is not None:
            # 最大化状态下拖动要先还原
            if self._parent_window.isMaximized():
                # 还原并保持光标位置比例
                rect = self._parent_window.normalGeometry()
                ratio = e.position().x() / self.width()
                self._parent_window.toggle_maximized()  # 还原
                self._parent_window.move(e.globalPosition().toPoint().x() - int(rect.width() * ratio), 0)
                self._drag_pos = QPoint(int(rect.width() * ratio), int(e.position().y()))
            else:
                self._parent_window.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._is_dragging = False
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._parent_window is not None:
            if not (self.min_btn.underMouse() or self.max_btn.underMouse() or self.close_btn.underMouse()):
                self._parent_window.toggle_maximized()
                e.accept()
                return
        super().mouseDoubleClickEvent(e)
