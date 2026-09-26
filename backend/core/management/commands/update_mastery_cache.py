"""计算并更新知识点掌握度缓存。

用法：
    python manage.py update_mastery_cache           # 更新所有知识点的掌握度
    python manage.py update_mastery_cache --exam=RK_RJJS  # 仅更新指定考试的知识点

掌握度计算逻辑：
    1. 对每个知识点 KP，找到所有 knowledgePointIds 包含 KP._id 的题目 → questionSet
    2. 从 historys 中找到 items 包含 questionSet 中任意题目的记录
    3. 对每条历史记录，检查 score_arr 中对应题目的对错
    4. 统计：totalAnswered(去重已答), totalCorrect(答对次数), masteryRate
    5. 掌握度分级：>=85% 精通, >=70% 熟练, >=60% 一般, <60% 薄弱, 0% 未练习
    6. 更新 knowledgepoints.masteryCache 字段
"""
from django.core.management.base import BaseCommand

from core.models import Document


class Command(BaseCommand):
    help = '从 historys 集合聚合答题数据，计算并更新 knowledgepoints.masteryCache'

    def add_arguments(self, parser):
        parser.add_argument('--exam', type=str, default='',
                            help='仅更新指定考试ID的知识点（如 RK_RJJS）')

    def handle(self, *args, **options):
        exam_filter = options.get('exam', '')

        # 1. 加载所有知识点
        kp_qs = Document.objects.filter(collection='knowledgepoints')
        if exam_filter:
            kp_qs = kp_qs.filter(data__examId=exam_filter)

        kps = list(kp_qs)
        if not kps:
            self.stdout.write(self.style.WARNING('无知识点数据，请先运行 seed_knowledge_points'))
            return

        # 2. 加载所有题目，构建 {question_id: question_doc} 映射
        all_questions = Document.objects.filter(collection='questions')
        question_map = {}
        for q_doc in all_questions:
            q = q_doc.to_client()
            question_map[q['_id']] = q

        # 3. 构建知识点 → 题目ID集合的映射
        kp_question_sets = {}
        for kp_doc in kps:
            kp = kp_doc.to_client()
            kp_id = kp['_id']
            kp_question_sets[kp_id] = set()

        for q_id, q in question_map.items():
            kp_ids = q.get('knowledgePointIds', [])
            for kp_id in kp_ids:
                if kp_id in kp_question_sets:
                    kp_question_sets[kp_id].add(q_id)

        # 4. 加载所有 historys 记录
        all_historys = Document.objects.filter(collection='historys')
        historys_list = []
        for h_doc in all_historys:
            h = h_doc.to_client()
            historys_list.append({
                'items': h.get('items', []),
                'score_arr': h.get('score_arr', []),
            })

        # 5. 计算每个知识点的掌握度
        updated = 0
        from datetime import datetime
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for kp_doc in kps:
            kp = kp_doc.to_client()
            kp_id = kp['_id']
            question_set = kp_question_sets.get(kp_id, set())

            if not question_set:
                # 无关联题目，跳过
                continue

            total_answered = set()
            total_correct = 0
            total_attempts = 0

            for h in historys_list:
                items = h.get('items', [])
                score_arr = h.get('score_arr', [])

                for idx, q_id in enumerate(items):
                    if q_id not in question_set:
                        continue

                    total_answered.add(q_id)
                    total_attempts += 1

                    # 获取用户答案
                    if idx < len(score_arr):
                        user_answer = score_arr[idx]
                        if not isinstance(user_answer, list):
                            user_answer = [user_answer] if user_answer else []
                    else:
                        user_answer = []

                    # 获取正确答案
                    question = question_map.get(q_id)
                    if not question:
                        continue

                    options = question.get('options', [])
                    if isinstance(options, str):
                        import json
                        try:
                            options = json.loads(options)
                        except (ValueError, TypeError):
                            options = []

                    correct_codes = []
                    for opt in options:
                        if isinstance(opt, dict) and opt.get('value') == 1:
                            correct_codes.append(opt.get('code', ''))

                    # 比对答案
                    if user_answer and len(user_answer) == len(correct_codes):
                        all_match = True
                        for code in user_answer:
                            if code not in correct_codes:
                                all_match = False
                                break
                        if all_match:
                            total_correct += 1

            # 计算掌握度
            answered_count = len(total_answered)
            if answered_count > 0:
                mastery_rate = round(total_correct / total_attempts * 100) if total_attempts > 0 else 0
            else:
                mastery_rate = 0

            # 分级
            if answered_count == 0:
                level = 'none'
            elif mastery_rate >= 85:
                level = 'mastered'
            elif mastery_rate >= 70:
                level = 'proficient'
            elif mastery_rate >= 60:
                level = 'fair'
            else:
                level = 'weak'

            # 更新 masteryCache
            updated_data = dict(kp_doc.data)
            updated_data['masteryCache'] = {
                'totalAnswered': answered_count,
                'totalCorrect': total_correct,
                'totalAttempts': total_attempts,
                'masteryRate': mastery_rate,
                'level': level,
                'lastUpdated': now_str,
            }
            kp_doc.data = updated_data
            kp_doc.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n=== 完成，共更新 {updated} 个知识点的掌握度缓存 ==='
        ))

        # 输出统计
        self.stdout.write(f'\n--- 掌握度分布 ---')
        level_counts = {'none': 0, 'weak': 0, 'fair': 0, 'proficient': 0, 'mastered': 0}
        for kp_doc in kps:
            mc = kp_doc.data.get('masteryCache', {})
            lv = mc.get('level', 'none')
            level_counts[lv] = level_counts.get(lv, 0) + 1

        level_labels = {
            'none': '未练习',
            'weak': '薄弱(<60%)',
            'fair': '一般(60-69%)',
            'proficient': '熟练(70-84%)',
            'mastered': '精通(>=85%)',
        }
        for lv in ['mastered', 'proficient', 'fair', 'weak', 'none']:
            self.stdout.write(f'  {level_labels[lv]:<16} {level_counts[lv]:>3} 个')
