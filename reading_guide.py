"""Local reading prompts: source material is kept distinct from conditional inference."""
from __future__ import annotations

import html
import re
from opencc import OpenCC

_converter = OpenCC('t2s')


def simplified(text: str) -> str:
    return _converter.convert(text or '')


# Specific reading lenses, not assertions about events beyond the supplied RSS text.
PROFILES = [
    (
        '就业与人工智能', ('求职', '投履历', '投简历', '招聘', '面试', '失业', '裁员', '找工作'),
        '招聘流程是否改变了求职者与雇主之间的信息筛选方式？',
        [
            '如果工具降低了批量投递成本，投递数量可能上升，但数量上升并不等于匹配质量提高。需要分开看投递量、面试率和最终录用率。',
            '如果企业也使用自动筛选，简历表达和筛选规则之间可能形成相互适应。能否带来长期优势，要看同岗位、同经验水平的比较。',
        ],
        ['报道里的案例能代表哪些求职群体？有没有同等条件下未使用工具的对照？',
         '结果改善来自技能匹配、简历表达还是投递数量？哪一个环节有可核对的数据？'],
        ['观察招聘平台是否调整筛选规则，以及雇主是否公布实际录用数据。',
         '追踪求职周期和入职后表现，避免只根据一次面试或个案判断成效。'],
    ),
    (
        '科研与校园', ('研究生', '大学', '校园', '学术', '实验室', '论文', '科研'),
        '事件会怎样影响研究、学习机会以及参与者的实际选择？',
        ['如果政策或环境变化影响招生、经费或合作，影响可能沿“资源变化→研究机会→个人选择”传导；需要逐环节核对。',
         '受访者的感受是理解处境的线索，但不能直接代表整个群体的比例。访谈样本和制度文件需要分别阅读。'],
        ['报道引用了多少人，来自哪些院校或学科？不同处境是否被混在一起？',
         '哪些变化已经实施，哪些只是担忧？是否有明确的政策条款或经费数字？'],
        ['关注院校正式通知、项目经费和实际招生变化。', '对照其他院校或学科的情况，判断是局部问题还是更广泛趋势。'],
    ),
    (
        '政策与政治', ('全会', '政策', '立法', '法案', '选举', '议会', '政府', '内阁', '维稳', '总统'),
        '应当如何区分政治信号、正式决定与实际执行？',
        ['如果报道涉及新的政策安排，真正的影响取决于文件内容、执行范围和资源投入；会议召开或表态本身不等于落实。',
         '如果措施改变了参与者的激励，执行部门和受影响群体可能作出不同反应。需要对照目标与实际结果。'],
        ['文中哪一句来自正式文件，哪一句是记者或受访者的解读？',
         '决定由谁执行、何时生效、涉及哪些人？有没有例外和约束条件？'],
        ['关注正式公告、具体条款、生效日期和后续执行数据。', '比较先前承诺与实际措施，留意是否存在实施落差。'],
    ),
    (
        '冲突与安全', ('战争', '冲突', '空袭', '导弹', '停火', '军方', '袭击', '核武'),
        '局势变化有没有得到独立证据支持，会改变哪些风险？',
        ['如果新的行动得到证实，短期影响可能先体现为当地安全和人员流动变化；更广的影响要看行动规模、持续时间及各方回应。',
         '冲突报道中的不同阵营可能提供不同数字和解释，应分开记录各方说法以及可独立核实的部分。'],
        ['时间、地点和事件经过是否有多方证据相互印证？', '伤亡或损失数字由谁提供，是否仍在更新？'],
        ['追踪独立核实、正式通报和谈判进展。', '观察后续行动是否与公开表态一致。'],
    ),
    (
        '经济与生活', ('物价', '通胀', '利率', '经济', '关税', '财政', '房价', '股市', '贸易', '能源'),
        '数字或政策变化通过什么路径影响企业和日常生活？',
        ['如果成本或价格变化持续，可能先影响直接相关的行业，再通过企业定价或收入变化传导到家庭。需要核对变化幅度和持续时间。',
         '总量数字可能掩盖不同地区、行业和收入群体的差异；同比、环比和绝对水平也不能混用。'],
        ['数字对应哪个时期、统计口径和比较基准？', '报道说明的是已经发生的变化，还是机构预测？谁最先承担成本？'],
        ['关注后续正式统计、修订值和分行业数据。', '观察价格、订单或家庭支出等实际指标，而非只看市场短期反应。'],
    ),
    (
        '科技与产品', ('人工智能', 'AI', '模型', '芯片', '科技', '软件', '隐私', '数据泄露'),
        '新能力是否有可重复的证据，使用边界在哪里？',
        ['如果新能力能在实际场景中重复实现，才可能转化为效率或成本优势；演示、基准测试和实际使用应分别比较。',
         '如果应用扩大，还需要观察错误率、使用成本以及数据处理方式，避免只依据单个亮点判断整体价值。'],
        ['测试由谁完成，有没有独立复现和与现有方法的公平对照？', '哪些用户和任务受益，什么情况下会失效？'],
        ['关注独立测试、实际部署效果和公开的限制说明。', '观察使用成本、可靠性及后续修复情况。'],
    ),
    (
        '影像与调查', ('卫星', '影像', '调查', '揭示', '曝光', '证据'),
        '观察到的现象与作者据此作出的解释之间，还缺少什么证据？',
        ['如果报道依据影像或调查材料，首先能支持的是材料直接显示的现象。对用途、动机或人员行为的判断通常还需要其他证据。',
         '如果能找到不同时期、不同角度的材料，可以判断变化是否持续；单张影像难以说明频率或完整背景。'],
        ['材料是什么时间取得的？报道有没有说明定位、时间和核验方法？', '哪些结论是直接观察，哪些是推测？有没有合理的其他解释？'],
        ['关注原始材料、核验方法以及后续独立调查。', '比较历史影像、官方回应和其他来源的补充证据。'],
    ),
]

DEFAULT = (
    '综合观察', (), '这条报道新增了什么信息，哪些结论还需要更多证据？',
    ['如果报道内容得到更多证据支持，可以进一步判断它影响的群体、范围和持续时间。当前标题与摘要不足以独立确认这些方面。',
     '如果事件持续发展，后续报道可能改变最初判断。应把当下已知的信息与对未来的预期分别记录。'],
    ['报道的核心说法由谁提出，有没有直接证据或原始文件？', '哪些信息缺失，什么新证据会让你改变当前判断？'],
    ['关注原始文件、当事方回应及独立来源的后续报道。', '记录时间线，区分重复报道和实质性新增信息。'],
)


TOPIC_PROFILES = {
    '心理': (
        '心理与行为', (), '这是相关性发现、实验结果还是观点？它适用于哪些人和情境？',
        ['如果研究发现情绪、认知或行为与某个因素相关，仍需核对设计能否支持因果解释；样本量、测量方法和效应大小决定结果的解释边界。',
         '如果结论来自特定年龄或实验环境，推广到日常生活需要额外证据。动物实验、初步研究和人群验证应分开看。'],
        ['研究对象是谁，有没有对照、长期随访和其他团队的复现？', '报道有没有说明局限性？有没有把群体差异直接套用到个人？'],
        ['关注原论文的方法、效应大小和独立复现。', '区分科学研究、科普解释与个人健康建议，避免仅依据新闻自行诊断或改变治疗。'],
    ),
    '教育': (
        '教育与成长', (), '这项变化是否改善了学习机会、教学过程或实际学习效果？',
        ['如果教育政策、课程或培养机制发生变化，应沿“资源投入→教学实施→学习体验→效果评估”的路径核对，宣布新项目不等于已经改善结果。',
         '如果某种方法在单所学校有效，还要看年龄、学科、教师支持与家庭资源，才能判断其他学习者是否同样适用。'],
        ['报道衡量的是分数、能力、参与感，还是项目数量？比较基准是什么？', '谁能获得这项机会，谁可能被排除？执行成本和教师负担由谁承担？'],
        ['关注正式方案、实施范围以及学生和教师的后续反馈。', '追踪实际学习效果与公平性，区分宣传、试点与已经验证的结果。'],
    ),
}


def build_guide(title: str, summary: str, topic: str = '') -> dict:
    title, summary = simplified(title), simplified(summary)
    text = f'{title}\n{summary}'
    # Classify by the title first; a passing keyword in the summary should not override it.
    profile = TOPIC_PROFILES.get(topic)
    if profile is None:
        profile = next((p for p in PROFILES if any(k.lower() in title.lower() for k in p[1])), None)
    if profile is None:
        profile = next((p for p in PROFILES if any(k.lower() in text.lower() for k in p[1])), DEFAULT)
    topic, _, lens, effects, questions, watch = profile
    numbers = list(dict.fromkeys(re.findall(r'\d+(?:[.,]\d+)*(?:%|％|亿|万|年|月|日|人|次|份|个)?', text)))[:6]
    return dict(title=title, summary=summary, topic=topic, lens=lens, effects=effects,
                questions=questions, watch=watch, numbers=numbers)


def clean_summary(title: str, summary: str) -> str:
    description = simplified(summary).strip()
    headline = simplified(title).strip()
    if headline and description.startswith(headline):
        description = description[len(headline):].lstrip(' \t\r\n：:。-—')
    parts = re.split(r'(?<=[。！？])\s*|(?:\r?\n){2,}', description)
    seen, unique = set(), []
    for part in parts:
        part = part.strip()
        key = re.sub(r'\s+', '', part)
        if key and key not in seen:
            unique.append(part)
            seen.add(key)
    return '\n\n'.join(unique)


def guide_html(title: str, summary: str, topic: str = '', compact: bool = False) -> str:
    data = build_guide(title, summary, topic)
    esc = html.escape
    def section(heading, items):
        return '<h3>' + heading + '</h3><ul>' + ''.join('<li>' + esc(item) + '</li>' for item in items) + '</ul>'
    document = '<style>body{color:#203047;line-height:1.65}h3{color:#234f80;margin-top:20px}li{margin-bottom:10px}p{margin-bottom:12px}</style>'
    document += '<p style="color:#657089">本地阅读引导 · 基于来源标题与摘要 · ' + esc(data['topic']) + '</p>'
    document += '<h3>来源报道了什么</h3>'
    if not compact:
        document += '<p><b>' + esc(data['title']) + '</b></p>'
    description = clean_summary(data['title'], data['summary']) or '该来源未提供独立摘要，请先阅读原文，再判断下方推演是否适用。'
    document += ''.join('<p>' + esc(part) + '</p>' for part in description.split('\n\n'))
    document += '<h3>这条新闻的阅读抓手</h3><p>'
    if not compact:
        document += '围绕“' + esc(data['title']) + '”，重点看：'
    document += esc(data['lens']) + '</p>'
    if data['numbers']:
        document += '<p>原文中的数字线索：' + esc('、'.join(data['numbers'])) + '。请回到原文核对其含义与比较基准。</p>'
    document += section('可能的影响路径（条件推演）', data['effects'])
    document += section('带着这两个问题读原文', data['questions'])
    document += section('接下来关注什么', data['watch'])
    document += '<p style="color:#657089">以上为按主题组织的本地阅读提示，未读取全文或进行多方核实，也不是对报道结论的独立确认。</p>'
    return document
