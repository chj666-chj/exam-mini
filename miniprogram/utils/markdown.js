/**
 * 轻量级 Markdown → rich-text nodes 解析器（纯 JS，无依赖）
 *
 * 支持语法：
 *   # / ## / ###  标题
 *   **bold**      加粗
 *   *italic*      斜体
 *   ![](url)      图片
 *   [text](url)   链接
 *   - / 1.        无序/有序列表
 *   >             引用
 *   `code`        行内代码
 *   ```           代码块
 *   | | |         表格
 *   \n\n          段落
 *
 * 输出格式：微信小程序 rich-text nodes 数组
 *   [{name: 'div', attrs: {class: 'md-h1'}, children: [{type: 'text', text: '内容'}]}]
 */

/**
 * 解析行内文本：处理加粗、斜体、行内代码、图片、链接
 * @param {string} text - 行内文本
 * @returns {Array} rich-text 子节点数组
 */
function parseInline(text) {
  var children = []
  var pos = 0

  while (pos < text.length) {
    // 找到最近的特殊字符
    var nextSpecial = text.length
    var specialType = null

    // ** 加粗
    var boldIdx = text.indexOf('**', pos)
    if (boldIdx >= 0 && boldIdx < nextSpecial) {
      nextSpecial = boldIdx
      specialType = 'bold'
    }

    // ` 行内代码
    var codeIdx = text.indexOf('`', pos)
    if (codeIdx >= 0 && codeIdx < nextSpecial) {
      nextSpecial = codeIdx
      specialType = 'code'
    }

    // ![ 图片
    var imgIdx = text.indexOf('![', pos)
    if (imgIdx >= 0 && imgIdx < nextSpecial) {
      nextSpecial = imgIdx
      specialType = 'img'
    }

    // [ 链接（排除 ![ 图片）
    var linkIdx = text.indexOf('[', pos)
    if (linkIdx >= 0 && linkIdx < nextSpecial && (linkIdx === 0 || text[linkIdx - 1] !== '!')) {
      nextSpecial = linkIdx
      specialType = 'link'
    }

    // * 斜体（排除 ** 加粗）
    var starIdx = text.indexOf('*', pos)
    if (starIdx >= 0 && starIdx < nextSpecial) {
      if (starIdx + 1 < text.length && text[starIdx + 1] === '*') {
        // 是 ** 加粗，已在上面处理
      } else {
        nextSpecial = starIdx
        specialType = 'italic'
      }
    }

    // 推入特殊字符之前的普通文本
    if (nextSpecial > pos) {
      children.push({ type: 'text', text: text.slice(pos, nextSpecial) })
      pos = nextSpecial
    }

    if (specialType === null) {
      if (pos < text.length) {
        children.push({ type: 'text', text: text.slice(pos) })
      }
      break
    }

    // 处理特殊元素
    if (specialType === 'bold') {
      var endBold = text.indexOf('**', pos + 2)
      if (endBold >= 0) {
        children.push({
          name: 'strong',
          attrs: {},
          children: parseInline(text.slice(pos + 2, endBold))
        })
        pos = endBold + 2
      } else {
        children.push({ type: 'text', text: text.slice(pos, pos + 2) })
        pos += 2
      }
    } else if (specialType === 'italic') {
      var endItalic = -1
      var searchPos = pos + 1
      while (searchPos < text.length) {
        var starPos = text.indexOf('*', searchPos)
        if (starPos < 0) break
        // 确保不是 ** 加粗的结束
        if (starPos + 1 < text.length && text[starPos + 1] === '*') {
          searchPos = starPos + 2
          continue
        }
        endItalic = starPos
        break
      }
      if (endItalic >= 0) {
        children.push({
          name: 'em',
          attrs: {},
          children: [{ type: 'text', text: text.slice(pos + 1, endItalic) }]
        })
        pos = endItalic + 1
      } else {
        children.push({ type: 'text', text: text.slice(pos, pos + 1) })
        pos += 1
      }
    } else if (specialType === 'code') {
      var endCode = text.indexOf('`', pos + 1)
      if (endCode >= 0) {
        children.push({
          name: 'code',
          attrs: { class: 'md-inline-code' },
          children: [{ type: 'text', text: text.slice(pos + 1, endCode) }]
        })
        pos = endCode + 1
      } else {
        children.push({ type: 'text', text: text.slice(pos, pos + 1) })
        pos += 1
      }
    } else if (specialType === 'img') {
      var imgEnd = text.indexOf(')', pos)
      if (imgEnd >= 0) {
        var imgContent = text.slice(pos + 2, imgEnd)
        var altEnd = imgContent.indexOf(']')
        var alt = altEnd >= 0 ? imgContent.slice(0, altEnd) : ''
        var url = altEnd >= 0 ? imgContent.slice(altEnd + 2) : imgContent
        children.push({
          name: 'img',
          attrs: { src: url, alt: alt, class: 'md-img' }
        })
        pos = imgEnd + 1
      } else {
        children.push({ type: 'text', text: text.slice(pos, pos + 2) })
        pos += 2
      }
    } else if (specialType === 'link') {
      var linkEnd = text.indexOf(')', pos)
      if (linkEnd >= 0) {
        var linkContent = text.slice(pos + 1, linkEnd)
        var textEnd = linkContent.indexOf(']')
        var linkText = textEnd >= 0 ? linkContent.slice(0, textEnd) : linkContent
        var linkUrl = textEnd >= 0 ? linkContent.slice(textEnd + 2) : ''
        children.push({
          name: 'a',
          attrs: { href: linkUrl },
          children: [{ type: 'text', text: linkText }]
        })
        pos = linkEnd + 1
      } else {
        children.push({ type: 'text', text: text.slice(pos, pos + 1) })
        pos += 1
      }
    }
  }

  if (children.length === 0) {
    children.push({ type: 'text', text: text })
  }
  return children
}

/**
 * 解析表格行
 * @param {Array} rows - 表格行数组（含表头行和分隔行之后的数据行）
 * @returns {Object} rich-text table 节点
 */
function parseTable(rows) {
  var headerCells = splitTableCells(rows[0])
  var bodyRows = rows.slice(1)

  var headerChildren = headerCells.map(function (cell) {
    return {
      name: 'th',
      attrs: { class: 'md-th' },
      children: [{ type: 'text', text: cell.trim() }]
    }
  })

  var bodyTrs = bodyRows.map(function (row) {
    var cells = splitTableCells(row)
    var tds = cells.map(function (cell) {
      return {
        name: 'td',
        attrs: { class: 'md-td' },
        children: [{ type: 'text', text: cell.trim() }]
      }
    })
    return { name: 'tr', attrs: {}, children: tds }
  })

  return {
    name: 'table',
    attrs: { class: 'md-table' },
    children: [
      { name: 'thead', attrs: {}, children: [{ name: 'tr', attrs: {}, children: headerChildren }] },
      { name: 'tbody', attrs: {}, children: bodyTrs }
    ]
  }
}

/**
 * 分割表格单元格（按 | 分割，去除首尾空单元格）
 */
function splitTableCells(row) {
  return row.split('|').filter(function (c, i, arr) {
    // 去除首尾空元素（因为行以 | 开头和结尾）
    if (i === 0 && c.trim() === '') return false
    if (i === arr.length - 1 && c.trim() === '') return false
    return true
  })
}

/**
 * 判断一行是否是列表项
 */
function isListItem(line) {
  return /^\s*-\s+/.test(line) || /^\s*\d+\.\s+/.test(line)
}

/**
 * 判断一行是否是代码块标记
 */
function isCodeBlockDelimiter(line) {
  return line.trim().startsWith('```')
}

/**
 * 主函数：将 Markdown 字符串解析为 rich-text nodes 数组
 * @param {string} md - Markdown 字符串
 * @returns {Array} rich-text nodes 数组
 */
function parse(md) {
  if (!md || typeof md !== 'string') return []

  var nodes = []
  var lines = md.split('\n')
  var i = 0

  while (i < lines.length) {
    var line = lines[i]

    // 空行：跳过
    if (line.trim() === '') {
      i++
      continue
    }

    // 代码块
    if (isCodeBlockDelimiter(line)) {
      var codeLines = []
      i++
      while (i < lines.length && !isCodeBlockDelimiter(lines[i])) {
        codeLines.push(lines[i])
        i++
      }
      i++ // 跳过结束标记 ```
      nodes.push({
        name: 'pre',
        attrs: { class: 'md-code-block' },
        children: [{ type: 'text', text: codeLines.join('\n') }]
      })
      continue
    }

    // 标题
    if (line.startsWith('### ')) {
      nodes.push({
        name: 'h3',
        attrs: { class: 'md-h3' },
        children: parseInline(line.slice(4))
      })
      i++
      continue
    }
    if (line.startsWith('## ')) {
      nodes.push({
        name: 'h2',
        attrs: { class: 'md-h2' },
        children: parseInline(line.slice(3))
      })
      i++
      continue
    }
    if (line.startsWith('# ')) {
      nodes.push({
        name: 'h1',
        attrs: { class: 'md-h1' },
        children: parseInline(line.slice(2))
      })
      i++
      continue
    }

    // 引用
    if (line.startsWith('> ')) {
      var quoteLines = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        quoteLines.push(lines[i].slice(2))
        i++
      }
      nodes.push({
        name: 'blockquote',
        attrs: { class: 'md-quote' },
        children: [{ type: 'text', text: quoteLines.join(' ') }]
      })
      continue
    }

    // 表格（行以 | 开头，且下一行是分隔符 |---|---|）
    if (line.trim().startsWith('|') && i + 1 < lines.length &&
        /^\|[\s\-:]+\|/.test(lines[i + 1].trim())) {
      var tableRows = [line]
      i += 2 // 跳过表头行和分隔符行
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableRows.push(lines[i])
        i++
      }
      nodes.push(parseTable(tableRows))
      continue
    }

    // 列表
    if (isListItem(line)) {
      var listItems = []
      var isOrdered = /^\s*\d+\.\s+/.test(line)
      while (i < lines.length && isListItem(lines[i])) {
        var itemText = lines[i].replace(/^\s*-\s+/, '').replace(/^\s*\d+\.\s+/, '')
        listItems.push({
          name: 'li',
          attrs: { class: 'md-li' },
          children: parseInline(itemText)
        })
        i++
      }
      nodes.push({
        name: isOrdered ? 'ol' : 'ul',
        attrs: { class: isOrdered ? 'md-ol' : 'md-ul' },
        children: listItems
      })
      continue
    }

    // 普通段落（收集连续的非特殊行）
    var paraLines = []
    while (i < lines.length && lines[i].trim() !== '' &&
           !lines[i].startsWith('#') && !lines[i].startsWith('> ') &&
           !isListItem(lines[i]) && !isCodeBlockDelimiter(lines[i]) &&
           !(lines[i].trim().startsWith('|') && i + 1 < lines.length &&
             /^\|[\s\-:]+\|/.test(lines[i + 1].trim()))) {
      paraLines.push(lines[i])
      i++
    }
    if (paraLines.length > 0) {
      nodes.push({
        name: 'p',
        attrs: { class: 'md-p' },
        children: parseInline(paraLines.join(' '))
      })
    }
  }

  return nodes
}

module.exports = { parse: parse }
