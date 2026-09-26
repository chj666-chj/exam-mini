"""Markdown 工具（零依赖实现，覆盖题库排版所需子集）。

支持语法：
- **加粗** / __加粗__
- ==高亮==（重点标记，前端渲染为 <mark>）
- *斜体* / _斜体_
- # 标题（1~4 级）
- 行内代码 `code`
- 图片 ![alt](url)
- 链接 [文字](url)
- 列表 - / 1.
"""
import re

_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s+', re.MULTILINE)
_BOLD_RE = re.compile(r'(\*\*|__)(.*?)\1')
_ITALIC_RE = re.compile(r'(?<!\w)(\*|_)(?!\s)(.*?)(?<!\s)\1(?!\w)')
_HIGHLIGHT_RE = re.compile(r'==(.*?)==')
_CODE_RE = re.compile(r'`([^`]*)`')
_BLOCKQUOTE_RE = re.compile(r'^\s{0,3}>\s?', re.MULTILINE)
_LIST_RE = re.compile(r'^\s*(?:[-*+]|\d+\.)\s+', re.MULTILINE)

ALLOWED_IMAGE_SCHEMES = ('http://', 'https://', '/media/', 'data:image/')


def extract_images(markdown_text):
    """提取 Markdown 中的图片地址，返回 [{'alt', 'url', 'title'}]。"""
    if not markdown_text:
        return []
    images = []
    for match in _IMAGE_RE.finditer(markdown_text):
        alt, url, title = match.group(1) or '', match.group(2) or '', match.group(3) or ''
        images.append({'alt': alt, 'url': url, 'title': title})
    return images


def validate_markdown(markdown_text):
    """校验 Markdown 语法与图片地址，返回错误信息列表。"""
    errors = []
    if not isinstance(markdown_text, str):
        return ['正文必须是字符串']
    text = markdown_text
    # 未闭合的重点标记
    if text.count('==') % 2 != 0:
        errors.append('存在未闭合的高亮标记 ==')
    for image in extract_images(text):
        url = image['url']
        if not url.startswith(ALLOWED_IMAGE_SCHEMES):
            errors.append(f'图片地址不合法：{url[:60]}')
    # 未闭合的加粗
    if text.count('**') % 2 != 0:
        errors.append('存在未闭合的加粗标记 **')
    return errors


def strip_markdown(markdown_text, max_length=0):
    """把 Markdown 还原为纯文本（用于列表摘要与重复检测）。"""
    if not markdown_text:
        return ''
    text = str(markdown_text)
    text = _IMAGE_RE.sub(lambda m: f'[图:{m.group(1) or "图片"}]', text)
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _HEADING_RE.sub('', text)
    text = _BOLD_RE.sub(lambda m: m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(2), text)
    text = _HIGHLIGHT_RE.sub(lambda m: m.group(1), text)
    text = _CODE_RE.sub(lambda m: m.group(1), text)
    text = _BLOCKQUOTE_RE.sub('', text)
    text = _LIST_RE.sub('· ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if max_length and len(text) > max_length:
        return text[:max_length] + '…'
    return text


def normalize_title(markdown_text):
    """重复检测用的归一化标题：去 Markdown、去空白、小写。"""
    return re.sub(r'\s+', '', strip_markdown(markdown_text)).lower()
