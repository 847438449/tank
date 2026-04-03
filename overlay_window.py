from __future__ import annotations

from PySide6.QtCore import QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget


class OverlayWindow(QWidget):
    def __init__(
        self,
        width: int = 420,
        height: int = 120,
        offset_x: int = 24,
        offset_y: int = 24,
        visible_ms: int = 5000,
        fade_ms: int = 600,
    ) -> None:
        super().__init__()
        self.resize(width, height)

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
        self._fade_animation.finished.connect(self.hide)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)

        self.label = QLabel("Ready", self)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            """
            QLabel {
                color: white;
                background-color: rgba(30, 30, 30, 180);
                border: 1px solid rgba(255,255,255,90);
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)

    def _start_fade(self) -> None:
        self._fade_animation.stop()
        self._fade_animation.setStartValue(self._opacity_effect.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def show_message(self, text: str) -> None:
        self._fade_timer.stop()
        self._fade_animation.stop()

        self.label.setText(text or "")
        self._opacity_effect.setOpacity(1.0)

        cursor_pos = QCursor.pos()
        target = QPoint(cursor_pos.x() + self.offset_x, cursor_pos.y() + self.offset_y)
        self.move(target)
        self.show()
        self.raise_()

        self._fade_timer.start(self.visible_ms)

    def show_text_near_cursor(self, text: str, offset_x: int = 24, offset_y: int = 24) -> None:
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.show_message(text)

    def hide_overlay(self) -> None:
        self._fade_timer.stop()
        self._fade_animation.stop()
        self.hide()
