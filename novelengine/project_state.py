"""Cross-process project write coordination and persistent Creative activation state.

The coordinator is a local SQLite mutex. All application-owned writes to a
project must hold it; Ollama calls happen outside the lock.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

STATE_FILE = 'creative_state.json'
SIDECAR_FILE = 'creative-memory.sqlite3'
_state = threading.local()


@contextmanager
def project_write_lock(directory: Path):
    """Serialize collaborating processes and allow same-thread nested calls."""
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    key = str(directory)
    held = getattr(_state, 'held', None)
    if held is None:
        held = {}
        _state.held = held
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    db = sqlite3.connect(directory / '.project-write-lock.sqlite3', timeout=45.0)
    try:
        db.execute('PRAGMA busy_timeout=45000')
        db.execute('BEGIN IMMEDIATE')
        held[key] = 1
        try:
            yield
        finally:
            held.pop(key, None)
            db.rollback()
    finally:
        db.close()


def project_state(directory: Path, *, project_id: str) -> dict:
    """Never infer that a missing sidecar means Creative is disabled."""
    directory = Path(directory)
    state_file = directory / STATE_FILE
    sidecar = directory / SIDECAR_FILE
    if not state_file.exists():
        if os.path.lexists(sidecar):
            raise RuntimeError('Dự án có sidecar nhưng không có cờ Creative bền vững; cần đối chiếu thủ công.')
        return {'format': 1, 'project_id': project_id, 'creative_enabled': False}
    if not state_file.is_file() or state_file.is_symlink():
        raise RuntimeError('Trạng thái Creative không phải tệp thường.')
    try:
        state = json.loads(state_file.read_text(encoding='utf8'))
    except (ValueError, UnicodeError, OSError) as exc:
        raise RuntimeError('Không đọc được trạng thái Creative của dự án.') from exc
    if (not isinstance(state, dict) or state.get('format') != 1
            or state.get('project_id') != project_id
            or type(state.get('creative_enabled')) is not bool):
        raise RuntimeError('Trạng thái Creative không khớp định danh dự án.')
    if state['creative_enabled'] and not os.path.lexists(sidecar):
        raise RuntimeError('Dự án đã bật Creative nhưng mất tệp trí nhớ: không được tạo sổ rỗng.')
    if not state['creative_enabled'] and os.path.lexists(sidecar):
        raise RuntimeError('Tồn tại Creative sidecar trong dự án chưa bật: cần đối chiếu.')
    return state


def save_project_state(directory: Path, state: dict):
    directory = Path(directory)
    fd, temporary = tempfile.mkstemp(prefix='.creative-state-', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / STATE_FILE)
    finally:
        Path(temporary).unlink(missing_ok=True)


def enable_creative(project_id: str) -> dict:
    """Explicit opt-in for an empty project; never auto-migrate legacy canon."""
    from .config import project_dir
    from .outline import load_outline
    from .creative.outline_contract import validate_outline
    from .creative.memory_storage import SQLiteMemoryStore
    from .store import story_db

    directory = project_dir(project_id)
    with project_write_lock(directory):
        state = project_state(directory, project_id=project_id)
        if state['creative_enabled']:
            return state
        c = story_db(project_id)
        try:
            used = any(c.execute(f'SELECT 1 FROM {name} LIMIT 1').fetchone()
                       for name in ('scenes', 'scene_versions', 'summaries', 'memory_items'))
        finally:
            c.close()
        if used:
            raise RuntimeError('Chỉ bật Creative trên dự án chưa có cảnh/canon. '
                               'Dự án cũ phải được migration có xác nhận.')
        contract = validate_outline(load_outline(directory / 'outline.json')).require_contract()
        SQLiteMemoryStore(directory, project_id=project_id, layout_id=contract.layout_id)
        state = {'format': 1, 'project_id': project_id, 'creative_enabled': True}
        save_project_state(directory, state)
        return state
