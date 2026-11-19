import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from novelengine.creative.memory_rules import MemoryConflict, MemoryEvent, MemoryRecord, StoryPosition
from novelengine.creative.memory_storage import (
    MEMORY_FILENAME, MemoryStorageError, SQLiteMemoryStore, StaleMemoryRevision,
)
from novelengine.creative.outline_contract import validate_outline
from novelengine.outline import sample_outline


def proposal(event):
    return MemoryRecord("propose", event.event_id, event)


class MemoryStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "Truyện #1"
        self.directory.mkdir()
        self.contract = validate_outline(sample_outline()).require_contract()
        self.store = self.open_store()

    def open_store(self):
        return SQLiteMemoryStore(self.directory, project_id="demo", layout_id=self.contract.layout_id)

    def test_reopen_preserves_journal_statuses_evidence_and_projection(self):
        position = self.contract.scene_position("001", "01", beat=1)
        fact = MemoryEvent("x", StoryPosition(0), "canon", "X", "Chìa khóa nằm trong hòm.")
        witnessed = MemoryEvent(
            "witness", position, "timeline", "open", "An mở hòm.", scene_revision=15,
        )
        learned = MemoryEvent(
            "learn", self.contract.scene_position("001", "01", beat=2), "knowledge", "An", "known",
            key="X", source="model", evidence="An nhận ra chìa.", requires=("witness",), scene_revision=15,
        )
        pending = MemoryEvent("p", StoryPosition(2), "thread", "letter", "đang mở", key="trạng thái")
        rejected = MemoryEvent("r", StoryPosition(2), "canon", "R", "Giả thuyết")
        revoked = MemoryEvent("u", StoryPosition(2), "canon", "U", "Chi tiết cũ")
        records = [
            proposal(fact), MemoryRecord("approve", "x", reason="Đã đọc."),
            proposal(witnessed), MemoryRecord("approve", "witness"),
            proposal(learned), MemoryRecord("approve", "learn"),
            proposal(pending), proposal(rejected), MemoryRecord("reject", "r", reason="Thiếu bằng chứng."),
            proposal(revoked), MemoryRecord("approve", "u"), MemoryRecord("undo", "u", reason="Đã đổi dàn ý."),
        ]
        self.assertEqual(self.store.commit(records), len(records))
        reopened = self.open_store().read()
        self.assertEqual(reopened.journal, tuple(records))
        self.assertEqual(reopened.revision, len(records))
        self.assertEqual(reopened.validate("p"), ())
        self.assertEqual([reopened.status(key) for key in ("x", "p", "r", "u")],
                         ["approved", "pending", "rejected", "revoked"])
        self.assertEqual(reopened.snapshot(before=position).known_facts("An"), ())
        self.assertEqual(reopened.snapshot().known_facts("An")[0].statement, fact.value)
        self.assertEqual(dict(reopened.snapshot().canon), {"X": fact.value})

    def test_retry_is_idempotent_and_stale_revision_leaves_state_intact(self):
        initial = self.store.read()
        event = MemoryEvent("a", StoryPosition(0), "canon", "A", "Ban đầu")
        command = proposal(event)
        self.assertEqual(self.store.commit([command], expected_revision=initial.revision), 1)
        second = self.open_store()
        approval = MemoryRecord("approve", "a", reason="Bản đã soát.")
        with self.assertRaises(StaleMemoryRevision) as error:
            second.commit([approval], expected_revision=initial.revision)
        self.assertEqual((error.exception.expected, error.exception.current), (0, 1))
        self.assertEqual(second.commit([command, approval]), 2)
        self.assertEqual(second.commit([command, approval]), 2)
        self.assertEqual(initial.journal, ())
        self.assertEqual(second.read().journal, (command, approval))

    def test_two_stores_serialize_conflicting_approvals(self):
        other = self.open_store()
        barrier = Barrier(2)

        def try_commit(store, event_id, value):
            event = MemoryEvent(event_id, StoryPosition(1), "canon", "X", value)
            barrier.wait(timeout=5)
            try:
                return store.commit([proposal(event), MemoryRecord("approve", event_id)])
            except MemoryConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(try_commit, self.store, "a", "Vàng"), pool.submit(try_commit, other, "b", "Xám")]
            self.assertCountEqual([future.result() for future in futures], [2, None])
        view = other.read()
        self.assertEqual(view.revision, 2)
        self.assertEqual(view.journal[0].event_id, view.journal[1].event_id)
        self.assertIn(view.snapshot().canon["X"], {"Vàng", "Xám"})

    def test_failed_sql_write_rolls_back_even_after_inserting_first_record(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("""
                CREATE TRIGGER fail_insert BEFORE INSERT ON ledger_journal
                WHEN NEW.event_id = 'b'
                BEGIN SELECT RAISE(ABORT, 'test write failure'); END
            """)
        first = MemoryEvent("a", StoryPosition(0), "canon", "A", "Trạng thái A")
        second = MemoryEvent("b", StoryPosition(0), "canon", "B", "Trạng thái B")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.commit([proposal(first), proposal(second)])
        self.assertEqual(self.open_store().read().journal, ())
        self.assertEqual(self.store.commit([proposal(first)]), 1)

    def test_dependency_conflict_rolls_back_other_decisions_in_batch(self):
        first = MemoryEvent("initial", StoryPosition(1), "timeline", "entry", "An vào kho.")
        second = MemoryEvent("later", StoryPosition(2), "timeline", "exit", "An rời kho.", requires=("initial",))
        third = MemoryEvent("extra", StoryPosition(3), "canon", "X", "Hậu đã rời bến.")
        self.store.commit([
            proposal(first), MemoryRecord("approve", "initial"), proposal(second), MemoryRecord("approve", "later"),
        ])
        original = self.store.read().journal
        with self.assertRaises(MemoryConflict):
            self.store.commit([proposal(third), MemoryRecord("undo", "initial")])
        self.assertEqual(self.open_store().read().journal, original)

    def test_legacy_sqlite_stays_byte_identical_and_bindings_are_checked(self):
        legacy = self.directory / "story.db"
        with closing(sqlite3.connect(legacy)) as db, db:
            db.execute("CREATE TABLE memory_items (id INTEGER PRIMARY KEY, content TEXT)")
            db.execute("INSERT INTO memory_items VALUES (1, 'canon cũ')")
        before = legacy.read_bytes()
        self.store.commit([proposal(MemoryEvent("a", StoryPosition(0), "canon", "A", "Sổ riêng"))])
        with self.assertRaises(MemoryStorageError):
            SQLiteMemoryStore(self.directory, project_id="other", layout_id=self.contract.layout_id)
        source = self.contract.to_v4()
        source["chapters"].reverse()
        reordered = validate_outline(source).require_contract()
        with self.assertRaises(MemoryStorageError):
            SQLiteMemoryStore(self.directory, project_id="demo", layout_id=reordered.layout_id)
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(self.open_store().read().revision, 1)

    def test_existing_foreign_database_is_rejected_without_a_schema_change(self):
        directory = self.directory / "foreign"
        directory.mkdir()
        path = directory / MEMORY_FILENAME
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE unrelated (data TEXT)")
        original = path.read_bytes()
        with self.assertRaises(MemoryStorageError):
            SQLiteMemoryStore(directory, project_id="demo", layout_id=self.contract.layout_id)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_journal_fails_closed(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("INSERT INTO ledger_journal (action, event_id, reason) VALUES ('approve', 'missing', '')")
        with self.assertRaisesRegex(MemoryStorageError, "Nhật ký trí nhớ không hợp lệ"):
            self.open_store().read()
