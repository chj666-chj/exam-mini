"""Excel 批量导入：按题型定义独立模板，解析 Excel 行并逐行校验。

支持的题型模板：single / multiple / judge / fill / qa
（multi_part 因嵌套子题结构复杂，不纳入 Excel 导入，请使用 JSON 导入。）

模板设计：每种题型一个 .xlsx 文件，含两个 Sheet：
  Sheet 1「题目导入」—— 表头行（加粗着色）+ 示例行
  Sheet 2「填写说明」—— 各字段含义、是否必填、格式要求

校验规则：逐行解析，对不合规行生成 {row, field, message} 错误明细，
校验通过的行转为 normalize_question 可消费的 item dict。
"""
import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from . import data_utils as du
from .question_schema import QTYPES

# ---------------------------------------------------------------- 模板定义

# 每种题型的列定义：key = 字段标识, header = 表头中文, required = 是否必填,
# hint = 填写说明, width = 列宽
# _FIELD: 映射到 normalize_question 输入 item 的字段名

TEMPLATE_SINGLE = {
    'qtype': 'single',
    'typename': '单选题',
    'columns': [
        {'key': 'content_md', 'header': '题目内容', 'required': True,
         'hint': '题目正文，支持 Markdown（**加粗**、==高亮==）。必填。',
         'width': 50},
        {'key': 'option_A', 'header': '选项A', 'required': True,
         'hint': '选项 A 的内容。必填。', 'width': 20},
        {'key': 'option_B', 'header': '选项B', 'required': True,
         'hint': '选项 B 的内容。必填。', 'width': 20},
        {'key': 'option_C', 'header': '选项C', 'required': False,
         'hint': '选项 C 的内容。可选。', 'width': 20},
        {'key': 'option_D', 'header': '选项D', 'required': False,
         'hint': '选项 D 的内容。可选。', 'width': 20},
        {'key': 'option_E', 'header': '选项E', 'required': False,
         'hint': '选项 E 的内容。可选。', 'width': 20},
        {'key': 'option_F', 'header': '选项F', 'required': False,
         'hint': '选项 F 的内容。可选。', 'width': 20},
        {'key': 'correct_answer', 'header': '正确答案', 'required': True,
         'hint': '正确选项的字母，如 A。必填。', 'width': 12},
        {'key': 'comments', 'header': '解析', 'required': False,
         'hint': '答案解析说明。可选。', 'width': 30},
        {'key': 'score', 'header': '分值', 'required': False,
         'hint': '题目分值，数字。可选，默认 0。', 'width': 8},
        {'key': 'difficulty', 'header': '难度等级', 'required': False,
         'hint': '如：简单 / 中等 / 困难。可选。', 'width': 12},
        {'key': 'tags', 'header': '相关标签', 'required': False,
         'hint': '标签名称，多个用英文逗号分隔。标签需已存在。可选。', 'width': 25},
        {'key': 'examid', 'header': '科目编号', 'required': False,
         'hint': '所属科目编号，如 001001。未填则使用导入页面的默认科目。', 'width': 12},
    ],
    'examples': [
        ['**面向对象**编程的三大特性不包括以下哪个？', '封装', '继承', '多态', '编译', '', '',
         'D', '封装、继承、多态是面向对象三大特性，编译属于编译原理概念。', 2, '简单', '基础知识,单选题', '001001'],
    ],
}

TEMPLATE_MULTIPLE = {
    'qtype': 'multiple',
    'typename': '多选题',
    'columns': [
        {'key': 'content_md', 'header': '题目内容', 'required': True,
         'hint': '题目正文，支持 Markdown。必填。', 'width': 50},
        {'key': 'option_A', 'header': '选项A', 'required': True,
         'hint': '选项 A 的内容。必填。', 'width': 20},
        {'key': 'option_B', 'header': '选项B', 'required': True,
         'hint': '选项 B 的内容。必填。', 'width': 20},
        {'key': 'option_C', 'header': '选项C', 'required': False,
         'hint': '选项 C 的内容。可选。', 'width': 20},
        {'key': 'option_D', 'header': '选项D', 'required': False,
         'hint': '选项 D 的内容。可选。', 'width': 20},
        {'key': 'option_E', 'header': '选项E', 'required': False,
         'hint': '选项 E 的内容。可选。', 'width': 20},
        {'key': 'option_F', 'header': '选项F', 'required': False,
         'hint': '选项 F 的内容。可选。', 'width': 20},
        {'key': 'correct_answer', 'header': '正确答案', 'required': True,
         'hint': '所有正确选项的字母，多个用英文逗号分隔，如 A,B,D。必填，至少 1 个。', 'width': 15},
        {'key': 'comments', 'header': '解析', 'required': False,
         'hint': '答案解析说明。可选。', 'width': 30},
        {'key': 'score', 'header': '分值', 'required': False,
         'hint': '题目分值，数字。可选，默认 0。', 'width': 8},
        {'key': 'difficulty', 'header': '难度等级', 'required': False,
         'hint': '如：简单 / 中等 / 困难。可选。', 'width': 12},
        {'key': 'tags', 'header': '相关标签', 'required': False,
         'hint': '标签名称，多个用英文逗号分隔。标签需已存在。可选。', 'width': 25},
        {'key': 'examid', 'header': '科目编号', 'required': False,
         'hint': '所属科目编号。未填则使用默认科目。', 'width': 12},
    ],
    'examples': [
        ['下列哪些是 ==JavaScript== 的数据类型？', 'String', 'Number', 'List', 'Boolean', '', '',
         'A,B,D', 'String、Number、Boolean 是 JS 数据类型，List 不是。', 3, '中等', '多选题,前端', '001001'],
    ],
}

TEMPLATE_JUDGE = {
    'qtype': 'judge',
    'typename': '判断题',
    'columns': [
        {'key': 'content_md', 'header': '题目内容', 'required': True,
         'hint': '题目正文，支持 Markdown。必填。', 'width': 55},
        {'key': 'correct_answer', 'header': '正确答案', 'required': True,
         'hint': '填写「正确」或「错误」，也可填 A（正确）/ B（错误）或 true/false。必填。', 'width': 12},
        {'key': 'comments', 'header': '解析', 'required': False,
         'hint': '答案解析说明。可选。', 'width': 30},
        {'key': 'score', 'header': '分值', 'required': False,
         'hint': '题目分值，数字。可选，默认 0。', 'width': 8},
        {'key': 'difficulty', 'header': '难度等级', 'required': False,
         'hint': '如：简单 / 中等 / 困难。可选。', 'width': 12},
        {'key': 'tags', 'header': '相关标签', 'required': False,
         'hint': '标签名称，多个用英文逗号分隔。可选。', 'width': 25},
        {'key': 'examid', 'header': '科目编号', 'required': False,
         'hint': '所属科目编号。未填则使用默认科目。', 'width': 12},
    ],
    'examples': [
        ['Python 是一种 ==解释型== 编程语言。', '正确', 'Python 代码由解释器逐行执行，无需编译为机器码。', 1, '简单', '判断题,Python', '001001'],
    ],
}

TEMPLATE_FILL = {
    'qtype': 'fill',
    'typename': '填空题',
    'columns': [
        {'key': 'content_md', 'header': '题目内容', 'required': True,
         'hint': '题目正文，空位用 4 个下划线 ____ 表示。必填。', 'width': 55},
        {'key': 'blank_1', 'header': '第1空答案', 'required': True,
         'hint': '第 1 空的可接受答案，多个用竖线 | 分隔，如 北京|Beijing。必填。', 'width': 20},
        {'key': 'blank_2', 'header': '第2空答案', 'required': False,
         'hint': '第 2 空的可接受答案，多个用竖线 | 分隔。可选。', 'width': 20},
        {'key': 'blank_3', 'header': '第3空答案', 'required': False,
         'hint': '第 3 空的可接受答案，多个用竖线 | 分隔。可选。', 'width': 20},
        {'key': 'blank_4', 'header': '第4空答案', 'required': False,
         'hint': '第 4 空的可接受答案，多个用竖线 | 分隔。可选。', 'width': 20},
        {'key': 'blank_5', 'header': '第5空答案', 'required': False,
         'hint': '第 5 空的可接受答案，多个用竖线 | 分隔。可选。', 'width': 20},
        {'key': 'comments', 'header': '解析', 'required': False,
         'hint': '答案解析说明。可选。', 'width': 30},
        {'key': 'score', 'header': '分值', 'required': False,
         'hint': '题目分值，数字。可选，默认 0。', 'width': 8},
        {'key': 'difficulty', 'header': '难度等级', 'required': False,
         'hint': '如：简单 / 中等 / 困难。可选。', 'width': 12},
        {'key': 'tags', 'header': '相关标签', 'required': False,
         'hint': '标签名称，多个用英文逗号分隔。可选。', 'width': 25},
        {'key': 'examid', 'header': '科目编号', 'required': False,
         'hint': '所属科目编号。未填则使用默认科目。', 'width': 12},
    ],
    'examples': [
        ['中国的首都是____，最大的经济中心是____。', '北京|Beijing', '上海|Shanghai', '', '', '',
         '北京是首都，上海是经济中心。', 2, '简单', '填空题,地理', '001001'],
    ],
}

TEMPLATE_QA = {
    'qtype': 'qa',
    'typename': '问答题',
    'columns': [
        {'key': 'content_md', 'header': '题目内容', 'required': True,
         'hint': '题目正文，支持 Markdown。必填。', 'width': 55},
        {'key': 'answer_md', 'header': '参考答案', 'required': True,
         'hint': '参考答案（支持 Markdown）。必填，除非在系统中单独启用 AI 判卷。', 'width': 50},
        {'key': 'comments', 'header': '解析', 'required': False,
         'hint': '答案解析说明。可选。', 'width': 30},
        {'key': 'score', 'header': '分值', 'required': False,
         'hint': '题目分值，数字。可选，默认 0。', 'width': 8},
        {'key': 'difficulty', 'header': '难度等级', 'required': False,
         'hint': '如：简单 / 中等 / 困难。可选。', 'width': 12},
        {'key': 'tags', 'header': '相关标签', 'required': False,
         'hint': '标签名称，多个用英文逗号分隔。可选。', 'width': 25},
        {'key': 'examid', 'header': '科目编号', 'required': False,
         'hint': '所属科目编号。未填则使用默认科目。', 'width': 12},
    ],
    'examples': [
        ['请简述 ==RESTful API== 的设计原则。',
         'RESTful API 设计原则包括：\n1. 资源导向：URL 表示资源\n2. 使用 HTTP 方法：GET/POST/PUT/DELETE\n3. 无状态通信\n4. 统一接口',
         '本题考察 REST 架构风格的理解。', 10, '中等', '问答题,API设计', '001001'],
    ],
}

# 题型 -> 模板定义
EXCEL_TEMPLATES = {
    'single': TEMPLATE_SINGLE,
    'multiple': TEMPLATE_MULTIPLE,
    'judge': TEMPLATE_JUDGE,
    'fill': TEMPLATE_FILL,
    'qa': TEMPLATE_QA,
}

# 选项字母 -> openpyxl 列 key 的映射（single / multiple 用）
_OPTION_KEYS = ['option_A', 'option_B', 'option_C', 'option_D', 'option_E', 'option_F']
_OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F']

# 填空题最多空数
_MAX_BLANKS = 5

# 样式常量
_HEADER_FONT = Font(name='微软雅黑', bold=True, color='FFFFFF', size=11)
_HEADER_FILL = PatternFill(start_color='409EFF', end_color='409EFF', fill_type='solid')
_HEADER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
_CELL_ALIGN = Alignment(vertical='top', wrap_text=True)
_THIN_BORDER = Border(
    left=Side(style='thin', color='D0D0D0'),
    right=Side(style='thin', color='D0D0D0'),
    top=Side(style='thin', color='D0D0D0'),
    bottom=Side(style='thin', color='D0D0D0'),
)
_EXAMPLE_FONT = Font(name='微软雅黑', size=10, color='606266', italic=True)
_INSTR_TITLE_FONT = Font(name='微软雅黑', bold=True, size=14, color='303133')
_INSTR_HEAD_FONT = Font(name='微软雅黑', bold=True, size=11, color='409EFF')
_INSTR_BODY_FONT = Font(name='微软雅黑', size=10, color='606266')


# ---------------------------------------------------------------- 模板生成

def generate_template(qtype):
    """生成指定题型的 Excel 模板 Workbook。

    返回 openpyxl.Workbook，含「题目导入」+「填写说明」两个 Sheet。
    """
    tmpl = EXCEL_TEMPLATES.get(qtype)
    if not tmpl:
        return None

    wb = Workbook()
    # Sheet 1: 题目导入
    ws = wb.active
    ws.title = '题目导入'
    cols = tmpl['columns']

    for ci, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=ci, value=col['header'])
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(ci)].width = col['width']

    # 示例行
    for example in tmpl.get('examples', []):
        row_num = ws.max_row + 1
        for ci, val in enumerate(example, 1):
            cell = ws.cell(row=row_num, column=ci, value=val)
            cell.font = _EXAMPLE_FONT
            cell.alignment = _CELL_ALIGN
            cell.border = _THIN_BORDER

    # 冻结表头
    ws.freeze_panes = 'A2'
    # 行高
    ws.row_dimensions[1].height = 28

    # Sheet 2: 填写说明
    ws2 = wb.create_sheet('填写说明')
    ws2.column_dimensions['A'].width = 16
    ws2.column_dimensions['B'].width = 10
    ws2.column_dimensions['C'].width = 60

    ws2.cell(row=1, column=1, value=f'{tmpl["typename"]} Excel 导入模板说明').font = _INSTR_TITLE_FONT
    ws2.merge_cells('A1:C1')

    row = 3
    headers = ['字段', '是否必填', '说明']
    for ci, h in enumerate(headers, 1):
        cell = ws2.cell(row=row, column=ci, value=h)
        cell.font = _INSTR_HEAD_FONT
        cell.alignment = Alignment(horizontal='center')
    row += 1

    for col in cols:
        ws2.cell(row=row, column=1, value=col['header']).font = _INSTR_BODY_FONT
        ws2.cell(row=row, column=2, value='必填' if col['required'] else '可选').font = _INSTR_BODY_FONT
        ws2.cell(row=row, column=3, value=col['hint']).font = _INSTR_BODY_FONT
        ws2.cell(row=row, column=2).alignment = Alignment(horizontal='center')
        row += 1

    # 通用注意事项
    row += 1
    notes = [
        '',
        '【通用注意事项】',
        '1. 请勿修改表头行（第 1 行），否则导入将无法识别列。',
        '2. 示例行（第 2 行）可删除或覆盖，不影响导入。',
        '3. 题目内容支持 Markdown 语法：**加粗**、==高亮==、![图片](url) 等。',
        '4. 标签名称需与系统中已创建的标签一致（按名称匹配），多个标签用英文逗号分隔。',
        '5. 科目编号若留空，将使用导入页面的默认科目编号。',
        '6. 空行将被自动跳过；每行数据会逐行校验，不合规行不会导入但不会中断整体流程。',
    ]
    for note in notes:
        ws2.cell(row=row, column=1, value=note).font = _INSTR_BODY_FONT
        if note.startswith('【'):
            ws2.cell(row=row, column=1).font = _INSTR_HEAD_FONT
        row += 1

    return wb


def template_to_bytes(qtype):
    """生成模板并返回 (bytes, filename)。"""
    wb = generate_template(qtype)
    if not wb:
        return None, None
    buf = io.BytesIO()
    wb.save(buf)
    tmpl = EXCEL_TEMPLATES[qtype]
    filename = f'{tmpl["typename"]}导入模板.xlsx'
    return buf.getvalue(), filename


# ---------------------------------------------------------------- Excel 解析

def _cell_text(cell):
    """安全取单元格文本值。"""
    if cell is None:
        return ''
    val = cell.value
    if val is None:
        return ''
    return str(val).strip()


def _is_empty_row(row_cells):
    """判断整行是否为空。"""
    return all(not _cell_text(c) for c in row_cells)


def _resolve_tag_names(name_str, existing_tags_by_name):
    """将逗号分隔的标签名称解析为 tag_id 列表。

    existing_tags_by_name: {name_lower: Tag} 映射。
    返回 (tag_ids, not_found_names)。
    """
    if not name_str:
        return [], []
    names = [n.strip() for n in name_str.split(',') if n.strip()]
    tag_ids = []
    not_found = []
    for name in names:
        tag = existing_tags_by_name.get(name.lower())
        if tag:
            tag_ids.append(tag.pk)
        else:
            not_found.append(name)
    return tag_ids, not_found


def parse_excel(file_obj, qtype, default_examid='', existing_tags=None):
    """解析上传的 Excel 文件，逐行转换为题目 item 并校验。

    参数：
        file_obj      —— Django UploadedFile 或文件类对象
        qtype         —— 题型代码（single/multiple/judge/fill/qa）
        default_examid — 默认科目编号
        existing_tags —— Tag queryset 或 None（用于标签名解析）

    返回：
        {
          'items': [item_dict, ...],       # 校验通过、可导入的题目
          'errors': [error_dict, ...],     # 校验失败的行明细
          'total_rows': int,               # 数据总行数（不含表头）
          'valid_count': int,              # 校验通过行数
          'invalid_count': int,            # 校验失败行数
        }
    """
    tmpl = EXCEL_TEMPLATES.get(qtype)
    if not tmpl:
        return {
            'items': [], 'errors': [{'row': 0, 'field': '', 'message': f'不支持的题型：{qtype}'}],
            'total_rows': 0, 'valid_count': 0, 'invalid_count': 1,
        }

    # 构建标签名 -> Tag 映射
    tags_by_name = {}
    if existing_tags:
        for tag in existing_tags:
            tags_by_name[tag.name.lower()] = tag

    # 读取 Excel
    wb = load_workbook(filename=io.BytesIO(file_obj.read()), data_only=True)
    ws = wb.active

    # 读取表头，建立 列名 -> 列索引 映射
    header_map = {}  # key -> col_index (1-based)
    for ci in range(1, ws.max_column + 1):
        header = _cell_text(ws.cell(row=1, column=ci))
        if not header:
            continue
        # 通过表头中文反查 key
        for col in tmpl['columns']:
            if col['header'] == header:
                header_map[col['key']] = ci
                break

    # 校验必需列是否存在
    missing_cols = []
    for col in tmpl['columns']:
        if col['required'] and col['key'] not in header_map:
            missing_cols.append(col['header'])

    if missing_cols:
        return {
            'items': [],
            'errors': [{'row': 1, 'field': ','.join(missing_cols),
                        'message': f'模板缺少必需列：{", ".join(missing_cols)}，请使用最新模板重新下载'}],
            'total_rows': 0, 'valid_count': 0, 'invalid_count': 1,
        }

    # 逐行解析
    items = []
    errors = []
    warnings = []
    total_rows = 0

    # 从第 2 行开始（跳过表头）
    for ri in range(2, ws.max_row + 1):
        row_cells = [ws.cell(row=ri, column=ci) for ci in range(1, ws.max_column + 1)]
        if _is_empty_row(row_cells):
            continue

        total_rows += 1
        row_errors = []
        row_warnings = []

        def get_val(key):
            """安全取某列的值。"""
            ci = header_map.get(key)
            if ci is None:
                return ''
            return _cell_text(ws.cell(row=ri, column=ci))

        def get_header(key):
            """取列的中文表头名（用于错误提示）。"""
            for col in tmpl['columns']:
                if col['key'] == key:
                    return col['header']
            return key

        # ---- 必填校验 ----
        for col in tmpl['columns']:
            if col['required']:
                val = get_val(col['key'])
                if not val:
                    row_errors.append({
                        'row': ri, 'field': col['header'],
                        'message': f'第 {ri} 行，字段「{col["header"]}」不能为空',
                    })

        content_md = get_val('content_md')
        examid = get_val('examid') or du.to_text(default_examid).strip()

        if not content_md:
            # 必填校验已覆盖，跳过后续解析
            if row_errors:
                errors.extend(row_errors)
            continue

        # ---- 按题型构建 item ----
        item = {
            'qtype': qtype,
            'content_md': content_md,
            'examid': examid,
            'comments': get_val('comments'),
            'score': du.to_number(get_val('score'), 0),
        }

        difficulty = get_val('difficulty')
        if difficulty:
            item['difficulty'] = difficulty

        # 标签解析（标签不存在为警告，不阻断导入）
        tag_str = get_val('tags')
        if tag_str:
            tag_ids, not_found = _resolve_tag_names(tag_str, tags_by_name)
            if not_found:
                row_warnings.append({
                    'row': ri, 'field': get_header('tags'),
                    'message': f'第 {ri} 行，标签「{", ".join(not_found)}」在系统中不存在，已跳过这些标签绑定',
                })
            if tag_ids:
                item['tag_ids'] = tag_ids

        # ---- 题型特有字段 ----
        if qtype in ('single', 'multiple'):
            # 构建选项
            options = []
            for idx, (okey, letter) in enumerate(zip(_OPTION_KEYS, _OPTION_LETTERS)):
                opt_content = get_val(okey)
                if not opt_content:
                    continue
                options.append({
                    'code': letter,
                    'content': opt_content,
                    'is_correct': False,  # 后面根据 correct_answer 设置
                })

            if len(options) < 2:
                row_errors.append({
                    'row': ri, 'field': '选项',
                    'message': f'第 {ri} 行，至少需要 2 个选项（当前仅 {len(options)} 个）',
                })

            # 解析正确答案
            correct_str = get_val('correct_answer')
            if correct_str:
                correct_letters = [c.strip().upper() for c in correct_str.split(',') if c.strip()]
                valid_letters = {o['code'] for o in options}
                invalid_letters = [c for c in correct_letters if c not in valid_letters]
                if invalid_letters:
                    row_errors.append({
                        'row': ri, 'field': get_header('correct_answer'),
                        'message': f'第 {ri} 行，正确答案「{", ".join(invalid_letters)}」不在已填选项范围内',
                    })
                else:
                    for opt in options:
                        if opt['code'] in correct_letters:
                            opt['is_correct'] = True

                if qtype == 'single':
                    if len(correct_letters) > 1:
                        row_errors.append({
                            'row': ri, 'field': get_header('correct_answer'),
                            'message': f'第 {ri} 行，单选题正确答案只能有 1 个（当前 {len(correct_letters)} 个）',
                        })
                else:  # multiple
                    if len(correct_letters) < 1:
                        row_errors.append({
                            'row': ri, 'field': get_header('correct_answer'),
                            'message': f'第 {ri} 行，多选题至少需要 1 个正确答案',
                        })

            item['options'] = options

        elif qtype == 'judge':
            # 解析正确答案
            correct_str = get_val('correct_answer')
            truthy = correct_str in ('正确', '对', 'A', 'a', 'true', 'True', '1', '是')
            falsy = correct_str in ('错误', '错', 'B', 'b', 'false', 'False', '0', '否')
            if not (truthy or falsy):
                row_errors.append({
                    'row': ri, 'field': get_header('correct_answer'),
                    'message': f'第 {ri} 行，判断题答案需为「正确」或「错误」（当前值「{correct_str}」无法识别）',
                })
            else:
                item['answer'] = True if truthy else False

        elif qtype == 'fill':
            # 解析填空答案
            blanks = []
            for bi in range(1, _MAX_BLANKS + 1):
                blank_str = get_val(f'blank_{bi}')
                if not blank_str:
                    continue
                # 多个可接受答案用 | 分隔
                answers = [a.strip() for a in blank_str.split('|') if a.strip()]
                if not answers:
                    row_errors.append({
                        'row': ri, 'field': f'第{bi}空答案',
                        'message': f'第 {ri} 行，第 {bi} 空答案不能为空',
                    })
                blanks.append(answers)

            if not blanks:
                row_errors.append({
                    'row': ri, 'field': '填空答案',
                    'message': f'第 {ri} 行，填空题至少需要 1 个空的答案',
                })

            # 校验空位数与正文 ____ 占位符数量匹配
            placeholder_count = content_md.count('____')
            if placeholder_count > 0 and placeholder_count != len(blanks):
                row_errors.append({
                    'row': ri, 'field': '填空答案',
                    'message': f'第 {ri} 行，正文有 {placeholder_count} 个空位（____），但只填了 {len(blanks)} 空答案',
                })

            item['blanks'] = blanks

        elif qtype == 'qa':
            # 参考答案（必填校验已在上方统一处理，此处仅在非空时赋值）
            answer_md = get_val('answer_md')
            if answer_md:
                item['answer_md'] = answer_md

        # ---- 汇总 ----
        if row_errors:
            errors.extend(row_errors)
            # 有阻断性错误时仍收集警告
            if row_warnings:
                warnings.extend(row_warnings)
        else:
            items.append(item)
            if row_warnings:
                warnings.extend(row_warnings)

    return {
        'qtype': qtype,
        'items': items,
        'errors': errors,
        'warnings': warnings,
        'total_rows': total_rows,
        'valid_count': len(items),
        'invalid_count': total_rows - len(items),
    }


def available_templates():
    """返回可用模板列表（供前端展示题型选择）。"""
    result = []
    for code, tmpl in EXCEL_TEMPLATES.items():
        result.append({
            'qtype': code,
            'typename': tmpl['typename'],
            'columns': [col['header'] for col in tmpl['columns']],
            'required_columns': [col['header'] for col in tmpl['columns'] if col['required']],
        })
    return result
