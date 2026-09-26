"""生成知识点主数据并自动标注题目。

用法：
    python manage.py seed_knowledge_points          # 生成知识点 + 标注题目
    python manage.py seed_knowledge_points --clean  # 清空旧知识点数据后重新生成

数据流：
    subjects.knowledgePoints (字符串数组)
      → knowledgepoints 集合 (三级树: 一级=章节名, 二级=知识点字符串)
    questions (无 knowledgePointIds)
      → questions.knowledgePointIds = [对应章节的一级知识点ID]
      → questions.knowledgePointNames = [章节名]

ID 命名规范：
    一级(章节级): KP_{examShort}_CH{chapterNum}     如 KP_RJJS_CH01
    二级(考点级): KP_{examShort}_CH{chapterNum}_{idx:03d}  如 KP_RJJS_CH01_001
"""
from django.core.management.base import BaseCommand

from core.models import Document


class Command(BaseCommand):
    help = '生成知识点主数据（knowledgepoints 集合）并自动标注题目（questions.knowledgePointIds）'

    def add_arguments(self, parser):
        parser.add_argument('--clean', action='store_true',
                            help='清空旧知识点数据后重新生成')

    def handle(self, *args, **options):
        if options['clean']:
            deleted, _ = Document.objects.filter(collection='knowledgepoints').delete()
            self.stdout.write(self.style.WARNING(f'已清空旧知识点数据 {deleted} 条 (--clean)'))

        # 1. 读取所有 subjects
        subjects = Document.objects.filter(collection='subjects').order_by('pk')
        if not subjects.exists():
            self.stdout.write(self.style.ERROR('subjects 集合为空，请先运行 seed_exam_data'))
            return

        kp_count = 0
        kp_map = {}  # subjectId → level1_kp_id, 用于题目标注

        for subj_doc in subjects:
            subj = subj_doc.to_client()
            subj_id = subj['_id']
            subj_name = subj.get('name', '')
            exam_id = subj.get('pid', '')
            kp_names = subj.get('knowledgePoints', [])
            sort_weight = subj.get('sortWeight', 0)

            # 从 subjectId 提取缩写和章节号: RK_RJJS_CH01 → RJJS, CH01
            parts = subj_id.split('_')
            if len(parts) >= 3:
                exam_short = parts[1]
                chapter_code = parts[2]  # 如 CH01
            else:
                exam_short = subj_id
                chapter_code = subj_id

            # --- 创建一级知识点（章节级） ---
            kp_level1_id = f"KP_{exam_short}_{chapter_code}"
            kp_level1_data = {
                'name': subj_name,
                'pid': exam_id,
                'examId': exam_id,
                'subjectId': subj_id,
                'level': 1,
                'description': subj.get('description', ''),
                'sortWeight': sort_weight,
                'questionCount': 0,  # 稍后更新
            }
            Document.objects.update_or_create(
                collection='knowledgepoints', doc_id=kp_level1_id,
                defaults={'data': kp_level1_data},
            )
            kp_count += 1
            kp_map[subj_id] = kp_level1_id

            # --- 创建二级知识点（考点级） ---
            for idx, kp_name in enumerate(kp_names):
                kp_level2_id = f"KP_{exam_short}_{chapter_code}_{idx + 1:03d}"
                kp_level2_data = {
                    'name': kp_name,
                    'pid': kp_level1_id,
                    'examId': exam_id,
                    'subjectId': subj_id,
                    'level': 2,
                    'description': '',
                    'sortWeight': idx + 1,
                    'questionCount': 0,
                }
                Document.objects.update_or_create(
                    collection='knowledgepoints', doc_id=kp_level2_id,
                    defaults={'data': kp_level2_data},
                )
                kp_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'knowledgepoints  {kp_count:>3} 条  (知识点主数据, {subjects.count()} 个章节)'
        ))

        # 2. 自动标注题目（章节级：关联到一级知识点）
        questions = Document.objects.filter(collection='questions').order_by('pk')
        annotated = 0
        question_count_by_kp = {}  # kp_id → count

        for q_doc in questions:
            q_data = dict(q_doc.data)
            examid = q_data.get('examid') or q_data.get('chapter', '')

            if examid in kp_map:
                kp_id = kp_map[examid]
                kp_doc = Document.objects.filter(
                    collection='knowledgepoints', doc_id=kp_id
                ).first()
                kp_name = kp_doc.data.get('name', '') if kp_doc else ''

                q_data['knowledgePointIds'] = [kp_id]
                q_data['knowledgePointNames'] = [kp_name]
                q_doc.data = q_data
                q_doc.save()
                annotated += 1

                question_count_by_kp[kp_id] = question_count_by_kp.get(kp_id, 0) + 1

        self.stdout.write(self.style.SUCCESS(
            f'questions annotated  {annotated:>3} 条  (自动标注 knowledgePointIds)'
        ))

        # 3. 更新一级知识点的 questionCount 缓存
        for kp_id, count in question_count_by_kp.items():
            kp_doc = Document.objects.filter(
                collection='knowledgepoints', doc_id=kp_id
            ).first()
            if kp_doc:
                updated = dict(kp_doc.data)
                updated['questionCount'] = count
                kp_doc.data = updated
                kp_doc.save()

        # 4. 输出统计
        self.stdout.write(self.style.SUCCESS(f'\n=== 完成 ==='))
        self.stdout.write(f'\n--- 知识点统计 ---')
        for subj_doc in subjects:
            subj = subj_doc.to_client()
            subj_id = subj['_id']
            if subj_id in kp_map:
                kp_id = kp_map[subj_id]
                kp_doc = Document.objects.filter(
                    collection='knowledgepoints', doc_id=kp_id
                ).first()
                q_count = kp_doc.data.get('questionCount', 0) if kp_doc else 0
                child_count = Document.objects.filter(
                    collection='knowledgepoints', data__pid=kp_id
                ).count()
                self.stdout.write(
                    f"  {subj.get('name', ''):<20} "
                    f"二级知识点:{child_count}  关联题目:{q_count}"
                )
