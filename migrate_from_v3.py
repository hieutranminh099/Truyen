"""Import the prior Novel_Engine_V3_Mobile/project into a NEW V4 project (no source writes).

Dry-run by default:
    python migrate_from_v3.py "C:\\AI\\Novel_Engine_V3_Mobile" --id truyen-cu
Apply:
    python migrate_from_v3.py "C:\\AI\\Novel_Engine_V3_Mobile" --id truyen-cu --apply
Include source books only if you confirm usage rights:
    ... --apply --confirm-rights
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from novelengine.config import project_dir
from novelengine.outline import parse_outline
from novelengine.store import create_project, story_db, save_scene, now, atomic_text
from novelengine.rag import import_document


def table_exists(c,name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())


def migrate(source: Path, ident: str, *, apply=False, confirm_rights=False):
    source=source.expanduser().resolve()
    old=(source/'project' if (source/'project').is_dir() else source)
    outline_file=old/'outline.json';db_file=old/'series.db'
    if not outline_file.is_file() or not db_file.is_file():
        raise FileNotFoundError('Không tìm thấy project/outline.json và project/series.db của V3 trong thư mục cung cấp')
    outline=parse_outline(outline_file.read_text(encoding='utf-8-sig'))
    c=sqlite3.connect(f'file:{db_file.as_posix()}?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    counts={name:c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] if table_exists(c,name) else 0
            for name in ('scenes','memory','canon','library')}
    result={'source':str(old),'destination_id':ident,'title':outline.get('title','Truyện V3'), 'counts':counts,
            'library_will_copy':bool(confirm_rights),'dry_run':not apply}
    if not apply:c.close();return result
    dest=project_dir(ident)
    if dest.exists():
        c.close();raise FileExistsError(f'Dự án đích đã tồn tại: {dest}. Hãy dùng ID khác.')
    create_project(str(outline.get('title','Truyện V3')), ident)
    atomic_text(dest/'outline.json',json.dumps(outline,ensure_ascii=False,indent=2))
    d=story_db(ident)
    try:
        if table_exists(c,'scenes'):
            for r in c.execute('SELECT * FROM scenes ORDER BY rowid'):
                if r['draft']:save_scene(d,r['chapter'],r['scene'],'draft',r['draft'])
                if r['review']:save_scene(d,r['chapter'],r['scene'],'review',review=r['review'])
                if r['edited']:save_scene(d,r['chapter'],r['scene'],'edited',r['edited'])
        if table_exists(c,'memory'):
            for r in c.execute('SELECT * FROM memory ORDER BY rowid'):
                d.execute('INSERT OR REPLACE INTO summaries(chapter,body,status,updated) VALUES(?,?,?,?)',
                          (str(r['chapter']),str(r['summary']),'approved' if r['approved'] else 'pending',now()))
        if table_exists(c,'canon'):
            for r in c.execute('SELECT * FROM canon ORDER BY rowid'):
                d.execute('''INSERT INTO memory_items(kind,subject,content,source,status,created)
                             VALUES('fact','',?,'migration-v3','approved',?)''',(str(r['fact']),now()))
        d.commit()
    finally:d.close()
    # No automatic license claims: importing copyrighted source requires --confirm-rights.
    if confirm_rights and table_exists(c,'library'):
        for r in c.execute('SELECT * FROM library'):
            body=str(r['body'] or '')
            if not body:continue
            try:
                doc=import_document(ident,str(r['name']),body.encode('utf8'),
                                    'Chuyển từ V3 — người dùng xác nhận có quyền sử dụng',True)
                if r['analysis']:
                    d=story_db(ident)
                    try:
                        tech=json.dumps({'technique':str(r['analysis'])[:850],
                             'when_to_use':'Ghi chú V3 cần xem xét lại','pitfall':'Chưa kiểm định','example_new':''},ensure_ascii=False)
                        d.execute('UPDATE chunks SET technique=? WHERE doc_id=? AND ordinal=0',(tech,doc['id']));d.commit()
                    finally:d.close()
            except ValueError as e:
                result.setdefault('warnings',[]).append(f'{r["name"]}: {e}')
    c.close()
    # Re-export migrated story chapters; preserve the original V3 files in place.
    from novelengine.store import export_chapter
    for ch in outline['chapters']:export_chapter(ident,ch)
    result['dry_run']=False
    return result


def main():
    p=argparse.ArgumentParser(description='Migrate Novel Engine V3 Mobile to V4 (dry-run first).')
    p.add_argument('source',help='V3 directory or V3/project directory')
    p.add_argument('--id',required=True,help='New project ID: ASCII letters, digits and dashes')
    p.add_argument('--apply',action='store_true',help='Execute import; source will not be modified')
    p.add_argument('--confirm-rights',action='store_true',help='I have rights to import the V3 library books')
    args=p.parse_args()
    print(json.dumps(migrate(Path(args.source),args.id,apply=args.apply,confirm_rights=args.confirm_rights),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
