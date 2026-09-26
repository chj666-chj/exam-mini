"""
Export the knowledgebase collection from the system database into portable files.

Usage:
    python manage.py export_knowledgebase_json [--dir <output_dir>]

Produces:
  1. knowledgebase_export.json   — single portable file (re-importable via
                                   import_knowledgebase_json). This is the
                                   canonical migration / backup format.
  2. knowledgebase/<_id>.md      — one human-readable Markdown file per document
                                   (for browsing / re-parsing / other systems).

The JSON structure is intentionally simple and self-describing so it can be
re-imported on any instance of this system (or adapted to another system) by
file upload / script.
"""
import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from core.models import Document


class Command(BaseCommand):
    help = "Export the knowledgebase collection into a portable JSON file (and per-doc Markdown files)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            type=str,
            default=None,
            help='Output directory (default: <project>/outputs/knowledgebase_export)',
        )

    def handle(self, *args, **options):
        out_dir = options['dir'] or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'outputs', 'knowledgebase_export'
        )
        os.makedirs(out_dir, exist_ok=True)
        md_dir = os.path.join(out_dir, 'knowledgebase')
        os.makedirs(md_dir, exist_ok=True)

        docs = Document.objects.filter(collection='knowledgebase').order_by('doc_id')
        documents = []
        for d in docs:
            data = dict(d.data)
            data['_id'] = d.doc_id
            documents.append(data)

        payload = {
            "meta": {
                "format": "exam-buddy-knowledgebase",
                "format_version": "1.0",
                "collection": "knowledgebase",
                "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "导出自考试宝系统 knowledgebase 集合",
                "count": len(documents),
                "import_command": "python manage.py import_knowledgebase_json <file> [--reset]",
            },
            "documents": documents,
        }

        json_path = os.path.join(out_dir, 'knowledgebase_export.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Per-document Markdown files
        md_count = 0
        for doc in documents:
            md = self.to_markdown(doc)
            safe_id = doc.get('_id', f'doc_{md_count}').replace('/', '_')
            md_path = os.path.join(md_dir, f"{safe_id}.md")
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md)
            md_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Exported {len(documents)} documents\n'
                f'  JSON : {json_path}\n'
                f'  Markdown dir: {md_dir} ({md_count} files)'
            )
        )

    @staticmethod
    def to_markdown(doc):
        lines = []
        lines.append(f"# {doc.get('title', doc.get('_id', '未命名'))}\n")
        meta = []
        if doc.get('type'):
            meta.append(f"- **类型**：{doc['type']}")
        if doc.get('category'):
            meta.append(f"- **分类**：{doc['category']}")
        if doc.get('bookTitle'):
            meta.append(f"- **来源书籍**：{doc['bookTitle']}")
        if doc.get('chapterNo'):
            meta.append(f"- **章节**：第{doc['chapterNo']}章 {doc.get('chapterTitle', '')}")
        if doc.get('pages'):
            meta.append(f"- **页数**：{doc['pages']}")
        if doc.get('summary'):
            meta.append(f"- **摘要**：{doc['summary']}")
        if meta:
            lines.append("\n".join(meta) + "\n")
        lines.append("---\n")
        lines.append(doc.get('content', '') or '（无正文内容）')
        lines.append("")
        return "\n".join(lines)
