import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from PySide6.QtCore import QEvent


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = app.QApplication.instance() or app.QApplication([])
        app.configure_font(cls.qt)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environ = patch.dict(os.environ, {'LOCALAPPDATA': self.directory.name})
        self.environ.start()
        self.refresh_patch = patch.object(app.DailyFocusWindow, 'refresh', lambda *args: None)
        self.refresh_patch.start()
        self.rows = [app.Article(title, summary, f'https://example.com/{i}', 'Test source', app.now_utc(), topic=topic)
                     for i, (title, summary, topic) in enumerate([
                         ('AI 模型评估', '比较实际任务的评估结果。', 'AI'),
                         ('人工智能与工作', '观察任务变化与用工结构。', 'AI'),
                         ('教师课程设计', '讨论课程评估。', '教育'),
                         ('学生学习方法', '关注学习体验。', '教育'),
                         ('睡眠与认知', '区分相关性与因果。', '心理'),
                     ])]
        store = app.NewsStore()
        store.save_articles(self.rows)
        store.save_selection(app.datetime.now(app.BJ_TZ).strftime('%Y-%m-%d'), self.rows)
        self.window = app.DailyFocusWindow()

    def tearDown(self):
        self.window.appearance_timer.stop()
        self.window.clock_timer.stop()
        self.window._quitting = True
        self.window.close()
        self.window.desktop_button.allow_close = True
        self.window.desktop_button.close()
        self.window.deleteLater()
        self.qt.sendPostedEvents(None, QEvent.DeferredDelete)
        self.refresh_patch.stop()
        self.environ.stop()
        self.directory.cleanup()

    def test_button_toggle_and_five_cached_cards(self):
        self.assertFalse(self.window.isVisible())
        self.window.desktop_button.show()
        self.window.desktop_button.click()
        self.qt.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertEqual(len(self.window.findChildren(app.ArticleCard)), 5)
        self.window.desktop_button.click()
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.desktop_button.isVisible())

    def test_transparency_does_not_fade_text(self):
        self.window.opacity_slider.setValue(65)
        self.assertEqual(self.window.centralWidget().transparency, 65)
        self.assertEqual(self.window.windowOpacity(), 1.0)
        self.window._save_appearance()
        self.assertTrue((app.app_data_dir() / 'appearance.json').exists())

    def test_metadata_survives_cache_roundtrip(self):
        cached = app.NewsStore().load_selection(self.window.day_key())
        self.assertEqual([row.topic for row in cached], ['AI', 'AI', '教育', '教育', '心理'])
        self.assertEqual(len(cached), 5)

    def test_repeated_resizing_does_not_duplicate_document(self):
        title = 'AI 课堂试点发布'
        fact = '本次试点采用课堂观察记录学习过程。'
        row = app.Article(title, title + '：' + fact + fact, 'https://example.com/story',
                          'Test source', app.now_utc(), topic='教育')
        dialog = app.ArticleDialog(row, self.window)
        dialog.show()
        for width, height in [(780, 800), (440, 620), (650, 700), (440, 620), (780, 800)]:
            with self.subTest(width=width, height=height):
                dialog.resize(width, height)
                self.qt.processEvents()
                browser = dialog.findChild(app.ReadingBrowser)
                text = browser.toPlainText()
                self.assertEqual(text.count(fact), 1)
                self.assertEqual(text.count('接下来关注什么'), 1)
                self.assertEqual(browser.toHtml().count('dailyfocus:photo'), 1)
                self.assertEqual(len(dialog.findChildren(app.QTextBrowser)), 1)
                self.assertEqual(browser.horizontalScrollBar().maximum(), 0)
        dialog.close()


if __name__ == '__main__':
    unittest.main()
