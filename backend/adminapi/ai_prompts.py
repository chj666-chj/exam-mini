"""AI Prompt 构建器 —— 为每个 AI 功能生成结构化的 system prompt 和 user prompt。

所有 prompt 要求 LLM 返回结构化 JSON 格式，由 parse_json_response() 统一解析。
兼容 ```json 代码块包裹和纯 JSON 两种返回形式。
"""
import json
import re


class PromptBuilder:
    """AI 功能的 prompt 构建器。

    每个功能对应一个 system prompt（定义返回格式约束）和
    一个 user prompt（注入具体业务数据）。
    """

    # ---- 各功能的 system prompt ----
    _SYSTEM_PROMPTS = {
        'question_analyze': (
            '你是一个专业的考试题目分析专家。请分析给定的考试题目，返回结构化的 JSON 结果。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "knowledge_points": [{"name": "知识点名称", "confidence": 0.0到1.0的浮点数}],\n'
            '  "difficulty": "easy" 或 "medium" 或 "hard",\n'
            '  "difficulty_score": 1到10的整数,\n'
            '  "qtype_detected": "single" 或 "multiple" 或 "judge" 或 "fill" 或 "qa" 或 "multi_part",\n'
            '  "answer_analysis_md": "答案解析（Markdown 格式）",\n'
            '  "suggested_tags": [{"category": "knowledge", "name": "标签名"}],\n'
            '  "key_concepts": ["核心概念1", "核心概念2"],\n'
            '  "common_mistakes": ["常见错误1", "常见错误2"]\n'
            '}'
        ),
        'exam_compose': (
            '你是一个专业的智能组卷专家。请根据候选题池和组卷要求，从候选题目中精选合适的题目组成一份试卷。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "question_ids": ["选中的题目ID列表"],\n'
            '  "total_score": 总分数字,\n'
            '  "distribution": {\n'
            '    "by_qtype": {"single": 数量, "multiple": 数量},\n'
            '    "by_difficulty": {"easy": 数量, "medium": 数量, "hard": 数量}\n'
            '  },\n'
            '  "composition_notes": "组卷说明（可选）"\n'
            '}'
        ),
        'ai_grade': (
            '你是一个专业的考试判卷专家。请根据题目内容、参考答案和评分标准，对考生的作答进行评分。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "score": 分数数字,\n'
            '  "feedback_md": "评分反馈（Markdown 格式，包括得分点和扣分点）",\n'
            '  "confidence": 0.0到1.0的浮点数\n'
            '}'
        ),
        'exam_analyze': (
            '你是一个专业的考试数据分析专家。请根据试卷的答题统计数据，生成深入的分析报告。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "overall_analysis": "总体分析（Markdown 格式，包含考试整体表现概述）",\n'
            '  "difficulty_assessment": {\n'
            '    "too_easy": [{"question_id": "题目ID", "accuracy": 正确率, "reason": "原因"}],\n'
            '    "too_hard": [{"question_id": "题目ID", "accuracy": 正确率, "reason": "原因"}]\n'
            '  },\n'
            '  "weak_points": [{"question_id": "题目ID", "accuracy": 正确率, "knowledge_point": "知识点", "suggestion": "改进建议"}],\n'
            '  "strong_points": [{"question_id": "题目ID", "accuracy": 正确率, "knowledge_point": "知识点"}],\n'
            '  "score_distribution_analysis": "得分分布分析（文字描述）",\n'
            '  "recommendations": ["改进建议1", "改进建议2", "改进建议3"],\n'
            '  "question_quality": {\n'
            '    "good_questions": ["区分度好的题目ID列表"],\n'
            '    "problematic_questions": ["存在问题的题目ID列表"]\n'
            '  }\n'
            '}'
        ),
        'learning_profile': (
            '你是一个专业的学习分析专家。请根据用户的答题历史统计数据，生成个性化的学习画像分析报告。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "learning_style": "学习风格分析（文字描述）",\n'
            '  "strengths": [{"subject": "科目", "accuracy": 正确率, "detail": "优势说明"}],\n'
            '  "weaknesses": [{"subject": "科目", "accuracy": 正确率, "detail": "薄弱说明", "suggestion": "改进建议"}],\n'
            '  "recommended_focus": ["建议重点关注的知识点1", "建议重点关注的知识点2"],\n'
            '  "trend_analysis": "近期答题趋势分析（文字描述）",\n'
            '  "study_plan": "个性化学习计划建议（Markdown 格式）",\n'
            '  "common_mistake_patterns": ["常见错误模式1", "常见错误模式2"]\n'
            '}'
        ),
        'review_recommend': (
            '你是一个专业的复习规划专家。请根据艾宾浩斯遗忘曲线算法生成的基础复习清单和用户学习画像，'
            '优化复习优先级并生成推荐理由。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "review_items": [\n'
            '    {\n'
            '      "note_id": "错题ID",\n'
            '      "question_id": "题目ID",\n'
            '      "priority": 1到10的整数,\n'
            '      "reason": "推荐复习理由",\n'
            '      "review_type": "new_review 或 reinforce 或 final_review",\n'
            '      "estimated_minutes": 预计复习分钟数\n'
            '    }\n'
            '  ],\n'
            '  "daily_summary": "今日复习建议摘要",\n'
            '  "estimated_total_minutes": 预计总复习时间,\n'
            '  "tips": ["复习技巧提示1", "复习技巧提示2"]\n'
            '}'
        ),
        'article_enhance': (
            '你是一个专业的备考内容创作助手。根据用户的需求和指定的操作类型，提供高质量的内容创作支持。\n'
            '操作类型说明：\n'
            '- topic（选题推荐）：返回严格 JSON {"topics": ["选题1", "选题2", "选题3", "选题4", "选题5"]}\n'
            '- outline（大纲生成）：返回 Markdown 格式的结构化大纲\n'
            '- generate（正文生成）：返回 Markdown 格式的完整备考文章\n'
            '- title（标题优化）：返回严格 JSON {"titles": ["标题1", "标题2", "标题3"]}\n'
            '- summary（摘要生成）：返回严格 JSON {"summary": "100到200字的摘要内容"}\n'
            '- image_suggest（配图建议）：返回严格 JSON {"keywords": ["关键词1", "关键词2", "关键词3"]}\n'
            '对于 JSON 格式的操作，返回严格 JSON，不要包含任何其他文字。\n'
            '对于 Markdown 格式的操作，直接返回 Markdown 内容。'
        ),
        # ---- P2 级功能 ----
        'kb_qa': (
            '你是一个专业的知识库问答助手。请严格依据提供的知识库片段回答用户问题。\n'
            '回答要求：\n'
            '- 只能使用提供的知识库内容作答，不得编造事实；\n'
            '- 若知识库内容不足以回答，明确说明「知识库中暂无相关内容」并给出通用的学习建议；\n'
            '- 使用清晰、友好的中文，采用 Markdown 格式组织答案（可使用标题、列表、加粗）。\n'
            '直接返回 Markdown 格式的答案正文，不要包含 JSON 包裹。'
        ),
        'auto_tag': (
            '你是一个专业的题目标签分类专家。请为给定题目推荐合适的标签。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "suggested_tags": [\n'
            '    {"name": "标签名", "category": "knowledge 或 difficulty 或 qtype", "confidence": 0.0到1.0的浮点数}\n'
            '  ]\n'
            '}\n'
            '推荐 3-6 个标签，优先覆盖知识点（knowledge）、难度（difficulty）与题型（qtype）。'
        ),
        'excel_validate': (
            '你是一个专业的题库数据质检专家。请校验批量导入的题目数据的质量。\n'
            '校验维度：字段完整性、格式规范性（如选项、答案、解析）、逻辑正确性（如答案是否与题干匹配）。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "errors": [{"row": 行号, "field": "字段名", "level": "error 或 warning", "message": "问题描述", "suggestion": "修改建议"}],\n'
            '  "corrections": [{"row": 行号, "field": "字段名", "original": "原始值", "corrected": "修正后的值"}],\n'
            '  "column_mapping": {"源列名": "目标字段名"}\n'
            '}'
        ),
        'learning_report': (
            '你是一个专业的学情分析专家。请根据用户的学习统计数据，生成个性化的学习报告。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "content_md": "Markdown 格式的报告正文（包含成绩概览、趋势分析、优势与不足、学习建议）",\n'
            '  "summary": "一句话总结",\n'
            '  "highlights": ["亮点1", "亮点2"],\n'
            '  "suggestions": ["改进建议1", "改进建议2"]\n'
            '}'
        ),
        'cs_chat': (
            '你是一个专业、友好的在线客服助手，服务于一个在线考试/刷题学习平台。\n'
            '回答要求：\n'
            '- 使用友好、口语化的中文，回答简洁明确；\n'
            '- 优先依据提供的平台规则和知识库内容作答；如无依据，给出合理的通用回答；\n'
            '- 不要编造平台没有的功能。\n'
            '返回格式要求（严格 JSON，不要包含任何其他文字）：\n'
            '{\n'
            '  "reply": "回复内容（可用 Markdown）",\n'
            '  "suggestions": ["推荐追问1", "推荐追问2", "推荐追问3"]\n'
            '}'
        ),
    }

    @classmethod
    def build_system_prompt(cls, func_name):
        """返回指定功能的 system prompt。

        若 func_name 未注册，返回通用 prompt。
        """
        return cls._SYSTEM_PROMPTS.get(
            func_name,
            '你是一个专业的 AI 助手，请返回结构化的 JSON 结果。'
        )

    @classmethod
    def build_question_analyze_prompt(cls, content_md, qtype, options):
        """题目解析 user prompt。

        Args:
            content_md: 题目正文 Markdown
            qtype: 题型代码（single/multiple/judge/fill/qa/multi_part）
            options: 选项列表（[{code, content, value}]）
        """
        parts = ['请分析以下考试题目：\n']
        parts.append('题型：%s' % (qtype or '未知'))
        parts.append('\n题目内容：\n%s' % (content_md or ''))
        if options and isinstance(options, list):
            opts_lines = []
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                code = opt.get('code', '')
                content = opt.get('content', '')
                opts_lines.append('%s. %s' % (code, content))
            if opts_lines:
                parts.append('\n选项：\n%s' % '\n'.join(opts_lines))
        parts.append('\n请返回 JSON 格式的分析结果。')
        return '\n'.join(parts)

    @classmethod
    def build_exam_compose_prompt(cls, candidate_pool, config):
        """组卷 user prompt。

        Args:
            candidate_pool: 候选题目列表 [{id, qtype, difficulty, knowledge_summary, score}]
            config: 组卷配置 {qtype_dist, difficulty_dist, total_score, count, knowledge_points, locked_questions}

        Note:
            候选题池列表会被限制在 AI_COMPOSE_PROMPT_MAX_LINES 行以内，
            避免 prompt 过大导致 LLM 超时。超出的题目不发送给 LLM。
        """
        from django.conf import settings

        parts = ['请根据以下要求智能组卷：\n']
        parts.append('组卷要求：')
        parts.append('- 题型分布：%s' % json.dumps(config.get('qtype_dist', {}), ensure_ascii=False))
        parts.append('- 难度分布：%s' % json.dumps(config.get('difficulty_dist', {}), ensure_ascii=False))
        total_count = config.get('count', 0)
        total_score = config.get('total_score', 0)
        parts.append('- 题目总数：%d' % total_count)
        parts.append('- 总分：%d' % total_score)
        knowledge_points = config.get('knowledge_points', [])
        if knowledge_points:
            parts.append('- 知识点覆盖：%s' % '、'.join(str(kp) for kp in knowledge_points))
        locked = config.get('locked_questions', [])
        if locked:
            parts.append('- 必选题目ID：%s' % '、'.join(str(qid) for qid in locked))

        # 限制候选题池行数，防止 prompt 过大导致 LLM 超时
        max_lines = getattr(settings, 'AI_COMPOSE_PROMPT_MAX_LINES', 200)
        pool_to_send = candidate_pool[:max_lines]
        truncated = len(candidate_pool) - len(pool_to_send)

        parts.append('\n候选题池（题号 | 题型 | 难度 | 知识点摘要 | 分值）：')
        for q in pool_to_send:
            parts.append('%s | %s | %s | %s | %s' % (
                q.get('id', ''),
                q.get('qtype', ''),
                q.get('difficulty', ''),
                q.get('knowledge_summary', ''),
                q.get('score', 0),
            ))
        if truncated > 0:
            parts.append('（注：候选题池共有 %d 题，已截取前 %d 题展示）' % (
                len(candidate_pool), len(pool_to_send)))

        parts.append('\n请从候选题池中精选题目，确保满足题型分布、难度分布和总分要求。')
        parts.append('返回 JSON 格式结果，question_ids 中的 ID 必须来自候选题池。')
        return '\n'.join(parts)

    @classmethod
    def build_grading_prompt(cls, question, answer_text, rubric, max_score):
        """判卷 user prompt。

        Args:
            question: 题目数据 dict（含 content_md, qtype, options, answer_md 等）
            answer_text: 考生作答文本
            rubric: 评分标准（可为空）
            max_score: 满分
        """
        parts = ['请对以下考生作答进行评分：\n']
        content_md = ''
        if isinstance(question, dict):
            content_md = question.get('content_md') or question.get('title', '')
        parts.append('题目内容：\n%s' % (content_md or ''))
        qtype = question.get('qtype', '') if isinstance(question, dict) else ''
        parts.append('\n题型：%s' % qtype)
        if isinstance(question, dict) and question.get('options'):
            opts_lines = []
            for opt in question['options']:
                if not isinstance(opt, dict):
                    continue
                code = opt.get('code', '')
                content = opt.get('content', '')
                opts_lines.append('%s. %s' % (code, content))
            if opts_lines:
                parts.append('\n选项：\n%s' % '\n'.join(opts_lines))
        ref_answer = ''
        if isinstance(question, dict):
            ref_answer = question.get('answer_md') or question.get('answer', '')
        if ref_answer:
            parts.append('\n参考答案：%s' % ref_answer)
        parts.append('\n考生作答：\n%s' % (answer_text or ''))
        if rubric:
            parts.append('\n评分标准：\n%s' % rubric)
        parts.append('\n满分：%s' % max_score)
        parts.append('\n请返回 JSON 格式的评分结果，score 为 0 到 %s 之间的数字。' % max_score)
        return '\n'.join(parts)

    @classmethod
    def build_exam_analyze_prompt(cls, stats_summary):
        """试卷分析 user prompt。

        Args:
            stats_summary: 试卷统计摘要 dict，包含：
                - exam_name: 考试名称
                - total_records: 总答题记录数
                - question_stats: 各题统计 [{question_id, accuracy, avg_time, difficulty}]
                - score_distribution: 得分分布 {high, medium, low}
                - avg_score: 平均得分
                - avg_accuracy: 平均正确率
        """
        parts = ['请根据以下试卷答题统计数据，生成深入的分析报告：\n']
        parts.append('考试名称：%s' % stats_summary.get('exam_name', '未知'))
        parts.append('总答题记录数：%d' % stats_summary.get('total_records', 0))
        parts.append('平均得分：%s' % stats_summary.get('avg_score', 0))
        parts.append('平均正确率：%s' % stats_summary.get('avg_accuracy', 0))

        score_dist = stats_summary.get('score_distribution', {})
        parts.append('\n得分分布：')
        parts.append('- 高分段（>=80%%）：%d 人' % score_dist.get('high', 0))
        parts.append('- 中分段（50%%-80%%）：%d 人' % score_dist.get('medium', 0))
        parts.append('- 低分段（<50%%）：%d 人' % score_dist.get('low', 0))

        question_stats = stats_summary.get('question_stats', [])
        if question_stats:
            parts.append('\n各题统计（题号 | 正确率 | 平均用时(秒) | 难度）：')
            for qs in question_stats:
                parts.append('%s | %s%% | %s | %s' % (
                    qs.get('question_id', ''),
                    qs.get('accuracy', 0),
                    qs.get('avg_time', 0),
                    qs.get('difficulty', '未知'),
                ))

        parts.append('\n请根据以上统计数据，分析试卷的整体质量、各题难度是否合理、'
                      '学生的薄弱知识点，并给出改进建议。')
        parts.append('返回 JSON 格式的分析报告。')
        return '\n'.join(parts)

    @classmethod
    def build_learning_profile_prompt(cls, history_summary):
        """答题分析（学习画像）user prompt。

        Args:
            history_summary: 用户答题历史统计摘要 dict，包含：
                - total_count: 总答题数
                - subject_stats: 各科目统计 [{subject, total, correct, accuracy}]
                - recent_trend: 近期正确率序列 [0.8, 0.7, 0.9, ...]
                - common_error_types: 常错题型列表
                - qtype_stats: 各题型正确率 [{qtype, accuracy}]
        """
        parts = ['请根据以下用户的答题历史统计数据，生成个性化的学习画像分析报告：\n']
        parts.append('总答题数：%d' % history_summary.get('total_count', 0))

        subject_stats = history_summary.get('subject_stats', [])
        if subject_stats:
            parts.append('\n各科目答题统计（科目 | 答题数 | 正确数 | 正确率）：')
            for ss in subject_stats:
                parts.append('%s | %d | %d | %s%%' % (
                    ss.get('subject', '未知'),
                    ss.get('total', 0),
                    ss.get('correct', 0),
                    ss.get('accuracy', 0),
                ))

        recent_trend = history_summary.get('recent_trend', [])
        if recent_trend:
            trend_str = ' -> '.join('%.0f%%' % (t * 100) for t in recent_trend)
            parts.append('\n近期正确率趋势（最近 %d 次答题）：%s' % (len(recent_trend), trend_str))

        common_error_types = history_summary.get('common_error_types', [])
        if common_error_types:
            parts.append('\n常错题型：%s' % '、'.join(common_error_types))

        qtype_stats = history_summary.get('qtype_stats', [])
        if qtype_stats:
            parts.append('\n各题型正确率：')
            for qts in qtype_stats:
                parts.append('- %s：%s%%' % (qts.get('qtype', ''), qts.get('accuracy', 0)))

        parts.append('\n请根据以上统计数据，分析用户的学习风格、优势和薄弱点，'
                      '并给出个性化的学习计划建议。')
        parts.append('返回 JSON 格式的学习画像报告。')
        return '\n'.join(parts)

    @classmethod
    def build_review_prompt(cls, base_plan, learning_profile):
        """复习推荐 user prompt。

        Args:
            base_plan: 艾宾浩斯算法生成的基础复习清单 dict，包含：
                - review_items: [{note_id, question_id, days_since_review, next_interval, risk_score, review_count}]
                - total_items: 总复习项数
            learning_profile: 用户学习画像 dict（可为空），包含：
                - weaknesses: 薄弱点列表
                - strengths: 优势列表
                - recommended_focus: 建议关注点
        """
        parts = ['请根据以下艾宾浩斯遗忘曲线算法生成的基础复习清单，优化复习优先级并生成推荐理由：\n']

        review_items = base_plan.get('review_items', [])
        parts.append('待复习题目数：%d' % len(review_items))

        if review_items:
            parts.append('\n基础复习清单（错题ID | 题目ID | 距上次复习天数 | 下次复习间隔 | 遗忘风险分 | 已复习次数）：')
            for item in review_items:
                parts.append('%s | %s | %d天 | %d天 | %.2f | %d次' % (
                    item.get('note_id', ''),
                    item.get('question_id', ''),
                    item.get('days_since_review', 0),
                    item.get('next_interval', 0),
                    item.get('risk_score', 0),
                    item.get('review_count', 0),
                ))

        if learning_profile and isinstance(learning_profile, dict):
            weaknesses = learning_profile.get('weaknesses', [])
            if weaknesses:
                parts.append('\n用户薄弱知识点：')
                for w in weaknesses:
                    if isinstance(w, dict):
                        parts.append('- %s：%s' % (w.get('subject', ''), w.get('detail', '')))
                    else:
                        parts.append('- %s' % w)

            recommended_focus = learning_profile.get('recommended_focus', [])
            if recommended_focus:
                parts.append('\n建议重点关注：%s' % '、'.join(str(rf) for rf in recommended_focus))

        parts.append('\n请根据遗忘曲线风险分和用户学习画像，为每个复习项分配 1-10 的优先级，'
                      '并生成推荐理由。')
        parts.append('返回 JSON 格式的优化后的复习推荐结果。')
        return '\n'.join(parts)

    @classmethod
    def build_article_enhance_prompt(cls, action, prompt, context):
        """文章增强 user prompt。

        Args:
            action: 操作类型（topic/outline/generate/title/summary/image_suggest）
            prompt: 用户输入的主题或正文
            context: 补充说明上下文
        """
        action_descriptions = {
            'topic': '请根据以下信息推荐 5 个备考文章选题',
            'outline': '请根据以下主题生成一份结构化的备考文章大纲',
            'generate': '请根据以下信息撰写一篇结构清晰、内容充实的 Markdown 格式备考文章',
            'title': '请根据以下文章正文，提供 3-5 个优质的标题候选',
            'summary': '请根据以下文章正文，自动提取 100-200 字的摘要',
            'image_suggest': '请根据以下文章正文，推荐 3 个配图关键词',
        }

        desc = action_descriptions.get(action, action_descriptions['generate'])
        parts = ['%s：\n' % desc]

        if action in ('topic', 'outline', 'generate'):
            parts.append('主题：%s' % prompt)
            if context:
                parts.append('\n补充说明：%s' % context)
        elif action in ('title', 'summary', 'image_suggest'):
            parts.append('文章正文：\n%s' % prompt)
            if context:
                parts.append('\n补充说明：%s' % context)

        # 添加格式提示
        if action == 'topic':
            parts.append('\n请返回 JSON 格式：{"topics": ["选题1", "选题2", "选题3", "选题4", "选题5"]}')
        elif action == 'outline':
            parts.append('\n请返回 Markdown 格式的结构化大纲，包含标题、章节和小节。')
        elif action == 'generate':
            parts.append('\n请返回 Markdown 格式的完整文章。')
        elif action == 'title':
            parts.append('\n请返回 JSON 格式：{"titles": ["标题1", "标题2", "标题3"]}')
        elif action == 'summary':
            parts.append('\n请返回 JSON 格式：{"summary": "摘要内容"}')
        elif action == 'image_suggest':
            parts.append('\n请返回 JSON 格式：{"keywords": ["关键词1", "关键词2", "关键词3"]}')

        return '\n'.join(parts)

    # ---- P2 级功能的 user prompt ----

    @classmethod
    def build_kb_qa_prompt(cls, question, contexts):
        """知识库问答 user prompt。

        Args:
            question: 用户问题
            contexts: 检索到的知识片段列表 [{'title', 'text'}]
        """
        parts = ['请基于以下知识库内容回答用户问题。\n']
        parts.append('用户问题：%s\n' % (question or ''))
        if contexts:
            parts.append('知识库参考内容：')
            for i, ctx in enumerate(contexts):
                if not isinstance(ctx, dict):
                    continue
                title = ctx.get('title', '')
                text = ctx.get('text', '')
                parts.append('【片段 %d】%s\n%s' % (i + 1, title, text))
        else:
            parts.append('（知识库中没有检索到相关内容）')
        parts.append('\n请严格依据上述材料作答；若材料不足以回答，'
                     '请说明知识库暂无相关内容，并给出通用建议。')
        parts.append('请直接返回 Markdown 格式的答案正文。')
        return '\n'.join(parts)

    @classmethod
    def build_auto_tag_prompt(cls, question_title, content_md, qtype):
        """题目自动标签 user prompt。

        Args:
            question_title: 题目标题（可空）
            content_md: 题目正文 Markdown
            qtype: 题型代码
        """
        parts = ['请为以下题目推荐合适的标签：\n']
        parts.append('题型：%s' % (qtype or '未知'))
        parts.append('标题：%s' % (question_title or ''))
        parts.append('题目内容：\n%s' % (content_md or ''))
        parts.append('\n请推荐 3-6 个标签，category 取值 knowledge / difficulty / qtype。')
        parts.append('返回 JSON 格式：'
                     '{"suggested_tags": [{"name": "标签名", "category": "knowledge", "confidence": 0.9}]}')
        return '\n'.join(parts)

    @classmethod
    def build_excel_validate_prompt(cls, rows, qtype):
        """Excel 智能校验 user prompt。

        Args:
            rows: 待校验行列表 list[dict]（表头映射后的字典）
            qtype: 题型代码（single/multiple/judge/fill/qa）
        """
        parts = ['请校验以下导入题目的数据质量（题型：%s）：\n' % (qtype or 'single')]
        for i, row in enumerate(rows or []):
            if isinstance(row, dict):
                pairs = '; '.join('%s=%s' % (k, v) for k, v in row.items())
            else:
                pairs = str(row)
            parts.append('第 %d 行: %s' % (i + 1, pairs))
        parts.append('\n请检查每题的数据完整性、格式规范性与逻辑正确性。')
        parts.append(
            '返回 JSON 格式：'
            '{"errors": [{"row": 行号, "field": "字段", "level": "error|warning", '
            '"message": "问题", "suggestion": "建议"}], '
            '"corrections": [{"row": 行号, "field": "字段", "original": "原值", "corrected": "修正值"}], '
            '"column_mapping": {"源列": "目标字段"}}'
        )
        return '\n'.join(parts)

    @classmethod
    def build_learning_report_prompt(cls, stats, report_type):
        """学习报告 user prompt。

        Args:
            stats: 聚合统计 dict，包含 record_count, avg_accuracy,
                accuracy_trend, subject_stats, wrong_count, study_days
            report_type: weekly / monthly / pre_exam
        """
        type_label = {'weekly': '周报', 'monthly': '月报',
                      'pre_exam': '考前报告'}.get(report_type, '学习报告')
        parts = ['请根据以下学习统计数据，生成一份%s：\n' % type_label]
        parts.append('答题记录数：%d' % stats.get('record_count', 0))
        parts.append('平均正确率：%s%%' % stats.get('avg_accuracy', 0))
        parts.append('错题数：%d' % stats.get('wrong_count', 0))
        parts.append('学习天数：%d' % stats.get('study_days', 0))

        trend = stats.get('accuracy_trend', [])
        if trend:
            parts.append('\n正确率趋势：')
            for t in trend:
                if isinstance(t, dict):
                    parts.append('- %s：%s%%' % (t.get('date', ''), t.get('accuracy', 0)))

        subject_stats = stats.get('subject_stats', {})
        if subject_stats:
            parts.append('\n各科目表现：')
            for subj, counts in subject_stats.items():
                if isinstance(counts, dict):
                    parts.append('- %s：正确率 %s%%（共 %d 题）' % (
                        subj, counts.get('accuracy', 0), counts.get('total', 0)))

        parts.append('\n请生成包含成绩概览、趋势分析、优势与不足、学习建议的学习报告。')
        parts.append(
            '返回 JSON 格式：{"content_md": "Markdown 正文", "summary": "一句话总结", '
            '"highlights": ["亮点1", "亮点2"], "suggestions": ["建议1", "建议2"]}'
        )
        return '\n'.join(parts)

    @classmethod
    def build_cs_chat_prompt(cls, message, faq_text, kb_context):
        """智能客服 user prompt。

        Args:
            message: 用户消息
            faq_text: 平台规则 / 常见问题文本
            kb_context: 知识库 top3 摘要文本
        """
        parts = ['用户问题：%s' % (message or '')]
        if kb_context:
            parts.append('\n可参考的知识库内容：\n%s' % kb_context)
        if faq_text:
            parts.append('\n平台规则（供参考）：\n%s' % faq_text)
        parts.append('\n请以友好、简洁的语气回答；若涉及平台规则，请依据平台规则作答。')
        parts.append('返回 JSON 格式：'
                     '{"reply": "回复内容", "suggestions": ["追问1", "追问2", "追问3"]}')
        return '\n'.join(parts)

    @staticmethod
    def parse_json_response(raw_text):
        """从 LLM 响应中提取 JSON。

        兼容以下格式：
        1. 纯 JSON 文本（直接 json.loads）
        2. ```json ... ``` 或 ``` ... ``` 代码块包裹
        3. JSON 前后有多余文字（提取第一个 { 到最后一个 }）
        4. JSON 数组格式（提取第一个 [ 到最后一个 ]，包装为 {"items": [...]}）

        Returns:
            解析后的 dict；解析失败返回空 dict {}。
        """
        if not raw_text:
            return {}
        text = raw_text.strip()

        # 1. 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {'items': result}
        except (ValueError, TypeError):
            pass

        # 2. 尝试提取 ```json ... ``` 或 ``` ... ``` 代码块
        json_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_block_match:
            try:
                result = json.loads(json_block_match.group(1).strip())
                if isinstance(result, dict):
                    return result
                if isinstance(result, list):
                    return {'items': result}
            except (ValueError, TypeError):
                pass

        # 3. 尝试提取第一个 { 到最后一个 }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except (ValueError, TypeError):
                pass

        # 4. 尝试提取第一个 [ 到最后一个 ]（数组格式）
        first_bracket = text.find('[')
        last_bracket = text.rfind(']')
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            try:
                result = json.loads(text[first_bracket:last_bracket + 1])
                if isinstance(result, list):
                    return {'items': result}
                return result
            except (ValueError, TypeError):
                pass

        return {}
