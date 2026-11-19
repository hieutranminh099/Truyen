"""Persistent, sequential jobs. Pause/cancel only at stable scene/chunk boundaries."""
from __future__ import annotations
import json
import threading
import sqlite3
from .store import queue_db, story_db, now
from .config import DATA_ROOT, project_dir
from .project_state import project_write_lock
from .outline import load_outline
from .pipeline import run_series, process_scene
from .rag import analyze_document, build_embeddings
from .ai import json_from_text


class JobInterrupted(Exception):
    def __init__(self, state, chapter_id=None):
        super().__init__(state)
        self.state = state
        self.chapter_id = chapter_id


class JobQueue:
    def __init__(self,ai,poll=.5):
        self.ai=ai;self.poll=poll;self.stop=threading.Event();self.thread=None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        # Keep the process lock on a separate SQLite file so web requests can
        # continue updating the queue during an Ollama request.
        lock = sqlite3.connect(DATA_ROOT / 'worker-lock.db', timeout=0, check_same_thread=False)
        try:
            try:
                lock.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                if 'locked' in str(exc).lower():
                    raise RuntimeError('Hàng đợi đang chạy trong một phiên Novel Engine khác.') from exc
                raise
            c = queue_db()
            try:
                with c:
                    c.execute(
                        "UPDATE jobs SET state='queued',updated=? "
                        "WHERE state IN ('running','waiting_approval')",
                        (now(),),
                    )
            finally:
                c.close()
            self.stop.clear()
            self.thread = threading.Thread(
                target=self._run_worker, args=(lock,), daemon=True, name='NovelJobWorker',
            )
            self.thread.start()
        except BaseException:
            lock.close()
            raise

    def _run_worker(self, lock):
        try:
            self._loop()
        finally:
            lock.close()

    def shutdown(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=3)

    def submit(self,project_id,kind,payload=None):
        if kind not in ('series','analyze','embed','rewrite','plan'):
            raise ValueError('Loại tác vụ không hợp lệ')
        c=queue_db()
        try:
            c.execute('BEGIN IMMEDIATE')
            if kind == 'series':
                self._require_no_active_series(c, project_id)
            cur=c.execute('INSERT INTO jobs(project_id,kind,payload,created,updated) VALUES(?,?,?,?,?)',
                          (project_id,kind,json.dumps(payload or {},ensure_ascii=False),now(),now()))
            c.commit();return cur.lastrowid
        finally:c.close()

    def _require_no_active_series(self, c, project_id, excluded_id=0):
        active = c.execute(
            "SELECT 1 FROM jobs WHERE project_id=? AND id!=? AND kind='series' "
            "AND state IN ('queued','running','paused','waiting_approval')",
            (project_id, excluded_id),
        ).fetchone()
        if active:
            raise ValueError('Dự án đã có tác vụ viết đang chờ/chạy; hãy tiếp tục tác vụ cũ.')

    def list(self,project_id=None):
        c=queue_db()
        try:
            if project_id:rows=c.execute('SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 40',(project_id,)).fetchall()
            else:rows=c.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 50').fetchall()
            return [dict(r) for r in rows]
        finally:c.close()

    def command(self,id,cmd):
        c=queue_db()
        try:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
            if not r:raise ValueError('Không tìm thấy tác vụ')
            if cmd=='pause' and r['state'] in ('running','queued'):
                c.execute('UPDATE jobs SET pause_requested=1,updated=? WHERE id=?',(now(),id))
            elif cmd=='cancel' and r['state'] in ('running','queued','paused','waiting_approval'):
                if r['state']=='running':c.execute('UPDATE jobs SET cancel_requested=1,updated=? WHERE id=?',(now(),id))
                else:c.execute("UPDATE jobs SET state='canceled',updated=? WHERE id=?",(now(),id))
            elif cmd=='resume' and r['state'] in ('paused','failed'):
                if r['kind'] == 'series':
                    self._require_no_active_series(c, r['project_id'], id)
                c.execute("UPDATE jobs SET state='queued',pause_requested=0,cancel_requested=0,error='',updated=? WHERE id=?",(now(),id))
            else:raise ValueError('Không thể áp dụng hành động này vào trạng thái hiện tại')
            c.commit()
        finally:c.close()

    def wake_approval(self,project_id):
        c=queue_db()
        try:
            c.execute("UPDATE jobs SET state='queued',updated=? WHERE project_id=? AND state='waiting_approval'",(now(),project_id))
            c.commit()
        finally:c.close()

    def _set(self,id,**values):
        c=queue_db()
        try:
            values['updated']=now()
            cols=', '.join(f'{k}=?' for k in values)
            c.execute(f'UPDATE jobs SET {cols} WHERE id=?',(*values.values(),id));c.commit()
        finally:c.close()

    def _checkpoint(self,id,typ,chapter_idx,scene_idx,msg, *, chapter_id=None):
        self._set(id,progress=json.dumps({'chapter_index':chapter_idx,'scene_index':scene_idx,'message':msg},ensure_ascii=False))
        if typ not in ('boundary','waiting'):return
        c=queue_db()
        try:
            r=c.execute('SELECT pause_requested,cancel_requested FROM jobs WHERE id=?',(id,)).fetchone()
        finally:c.close()
        if r['cancel_requested']:raise JobInterrupted('canceled')
        if r['pause_requested']:raise JobInterrupted('paused')
        if typ=='waiting':
            raise JobInterrupted('waiting_approval', chapter_id)

    def _loop(self):
        while not self.stop.is_set():
            c=queue_db()
            try:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
                if row:
                    c.execute("UPDATE jobs SET state='running',updated=? WHERE id=?",(now(),row['id']))
                    c.commit()
            finally:c.close()
            if not row:
                self.stop.wait(self.poll);continue
            job=dict(row)
            try:
                self._execute(job)
                self._set(job['id'],state='done',progress='Đã hoàn tất')
            except JobInterrupted as e:
                self._set(job['id'],state=e.state)
                if e.chapter_id is not None:
                    # A browser can approve after the summary is committed but
                    # before the worker parks. Recheck the now-visible wait state.
                    c = story_db(job['project_id'])
                    try:
                        approved = c.execute(
                            "SELECT 1 FROM summaries WHERE chapter=? AND status='approved'",
                            (e.chapter_id,),
                        ).fetchone()
                    finally:
                        c.close()
                    if approved:
                        self.wake_approval(job['project_id'])
            except Exception as e:
                self._set(job['id'],state='failed',error=f'{type(e).__name__}: {e}'[:1300])

    def _execute(self,job):
        id=job['id'];project=job['project_id'];payload=json.loads(job['payload'])
        def checkpoint(typ, chapter_index, scene_index, message, **kwargs):
            self._checkpoint(id, typ, chapter_index, scene_index, message, **kwargs)

        self._checkpoint(id,'boundary',0,0,'Khởi động tác vụ')
        if job['kind']=='series':
            run_series(project,self.ai,cloud_critic=bool(payload.get('cloud_critic')),
                       use_embeddings=bool(payload.get('semantic')),checkpoint=checkpoint)
        elif job['kind']=='analyze':
            doc_id=int(payload['doc_id']);limit=int(payload.get('limit',20))
            def cp(n,total):self._checkpoint(id,'boundary',0,n,f'Phân tích {n}/{total} đoạn')
            analyze_document(project,doc_id,self.ai,limit=limit,checkpoint=cp)
        elif job['kind']=='embed':
            def cp(n,total):self._checkpoint(id,'boundary',0,n,f'Tạo embedding {n}/{total}')
            build_embeddings(project,self.ai,limit=int(payload.get('limit',30)),checkpoint=cp)
        elif job['kind']=='rewrite':
            ch_id=str(payload['chapter']);sc_id=str(payload['scene'])
            outline=load_outline(project_dir(project)/'outline.json')
            ch=next((c for c in outline['chapters'] if c['id']==ch_id),None)
            sc=next((s for s in ch['scenes'] if s['id']==sc_id),None) if ch else None
            if not sc:raise ValueError('Không tìm thấy cảnh trong dàn ý')
            process_scene(
                project, outline, ch, sc, self.ai, rewrite=True,
                progress=lambda message: self._checkpoint(id, 'progress', 0, 0, message),
                before_save=lambda: self._checkpoint(id, 'boundary', 0, 0, 'Đang lưu bản viết lại'),
            )
        elif job['kind']=='plan':
            premise=str(payload.get('premise','')).strip()
            if not premise:raise ValueError('Thiếu ý tưởng dàn ý')
            cloud=bool(payload.get('cloud',False))
            chapters=max(1,min(8,int(payload.get('chapters',2))))
            system=('Bạn là kiến trúc sư tiểu thuyết Việt Nam. Xuất CHỈ JSON object với title,genre,premise,world,characters,chapters. '
                    'chapters là mảng gồm id,title,purpose,scenes; mỗi scene gồm id,title,pov,goal,beats là mảng chuỗi, '
                    'must_include (mảng),forbidden (mảng),target_words (số). Mỗi chương gồm 2-3 cảnh. '
                    'Chú ý tính nhân quả, chiều sâu nhân vật, không sáo mòn và bí mật chưa hé lộ.')
            raw=self.ai.chat(system,f'Ý TƯỞNG: {premise[:4000]}\nTạo {chapters} chương đầu tiên, mỗi chương 2 cảnh.',
                             role='planner',cloud=cloud,temperature=.65,max_tokens=3000,structured=True)
            obj=json_from_text(raw)
            from .outline import parse_outline
            from .store import atomic_text
            obj=parse_outline(obj)
            # Do not overwrite an existing approved outline; save as candidate for review.
            self._checkpoint(id, 'boundary', 0, 0, 'Đang lưu dàn ý đề xuất')
            path=project_dir(project)/'outline_candidate.json'
            with project_write_lock(project_dir(project)):
                atomic_text(path,json.dumps(obj,ensure_ascii=False,indent=2))
        else:raise ValueError('Loại tác vụ không hỗ trợ')
