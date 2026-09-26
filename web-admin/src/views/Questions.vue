<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Tickets /></el-icon></span>
        题库管理
      </div>
      <div>
        <el-button type="success" plain @click="$router.push('/import')">
          <el-icon><Upload /></el-icon>批量导入
        </el-button>
        <el-button v-if="canAnalyze" type="primary" plain :disabled="!selection.length" :loading="batchLoading" @click="startBatchAnalyze">
          <el-icon><MagicStick /></el-icon>批量AI解析（{{ selection.length }}）
        </el-button>
        <el-button v-if="canAnalyze" type="warning" plain :disabled="!selection.length" :loading="batchTagLoading" @click="startBatchTagSync">
          <el-icon><PriceTag /></el-icon>批量AI标签（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove(ids)">
          批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建题目
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索题干 / 题型" clearable @keyup.enter="search" @clear="search" />
        <el-input v-model="filters.examid" placeholder="科目编号" clearable @keyup.enter="search" @clear="search" style="width: 160px" />
        <el-select v-model="filters.qtype" placeholder="题型" clearable @change="search" style="width: 120px">
          <el-option label="单选题" value="single" />
          <el-option label="多选题" value="multiple" />
          <el-option label="判断题" value="judge" />
          <el-option label="填空题" value="fill" />
          <el-option label="问答题" value="qa" />
          <el-option label="一题多问" value="multi_part" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="list" size="default" border stripe @selection-change="(rows) => (selection = rows)">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column prop="_id" label="ID" width="80" />
        <el-table-column label="题型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="qtypeTag(row.qtype || row.typecode)">{{ row.typename || qtypeLabel(row.qtype) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题干" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || row.content_md?.slice(0, 60) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="examid" label="科目" width="100" />
        <el-table-column label="AI解析" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="hasAnalysis(row)" type="success" size="small">已解析</el-tag>
            <el-tag v-else type="info" size="small">未解析</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="t in (row._tags || [])" :key="t.id" size="small" effect="plain" style="margin: 2px">{{ t.name }}</el-tag>
            <span v-if="!row._tags?.length" class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
            <el-button v-if="canAnalyze" link type="primary" :loading="analyzingId === row._id" @click="analyzeOne(row)">AI解析</el-button>
            <el-button v-if="canAnalyze" link type="warning" :loading="tagSyncingId === row._id" @click="openTagSync(row)">AI标签</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="remove(row._id, `题目「${row.title?.slice(0, 12)}」`)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper" background @current-change="load" @size-change="load" />
      </div>
    </div>

    <!-- 编辑/新建 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? `编辑题目 ${form._id}` : '新建题目'" width="860px" top="4vh" :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="8">
            <el-form-item label="题目ID">
              <el-input v-model="form._id" :disabled="isEdit" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="题型">
              <el-select v-model="form.qtype" style="width: 100%" @change="onQtypeChange">
                <el-option label="单选题" value="single" />
                <el-option label="多选题" value="multiple" />
                <el-option label="判断题" value="judge" />
                <el-option label="填空题" value="fill" />
                <el-option label="问答题" value="qa" />
                <el-option label="一题多问" value="multi_part" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="科目编号">
              <el-input v-model="form.examid" placeholder="如 001001" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 题干 Markdown 编辑器 -->
        <el-form-item label="题目正文">
          <div class="md-editor-wrap">
            <div class="md-toolbar">
              <el-button text size="small" @click="insertMd('**', '**', '加粗')">B</el-button>
              <el-button text size="small" @click="insertMd('==', '==', '高亮')">H</el-button>
              <el-button text size="small" @click="insertMd('`', '`', '代码')">Code</el-button>
              <el-button text size="small" @click="insertMd('\n- ', '', '列表项')">列表</el-button>
              <el-upload :show-file-list="false" :before-upload="onInsertImage" accept="image/*">
                <el-button text size="small">图片</el-button>
              </el-upload>
              <el-button text size="small" @click="mdPreview = !mdPreview">{{ mdPreview ? '编辑' : '预览' }}</el-button>
            </div>
            <el-input v-if="!mdPreview" v-model="form.content_md" type="textarea" :rows="5" placeholder="支持 Markdown：**加粗**、==高亮==、![图片](url) 等" />
            <div v-else class="md-preview-area"><MarkdownRenderer :content="form.content_md" /></div>
          </div>
        </el-form-item>

        <el-form-item label="解析">
          <el-input v-model="form.comments" type="textarea" :rows="2" placeholder="答案解析（可选）" />
        </el-form-item>

        <el-form-item label="标签">
          <el-select v-model="form.tag_ids" multiple filterable allow-create placeholder="选择或输入标签" style="width: 100%">
            <el-option v-for="t in allTags" :key="t.id" :label="t.name + ' (' + t.category + ')'" :value="t.id" />
          </el-select>
        </el-form-item>

        <!-- 单选/多选题：选项编辑器 -->
        <template v-if="form.qtype === 'single' || form.qtype === 'multiple'">
          <el-form-item :label="form.qtype === 'single' ? '选项（单选）' : '选项（多选）'">
            <div class="options-editor">
              <div v-for="(opt, idx) in form.options" :key="idx" class="option-row">
                <el-input v-model="opt.code" class="opt-code" placeholder="A" />
                <el-input v-model="opt.content" placeholder="选项内容" />
                <el-checkbox v-if="form.qtype === 'multiple'" v-model="opt.is_correct">正确</el-checkbox>
                <el-radio v-else v-model="singleCorrect" :value="idx">正确</el-radio>
                <el-button link type="danger" :disabled="form.options.length <= 2" @click="form.options.splice(idx, 1)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
              <el-button size="small" @click="addOption"><el-icon><Plus /></el-icon>新增选项</el-button>
            </div>
          </el-form-item>
        </template>

        <!-- 判断题 -->
        <template v-if="form.qtype === 'judge'">
          <el-form-item label="正确答案">
            <el-radio-group v-model="form.judgeAnswer">
              <el-radio :value="true">正确</el-radio>
              <el-radio :value="false">错误</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>

        <!-- 填空题 -->
        <template v-if="form.qtype === 'fill'">
          <el-form-item label="填空答案">
            <div class="blanks-editor">
              <div v-for="(blank, idx) in form.blanks" :key="idx" class="blank-row">
                <span class="blank-label">第 {{ idx + 1 }} 空</span>
                <el-input v-model="form.blanks[idx]" placeholder="可接受答案，用英文逗号分隔" />
                <el-button link type="danger" @click="form.blanks.splice(idx, 1)"><el-icon><Delete /></el-icon></el-button>
              </div>
              <el-button size="small" @click="form.blanks.push('')"><el-icon><Plus /></el-icon>新增空</el-button>
              <div class="hint">题干中使用 ____（4个以上下划线）标记空位</div>
            </div>
          </el-form-item>
        </template>

        <!-- 问答题 -->
        <template v-if="form.qtype === 'qa'">
          <el-form-item label="参考答案">
            <el-input v-model="form.answer_md" type="textarea" :rows="3" placeholder="参考答案（Markdown）" />
          </el-form-item>
          <el-form-item label="AI 判卷">
            <el-switch v-model="form.ai_grading.enabled" />
            <span class="hint">启用后将由 AI 自动评分（需接入判卷服务）</span>
          </el-form-item>
          <template v-if="form.ai_grading.enabled">
            <el-form-item label="评分要点">
              <el-input v-model="form.ai_grading.rubric" type="textarea" :rows="2" placeholder="评分标准/要点" />
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="判卷模型">
                  <el-input v-model="form.ai_grading.model" placeholder="如 gpt-4" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="满分">
                  <el-input-number v-model="form.ai_grading.max_score" :min="0" :max="100" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>
        </template>

        <!-- 一题多问 -->
        <template v-if="form.qtype === 'multi_part'">
          <el-form-item label="子题列表">
            <div class="subs-editor">
              <el-alert type="warning" :closable="false" style="margin-bottom: 12px" title="一题多问至少包含 2 个小问，每个小问可以是单选/多选/判断/填空/问答" />
              <div v-for="(sub, idx) in form.sub_questions" :key="idx" class="sub-block">
                <div class="sub-header">
                  <span class="sub-title">第 {{ idx + 1 }} 小问</span>
                  <el-select v-model="sub.qtype" size="small" style="width: 100px">
                    <el-option label="单选" value="single" />
                    <el-option label="多选" value="multiple" />
                    <el-option label="判断" value="judge" />
                    <el-option label="填空" value="fill" />
                    <el-option label="问答" value="qa" />
                  </el-select>
                  <el-button link type="danger" :disabled="form.sub_questions.length <= 2" @click="form.sub_questions.splice(idx, 1)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-input v-model="sub.title" placeholder="小问题干" style="margin-bottom: 8px" />
                <!-- 子题选项 -->
                <template v-if="sub.qtype === 'single' || sub.qtype === 'multiple'">
                  <div v-for="(opt, oi) in sub.options" :key="oi" class="option-row">
                    <el-input v-model="opt.code" class="opt-code" size="small" />
                    <el-input v-model="opt.content" size="small" placeholder="选项内容" />
                    <el-checkbox v-if="sub.qtype === 'multiple'" v-model="opt.is_correct" size="small">正确</el-checkbox>
                    <el-radio v-else v-model="sub._correct" :value="oi" size="small">正确</el-radio>
                    <el-button link type="danger" size="small" @click="sub.options.splice(oi, 1)"><el-icon><Delete /></el-icon></el-button>
                  </div>
                  <el-button size="small" text @click="sub.options.push({ code: String.fromCharCode(65 + sub.options.length), content: '', is_correct: false })">+选项</el-button>
                </template>
                <!-- 子题判断 -->
                <template v-if="sub.qtype === 'judge'">
                  <el-radio-group v-model="sub._judgeAnswer" size="small">
                    <el-radio :value="true">正确</el-radio>
                    <el-radio :value="false">错误</el-radio>
                  </el-radio-group>
                </template>
                <!-- 子题填空 -->
                <template v-if="sub.qtype === 'fill'">
                  <el-input v-model="sub._blanks" size="small" placeholder="可接受答案，逗号分隔" />
                </template>
                <!-- 子题问答 -->
                <template v-if="sub.qtype === 'qa'">
                  <el-input v-model="sub.answer_md" type="textarea" :rows="2" size="small" placeholder="参考答案" />
                </template>
              </div>
              <el-button size="small" @click="addSubQuestion"><el-icon><Plus /></el-icon>新增小问</el-button>
            </div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 查看 -->
    <el-dialog v-model="detailVisible" title="题目详情" width="700px" top="6vh">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="ID">{{ detail._id }}</el-descriptions-item>
        <el-descriptions-item label="题型">{{ detail.typename || qtypeLabel(detail.qtype) }}</el-descriptions-item>
        <el-descriptions-item label="科目" :span="2">{{ detail.examid }}</el-descriptions-item>
        <el-descriptions-item label="标签" :span="2">
          <el-tag v-for="t in (detail._tags || [])" :key="t.id" size="small" effect="plain" style="margin: 2px">{{ t.name }}</el-tag>
          <span v-if="!detail._tags?.length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="正文" :span="2">
          <MarkdownRenderer :content="detail.content_md || detail.title" />
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.comments" label="解析" :span="2">{{ detail.comments }}</el-descriptions-item>
      </el-descriptions>

      <!-- 选项展示 -->
      <template v-if="detail.options?.length">
        <div class="block-title" style="margin: 16px 0 8px">选项</div>
        <el-table :data="detail.options" size="small" border>
          <el-table-column prop="code" label="选项" width="60" />
          <el-table-column prop="content" label="内容" />
          <el-table-column label="正确" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="String(row.value) === '1' ? 'success' : 'info'" size="small">{{ String(row.value) === '1' ? '✓' : '✗' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 填空展示 -->
      <template v-if="detail.blanks?.length">
        <div class="block-title" style="margin: 16px 0 8px">填空答案</div>
        <div v-for="(blank, i) in detail.blanks" :key="i" style="margin: 4px 0">
          <el-tag size="small" type="info">第 {{ i + 1 }} 空</el-tag> {{ Array.isArray(blank) ? blank.join(' / ') : blank }}
        </div>
      </template>

      <!-- 问答展示 -->
      <template v-if="detail.answer_md">
        <div class="block-title" style="margin: 16px 0 8px">参考答案</div>
        <MarkdownRenderer :content="detail.answer_md" />
      </template>

      <!-- AI判卷展示 -->
      <template v-if="detail.ai_grading?.enabled">
        <div class="block-title" style="margin: 16px 0 8px">AI 判卷配置</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="模型">{{ detail.ai_grading.model || '-' }}</el-descriptions-item>
          <el-descriptions-item label="满分">{{ detail.ai_grading.max_score || '-' }}</el-descriptions-item>
          <el-descriptions-item label="评分要点" :span="2">{{ detail.ai_grading.rubric || '-' }}</el-descriptions-item>
        </el-descriptions>
      </template>

      <!-- 一题多问展示 -->
      <template v-if="detail.sub_questions?.length">
        <div class="block-title" style="margin: 16px 0 8px">子题（{{ detail.sub_questions.length }} 小问）</div>
        <div v-for="(sub, i) in detail.sub_questions" :key="i" class="sub-detail">
          <div class="sub-detail-title">第 {{ i + 1 }} 问（{{ sub.typename || qtypeLabel(sub.qtype) }}）</div>
          <MarkdownRenderer :content="sub.title || sub.content_md" />
          <div v-if="sub.options?.length" style="margin-top: 6px">
            <el-tag v-for="opt in sub.options" :key="opt.code" size="small" :type="String(opt.value) === '1' ? 'success' : 'info'" style="margin: 2px">
              {{ opt.code }}. {{ opt.content }}
            </el-tag>
          </div>
          <div v-if="sub.blanks?.length" style="margin-top: 4px; font-size: 13px; color: #606266">
            填空答案：{{ sub.blanks.map(b => Array.isArray(b) ? b.join('/') : b).join('；') }}
          </div>
          <div v-if="sub.answer_md" style="margin-top: 4px; font-size: 13px; color: #606266">
            参考答案：{{ sub.answer_md }}
          </div>
        </div>
      </template>

      <!-- AI 解析摘要 -->
      <template v-if="detail.ai_analysis && hasAnalysis(detail)">
        <div class="block-title" style="margin: 16px 0 8px">
          AI 解析
          <el-button v-if="canAnalyze" link type="primary" size="small" style="margin-left: 8px" @click="showAnalysisResult(detail)">查看完整解析</el-button>
        </div>
        <div class="ai-summary">
          <el-tag :type="difficultyTag(detail.ai_analysis.difficulty)" size="small">难度: {{ difficultyLabel(detail.ai_analysis.difficulty) }}</el-tag>
          <el-tag v-if="detail.ai_analysis.qtype_detected" size="small" type="info">题型: {{ qtypeLabel(detail.ai_analysis.qtype_detected) }}</el-tag>
          <el-tag v-for="(kp, i) in (detail.ai_analysis.knowledge_points || []).slice(0, 5)" :key="i" size="small" effect="plain" style="margin: 2px">
            {{ typeof kp === 'object' ? kp.name : kp }}
          </el-tag>
        </div>
      </template>
    </el-dialog>

    <!-- AI 解析结果弹窗 -->
    <el-dialog v-model="analysisDialogVisible" title="AI 解析结果" width="760px" top="4vh" :close-on-click-modal="false">
      <div v-loading="analysisLoading" class="analysis-result">
        <template v-if="analysisResult">
          <!-- 题型与难度概览卡片 -->
          <div class="overview-card">
            <div class="overview-item">
              <span class="overview-label">题型</span>
              <el-tag :type="qtypeTag(analysisResult.qtype_detected || currentAnalysisRow?.qtype)" size="small">
                {{ qtypeLabel(analysisResult.qtype_detected || currentAnalysisRow?.qtype) }}
              </el-tag>
            </div>
            <div class="overview-divider"></div>
            <div class="overview-item">
              <span class="overview-label">难度</span>
              <el-tag :type="difficultyTag(analysisResult.difficulty)" size="small">
                {{ difficultyLabel(analysisResult.difficulty) }}
              </el-tag>
            </div>
            <div v-if="analysisResult.difficulty_score" class="overview-divider"></div>
            <div v-if="analysisResult.difficulty_score" class="overview-item">
              <span class="overview-label">难度分值</span>
              <span class="overview-value">{{ analysisResult.difficulty_score }} / 10</span>
            </div>
          </div>

          <!-- 知识点关联 -->
          <div v-if="kpItems.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Connection /></el-icon>
              知识点关联
            </div>
            <div class="kp-grid">
              <div v-for="(kp, i) in kpItems" :key="i" class="kp-card">
                <div class="kp-name">{{ kp.name || kp }}</div>
                <span v-if="kp.confidence != null" class="kp-confidence-value">{{ (kp.confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- 推荐标签 -->
          <div v-if="analysisResult.suggested_tags?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><PriceTag /></el-icon>
              推荐标签
            </div>
            <div class="tag-list">
              <el-tag v-for="(tag, i) in analysisResult.suggested_tags" :key="i" type="warning" size="small" effect="plain" style="margin: 2px">
                {{ typeof tag === 'object' ? (tag.name || '-') : tag }}
              </el-tag>
            </div>
          </div>

          <!-- 核心概念 -->
          <div v-if="analysisResult.key_concepts?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Key /></el-icon>
              核心概念
            </div>
            <div class="concept-chips">
              <span v-for="(c, i) in analysisResult.key_concepts" :key="i" class="concept-chip">{{ c }}</span>
            </div>
          </div>

          <!-- 常见错误 -->
          <div v-if="analysisResult.common_mistakes?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px; color: #E24B4A;"><WarningFilled /></el-icon>
              常见错误
              <span class="block-subtitle">{{ analysisResult.common_mistakes.length }} 项</span>
            </div>
            <div class="mistake-list">
              <div v-for="(m, i) in analysisResult.common_mistakes" :key="i" class="mistake-item">
                <div class="mistake-index">{{ i + 1 }}</div>
                <div class="mistake-content">{{ typeof m === 'object' ? (m.description || m.mistake || m.text || JSON.stringify(m)) : m }}</div>
              </div>
            </div>
          </div>

          <!-- 答案解析 -->
          <div v-if="analysisResult.answer_analysis_md || analysisResult.answer_analysis" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Document /></el-icon>
              答案解析
            </div>
            <MarkdownRenderer :content="analysisResult.answer_analysis_md || analysisResult.answer_analysis" />
          </div>

          <!-- 元数据 -->
          <div v-if="analysisResult.model || analysisResult.analyzed_at" class="result-meta">
            <span v-if="analysisResult.model">模型: {{ analysisResult.model }}</span>
            <span v-if="analysisResult.analyzed_at">解析时间: {{ formatTime(analysisResult.analyzed_at) }}</span>
          </div>
        </template>
        <el-empty v-else description="暂无解析结果" />
      </div>
      <template #footer>
        <el-button @click="analysisDialogVisible = false">关闭</el-button>
        <el-button v-if="canAnalyze" type="primary" :loading="analysisLoading" @click="reanalyze">重新解析</el-button>
      </template>
    </el-dialog>

    <!-- 批量解析进度 -->
    <el-dialog v-model="batchDialogVisible" title="批量 AI 解析" width="500px" :close-on-click-modal="false" :close-on-press-escape="!batchLoading">
      <div class="batch-progress">
        <el-progress :percentage="batchPercent" :status="batchStatus" :stroke-width="20" :text-inside="true" />
        <div class="batch-status-text">{{ batchStatusText }}</div>
        <div v-if="batchResult" class="batch-result">
          <el-alert v-if="batchResult.success_count" type="success" :title="`成功解析 ${batchResult.success_count} 题`" :closable="false" style="margin-bottom: 8px" />
          <el-alert v-if="batchResult.fail_count" type="warning" :title="`失败 ${batchResult.fail_count} 题`" :closable="false" style="margin-bottom: 8px" />
        </div>
      </div>
      <template #footer>
        <el-button v-if="!batchLoading" type="primary" @click="batchDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- AI 标签推荐弹窗 -->
    <el-dialog v-model="tagSyncDialogVisible" title="AI 标签推荐与同步" width="620px" :close-on-click-modal="false">
      <div v-loading="tagSyncLoading" class="tag-sync-body">
        <!-- 题目预览 -->
        <div v-if="tagSyncQuestion" class="tag-sync-preview">
          <div class="tag-sync-preview-label">题目</div>
          <div class="tag-sync-preview-text">{{ tagSyncQuestion.title || tagSyncQuestion.content_md?.slice(0, 100) || '-' }}</div>
        </div>

        <!-- 当前已绑定标签 -->
        <div v-if="currentBoundTags.length" class="tag-sync-section">
          <div class="tag-sync-section-title">当前已绑定标签</div>
          <div class="tag-sync-tag-list">
            <el-tag v-for="t in currentBoundTags" :key="t.id" size="small" effect="plain" style="margin: 2px">{{ t.name }}</el-tag>
          </div>
        </div>

        <!-- AI 推荐标签 -->
        <div v-if="syncedTags.length" class="tag-sync-section">
          <div class="tag-sync-section-title">
            AI 推荐（已自动同步到标签管理）
            <el-tag v-if="newSyncedCount" type="success" size="small" style="margin-left: 8px">新增 {{ newSyncedCount }} 个</el-tag>
          </div>
          <div class="tag-sync-tag-list">
            <el-tag
              v-for="(t, i) in syncedTags"
              :key="i"
              :type="t.is_new ? 'success' : 'warning'"
              size="small"
              effect="plain"
              style="margin: 2px"
            >
              {{ t.name }}
              <span v-if="t.is_new" class="tag-sync-badge">新</span>
              <span v-if="t.confidence != null" class="tag-sync-conf">{{ formatConfidence(t.confidence) }}</span>
            </el-tag>
          </div>
        </div>
        <el-alert v-if="!tagSyncLoading && !syncedTags.length" type="info" :closable="false" title="AI 未返回推荐标签" style="margin-bottom: 12px" />

        <!-- 自动绑定选项 -->
        <div class="tag-sync-section">
          <div class="tag-sync-section-title">应用选项</div>
          <el-checkbox v-model="tagAutoBind">自动绑定推荐标签到本题</el-checkbox>
          <div class="tag-sync-hint">勾选后，AI 推荐的标签将自动绑定到当前题目。不存在的标签会自动创建到标签管理中。</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="tagSyncDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="tagSyncApplying" :disabled="!syncedTags.length" @click="applyTagSync">
          {{ tagAutoBind ? '应用标签并绑定' : '仅同步到标签管理' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量 AI 标签进度 -->
    <el-dialog v-model="batchTagDialogVisible" title="批量 AI 标签同步" width="500px" :close-on-click-modal="false" :close-on-press-escape="!batchTagLoading">
      <div class="batch-progress">
        <el-progress :percentage="batchTagPercent" :status="batchTagStatus" :stroke-width="20" :text-inside="true" />
        <div class="batch-status-text">{{ batchTagStatusText }}</div>
        <div v-if="batchTagResult" class="batch-result">
          <el-alert v-if="batchTagResult.total" type="success" :title="`共处理 ${batchTagResult.total} 题，新增标签 ${batchTagResult.new_tag_count || 0} 个`" :closable="false" style="margin-bottom: 8px" />
        </div>
      </div>
      <template #footer>
        <el-button v-if="!batchTagLoading" type="primary" @click="batchTagDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Plus, Upload, MagicStick, Connection, PriceTag, Key, WarningFilled, Document } from '@element-plus/icons-vue'
import { useResource } from '../composables/useResource'
import { useUserStore } from '../stores/user'
import { tagApi, uploadApi, aiApi } from '../api'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'

const user = useUserStore()
const canManage = user.hasPerm('question.manage')
const canAnalyze = user.hasPerm('ai.analyze')

const { list, total, page, pageSize, loading, keyword, filters, load, search, reset, save, remove, bulkRemove } =
  useResource('questions', { examid: '', qtype: '' })

const selection = ref([])
const ids = computed(() => selection.value.map((r) => r._id))
const allTags = ref([])
const mdPreview = ref(false)

// ---- AI 解析状态 ----
const analyzingId = ref('')
const analysisDialogVisible = ref(false)
const analysisLoading = ref(false)
const analysisResult = ref(null)
const currentAnalysisRow = ref(null)
const batchLoading = ref(false)
const batchDialogVisible = ref(false)
const batchPercent = ref(0)
const batchStatusText = ref('')
const batchStatus = ref('')
const batchResult = ref(null)
let batchTimer = null

// ---- AI 标签状态 ----
const tagSyncingId = ref('')
const tagSyncDialogVisible = ref(false)
const tagSyncLoading = ref(false)
const tagSyncApplying = ref(false)
const tagSyncQuestion = ref(null)
const syncedTags = ref([])
const currentBoundTags = ref([])
const tagAutoBind = ref(true)
const newSyncedCount = ref(0)
// 批量 AI 标签
const batchTagLoading = ref(false)
const batchTagDialogVisible = ref(false)
const batchTagPercent = ref(0)
const batchTagStatusText = ref('')
const batchTagStatus = ref('')
const batchTagResult = ref(null)
let batchTagTimer = null

const dialogVisible = ref(false)
const detailVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const singleCorrect = ref(0)
const detail = ref({})
const form = ref(blankForm())

const qtypeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题', multi_part: '一题多问' }
const qtypeTagTypes = { single: 'primary', multiple: 'success', judge: 'warning', fill: 'info', qa: 'danger', multi_part: '' }
function qtypeLabel(q) { return qtypeLabels[q] || q || '-' }
function qtypeTag(q) { return qtypeTagTypes[q] || 'info' }

function blankForm() {
  return {
    _id: '',
    qtype: 'single',
    content_md: '',
    comments: '',
    examid: '',
    tag_ids: [],
    options: [
      { code: 'A', content: '', is_correct: true },
      { code: 'B', content: '', is_correct: false },
      { code: 'C', content: '', is_correct: false },
      { code: 'D', content: '', is_correct: false },
    ],
    judgeAnswer: true,
    blanks: [''],
    answer_md: '',
    ai_grading: { enabled: false, rubric: '', model: '', max_score: 0 },
    sub_questions: [],
  }
}

function onQtypeChange() {
  // 切换题型时保留通用字段，初始化特定字段
  if (form.value.qtype === 'multi_part' && form.value.sub_questions.length < 2) {
    form.value.sub_questions = [
      { qtype: 'single', title: '', options: [{ code: 'A', content: '', is_correct: true }, { code: 'B', content: '', is_correct: false }], _correct: 0 },
      { qtype: 'fill', title: '', _blanks: '' },
    ]
  }
  // 新建题目时自动同步题型标签
  if (!isEdit.value) {
    autoSelectQtypeTag()
  }
}

function addOption() {
  const next = String.fromCharCode(65 + form.value.options.length)
  form.value.options.push({ code: next, content: '', is_correct: false })
}

function addSubQuestion() {
  form.value.sub_questions.push({ qtype: 'single', title: '', options: [{ code: 'A', content: '', is_correct: true }, { code: 'B', content: '', is_correct: false }], _correct: 0 })
}

function insertMd(prefix, suffix, placeholder) {
  const textarea = document.querySelector('.md-editor-wrap textarea')
  if (!textarea) { form.value.content_md += prefix + placeholder + suffix; return }
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selected = form.value.content_md.substring(start, end) || placeholder
  form.value.content_md = form.value.content_md.substring(0, start) + prefix + selected + suffix + form.value.content_md.substring(end)
}

async function onInsertImage(file) {
  try {
    const res = await uploadApi.image(file)
    const url = res?.url
    insertMd(`![${file.name}](${url})`, '', '')
    ElMessage.success('图片已上传并插入')
  } catch (e) {
    ElMessage.error('图片上传失败')
  }
  return false
}

function buildPayload() {
  const f = form.value
  const payload = {
    qtype: f.qtype,
    content_md: f.content_md || f.title,
    examid: f.examid,
    comments: f.comments,
    tag_ids: f.tag_ids,
  }
  if (f._id && !isEdit.value) payload._id = f._id

  if (f.qtype === 'single' || f.qtype === 'multiple') {
    payload.options = f.options.map(o => ({
      code: o.code,
      content: o.content,
      is_correct: f.qtype === 'single' ? false : o.is_correct,
    }))
    if (f.qtype === 'single') {
      payload.options[singleCorrect.value].is_correct = true
    }
  } else if (f.qtype === 'judge') {
    payload.answer = f.judgeAnswer
  } else if (f.qtype === 'fill') {
    payload.blanks = f.blanks.map(b => b.split(',').map(s => s.trim()).filter(Boolean)).filter(b => b.length)
  } else if (f.qtype === 'qa') {
    payload.answer_md = f.answer_md
    if (f.ai_grading.enabled) {
      payload.ai_grading = { ...f.ai_grading }
    }
  } else if (f.qtype === 'multi_part') {
    payload.sub_questions = f.sub_questions.map(sub => {
      const s = { qtype: sub.qtype, title: sub.title }
      if (sub.qtype === 'single' || sub.qtype === 'multiple') {
        s.options = sub.options.map(o => ({
          code: o.code,
          content: o.content,
          is_correct: sub.qtype === 'single' ? false : o.is_correct,
        }))
        if (sub.qtype === 'single' && sub._correct !== undefined) {
          s.options[sub._correct].is_correct = true
        }
      } else if (sub.qtype === 'judge') {
        s.answer = sub._judgeAnswer
      } else if (sub.qtype === 'fill') {
        s.blanks = (sub._blanks || '').split(',').map(x => x.trim()).filter(Boolean).map(x => [x])
      } else if (sub.qtype === 'qa') {
        s.answer_md = sub.answer_md || ''
        s.ai_grading = { enabled: false, rubric: '', model: '', max_score: 0 }
      }
      return s
    })
  }
  return payload
}

function openCreate() {
  isEdit.value = false
  form.value = blankForm()
  singleCorrect.value = 0
  mdPreview.value = false
  // 新建时自动选中当前题型对应的标签
  autoSelectQtypeTag()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.value = {
    _id: row._id,
    qtype: row.qtype || mapTypecode(row.typecode) || 'single',
    content_md: row.content_md || row.title || '',
    comments: row.comments || '',
    examid: row.examid || '',
    tag_ids: (row._tags || []).map(t => t.id),
    options: (row.options || []).map(o => ({ code: o.code, content: o.content, is_correct: String(o.value) === '1' })),
    judgeAnswer: (row.options || []).find(o => String(o.value) === '1')?.code === 'A',
    blanks: (row.blanks || []).map(b => Array.isArray(b) ? b.join(',') : b),
    answer_md: row.answer_md || '',
    ai_grading: row.ai_grading || { enabled: false, rubric: '', model: '', max_score: 0 },
    sub_questions: (row.sub_questions || []).map(sub => ({
      qtype: sub.qtype || mapTypecode(sub.typecode) || 'single',
      title: sub.title || sub.content_md || '',
      options: (sub.options || []).map(o => ({ code: o.code, content: o.content, is_correct: String(o.value) === '1' })),
      _correct: (sub.options || []).findIndex(o => String(o.value) === '1'),
      _judgeAnswer: (sub.options || []).find(o => String(o.value) === '1')?.code === 'A',
      _blanks: (sub.blanks || []).map(b => Array.isArray(b) ? b.join(',') : b).join(','),
      answer_md: sub.answer_md || '',
    })),
  }
  const idx = form.value.options.findIndex(o => o.is_correct)
  singleCorrect.value = idx >= 0 ? idx : 0
  if (!form.value.sub_questions.length && form.value.qtype === 'multi_part') onQtypeChange()
  mdPreview.value = false
  // 若列表数据中缺少标签，从接口加载
  if (!row._tags || !row._tags.length) {
    tagApi.questionTags(row._id).then(res => {
      const tags = Array.isArray(res) ? res : (res?.list || [])
      form.value.tag_ids = tags.map(t => t.id)
    }).catch(() => {})
  }
  dialogVisible.value = true
}

function mapTypecode(code) {
  const map = { '01': 'single', '02': 'multiple', '03': 'judge', '04': 'fill', '05': 'qa', '06': 'multi_part' }
  return map[code] || ''
}

function openDetail(row) {
  detail.value = row
  detailVisible.value = true
  // 加载标签
  if (canManage || user.hasPerm('tag.view')) {
    tagApi.questionTags(row._id).then(res => {
      detail.value = { ...detail.value, _tags: Array.isArray(res) ? res : (res?.list || []) }
    }).catch(() => {})
  }
}

async function submit() {
  const f = form.value
  if (!f.content_md.trim()) { ElMessage.warning('请填写题目正文'); return }
  if (!f.examid.trim()) { ElMessage.warning('请填写科目编号'); return }

  const payload = buildPayload()
  saving.value = true
  try {
    let questionId
    if (isEdit.value) {
      await save(payload, f._id)
      questionId = f._id
    } else {
      const result = await save(payload, null)
      questionId = result?._id || f._id
    }
    // 保存标签绑定（新建和编辑均执行）
    if (questionId) {
      try {
        const resolvedIds = await resolveTagIds(f.tag_ids || [])
        await tagApi.bindQuestionTags(questionId, resolvedIds)
      } catch (e) { /* ignore tag bind error */ }
    }
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function resolveTagIds(tagIds) {
  // 分离已有标签 ID（数字）和新创建的标签名（字符串）
  const existingIds = []
  const newNames = []
  for (const t of tagIds) {
    if (typeof t === 'number') {
      existingIds.push(t)
    } else if (typeof t === 'string' && t.trim()) {
      // allow-create 产生的是字符串名称，检查是否已有同名标签
      const found = allTags.value.find(tag => tag.name === t.trim())
      if (found) {
        existingIds.push(found.id)
      } else {
        newNames.push(t.trim())
      }
    }
  }
  // 创建新标签（归类为知识点）
  for (const name of newNames) {
    try {
      const res = await tagApi.create({ name, category: 'knowledge' })
      if (res?.id) {
        existingIds.push(res.id)
        allTags.value.push(res)
      }
    } catch (e) { /* 同名标签已存在则忽略 */ }
  }
  return existingIds
}

function autoSelectQtypeTag() {
  // 新建题目时自动选中对应题型标签
  const label = qtypeLabels[form.value.qtype]
  const tag = allTags.value.find(t => t.category === 'qtype' && t.name === label)
  if (tag) {
    form.value.tag_ids = [tag.id]
  }
}

async function loadTags() {
  try {
    const res = await tagApi.list({ page: 1, page_size: 200 })
    allTags.value = res?.list || []
  } catch (e) { /* ignore */ }
}

// ---- AI 解析功能 ----

/** 判断题目是否已有 AI 解析（兼容 answer_analysis_md / answer_analysis 两种字段名） */
function hasAnalysis(row) {
  const a = row?.ai_analysis
  return !!(a && (a.knowledge_points?.length || a.answer_analysis_md || a.answer_analysis || a.difficulty))
}

/** 难度标签 */
function difficultyLabel(d) {
  const map = { easy: '简单', medium: '中等', hard: '困难', 1: '简单', 2: '中等', 3: '困难' }
  return map[d] || d || '-'
}
function difficultyTag(d) {
  const map = { easy: 'success', medium: 'warning', hard: 'danger', 1: 'success', 2: 'warning', 3: 'danger' }
  return map[d] || 'info'
}

/** 知识点规整为 [{name, confidence}] */
const kpItems = computed(() => {
  if (!analysisResult.value) return []
  const kps = analysisResult.value.knowledge_points || []
  return kps.map((kp) => {
    if (typeof kp === 'string') return { name: kp, confidence: null }
    if (typeof kp === 'object' && kp) return { name: kp.name || kp.knowledge_point || '-', confidence: kp.confidence ?? null }
    return { name: String(kp), confidence: null }
  })
})

/** 格式化时间 */
function formatTime(ts) {
  if (!ts) return '-'
  try {
    return new Date(ts).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}

/** 单题 AI 解析 */
async function analyzeOne(row) {
  analyzingId.value = row._id
  try {
    const res = await aiApi.analyzeQuestion(row._id)
    if (res) {
      const result = res.analysis || res.ai_analysis || res
      analysisResult.value = result
      currentAnalysisRow.value = row
      row.ai_analysis = result
      analysisDialogVisible.value = true
      ElMessage.success('AI 解析完成')
      await load()
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    analyzingId.value = ''
  }
}

/** 查看已有解析结果 */
function showAnalysisResult(row) {
  currentAnalysisRow.value = row
  analysisResult.value = row.ai_analysis || null
  analysisDialogVisible.value = true
}

/** 重新解析 */
async function reanalyze() {
  if (!currentAnalysisRow.value) return
  analysisLoading.value = true
  try {
    const res = await aiApi.analyzeQuestion(currentAnalysisRow.value._id)
    if (res) {
      const result = res.analysis || res.ai_analysis || res
      analysisResult.value = result
      currentAnalysisRow.value.ai_analysis = result
      ElMessage.success('重新解析完成')
      await load()
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    analysisLoading.value = false
  }
}

/** 批量 AI 解析 */
async function startBatchAnalyze() {
  if (!selection.value.length) {
    ElMessage.warning('请先选择要解析的题目')
    return
  }
  const ids = selection.value.map((r) => r._id)
  batchLoading.value = true
  batchDialogVisible.value = true
  batchPercent.value = 0
  batchStatus.value = ''
  batchStatusText.value = '正在提交批量解析任务...'
  batchResult.value = null
  try {
    const res = await aiApi.analyzeBatch(ids)
    const jobId = res?.job_id || res?.jobId
    if (!jobId) {
      ElMessage.warning('未返回任务 ID')
      batchLoading.value = false
      return
    }
    batchStatusText.value = `任务已提交（ID: ${jobId}），正在解析...`
    pollBatchJob(jobId)
  } catch (e) {
    batchLoading.value = false
    batchStatus.value = 'exception'
    batchStatusText.value = '批量解析提交失败'
  }
}

function pollBatchJob(jobId) {
  let count = 0
  const maxCount = 150 // 5 分钟超时
  batchTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearBatchTimer()
      batchLoading.value = false
      batchStatus.value = 'exception'
      batchStatusText.value = '解析超时，请稍后查看任务列表'
      return
    }
    try {
      const res = await aiApi.jobStatus(jobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      batchPercent.value = Math.min(progress, 99)
      const statusMap = { pending: '排队中...', running: '正在解析...', processing: '正在解析...' }
      batchStatusText.value = res?.message || statusMap[status] || status || '处理中...'
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearBatchTimer()
        batchPercent.value = 100
        batchStatus.value = 'success'
        batchStatusText.value = '批量解析完成'
        batchResult.value = {
          success_count: res?.success_count ?? res?.total ?? selection.value.length,
          fail_count: res?.fail_count ?? 0,
        }
        batchLoading.value = false
        ElMessage.success('批量 AI 解析完成')
        await load()
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearBatchTimer()
        batchStatus.value = 'exception'
        batchStatusText.value = `任务${status === 'failed' ? '失败' : '已取消'}`
        batchResult.value = { success_count: 0, fail_count: res?.fail_count ?? selection.value.length }
        batchLoading.value = false
      }
    } catch (e) {
      // 单次查询失败不中断轮询
    }
  }, 2000)
}

function clearBatchTimer() {
  if (batchTimer) {
    clearInterval(batchTimer)
    batchTimer = null
  }
}

// ---- AI 标签功能 ----

/** 格式化置信度 */
function formatConfidence(v) {
  const num = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(num)) return ''
  return ` ${Math.round(num <= 1 ? num * 100 : num)}%`
}

/** 打开单题 AI 标签推荐弹窗 */
async function openTagSync(row) {
  tagSyncQuestion.value = row
  tagSyncDialogVisible.value = true
  tagSyncLoading.value = true
  tagSyncingId.value = row._id
  syncedTags.value = []
  currentBoundTags.value = []
  tagAutoBind.value = true
  newSyncedCount.value = 0

  // 加载当前已绑定标签
  try {
    const tagsRes = await tagApi.questionTags(row._id)
    currentBoundTags.value = Array.isArray(tagsRes) ? tagsRes : (tagsRes?.list || [])
  } catch (e) { /* ignore */ }

  // 调用 AI 标签推荐 + 自动同步
  try {
    const res = await aiApi.autoTagSync(row._id, { auto_bind: false })
    syncedTags.value = res?.synced_tags || []
    newSyncedCount.value = (res?.synced_tags || []).filter(t => t.is_new).length
  } catch (e) {
    // handled by interceptor
  } finally {
    tagSyncLoading.value = false
    tagSyncingId.value = ''
  }
}

/** 应用 AI 标签同步（绑定到题目） */
async function applyTagSync() {
  if (!tagSyncQuestion.value || !syncedTags.value.length) return
  tagSyncApplying.value = true
  try {
    const tagNames = syncedTags.value.map(t => t.name)
    if (tagAutoBind.value) {
      // 自动绑定：调用 apply 接口
      await aiApi.applyQuestionTags(tagSyncQuestion.value._id, { tag_names: tagNames })
      ElMessage.success(`已应用 ${tagNames.length} 个标签并绑定到题目`)
    } else {
      ElMessage.success(`已同步 ${syncedTags.value.filter(t => t.is_new).length} 个新标签到标签管理`)
    }
    tagSyncDialogVisible.value = false
    // 刷新标签列表和题目列表
    await loadTags()
    await load()
  } catch (e) {
    // handled by interceptor
  } finally {
    tagSyncApplying.value = false
  }
}

/** 批量 AI 标签同步 */
async function startBatchTagSync() {
  if (!selection.value.length) {
    ElMessage.warning('请先选择要推荐标签的题目')
    return
  }
  const ids = selection.value.map((r) => r._id)
  batchTagLoading.value = true
  batchTagDialogVisible.value = true
  batchTagPercent.value = 0
  batchTagStatus.value = ''
  batchTagStatusText.value = '正在提交批量 AI 标签同步任务...'
  batchTagResult.value = null
  try {
    const res = await aiApi.autoTagSyncBatch(ids, true)
    const jobId = res?.job_id || res?.jobId
    if (!jobId) {
      ElMessage.warning('未返回任务 ID')
      batchTagLoading.value = false
      return
    }
    batchTagStatusText.value = `任务已提交（ID: ${jobId}），正在同步...`
    pollBatchTagJob(jobId)
  } catch (e) {
    batchTagLoading.value = false
    batchTagStatus.value = 'exception'
    batchTagStatusText.value = '批量标签同步提交失败'
  }
}

function pollBatchTagJob(jobId) {
  let count = 0
  const maxCount = 150
  batchTagTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearBatchTagTimer()
      batchTagLoading.value = false
      batchTagStatus.value = 'exception'
      batchTagStatusText.value = '同步超时，请稍后查看任务列表'
      return
    }
    try {
      const res = await aiApi.jobStatus(jobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      batchTagPercent.value = Math.min(progress, 99)
      const statusMap = { pending: '排队中...', running: '正在同步标签...', processing: '正在同步标签...' }
      batchTagStatusText.value = res?.message || statusMap[status] || status || '处理中...'
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearBatchTagTimer()
        batchTagPercent.value = 100
        batchTagStatus.value = 'success'
        batchTagStatusText.value = '批量 AI 标签同步完成'
        batchTagResult.value = {
          total: res?.total ?? res?.result?.total ?? selection.value.length,
          new_tag_count: res?.result?.new_tag_count ?? res?.new_tag_count ?? 0,
        }
        batchTagLoading.value = false
        ElMessage.success('批量 AI 标签同步完成')
        await loadTags()
        await load()
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearBatchTagTimer()
        batchTagStatus.value = 'exception'
        batchTagStatusText.value = `任务${status === 'failed' ? '失败' : '已取消'}`
        batchTagLoading.value = false
      }
    } catch (e) {
      // 单次查询失败不中断轮询
    }
  }, 2000)
}

function clearBatchTagTimer() {
  if (batchTagTimer) {
    clearInterval(batchTagTimer)
    batchTagTimer = null
  }
}

onMounted(() => {
  load()
  loadTags()
})

onBeforeUnmount(() => {
  clearBatchTimer()
  clearBatchTagTimer()
})
</script>

<style scoped>
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
.options-editor { width: 100%; }
.option-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.opt-code { width: 60px; flex: none; }
.blanks-editor { width: 100%; }
.blank-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.blank-label { white-space: nowrap; font-size: 13px; color: #606266; min-width: 60px; }
.subs-editor { width: 100%; }
.sub-block { border: 1px solid #e4e7ed; border-radius: 6px; padding: 12px; margin-bottom: 12px; background: #fafafa; }
.sub-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.sub-title { font-weight: 600; font-size: 14px; }
.block-title { font-size: 14px; font-weight: 600; }
.md-editor-wrap { width: 100%; }
.md-toolbar { display: flex; gap: 4px; margin-bottom: 6px; padding: 4px 8px; background: #f4f6fa; border-radius: 4px; }
.md-preview-area { border: 1px solid #dcdfe6; border-radius: 4px; padding: 12px; min-height: 100px; background: #fff; }
.hint { margin-left: 8px; font-size: 12px; color: #909399; }
.muted { color: #c0c4cc; }
.sub-detail { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #e4e7ed; }
.sub-detail-title { font-weight: 600; font-size: 13px; margin-bottom: 4px; color: #303133; }

/* ---- AI 解析相关样式 ---- */
.ai-summary { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; padding: 8px 0; }
.analysis-result { max-height: 65vh; overflow-y: auto; }
.overview-card { display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 8px; margin-bottom: 4px; }
.overview-item { display: flex; align-items: center; gap: 8px; }
.overview-label { font-size: 13px; color: #909399; white-space: nowrap; }
.overview-value { font-size: 14px; font-weight: 500; color: #303133; }
.overview-divider { width: 1px; height: 20px; background: #dcdfe6; }
.result-section { margin-top: 16px; }
.block-subtitle { font-size: 12px; font-weight: 400; color: #909399; margin-left: 8px; }
.kp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.kp-card { padding: 10px 14px; background: #f0f5ff; border: 1px solid #d6e4ff; border-radius: 8px; display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.kp-name { font-size: 13px; font-weight: 500; color: #303133; flex: 1; min-width: 0; word-break: break-word; line-height: 1.6; }
.kp-confidence-value { font-size: 11px; font-weight: 400; color: #c0c4cc; flex-shrink: 0; white-space: nowrap; line-height: 1.6; }
.tag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.concept-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.concept-chip { display: inline-block; padding: 4px 12px; font-size: 13px; color: #606266; background: #f4f4f5; border-radius: 12px; line-height: 1.6; }
.mistake-list { display: flex; flex-direction: column; gap: 8px; }
.mistake-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; background: #fef0f0; border-left: 3px solid #f56c6c; border-radius: 0 6px 6px 0; }
.mistake-index { flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; background: #f56c6c; color: #fff; font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; line-height: 1; }
.mistake-content { font-size: 13px; color: #606266; line-height: 1.7; flex: 1; }
.result-meta { margin-top: 20px; padding-top: 12px; border-top: 1px solid #ebeef5; display: flex; gap: 16px; font-size: 12px; color: #c0c4cc; }
.batch-progress { text-align: center; padding: 20px 0; }
.batch-status-text { margin-top: 12px; font-size: 14px; color: #606266; }
.batch-result { margin-top: 16px; text-align: left; }

/* ---- AI 标签弹窗 ---- */
.tag-sync-body { min-height: 120px; }
.tag-sync-preview { background: #f4f6fa; border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; }
.tag-sync-preview-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.tag-sync-preview-text { font-size: 14px; color: #303133; line-height: 1.6; }
.tag-sync-section { margin-top: 14px; }
.tag-sync-section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.tag-sync-tag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-sync-badge { font-size: 10px; background: #67c23a; color: #fff; border-radius: 3px; padding: 0 4px; margin-left: 2px; }
.tag-sync-conf { color: #e6a23c; font-size: 11px; }
.tag-sync-hint { margin-top: 6px; font-size: 12px; color: #909399; }
</style>
