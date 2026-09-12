# JournalZaM - local PyQt5 journaling app
# Keep JournalZaM.py, JournalZaM.ui and JournalZaM_schema.sql in the same folder.

import os
import sys
import re
import uuid
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, date, timedelta

from PyQt5 import uic
from PyQt5.QtCore import Qt, QDate, QUrl, QSize
from PyQt5.QtGui import (
    QFont, QColor, QTextCharFormat, QTextCursor, QTextListFormat,
    QTextDocument, QImage, QPixmap, QIcon
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog, QColorDialog,
    QInputDialog, QTableWidgetItem, QHeaderView, QListWidgetItem
)

BASE_DIR = Path(__file__).resolve().parent
UI_FILE = BASE_DIR / "JournalZaM.ui"
SCHEMA_FILE = BASE_DIR / "JournalZaM_schema.sql"
DB_FILE = BASE_DIR / "JournalZaM_DB.db"


class JournalWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_FILE), self)

        self.conn = sqlite3.connect(str(DB_FILE))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.initialize_database()

        self.current_entry_id = None
        self.pending_images = {}       # image_key -> {data, file_name, mime_type}
        self.entry_dates = set()

        self.nav_buttons = [
            self.btnWrite, self.btnCalendar, self.btnJournal, self.btnGallery,
            self.btnSearch, self.btnMemories, self.btnStats, self.btnSettings
        ]
        self.page_titles = {
            0: ("Write", "Put the day into words — text, mood, people, tags and pictures."),
            1: ("Calendar", "See your journal grow across months and years."),
            2: ("Journal", "Read your memories like a private digital book."),
            3: ("Gallery", "All the pictures hidden inside your journal."),
            4: ("Search", "Find a sentence, person, tag, mood or memory."),
            5: ("Memories", "Rediscover old days and random moments."),
            6: ("Statistics", "A quiet overview of your writing habits and emotional history."),
            7: ("Settings", "Your local database, backups and exports.")
        }

        self.setup_styles_and_navigation()
        self.setup_editor()
        self.setup_tables()
        self.connect_signals()

        self.dateEntry.setDate(QDate.currentDate())
        self.lblToday.setText(datetime.now().strftime("%A, %d %B %Y"))
        self.lblDatabasePath.setText(f"Database: {DB_FILE}")

        self.load_categories()
        self.refresh_all()
        self.show_page(0)

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    def initialize_database(self):
        if not SCHEMA_FILE.exists():
            raise FileNotFoundError(f"Missing schema file: {SCHEMA_FILE}")
        self.conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup_styles_and_navigation(self):
        for button in self.nav_buttons:
            button.setProperty("class", "navButton")
            button.setProperty("active", False)

        for b in (self.btnSaveEntry, self.btnRunSearch, self.btnRandomMemory, self.btnOpenCalendarEntry):
            b.setProperty("class", "primary")
        for b in (self.btnClearEntry, self.btnEditSelected, self.btnRefreshGallery, self.btnExportHtml, self.btnBackupDb):
            b.setProperty("class", "secondary")
        self.btnDeleteEntry.setProperty("class", "danger")

        for b in (
            self.btnBold, self.btnItalic, self.btnUnderline, self.btnStrike,
            self.btnTextColor, self.btnHighlight, self.btnAlignLeft,
            self.btnAlignCenter, self.btnAlignRight, self.btnBullet,
            self.btnNumbered, self.btnLink, self.btnImage, self.btnUndo, self.btnRedo
        ):
            b.setProperty("class", "tool")

        self.btnWrite.clicked.connect(lambda: self.show_page(0))
        self.btnCalendar.clicked.connect(lambda: self.show_page(1))
        self.btnJournal.clicked.connect(lambda: self.show_page(2))
        self.btnGallery.clicked.connect(lambda: self.show_page(3))
        self.btnSearch.clicked.connect(lambda: self.show_page(4))
        self.btnMemories.clicked.connect(lambda: self.show_page(5))
        self.btnStats.clicked.connect(lambda: self.show_page(6))
        self.btnSettings.clicked.connect(lambda: self.show_page(7))

    def setup_editor(self):
        self.comboFontSize.setCurrentText("12")
        self.txtEditor.setFont(QFont("Segoe UI", 12))
        self.txtEditor.setTabStopWidth(32)

    def setup_tables(self):
        self.tableSearch.setColumnCount(7)
        self.tableSearch.setHorizontalHeaderLabels(
            ["Date", "Title", "Mood", "Rating", "Category", "Tags", "Preview"]
        )
        self.tableSearch.verticalHeader().setVisible(False)
        self.tableSearch.setSelectionBehavior(self.tableSearch.SelectRows)
        self.tableSearch.setEditTriggers(self.tableSearch.NoEditTriggers)
        self.tableSearch.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)

        self.tableMonthlyStats.setColumnCount(3)
        self.tableMonthlyStats.setHorizontalHeaderLabels(["Month", "Entries", "Words"])
        self.tableMonthlyStats.verticalHeader().setVisible(False)
        self.tableMonthlyStats.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.tableMoodStats.setColumnCount(2)
        self.tableMoodStats.setHorizontalHeaderLabels(["Mood", "Entries"])
        self.tableMoodStats.verticalHeader().setVisible(False)
        self.tableMoodStats.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def connect_signals(self):
        # Editor
        self.btnBold.clicked.connect(self.toggle_bold)
        self.btnItalic.clicked.connect(self.toggle_italic)
        self.btnUnderline.clicked.connect(self.toggle_underline)
        self.btnStrike.clicked.connect(self.toggle_strike)
        self.btnTextColor.clicked.connect(self.set_text_color)
        self.btnHighlight.clicked.connect(self.set_highlight_color)
        self.btnAlignLeft.clicked.connect(lambda: self.txtEditor.setAlignment(Qt.AlignLeft))
        self.btnAlignCenter.clicked.connect(lambda: self.txtEditor.setAlignment(Qt.AlignCenter))
        self.btnAlignRight.clicked.connect(lambda: self.txtEditor.setAlignment(Qt.AlignRight))
        self.btnBullet.clicked.connect(lambda: self.insert_list(QTextListFormat.ListDisc))
        self.btnNumbered.clicked.connect(lambda: self.insert_list(QTextListFormat.ListDecimal))
        self.btnLink.clicked.connect(self.insert_link)
        self.btnImage.clicked.connect(self.insert_image)
        self.btnUndo.clicked.connect(self.txtEditor.undo)
        self.btnRedo.clicked.connect(self.txtEditor.redo)
        self.fontFamily.currentFontChanged.connect(self.apply_font_family)
        self.comboFontSize.currentTextChanged.connect(self.apply_font_size)
        self.txtEditor.textChanged.connect(self.update_word_count)
        self.txtEditor.currentCharFormatChanged.connect(self.sync_format_buttons)

        # Entries
        self.btnSaveEntry.clicked.connect(self.save_entry)
        self.btnClearEntry.clicked.connect(self.new_entry)
        self.btnDeleteEntry.clicked.connect(self.delete_entry)

        # Calendar / reading
        self.calendarJournal.selectionChanged.connect(self.load_calendar_day)
        self.listCalendarEntries.currentItemChanged.connect(self.calendar_item_changed)
        self.btnOpenCalendarEntry.clicked.connect(self.open_calendar_entry)
        self.listEntries.currentItemChanged.connect(self.journal_item_changed)
        self.listEntries.itemDoubleClicked.connect(lambda _item: self.edit_selected_entry())
        self.btnEditSelected.clicked.connect(self.edit_selected_entry)
        self.editJournalFilter.textChanged.connect(self.load_journal_list)

        # Gallery
        self.btnRefreshGallery.clicked.connect(self.load_gallery)
        self.listGallery.itemDoubleClicked.connect(self.gallery_item_open)

        # Search
        self.btnRunSearch.clicked.connect(self.run_search)
        self.editSearch.returnPressed.connect(self.run_search)
        self.tableSearch.cellDoubleClicked.connect(self.search_result_open)

        # Memories
        self.btnRandomMemory.clicked.connect(self.random_memory)
        self.listMemories.currentItemChanged.connect(self.memory_item_changed)

        # Settings
        self.btnExportHtml.clicked.connect(self.export_selected_html)
        self.btnBackupDb.clicked.connect(self.backup_database)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def show_page(self, index):
        self.stackedWidget.setCurrentIndex(index)
        title, subtitle = self.page_titles[index]
        self.lblHeaderTitle.setText(title)
        self.lblHeaderSubtitle.setText(subtitle)

        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

        if index == 1:
            self.refresh_calendar()
            self.load_calendar_day()
        elif index == 2:
            self.load_journal_list()
        elif index == 3:
            self.load_gallery()
        elif index == 5:
            self.load_on_this_day()
        elif index == 6:
            self.load_statistics()

    # ------------------------------------------------------------------
    # Rich text
    # ------------------------------------------------------------------
    def merge_format(self, fmt):
        cursor = self.txtEditor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.txtEditor.mergeCurrentCharFormat(fmt)

    def toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.btnBold.isChecked() else QFont.Normal)
        self.merge_format(fmt)

    def toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.btnItalic.isChecked())
        self.merge_format(fmt)

    def toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.btnUnderline.isChecked())
        self.merge_format(fmt)

    def toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.btnStrike.isChecked())
        self.merge_format(fmt)

    def apply_font_family(self, font):
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self.merge_format(fmt)

    def apply_font_size(self, value):
        if not value:
            return
        try:
            size = float(value)
        except ValueError:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self.merge_format(fmt)

    def set_text_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.merge_format(fmt)

    def set_highlight_color(self):
        color = QColorDialog.getColor(QColor("#FFF1A8"), self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.merge_format(fmt)

    def insert_list(self, style):
        cursor = self.txtEditor.textCursor()
        cursor.beginEditBlock()
        list_fmt = QTextListFormat()
        list_fmt.setStyle(style)
        cursor.createList(list_fmt)
        cursor.endEditBlock()

    def insert_link(self):
        text, ok = QInputDialog.getText(self, "Link text", "Visible text:")
        if not ok or not text:
            return
        url, ok = QInputDialog.getText(self, "Link address", "URL:")
        if not ok or not url:
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QColor("#4D6FA8"))
        fmt.setFontUnderline(True)
        cursor = self.txtEditor.textCursor()
        cursor.insertText(text, fmt)

    def insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not path:
            return

        data = Path(path).read_bytes()
        image = QImage.fromData(data)
        if image.isNull():
            QMessageBox.warning(self, "Image", "This image could not be read.")
            return

        # Keep huge photographs from dominating the editor while retaining the original bytes.
        if image.width() > 900:
            image = image.scaledToWidth(900, Qt.SmoothTransformation)

        key = str(uuid.uuid4())
        source = f"journal-image://{key}"
        self.pending_images[key] = {
            "data": data,
            "file_name": Path(path).name,
            "mime_type": self.guess_mime(path)
        }
        self.txtEditor.document().addResource(QTextDocument.ImageResource, QUrl(source), image)
        self.txtEditor.textCursor().insertImage(source)

    @staticmethod
    def guess_mime(path):
        ext = Path(path).suffix.lower()
        return {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp"
        }.get(ext, "application/octet-stream")

    def sync_format_buttons(self, fmt):
        self.btnBold.blockSignals(True)
        self.btnItalic.blockSignals(True)
        self.btnUnderline.blockSignals(True)
        self.btnStrike.blockSignals(True)
        self.btnBold.setChecked(fmt.fontWeight() >= QFont.Bold)
        self.btnItalic.setChecked(fmt.fontItalic())
        self.btnUnderline.setChecked(fmt.fontUnderline())
        self.btnStrike.setChecked(fmt.fontStrikeOut())
        self.btnBold.blockSignals(False)
        self.btnItalic.blockSignals(False)
        self.btnUnderline.blockSignals(False)
        self.btnStrike.blockSignals(False)

    def update_word_count(self):
        text = self.txtEditor.toPlainText()
        words = len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))
        self.lblWordCount.setText(f"{words:,} words • {len(text):,} characters")

    # ------------------------------------------------------------------
    # Categories, tags, people
    # ------------------------------------------------------------------
    def load_categories(self):
        rows = self.conn.execute(
            "SELECT id, name FROM categories WHERE active=1 ORDER BY name COLLATE NOCASE"
        ).fetchall()

        self.comboCategory.clear()
        self.comboSearchCategory.clear()
        self.comboSearchCategory.addItem("Any category", None)

        for row in rows:
            self.comboCategory.addItem(row["name"], row["id"])
            self.comboSearchCategory.addItem(row["name"], row["id"])

        moods = ["😄 Great", "🙂 Good", "😐 Neutral", "😔 Low", "😡 Angry", "😴 Tired", "🤩 Excited"]
        self.comboSearchMood.clear()
        self.comboSearchMood.addItem("Any mood")
        self.comboSearchMood.addItems(moods)

    def save_names(self, entry_id, text, table, relation_table, relation_fk):
        names = sorted({x.strip() for x in text.split(",") if x.strip()})
        self.conn.execute(f"DELETE FROM {relation_table} WHERE entry_id=?", (entry_id,))
        for name in names:
            self.conn.execute(f"INSERT OR IGNORE INTO {table}(name) VALUES (?)", (name,))
            item_id = self.conn.execute(
                f"SELECT id FROM {table} WHERE name=? COLLATE NOCASE", (name,)
            ).fetchone()[0]
            self.conn.execute(
                f"INSERT OR IGNORE INTO {relation_table}(entry_id, {relation_fk}) VALUES (?,?)",
                (entry_id, item_id)
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def save_entry(self):
        title = self.editTitle.text().strip()
        plain = self.txtEditor.toPlainText().strip()
        if not title and not plain:
            QMessageBox.warning(self, "Empty entry", "Write something or add a title first.")
            return

        entry_date = self.dateEntry.date().toString("yyyy-MM-dd")
        title = title or datetime.strptime(entry_date, "%Y-%m-%d").strftime("%A, %d %B %Y")
        html = self.txtEditor.toHtml()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        values = (
            entry_date, title, html, self.txtEditor.toPlainText(),
            self.comboMood.currentText(), self.spinRating.value(),
            self.comboCategory.currentData(), int(self.checkFavorite.isChecked()), now
        )

        try:
            if self.current_entry_id is None:
                cur = self.conn.execute("""
                    INSERT INTO journal_entries(
                        entry_date,title,body_html,body_plain,mood,day_rating,
                        category_id,favorite,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                """, values)
                self.current_entry_id = cur.lastrowid
            else:
                self.conn.execute("""
                    UPDATE journal_entries
                    SET entry_date=?, title=?, body_html=?, body_plain=?, mood=?,
                        day_rating=?, category_id=?, favorite=?, updated_at=?
                    WHERE id=?
                """, values + (self.current_entry_id,))

            self.save_names(self.current_entry_id, self.editTags.text(), "tags", "entry_tags", "tag_id")
            self.save_names(self.current_entry_id, self.editPeople.text(), "people", "entry_people", "person_id")

            # Persist newly inserted images. Existing images remain until entry deletion.
            for key, img in self.pending_images.items():
                self.conn.execute("""
                    INSERT OR IGNORE INTO entry_images(
                        entry_id,image_key,file_name,mime_type,image_data
                    ) VALUES (?,?,?,?,?)
                """, (
                    self.current_entry_id, key, img["file_name"],
                    img["mime_type"], sqlite3.Binary(img["data"])
                ))

            self.conn.commit()
            self.pending_images.clear()
            self.refresh_all()
            QMessageBox.information(self, "Saved", "Your journal entry was saved.")
        except sqlite3.Error as exc:
            self.conn.rollback()
            QMessageBox.critical(self, "Database error", str(exc))

    def new_entry(self):
        self.current_entry_id = None
        self.pending_images.clear()
        self.dateEntry.setDate(QDate.currentDate())
        self.editTitle.clear()
        self.txtEditor.clear()
        self.editTags.clear()
        self.editPeople.clear()
        self.spinRating.setValue(7)
        self.comboMood.setCurrentIndex(1)
        self.checkFavorite.setChecked(False)
        if self.comboCategory.count():
            self.comboCategory.setCurrentIndex(0)
        self.update_word_count()

    def delete_entry(self):
        if self.current_entry_id is None:
            return
        answer = QMessageBox.question(
            self, "Delete entry", "Permanently delete this journal entry and its stored pictures?"
        )
        if answer != QMessageBox.Yes:
            return
        self.conn.execute("DELETE FROM journal_entries WHERE id=?", (self.current_entry_id,))
        self.conn.commit()
        self.new_entry()
        self.refresh_all()

    def load_entry_into_editor(self, entry_id):
        row = self.conn.execute(
            "SELECT * FROM journal_entries WHERE id=?", (entry_id,)
        ).fetchone()
        if not row:
            return

        self.current_entry_id = entry_id
        self.pending_images.clear()
        self.dateEntry.setDate(QDate.fromString(row["entry_date"], "yyyy-MM-dd"))
        self.editTitle.setText(row["title"])
        self.comboMood.setCurrentText(row["mood"] or "")
        self.spinRating.setValue(row["day_rating"] or 5)
        self.checkFavorite.setChecked(bool(row["favorite"]))

        idx = self.comboCategory.findData(row["category_id"])
        if idx >= 0:
            self.comboCategory.setCurrentIndex(idx)

        self.editTags.setText(", ".join(r[0] for r in self.conn.execute("""
            SELECT t.name FROM tags t JOIN entry_tags et ON et.tag_id=t.id
            WHERE et.entry_id=? ORDER BY t.name
        """, (entry_id,))))
        self.editPeople.setText(", ".join(r[0] for r in self.conn.execute("""
            SELECT p.name FROM people p JOIN entry_people ep ON ep.person_id=p.id
            WHERE ep.entry_id=? ORDER BY p.name
        """, (entry_id,))))

        self.set_html_with_images(self.txtEditor, entry_id, row["body_html"])
        self.show_page(0)

    def set_html_with_images(self, widget, entry_id, html):
        doc = widget.document()
        doc.clear()
        for img in self.conn.execute(
            "SELECT image_key,image_data FROM entry_images WHERE entry_id=?", (entry_id,)
        ):
            image = QImage.fromData(bytes(img["image_data"]))
            doc.addResource(
                QTextDocument.ImageResource,
                QUrl(f"journal-image://{img['image_key']}"),
                image
            )
        widget.setHtml(html or "")

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    def refresh_calendar(self):
        # Clear prior formatting.
        from PyQt5.QtGui import QTextCharFormat
        normal = QTextCharFormat()
        for ds in self.entry_dates:
            qd = QDate.fromString(ds, "yyyy-MM-dd")
            self.calendarJournal.setDateTextFormat(qd, normal)

        self.entry_dates = {
            r[0] for r in self.conn.execute("SELECT DISTINCT entry_date FROM journal_entries")
        }
        marked = QTextCharFormat()
        marked.setBackground(QColor("#DDEBE8"))
        marked.setForeground(QColor("#204039"))
        marked.setFontWeight(QFont.Bold)
        for ds in self.entry_dates:
            self.calendarJournal.setDateTextFormat(QDate.fromString(ds, "yyyy-MM-dd"), marked)

    def load_calendar_day(self):
        ds = self.calendarJournal.selectedDate().toString("yyyy-MM-dd")
        self.lblCalendarDate.setText(
            self.calendarJournal.selectedDate().toString("dddd, dd MMMM yyyy")
        )
        rows = self.conn.execute("""
            SELECT id,title,mood FROM journal_entries
            WHERE entry_date=? ORDER BY created_at
        """, (ds,)).fetchall()

        self.listCalendarEntries.clear()
        self.txtCalendarPreview.clear()
        for row in rows:
            item = QListWidgetItem(f"{row['mood'] or ''}  {row['title']}")
            item.setData(Qt.UserRole, row["id"])
            self.listCalendarEntries.addItem(item)
        if rows:
            self.listCalendarEntries.setCurrentRow(0)

    def calendar_item_changed(self, current, previous):
        if not current:
            return
        entry_id = current.data(Qt.UserRole)
        row = self.conn.execute(
            "SELECT body_html FROM journal_entries WHERE id=?", (entry_id,)
        ).fetchone()
        if row:
            self.set_html_with_images(self.txtCalendarPreview, entry_id, row["body_html"])

    def open_calendar_entry(self):
        item = self.listCalendarEntries.currentItem()
        if item:
            self.load_entry_into_editor(item.data(Qt.UserRole))

    # ------------------------------------------------------------------
    # Journal reading view
    # ------------------------------------------------------------------
    def load_journal_list(self):
        needle = self.editJournalFilter.text().strip()
        sql = """
            SELECT id,entry_date,title,mood,favorite
            FROM journal_entries
        """
        params = []
        if needle:
            sql += " WHERE title LIKE ? OR body_plain LIKE ?"
            params = [f"%{needle}%", f"%{needle}%"]
        sql += " ORDER BY entry_date DESC, created_at DESC"

        rows = self.conn.execute(sql, params).fetchall()
        self.listEntries.clear()
        for row in rows:
            star = "★ " if row["favorite"] else ""
            item = QListWidgetItem(
                f"{row['entry_date']}   {row['mood'] or ''}\n{star}{row['title']}"
            )
            item.setData(Qt.UserRole, row["id"])
            self.listEntries.addItem(item)
        if rows:
            self.listEntries.setCurrentRow(0)

    def journal_item_changed(self, current, previous):
        if not current:
            self.lblReadTitle.setText("Select an entry")
            self.txtReading.clear()
            return
        entry_id = current.data(Qt.UserRole)
        row = self.conn.execute("""
            SELECT e.*, COALESCE(c.name,'') category
            FROM journal_entries e
            LEFT JOIN categories c ON c.id=e.category_id
            WHERE e.id=?
        """, (entry_id,)).fetchone()
        if not row:
            return
        self.lblReadTitle.setText(("★ " if row["favorite"] else "") + row["title"])
        self.lblReadMeta.setText(
            f"{row['entry_date']}   •   {row['mood'] or 'No mood'}   •   "
            f"{row['day_rating'] or '—'}/10   •   {row['category'] or 'Uncategorized'}"
        )
        self.set_html_with_images(self.txtReading, entry_id, row["body_html"])
        self.btnEditSelected.setProperty("entry_id", entry_id)

    def edit_selected_entry(self):
        item = self.listEntries.currentItem()
        entry_id = item.data(Qt.UserRole) if item else self.btnEditSelected.property("entry_id")
        if entry_id:
            self.load_entry_into_editor(int(entry_id))

    # ------------------------------------------------------------------
    # Gallery
    # ------------------------------------------------------------------
    def load_gallery(self):
        rows = self.conn.execute("""
            SELECT i.id,i.entry_id,i.image_data,i.file_name,e.entry_date,e.title
            FROM entry_images i
            JOIN journal_entries e ON e.id=i.entry_id
            ORDER BY e.entry_date DESC, i.id DESC
        """).fetchall()

        self.listGallery.clear()
        for row in rows:
            pix = QPixmap()
            pix.loadFromData(bytes(row["image_data"]))
            if pix.isNull():
                continue
            icon = QIcon(pix.scaled(180, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item = QListWidgetItem(icon, f"{row['entry_date']}\n{row['title']}")
            item.setData(Qt.UserRole, row["entry_id"])
            item.setToolTip(row["file_name"] or "")
            self.listGallery.addItem(item)

    def gallery_item_open(self, item):
        if item:
            self.load_entry_into_editor(item.data(Qt.UserRole))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def run_search(self):
        needle = self.editSearch.text().strip()
        mood = self.comboSearchMood.currentText()
        category_id = self.comboSearchCategory.currentData()

        clauses = ["1=1"]
        params = []

        if needle:
            clauses.append("""(
                e.title LIKE ? OR e.body_plain LIKE ?
                OR EXISTS(
                    SELECT 1 FROM entry_tags et JOIN tags t ON t.id=et.tag_id
                    WHERE et.entry_id=e.id AND t.name LIKE ?
                )
                OR EXISTS(
                    SELECT 1 FROM entry_people ep JOIN people p ON p.id=ep.person_id
                    WHERE ep.entry_id=e.id AND p.name LIKE ?
                )
            )""")
            like = f"%{needle}%"
            params.extend([like, like, like, like])
        if mood != "Any mood":
            clauses.append("e.mood=?")
            params.append(mood)
        if category_id is not None:
            clauses.append("e.category_id=?")
            params.append(category_id)
        if self.checkSearchImages.isChecked():
            clauses.append("EXISTS(SELECT 1 FROM entry_images i WHERE i.entry_id=e.id)")
        if self.checkSearchFavorite.isChecked():
            clauses.append("e.favorite=1")

        rows = self.conn.execute(f"""
            SELECT e.id,e.entry_date,e.title,e.mood,e.day_rating,
                   COALESCE(c.name,'') category,
                   COALESCE(GROUP_CONCAT(DISTINCT t.name),'') tags,
                   substr(replace(e.body_plain, char(10), ' '),1,170) preview
            FROM journal_entries e
            LEFT JOIN categories c ON c.id=e.category_id
            LEFT JOIN entry_tags et ON et.entry_id=e.id
            LEFT JOIN tags t ON t.id=et.tag_id
            WHERE {' AND '.join(clauses)}
            GROUP BY e.id
            ORDER BY e.entry_date DESC
        """, params).fetchall()

        self.tableSearch.setRowCount(len(rows))
        for r, row in enumerate(rows):
            vals = [
                row["entry_date"], row["title"], row["mood"] or "",
                row["day_rating"] or "", row["category"], row["tags"], row["preview"]
            ]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setData(Qt.UserRole, row["id"])
                self.tableSearch.setItem(r, c, item)

    def search_result_open(self, row, column):
        item = self.tableSearch.item(row, 0)
        if item:
            self.load_entry_into_editor(item.data(Qt.UserRole))

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------
    def load_on_this_day(self):
        today = date.today()
        md = today.strftime("%m-%d")
        rows = self.conn.execute("""
            SELECT id,entry_date,title,mood
            FROM journal_entries
            WHERE substr(entry_date,6,5)=? AND entry_date<>?
            ORDER BY entry_date DESC
        """, (md, today.isoformat())).fetchall()

        self.listMemories.clear()
        self.txtMemoryPreview.clear()
        self.lblMemoryHeading.setText(f"On this day — {today.strftime('%d %B')}")
        for row in rows:
            years = today.year - int(row["entry_date"][:4])
            item = QListWidgetItem(
                f"{years} year{'s' if years != 1 else ''} ago • {row['entry_date']} • "
                f"{row['mood'] or ''}\n{row['title']}"
            )
            item.setData(Qt.UserRole, row["id"])
            self.listMemories.addItem(item)
        if rows:
            self.listMemories.setCurrentRow(0)

    def random_memory(self):
        row = self.conn.execute("""
            SELECT id,entry_date,title,mood FROM journal_entries
            ORDER BY RANDOM() LIMIT 1
        """).fetchone()
        if not row:
            QMessageBox.information(self, "Memories", "Write a few entries first.")
            return
        self.listMemories.clear()
        item = QListWidgetItem(
            f"Random memory • {row['entry_date']} • {row['mood'] or ''}\n{row['title']}"
        )
        item.setData(Qt.UserRole, row["id"])
        self.listMemories.addItem(item)
        self.listMemories.setCurrentRow(0)

    def memory_item_changed(self, current, previous):
        if not current:
            return
        entry_id = current.data(Qt.UserRole)
        row = self.conn.execute(
            "SELECT body_html FROM journal_entries WHERE id=?", (entry_id,)
        ).fetchone()
        if row:
            self.set_html_with_images(self.txtMemoryPreview, entry_id, row["body_html"])

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def calculate_current_streak(self):
        days = {
            datetime.strptime(r[0], "%Y-%m-%d").date()
            for r in self.conn.execute("SELECT DISTINCT entry_date FROM journal_entries")
        }
        if not days:
            return 0
        d = date.today()
        if d not in days:
            d -= timedelta(days=1)
            if d not in days:
                return 0
        streak = 0
        while d in days:
            streak += 1
            d -= timedelta(days=1)
        return streak

    def load_statistics(self):
        row = self.conn.execute("""
            SELECT COUNT(*) entries,
                   COALESCE(SUM(
                       CASE WHEN trim(body_plain)='' THEN 0
                       ELSE length(trim(body_plain)) - length(replace(trim(body_plain),' ','')) + 1 END
                   ),0) words,
                   ROUND(AVG(day_rating),1) avg_rating
            FROM journal_entries
        """).fetchone()
        photos = self.conn.execute("SELECT COUNT(*) FROM entry_images").fetchone()[0]

        self.lblStatEntries.setText(f"{row['entries']:,}")
        self.lblStatWords.setText(f"{row['words']:,}")
        self.lblStatStreak.setText(f"{self.calculate_current_streak()} days")
        self.lblStatRating.setText(str(row["avg_rating"] if row["avg_rating"] is not None else "—"))
        self.lblStatPhotos.setText(f"{photos:,}")

        monthly = self.conn.execute("""
            SELECT substr(entry_date,1,7) month,
                   COUNT(*) entries,
                   SUM(CASE WHEN trim(body_plain)='' THEN 0
                       ELSE length(trim(body_plain))-length(replace(trim(body_plain),' ',''))+1 END) words
            FROM journal_entries
            GROUP BY substr(entry_date,1,7)
            ORDER BY month DESC
            LIMIT 18
        """).fetchall()
        self.tableMonthlyStats.setRowCount(len(monthly))
        for r, data in enumerate(monthly):
            for c, value in enumerate(data):
                self.tableMonthlyStats.setItem(r, c, QTableWidgetItem(str(value or 0)))

        moods = self.conn.execute("""
            SELECT COALESCE(mood,'No mood'),COUNT(*)
            FROM journal_entries GROUP BY mood ORDER BY COUNT(*) DESC
        """).fetchall()
        self.tableMoodStats.setRowCount(len(moods))
        for r, data in enumerate(moods):
            for c, value in enumerate(data):
                self.tableMoodStats.setItem(r, c, QTableWidgetItem(str(value)))

    # ------------------------------------------------------------------
    # Export / backup
    # ------------------------------------------------------------------
    def export_selected_html(self):
        entry_id = self.current_entry_id
        if not entry_id:
            item = self.listEntries.currentItem()
            entry_id = item.data(Qt.UserRole) if item else None
        if not entry_id:
            QMessageBox.information(self, "Export", "Open or select an entry first.")
            return

        row = self.conn.execute(
            "SELECT entry_date,title,body_html FROM journal_entries WHERE id=?", (entry_id,)
        ).fetchone()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HTML", f"{row['entry_date']}_{row['title']}.html", "HTML (*.html)"
        )
        if path:
            Path(path).write_text(row["body_html"], encoding="utf-8")
            QMessageBox.information(self, "Export", "HTML exported.")

    def backup_database(self):
        default = BASE_DIR / f"JournalZaM_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup database", str(default), "SQLite database (*.db)"
        )
        if path:
            self.conn.commit()
            shutil.copy2(DB_FILE, path)
            QMessageBox.information(self, "Backup", "Database backup created.")

    # ------------------------------------------------------------------
    # Refresh / close
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.refresh_calendar()
        self.load_journal_list()
        self.load_gallery()
        self.run_search()
        self.load_on_this_day()
        self.load_statistics()

    def closeEvent(self, event):
        try:
            self.conn.commit()
            self.conn.close()
        finally:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("JournalZaM")
    window = JournalWindow()
    window.show()
    sys.exit(app.exec_())
