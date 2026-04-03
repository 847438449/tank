from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QPropertyAnimation, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class OverlayWindow(QWidget):
    signal_show_message = Signal(str)
    signal_close_overlay = Signal()

    def __init__(
        self,
        width: int = 420,
        height: int = 140,
        offset_x: int = 24,
        offset_y: int = 24,
        visible_ms: int = 5000,
        fade_ms: int = 600,
    ) -> None:
        super().__init__()
        self.resize(width, height)
        self.setMinimumSize(280, 96)

        self.offset_x = offset_x
        self.offset_y = offset_y
        self.visible_ms = visible_ms
        self.fade_ms = fade_ms

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(self.fade_ms)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_finished)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)

        self.container = QWidget(self)
        self.container.setStyleSheet(
            """
            QWidget {
                background-color: rgba(30, 30, 30, 220);
                border: 1px solid rgba(255,255,255,140);
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-size: 14px;
                padding: 2px;
            }
            QPushButton {
                color: white;
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QPushButton:hover { color: #ff8080; }
            """
        )

        self.close_button = QPushButton("×", self.container)
        self.close_button.setToolTip("关闭")
        self.close_button.clicked.connect(self.close_overlay)

        self.label = QLabel("Ready", self.container)
        self.label.setWordWrap(True)
        self.label.setMinimumHeight(48)

        top_layout = QHBoxLayout()
        top_layout.addStretch(1)
        top_layout.addWidget(self.close_button)

        body_layout = QVBoxLayout(self.container)
        body_layout.addLayout(top_layout)
        body_layout.addWidget(self.label)
        body_layout.setContentsMargins(10, 6, 10, 10)

        layout = QVBoxLayout(self)
        layout.addWidget(self.container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.signal_show_message.connect(self._show_message_impl)
        self.signal_close_overlay.connect(self._close_overlay_impl)

    def show_message(self, text: str) -> None:
        logging.info("Overlay requested")
        self.signal_show_message.emit(text or "")

    def close_overlay(self) -> None:
        self.signal_close_overlay.emit()

    @Slot()
    def _start_fade(self) -> None:
        self._fade_animation.stop()
        self._fade_animation.setStartValue(self._opacity_effect.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    @Slot()
    def _on_fade_finished(self) -> None:
        self.hide()
        logging.info("Overlay hidden by timer")

    def _calc_safe_position(self) -> QPoint:
        cursor_pos = QCursor.pos()
        raw_x = cursor_pos.x() + self.offset_x
        raw_y = cursor_pos.y() + self.offset_y

        screen = QGuiApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()

        if screen is None:
            return QPoint(raw_x, raw_y)

        geo = screen.availableGeometry()
        x = min(max(raw_x, geo.left()), geo.right() - self.width())
        y = min(max(raw_y, geo.top()), geo.bottom() - self.height())

        if (x, y) != (raw_x, raw_y):
            logging.info("Overlay adjusted to screen bounds")

        logging.info("Overlay positioned at x=%s, y=%s", x, y)
        return QPoint(x, y)

    @Slot(str)
    def _show_message_impl(self, text: str) -> None:
        self._fade_timer.stop()
        self._fade_animation.stop()

        self.label.setText(text)
        self.adjustSize()
        self.resize(max(self.width(), 320), max(self.height(), 110))
        self._opacity_effect.setOpacity(1.0)

        self.move(self._calc_safe_position())
        self.show()
        self.raise_()
        self.activateWindow()
        self._fade_timer.start(max(1000, self.visible_ms))
        logging.info("Overlay actually shown")

    @Slot()
    def _close_overlay_impl(self) -> None:
        self._fade_timer.stop()
        self._fade_animation.stop()
        self.hide()
        logging.info("Overlay manually closed")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
            event.accept()
            return
        super().keyPressEvent(event)

    def hide_overlay(self) -> None:
        self.close_overlay()
