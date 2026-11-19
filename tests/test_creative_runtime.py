"""Offline end-to-end tests for opt-in Creative runtime and approval flows."""
from __future__ import annotations

import json
from contextlib import closing

from test_engine import Base, FakeAI
from test_pipeline_quality import ScriptedAI, prose
from novelengine.config import project_dir
from novelengine.project_state import enable_creative, project_state
from novelengine.creative_runtime import (
    creative_propose, creative_action, creative_import_model, creative_status,
    creative_note, creative_packet,
)
from novelengine.creative.v41_adapters import StaleMemorySource
from novelengine.pipeline import scene_packet, process_scene
from novelengine.store import save_scene, scene_revision, story_db, now
from novelengine.project_backup import create_backup


class CreativeRuntimeTests(Base):
    def setUp(self):
        super().setUp()
        self.ch = self.outline['chapters'][0]
        self.sc = self.ch['scenes'][0]

    def test_creative_off_by_default_and_clean_explicit_enable(self):
        self.assertFalse(project_state(project_dir(self.pid), project_id=self.pid)['creative_enabled'])
        self.assertIn('VOICE BIBLE:', scene_packet(self.pid, self.outline, self.ch, self.sc)[0])
        state = enable_creative(self.pid)
        self.assertTrue(state['creative_enabled'])
        self.assertTrue((project_dir(self.pid) / 'creative-memory.sqlite3').is_file())
        payload, hints = scene_packet(self.pid, self.outline, self.ch, self.sc)
        obj = json.loads(payload)
        self.assertEqual(obj['scene_id'], self.sc['id'])
        self.assertEqual(obj['goal'], self.sc['goal'])
        self.assertTrue(creative_status(self.pid)['enabled'])
        self.assertEqual(hints, [])

    def test_creative_cannot_auto_migrate_existing_scene(self):
        with closing(story_db(self.pid)) as db:
            save_scene(db, '001', '01', 'draft', 'Đã có cảnh trước.')
        with self.assertRaisesRegex(RuntimeError, 'chưa có cảnh/canon'):
            enable_creative(self.pid)
        self.assertFalse((project_dir(self.pid) / 'creative-memory.sqlite3').exists())

    def test_approved_pov_fact_visible_only_when_known(self):
        enable_creative(self.pid)
        a = creative_propose(self.pid, {
            'kind': 'canon', 'subject': 'bell', 'value': 'CANON_DUOC_BIET',
        })
        creative_action(self.pid, {'event_id': a['id'], 'action': 'approve'})
        b = creative_propose(self.pid, {
            'kind': 'knowledge', 'subject': 'An', 'key': 'bell', 'value': 'known',
            'evidence': 'Tác giả xác nhận An đã biết.',
        })
        creative_action(self.pid, {'event_id': b['id'], 'action': 'approve'})
        packet, _ = scene_packet(self.pid, self.outline, self.ch, self.sc)
        self.assertIn('CANON_DUOC_BIET', packet)
        revised = json.loads(json.dumps(self.outline))
        revised['chapters'][0]['scenes'][0]['pov'] = 'Linh'
        packet, _ = scene_packet(self.pid, revised, revised['chapters'][0],
                                 revised['chapters'][0]['scenes'][0])
        self.assertNotIn('CANON_DUOC_BIET', packet)

    def test_approved_source_revision_becomes_stale_after_rewrite(self):
        enable_creative(self.pid)
        with closing(story_db(self.pid)) as db:
            save_scene(db, self.ch['id'], self.sc['id'], 'edited', 'Cảnh gốc đã hoàn thành.')
        event = creative_propose(self.pid, {
            'kind': 'canon', 'subject': 'source', 'value': 'Mốc đã được viết',
            'chapter_id': self.ch['id'], 'scene_id': self.sc['id'],
        })
        creative_action(self.pid, {'event_id': event['id'], 'action': 'approve'})
        following = self.ch['scenes'][1]
        creative_packet(self.pid, self.outline, self.ch, following)
        with closing(story_db(self.pid)) as db:
            save_scene(db, self.ch['id'], self.sc['id'], 'edited', 'Cảnh gốc đã sửa lần nữa.')
        self.assertTrue(next(item for item in creative_status(self.pid)['items'] if item['id']==event['id'])['stale_source'])
        with self.assertRaises(StaleMemorySource):
            creative_packet(self.pid, self.outline, self.ch, following)

    def test_writer_does_not_publish_if_ledger_changed_during_generation(self):
        enable_creative(self.pid)

        def add_fact_during_writer():
            creative_propose(self.pid, {
                'kind': 'canon', 'subject': 'new', 'value': 'Trí nhớ thay đổi',
            })
            return prose(250)

        ai = ScriptedAI(writer=[add_fact_during_writer])
        with self.assertRaisesRegex(RuntimeError, 'Creative Memory đã thay đổi'):
            process_scene(self.pid, self.outline, self.ch, self.sc, ai)
        with closing(story_db(self.pid)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0], 0)
        self.assertEqual(creative_status(self.pid)['revision'], 1)

    def test_model_v4_import_requires_placement_and_separate_approval(self):
        enable_creative(self.pid)
        with closing(story_db(self.pid)) as db, db:
            save_scene(db, self.ch['id'], self.sc['id'], 'edited', 'Văn bản nguồn', commit=False)
            db.execute(
                """INSERT INTO memory_items(kind,subject,content,chapter,source,status,created)
                   VALUES('fact','An','An mang chuông',?,'model','pending',?)""",
                (self.ch['id'], now()),
            )
            row_id = db.execute('SELECT id FROM memory_items').fetchone()[0]
        with self.assertRaises(ValueError):
            creative_import_model(self.pid, {'id': row_id, 'subject': 'An'})
        result = creative_import_model(self.pid, {
            'id': row_id, 'subject': 'bell-import', 'scene_id': self.sc['id'],
        })
        self.assertEqual(result['status'], 'pending')
        creative_action(self.pid, {'event_id': result['id'], 'action': 'approve'})
        # Never mirror sidecar decisions back into story.db without a journal.
        with closing(story_db(self.pid)) as db:
            self.assertEqual(db.execute('SELECT status FROM memory_items WHERE id=?', (row_id,)).fetchone()[0], 'pending')
        self.assertEqual(creative_status(self.pid)['revision'], 2)

    def test_curated_rag_note_is_versioned_in_backup(self):
        enable_creative(self.pid)
        creative_note(self.pid, {
            'action': 'add', 'name': 'Ẩn cảm xúc', 'purpose': 'An thể hiện sợ hãi qua hành động',
            'expected_effect': 'Tăng ẩn ý',
        })
        info = creative_status(self.pid)
        self.assertEqual(len(info['notes']), 1)
        self.assertTrue(info['notes'][0]['reviewed'])
        filename = project_dir(self.pid) / 'backups' / create_backup(self.pid)
        import zipfile
        with zipfile.ZipFile(filename) as archive:
            self.assertIn('creative-notes.json', archive.namelist())
        creative_note(self.pid, {'action': 'delete', 'note_id': info['notes'][0]['note_id']})
        self.assertEqual(creative_status(self.pid)['notes'], [])
