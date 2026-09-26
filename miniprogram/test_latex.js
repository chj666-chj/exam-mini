// Test _preprocessMath logic from exam.js
function _preprocessMath(text) {
  if (!text || typeof text !== 'string') return '';
  var s = text;
  // 去掉行内 LaTeX 定界符 $...$ 和 \(...\)
  s = s.replace(/\$([^$]+)\$/g, function (_, inner) {
    return inner;
  });
  s = s.replace(/\\\(([^)]+)\\\)/g, function (_, inner) {
    return inner;
  });
  // 去掉块级 LaTeX 定界符 $$...$$ 和 \[...\]
  s = s.replace(/\$\$([^$]+)\$\$/g, function (_, inner) {
    return inner;
  });
  s = s.replace(/\\\[([^\]]+)\\\]/g, function (_, inner) {
    return inner;
  });
  // 上标转换
  var supMap = { '0': '\u2070', '1': '\u00B9', '2': '\u00B2', '3': '\u00B3', '4': '\u2074', '5': '\u2075', '6': '\u2076', '7': '\u2077', '8': '\u2078', '9': '\u2079', '+': '\u207A', '-': '\u207B', '=': '\u207C', '(': '\u207D', ')': '\u207E' };
  s = s.replace(/\^{([^}]+)}/g, function (_, inner) {
    return inner.split('').map(function (c) { return supMap[c] || c; }).join('');
  });
  s = s.replace(/\^(\d)/g, function (_, d) {
    return supMap[d] || ('^' + d);
  });
  // 下标转换
  var subMap = { '0': '\u2080', '1': '\u2081', '2': '\u2082', '3': '\u2083', '4': '\u2084', '5': '\u2085', '6': '\u2086', '7': '\u2087', '8': '\u2088', '9': '\u2089' };
  s = s.replace(/_{([^}]+)}/g, function (_, inner) {
    return inner.split('').map(function (c) { return subMap[c] || c; }).join('');
  });
  s = s.replace(/_(\d)/g, function (_, d) {
    return subMap[d] || ('_' + d);
  });
  // \times → ×, \div → ÷, etc.
  s = s.replace(/\\times/g, '\u00D7').replace(/\\div/g, '\u00F7');
  s = s.replace(/\\leq/g, '\u2264').replace(/\\geq/g, '\u2265').replace(/\\neq/g, '\u2260');
  // \frac{a}{b} → a/b
  s = s.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, function (_, a, b) {
    return a + '/' + b;
  });
  // \sqrt{x} → √x
  s = s.replace(/\\sqrt\{([^}]+)\}/g, function (_, x) {
    return '\u221A' + x;
  });
  return s;
}

// Test with the user's example
var test1 = '二进制数 11011 从右向左的权值依次为 $2^0, 2^1, 2^2, 2^3, 2^4$。\n计算：$1 \\times 2^4 + 1 \\times 2^3 + 0 \\times 2^2 + 1 \\times 2^1 + 1 \\times 2^0$\n$= 16 + 8 + 0 + 2 + 1$\n$= 27$';
console.log('=== Test 1: LaTeX math ===');
console.log('Input:', test1);
console.log('Output:', _preprocessMath(test1));
console.log('');

// Test with Markdown bold + lists
var test2 = '正确答案是 **D. 27**。\n\n**解析：**\n- 按权展开：$1 \\times 2^4 + 1 \\times 2^3 + 0 \\times 2^2 + 1 \\times 2^1 + 1 \\times 2^0$\n- 计算结果：$16 + 8 + 0 + 2 + 1 = 27$';
console.log('=== Test 2: Markdown + LaTeX ===');
console.log('Input:', test2);
console.log('Output:', _preprocessMath(test2));
console.log('');

// Test markdown parsing
var md = require('./utils/markdown.js');
var processed = _preprocessMath(test2);
var nodes = md.parse(processed);
console.log('=== Test 3: Markdown nodes ===');
console.log('Node count:', nodes.length);
nodes.forEach(function(n, i) {
  console.log('  Node', i, ':', n.name || n.type, '-', JSON.stringify(n).slice(0, 100));
});
