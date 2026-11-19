"""Project ZIP snapshots and fail-closed restore for V4 and Creative V4.1.

All cooperating writers acquire project_write_lock before commit. The lock is
held across *both* SQLite backup calls and all non-database file copies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_ROOT, PROJECTS, project_dir, validate_project_id
from .project_state import (
    SIDECAR_FILE, STATE_FILE, project_state, project_write_lock, save_project_state,
)
from .creative.memory_storage import SQLiteMemoryStore
from .creative.outline_contract import validate_outline
from .outline import load_outline

BACKUP_FORMAT = 1
MAX_RESTORE_BYTES = 128 * 1024 * 1024
MAX_EXTRACTED_BYTES = 768 * 1024 * 1024


def _digest(path: Path) -> dict:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}


def _sqlite_snapshot(src: Path, dst: Path):
    if not src.is_file() or src.is_symlink() or src.stat().st_size == 0:
        raise RuntimeError('Database nguồn bị thiếu, rỗng hoặc không phải tệp thường.')
    uri = src.resolve(strict=True).as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as source:
        with closing(sqlite3.connect(dst)) as target:
            source.backup(target)
            # The source V4 database uses WAL. A portable standalone snapshot
            # must not depend on its transient -wal/-shm companion files.
            target.execute('PRAGMA journal_mode=DELETE')
    with closing(sqlite3.connect(dst)) as check:
        if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Snapshot SQLite không toàn vẹn.')


def _scene_revisions(db: Path) -> dict:
    with closing(sqlite3.connect(f'{db.resolve().as_uri()}?mode=ro', uri=True)) as c:
        return {
            f'{chapter}/{scene}': version
            for chapter, scene, version in c.execute(
                'SELECT chapter,scene,MAX(id) FROM scene_versions GROUP BY chapter,scene'
            )
        }


def _safe_source_files(directory: Path) -> list[Path]:
    names = ('outline.json', 'outline_candidate.json', 'voice_bible.md')
    paths = [directory / name for name in names]
    paths.extend((directory / 'exports').glob('chapter_*.md'))
    safe = []
    for path in paths:
        if (path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(directory.resolve())):
            safe.append(path)
    if not (directory / 'outline.json').is_file():
        raise RuntimeError('Thiếu dàn ý dự án.')
    return safe


def _validate_sidecar(staging: Path, project_id: str, layout_id: str) -> int:
    if not (staging / SIDECAR_FILE).is_file():
        raise RuntimeError('Creative sidecar là thành phần bắt buộc.')
    store = SQLiteMemoryStore(staging, project_id=project_id, layout_id=layout_id)
    return store.read().revision


def create_backup(project_id: str) -> str:
    """Stage and validate a complete project snapshot before publishing ZIP."""
    project_id = validate_project_id(project_id)
    directory = project_dir(project_id)
    backups = directory / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    name = 'backup_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.zip'
    final_path = backups / name
    with tempfile.TemporaryDirectory(prefix='.backup-staging-', dir=backups) as tmp:
        staging = Path(tmp) / 'contents'
        staging.mkdir()
        with project_write_lock(directory):
            state = project_state(directory, project_id=project_id)
            contract = validate_outline(load_outline(directory / 'outline.json')).require_contract()
            _sqlite_snapshot(directory / 'story.db', staging / 'story.db')
            if state['creative_enabled']:
                _sqlite_snapshot(directory / SIDECAR_FILE, staging / SIDECAR_FILE)
                ledger_revision = _validate_sidecar(staging, project_id, contract.layout_id)
            else:
                ledger_revision = None
            for source in _safe_source_files(directory):
                dst = staging / source.relative_to(directory)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(source.read_bytes())
            save_project_state(staging, state)
            revisions = _scene_revisions(staging / 'story.db')
            files = {
                p.relative_to(staging).as_posix(): _digest(p)
                for p in staging.rglob('*')
                if p.is_file() and _allowed(p.relative_to(staging).as_posix())
            }
            files.pop('manifest.json', None)
            manifest = {
                'format': BACKUP_FORMAT,
                'snapshot_id': name.removesuffix('.zip'),
                'project_id': project_id,
                'creative_enabled': state['creative_enabled'],
                'layout_id': contract.layout_id,
                'outline_sha256': files['outline.json']['sha256'],
                'ledger_revision': ledger_revision,
                'scene_revisions': revisions,
                'files': files,
            }
        (staging / 'manifest.json').write_text(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2), encoding='utf8'
        )
        temporary_zip = Path(tmp) / 'staged.zip'
        with zipfile.ZipFile(temporary_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob('*')):
                if path.is_file() and _allowed(path.relative_to(staging).as_posix()):
                    archive.write(path, path.relative_to(staging).as_posix())
        with zipfile.ZipFile(temporary_zip) as archive:
            if bad := archive.testzip():
                raise RuntimeError('ZIP không toàn vẹn tại tệp ' + bad)
        # A state change between snapshot and publish is not allowed to turn a
        # formerly complete legacy backup into a supposedly Creative backup.
        with project_write_lock(directory):
            current = project_state(directory, project_id=project_id)
            if current['creative_enabled'] != state['creative_enabled']:
                raise RuntimeError('Chế độ Creative đã thay đổi khi sao lưu; hãy tạo lại snapshot.')
            temporary_zip.replace(final_path)
    return name


def _allowed(name: str) -> bool:
    return (name in {'story.db', SIDECAR_FILE, 'outline.json', 'outline_candidate.json',
                     'voice_bible.md', STATE_FILE, 'manifest.json'}
            or bool(re.fullmatch(r'exports/chapter_[A-Za-z0-9_-]+\.md', name)))


def _check_archive(archive: zipfile.ZipFile) -> list:
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)) or len(entries) > 5000:
        raise ValueError('ZIP có tên tệp trùng hoặc quá nhiều tệp.')
    total = 0
    for item in entries:
        if (not _allowed(item.filename) or item.is_dir() or item.filename.startswith('/')
                or '\\' in item.filename or item.flag_bits & 0x1):
            raise ValueError('ZIP chứa đường dẫn hoặc loại tệp không được phép: ' + repr(item.filename))
        mode = item.external_attr >> 16
        if (mode & 0o170000) == 0o120000:
            raise ValueError('ZIP chứa symlink.')
        total += item.file_size
    if total > MAX_EXTRACTED_BYTES:
        raise ValueError('ZIP giải nén vượt giới hạn.')
    if not {'manifest.json', 'story.db', 'outline.json', STATE_FILE} <= set(names):
        raise ValueError('ZIP không có manifest hoặc thiếu tệp bắt buộc. '
                         'Backup V4 cũ cần được phân loại thủ công, không tự tạo sidecar.')
    if bad := archive.testzip():
        raise ValueError('CRC ZIP không khớp tại tệp ' + bad)
    return entries


def _verify_staged(staging: Path, *, project_id: str) -> dict:
    manifest = json.loads((staging / 'manifest.json').read_text(encoding='utf8'))
    if (not isinstance(manifest, dict) or manifest.get('format') != BACKUP_FORMAT
            or manifest.get('project_id') != project_id
            or type(manifest.get('creative_enabled')) is not bool):
        raise ValueError('Manifest sai định dạng hoặc ID dự án.')
    files = manifest.get('files')
    if not isinstance(files, dict):
        raise ValueError('Manifest thiếu danh sách tệp.')
    actual = {p.relative_to(staging).as_posix() for p in staging.rglob('*') if p.is_file()}
    if actual != set(files) | {'manifest.json'}:
        raise ValueError('Danh sách tệp ZIP khác manifest.')
    for name, expected in files.items():
        if not _allowed(name) or not isinstance(expected, dict) or _digest(staging / name) != expected:
            raise ValueError('Hash hoặc kích thước ZIP không khớp: ' + name)
    state = project_state(staging, project_id=project_id)
    if state['creative_enabled'] != manifest['creative_enabled']:
        raise ValueError('Cờ Creative không khớp manifest.')
    contract = validate_outline(load_outline(staging / 'outline.json')).require_contract()
    if (manifest.get('layout_id') != contract.layout_id
            or manifest.get('outline_sha256') != files['outline.json']['sha256']):
        raise ValueError('Định danh thứ tự cảnh/dàn ý không khớp manifest.')
    with closing(sqlite3.connect(f'{(staging / "story.db").resolve().as_uri()}?mode=ro', uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('story.db không toàn vẹn.')
    revisions = _scene_revisions(staging / 'story.db')
    if revisions != manifest.get('scene_revisions'):
        raise ValueError('Phiên bản cảnh nguồn không khớp manifest.')
    if state['creative_enabled']:
        rev = _validate_sidecar(staging, project_id, contract.layout_id)
        if rev != manifest.get('ledger_revision'):
            raise ValueError('Revision ledger không khớp manifest.')
        store = SQLiteMemoryStore(staging, project_id=project_id, layout_id=contract.layout_id)
        # A stale event remains part of history, but is not auto-accepted as canon.
        with closing(sqlite3.connect(f'{(staging / "story.db").resolve().as_uri()}?mode=ro', uri=True)) as c:
            for event in store.read().approved_events():
                if event.scene_revision is None:
                    continue
                chapters = contract.to_v4()['chapters']
                try:
                    chapter_obj = chapters[event.position.chapter - 1]
                    scene_obj = chapter_obj['scenes'][event.position.scene - 1]
                    chapter, scene = chapter_obj['id'], scene_obj['id']
                except (IndexError, TypeError):
                    raise ValueError('Sự kiện Creative trỏ vào cảnh ngoài dàn ý.') from None
                row = c.execute(
                    'SELECT id FROM scene_versions WHERE id=? AND chapter=? AND scene=?',
                    (event.scene_revision, chapter, scene),
                ).fetchone()
                if row is None:
                    raise ValueError('Sự kiện Creative trỏ vào phiên bản cảnh không tồn tại.')
    elif SIDECAR_FILE in files:
        raise ValueError('Backup Creative disabled không được mang sidecar.')
    return manifest


def restore_backup(source: Path, project_id: str, *, data_root: Path | None = None) -> dict:
    """Never overwrite an existing project. No directory is published before validation."""
    project_id = validate_project_id(project_id)
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_RESTORE_BYTES:
        raise ValueError('Tệp ZIP không hợp lệ hoặc vượt giới hạn upload.')
    root = Path(data_root).expanduser().resolve() if data_root is not None else DATA_ROOT
    projects_root = root / 'projects'
    root.mkdir(parents=True, exist_ok=True)
    projects_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-staging-', dir=root) as tmp:
        staging = Path(tmp) / project_id
        staging.mkdir()
        with zipfile.ZipFile(source) as archive:
            entries = _check_archive(archive)
            for entry in entries:
                dst = staging / entry.filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, dst.open('xb') as target:
                    while chunk := src.read(1024 * 1024):
                        target.write(chunk)
        manifest = _verify_staged(staging, project_id=project_id)
        (staging / 'manifest.json').unlink()
        # Atomic namespace mutation for cooperating application processes.
        with project_write_lock(root):
            destination = projects_root / project_id
            if os.path.lexists(destination):
                raise FileExistsError('Dự án đích đã tồn tại. Không ghi đè.')
            staging.rename(destination)
    return {'id': project_id, 'creative_enabled': manifest['creative_enabled'],
            'ledger_revision': manifest['ledger_revision']}
