"""Transactional storage for MemoryLedger in a dedicated project sidecar."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import ExitStack, closing, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Iterator

from .memory_rules import (
    MemoryEvent, MemoryIssue, MemoryLedger, MemoryRecord, MemorySnapshot, MemoryStatus, StoryPosition,
)


MEMORY_FILENAME = "creative-memory.sqlite3"
_APPLICATION_ID = 0x4E454D31
_FORMAT_VERSION = 1
_TABLE_COLUMNS = {
    "ledger_binding": (
        ("singleton", "INTEGER", 0, None, 1),
        ("project_id", "TEXT", 1, None, 0),
        ("layout_id", "TEXT", 1, None, 0),
    ),
    "ledger_journal": (
        ("seq", "INTEGER", 0, None, 1),
        ("action", "TEXT", 1, None, 0),
        ("event_id", "TEXT", 1, None, 0),
        ("event_json", "TEXT", 0, None, 0),
        ("reason", "TEXT", 1, None, 0),
    ),
}


class MemoryStorageError(ValueError):
    """The sidecar format, project binding or journal could not be read."""


class StaleMemoryRevision(MemoryStorageError):
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"Nhật ký trí nhớ đã đổi từ mốc {expected} sang {current}.")


@dataclass(frozen=True, slots=True)
class StoredMemory:
    project_id: str
    layout_id: str
    revision: int
    _ledger: MemoryLedger = field(repr=False)

    @property
    def journal(self) -> tuple[MemoryRecord, ...]:
        return self._ledger.journal

    def snapshot(self, *, before: StoryPosition | None = None) -> MemorySnapshot:
        return self._ledger.snapshot(before=before)

    def approved_events(self) -> tuple[MemoryEvent, ...]:
        return self._ledger.approved_events()

    def status(self, event_id: str) -> MemoryStatus:
        return self._ledger.status(event_id)

    def validate(self, event_id: str) -> tuple[MemoryIssue, ...]:
        return self._ledger.validate(event_id)


def _records(db: sqlite3.Connection) -> Iterator[MemoryRecord]:
    rows = db.execute("SELECT seq, action, event_id, event_json, reason FROM ledger_journal ORDER BY seq")
    for index, (seq, action, event_id, event_json, reason) in enumerate(rows, 1):
        if seq != index:
            raise ValueError(f"Thiếu bản ghi trí nhớ ở mốc {index}.")
        event = None
        if event_json is not None:
            values = json.loads(event_json)
            if not isinstance(values, dict):
                raise ValueError("Sự kiện trong nhật ký phải là JSON object.")
            values["position"] = StoryPosition(**values["position"])
            event = MemoryEvent(**values)
        yield MemoryRecord(action, event_id, event, reason)


class SQLiteMemoryStore:
    """Open an explicit sidecar bound to one project and outline ordering."""

    def __init__(self, project_dir: Path, *, project_id: str, layout_id: str):
        if not project_id.strip() or not layout_id.strip():
            raise ValueError("Cần ID dự án và định danh thứ tự dàn ý.")
        directory = Path(project_dir).resolve(strict=True)
        if not directory.is_dir():
            raise NotADirectoryError(directory)
        self.path = directory / MEMORY_FILENAME
        self._binding = (project_id, layout_id)
        try:
            self.path.lstat()
        except FileNotFoundError:
            self._create()
        except OSError as exc:
            raise MemoryStorageError(f"Không kiểm tra được tệp {MEMORY_FILENAME}. {exc}") from exc
        with self._transaction() as db:
            self._check_database(db, verify_pages=True)

    def _create(self) -> None:
        try:
            with TemporaryDirectory(prefix=".creative-memory-", dir=self.path.parent) as temporary:
                candidate = Path(temporary) / MEMORY_FILENAME
                with closing(sqlite3.connect(candidate, timeout=5.0)) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    self._initialize(db)
                try:
                    # Publish only a committed database. Windows rename has no-replace semantics.
                    if os.name == "nt":
                        candidate.rename(self.path)
                    else:
                        os.link(candidate, self.path)
                except FileExistsError:
                    # The constructor will validate the file already at the destination.
                    pass
        except (OSError, sqlite3.DatabaseError) as exc:
            raise MemoryStorageError(f"Không tạo được tệp {MEMORY_FILENAME}. {exc}") from exc

    def _file_size(self) -> int:
        try:
            info = self.path.lstat()
        except OSError as exc:
            raise MemoryStorageError(f"Không đọc được tệp {MEMORY_FILENAME}. {exc}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise MemoryStorageError("Đường dẫn sổ trí nhớ phải là tệp thường của dự án.")
        if info.st_size == 0:
            raise MemoryStorageError(f"Tệp {MEMORY_FILENAME} đã tồn tại và rỗng (0 byte).")
        return info.st_size

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        self._file_size()
        mode = "rw" if write else "ro"
        uri = f"{self.path.as_uri()}?mode={mode}"
        with ExitStack() as stack:
            try:
                db = stack.enter_context(closing(sqlite3.connect(uri, uri=True, timeout=5.0)))
                stack.enter_context(db)
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            except sqlite3.DatabaseError as exc:
                raise MemoryStorageError(f"Không mở được tệp {MEMORY_FILENAME}. {exc}") from exc
            yield db

    def _initialize(self, db: sqlite3.Connection) -> None:
        db.execute("""CREATE TABLE ledger_binding (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            project_id TEXT NOT NULL,
            layout_id TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE ledger_journal (
            seq INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_json TEXT,
            reason TEXT NOT NULL
        )""")
        db.execute("INSERT INTO ledger_binding VALUES (1, ?, ?)", self._binding)
        db.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
        db.execute(f"PRAGMA user_version = {_FORMAT_VERSION}")

    def _check_database(self, db: sqlite3.Connection, *, verify_pages: bool = False) -> None:
        try:
            application_id = db.execute("PRAGMA application_id").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if application_id != _APPLICATION_ID or version != _FORMAT_VERSION:
                raise MemoryStorageError("Định dạng sổ trí nhớ không được hỗ trợ.")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            # SQLite can pad a short final page during a read.
            if self._file_size() % page_size:
                raise MemoryStorageError(f"Tệp {MEMORY_FILENAME} bị cắt giữa trang SQLite.")
            for table, expected in _TABLE_COLUMNS.items():
                columns = tuple(row[1:] for row in db.execute(f"PRAGMA table_info({table})"))
                if columns != expected:
                    raise MemoryStorageError(f"Lược đồ bảng {table} của sổ trí nhớ không hợp lệ.")
            bindings = db.execute("SELECT singleton, project_id, layout_id FROM ledger_binding").fetchmany(2)
            if len(bindings) != 1 or bindings[0][0] != 1:
                raise MemoryStorageError("Sổ trí nhớ cần đúng một bản ghi định danh dự án.")
            if bindings[0][1:] != self._binding:
                raise MemoryStorageError("Sổ trí nhớ thuộc dự án hoặc thứ tự dàn ý khác.")
            if verify_pages:
                result = db.execute("PRAGMA quick_check(1)").fetchone()
                if result != ("ok",):
                    raise MemoryStorageError(f"Tệp {MEMORY_FILENAME} không toàn vẹn. {result[0]}")
        except sqlite3.DatabaseError as exc:
            raise MemoryStorageError(f"Không đọc được định dạng SQLite của tệp {MEMORY_FILENAME}. {exc}") from exc

    def _load(self, db: sqlite3.Connection) -> StoredMemory:
        self._check_database(db)
        try:
            ledger = MemoryLedger.from_journal(_records(db))
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
            raise MemoryStorageError(f"Nhật ký trí nhớ không hợp lệ. {exc}") from exc
        return StoredMemory(*self._binding, len(ledger.journal), ledger)

    def read(self) -> StoredMemory:
        """Return a view of one committed revision."""
        with self._transaction() as db:
            return self._load(db)

    def commit(self, records: Iterable[MemoryRecord], *, expected_revision: int | None = None) -> int:
        """Validate and record a whole batch, returning the committed journal revision."""
        batch = tuple(records)
        with self._transaction(write=True) as db:
            previous = self._load(db)
            if expected_revision is not None and expected_revision != previous.revision:
                raise StaleMemoryRevision(expected_revision, previous.revision)
            ledger = previous._ledger
            decide = {"approve": ledger.approve, "reject": ledger.reject, "undo": ledger.undo}
            for record in batch:
                if record.event is not None:
                    ledger.propose(record.event)
                else:
                    decide[record.action](record.event_id, reason=record.reason)

            journal = ledger.journal
            db.executemany(
                "INSERT INTO ledger_journal (action, event_id, event_json, reason) VALUES (?, ?, ?, ?)",
                (
                    (
                        record.action, record.event_id,
                        json.dumps(asdict(record.event), ensure_ascii=False) if record.event is not None else None,
                        record.reason,
                    )
                    for record in journal[previous.revision:]
                ),
            )
            return len(journal)
