"""Run with python -m unittest discover -s tests -v. No Ollama or external API required."""
import os
import tempfile
TEST_ROOT=tempfile.TemporaryDirectory(prefix='novel_engine_test_')
os.environ['NOVEL_DATA_DIR']=TEST_ROOT.name
import io
import json
import time
import unittest
import urllib.error
import urllib.request
import zipfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from novelengine.config import Settings, project_dir
from novelengine.store import (bootstrap,create_project,story_db,queue_db,save_scene,get_scene,restore_version,update_memory,export_chapter,now)
from novelengine.outline import sample_outline,parse_outline,load_outline
from novelengine.pipeline import process_scene,summarize_chapter,run_series,scene_packet
from novelengine.rag import import_document,search_library,analyze_document,build_embeddings,find_techniques,epub_text
from novelengine.jobs import JobQueue,JobInterrupted
from novelengine.server import NovelApp,make_handler


class FakeAI:
    def __init__(self):
        self.settings=type('S',(),{'ctx':4096,'tokens':1250,'model':'fake-writer'})()
        self.calls=[]
    def chat(self,system,user,**opts):
        self.calls.append((system[:30],opts.get('role'),opts.get('cloud')))
        role=opts.get('role')
        if role=='planner':return json.dumps(sample_outline(),ensure_ascii=False)
        if role=='analyzer':return json.dumps({'technique':'Ẩn cảm xúc bằng hành động nhỏ','when_to_use':'Khi phản bội','pitfall':'Giải thích quá rõ','example_new':'Một chiếc cốc vỡ'},ensure_ascii=False)
        if role=='summary':return json.dumps({'summary':'An trở về thị trấn và nghe tiếng chuông.',
                  'proposals':[{'kind':'fact','subject':'An','content':'An nghe tiếng chuông gỉ bên bến đò.'}]},ensure_ascii=False)
        if role=='critic':return json.dumps({'critical':[],'style':[],'missing':[],'strengths':['nhịp đều'],'fixes':[]},ensure_ascii=False)
        if role=='editor':
            required = 'mẩu giấy không có tên' if 'mẩu giấy không có tên' in user else 'chuông đồng gỉ'
            return f'Cô nắm {required}, lặng lẽ bước qua bến đò. '*40
        if role=='roleplay':return 'Tôi sẽ không tiết lộ bí mật khi chưa có lý do.'
        return 'An nghe tiếng chuông đồng gỉ từ phía bến đò. '*50
    def embed(self,text):return [0.3,0.5,0.7]


class Base(unittest.TestCase):
    counter=0
    @classmethod
    def setUpClass(cls):bootstrap()
    def setUp(self):
        Base.counter+=1
        self.pid=f'test-{Base.counter:02d}'
        create_project('Thử nghiệm truyện',self.pid)
        self.ai=FakeAI()
        self.outline=load_outline(project_dir(self.pid)/'outline.json')


class OutlineAndStoreTests(Base):
    def test_schema_validation(self):
        self.assertEqual(len(parse_outline(sample_outline())['chapters']),2)
        sample=sample_outline();sample['chapters'][0]['scenes'][1]['id']='01'
        with self.assertRaises(ValueError):parse_outline(sample)
        sample=sample_outline();sample['chapters'][0]['scenes'][0]['beats']=[]
        with self.assertRaises(ValueError):parse_outline(sample)

    def test_scene_checkpoint_and_restore(self):
        ch=self.outline['chapters'][0];sc=ch['scenes'][0]
        r=process_scene(self.pid,self.outline,ch,sc,self.ai)
        self.assertFalse(r['skipped'])
        self.assertEqual(process_scene(self.pid,self.outline,ch,sc,self.ai),{'skipped':True})
        c=story_db(self.pid)
        versions=list(c.execute('SELECT id FROM scene_versions ORDER BY id'))
        self.assertEqual(len(versions),2)
        c.execute('INSERT INTO summaries(chapter,body,status,updated) VALUES(?,?,?,?)',('001','abc','approved',now()))
        c.execute("INSERT INTO memory_items(kind,subject,content,chapter,source,status,created) VALUES('fact','An','ABC','001','model','approved',?)",(now(),))
        c.commit();c.close()
        restore_version(self.pid,versions[0]['id'])
        c=story_db(self.pid)
        self.assertEqual(c.execute('SELECT status FROM summaries WHERE chapter="001"').fetchone()[0],'stale')
        self.assertEqual(c.execute('SELECT status FROM memory_items').fetchone()[0],'stale')
        self.assertEqual(c.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0],3)
        c.close()

    def test_private_knowledge_not_shown_to_other_pov(self):
        c=story_db(self.pid)
        c.execute("INSERT INTO memory_items(kind,subject,content,status,visibility,created) VALUES('knowledge','Linh','MAT_MA_BI_MAT','approved','private',?)",(now(),))
        c.execute("INSERT INTO memory_items(kind,subject,content,status,visibility,created) VALUES('fact','Thị trấn','Mưa kéo dài','approved','public',?)",(now(),))
        c.commit();c.close()
        ch=self.outline['chapters'][0];sc=ch['scenes'][0]
        pkt,_=scene_packet(self.pid,self.outline,ch,sc)
        self.assertNotIn('MAT_MA_BI_MAT',pkt)
        self.assertIn('Mưa kéo dài',pkt)
        sc=dict(sc,pov='Linh')
        pkt,_=scene_packet(self.pid,self.outline,ch,sc)
        self.assertIn('MAT_MA_BI_MAT',pkt)

    def test_summary_requires_manual_approval(self):
        ch=self.outline['chapters'][0]
        for sc in ch['scenes']:process_scene(self.pid,self.outline,ch,sc,self.ai)
        self.assertEqual(summarize_chapter(self.pid,ch,self.ai),'pending')
        c=story_db(self.pid)
        self.assertEqual(c.execute('SELECT status FROM summaries').fetchone()[0],'pending')
        item=c.execute('SELECT id,status FROM memory_items').fetchone()
        self.assertEqual(item['status'],'pending')
        update_memory(c,item['id'],'approve')
        self.assertEqual(c.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],1)
        update_memory(c,item['id'],'revoke')
        self.assertEqual(c.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],2)
        c.close()

    def test_summary_drops_result_if_scene_changes_during_generation(self):
        chapter = self.outline['chapters'][0]
        for scene in chapter['scenes']:
            process_scene(self.pid, self.outline, chapter, scene, self.ai)
        original_chat = self.ai.chat

        def concurrent_chat(system, user, **options):
            c = story_db(self.pid)
            try:
                save_scene(c, chapter['id'], chapter['scenes'][0]['id'], 'edited',
                           'Bản thảo mới được lưu trong lúc tạo tóm tắt.')
            finally:
                c.close()
            return original_chat(system, user, **options)

        self.ai.chat = concurrent_chat
        with self.assertRaisesRegex(RuntimeError, 'Chương đã thay đổi'):
            summarize_chapter(self.pid, chapter, self.ai)
        c = story_db(self.pid)
        try:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM summaries').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM memory_items').fetchone()[0], 0)
        finally:
            c.close()


class LibraryTests(Base):
    def test_import_rights_duplicates_and_rag(self):
        raw=('Tôi nhìn thấy một người im lặng.\n\n'+'Anh ta cầm chiếc ô trong bóng tối.\n\n')*12
        with self.assertRaises(ValueError):import_document(self.pid,'a.txt',raw.encode(),'tự viết',False)
        d=import_document(self.pid,'a.txt',raw.encode(),'Tác phẩm tự viết',True)
        self.assertGreater(d['chunks'],0)
        self.assertTrue(import_document(self.pid,'a.txt',raw.encode(),'Tác phẩm tự viết',True)['duplicate'])
        self.assertEqual(len(search_library(self.pid)),1)
        n=analyze_document(self.pid,d['id'],self.ai,limit=100)
        self.assertEqual(n,d['chunks'])
        k=build_embeddings(self.pid,self.ai,limit=100)
        self.assertEqual(k,n)
        hits=find_techniques(self.pid,'cảm xúc phản bội hành động',self.ai,top_k=2)
        self.assertGreater(len(hits),0)
        self.assertIn('Ẩn cảm xúc',hits[0]['technique'])
        self.assertNotIn('Tôi nhìn thấy',hits[0]['technique'])

    def test_epub_extract_spine(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
            z.writestr('OPS/book.opf','<package><manifest><item id="s1" href="c1.xhtml"/></manifest><spine><itemref idref="s1"/></spine></package>')
            z.writestr('OPS/c1.xhtml','<html><body><p>Chương một</p><p>Tình tiết sâu sắc</p></body></html>')
        self.assertIn('Chương một',epub_text(b.getvalue()))


class JobTests(Base):
    def test_series_pauses_for_approval_then_resumes(self):
        j=JobQueue(self.ai,poll=.03);j.start()
        try:
            jid=j.submit(self.pid,'series',{})
            state=self.wait(j,jid,'waiting_approval')
            self.assertEqual(state,'waiting_approval')
            c=story_db(self.pid);c.execute("UPDATE summaries SET status='approved' WHERE chapter='001'");c.commit();c.close()
            j.wake_approval(self.pid)
            state=self.wait(j,jid,'waiting_approval',want_chapter='002')
            self.assertEqual(state,'waiting_approval')
            c=story_db(self.pid);c.execute("UPDATE summaries SET status='approved' WHERE chapter='002'");c.commit();c.close()
            j.wake_approval(self.pid)
            self.assertEqual(self.wait(j,jid,'done'),'done')
            c=story_db(self.pid)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM scenes WHERE edited!=""').fetchone()[0],3)
            c.close()
            self.assertTrue((project_dir(self.pid)/'exports'/'chapter_002.md').exists())
        finally:j.shutdown()

    def wait(self,j,jid,expected,want_chapter=None,timeout=9):
        end=time.time()+timeout
        while time.time()<end:
            row=next(x for x in j.list(self.pid) if x['id']==jid)
            if row['state']=='failed' and expected!='failed':self.fail('Job failed: '+row['error'])
            if row['state']==expected:
                if want_chapter:
                    c=story_db(self.pid);has=bool(c.execute('SELECT 1 FROM summaries WHERE chapter=?',(want_chapter,)).fetchone());c.close()
                    if not has: time.sleep(.02);continue
                return row['state']
            time.sleep(.03)
        self.fail(f'Timed out waiting for {expected}: {j.list(self.pid)}')

    def test_early_approval_is_not_lost(self):
        queue = JobQueue(self.ai, poll=.03)
        original_checkpoint = queue._checkpoint

        def checkpoint(job_id, typ, chapter_index, scene_index, message, **kwargs):
            if typ == 'waiting':
                chapter_id = self.outline['chapters'][chapter_index]['id']
                c = story_db(self.pid)
                try:
                    c.execute("UPDATE summaries SET status='approved' WHERE chapter=?", (chapter_id,))
                    c.commit()
                finally:
                    c.close()
                queue.wake_approval(self.pid)
            return original_checkpoint(job_id, typ, chapter_index, scene_index, message, **kwargs)

        queue._checkpoint = checkpoint
        job_id = queue.submit(self.pid, 'series')
        queue.start()
        try:
            self.wait(queue, job_id, 'done', timeout=20)
        finally:
            queue.shutdown()

    def test_bootstrap_does_not_requeue_live_worker(self):
        entered = threading.Event()
        release = threading.Event()
        original_chat = self.ai.chat

        def slow_chat(system, user, **options):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('Test worker did not receive release')
            return original_chat(system, user, **options)

        self.ai.chat = slow_chat
        queue = JobQueue(self.ai, poll=.03)
        job_id = queue.submit(self.pid, 'plan', {'premise': 'Một đêm mưa'})
        queue.start()
        try:
            self.assertTrue(entered.wait(2))
            bootstrap()
            self.assertEqual(queue.list(self.pid)[0]['state'], 'running')
            other = JobQueue(self.ai)
            with self.assertRaisesRegex(RuntimeError, 'Hàng đợi đang chạy'):
                other.start()
        finally:
            release.set()
            queue.shutdown()
        self.assertEqual(next(j['state'] for j in queue.list(self.pid) if j['id'] == job_id), 'done')

    def test_pause_resume(self):
        j=JobQueue(self.ai,poll=.03)
        jid=j.submit(self.pid,'series',{})
        j.command(jid,'pause')
        j.start()
        try:
            self.wait(j,jid,'paused')
            j.command(jid,'resume')
            self.wait(j,jid,'waiting_approval')
        finally:j.shutdown()

    def test_rewrite_preserves_approved_chapter_until_success(self):
        chapter = self.outline['chapters'][0]
        scene = chapter['scenes'][0]
        chapter_id, scene_id = chapter['id'], scene['id']
        process_scene(self.pid, self.outline, chapter, scene, self.ai)
        exported = project_dir(self.pid) / 'exports' / f'chapter_{chapter_id}.md'
        original_export = exported.read_bytes()
        c = story_db(self.pid)
        try:
            original = get_scene(c, chapter_id, scene_id)
            c.execute("INSERT INTO summaries VALUES(?, 'TOM_TAT_CU', 'approved', ?)", (chapter_id, now()))
            c.execute(
                "INSERT INTO memory_items(kind,content,chapter,source,status,created) "
                "VALUES('fact','CANON_CU',?,'model','approved',?)",
                (chapter_id, now()),
            )
            c.commit()
        finally:
            c.close()

        original_chat = self.ai.chat

        def interrupted_chat(system, user, **options):
            if options['role'] == 'writer':
                self.assertNotIn('CANON_CU', user)
                self.assertNotIn('TOM_TAT_CU', user)
            if options['role'] == 'editor':
                raise RuntimeError('Ollama mất kết nối')
            return original_chat(system, user, **options)

        self.ai.chat = interrupted_chat
        queue = JobQueue(self.ai, poll=.03)
        job_id = queue.submit(self.pid, 'rewrite', {'chapter': chapter_id, 'scene': scene_id})
        queue.start()
        try:
            self.wait(queue, job_id, 'failed')
            self.assertIn('Ollama mất kết nối', queue.list(self.pid)[0]['error'])
            c = story_db(self.pid)
            try:
                self.assertEqual(get_scene(c, chapter_id, scene_id), original)
                self.assertEqual(c.execute('SELECT status FROM summaries').fetchone()[0], 'approved')
                self.assertEqual(c.execute('SELECT status FROM memory_items').fetchone()[0], 'approved')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0], 2)
            finally:
                c.close()
            self.assertEqual(exported.read_bytes(), original_export)

            new_prose = 'An mang chuông đồng gỉ rời bến đò khi trời vừa hửng sáng. ' * 50
            self.ai.chat = lambda system, user, **opts: (
                new_prose if opts['role'] == 'editor' else original_chat(system, user, **opts)
            )
            queue.command(job_id, 'resume')
            self.wait(queue, job_id, 'done')
            c = story_db(self.pid)
            try:
                self.assertEqual(get_scene(c, chapter_id, scene_id)['edited'], new_prose)
                self.assertEqual(c.execute('SELECT status FROM summaries').fetchone()[0], 'stale')
                self.assertEqual(c.execute('SELECT status FROM memory_items').fetchone()[0], 'stale')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0], 4)
            finally:
                c.close()
            self.assertIn(new_prose.rstrip(), exported.read_text(encoding='utf8'))
        finally:
            queue.shutdown()

    def test_cancel_rewrite_leaves_current_scene_in_place(self):
        chapter = self.outline['chapters'][0]
        scene = chapter['scenes'][0]
        chapter_id, scene_id = chapter['id'], scene['id']
        process_scene(self.pid, self.outline, chapter, scene, self.ai)
        entered = threading.Event()
        release = threading.Event()
        original_chat = self.ai.chat

        def slow_chat(system, user, **options):
            if options['role'] == 'editor':
                entered.set()
                if not release.wait(3):
                    raise TimeoutError('Test worker did not receive release')
                return 'Bản viết lại có chuông đồng gỉ trong lần thử hủy. ' * 80
            return original_chat(system, user, **options)

        self.ai.chat = slow_chat
        queue = JobQueue(self.ai, poll=.03)
        job_id = queue.submit(self.pid, 'rewrite', {'chapter': chapter_id, 'scene': scene_id})
        queue.start()
        try:
            self.assertTrue(entered.wait(2))
            queue.command(job_id, 'cancel')
            release.set()
            self.wait(queue, job_id, 'canceled', timeout=2)
            c = story_db(self.pid)
            try:
                self.assertNotIn('Bản viết lại', get_scene(c, chapter_id, scene_id)['edited'])
                self.assertEqual(c.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0], 2)
            finally:
                c.close()
        finally:
            release.set()
            queue.shutdown()

    def test_scene_generation_does_not_overwrite_manual_edit(self):
        chapter = self.outline['chapters'][0]
        scene = chapter['scenes'][0]
        original_chat = self.ai.chat
        manual_text = 'Bản sửa tay mới được lưu khi Ollama đang xử lý.'

        def concurrent_chat(system, user, **options):
            if options['role'] == 'editor':
                c = story_db(self.pid)
                try:
                    save_scene(c, chapter['id'], scene['id'], 'edited', manual_text)
                finally:
                    c.close()
            return original_chat(system, user, **options)

        self.ai.chat = concurrent_chat
        with self.assertRaisesRegex(RuntimeError, 'Cảnh đã thay đổi'):
            process_scene(self.pid, self.outline, chapter, scene, self.ai)
        c = story_db(self.pid)
        try:
            self.assertEqual(get_scene(c, chapter['id'], scene['id'])['edited'], manual_text)
        finally:
            c.close()

    def test_planner_candidate_does_not_overwrite(self):
        j=JobQueue(self.ai,poll=.03);j.start()
        try:
            jid=j.submit(self.pid,'plan',{'premise':'Một thế giới giả tưởng','chapters':2})
            self.wait(j,jid,'done')
            candidate=project_dir(self.pid)/'outline_candidate.json'
            self.assertTrue(candidate.exists())
            self.assertEqual(load_outline(candidate)['title'],'Người Giữ Những Mùa Mưa')
        finally:j.shutdown()


class MigrationTests(Base):
    def test_migrate_v3_existing_scenes_and_canon(self):
        from migrate_from_v3 import migrate
        import sqlite3
        with tempfile.TemporaryDirectory() as t:
            old=Path(t)/'V3'/'project';old.mkdir(parents=True)
            (old/'outline.json').write_text(json.dumps(sample_outline(),ensure_ascii=False),encoding='utf8')
            db=sqlite3.connect(old/'series.db')
            db.execute('CREATE TABLE scenes (chapter TEXT,scene TEXT,draft TEXT,edited TEXT,review TEXT,created TEXT)')
            db.execute('CREATE TABLE memory (chapter TEXT,summary TEXT,approved INTEGER)')
            db.execute('CREATE TABLE canon (id INTEGER PRIMARY KEY, fact TEXT,created TEXT)')
            db.execute('INSERT INTO scenes VALUES(?,?,?,?,?,?)',('001','01','Bản nháp từ V3','Bản sửa từ V3','{}','2026'))
            db.execute('INSERT INTO memory VALUES(?,?,?)',('001','Tóm tắt cũ',1))
            db.execute('INSERT INTO canon(fact,created) VALUES(?,?)',('Sự thật từ V3','2026'))
            db.commit();db.close()
            target='migrate-'+self.pid
            res=migrate(old,target,apply=False)
            self.assertTrue(res['dry_run'])
            self.assertFalse(project_dir(target).exists())
            res=migrate(old,target,apply=True)
            self.assertFalse(res['dry_run'])
            db2=story_db(target)
            self.assertEqual(db2.execute('SELECT edited FROM scenes').fetchone()[0],'Bản sửa từ V3')
            self.assertEqual(db2.execute('SELECT status FROM summaries').fetchone()[0],'approved')
            self.assertEqual(db2.execute('SELECT status FROM memory_items').fetchone()[0],'approved')
            db2.close()
            self.assertTrue((old/'series.db').is_file())


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.s=Settings()
        self.app=NovelApp(settings=self.s,ai=self.ai,worker=False)
        self.httpd=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app))
        self.base='http://127.0.0.1:'+str(self.httpd.server_address[1])
        self.server_thread=threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.server_thread.start()
    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.server_thread.join(timeout=2);self.app.shutdown()

    def req(self,path,value=None,auth=True,headers=None,raw=None):
        hs=dict(headers or {})
        if auth:hs['X-Novel-Token']=self.s.browser_token
        if value is not None:
            hs['Content-Type']='application/json';data=json.dumps(value).encode()
        else:data=raw
        request=urllib.request.Request(self.base+path,data=data,headers=hs)
        try:
            with urllib.request.urlopen(request,timeout=5) as resp:
                return resp.status,resp.headers,resp.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code,e.headers,e.read()

    def test_auth_isolation_and_no_token_in_url(self):
        s,_,_=self.req('/api/bootstrap',auth=False);self.assertEqual(s,401)
        s,_,_=self.req('/api/bootstrap?token='+self.s.browser_token,auth=False);self.assertEqual(s,401)
        s,_,b=self.req('/api/bootstrap');self.assertEqual(s,200)
        self.assertNotIn(self.s.browser_token,b.decode())
        s,_,_=self.req('/api/project/../memory');self.assertNotEqual(s,200)
        s,_,_=self.req('/api/project/'+self.pid+'/outline');self.assertEqual(s,200)

    def test_post_requires_matching_origin_when_present(self):
        from urllib.parse import urlsplit
        route = '/api/projects'
        payload = {'id': 'origin-test', 'title': 'Origin test'}
        code, _, _ = self.req(route, payload, headers={'Origin': 'https://example.invalid'})
        self.assertEqual(code, 403)
        code, _, _ = self.req(route, payload, headers={'Origin': 'https://' + urlsplit(self.base).netloc})
        self.assertEqual(code, 201)

    def test_upload_and_backup(self):
        import urllib.parse
        path='/api/project/'+self.pid+'/upload?'+urllib.parse.urlencode({'name':'a.txt','license':'Tôi viết','rights':'yes'})
        s,_,b=self.req(path,headers={'Content-Type':'application/octet-stream'},raw='Tài liệu để thử nghiệm'.encode())
        self.assertEqual(s,201,b.decode())
        s,_,b=self.req('/api/project/'+self.pid+'/backup',value={})
        self.assertEqual(s,200,b.decode())
        name=json.loads(b)['name']
        s,_,content=self.req('/api/project/'+self.pid+'/backup?name='+name)
        self.assertEqual(s,200)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(content)))
        self.assertNotIn(b'browser_token.txt',content)

    def test_manual_scene_edit_is_versioned(self):
        chapter=self.outline['chapters'][0]['id']
        scene=self.outline['chapters'][0]['scenes'][0]['id']
        p='/api/project/'+self.pid+'/scene-edit'
        s,_,b=self.req(p,value={'chapter':chapter,'scene':scene,'text':'Cảnh được sửa thủ công. '*30})
        self.assertEqual(s,200,b.decode())
        c=story_db(self.pid)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0],1)
        self.assertEqual(c.execute('SELECT stage FROM scenes').fetchone()[0],'edited')
        c.close()

    def test_gateway_and_sse(self):
        s,_,_=self.req('/v1/models',auth=False);self.assertEqual(s,401)
        bearer={'Authorization':'Bearer '+self.s.gateway_token}
        s,_,b=self.req('/v1/models',auth=False,headers=bearer);self.assertEqual(s,200)
        self.assertIn('novel-'+self.pid,b.decode())
        body={'model':'novel-'+self.pid,'messages':[{'role':'user','content':'Xin chào'}], 'stream':True}
        s,h,b=self.req('/v1/chat/completions',value=body,auth=False,headers=bearer)
        self.assertEqual(s,200,b.decode());self.assertIn('text/event-stream',h.get('Content-Type'))
        self.assertIn(b'[DONE]',b)
        self.assertIn('Tôi sẽ',b.decode())


if __name__=='__main__':unittest.main()
