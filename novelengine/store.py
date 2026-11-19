"""One SQLite database per story, central persistent job queue, safe atomic exports."""
from __future__ import annotations
import datetime as dt
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from .config import DATA_ROOT, PROJECTS, project_dir, slug, validate_project_id
from .outline import sample_outline, parse_outline, load_outline


def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def conn(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA journal_mode=WAL')
    return c


SCHEMA = '''
CREATE TABLE IF NOT EXISTS scenes (
 chapter TEXT NOT NULL, scene TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'new',
 draft TEXT NOT NULL DEFAULT '', edited TEXT NOT NULL DEFAULT '', review TEXT NOT NULL DEFAULT '',
 updated TEXT NOT NULL, PRIMARY KEY(chapter, scene)
);
CREATE TABLE IF NOT EXISTS scene_versions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, chapter TEXT NOT NULL, scene TEXT NOT NULL,
 stage TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scene_versions_scene ON scene_versions(chapter, scene, id);
CREATE TABLE IF NOT EXISTS summaries (
 chapter TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '',
 content TEXT NOT NULL, chapter TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'manual',
 status TEXT NOT NULL DEFAULT 'pending', visibility TEXT NOT NULL DEFAULT 'public', created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_items(status,kind);
CREATE TABLE IF NOT EXISTS memory_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, action TEXT NOT NULL, stamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, license TEXT NOT NULL,
 sha256 TEXT NOT NULL UNIQUE, byte_size INTEGER NOT NULL, imported TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, body TEXT NOT NULL, technique TEXT NOT NULL DEFAULT '',
 embedding TEXT NOT NULL DEFAULT '', UNIQUE(doc_id,ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(body,technique,content='chunks',content_rowid='id',tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid,body,technique) VALUES (new.id,new.body,new.technique); END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts,rowid,body,technique) VALUES('delete',old.id,old.body,old.technique); END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts,rowid,body,technique) VALUES('delete',old.id,old.body,old.technique);
  INSERT INTO chunks_fts(rowid,body,technique) VALUES(new.id,new.body,new.technique); END;
CREATE TABLE IF NOT EXISTS activity (
 id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, message TEXT NOT NULL, created TEXT NOT NULL
);
'''

QUEUE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued', progress TEXT NOT NULL DEFAULT '',
 pause_requested INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state,id);
'''


def queue_db():
    c = conn(DATA_ROOT / 'queue.db')
    c.executescript(QUEUE_SCHEMA)
    c.commit()
    return c


def story_db(project_id: str):
    path = project_dir(project_id) / 'story.db'
    if not path.parent.is_dir():
        raise FileNotFoundError('Chưa tồn tại dự án: ' + project_id)
    c = conn(path)
    c.executescript(SCHEMA)
    # Upgrade early V4 preview DBs in place without data loss.
    cols={r[1] for r in c.execute('PRAGMA table_info(memory_items)')}
    if 'visibility' not in cols:
        c.execute("ALTER TABLE memory_items ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
    c.commit()
    return c


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='._novel_')
    try:
        import os
        with os.fdopen(fd, 'w', encoding='utf8', newline='\n') as f:
            f.write(text)
            f.flush(); os.fsync(f.fileno())
        Path(tmp).replace(path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def create_project(title: str, project_id: str = '') -> dict:
    from .project_state import project_write_lock, save_project_state
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with project_write_lock(DATA_ROOT):
        PROJECTS.mkdir(parents=True, exist_ok=True)
        ident = slug(project_id or title)
        d = project_dir(ident)
        if d.exists():
            raise FileExistsError('Dự án đã tồn tại: ' + ident)
        d.mkdir(parents=True)
        (d / 'exports').mkdir()
        (d / 'backups').mkdir()
        outline = sample_outline()
        outline['title'] = title.strip()[:140] or outline['title']
        atomic_text(d / 'outline.json', json.dumps(outline, ensure_ascii=False, indent=2))
        atomic_text(d / 'voice_bible.md', '# Hồ sơ giọng văn\n\nĐiểm nhìn giới hạn.\nLời thoại giàu ẩn ý; không giải thích cảm xúc quá mức.\nĐể hành vi và đồ vật mang ý nghĩa.\nKhông sáo ngữ, không tóm tắt dàn ý thành văn xuôi.\n')
        save_project_state(d, {'format': 1, 'project_id': ident, 'creative_enabled': False})
        c = story_db(ident)
        c.close()
        return {'id': ident, 'title': outline['title']}

def bootstrap():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS.mkdir(parents=True, exist_ok=True)
    c = queue_db()
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            if not any(p.is_dir() for p in PROJECTS.iterdir()):
                create_project('Người Giữ Những Mùa Mưa', 'demo')
    finally:
        c.close()


def projects():
    out = []
    for d in sorted(PROJECTS.iterdir()):
        if not d.is_dir() or not (d / 'story.db').is_file():
            continue
        try:
            title = load_outline(d / 'outline.json').get('title', d.name)
            out.append({'id': d.name, 'title': str(title)})
        except Exception:
            out.append({'id': d.name, 'title': d.name})
    return out


def save_outline(project_id: str, outline: dict | str):
    from .project_state import project_write_lock
    with project_write_lock(project_dir(project_id)):
        out = parse_outline(outline)
        d = project_dir(project_id)
        if not d.is_dir(): raise FileNotFoundError('Dự án không tồn tại')
        atomic_text(d / 'outline.json', json.dumps(out, ensure_ascii=False, indent=2))
        return out


def save_scene(c, chapter, scene, stage, text='', review=None, *, commit=True):
    chapter, scene = str(chapter), str(scene)
    stamp = now()
    c.execute('''INSERT OR IGNORE INTO scenes(chapter,scene,updated) VALUES(?,?,?)''', (chapter,scene,stamp))
    if stage == 'draft':
        c.execute('UPDATE scenes SET draft=?,stage=?,updated=? WHERE chapter=? AND scene=?',(text, stage,stamp,chapter,scene))
    elif stage == 'edited':
        c.execute('UPDATE scenes SET edited=?,stage=?,updated=? WHERE chapter=? AND scene=?',(text,stage,stamp,chapter,scene))
    elif stage == 'review':
        c.execute('UPDATE scenes SET review=?,stage=?,updated=? WHERE chapter=? AND scene=?',(review if review is not None else text,stage,stamp,chapter,scene))
    else:
        raise ValueError('stage không hợp lệ')
    if stage in ('draft','edited'):
        c.execute('INSERT INTO scene_versions(chapter,scene,stage,text,created) VALUES(?,?,?,?,?)',(chapter,scene,stage,text,stamp))
    if commit:
        c.commit()


def scene_revision(c, chapter, scene):
    return c.execute(
        'SELECT MAX(id) FROM scene_versions WHERE chapter=? AND scene=?',
        (chapter, scene),
    ).fetchone()[0]


def supersede_chapter_model_memory(c, chapter):
    """Remove stale machine proposals from Writer context without erasing approvals.

    An approved machine fact becomes 'stale' and leaves an audit trail for
    explicit human review. Undecided proposals can be revoked. Call inside
    the same caller-owned transaction as the scene/summary update.
    """
    approved_ids = [
        row['id'] for row in c.execute(
            "SELECT id FROM memory_items WHERE chapter=? AND source='model' AND status='approved'",
            (chapter,),
        )
    ]
    stamp = now()
    c.executemany(
        "INSERT INTO memory_audit(item_id,action,stamp) VALUES(?,'stale',?)",
        ((item_id, stamp) for item_id in approved_ids),
    )
    c.execute(
        "UPDATE memory_items SET status='stale' "
        "WHERE chapter=? AND source='model' AND status='approved'",
        (chapter,),
    )
    c.execute(
        "UPDATE memory_items SET status='revoked' "
        "WHERE chapter=? AND source='model' AND status='pending'",
        (chapter,),
    )


def invalidate_chapter_memory(c, chapter):
    c.execute("UPDATE summaries SET status='stale',updated=? WHERE chapter=?", (now(), chapter))
    supersede_chapter_model_memory(c, chapter)


def get_scene(c, chapter, scene):
    row = c.execute('SELECT * FROM scenes WHERE chapter=? AND scene=?',(str(chapter),str(scene))).fetchone()
    return dict(row) if row else None


def export_chapter(project_id: str, chapter: dict):
    from .project_state import project_write_lock
    with project_write_lock(project_dir(project_id)):
        c = story_db(project_id)
        lines = ['# ' + str(chapter.get('title', chapter['id']))]
        for sc in chapter['scenes']:
            r = get_scene(c,chapter['id'],sc['id'])
            if r and (r['edited'] or r['draft']):
                lines.extend(['', '## ' + str(sc.get('title',sc['id'])), '', r['edited'] or r['draft'], ''])
        c.close()
        d = project_dir(project_id) / 'exports'
        path = d / ('chapter_' + re.sub(r'[^a-zA-Z0-9_-]', '_', str(chapter['id'])) + '.md')
        atomic_text(path, '\n'.join(lines).rstrip()+'\n')
        return path
    

def restore_version(project_id: str, version_id: int):
    c = story_db(project_id)
    try:
        with c:
            v = c.execute('SELECT * FROM scene_versions WHERE id=?', (version_id,)).fetchone()
            if not v:
                raise ValueError('Không tìm thấy phiên bản')
            # A restore creates a new version, preserving the intervening history.
            save_scene(c, v['chapter'], v['scene'], 'edited', v['text'], commit=False)
            invalidate_chapter_memory(c, v['chapter'])
    finally:
        c.close()
    outline=load_outline(project_dir(project_id)/'outline.json')
    for ch in outline['chapters']:
        if str(ch['id']) == str(v['chapter']): export_chapter(project_id,ch); break
    return {'chapter': v['chapter'], 'scene': v['scene']}


def update_memory(c, item_id: int, action: str):
    valid={'approve':'approved','reject':'rejected','revoke':'revoked'}
    if action not in valid: raise ValueError('Hành động không hợp lệ')
    item = c.execute('SELECT id,status FROM memory_items WHERE id=?',(item_id,)).fetchone()
    if not item: raise ValueError('Không tìm thấy mục trí nhớ')
    if item['status'] == valid[action]: return
    c.execute('UPDATE memory_items SET status=? WHERE id=?',(valid[action],item_id))
    c.execute('INSERT INTO memory_audit(item_id,action,stamp) VALUES(?,?,?)',(item_id,action,now()))
    c.commit()
