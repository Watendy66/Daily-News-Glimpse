"""Responsive illustrations and article reading layout (no network on the UI thread)."""
import html
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QUrl, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QColor, QFont, QImage, QTextDocument
from PySide6.QtWidgets import QWidget, QTextBrowser, QApplication
from news_media import image_path
from topics import topics_for
from reading_guide import guide_html


class NewsPicture(QWidget):
    def __init__(self, article, data_dir, parent=None):
        super().__init__(parent)
        self.article = article
        self.topic = article.topic or next(iter(topics_for(article.title, article.summary)), '新闻')
        path = image_path(article.image_url, data_dir)
        self.picture = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self.setFixedSize(104, 78)
        self.setToolTip('报道配图，来源：' + article.source if not self.picture.isNull() else '主题示意，非新闻现场')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, 9, 9)
        painter.setClipPath(clip)
        if not self.picture.isNull():
            # Contain, rather than crop: diagrams and research figures keep their labels.
            painter.fillRect(rect, QColor('#f2e9db'))
            picture = self.picture.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap((self.width()-picture.width())//2, (self.height()-picture.height())//2, picture)
        else:
            color = {'AI': '#e1e9ed', '教育': '#ede5d4', '心理': '#e2e9df'}.get(self.topic, '#ede5d4')
            painter.fillRect(rect, QColor(color))
            painter.setPen(QColor('#7c8986'))
            if self.topic == '教育':
                painter.drawRoundedRect(QRectF(27, 10, 50, 28), 3, 3)
                painter.drawLine(52, 11, 52, 37)
            else:
                points = [(27, 20), (52, 11), (77, 25), (50, 37)]
                for a, b in zip(points, points[1:] + points[:1]):
                    painter.drawLine(*a, *b)
                for x,y in points:
                    painter.setBrush(QColor('#fffaf0'))
                    painter.drawEllipse(QRectF(x-4,y-4,8,8))
            font = QApplication.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QColor('#3d5149'))
            painter.drawText(QRectF(0,41,self.width(),17), Qt.AlignCenter, self.topic)
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(QRectF(0,59,self.width(),16), Qt.AlignCenter, '主题示意')
        painter.end()


class ReadingBrowser(QTextBrowser):
    def __init__(self, article, data_dir, parent=None):
        super().__init__(parent)
        self.article = article
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().setDefaultFont(QApplication.font())
        self.document().setDocumentMargin(18)
        thumbnail = NewsPicture(article, data_dir)
        if thumbnail.picture.isNull():
            self.photo = thumbnail.grab().toImage()
            self.caption = '主题示意，非新闻现场'
            self.illustration = True
        else:
            self.photo = thumbnail.picture.toImage()
            self.caption = '报道配图 · 来源：' + article.source
            self.illustration = False
        thumbnail.deleteLater()
        self.render_content()

    def render_content(self):
        # setHtml changes scrollbar visibility and can synchronously trigger resizeEvent.
        # Re-entering setHtml before the first parse completes duplicates the document.
        if getattr(self, '_rendering', False):
            return
        viewport_width = self.viewport().width()
        if getattr(self, '_last_render_width', None) == viewport_width:
            return
        self._rendering = True
        try:
            self._replace_document(viewport_width)
            self._last_render_width = viewport_width
        finally:
            self._rendering = False
        if self.viewport().width() != viewport_width:
            QTimer.singleShot(0, self.render_content)

    def _replace_document(self, viewport_width):
        old_scroll = self.verticalScrollBar().value()
        width = max(180, min(640, viewport_width - 48))
        if self.illustration:
            width = min(width, 190)
        height = max(1, round(width * self.photo.height() / max(1,self.photo.width())))
        if height > 260:
            width = round(width*260/height)
            height = 260
        media = '<p align="center"><img src="dailyfocus:photo" width="%d" height="%d"></p>' % (width,height)
        media += '<p align="center" style="color:#746754;font-size:10pt">' + html.escape(self.caption) + '</p>'
        body = guide_html(self.article.title, self.article.summary, self.article.topic, compact=True)
        self.setHtml(media + body)
        self.document().addResource(QTextDocument.ImageResource, QUrl('dailyfocus:photo'), self.photo)
        self.document().markContentsDirty(0, self.document().characterCount())
        self.verticalScrollBar().setValue(old_scroll)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'photo'):
            self.render_content()
