<template>
  <div class="md-render" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: { type: String, default: '' },
  // 是否开启 ==高亮== 语法
  highlight: { type: Boolean, default: true },
})

marked.setOptions({
  breaks: true,
  gfm: true,
})

/* ---- LaTeX 数学公式预处理 ----
 * 在交给 marked 之前，把 $...$ 和 $$...$$ 中的 LaTeX 转换为 HTML，
 * 避免 marked 把 $ 当普通文本、把 ^/_ 当 Markdown 语法处理。
 */

// 常见 LaTeX 符号 → Unicode/HTML 映射表
const LATEX_SYMBOLS = {
  '\\times': '\u00D7',       // ×
  '\\div': '\u00F7',          // ÷
  '\\pm': '\u00B1',           // ±
  '\\mp': '\u2213',           // ∓
  '\\cdot': '\u00B7',         // ·
  '\\cdots': '\u22EF',        // ⋯
  '\\ldots': '\u2026',        // …
  '\\vdots': '\u22EE',        // ⋮
  '\\leq': '\u2264',          // ≤
  '\\geq': '\u2265',          // ≥
  '\\neq': '\u2260',          // ≠
  '\\approx': '\u2248',       // ≈
  '\\equiv': '\u2261',        // ≡
  '\\sim': '\u223C',          // ∼
  '\\propto': '\u221D',       // ∝
  '\\infty': '\u221E',        // ∞
  '\\partial': '\u2202',      // ∂
  '\\nabla': '\u2207',        // ∇
  '\\forall': '\u2200',       // ∀
  '\\exists': '\u2203',       // ∃
  '\\in': '\u2208',           // ∈
  '\\notin': '\u2209',        // ∉
  '\\subset': '\u2282',       // ⊂
  '\\supset': '\u2283',       // ⊃
  '\\subseteq': '\u2286',     // ⊆
  '\\supseteq': '\u2287',     // ⊇
  '\\cup': '\u222A',          // ∪
  '\\cap': '\u2229',          // ∩
  '\\emptyset': '\u2205',     // ∅
  '\\sum': '\u03A3',          // Σ
  '\\prod': '\u03A0',         // Π
  '\\int': '\u222B',          // ∫
  '\\oint': '\u222E',         // ∮
  '\\sqrt': '\u221A',         // √ (特殊处理，见下方)
  '\\pi': '\u03C0',           // π
  '\\theta': '\u03B8',        // θ
  '\\alpha': '\u03B1',        // α
  '\\beta': '\u03B2',         // β
  '\\gamma': '\u03B3',        // γ
  '\\delta': '\u03B4',        // δ
  '\\epsilon': '\u03B5',      // ε
  '\\varepsilon': '\u03F5',   // ϵ
  '\\zeta': '\u03B6',         // ζ
  '\\eta': '\u03B7',          // η
  '\\iota': '\u03B9',         // ι
  '\\kappa': '\u03BA',        // κ
  '\\lambda': '\u03BB',       // λ
  '\\mu': '\u03BC',           // μ
  '\\nu': '\u03BD',           // ν
  '\\xi': '\u03BE',           // ξ
  '\\rho': '\u03C1',          // ρ
  '\\sigma': '\u03C3',        // σ
  '\\tau': '\u03C4',          // τ
  '\\upsilon': '\u03C5',      // υ
  '\\phi': '\u03C6',          // φ
  '\\varphi': '\u03D5',       // ϕ
  '\\chi': '\u03C7',          // χ
  '\\psi': '\u03C8',          // ψ
  '\\omega': '\u03C9',        // ω
  '\\Gamma': '\u0393',        // Γ
  '\\Delta': '\u0394',        // Δ
  '\\Theta': '\u0398',        // Θ
  '\\Lambda': '\u039B',       // Λ
  '\\Xi': '\u039E',           // Ξ
  '\\Pi': '\u03A0',           // Π
  '\\Sigma': '\u03A3',        // Σ
  '\\Phi': '\u03A6',          // Φ
  '\\Psi': '\u03A8',          // Ψ
  '\\Omega': '\u03A9',        // Ω
  '\\to': '\u2192',           // →
  '\\rightarrow': '\u2192',   // →
  '\\leftarrow': '\u2190',    // ←
  '\\Rightarrow': '\u21D2',   // ⇒
  '\\Leftarrow': '\u21D0',    // ⇐
  '\\leftrightarrow': '\u2194', // ↔
  '\\Leftrightarrow': '\u21D4',  // ⇔
  '\\mapsto': '\u21A6',       // ↦
  '\\uparrow': '\u2191',      // ↑
  '\\downarrow': '\u2193',    // ↓
  '\\circ': '\u00B0',         // °
  '\\angle': '\u2220',        // ∠
  '\\perp': '\u22A5',         // ⊥
  '\\parallel': '\u2225',     // ∥
  '\\triangle': '\u25B3',     // △
  '\\degree': '\u00B0',       // °
  '\\prime': '\u2032',        // ′
  '\\dagger': '\u2020',       // †
  '\\bullet': '\u2022',       // •
  '\\star': '\u22C6',         // ⋆
  '\\oplus': '\u2295',        // ⊕
  '\\ominus': '\u2296',       // ⊖
  '\\otimes': '\u2297',       // ⊗
  '\\oslash': '\u2298',       // ⊘
  '\\odot': '\u2299',         // ⊙
  '\\bigcup': '\u22C3',       // ⋃
  '\\bigcap': '\u22C2',       // ⋂
  '\\bigoplus': '\u2A01',     // ⨁
  '\\bigotimes': '\u2A02',    // ⨂
  '\\langle': '\u27E8',       // ⟨
  '\\rangle': '\u27E9',       // ⟩
  '\\ell': '\u2113',          // ℓ
  '\\hbar': '\u210F',         // ℏ
  '\\Re': '\u211C',           // ℜ
  '\\Im': '\u2111',           // ℑ
  '\\aleph': '\u2135',        // ℵ
  '\\imath': '\u0131',        // ı
  '\\jmath': '\u0237',        // ȷ
  '\\neg': '\u00AC',          // ¬
  '\\land': '\u2227',         // ∧
  '\\lor': '\u2228',          // ∨
  '\\sin': 'sin',
  '\\cos': 'cos',
  '\\tan': 'tan',
  '\\cot': 'cot',
  '\\sec': 'sec',
  '\\csc': 'csc',
  '\\arcsin': 'arcsin',
  '\\arccos': 'arccos',
  '\\arctan': 'arctan',
  '\\log': 'log',
  '\\ln': 'ln',
  '\\lg': 'lg',
  '\\lim': 'lim',
  '\\max': 'max',
  '\\min': 'min',
  '\\exp': 'exp',
  '\\det': 'det',
  '\\dim': 'dim',
  '\\ker': 'ker',
  '\\deg': 'deg',
  '\\hom': 'hom',
  '\\arg': 'arg',
  '\\sup': 'sup',
  '\\inf': 'inf',
}

/**
 * 将 LaTeX 数学表达式内容转换为 HTML。
 * 处理顺序：先保护 {} 分组 → 替换符号 → 处理上下标 → 处理 \frac/\sqrt → 恢复分组。
 */
function latexToHtml(latex) {
  let s = latex

  // 1) 去掉 \left 和 \right 修饰符（仅保留括号本身）
  s = s.replace(/\\left\s*/g, '').replace(/\\right\s*/g, '')

  // 2) 处理 \frac{a}{b} → a/b（先处理，避免被后续 {} 移除干扰）
  s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, function(_, num, den) {
    return '<span class="math-frac"><span class="math-num">' + num.trim() + '</span><span class="math-den">' + den.trim() + '</span></span>'
  })
  // 嵌套 frac：再跑一轮
  s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, function(_, num, den) {
    return '<span class="math-frac"><span class="math-num">' + num.trim() + '</span><span class="math-den">' + den.trim() + '</span></span>'
  })

  // 3) 处理 \sqrt{x} → √x̄（用上划线表示根号下的内容）
  s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, function(_, inner) {
    return '\u221A<span class="math-sqrt">' + inner.trim() + '</span>'
  })
  s = s.replace(/\\sqrt\s*([a-zA-Z0-9])/g, '\u221A$1')

  // 4) 处理 \overline{x} → x̄
  s = s.replace(/\\overline\s*\{([^{}]*)\}/g, function(_, inner) {
    return '<span style="text-decoration: overline">' + inner.trim() + '</span>'
  })

  // 5) 处理 \text{...} / \mathrm{...} / \textbf{...} → 直接取内容
  s = s.replace(/\\(?:text|mathrm|mathbf|mathsf|mathtt)\s*\{([^{}]*)\}/g, '$1')

  // 6) 替换 LaTeX 符号命令（按长度降序排列，避免短前缀覆盖长命令）
  const sortedSymbols = Object.keys(LATEX_SYMBOLS).sort((a, b) => b.length - a.length)
  for (const cmd of sortedSymbols) {
    // 确保后面不跟字母（如 \sin 不应匹配 \single）
    const escaped = cmd.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    s = s.replace(new RegExp(escaped + '(?![a-zA-Z])', 'g'), LATEX_SYMBOLS[cmd])
  }

  // 7) 处理上标 ^{...} → <sup>...</sup>
  s = s.replace(/\^\{([^{}]+)\}/g, function(_, inner) {
    return '<sup>' + inner + '</sup>'
  })
  // 嵌套上标 ^{a^{b}} → 再跑一轮（简化处理）
  s = s.replace(/\^\{([^{}]+)\}/g, function(_, inner) {
    return '<sup>' + inner + '</sup>'
  })
  // 单字符上标 ^x → <sup>x</sup>（x 为单个非空格字符，不含 {}）
  s = s.replace(/\^([a-zA-Z0-9])/g, '<sup>$1</sup>')

  // 8) 处理下标 _{...} → <sub>...</sub>
  s = s.replace(/_\{([^{}]+)\}/g, function(_, inner) {
    return '<sub>' + inner + '</sub>'
  })
  s = s.replace(/_\{([^{}]+)\}/g, function(_, inner) {
    return '<sub>' + inner + '</sub>'
  })
  // 单字符下标 _x → <sub>x</sub>
  s = s.replace(/_([a-zA-Z0-9])/g, '<sub>$1</sub>')

  // 9) 处理 \, \; \quad \qquad 等间距命令 → 空格
  s = s.replace(/\\[,;:!]/g, ' ')
  s = s.replace(/\\quad/g, '  ')
  s = s.replace(/\\qquad/g, '   ')
  s = s.replace(/\\space/g, ' ')

  // 10) 处理 \begin{cases}...\end{cases}（分段函数）→ 简化为多行
  s = s.replace(/\\begin\{cases\}([\s\S]*?)\\end\{cases\}/g, function(_, inner) {
    const lines = inner.split('\\\\').filter(l => l.trim()).map(l => {
      return l.trim().replace(/&/g, '  ').replace(/^\s*/, '')
    })
    return '<span class="math-cases">' + lines.map(l => '&emsp;' + l).join('<br>') + '</span>'
  })

  // 11) 处理 \\（换行）→ <br>
  s = s.replace(/\\\\/g, '<br>')

  // 12) 清理残留的 &（矩阵/表格对齐符）→ 空格
  s = s.replace(/&/g, ' ')

  // 13) 移除剩余未识别的反斜杠命令（防止显示原始 \xxx）
  s = s.replace(/\\[a-zA-Z]+/g, function(match) {
    // 如果是已知符号但没被替换（不太可能），返回原样；否则返回去掉反斜杠的文本
    return match.substring(1)
  })

  // 14) 移除残留的花括号（分组用，内容已展开）
  s = s.replace(/\{([^{}]*)\}/g, '$1')
  s = s.replace(/\{([^{}]*)\}/g, '$1')
  s = s.replace(/[{}]/g, '')

  return s
}

/**
 * 预处理 Markdown 文本：
 * 1. 提取 $$...$$ 块级数学和 $...$ 行内数学
 * 2. 将 LaTeX 转换为 HTML
 * 3. 替换 ==高亮== 语法
 */
function preprocess(md) {
  if (!md) return ''

  let s = md

  // 先处理 $$...$$ 块级数学（非贪婪，跨行匹配）
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, function(_, inner) {
    const converted = latexToHtml(inner.trim())
    return '<div class="math-block">' + converted + '</div>'
  })

  // 再处理 $...$ 行内数学
  // 仅限制结尾 $ 不能紧跟数字（防止 $5、$10 等货币金额被误判为数学公式结尾），
  // 开头 $ 不做限制（因为 $2^0$ 等数学公式常以数字开头）
  s = s.replace(/\$([^$\n]+?)\$(?!\d)/g, function(_, inner) {
    const converted = latexToHtml(inner.trim())
    return '<span class="math-inline">' + converted + '</span>'
  })

  // ==高亮== → <mark>标签
  if (props.highlight) {
    s = s.replace(/==(.+?)==/g, '<mark>$1</mark>')
  }

  return s
}

const html = computed(() => {
  const raw = preprocess(props.content || '')
  const rendered = marked.parse(raw)
  return DOMPurify.sanitize(rendered, {
    ADD_TAGS: ['mark', 'sup', 'sub', 'span', 'div'],
    ADD_ATTR: ['target', 'class', 'style'],
  })
})
</script>

<style scoped>
.md-render {
  line-height: 1.7;
  font-size: 14px;
  word-break: break-word;
}

.md-render :deep(strong) {
  font-weight: 700;
  color: #303133;
}

.md-render :deep(mark) {
  background: #fef08a;
  color: #92400e;
  padding: 0 2px;
  border-radius: 2px;
}

.md-render :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 8px 0;
}

.md-render :deep(p) {
  margin: 6px 0;
}

.md-render :deep(ul),
.md-render :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.md-render :deep(code) {
  background: #f4f6fa;
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 13px;
}

.md-render :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
}

.md-render :deep(pre code) {
  background: none;
  padding: 0;
}

.md-render :deep(blockquote) {
  border-left: 3px solid #c0c4cc;
  padding-left: 12px;
  color: #606266;
  margin: 8px 0;
}

.md-render :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.md-render :deep(th),
.md-render :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.md-render :deep(th) {
  background: #f4f6fa;
  font-weight: 600;
}

/* ---- LaTeX 数学公式样式 ---- */

/* 行内公式 */
.md-render :deep(.math-inline) {
  font-family: 'Cambria Math', 'Latin Modern Math', 'STIX Two Math', Georgia, 'Times New Roman', serif;
  font-style: italic;
  background: #f8f9fb;
  padding: 1px 4px;
  border-radius: 3px;
  margin: 0 1px;
  white-space: nowrap;
}

/* 块级公式 */
.md-render :deep(.math-block) {
  font-family: 'Cambria Math', 'Latin Modern Math', 'STIX Two Math', Georgia, 'Times New Roman', serif;
  font-style: italic;
  background: #f8f9fb;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px 16px;
  margin: 10px 0;
  text-align: center;
  overflow-x: auto;
  font-size: 15px;
  line-height: 2;
}

/* 上标 */
.md-render :deep(sup) {
  font-size: 0.75em;
  vertical-align: super;
  line-height: 0;
  font-style: normal;
}

/* 下标 */
.md-render :deep(sub) {
  font-size: 0.75em;
  vertical-align: sub;
  line-height: 0;
  font-style: normal;
}

/* 分数 \frac{a}{b} */
.md-render :deep(.math-frac) {
  display: inline-flex;
  flex-direction: column;
  vertical-align: middle;
  text-align: center;
  margin: 0 2px;
  line-height: 1.1;
}

.md-render :deep(.math-num) {
  border-bottom: 1px solid currentColor;
  padding: 0 4px 1px;
  font-size: 0.85em;
}

.md-render :deep(.math-den) {
  padding: 1px 4px 0;
  font-size: 0.85em;
}

/* 根号下内容 \sqrt{x} */
.md-render :deep(.math-sqrt) {
  border-top: 1px solid currentColor;
  padding: 0 2px;
}

/* 分段函数 */
.md-render :deep(.math-cases) {
  display: inline-block;
  text-align: left;
  border-left: 2px solid #909399;
  padding-left: 8px;
}
</style>
