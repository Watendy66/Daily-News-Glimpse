from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import html
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo
from reading_guide import simplified, guide_html
from topics import topics_for, choose_topics
from news_media import image_from_html, enrich_media, image_path, ResearchList
from news_views import NewsPicture, ReadingBrowser

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, QSize, QUrl, QPoint, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPalette, QFontDatabase, QPainter, QPainterPath, QPixmap, QAction, QImage, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QSlider,
    QSizeGrip,
    QTabWidget,
    QMenu,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "拾光简报 · Daily Glimpse"
BJ_TZ = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
USER_AGENT = "DailyGlimpse/0.1 (+personal RSS reader)"


def app_data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DailyFocus"
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundled_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / name
    return Path(__file__).resolve().parent / name


def configure_font(application: QApplication) -> str:
    font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'STZHONGS.TTF'
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    installed = set(QFontDatabase.families())
    family = next((name for name in ('华文中宋', 'STZhongsong') if name in installed), 'Microsoft YaHei UI')
    font = QFont(family, 11)
    font.setFamilies([family, 'Georgia', 'Segoe UI'])
    application.setFont(font)
    logging.info('Display font: %s', family)
    return family


def paint_backdrop(widget: QWidget, image: QPixmap, transparency: int, rounded: bool = True):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    bounds = QRectF(widget.rect())
    if rounded:
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 16, 16)
        painter.setClipPath(clip)
    painter.setOpacity(1.0 - transparency / 100.0)
    if not image.isNull():
        ratio = max(bounds.width() / image.width(), bounds.height() / image.height())
        width, height = bounds.width() / ratio, bounds.height() / ratio
        crop = QRectF((image.width() - width) / 2, (image.height() - height) / 2, width, height)
        painter.drawPixmap(bounds, image, crop)
    else:
        painter.fillRect(bounds, QColor('#ebcfaa'))
    painter.end()


class BackgroundSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.transparency = 18
        self.image = QPixmap(str(bundled_path('assets/background.jpg')))
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        paint_backdrop(self, self.image, self.transparency)


def user_sources_path() -> Path:
    return app_data_dir() / "sources.json"


def ensure_user_sources() -> Path:
    destination = user_sources_path()
    if not destination.exists():
        source = bundled_path("sources.json")
        if source.exists():
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        try:
            current = json.loads(destination.read_text(encoding='utf-8'))
            defaults = json.loads(bundled_path('sources.json').read_text(encoding='utf-8'))
            if current.get('schema_version', 1) < 2:
                backup = destination.with_name('sources.before-topics.json')
                if not backup.exists():
                    backup.write_text(destination.read_text(encoding='utf-8'), encoding='utf-8')
                # Keep custom subscriptions; the topic filter still excludes unrelated stories.
                defaults['feeds'].extend(feed for feed in current.get('feeds', [])
                    if feed.get('name') not in ('BBC 中文', '德国之声中文', '美国之音中文', '法国国际广播电台中文'))
                destination.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding='utf-8')
        except (OSError, ValueError):
            logging.exception('Could not migrate source settings')
    return destination


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return now_utc()
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or BJ_TZ).astimezone(UTC)
    except ValueError:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
        except ValueError:
            continue
    return now_utc()


def strip_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize_text(value: str) -> str:
    value = simplified(value)
    value = re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)
    return value


def title_tokens(title: str) -> set[str]:
    text = normalize_text(title)
    if len(text) <= 4:
        return {text}
    return {text[i : i + 2] for i in range(len(text) - 1)}


def similarity(left: str, right: str) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class Article:
    title: str
    summary: str
    link: str
    source: str
    published_at: datetime
    story_key: str = ""
    follow_up: bool = False
    source_rank: int = 99
    topic: str = ''
    image_url: str = ''

    @property
    def identity(self) -> str:
        raw = self.link or f"{self.source}|{self.title}|{iso(self.published_at)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NewsStore:
    def __init__(self) -> None:
        self.path = app_data_dir() / "daily_focus.sqlite3"
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    identity TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    link TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    story_key TEXT NOT NULL,
                    content_signature TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_selection (
                    day TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    identity TEXT NOT NULL,
                    PRIMARY KEY (day, position)
                );
                CREATE INDEX IF NOT EXISTS idx_articles_story ON articles(story_key);
                """
            )
            columns = {row[1] for row in connection.execute('PRAGMA table_info(articles)')}
            for name in ('topic', 'image_url'):
                if name not in columns:
                    connection.execute(f"ALTER TABLE articles ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def recent_titles(self, days: int = 14) -> list[tuple[str, str, str]]:
        cutoff = iso(now_utc() - timedelta(days=days))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT title, story_key, content_signature FROM articles WHERE fetched_at >= ?",
                (cutoff,),
            ).fetchall()
        return [(row["title"], row["story_key"], row["content_signature"]) for row in rows]

    def save_articles(self, articles: Iterable[Article]) -> None:
        with self._lock, self._connect() as connection:
            for article in articles:
                signature = hashlib.sha256(
                    f"{article.title}\n{article.summary}".encode("utf-8")
                ).hexdigest()
                connection.execute(
                    """
                    INSERT OR REPLACE INTO articles
                    (identity, title, summary, link, source, published_at, fetched_at, story_key, content_signature, topic, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.identity,
                        article.title,
                        article.summary,
                        article.link,
                        article.source,
                        iso(article.published_at),
                        iso(now_utc()),
                        article.story_key,
                        signature,
                        article.topic,
                        article.image_url,
                    ),
                )

    def save_selection(self, day: str, articles: list[Article]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM daily_selection WHERE day = ?", (day,))
            for position, article in enumerate(articles[:5]):
                connection.execute(
                    "INSERT INTO daily_selection(day, position, identity) VALUES (?, ?, ?)",
                    (day, position, article.identity),
                )

    def load_selection(self, day: str) -> list[Article]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.* FROM daily_selection d
                JOIN articles a ON a.identity = d.identity
                WHERE d.day = ? ORDER BY d.position
                """,
                (day,),
            ).fetchall()
        return [
            Article(
                title=row["title"],
                summary=row["summary"],
                link=row["link"],
                source=row["source"],
                published_at=parse_datetime(row["published_at"]),
                story_key=row["story_key"],
                topic=row['topic'],
                image_url=row['image_url'],
            )
            for row in rows
        ]


class FeedReader:
    def __init__(self, store: NewsStore) -> None:
        self.store = store

    def load_sources(self) -> list[dict]:
        path = ensure_user_sources()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [entry for entry in payload.get("feeds", []) if entry.get("url")]
        except (OSError, json.JSONDecodeError) as exc:
            logging.exception("Unable to read source configuration: %s", exc)
            return []

    def fetch(self) -> tuple[list[Article], list[str]]:
        sources = self.load_sources()
        old_titles = self.store.recent_titles()
        all_articles: list[Article] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            requests = {pool.submit(self._fetch_one, source, rank): source for rank, source in enumerate(sources)}
            for future in as_completed(requests):
                source = requests[future]
                try:
                    all_articles.extend(future.result())
                except Exception as exc:
                    logging.warning("Feed failed: %s (%s)", source.get("name"), exc)
                    errors.append(f"{source.get('name', '未命名来源')}: {exc}")

        all_articles = self._dedupe(all_articles)
        cutoff = now_utc() - timedelta(days=7)
        all_articles = [article for article in all_articles if cutoff <= article.published_at <= now_utc() + timedelta(hours=1)]
        for article in all_articles:
            article.story_key, article.follow_up = self._story_match(article, old_titles)
        all_articles.sort(
            key=lambda item: (
                not item.follow_up,
                -item.published_at.timestamp(),
                item.source_rank,
            )
        )
        chosen = self._choose_five(all_articles)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda article: enrich_media(article, app_data_dir()), chosen))
        if chosen:
            self.store.save_articles(chosen)
        return chosen, errors

    def _fetch_one(self, source: dict, rank: int) -> list[Article]:
        if source.get('kind') == 'research-list':
            return self._fetch_research(source, rank)
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/xml"}
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            root = ET.fromstring(response.read())
        entries = root.findall(".//item") or root.findall(".//{*}entry")
        result: list[Article] = []
        for entry in entries[:120]:
            title = self._text(entry, "title")
            link = self._link(entry)
            if not title or not link:
                continue
            if urllib.parse.urlparse(link).scheme not in ('https', 'http'):
                continue
            summary = self._text(entry, "description") or self._text(entry, "summary") or self._text(entry, "content")
            published = (
                self._text(entry, "pubDate")
                or self._text(entry, "published")
                or self._text(entry, "updated")
            )
            picture = ''
            for element in entry.iter():
                tag = element.tag.split('}')[-1]
                if tag in ('thumbnail', 'content', 'enclosure'):
                    candidate = element.get('url', '')
                    if candidate and (tag == 'thumbnail' or element.get('type', '').startswith('image/') or element.tag.startswith('{http://search.yahoo.com/mrss/}')):
                        picture = urllib.parse.urljoin(link, candidate)
                        break
            picture = picture or image_from_html(summary, link)
            result.append(
                Article(
                    title=simplified(strip_html(title)),
                    summary=simplified(strip_html(summary))[:900],
                    link=link,
                    source=simplified(source.get("name", urllib.parse.urlparse(link).netloc)),
                    published_at=parse_datetime(published),
                    source_rank=rank,
                    image_url=picture,
                )
            )
        return result

    def _fetch_research(self, source, rank):
        request = urllib.request.Request(source['url'], headers={'User-Agent': 'Mozilla/5.0 DailyFocus/1.0'})
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read(2_000_000).decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        parser = ResearchList()
        parser.feed(content)
        articles, seen = [], set()
        for href, heading, text in parser.entries[:25]:
            link = urllib.parse.urljoin(source['url'], href)
            if link in seen:
                continue
            seen.add(link)
            match = re.search(r't(\d{4})(\d{2})(\d{2})_', link)
            if not match:
                continue
            date = datetime(*map(int, match.groups()), tzinfo=BJ_TZ).astimezone(UTC)
            # Institute listing starts with the article title, then its short description/date.
            text = re.sub(r'\s+', ' ', text).strip()
            title = heading or re.split(r'(?<=[。！？])\s|\d{4}-\d{2}-\d{2}', text)[0].strip()
            if not title:
                continue
            summary = text[len(title):].strip() if text.startswith(title) else text
            summary = re.sub(r'\d{4}-\d{2}-\d{2}', '', summary).strip()
            articles.append(Article(simplified(title[:150]), simplified(summary[:900]), link,
                                    source['name'], date, source_rank=rank, topic=source.get('topic', '心理')))
        return articles

    @staticmethod
    def _text(element: ET.Element, name: str) -> str:
        child = element.find(name)
        if child is None:
            child = element.find(f"{{*}}{name}")
        return "" if child is None or child.text is None else child.text.strip()

    @staticmethod
    def _link(element: ET.Element) -> str:
        direct = FeedReader._text(element, "link")
        if direct:
            return direct
        for child in element.findall("{*}link"):
            href = child.attrib.get("href")
            if href:
                return href
        return ""

    @staticmethod
    def _dedupe(articles: list[Article]) -> list[Article]:
        seen: set[str] = set()
        result = []
        for article in articles:
            key = article.link or normalize_text(article.title)
            if key in seen:
                continue
            seen.add(key)
            result.append(article)
        return result

    @staticmethod
    def _story_match(article: Article, old_titles: list[tuple[str, str, str]]) -> tuple[str, bool]:
        best: tuple[float, str] | None = None
        for old_title, story_key, _signature in old_titles:
            if normalize_text(article.title) == normalize_text(old_title):
                return story_key or hashlib.sha1(normalize_text(article.title).encode()).hexdigest()[:16], False
            score = similarity(article.title, old_title)
            if best is None or score > best[0]:
                best = (score, story_key)
        if best and best[0] >= 0.42:
            return best[1] or hashlib.sha1(normalize_text(article.title).encode()).hexdigest()[:16], True
        return hashlib.sha1(normalize_text(article.title).encode()).hexdigest()[:16], False

    @staticmethod
    def _choose_five(articles: list[Article]) -> list[Article]:
        return choose_topics(articles)


class FetchWorker(QObject):
    finished = Signal(object, object)

    def __init__(self, reader: FeedReader) -> None:
        super().__init__()
        self.reader = reader

    def run(self) -> None:
        try:
            articles, errors = self.reader.fetch()
            self.finished.emit(articles, errors)
        except Exception as exc:
            logging.exception("Refresh failed")
            self.finished.emit([], [str(exc)])


class ArticleDialog(QDialog):
    def __init__(self, article: Article, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.background_image = QPixmap(str(bundled_path('assets/background.jpg')))
        self.background_transparency = parent.opacity_slider.value() if hasattr(parent, 'opacity_slider') else 18
        self.setWindowTitle(simplified(article.title))
        self.setMinimumSize(420, 430)
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(780, area.width()-40), min(850, area.height()-40))
        self.setSizeGripEnabled(True)
        self.setModal(True)
        layout = QVBoxLayout(self)
        title = QLabel(simplified(article.title))
        title.setTextFormat(Qt.PlainText)
        title.setObjectName("detailTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        metadata = QLabel(f"{article.topic or '专题'} · {simplified(article.source)} · {article.published_at.astimezone(BJ_TZ):%Y-%m-%d %H:%M}")
        metadata.setWordWrap(True)
        metadata.setTextFormat(Qt.PlainText)
        metadata.setObjectName("metadata")
        layout.addWidget(metadata)
        source_url = QLabel('原文来源：' + urllib.parse.urlparse(article.link).netloc)
        source_url.setToolTip(article.link)
        source_url.setWordWrap(True)
        source_url.setTextFormat(Qt.PlainText)
        source_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(source_url)
        guide = ReadingBrowser(article, app_data_dir())
        layout.addWidget(guide, 1)
        buttons = QHBoxLayout()
        source_button = QPushButton("打开来源原文")
        source_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(article.link)))
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(source_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def paintEvent(self, event):
        paint_backdrop(self, self.background_image, self.background_transparency, rounded=False)


class ArticleCard(QFrame):
    clicked = Signal(object)

    def __init__(self, article: Article, number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.article = article
        self.setObjectName("articleCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        number_label = QLabel(f"{number:02d}")
        number_label.setObjectName("number")
        top.addWidget(number_label)
        source_label = QLabel(f"{article.topic or next(iter(topics_for(article.title, article.summary)), '专题')} · {simplified(article.source)}")
        source_label.setWordWrap(True)
        source_label.setTextFormat(Qt.PlainText)
        source_label.setObjectName("source")
        source_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(source_label, 1)
        if article.follow_up:
            update_label = QLabel("相关后续报道")
            update_label.setObjectName("updateTag")
            top.addWidget(update_label)
        layout.addLayout(top)
        title = QLabel(simplified(article.title))
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title.setObjectName("cardTitle")
        title_row = QHBoxLayout()
        picture = NewsPicture(article, app_data_dir())
        title_row.addWidget(picture, 0, Qt.AlignTop)
        title_row.addWidget(title, 1)
        layout.addLayout(title_row)
        time_label = QLabel(article.published_at.astimezone(BJ_TZ).strftime("%m-%d %H:%M"))
        time_label.setObjectName("time")
        layout.addWidget(time_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.article)
        super().mousePressEvent(event)


class DragHeader(QWidget):
    """Native title-bar dragging with a fallback for platforms without native movement."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.offset = None
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("按住这里拖动窗口")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            handle = self.window().windowHandle()
            if handle and handle.startSystemMove():
                self.offset = None
            event.accept()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self.offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.offset = None


class DesktopNewsButton(QToolButton):
    positionChanged = Signal()
    exitRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(82, 82)
        self.setText('今日\n新闻')
        self.setAccessibleName('今日新闻')
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('点击展开或收起 · 拖动移动 · 右键菜单')
        self.image = QPixmap(str(bundled_path('assets/background.jpg')))
        self.press_position = None
        self.dragging = False
        self.allow_close = False

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.exitRequested.emit()

    def paintEvent(self, event):
        paint_backdrop(self, self.image, 0)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 246, 225, 225 if self.underMouse() else 200))
        painter.drawRoundedRect(QRectF(9, 19, 64, 45), 10, 10)
        painter.setPen(QColor('#3f291c'))
        font = QApplication.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_position = event.globalPosition().toPoint()
            self.start_position = self.pos()
            self.dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_position is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.press_position
            if self.dragging or delta.manhattanLength() >= QApplication.startDragDistance():
                self.dragging = True
                self.setDown(False)
                self.move(self.start_position + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_position = None
            if self.dragging:
                self.dragging = False
                self.setDown(False)
                self.positionChanged.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)


class DailyFocusWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = NewsStore()
        self.reader = FeedReader(self.store)
        self.refresh_thread: QThread | None = None
        self.refresh_worker: FetchWorker | None = None
        self.cards_layout: QVBoxLayout | None = None
        self.date_label = QLabel()
        self.status_label = QLabel()
        self.refresh_action = QAction("刷新新闻", self)
        self.refresh_action.setShortcut('F5')
        self.refresh_action.triggered.connect(self.refresh)
        self.addAction(self.refresh_action)
        self._quitting = False
        self._build_ui()
        self._place_on_desktop()
        self._restore_appearance()
        self.desktop_button = DesktopNewsButton()
        self.desktop_button.clicked.connect(self.toggle_panel)
        self.desktop_button.exitRequested.connect(self.request_exit)
        self.desktop_button.positionChanged.connect(self._queue_appearance_save)
        self.desktop_button.setContextMenuPolicy(Qt.CustomContextMenu)
        self.desktop_button.customContextMenuRequested.connect(
            lambda point: self._show_menu(self.desktop_button.mapToGlobal(point)))
        self._place_button()
        self._schedule_next_refresh()
        self._update_time()
        cached = self.store.load_selection(self.day_key())
        if len(cached) == 5 and all(article.topic in ('AI', '教育', '心理') for article in cached):
            self.show_articles(cached, "已显示今日缓存")
        else:
            self.show_articles([], '正在更新 AI、教育、心理新闻…')
        QTimer.singleShot(300, self.refresh)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._check_schedule)
        self.clock_timer.start(30_000)

    def _build_ui(self) -> None:
        self.setWindowTitle('今日新闻')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(410, 700)
        self.setMinimumSize(350, 450)
        root = BackgroundSurface()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 14)
        self.drag_header = DragHeader(root)
        header = QHBoxLayout(self.drag_header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel('今日新闻')
        title.setObjectName("appTitle")
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(title)
        header.addStretch(1)
        self.drag_header.setContextMenuPolicy(Qt.CustomContextMenu)
        self.drag_header.customContextMenuRequested.connect(
            lambda point: self._show_menu(self.drag_header.mapToGlobal(point)))
        outer.addWidget(self.drag_header)
        self.date_label.setObjectName("dateLabel")
        outer.addWidget(self.date_label)
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        appearance = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 80)
        self.opacity_slider.setValue(18)
        self.opacity_slider.setToolTip("仅调整图片背景；向右更透明，文字保持清晰")
        self.opacity_slider.valueChanged.connect(self._set_transparency)
        appearance.addWidget(self.opacity_slider, 1)
        outer.addLayout(appearance)
        scroll = QScrollArea()
        scroll.setObjectName('newsScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('newsContent')
        content.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        self.cards_layout = QVBoxLayout(content)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        grip = QSizeGrip(root)
        grip.setToolTip("拖动调整窗口大小")
        bottom.addWidget(grip, 0, Qt.AlignBottom)
        outer.addLayout(bottom)
        self.setStyleSheet(
            """
            QMainWindow, #root { background: transparent; color: #35281e; }
            #newsScroll, #newsScroll QWidget, #newsContent { background: transparent; }
            QLabel { background: transparent; }
            QLabel#appTitle { font-size: 22px; font-weight: 700; color: #17213b; }
            QLabel#dateLabel { color: #463b32; font-size: 12px; }
            QLabel#status { color: #463b32; font-size: 12px; min-height: 16px; }
            QPushButton, QToolButton { border: 1px solid rgba(255,250,237,140); border-radius: 8px; padding: 7px 10px; background: rgba(255,245,224,215); color: #533b2b; }
            QPushButton:hover, QToolButton:hover { background: #fff3d8; }
            QFrame#articleCard { background: rgba(255,249,235,180); border: 1px solid rgba(255,245,224,200); border-radius: 12px; }
            QFrame#articleCard:hover { border: 1px solid #b57848; background: rgba(255,249,235,220); }
            QLabel#number { color: #6c87aa; font-size: 15px; font-weight: 700; }
            QLabel#source { color: #496d93; font-size: 11px; }
            QLabel#updateTag { background: #e7f5ec; color: #25824a; border-radius: 7px; padding: 3px 6px; font-size: 10px; }
            QLabel#cardTitle { color: #30261f; font-size: 16px; font-weight: 400; }
            QLabel#time { color: #69533e; font-size: 11px; }
            QLabel#footer { color: #3b3028; font-size: 11px; background: rgba(255,246,225,190); border-radius: 4px; padding: 3px; }
            QTextBrowser { background: rgba(255,250,240,235); border: 1px solid #d4bba0; border-radius: 8px; padding: 8px; }
            QTabWidget::pane { background: transparent; border: 0; }
            QTabBar::tab { background: rgba(255,240,213,220); padding: 8px 12px; }
            QTabBar::tab:selected { background: #fffaf0; }
            QLabel#detailTitle { color: #17213b; font-size: 18px; font-weight: 700; }
            QLabel#metadata { color: #66809a; }
            """
        )

    def _set_transparency(self, value):
        self.opacity_slider.setToolTip(f"背景透明度 {value}%")
        self.setWindowOpacity(1.0)
        self.centralWidget().transparency = value
        self.centralWidget().update()

    def _restore_appearance(self):
        data = {}
        try:
            data = json.loads((app_data_dir() / 'appearance.json').read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                data = {}
            self.resize(max(350, min(1600, int(data.get('width', 410)))),
                        max(450, min(1400, int(data.get('height', 700)))))
            position = QPoint(int(data.get('x', self.x())), int(data.get('y', self.y())))
            if any(screen.availableGeometry().contains(position + QPoint(80, 25)) for screen in QApplication.screens()):
                self.move(position)
            self.opacity_slider.setValue(max(0, min(80, int(data.get('transparency', 18)))))
        except (OSError, ValueError, TypeError):
            pass
        self._saved_appearance = data if isinstance(data, dict) else {}
        self._set_transparency(self.opacity_slider.value())
        self.appearance_timer = QTimer(self)
        self.appearance_timer.setSingleShot(True)
        self.appearance_timer.timeout.connect(self._save_appearance)
        self.opacity_slider.valueChanged.connect(self._queue_appearance_save)

    def _queue_appearance_save(self, *args):
        if hasattr(self, 'appearance_timer'):
            self.appearance_timer.start(400)

    def _save_appearance(self):
        data = dict(x=self.x(), y=self.y(), width=self.width(), height=self.height(),
                    transparency=self.opacity_slider.value())
        if hasattr(self, 'desktop_button'):
            data.update(button_x=self.desktop_button.x(), button_y=self.desktop_button.y())
        try:
            (app_data_dir() / 'appearance.json').write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            logging.exception('Unable to save appearance')

    def moveEvent(self, event):
        super().moveEvent(event)
        self._queue_appearance_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_appearance_save()

    def day_key(self) -> str:
        return datetime.now(BJ_TZ).strftime("%Y-%m-%d")

    def _place_button(self):
        area = QApplication.primaryScreen().availableGeometry()
        data = self._saved_appearance
        try:
            point = QPoint(int(data.get('button_x', area.right() - 105)),
                           int(data.get('button_y', area.bottom() - 105)))
        except (TypeError, ValueError):
            point = QPoint(area.right() - 105, area.bottom() - 105)
        if not any(screen.availableGeometry().contains(point + QPoint(41, 41)) for screen in QApplication.screens()):
            point = QPoint(area.right() - 105, area.bottom() - 105)
        self.desktop_button.move(point)

    def toggle_panel(self):
        if self.isVisible():
            self._save_appearance()
            self.hide()
            return
        screen = QApplication.screenAt(self.desktop_button.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
        x = self.desktop_button.x() - self.width() - 12
        if x < area.left():
            x = self.desktop_button.x() + self.desktop_button.width() + 12
        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = max(area.top(), min(self.desktop_button.y() + 82 - self.height(), area.bottom() - self.height() + 1))
        self.move(x, y)
        self._update_time()
        self.show()

    def _show_menu(self, position):
        menu = QMenu(self)
        menu.addAction('收起新闻' if self.isVisible() else '展开新闻', self.toggle_panel)
        menu.addAction(self.refresh_action)
        menu.addSeparator()
        menu.addAction('退出小组件', self.request_exit)
        menu.exec(position)

    def request_exit(self):
        self._quitting = True
        self.hide()
        self.desktop_button.hide()
        if self.refresh_thread and self.refresh_thread.isRunning():
            self.refresh_thread.finished.connect(self._finish_exit)
        else:
            self._finish_exit()

    def _finish_exit(self):
        self._save_appearance()
        self.desktop_button.allow_close = True
        self.desktop_button.close()
        self.close()
        QApplication.quit()

    def _update_time(self):
        self.date_label.setText(datetime.now(BJ_TZ).strftime('%Y-%m-%d %H:%M'))
        self.date_label.setToolTip('北京时间')

    def _place_on_desktop(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 22, area.bottom() - self.height() - 22)

    def _schedule_next_refresh(self) -> None:
        local_now = datetime.now(BJ_TZ)
        next_run = local_now.replace(hour=8, minute=0, second=0, microsecond=0)
        if next_run <= local_now:
            next_run += timedelta(days=1)
        self.next_run = next_run

    def _check_schedule(self) -> None:
        self._update_time()
        if datetime.now(BJ_TZ) >= self.next_run:
            self._automatic_refresh()

    def _automatic_refresh(self) -> None:
        self.refresh()
        self._schedule_next_refresh()

    def refresh(self) -> None:
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            return
        self.refresh_action.setEnabled(False)
        self.status_label.setText("正在读取新闻源…")
        self.refresh_thread = QThread(self)
        self.refresh_worker = FetchWorker(self.reader)
        self.refresh_worker.moveToThread(self.refresh_thread)
        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self._on_refresh_finished)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self._cleanup_refresh)
        self.refresh_thread.start()

    def _cleanup_refresh(self) -> None:
        if self.refresh_worker:
            self.refresh_worker.deleteLater()
        if self.refresh_thread:
            self.refresh_thread.deleteLater()
        self.refresh_worker = None
        self.refresh_thread = None

    def _on_refresh_finished(self, articles: list[Article], errors: list[str]) -> None:
        logging.info("Refresh completed: %d articles, %d source errors", len(articles), len(errors))
        self.refresh_action.setEnabled(True)
        if len(articles) >= 5:
            self.store.save_selection(self.day_key(), articles[:5])
            suffix = f" · {len(errors)} 个源暂不可用" if errors else ""
            self.show_articles(articles[:5], "已更新 · 今日 5 条" + suffix)
        else:
            cached = self.store.load_selection(self.day_key())
            if len(cached) == 5 and all(article.topic in ('AI', '教育', '心理') for article in cached):
                self.show_articles(cached, "网络源不足，已保留今日 5 条缓存")
            else:
                self.show_articles([], f"仅取得 {len(articles)} 条，未满 5 条；请检查新闻源配置")
        if errors:
            self.status_label.setToolTip("\n".join(errors))

    def show_articles(self, articles: list[Article], status: str) -> None:
        self._update_time()
        self.status_label.setText(status)
        self.date_label.setToolTip(status)
        if not self.cards_layout:
            return
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not articles:
            message = QLabel(status)
            message.setWordWrap(True)
            message.setStyleSheet('background: rgba(255,249,235,210); padding: 14px; border-radius: 10px; color: #403025;')
            self.cards_layout.insertWidget(0, message)
        for number, article in enumerate(articles[:5], 1):
            card = ArticleCard(article, number)
            card.clicked.connect(self.open_article)
            self.cards_layout.insertWidget(number - 1, card)

    def open_article(self, article: Article) -> None:
        ArticleDialog(article, self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._quitting:
            self._save_appearance()
            self.hide()
            event.ignore()
            return
        if self.refresh_thread and self.refresh_thread.isRunning():
            self.status_label.setText("正在完成网络请求，请稍后关闭…")
            self.refresh_thread.finished.connect(self.close)
            event.ignore()
            return
        event.accept()
        self._save_appearance()


def main() -> int:
    logging.basicConfig(
        filename=app_data_dir() / "daily_focus.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    app = QApplication(sys.argv)
    configure_font(app)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)
    window = DailyFocusWindow()
    window.desktop_button.show()
    logging.info("Desktop news button opened; panel collapsed")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
