"""富题目数据结构：六种题型的归一化与校验。

题目仍以 core.Document(collection='questions') 存储，本文档定义扩展字段：

| 字段 | 说明 |
|------|------|
| qtype | single/multiple/judge/fill/qa/multi_part |
| title | 纯文本摘要（由 Markdown 生成，兼容小程序列表展示） |
| content_md | 题目正文 Markdown（支持 **加粗**、==高亮==、图片、列表等） |
| images | 从正文提取的图片地址列表 |
| options | 选项（single/multiple/judge 使用） |
| answer / answer_md | 填空/问答的参考答案（answer_md 为 Markdown） |
| blanks | 填空题各空可接受答案列表 |
| sub_questions | 一题多问的子题（递归结构，深度 1） |
| ai_grading | AI 判卷预留：{enabled, rubric, model, max_score} |
| tag_ids | 绑定的标签 id 列表（镜像存储，权威数据在 QuestionTag 表） |
| examid | 所属科目编号（必填） |
| score | 分值（可选） |
| typename | 兼容旧字段：题型中文名 |
"""
from . import data_utils as du
from . import markdown_utils as md

QTYPES = {
    'single': '单选题',
    'multiple': '多选题',
    'judge': '判断题',
    'fill': '填空题',
    'qa': '问答题',
    'multi_part': '一题多问',
}

# 旧字段 typename -> qtype 映射
_TYPENAME_MAP = {
    '单选': 'single', '单选题': 'single', 'single': 'single',
    '多选': 'multiple', '多选题': 'multiple', 'multiple': 'multiple',
    '判断': 'judge', '判断题': 'judge', 'judge': 'judge',
    '填空': 'fill', '填空题': 'fill', 'fill': 'fill',
    '问答': 'qa', '问答题': 'qa', '简答': 'qa', 'qa': 'qa',
    '一题多问': 'multi_part', '材料题': 'multi_part', 'multi_part': 'multi_part',
}

# 填空占位符：连续 4 个以上下划线
_BLANK_PLACEHOLDER = '____'

DEFAULT_AI_GRADING = {
    'enabled': False,   # 是否启用 AI 判卷
    'rubric': '',       # 评分要点/判分标准（Markdown）
    'model': '',        # 判卷模型标识
    'max_score': 0,     # 该题满分（0 表示未配置）
}


def infer_qtype(item):
    """从 qtype / typename / type 推导题型代码。"""
    raw = du.to_text(item.get('qtype')).strip() or du.to_text(item.get('typename')).strip() or du.to_text(item.get('type')).strip()
    if raw in QTYPES:
        return raw
    return _TYPENAME_MAP.get(raw, '')


def _normalize_options(options, allow_multiple):
    """归一化选项：value 统一为字符串 '1'/'0'。"""
    result = []
    for idx, opt in enumerate(options):
        if not isinstance(opt, dict):
            return None, f'第 {idx + 1} 个选项必须是对象'
        code = du.to_text(opt.get('code')).strip()
        content = du.to_text(opt.get('content')).strip()
        if not code:
            return None, f'第 {idx + 1} 个选项缺少选项码 code'
        if not content:
            return None, f'第 {idx + 1} 个选项缺少内容 content'
        # 兼容两种写法：value('1'/'0') 或 is_correct(true/false)
        is_correct = opt.get('is_correct')
        if is_correct is not None:
            val = '1' if is_correct in (True, 1, '1', 'true', 'True') else '0'
        else:
            val = '1' if du.to_number(opt.get('value'), 0) == 1 else '0'
        result.append({
            'code': code,
            'content': content,
            'value': val,
        })
    correct = sum(1 for o in result if o['value'] == '1')
    if allow_multiple:
        if correct < 1:
            return None, '多选题至少需要 1 个正确答案'
    else:
        if correct != 1:
            return None, '单选题必须恰好 1 个正确答案'
    return result, None


def _judge_options(answer):
    """判断题选项：answer 可为 true/false/'A'/'B'/'正确'/'错误'/1/0。"""
    truthy = answer in (True, 1, '1', 'A', 'a', '正确', '对', 'true', 'True')
    falsy = answer in (False, 0, '0', 'B', 'b', '错误', '错', 'false', 'False')
    if not (truthy or falsy):
        return None, '判断题需要 answer 字段（true/false 或 A/B 或 正确/错误）'
    return [
        {'code': 'A', 'content': '正确', 'value': '1' if truthy else '0'},
        {'code': 'B', 'content': '错误', 'value': '1' if falsy else '0'},
    ], None


def _normalize_ai_grading(raw):
    grading = dict(DEFAULT_AI_GRADING)
    if isinstance(raw, dict):
        grading['enabled'] = bool(raw.get('enabled', False))
        grading['rubric'] = du.to_text(raw.get('rubric'))
        grading['model'] = du.to_text(raw.get('model'))
        grading['max_score'] = du.to_number(raw.get('max_score'), 0)
    return grading


def normalize_sub_question(item, index, default_examid=''):
    """一题多问的子题（只允许客观型与填空/问答，不允许嵌套 multi_part）。"""
    data, errors = normalize_question(item, default_examid=default_examid, allow_types=('single', 'multiple', 'judge', 'fill', 'qa'))
    if data:
        data.pop('examid', None)  # 子题跟随母题科目
    prefix = f'第 {index + 1} 小问：'
    return data, [prefix + e for e in errors]


def normalize_question(item, default_examid='', allow_types=None):
    """归一化一道题目。

    返回 (data, errors)。data 可直接作为 Document.data；
    errors 非空时 data 为 None。
    """
    allow_types = allow_types or tuple(QTYPES.keys())
    if not isinstance(item, dict):
        return None, ['题目必须是 JSON 对象']

    errors = []
    qtype = infer_qtype(item)
    if not qtype:
        errors.append(f'题型无法识别（qtype/typename），支持：{", ".join(QTYPES.keys())}')
    elif qtype not in allow_types:
        errors.append(f'不允许的题型：{qtype}')

    # 正文：优先 content_md，兼容老字段 title 作为 Markdown 源
    content_md = du.to_text(item.get('content_md')) or du.to_text(item.get('title'))
    if not content_md.strip():
        errors.append('题目正文 content_md（或 title）不能为空')
    errors.extend(md.validate_markdown(content_md))

    examid = du.to_text(item.get('examid')).strip() or du.to_text(default_examid).strip()
    if not examid:
        errors.append('所属科目编号 examid 不能为空')

    if errors:
        return None, errors

    data = {
        'qtype': qtype,
        'typename': QTYPES.get(qtype, qtype),
        'typecode': du.to_text(item.get('typecode')) or qtype,
        'title': md.strip_markdown(content_md, max_length=60),
        'content_md': content_md,
        'images': md.extract_images(content_md),
        'examid': examid,
        'comments': du.to_text(item.get('comments')) or du.to_text(item.get('analysis')),
        'score': du.to_number(item.get('score'), 0),
        'ai_grading': _normalize_ai_grading(item.get('ai_grading')),
    }
    if 'difficulty' in item:
        data['difficulty'] = du.to_text(item.get('difficulty'))
    tag_ids = item.get('tag_ids')
    if isinstance(tag_ids, list):
        data['tag_ids'] = [int(t) for t in tag_ids if str(t).isdigit()]

    # ---- 分题型处理 ----
    if qtype in ('single', 'multiple'):
        options, err = _normalize_options(item.get('options') or [], allow_multiple=(qtype == 'multiple'))
        if err:
            return None, [err]
        data['options'] = options
    elif qtype == 'judge':
        if item.get('options'):
            options, err = _normalize_options(item['options'], allow_multiple=False)
            if err:
                return None, [err]
            data['options'] = options
        else:
            options, err = _judge_options(item.get('answer'))
            if err:
                return None, [err]
            data['options'] = options
        data['answer'] = [o['code'] for o in data['options'] if o['value'] == '1']
    elif qtype == 'fill':
        blanks = item.get('blanks')
        if not isinstance(blanks, list) or not blanks:
            return None, ['填空题需要 blanks 数组（各空可接受答案）']
        cleaned = []
        for i, blank in enumerate(blanks):
            if not isinstance(blank, list) or not blank:
                return None, [f'第 {i + 1} 空答案必须是非空数组']
            cleaned.append([du.to_text(b) for b in blank if du.to_text(b).strip()])
            if not cleaned[-1]:
                return None, [f'第 {i + 1} 空答案不能为空']
        data['blanks'] = cleaned
        data['blank_count'] = len(cleaned)
        # AI 判卷对填空同样可启用（近似匹配场景）
    elif qtype == 'qa':
        data['answer_md'] = du.to_text(item.get('answer_md')) or du.to_text(item.get('answer'))
        if not data['ai_grading']['enabled'] and not data['answer_md'].strip():
            return None, ['问答题需要 answer_md 参考答案，或在 ai_grading 中启用 AI 判卷']
    elif qtype == 'multi_part':
        subs = item.get('sub_questions')
        if not isinstance(subs, list) or len(subs) < 2:
            return None, ['一题多问需要 sub_questions 数组（至少 2 个小问）']
        if len(subs) > 20:
            return None, ['一题多问最多 20 个小问']
        sub_data = []
        sub_errors = []
        for idx, sub in enumerate(subs):
            sdata, serrs = normalize_sub_question(sub, idx, default_examid=examid)
            if serrs:
                sub_errors.extend(serrs)
            else:
                sub_data.append(sdata)
        if sub_errors:
            return None, sub_errors
        data['sub_questions'] = sub_data

    return data, []


def duplicate_key(data):
    """重复检测键：科目 + 归一化题干。"""
    return (data.get('examid') or '', md.normalize_title(data.get('content_md') or data.get('title') or ''))
