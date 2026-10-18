import unittest
from datetime import datetime, timezone

from app import Article, parse_datetime, BJ_TZ
from topics import choose_topics, topics_for
from news_media import image_from_html, web_url, ResearchList
from reading_guide import clean_summary, guide_html


class TopicTests(unittest.TestCase):
    def test_off_topic_and_incidental_mentions_are_excluded(self):
        for title in ('议会召开会议', 'AI 笔记本开售，售价 4999 元', '大学学生高坠死亡',
                      '某人任中国科学技术大学副校长', '大学团队破解材料制造难题'):
            with self.subTest(title=title):
                self.assertEqual(topics_for(title), [])

    def test_quota_is_unique_and_does_not_fill_with_general_news(self):
        titles = ['全球时政新闻', 'AI 模型研究', '教师教学课程改革', '睡眠认知研究',
                  '人工智能产业进展', '学生学习方法']
        rows = [Article(title, '', f'https://example.com/{i}', 'Test', datetime.now(timezone.utc))
                for i, title in enumerate(titles)]
        chosen = choose_topics(rows)
        self.assertEqual([row.topic for row in chosen], ['AI', 'AI', '教育', '教育', '心理'])
        self.assertEqual(len({row.identity for row in chosen}), 5)
        self.assertEqual(choose_topics(rows[:1]), [])

    def test_media_parsing(self):
        self.assertEqual(image_from_html('<img src="/photo.jpg">', 'https://example.com/a'),
                         'https://example.com/photo.jpg')
        self.assertFalse(web_url('file:///C:/Windows/test.jpg'))
        self.assertFalse(web_url('http://127.0.0.1/image.jpg'))
        self.assertTrue(web_url('https://example.com/image.jpg'))
        parser = ResearchList()
        parser.feed('<a href="./202610/t20261015_1.html"><h3>认知研究</h3><p>摘要</p></a>')
        self.assertEqual(parser.entries[0][1], '认知研究')

    def test_source_dates_are_china_local_time(self):
        self.assertEqual(parse_datetime('2026-10-18 11:22').astimezone(BJ_TZ).hour, 11)

    def test_summary_is_unique_and_html_is_escaped(self):
        title = 'AI 教育试点'
        fact = '试点记录学习过程。'
        self.assertEqual(clean_summary(title, title + '：' + fact + fact), fact)
        rendered = guide_html('<script>', '测试内容。', compact=True)
        self.assertNotIn('<script>', rendered)


if __name__ == '__main__':
    unittest.main()
