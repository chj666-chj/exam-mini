"""
Import knowledge base entries from a portable JSON export file into the
`knowledgebase` collection.

Usage:
    python manage.py import_knowledgebase_json <path-to-json>
    python manage.py import_knowledgebase_json <path-to-json> --reset

The JSON file must follow the format produced by tools/build_knowledgebase.py:
{
  "meta": { ... },
  "documents": [ { "_id": "...", "title": "...", ... }, ... ]
}

This is idempotent: existing _id entries are updated, new ones created.
"""
import json
import os
import sys
from django.core.management.base import BaseCommand
from core.models import Document


class Command(BaseCommand):
    help = "Import knowledge base documents from a portable JSON file into the knowledgebase collection"

    def add_arguments(self, parser):
        parser.add_argument('json_path', type=str, help='Path to the knowledge base JSON export file')
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear existing knowledgebase documents before importing',
        )

    def handle(self, *args, **options):
        json_path = options['json_path']
        if not os.path.exists(json_path):
            self.stderr.write(self.style.ERROR(f'File not found: {json_path}'))
            sys.exit(1)

        with open(json_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        documents = payload.get('documents', [])
        if not documents:
            self.stderr.write(self.style.ERROR('No documents found in JSON (expected "documents" key)'))
            sys.exit(1)

        if options['reset']:
            deleted, _ = Document.objects.filter(collection='knowledgebase').delete()
            self.stdout.write(self.style.WARNING(f'Cleared {deleted} existing knowledgebase documents'))

        created = 0
        updated = 0
        errors = 0
        for doc_data in documents:
            doc_id = doc_data.get('_id')
            if not doc_id:
                self.stderr.write(self.style.WARNING(f'Skipping document without _id: {doc_data.get("title", "?")}'))
                errors += 1
                continue
            # Remove _id from the data payload (it becomes the doc_id column)
            data = {k: v for k, v in doc_data.items() if k != '_id'}
            _, was_created = Document.objects.update_or_create(
                collection='knowledgebase',
                doc_id=doc_id,
                defaults={'data': data},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Knowledge base import complete: {created} created, {updated} updated, '
                f'{errors} errors, {len(documents)} total documents'
            )
        )
