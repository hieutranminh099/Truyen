"""Minimal authenticated HTTP backend; binds loopback by default for Tailscale Serve."""
from __future__ import annotations
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import urllib.parse
import zipfile
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from .config import ROOT, DATA_ROOT, Settings, MAX_JSON_BYTES, MAX_UPLOAD_BYTES, project_dir, validate_project_id
from .store import (bootstrap, create_project, projects, queue_db, story_db, now, atomic_text,
                    update_memory, restore_version, export_chapter, get_scene, save_scene,
                    invalidate_chapter_memory)
from .outline import load_outline, parse_outline
from .rag import import_document, search_library
from .ai import AI
from .jobs import JobQueue
from .project_backup import create_backup, restore_backup, MAX_RESTORE_BYTES
from .project_state import project_write_lock, project_state, enable_creative


class NovelApp:
    def __init__(self,settings=None,ai=None,worker=True):
        self.settings=settings or Settings()
        bootstrap()
        self.ai=ai or AI(self.settings)
        self.jobs=JobQueue(self.ai)
        if worker:self.jobs.start()

    def shutdown(self):self.jobs.shutdown()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version='NovelEngine/4'
        timeout = 15
        def log_message(self,fmt,*args):
            # Keep tokens, payloads, draft text out of the access log.
            return

        def headers_common(self,kind='application/json; charset=utf-8'):
            self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

        def send_bytes(self,data: bytes,code=200,content_type='application/json; charset=utf-8',extra=None):
            self.send_response(code);self.headers_common(content_type)
            for k,v in (extra or {}).items(): self.send_header(k,v)
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass

        def reply(self,obj,code=200):
            self.send_bytes(json.dumps(obj,ensure_ascii=False).encode('utf8'),code)

        def error_reply(self,e,code=400):
            if isinstance(e,FileNotFoundError):code=404
            elif isinstance(e,PermissionError):code=403
            self.reply({'error':str(e)[:600]},code)

        def browse_auth(self):
            supplied=self.headers.get('X-Novel-Token','')
            return bool(supplied) and secrets.compare_digest(supplied.encode('utf-8'),app.settings.browser_token.encode('utf-8'))

        def gateway_auth(self):
            supplied=self.headers.get('Authorization','')
            if not supplied.lower().startswith('bearer '):return False
            return secrets.compare_digest(supplied[7:].strip().encode('utf-8'),app.settings.gateway_token.encode('utf-8'))

        def _route(self):
            parts=urllib.parse.urlsplit(self.path)
            return parts.path,urllib.parse.parse_qs(parts.query)

        def project_route(self,p):
            match=re.fullmatch(r'/api/project/([^/]+)/([^/]+)',p)
            if not match: return None
            return validate_project_id(urllib.parse.unquote(match.group(1))),match.group(2)

        def do_GET(self):
            try:
                p,q=self._route()
                if p in ('/','/index.html'):
                    b=(ROOT/'static'/'index.html').read_bytes()
                    return self.send_bytes(b,content_type='text/html; charset=utf-8')
                if p in ('/app.js','/app.css'):
                    kind='application/javascript; charset=utf-8' if p.endswith('js') else 'text/css; charset=utf-8'
                    return self.send_bytes((ROOT/'static'/p[1:]).read_bytes(),content_type=kind)
                if p=='/health':return self.reply({'ok':True})
                if p=='/v1/models':
                    if not self.gateway_auth():return self.reply({'error':'Gateway API key bắt buộc'},401)
                    return self.reply({'object':'list','data':[{'id':'novel-'+p['id'],'object':'model','owned_by':'novel-engine'} for p in projects()]})
                if not self.browse_auth():return self.reply({'error':'Mã truy cập không đúng'},401)
                if p=='/api/bootstrap':return self.reply({'projects':projects(),'settings':app.settings.info()})
                if p=='/api/projects':return self.reply({'items':projects()})
                if p=='/api/jobs':return self.reply({'items':app.jobs.list(q.get('project',[''])[0])})
                route=self.project_route(p)
                if not route:return self.reply({'error':'API route không tồn tại'},404)
                pid,action=route; d=project_dir(pid)
                if not (d/'story.db').exists(): raise FileNotFoundError('Dự án không tồn tại')
                if action=='creative-status':
                    return self.reply(project_state(d, project_id=pid))
                if action=='outline':return self.reply({'value':load_outline(d/'outline.json')})
                if action=='candidate':
                    x=d/'outline_candidate.json'
                    return self.reply({'value':json.loads(x.read_text(encoding='utf8')) if x.exists() else None})
                if action=='voice':return self.reply({'text':(d/'voice_bible.md').read_text(encoding='utf8')})
                if action=='scenes':
                    c=story_db(pid)
                    try: rows=c.execute('SELECT chapter,scene,stage,updated,length(edited) AS chars FROM scenes ORDER BY rowid').fetchall()
                    finally:c.close()
                    return self.reply({'items':[dict(x) for x in rows]})
                if action=='scene':
                    chapter=q.get('chapter',[''])[0];scene=q.get('scene',[''])[0]
                    c=story_db(pid)
                    try:
                        r=get_scene(c,chapter,scene)
                        versions=[dict(x) for x in c.execute('''SELECT id,stage,created,length(text) AS chars FROM scene_versions
                                  WHERE chapter=? AND scene=? ORDER BY id DESC LIMIT 50''',(chapter,scene))]
                    finally:c.close()
                    return self.reply({'scene':r,'versions':versions})
                if action=='versions':
                    c=story_db(pid)
                    try:r=c.execute('SELECT * FROM scene_versions WHERE id=?',(int(q['id'][0]),)).fetchone()
                    finally:c.close()
                    return self.reply({'item':dict(r) if r else None})
                if action=='chapters':
                    outline=load_outline(d/'outline.json');c=story_db(pid)
                    try:
                        out=[]
                        for ch in outline['chapters']:
                            rows=[get_scene(c,ch['id'],s['id']) for s in ch['scenes']]
                            st=c.execute('SELECT status FROM summaries WHERE chapter=?',(ch['id'],)).fetchone()
                            out.append({'id':ch['id'],'title':ch['title'],'scenes':len(rows),'finished':sum(bool(x and x['edited']) for x in rows),
                                        'summary':st['status'] if st else None})
                    finally:c.close()
                    return self.reply({'items':out})
                if action=='memory':
                    c=story_db(pid)
                    try:
                        summaries=[dict(r) for r in c.execute('SELECT * FROM summaries ORDER BY rowid')]
                        items=[dict(r) for r in c.execute('SELECT * FROM memory_items ORDER BY id DESC LIMIT 300')]
                    finally:c.close()
                    return self.reply({'summaries':summaries,'items':items})
                if action=='library':return self.reply({'items':search_library(pid,q.get('q',[''])[0])})
                if action=='export':
                    ch=q.get('chapter',[''])[0]
                    outline=load_outline(d/'outline.json')
                    chapter=next((x for x in outline['chapters'] if x['id']==ch),None)
                    if not chapter:raise ValueError('Chương không tồn tại')
                    path=export_chapter(pid,chapter)
                    return self.send_bytes(path.read_bytes(),content_type='text/markdown; charset=utf-8',
                                           extra={'Content-Disposition': 'attachment; filename="chapter_'+re.sub(r'[^\w-]','_',ch)+'.md"'})
                if action=='backup':
                    name=q.get('name',[''])[0]
                    if not re.fullmatch(r'backup_[0-9T_-]+\.zip',name):raise ValueError('Tên backup không hợp lệ')
                    f=d/'backups'/name
                    if not f.exists():raise FileNotFoundError('Backup không tồn tại')
                    return self.send_bytes(f.read_bytes(),content_type='application/zip',
                                           extra={'Content-Disposition':f'attachment; filename="{name}"'})
                return self.reply({'error':'Không có endpoint này'},404)
            except Exception as e:self.error_reply(e)

        def read_body(self, limit):
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get('Transfer-Encoding') or len(lengths) != 1:
                raise ValueError('Yêu cầu phải khai báo một Content-Length')
            if not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
                raise ValueError('Content-Length không hợp lệ')
            length = int(lengths[0])
            if not 0 < length <= limit:
                raise ValueError('Nội dung trống hoặc vượt giới hạn')
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError('Yêu cầu chưa gửi đủ nội dung')
            return data

        def read_json(self):
            obj = json.loads(self.read_body(MAX_JSON_BYTES))
            if not isinstance(obj, dict):
                raise ValueError('Yêu cầu phải là JSON object')
            return obj

        def check_write_origin(self):
            origin = self.headers.get('Origin')
            if origin is None:  # CLI and native gateway clients.
                return
            parts = urllib.parse.urlsplit(origin)
            host = self.headers.get('Host', '')
            if (parts.scheme not in {'http', 'https'} or not host
                    or parts.netloc.lower() != host.lower() or parts.path
                    or parts.query or parts.fragment):
                raise PermissionError('Origin không khớp máy chủ')

        def do_POST(self):
            try:
                self.check_write_origin()
                p,q=self._route()
                if p=='/v1/chat/completions':
                    if not self.gateway_auth():return self.reply({'error':'Gateway API key không hợp lệ'},401)
                    return self.gateway(self.read_json())
                if not self.browse_auth():return self.reply({'error':'Mã truy cập không đúng'},401)
                if p=='/api/projects':
                    data=self.read_json();return self.reply(create_project(str(data.get('title','Truyện mới')),str(data.get('id',''))),201)
                if p=='/api/restore-project':
                    new_id = validate_project_id(q.get('id', [''])[0])
                    raw = self.read_body(MAX_RESTORE_BYTES)
                    with tempfile.TemporaryDirectory(prefix='.restore-upload-', dir=DATA_ROOT) as folder:
                        archive = Path(folder) / 'upload.zip'
                        archive.write_bytes(raw)
                        return self.reply(restore_backup(archive, new_id), 201)
                m=re.fullmatch(r'/api/jobs/(\d+)/(pause|cancel|resume)',p)
                if m:
                    app.jobs.command(int(m.group(1)),m.group(2))
                    return self.reply({'ok':True})
                route=self.project_route(p)
                if not route:return self.reply({'error':'API route không tồn tại'},404)
                pid,action=route; d=project_dir(pid)
                if not (d/'story.db').exists():raise FileNotFoundError('Dự án không tồn tại')
                if action=='creative-enable':
                    data = self.read_json()
                    if data.get('confirm') is not True:
                        raise ValueError('Cần confirm=true để bật Creative cho dự án chưa có dữ liệu.')
                    return self.reply(enable_creative(pid))
                with project_write_lock(d):
                    if action=='upload':
                        name=q.get('name',[''])[0]; license_note=q.get('license',[''])[0]
                        confirmed=q.get('rights',[''])[0]=='yes'
                        return self.reply(import_document(pid,name,self.read_body(MAX_UPLOAD_BYTES),license_note,confirmed),201)
                    data=self.read_json()
                    if action=='outline':
                        obj=parse_outline(data.get('value',{}))
                        # Existing scenes with changed IDs should never silently mix histories.
                        c=story_db(pid)
                        try:has_data=bool(c.execute('SELECT 1 FROM scenes LIMIT 1').fetchone())
                        finally:c.close()
                        if has_data and not data.get('confirm_existing'):
                            raise ValueError('Dự án đã có bản thảo. Xác nhận confirm_existing=true sau khi đã sao lưu; tránh thay đổi ID cảnh/chương.')
                        atomic_text(d/'outline.json',json.dumps(obj,ensure_ascii=False,indent=2))
                        return self.reply({'ok':True})
                    if action=='candidate-accept':
                        candidate=d/'outline_candidate.json'
                        if not candidate.exists():raise ValueError('Không có dàn ý đề xuất')
                        c=story_db(pid)
                        try:has=bool(c.execute('SELECT 1 FROM scenes LIMIT 1').fetchone())
                        finally:c.close()
                        if has:raise ValueError('Dự án đã có bản thảo; không tự ghi đè dàn ý')
                        obj=parse_outline(candidate.read_text(encoding='utf8'))
                        atomic_text(d/'outline.json',json.dumps(obj,ensure_ascii=False,indent=2))
                        return self.reply({'ok':True})
                    if action=='voice':
                        text=str(data.get('text',''))
                        if len(text)>16000:raise ValueError('Voice Bible dài quá 16.000 ký tự')
                        atomic_text(d/'voice_bible.md',text)
                        return self.reply({'ok':True})
                    if action=='job':
                        kind=str(data.get('kind','series'))
                        payload=dict(data.get('payload',{}))
                        if kind=='plan' and payload.get('cloud') and not app.settings.cloud_enabled:
                            raise ValueError('Cloud đang tắt trong cấu hình')
                        if kind=='series' and payload.get('cloud_critic') and not app.settings.cloud_enabled:
                            raise ValueError('Cloud đang tắt trong cấu hình')
                        if kind=='plan' and not isinstance(payload.get('premise'),str):
                            raise ValueError('Cần premise là chuỗi')
                        return self.reply({'id':app.jobs.submit(pid,kind,payload)},201)
                    if action=='approve-chapter':
                        ch=str(data.get('chapter',''));c=story_db(pid)
                        try:
                            r=c.execute("UPDATE summaries SET status='approved',updated=? WHERE chapter=? AND status='pending'",(now(),ch))
                            if not r.rowcount: raise ValueError('Chương không có tóm tắt đang chờ duyệt')
                            c.commit()
                        finally:c.close()
                        app.jobs.wake_approval(pid)
                        return self.reply({'ok':True})
                    if action=='memory':
                        kind=str(data.get('kind','fact'))
                        if kind not in ('fact','timeline','character','knowledge','thread'):raise ValueError('Loại trí nhớ không hợp lệ')
                        content=str(data.get('content','')).strip()
                        if not content or len(content)>1600:raise ValueError('Nội dung trống hoặc quá 1600 ký tự')
                        subject=str(data.get('subject',''))[:120]
                        c=story_db(pid)
                        try:
                            cur=c.execute('INSERT INTO memory_items(kind,subject,content,source,status,visibility,created) VALUES(?,?,?,"manual","pending",?,?)',
                                          (kind,subject,content,'private' if kind=='knowledge' else str(data.get('visibility','public')),now()));c.commit()
                            return self.reply({'id':cur.lastrowid},201)
                        finally:c.close()
                    if action=='memory-action':
                        c=story_db(pid)
                        try:update_memory(c,int(data['id']),str(data['action']))
                        finally:c.close()
                        return self.reply({'ok':True})
                    if action=='scene-edit':
                        chapter_id=str(data.get('chapter',''));scene_id=str(data.get('scene',''))
                        prose=str(data.get('text','')).strip()
                        if len(prose)<30 or len(prose)>100000: raise ValueError('Bản sửa cần 30–100.000 ký tự')
                        outline=load_outline(d/'outline.json')
                        chapter=next((ch for ch in outline['chapters'] if ch['id']==chapter_id),None)
                        if not chapter or not any(sc['id']==scene_id for sc in chapter['scenes']):
                            raise ValueError('Cảnh không có trong dàn ý')
                        c=story_db(pid)
                        try:
                            with c:
                                save_scene(c, chapter_id, scene_id, 'edited', prose, commit=False)
                                invalidate_chapter_memory(c, chapter_id)
                        finally:c.close()
                        export_chapter(pid,chapter)
                        return self.reply({'ok':True})
                    if action=='restore':
                        return self.reply(restore_version(pid,int(data['version_id'])))
                    if action=='backup':
                        return self.reply({'name':self._backup(pid)})
                    return self.reply({'error':'Không có endpoint này'},404)
            except Exception as e:self.error_reply(e)

        def _backup(self,pid):
            return create_backup(pid)

        def gateway(self,data):
            """Best-effort OpenAI-compatible endpoint; stream mode returns buffered SSE."""
            msg=data.get('messages',[])
            if not isinstance(msg,list) or not msg or len(msg)>100:raise ValueError('messages[] không hợp lệ')
            model=str(data.get('model','novel-demo'))
            if model.startswith('novel-'):
                model_segment=model[len('novel-'):]
                pid,sep,actor=model_segment.partition('--')
                actor=actor.replace('_',' ').strip() if sep else ''
            else:
                p=projects();pid=p[0]['id'] if p else 'demo';actor=''
            d=project_dir(pid)
            if not (d/'story.db').exists():raise ValueError('Dự án nhập vai không tồn tại')
            c=story_db(pid)
            try:
                # Spoiler/knowledge firewall: private knowledge never goes to unidentified NPCs.
                facts=c.execute("""SELECT kind,subject,content FROM memory_items WHERE status='approved'
                                   AND (visibility='public' OR (kind='knowledge' AND lower(subject)=lower(?)))
                                   ORDER BY id DESC LIMIT 22""",(actor,)).fetchall()
                summaries=c.execute("SELECT chapter,body FROM summaries WHERE status='approved' ORDER BY rowid DESC LIMIT 3").fetchall()
            finally:c.close()
            memory='\n'.join(f'- [{r["kind"]}] {r["subject"]}: {r["content"]}' for r in facts)
            chronicle='\n'.join(f'- {r["chapter"]}: {r["body"][:500]}' for r in summaries)
            voice=(d/'voice_bible.md').read_text(encoding='utf8')[:1200]
            system=('HỒ SƠ THẾ GIỚI VÀ SỰ THẬT ĐÃ DUYỆT (CHỈ THAM KHẢO, KHÔNG TIẾT LỘ BÍ MẬT KHÔNG THUỘC NHÂN VẬT):\n'
                    +memory[:2500]+'\nDIỄN BIẾN:\n'+chronicle[:1400]+'\nGIỌNG VĂN:\n'+voice+
                    '\nKhông tự cập nhật canon khi trò chuyện.')
            clean=[]
            for item in msg[-40:]:
                if not isinstance(item,dict):continue
                role=item.get('role')
                if role not in ('system','user','assistant'):continue
                content=item.get('content','')
                if isinstance(content,list): content='\n'.join(str(x.get('text','')) for x in content if isinstance(x,dict))
                clean.append({'role':role,'content':str(content)[:3500]})
            if not clean:raise ValueError('Không có nội dung đối thoại')
            # Pack into a single user request; preserve original system/world info from ST.
            user='HỘI THOẠI SILLYTAVERN:\n'+'\n'.join(f'{x["role"]}: {x["content"]}' for x in clean)
            output=app.ai.chat(system,user,role='roleplay',temperature=float(data.get('temperature',.8)),
                              max_tokens=min(2048,max(128,int(data.get('max_tokens') or 700))))
            result={'id':'chatcmpl-novel','object':'chat.completion','created':int(datetime.now().timestamp()),
                    'model':model,'choices':[{'index':0,'message':{'role':'assistant','content':output},'finish_reason':'stop'}]}
            if not data.get('stream'):return self.reply(result)
            # Streaming compatibility: SSE envelope, but model completes before the first chunk.
            chunk={'id':result['id'],'object':'chat.completion.chunk','created':result['created'],'model':model,
                   'choices':[{'index':0,'delta':{'role':'assistant','content':output},'finish_reason':None}]}
            end={'id':result['id'],'object':'chat.completion.chunk','created':result['created'],'model':model,
                 'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}
            frames=('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n'+
                    'data: '+json.dumps(end,ensure_ascii=False)+'\n\n'+'data: [DONE]\n\n').encode('utf8')
            return self.send_bytes(frames,content_type='text/event-stream; charset=utf-8')
    return Handler


def serve(settings=None,ai=None):
    app=NovelApp(settings,ai,worker=False)
    httpd=ThreadingHTTPServer((app.settings.host,app.settings.port),make_handler(app))
    httpd.daemon_threads=True
    print(f'Novel Engine Hybrid: http://{app.settings.host}:{app.settings.port}')
    print('Mã giao diện (giữ bí mật):',app.settings.browser_token)
    print('API key SillyTavern (giữ bí mật):',app.settings.gateway_token)
    print('Dữ liệu:',project_dir('demo').parent)
    print('Tailscale Serve: chỉ dùng HTTPS riêng tư. KHÔNG mở port forwarding hoặc Funnel.')
    try:
        app.jobs.start()
        httpd.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:pass
    finally:httpd.server_close();app.shutdown()
