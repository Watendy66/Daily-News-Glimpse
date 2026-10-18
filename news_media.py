"""Extract publisher-provided image URLs and keep a bounded local image cache."""
import hashlib
import ipaddress
import re
from html.parser import HTMLParser
from pathlib import Path
import urllib.parse
import urllib.request
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt


def web_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
            return False
        if parsed.hostname.lower() in ('localhost', 'localhost.localdomain'):
            return False
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


class PageMedia(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = ''
        self.description = ''
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = attrs.get('property', attrs.get('name', '')).lower()
            candidate = attrs.get('content', '')
            if key in ('og:image', 'twitter:image') and not self.image and plausible_image(candidate):
                self.image = candidate
            if key in ('description', 'og:description') and not self.description:
                self.description = attrs.get('content', '')
        if tag == 'img':
            url = attrs.get('data-src') or attrs.get('src', '')
            if plausible_image(url):
                self.images.append(url)


def plausible_image(url):
    return bool(url) and not any(word in url.lower() for word in ('logo', 'lgo_', 'icon', 'avatar', 'qrcode', 'weixin', 'header-', 'banner', 'loading', 'footer'))


def image_from_html(raw, base_url):
    parser = PageMedia()
    parser.feed(raw)
    candidate = parser.image or (parser.images[0] if parser.images else '')
    return urllib.parse.urljoin(base_url, candidate) if candidate else ''


def image_path(image_url, data_dir):
    if not image_url:
        return None
    return Path(data_dir) / 'images' / (hashlib.sha256(image_url.encode()).hexdigest() + '.jpg')


def enrich_media(article, data_dir):
    """Called in background worker, never on the UI thread."""
    headers = {'User-Agent': 'Mozilla/5.0 DailyFocus/1.0'}
    try:
        if not article.image_url and web_url(article.link):
            request = urllib.request.Request(article.link, headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(1_500_000)
                encoding = response.headers.get_content_charset() or 'utf-8'
            parser = PageMedia()
            text = raw.decode(encoding, errors='replace')
            parser.feed(text)
            content_start = re.search(r'<(?:div|article)[^>]+(?:class|id)=[\"\'][^\"\']*(?:TRS_Editor|TRS_UEDITOR|post_content|post-content|article-content|article_content|v_news_content|content-body|articleBody|id=content)[^\"\']*[\"\'][^>]*>', text, re.I)
            content_images = []
            if content_start:
                body = PageMedia()
                body.feed(text[content_start.end():])
                content_images = body.images
            # With no article metadata or content container, avoid arbitrary site graphics.
            candidate = parser.image or (content_images[0] if content_images else '')
            article.image_url = urllib.parse.urljoin(article.link, candidate) if candidate else ''
        if not plausible_image(article.image_url):
            article.image_url = ''
            return
        if not web_url(article.image_url):
            article.image_url = ''
            return
        path = image_path(article.image_url, data_dir)
        if not path.exists():
            headers['Referer'] = article.link
            request = urllib.request.Request(article.image_url, headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                return
            image = QImage.fromData(raw)
            if image.isNull() or image.width() < 160 or image.height() < 80 or image.width() * image.height() > 40_000_000:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            image = image.scaled(1400, 1000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image.save(str(path), 'JPG', 86)
    except Exception:
        # Missing pictures never prevent a five-story update.
        return


class ResearchList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
        self.current = None
        self.in_heading = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and re.search(r't\d{8}_\d+\.html', attrs.get('href', '')):
            self.current = [attrs['href'], [], []]
        if self.current is not None and tag in ('h2', 'h3', 'h4', 'h5'):
            self.in_heading = True

    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data.strip())
            if self.in_heading:
                self.current[2].append(data.strip())

    def handle_endtag(self, tag):
        if tag in ('h2', 'h3', 'h4', 'h5'):
            self.in_heading = False
        if tag == 'a' and self.current is not None:
            chunks = list(filter(None, self.current[1]))
            heading = ' '.join(filter(None, self.current[2])) or next((part for part in chunks if len(part) >= 6 and not re.fullmatch(r'[\d\-/\s]+', part)), '')
            self.entries.append((self.current[0], heading, ' '.join(chunks)))
            self.current = None
