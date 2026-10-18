"""Topic-only selection. Unrelated headlines never fill a topic slot."""
import re
from reading_guide import simplified

QUOTAS = {'AI': 2, '教育': 2, '心理': 1}
KEYWORDS = {
    'AI': ('人工智能', '大模型', '语言模型', '生成式', '智能体', '机器学习', '深度学习', '神经网络', 'deepseek', 'chatgpt', 'openai', 'claude', 'gemini', 'gpt-', 'llm'),
    '教育': ('教育', '教学', '课程', '课堂', '学习方法', '学习效果', '招生', '高考', '中考', '教师', '师资', '学生', '高校', '大学', '学校', '学院', '研究生', '本科', '学位', '职教'),
    '心理': ('心理', '认知', '情绪', '焦虑', '抑郁', '睡眠', '失眠', '孤独', '幸福感', '注意力', '自尊', '自我认同', '情感', '记忆力', '成瘾', '人格', '亲子', '儿童发展', '社会行为', '行为科学'),
}

def topics_for(title, summary=''):
    title, summary = simplified(title).lower(), simplified(summary).lower()
    scores = {}
    for topic, words in KEYWORDS.items():
        score = sum(4 for word in words if word in title)
        if score:
            score += sum(1 for word in words if word in summary[:500])
        if topic == 'AI' and re.search(r'\bai\b', title, re.I):
            score += 5
        if score >= 3:
            scores[topic] = score
    # Campus crime and accidents alone are not educational developments.
    if any(word in title for word in ('死亡', '高坠', '杀害', '涉嫌', '投毒', '被捕')):
        if not any(word in title for word in ('教育', '教学', '课程', '心理', '辅导')):
            scores.pop('教育', None)
    if any(word in title for word in ('开售', '上架', '首发价', '开启预约', '元起', '发售')):
        if not any(word in title for word in ('模型', '智能体', '人工智能')):
            scores.pop('AI', None)
    if any(word in title for word in ('当选', '接受调查', '开除党籍', '举报')) or re.search(r'任.{0,30}(?:副?校长|副?院长|书记)', title):
        if not any(word in title for word in ('教育改革', '教学', '课程')):
            scores.pop('教育', None)
    if '教育' in scores and not any(word in title for word in ('教育', '教学', '课程', '课堂', '教师', '招生', '高考', '中考', '培养', '学习', '学生', '本科', '研究生', '职教', '学位', '毕业', '学院成立', '师资')):
        scores.pop('教育', None)
    return sorted(scores, key=lambda topic: -scores[topic])


def choose_topics(articles):
    selected, seen = [], set()
    for topic, quota in QUOTAS.items():
        for article in articles:
            if quota <= 0:
                break
            matches = topics_for(article.title, article.summary)
            if article.topic == '心理' and '心理' not in matches:
                matches.append('心理')
            if article.identity in seen or topic not in matches:
                continue
            if any(_same_story(article.title, chosen.title) for chosen in selected):
                continue
            article.topic = topic
            selected.append(article)
            seen.add(article.identity)
            quota -= 1
    # Shortage can be filled only from the three requested topics.
    for article in articles:
        if len(selected) >= 5:
            break
        topics = topics_for(article.title, article.summary)
        if article.identity in seen or not topics or any(_same_story(article.title, chosen.title) for chosen in selected):
            continue
        article.topic = topics[0]
        selected.append(article)
        seen.add(article.identity)
    return selected


def _same_story(left, right):
    def grams(text):
        text = re.sub(r'\W+', '', simplified(text).lower())
        return {text[i:i+2] for i in range(max(0, len(text)-1))}
    a, b = grams(left), grams(right)
    return bool(a and b) and len(a & b) / len(a | b) > .7
