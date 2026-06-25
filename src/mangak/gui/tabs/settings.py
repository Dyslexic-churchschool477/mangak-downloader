"""
MangaK Downloader — "⚙️ Settings" Tab

Form with all config options and a Save button.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mangak.core import Settings
from mangak.core.exceptions import ConfigError
from mangak.core.themes import Colors
from mangak.gui.widgets.glass_panel import GlassPanel
from mangak.gui.widgets.toast import ToastManager


def _form_row(label_text: str, widget: QWidget, layout: QVBoxLayout, note: Optional[str] = None) -> None:
    row = QHBoxLayout()
    row.setSpacing(12)
    row.setContentsMargins(0, 4, 0, 4)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(180)
    lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    if note:
        nl = QLabel(note)
        nl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;")
        row.addWidget(nl)
    layout.addLayout(row)


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: bold; padding-bottom: 4px;")
    return lbl


class SettingsTab(QWidget):
    """'⚙️ Settings' tab: configuration form with Save button."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = Settings()
        self._setup_ui()

    def _make_combo(self, items: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.BG_SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                min-width: 120px;
            }}
            QComboBox::drop-down {{ border: none; padding-right: 8px; }}
            QComboBox:hover {{ border-color: {Colors.ACCENT_PRIMARY}66; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                selection-background-color: {Colors.ACCENT_PRIMARY}44;
                selection-color: {Colors.TEXT_PRIMARY};
            }}
        """)
        return combo

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"SettingsTab {{ background: {Colors.BG_BASE}; }}")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        root = QVBoxLayout(scroll_content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        title = QLabel("⚙️  Settings")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        root.addWidget(title)

        # ── General Section ──
        general = GlassPanel()
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(24, 16, 24, 16)
        general_layout.setSpacing(12)
        general_layout.addWidget(_section_header("📂 General"))

        # Download Directory
        dl_row = QHBoxLayout()
        dl_row.setSpacing(8)
        dl_row.setContentsMargins(0, 4, 0, 4)
        dl_label = QLabel("Download Directory")
        dl_label.setFixedWidth(180)
        dl_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
        dl_row.addWidget(dl_label)
        self._dl_dir_input = QLineEdit()
        self._dl_dir_input.setText(self._settings.get("download_dir", "downloads"))
        self._dl_dir_input.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 8px 14px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT_PRIMARY}; }}
        """)
        dl_row.addWidget(self._dl_dir_input, 1)
        self._browse_btn = QPushButton("Browse")
        self._browse_btn.setFixedHeight(34)
        self._browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_SURFACE}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 0 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {Colors.BG_ELEVATED}; }}
        """)
        self._browse_btn.clicked.connect(self._on_browse)
        dl_row.addWidget(self._browse_btn)
        general_layout.addLayout(dl_row)

        # Export Format
        self._format_combo = self._make_combo(["cbz", "zip", "pdf", "folder"], self._settings.get("export_format", "cbz"))
        _form_row("Export Format", self._format_combo, general_layout)

        # Concurrent Downloads (chapter-level)
        self._concurrency_combo = self._make_combo(["1", "2", "3", "4", "5", "6", "8"], str(self._settings.get("concurrent_downloads", 4)))
        _form_row("Concurrent Downloads", self._concurrency_combo, general_layout)

        # Concurrent Image Downloads (page-level)
        self._img_concurrency_combo = self._make_combo(["1", "2", "3", "4", "6", "8", "12", "16"], str(self._settings.get("concurrent_image_downloads", 4)))
        _form_row("Concurrent Images", self._img_concurrency_combo, general_layout, "Parallel page downloads per chapter")

        # Rate Limit
        self._delay_combo = self._make_combo(["0", "0.1", "0.25", "0.5", "1.0", "2.0"], str(self._settings.get("rate_limit_delay", 0.25)))
        _form_row("Rate Limit Delay (s)", self._delay_combo, general_layout, "Between page downloads")

        root.addWidget(general)

        # ── Behavior Section ──
        behavior = GlassPanel()
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.setContentsMargins(24, 16, 24, 16)
        behavior_layout.setSpacing(12)
        behavior_layout.addWidget(_section_header("🎯 Behavior"))

        def make_checkbox(text: str, key: str, default: bool) -> QCheckBox:
            chk = QCheckBox(text)
            chk.setChecked(self._settings.get(key, default))
            chk.setStyleSheet(f"""
                QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: 13px; spacing: 10px; }}
                QCheckBox::indicator {{
                    width: 18px; height: 18px;
                    border: 2px solid {Colors.BORDER}; border-radius: 4px;
                    background: {Colors.BG_SURFACE};
                }}
                QCheckBox::indicator:checked {{ background: {Colors.ACCENT_PRIMARY}; border-color: {Colors.ACCENT_PRIMARY}; }}
                QCheckBox::indicator:hover {{ border-color: {Colors.ACCENT_PRIMARY}88; }}
            """)
            return chk

        self._delete_after_chk = make_checkbox("Delete images after export", "delete_images_after_export", True)
        behavior_layout.addWidget(self._delete_after_chk)

        self._auto_open_chk = make_checkbox("Auto-open folder after download", "auto_open_folder", False)
        behavior_layout.addWidget(self._auto_open_chk)

        root.addWidget(behavior)

        # ── Advanced Section ──
        advanced = GlassPanel()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(24, 16, 24, 16)
        advanced_layout.setSpacing(12)
        advanced_layout.addWidget(_section_header("🔧 Advanced"))

        # Theme (dark only)
        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)
        theme_row.setContentsMargins(0, 4, 0, 4)
        theme_label = QLabel("Theme")
        theme_label.setFixedWidth(180)
        theme_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px;")
        theme_row.addWidget(theme_label)
        self._theme_combo = self._make_combo(["dark"], self._settings.get("theme", "dark"))
        theme_row.addWidget(self._theme_combo, 1)
        advanced_layout.addLayout(theme_row)

        root.addWidget(advanced)

        # ── Save + Reset buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._save_btn = QPushButton("💾  Save Settings")
        self._save_btn.setFixedHeight(40)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_PRIMARY};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT_PRIMARY}CC; }}
        """)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._reset_btn = QPushButton("↺  Reset to Defaults")
        self._reset_btn.setFixedHeight(40)
        self._reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.WARNING};
                border: 1px solid {Colors.WARNING}66;
                border-radius: 8px;
                padding: 0 24px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {Colors.WARNING}15; }}
        """)
        self._reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(self._reset_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)
        root.addStretch()

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        scroll.setWidget(scroll_content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Slots ──

    def _on_save(self) -> None:
        """Save all settings from UI controls."""
        self._settings.set("download_dir", self._dl_dir_input.text().strip() or "downloads")
        self._settings.set("export_format", self._format_combo.currentText())
        self._settings.set("concurrent_downloads", int(self._concurrency_combo.currentText()))
        self._settings.set("concurrent_image_downloads", int(self._img_concurrency_combo.currentText()))
        self._settings.set("rate_limit_delay", float(self._delay_combo.currentText()))
        self._settings.set("delete_images_after_export", self._delete_after_chk.isChecked())
        self._settings.set("auto_open_folder", self._auto_open_chk.isChecked())
        self._settings.set("theme", self._theme_combo.currentText())
        ToastManager.show_toast_cls("Settings Saved", "All settings saved successfully.", "success")

    def _on_browse(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Select Download Directory", self._dl_dir_input.text())
        if dir_path:
            self._dl_dir_input.setText(dir_path)

    def _on_reset(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Reset Settings", "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._settings.reset()
            self._reload_from_settings()
            ToastManager.show_toast_cls("Settings Reset", "All settings restored to defaults.", "info")

    def _reload_from_settings(self) -> None:
        self._dl_dir_input.setText(self._settings.get("download_dir", "downloads"))
        fmt = self._settings.get("export_format", "cbz")
        idx = self._format_combo.findText(fmt)
        if idx >= 0: self._format_combo.setCurrentIndex(idx)
        conc = str(self._settings.get("concurrent_downloads", 4))
        idx2 = self._concurrency_combo.findText(conc)
        if idx2 >= 0: self._concurrency_combo.setCurrentIndex(idx2)
        imgc = str(self._settings.get("concurrent_image_downloads", 4))
        idx3 = self._img_concurrency_combo.findText(imgc)
        if idx3 >= 0: self._img_concurrency_combo.setCurrentIndex(idx3)
        delay = str(self._settings.get("rate_limit_delay", 0.25))
        idx4 = self._delay_combo.findText(delay)
        if idx4 >= 0: self._delay_combo.setCurrentIndex(idx4)
        self._delete_after_chk.setChecked(self._settings.get("delete_images_after_export", True))
        self._auto_open_chk.setChecked(self._settings.get("auto_open_folder", False))
