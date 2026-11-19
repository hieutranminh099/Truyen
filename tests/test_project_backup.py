"""Offline backup/restore acceptance tests: no Ollama, no user data."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from test_engine import Base
from novelengine.config import project_dir
from novelengine.project_backup import create_backup, restore_backup
from novelengine.project_state import enable_creative, project_write_lock, project_state
from novelengine.creative.memory_rules import MemoryEvent, MemoryRecord, StoryPosition
from novelengine.creative.memory_storage import SQLiteMemoryStore
from novelengine.creative.outline_contract import validate_outline
from novelengine.outline import load_outline
from novelengine.store import story_db, save_scene


class ProjectBackupTests(Base):
    def backup(self):
        return project_dir(self.pid) / 'backups' / create_backup(self.pid)

    def restored(self, source):
        root = tempfile.TemporaryDirectory(prefix='novel-restore-qa-')
        self.addCleanup(root.cleanup)
        result = restore_backup(source, self.pid, data_root=Path(root.name))
        return Path(root.name) / 'projects' / self.pid, result

    def test_legacy_zip_roundtrip_with_manifest_and_crc(self):
        with closing(story_db(self.pid)) as db, db:
            save_scene(db, '001', '01', 'edited', 'Bản thảo V4.' * 15, commit=False)
        archive = self.backup()
        with zipfile.ZipFile(archive) as zipfile_obj:
            names = set(zipfile_obj.namelist())
            self.assertIn('manifest.json', names)
            self.assertIn('story.db', names)
            self.assertIn('creative_state.json', names)
            self.assertNotIn('creative-memory.sqlite3', names)
            self.assertIsNone(zipfile_obj.testzip())
        target, result = self.restored(archive)
        self.assertFalse(result['creative_enabled'])
        with closing(sqlite3.connect(target / 'story.db')) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute("SELECT stage FROM scenes").fetchone()[0], 'edited')
        self.assertFalse(project_state(target, project_id=self.pid)['creative_enabled'])

    def test_creative_zip_keeps_approved_journal_after_restart(self):
        enable_creative(self.pid)
        location = project_dir(self.pid)
        contract = validate_outline(load_outline(location / 'outline.json')).require_contract()
        store = SQLiteMemoryStore(location, project_id=self.pid, layout_id=contract.layout_id)
        event = MemoryEvent('bell', StoryPosition(0), 'canon', 'bell', 'Chiếc chuông đồng gỉ')
        self.assertEqual(store.commit([MemoryRecord('propose', event.event_id, event)]), 1)
        self.assertEqual(store.commit([MemoryRecord('approve', 'bell', reason='Tác giả duyệt')]), 2)
        archive = self.backup()
        with zipfile.ZipFile(archive) as z:
            self.assertIn('creative-memory.sqlite3', z.namelist())
        restored, result = self.restored(archive)
        self.assertTrue(result['creative_enabled'])
        self.assertEqual(result['ledger_revision'], 2)
        read = SQLiteMemoryStore(restored, project_id=self.pid, layout_id=contract.layout_id).read()
        self.assertEqual(read.revision, 2)
        self.assertEqual(read.status('bell'), 'approved')
        self.assertEqual(len(read.journal), 2)

    def test_creative_missing_sidecar_rejected_without_new_empty_ledger(self):
        enable_creative(self.pid)
        sidecar = project_dir(self.pid) / 'creative-memory.sqlite3'
        sidecar.unlink()
        with self.assertRaisesRegex(RuntimeError, 'mất tệp trí nhớ'):
            self.backup()
        self.assertFalse(sidecar.exists())

    def test_zip_with_correct_crc_but_wrong_hash_is_rejected(self):
        source = self.backup()
        counterfeit = source.with_name('counterfeit.zip')
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(counterfeit, 'w') as dst:
            for info in src.infolist():
                content = src.read(info.filename)
                if info.filename == 'voice_bible.md':
                    content += b'FAKE'
                dst.writestr(info.filename, content)
        with tempfile.TemporaryDirectory(prefix='novel-restore-qa-') as root:
            with self.assertRaisesRegex(ValueError, 'Hash'):
                restore_backup(counterfeit, self.pid, data_root=Path(root))
            self.assertFalse((Path(root) / 'projects' / self.pid).exists())

    def test_existing_restore_destination_is_not_overwritten(self):
        archive = self.backup()
        with tempfile.TemporaryDirectory(prefix='novel-restore-qa-') as root:
            restore_backup(archive, self.pid, data_root=Path(root))
            target = Path(root) / 'projects' / self.pid
            before = (target / 'outline.json').read_bytes()
            with self.assertRaises(FileExistsError):
                restore_backup(archive, self.pid, data_root=Path(root))
            self.assertEqual(before, (target / 'outline.json').read_bytes())

    def test_missing_manifest_old_zip_is_not_auto_migrated(self):
        source = self.backup()
        legacy = source.with_name('legacy.zip')
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(legacy, 'w') as dst:
            for item in src.infolist():
                if item.filename not in ('manifest.json', 'creative_state.json'):
                    dst.writestr(item.filename, src.read(item.filename))
        with tempfile.TemporaryDirectory(prefix='novel-restore-qa-') as root:
            with self.assertRaisesRegex(ValueError, 'manifest'):
                restore_backup(legacy, self.pid, data_root=Path(root))
            self.assertFalse((Path(root) / 'projects' / self.pid).exists())

    def test_failed_second_sqlite_snapshot_does_not_publish_any_zip(self):
        enable_creative(self.pid)
        from novelengine.project_backup import _sqlite_snapshot
        original = _sqlite_snapshot

        def fail_sidecar(source, target):
            if source.name == 'creative-memory.sqlite3':
                raise OSError('disk full during second snapshot')
            return original(source, target)

        with patch('novelengine.project_backup._sqlite_snapshot', side_effect=fail_sidecar):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.backup()
        backup_dir = project_dir(self.pid) / 'backups'
        self.assertFalse(list(backup_dir.glob('backup_*.zip')))
        self.assertFalse(list(backup_dir.glob('.backup-staging-*')))
        self.assertTrue(self.backup().is_file())


    def test_qa04_truncated_empty_source_fails_closed_without_repairing_bytes(self):
        """SQLite backup may pad a short source page. Validate the source first."""
        enable_creative(self.pid)
        sidecar = project_dir(self.pid) / 'creative-memory.sqlite3'
        original = sidecar.read_bytes()
        self.assertGreater(len(original), 4096)
        self.assertEqual(len(original) % 4096, 0)
        sidecar.write_bytes(original[:-1])
        damaged = sidecar.read_bytes()
        before = hashlib.sha256(damaged).hexdigest()
        backup_dir = project_dir(self.pid) / 'backups'

        with self.assertRaisesRegex(ValueError, 'cắt giữa trang SQLite'):
            self.backup()

        self.assertEqual(sidecar.read_bytes(), damaged)
        self.assertEqual(hashlib.sha256(sidecar.read_bytes()).hexdigest(), before)
        self.assertFalse(list(backup_dir.glob('backup_*.zip')))
        self.assertFalse(list(backup_dir.glob('.backup-staging-*')))

    def test_qa04_truncated_populated_source_preserves_existing_backup(self):
        enable_creative(self.pid)
        location = project_dir(self.pid)
        contract = validate_outline(load_outline(location / 'outline.json')).require_contract()
        store = SQLiteMemoryStore(location, project_id=self.pid, layout_id=contract.layout_id)
        event = MemoryEvent('qa04', StoryPosition(0), 'canon', 'bell', 'Nguồn đã có dữ kiện')
        store.commit([MemoryRecord('propose', event.event_id, event)])
        archive = self.backup()
        original_backup = archive.read_bytes()
        sidecar = location / 'creative-memory.sqlite3'
        valid = sidecar.read_bytes()
        sidecar.write_bytes(valid[:-1])
        original_hash = hashlib.sha256(sidecar.read_bytes()).hexdigest()

        with self.assertRaisesRegex(ValueError, 'cắt giữa trang SQLite'):
            self.backup()

        self.assertEqual(hashlib.sha256(sidecar.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(archive.read_bytes(), original_backup)
        self.assertEqual(list(archive.parent.glob('backup_*.zip')), [archive])

    def test_qa05_crashed_child_stage_is_reclaimed_on_next_backup(self):
        """A hard process exit must not leave public ZIPs or persistent debris."""
        backups = project_dir(self.pid) / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        child_code = (
            'import os, pathlib, sqlite3, sys, tempfile; '
            "p=pathlib.Path(tempfile.mkdtemp(prefix='.backup-staging-',dir=sys.argv[1])); "
            "c=sqlite3.connect(p/'.backup-active.sqlite3',isolation_level=None); "
            "c.execute('CREATE TABLE lease (singleton INTEGER PRIMARY KEY)'); "
            "c.execute('BEGIN IMMEDIATE'); "
            "(p/'staged.zip').write_bytes(b'PARTIAL ZIP'); "
            'os._exit(17)'
        )
        crashed = subprocess.run([sys.executable, '-c', child_code, str(backups)],
                                 capture_output=True, timeout=20)
        self.assertEqual(crashed.returncode, 17, crashed.stderr.decode(errors='replace'))
        orphaned = list(backups.glob('.backup-staging-*'))
        self.assertEqual(len(orphaned), 1)
        self.assertFalse(list(backups.glob('backup_*.zip')))
        archive = self.backup()
        self.assertTrue(archive.is_file())
        self.assertFalse(orphaned[0].exists())
        self.assertFalse(list(backups.glob('.backup-staging-*')))
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())

    def test_qa05_does_not_delete_a_concurrently_active_stage(self):
        """Only an unlocked marker may be reclaimed; live backups are untouched."""
        from novelengine.project_backup import _backup_stage
        location = project_dir(self.pid)
        backups = location / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        with _backup_stage(location, backups) as working:
            (working / 'staged.zip').write_bytes(b'ACTIVE')
            archive = self.backup()
            self.assertTrue(archive.exists())
            self.assertEqual((working / 'staged.zip').read_bytes(), b'ACTIVE')
        self.assertFalse(working.exists())

    def test_project_writer_cannot_commit_between_two_snapshots(self):
        enable_creative(self.pid)
        directory = project_dir(self.pid)
        contract = validate_outline(load_outline(directory / 'outline.json')).require_contract()
        started = threading.Event()
        committed = threading.Event()
        errors = []

        def writer():
            if not started.wait(10):
                errors.append('backup did not reach first snapshot')
                return
            with project_write_lock(directory):
                with closing(story_db(self.pid)) as db, db:
                    save_scene(db, '001', '01', 'edited', 'Đã thay đổi sau snapshot', commit=False)
                store = SQLiteMemoryStore(directory, project_id=self.pid, layout_id=contract.layout_id)
                event = MemoryEvent('later', StoryPosition(0), 'canon', 'clock', 'Chuông mới')
                store.commit([MemoryRecord('propose', 'later', event)])
                committed.set()

        from novelengine.project_backup import _sqlite_snapshot
        original = _sqlite_snapshot

        def synchronized(source, target):
            original(source, target)
            if source.name == 'story.db':
                started.set()
                self.assertFalse(committed.wait(.1))

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        try:
            with patch('novelengine.project_backup._sqlite_snapshot', side_effect=synchronized):
                archive = self.backup()
        finally:
            thread.join(10)
        self.assertFalse(errors)
        self.assertTrue(committed.is_set())
        target, result = self.restored(archive)
        with closing(sqlite3.connect(target / 'story.db')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0], 0)
        restored = SQLiteMemoryStore(target, project_id=self.pid, layout_id=contract.layout_id)
        self.assertEqual(restored.read().revision, 0)
        self.assertEqual(result['ledger_revision'], 0)
