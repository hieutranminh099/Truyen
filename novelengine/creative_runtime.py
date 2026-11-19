"""Opt-in backend integration for Creative Memory, Outline, Voice, RAG and Writer.

Creative actions commit only the sidecar, while V4 scene/summary actions commit
only story.db. A shared project lock serializes writes and consistent snapshots;
no unprotected multi-database write transaction is introduced here.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import asdict
from pathlib import Path

from .config import project_dir
from .project_state import project_state, project_write_lock
from .outline import load_outline
from .store import atomic_text, scene_revision, story_db
from .rag import find_techniques
from .creative.memory_rules import MemoryEvent, MemoryRecord, StoryPosition
from .creative.memory_storage import SQLiteMemoryStore
from .creative.outline_contract import validate_outline
from .creative.retrieval_engine import RetrievalContext, TechniqueNote
from .creative.v41_adapters import (
    LegacyMemoryMapping, adapt_voice, adapt_v4_retrieval, map_v4_memory_row, prepare_scene,
)

NOTES_FILE = 'creative-notes.json'


def _contract(project_id: str):
    return validate_outline(load_outline(project_dir(project_id) / 'outline.json')).require_contract()


def _enabled(project_id: str) -> bool:
    if not project_state(project_dir(project_id), project_id=project_id)['creative_enabled']:
        return False
    return True


def _store(project_id: str, contract=None) -> SQLiteMemoryStore:
    if not _enabled(project_id):
        raise ValueError('Creative chưa được bật cho dự án này.')
    contract = contract or _contract(project_id)
    return SQLiteMemoryStore(project_dir(project_id), project_id=project_id,
                             layout_id=contract.layout_id)


def _revisions(project_id: str, contract) -> dict[StoryPosition, int | None]:
    c = story_db(project_id)
    try:
        rows = c.execute('SELECT chapter,scene,MAX(id) AS revision '
                         'FROM scene_versions GROUP BY chapter,scene').fetchall()
        positions = {}
        for item in rows:
            try:
                key = contract.scene_position(str(item['chapter']), str(item['scene']))
            except KeyError:
                continue
            positions[key] = item['revision']
        return positions
    finally:
        c.close()


def creative_revision(project_id: str) -> int | None:
    if not _enabled(project_id):
        return None
    return _store(project_id).read().revision


def _notes(project_id: str) -> list[TechniqueNote]:
    filename = project_dir(project_id) / NOTES_FILE
    if not filename.exists():
        return []
    if filename.is_symlink() or not filename.is_file():
        raise ValueError('Creative RAG notes phải là tệp thường.')
    values = json.loads(filename.read_text(encoding='utf8'))
    if not isinstance(values, list):
        raise ValueError('Creative RAG notes phải là mảng.')
    return [TechniqueNote(**value) for value in values]


def creative_packet(project_id: str, outline: dict, ch: dict, sc: dict):
    """Return V4's (text, hints) plus the exact ledger revision used."""
    contract = validate_outline(outline).require_contract()
    ledger = _store(project_id, contract).read()
    raw_voice = (project_dir(project_id) / 'voice_bible.md').read_text(encoding='utf8')
    voice = adapt_voice(raw_voice, situation=str(sc.get('goal','')), characters=(str(sc.get('pov','')),))
    context = RetrievalContext(
        scene_type=str(sc.get('title','')),
        narrative_goal=str(sc.get('goal','')),
        genre=str(outline.get('genre','')) if isinstance(outline.get('genre'),str) else '',
        character_state=str(sc.get('emotional_arc','')),
    )
    query = ' '.join((str(sc.get('goal','')), ' '.join(sc.get('beats',[]))))[:1400]
    legacy_hits = find_techniques(project_id, query, ai=None, top_k=4)
    retrieval = adapt_v4_retrieval(context, legacy_hits, reviewed_notes=_notes(project_id))
    result = prepare_scene(
        contract, str(ch['id']), str(sc['id']), project_id=project_id,
        memory=ledger, scene_revisions=_revisions(project_id, contract),
        voice=voice, retrieval=retrieval,
    )
    packet, hints = result.as_pipeline_result()
    return packet, hints, result.memory_revision


def creative_status(project_id: str) -> dict:
    if not _enabled(project_id):
        return {'enabled': False, 'revision': None, 'items': [], 'notes': [], 'legacy_pending': []}
    with project_write_lock(project_dir(project_id)):
        contract = _contract(project_id)
        view = _store(project_id, contract).read()
        positions = _revisions(project_id, contract)
        records = {}
        for record in view.journal:
            item = records.setdefault(record.event_id, {})
            if record.event is not None:
                item.update(asdict(record.event))
            item['id'] = record.event_id
            item['status'] = view.status(record.event_id)
        stale = set()
        for event in view.approved_events():
            if event.scene_revision is None:
                continue
            source = StoryPosition(event.position.chapter, event.position.scene)
            if positions.get(source) != event.scene_revision:
                stale.add(event.event_id)
        c = story_db(project_id)
        try:
            legacy = [dict(row) for row in c.execute(
                "SELECT id,chapter,kind,subject,content FROM memory_items "
                "WHERE status='pending' AND source='model' ORDER BY id DESC LIMIT 100"
            )]
        finally:
            c.close()
        return {
            'enabled': True, 'revision': view.revision, 'layout_id': contract.layout_id,
            'items': [dict(item, stale_source=item['id'] in stale) for item in records.values()],
            'legacy_pending': legacy, 'notes': [asdict(n) for n in _notes(project_id)],
        }


def _expected(data: dict) -> int | None:
    revision = data.get('expected_revision')
    if revision is None:
        return None
    if type(revision) is not int or revision < 0:
        raise ValueError('expected_revision phải là số nguyên không âm.')
    return revision


def creative_propose(project_id: str, data: dict) -> dict:
    with project_write_lock(project_dir(project_id)):
        contract = _contract(project_id)
        store = _store(project_id, contract)
        chapter = str(data.get('chapter_id', '')).strip()
        scene = str(data.get('scene_id', '')).strip()
        if bool(chapter) != bool(scene):
            raise ValueError('Vị trí nguồn cần đủ ID chương và cảnh.')
        position = contract.scene_position(chapter, scene) if chapter else StoryPosition(0)
        source_revision = None
        if chapter:
            c = story_db(project_id)
            try:
                source_revision = scene_revision(c, chapter, scene)
            finally:
                c.close()
            if source_revision is None:
                raise ValueError('Cảnh nguồn chưa có phiên bản đã lưu. '
                                 'Không được gắn canon vào cảnh chưa viết.')
        kind, subject, value = (data.get('kind'), data.get('subject'), data.get('value'))
        if not all(isinstance(v, str) for v in (kind, subject, value)):
            raise ValueError('kind, subject và value phải là chuỗi.')
        event = MemoryEvent(
            'human:' + secrets.token_hex(12), position, kind, subject, value,
            key=str(data.get('key', '')), source='human',
            evidence=str(data.get('evidence', '')),
            scene_revision=source_revision,
        )
        revision = store.commit([MemoryRecord('propose', event.event_id, event)],
                                expected_revision=_expected(data))
        return {'id': event.event_id, 'revision': revision, 'status': 'pending'}


def creative_action(project_id: str, data: dict) -> dict:
    with project_write_lock(project_dir(project_id)):
        event_id = data.get('event_id')
        action = data.get('action')
        if not isinstance(event_id, str) or action not in ('approve', 'reject', 'undo'):
            raise ValueError('Cần ID sự kiện và hành động approve/reject/undo.')
        record = MemoryRecord(action, event_id, reason=str(data.get('reason', '')))
        store = _store(project_id)
        revision = store.commit([record], expected_revision=_expected(data))
        return {'id': event_id, 'revision': revision, 'status': store.read().status(event_id)}


def creative_import_model(project_id: str, data: dict) -> dict:
    """Stage an existing V4 proposal for new independent Creative approval."""
    with project_write_lock(project_dir(project_id)):
        contract = _contract(project_id)
        store = _store(project_id, contract)
        row_id = data.get('id')
        if type(row_id) is not int or row_id <= 0:
            raise ValueError('Cần ID đề xuất model dương.')
        c = story_db(project_id)
        try:
            row = c.execute('SELECT * FROM memory_items WHERE id=? AND source="model" AND status="pending"',
                            (row_id,)).fetchone()
            if row is None:
                raise ValueError('Không còn đề xuất V4 chờ duyệt.')
            chapter = row['chapter']
            scene_id = str(data.get('scene_id', '')).strip() or None
            rev = scene_revision(c, chapter, scene_id) if chapter and scene_id else None
        finally:
            c.close()
        mapping = LegacyMemoryMapping(
            subject=str(data.get('subject', row['subject'] or f'v4-{row_id}')),
            key=str(data.get('key', '')),
            value=data.get('value'),
            scene_id=scene_id, scene_revision=rev,
            evidence=str(data.get('evidence', '')),
        )
        record = map_v4_memory_row(row, contract, mapping)
        revision = store.commit([record], expected_revision=_expected(data))
        return {'id': record.event_id, 'revision': revision, 'status': store.read().status(record.event_id)}


def creative_note(project_id: str, data: dict) -> dict:
    with project_write_lock(project_dir(project_id)):
        _store(project_id)
        notes = _notes(project_id)
        action = data.get('action', 'add')
        if action == 'delete':
            target = data.get('note_id')
            if not isinstance(target, str):
                raise ValueError('note_id không hợp lệ.')
            notes = [note for note in notes if note.note_id != target]
        elif action == 'add':
            note = TechniqueNote(
                'curated:' + secrets.token_hex(12),
                str(data.get('name', '')),
                purpose=str(data.get('purpose', '')),
                expected_effect=str(data.get('expected_effect', '')),
                limitations=str(data.get('limitations', '')),
                reviewed=True,
            )
            notes.append(note)
        else:
            raise ValueError('Hành động ghi chú không hợp lệ.')
        atomic_text(project_dir(project_id) / NOTES_FILE,
                    json.dumps([asdict(note) for note in notes], ensure_ascii=False, indent=2))
        return {'count': len(notes)}
