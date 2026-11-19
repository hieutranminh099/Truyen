'use strict';
let token=sessionStorage.getItem('novel_token')||'';
let project='';let allProjects=[];let chapters=[];let selectedScene=null;let alertTimer=null;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const qp=s=>encodeURIComponent(String(s));
function alertMessage(message,error=false){const el=$('alert');el.hidden=false;el.className='alert'+(error?' error':'');el.textContent=message;clearTimeout(alertTimer);alertTimer=setTimeout(()=>el.hidden=true,8000)}
async function request(path,{method='GET',value,raw,headers={}}={}){
  const opts={method,headers:{'X-Novel-Token':token,...headers}};
  if(value!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(value);opts.method='POST'}
  if(raw!==undefined){opts.body=raw;opts.method='POST'}
  const res=await fetch(path,opts);
  let data;try{data=await res.json()}catch{throw Error('Máy chủ trả dữ liệu không hợp lệ')}
  if(!res.ok)throw Error(data.error||'HTTP '+res.status);
  return data;
}
async function safe(fn){try{return await fn()}catch(e){alertMessage(e.message||String(e),true);throw e}}
async function fire(fn){try{await fn()}catch(e){alertMessage(e.message||String(e),true)}}
function view(name){
  for(const p of document.querySelectorAll('.panel'))p.classList.toggle('active',p.id==='panel-'+name);
  for(const n of document.querySelectorAll('.nav'))n.classList.toggle('active',n.dataset.panel===name);
  $('page-title').textContent=({'dashboard':'Tổng quan dự án','outline':'Dàn ý & nhân vật','jobs':'Viết truyện bằng AI','drafts':'Bản thảo','memory':'Trí nhớ truyện','library':'Tài liệu tham khảo','settings':'Cài đặt & kết nối'})[name]||'Novel Engine';
  window.scrollTo({top:0,behavior:'instant'});
  if(name==='jobs')void fire(loadJobs);
  if(name==='memory')void fire(async()=>{await loadMemory();await loadCreative()});
  if(name==='library')void fire(loadLibrary);
  if(name==='drafts')void fire(loadDrafts);
}
function badge(s){const cls={done:'good',edited:'good',approved:'good',running:'warn',waiting_approval:'warn',pending:'warn',stale:'bad',failed:'bad',canceled:'bad',revoked:'bad'}[s]||'';return `<span class="badge ${cls}">${esc(s??'chưa có')}</span>`}
function btn(title,fn,cls='secondary'){
  const b=document.createElement('button');b.type='button';b.className='btn small '+cls;b.textContent=title;b.addEventListener('click',()=>fire(fn));return b;
}
function empty(parent,msg){parent.innerHTML='<p class="muted">'+esc(msg)+'</p>'}
function item(parent,title,detail,status){const e=document.createElement('div');e.className='item';e.innerHTML=`<div class="item-head"><strong>${esc(title)}</strong>${badge(status)}</div><p class="muted">${esc(detail)}</p>`;parent.append(e);return e}
function setProject(pid){
  if(pid!==project){
    resetScene();
    $('draft-chapter').replaceChildren();
    $('draft-scene').replaceChildren();
  }
  project=pid;
  sessionStorage.setItem('novel_project',project);
  $('project-select').value=project;
  void fire(refreshAll);
}
async function loadProjects(){const x=await request('/api/bootstrap');allProjects=x.projects;const sel=$('project-select');sel.innerHTML='';for(const p of allProjects){const opt=document.createElement('option');opt.value=p.id;opt.textContent=p.title+' ('+p.id+')';sel.append(opt)}
  const saved=sessionStorage.getItem('novel_project');project=(allProjects.find(x=>x.id===saved)||allProjects[0]||{}).id||'';sel.value=project;
  $('config-view').innerHTML=Object.entries(x.settings).map(([k,v])=>`<div class="stat config-value"><small>${esc(k)}</small><b>${esc(v)}</b></div>`).join('');
  const port=Number(x.settings?.port)||8765;
  $('settings-local-url').textContent='127.0.0.1:'+port;
  $('settings-tailscale-command').textContent='tailscale serve --bg '+port;
  $('settings-gateway-url').textContent='http://127.0.0.1:'+port+'/v1';
  $('server-dot').classList.add('online');$('server-label').textContent='Đã kết nối · Local first';
}
async function refreshAll(){if(!project)return;await Promise.all([loadDashboard(),loadOutline(),loadVoice(),loadJobs(),loadMemory(),loadLibrary(),loadDrafts()])}
async function loadDashboard(){const [sc,chs,mem]=await Promise.all([request('/api/project/'+qp(project)+'/scenes'),request('/api/project/'+qp(project)+'/chapters'),request('/api/project/'+qp(project)+'/memory')]);chapters=chs.items;
  const total=chapters.reduce((n,x)=>n+x.scenes,0),done=chapters.reduce((n,x)=>n+x.finished,0),approved=mem.summaries.filter(x=>x.status==='approved').length;
  $('stats').innerHTML=[[done+'/'+total,'Cảnh hoàn thành'],[chapters.length,'Chương trong dàn ý'],[approved,'Chương đã duyệt'],[mem.items.filter(x=>x.status==='approved').length,'Dữ kiện canon']].map(([v,k])=>`<div class="stat"><b>${esc(v)}</b><small>${esc(k)}</small></div>`).join('');
  const list=$('chapter-list');list.innerHTML='';for(const ch of chapters){const e=item(list,ch.id+' · '+ch.title,`${ch.finished}/${ch.scenes} cảnh`,ch.summary||'chưa viết');const p=document.createElement('div');p.className='progress';const inner=document.createElement('div');inner.style.width=Math.round(ch.finished/ch.scenes*100)+'%';p.append(inner);e.append(p)}
}
async function loadOutline(){
  const pid=project;
  const x=await request('/api/project/'+qp(pid)+'/outline');
  if(pid===project)$('outline-text').value=JSON.stringify(x.value,null,2);
}
async function loadVoice(){
  const pid=project;
  const x=await request('/api/project/'+qp(pid)+'/voice');
  if(pid===project)$('voice-text').value=x.text;
}
async function loadJobs(){const x=await request('/api/jobs?project='+qp(project));const list=$('job-list');list.innerHTML='';if(!x.items.length)return empty(list,'Chưa có tác vụ.');for(const j of x.items){let detail=j.progress;try{detail=JSON.parse(j.progress).message||detail}catch{}const e=item(list,`#${j.id} · ${j.kind}`,detail||j.created,j.state);if(j.error){const err=document.createElement('p');err.className='danger';err.textContent=j.error;e.append(err)}const row=document.createElement('div');row.className='btn-row';if(j.state==='running'||j.state==='queued'){row.append(btn('Tạm dừng',()=>jobCmd(j.id,'pause')));row.append(btn('Hủy tại ranh giới',()=>jobCmd(j.id,'cancel'),'warn'))}if(j.state==='failed'||j.state==='paused')row.append(btn('Tiếp tục',()=>jobCmd(j.id,'resume'),'primary'));if(j.state==='waiting_approval')row.append(btn('Duyệt chương',()=>{view('memory');return loadMemory()},'primary'));if(['paused','waiting_approval'].includes(j.state))row.append(btn('Hủy',()=>jobCmd(j.id,'cancel'),'warn'));e.append(row)}}
async function jobCmd(id,cmd){await request('/api/jobs/'+id+'/'+cmd,{value:{}});alertMessage('Đã gửi lệnh '+cmd);await loadJobs()}
function resetScene(){
  selectedScene=null;
  $('manual-edit-box').hidden=true;
  $('manual-edit-text').value='';
  $('draft-text').hidden=false;
  $('draft-text').textContent='Chọn chương và cảnh để đọc.';
  $('version-list').replaceChildren();
}

async function loadDrafts(){
  const pid=project;
  const {value:outline}=await request('/api/project/'+qp(pid)+'/outline');
  if(pid!==project)return;
  const chapterSelect=$('draft-chapter');
  const previousChapter=chapterSelect.value;
  const sceneSelect=$('draft-scene');
  const previousScene=sceneSelect.value;
  chapterSelect.replaceChildren(...outline.chapters.map(ch=>new Option(ch.id+' · '+ch.title,ch.id)));
  if(outline.chapters.some(ch=>ch.id===previousChapter))chapterSelect.value=previousChapter;
  const chapter=outline.chapters.find(ch=>ch.id===chapterSelect.value);
  sceneSelect.replaceChildren(...chapter.scenes.map(sc=>new Option(sc.id+' · '+(sc.title||'Cảnh'),sc.id)));
  if(chapter.id===previousChapter&&chapter.scenes.some(sc=>sc.id===previousScene))sceneSelect.value=previousScene;
  if(selectedScene&&(selectedScene.chapter!==chapterSelect.value||selectedScene.scene!==sceneSelect.value))resetScene();
}

async function openScene(){
  const pid=project;
  const ch=$('draft-chapter').value,sc=$('draft-scene').value;
  if(!ch||!sc)return;
  const projectRoute='/api/project/'+qp(pid);
  const x=await request(projectRoute+'/scene?chapter='+qp(ch)+'&scene='+qp(sc));
  if(pid!==project||ch!==$('draft-chapter').value||sc!==$('draft-scene').value)return;
  const opened={chapter:ch,scene:sc};
  selectedScene=opened;
  $('manual-edit-box').hidden=true;
  $('draft-text').hidden=false;
  $('draft-text').textContent=x.scene?.edited||x.scene?.draft||'Chưa viết cảnh này.';
  const list=$('version-list');
  list.replaceChildren();
  for(const v of x.versions){
    const e=item(list,`Phiên bản #${v.id}`,`${v.created} · ${v.chars} ký tự`,v.stage);
    e.append(btn('Xem bản này',async()=>{
      const res=await request(projectRoute+'/versions?id='+v.id);
      if(selectedScene===opened)$('draft-text').textContent=res.item.text;
    }));
    e.append(btn('Khôi phục',async()=>{
      if(selectedScene!==opened||!confirm('Khôi phục phiên bản này? Tóm tắt chương sẽ cần duyệt lại.'))return;
      await request(projectRoute+'/restore',{value:{version_id:v.id}});
      if(selectedScene===opened){
        await openScene();
        alertMessage('Đã tạo phiên bản khôi phục mới');
      }
    },'warn'));
  }
}

async function loadMemory(){const x=await request('/api/project/'+qp(project)+'/memory');const creativeMode=(await request('/api/project/'+qp(project)+'/creative')).enabled;const sums=$('summary-list');sums.innerHTML='';for(const s of x.summaries){const e=item(sums,'Chương '+s.chapter,s.body,s.status);if(s.status==='pending')e.append(btn('Duyệt và tiếp tục',async()=>{await request('/api/project/'+qp(project)+'/approve-chapter',{value:{chapter:s.chapter}});alertMessage('Đã duyệt; công việc sẽ tiếp tục.');await loadMemory();await loadJobs();await loadDashboard()},'primary'))}if(!x.summaries.length)empty(sums,'Chưa có tóm tắt chương.');const mem=$('memory-items');mem.innerHTML='';for(const x1 of x.items){const e=item(mem,`${x1.kind.toUpperCase()} ${x1.subject?'· '+x1.subject:''}`,x1.content,x1.status);const row=document.createElement('div');row.className='btn-row';if(!creativeMode&&x1.status!=='approved')row.append(btn('Duyệt',()=>memoryAction(x1.id,'approve'),'primary'));if(!creativeMode&&x1.status==='pending')row.append(btn('Từ chối',()=>memoryAction(x1.id,'reject')));if(!creativeMode&&x1.status==='approved')row.append(btn('Thu hồi',()=>memoryAction(x1.id,'revoke'),'warn'));e.append(row)}if(!x.items.length)empty(mem,'Chưa có dữ kiện.');}
async function memoryAction(id,action){await request('/api/project/'+qp(project)+'/memory-action',{value:{id,action}});await loadMemory();await loadDashboard()}
async function loadLibrary(){const x=await request('/api/project/'+qp(project)+'/library?q='+qp($('library-query').value));const list=$('doc-list');list.innerHTML='';for(const d of x.items){const e=item(list,d.name,`Quyền: ${d.license} · ${d.chunks??'?'} đoạn · Đã phân tích ${d.analyzed??'?'} đoạn`);e.append(btn('Phân tích tối đa 20 đoạn',async()=>{const j=await request('/api/project/'+qp(project)+'/job',{value:{kind:'analyze',payload:{doc_id:d.id,limit:20}}});alertMessage('Đã xếp hàng công việc #'+j.id);await loadJobs()}))}if(!x.items.length)empty(list,'Chưa có tài liệu hoặc không tìm thấy từ khóa.')}
async function downloadChapter(){const chapter=$('draft-chapter').value;if(!chapter)throw Error('Hãy chọn chương để xuất');const res=await fetch('/api/project/'+qp(project)+'/export?chapter='+qp(chapter),{headers:{'X-Novel-Token':token}});if(!res.ok){const e=await res.json();throw Error(e.error)}const b=await res.blob();downloadBlob(b,'chapter_'+chapter+'.md')}
function downloadBlob(blob,name){const link=document.createElement('a');const url=URL.createObjectURL(blob);link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)}
async function createBackup(){const x=await request('/api/project/'+qp(project)+'/backup',{value:{}});const res=await fetch('/api/project/'+qp(project)+'/backup?name='+qp(x.name),{headers:{'X-Novel-Token':token}});if(!res.ok)throw Error('Không tải được backup');downloadBlob(await res.blob(),x.name);$('backup-result').textContent='Đã tạo và tải '+x.name}

async function loadCreative(){
  if(!project)return;
  const pid=project;
  const data=await request('/api/project/'+qp(pid)+'/creative');
  if(pid!==project)return;
  const enabled=data.enabled;
  $('creative-enable').hidden=enabled;
  $('creative-form').hidden=!enabled;
  $('memory-add').disabled=enabled;
  $('creative-status').textContent=enabled
    ? 'Đang bật · Ledger revision '+data.revision+' · '+data.items.length+' sự kiện · Không tự chuyển dữ kiện V4'
    : 'Đang tắt · dữ liệu V4 cũ được giữ nguyên. Chỉ bật trên dự án chưa có cảnh và canon.';
  if(!enabled)return;
  const list=$('creative-items');list.replaceChildren();
  for(const event of data.items){
    const source=event.position?.chapter?(' · vị trí '+event.position.chapter+'/'+event.position.scene):' · canon ban đầu';
    const label=(event.kind||'event')+' · '+(event.subject||event.id);
    const el=item(list,label,(event.value||'')+source+(event.stale_source?' · NGUỒN CŨ, CẦN DUYỆT LẠI':''),event.stale_source?'stale':event.status);
    if(event.status==='pending'){
      el.append(btn('Duyệt',()=>creativeDecide(event.id,'approve',data.revision),'primary'));
      el.append(btn('Từ chối',()=>creativeDecide(event.id,'reject',data.revision)));
    }
    if(event.status==='approved')el.append(btn('Thu hồi',()=>creativeDecide(event.id,'undo',data.revision),'warn'));
  }
  if(!data.items.length)empty(list,'Chưa có quyết định Creative. Hãy tạo một đề xuất.');
  const legacy=$('creative-legacy');legacy.replaceChildren();
  for(const fact of data.legacy_pending){
    const el=item(legacy,fact.kind+' · '+(fact.subject||fact.id),fact.content+' · chương '+(fact.chapter||'gốc'),'pending');
    el.append(btn('Nhập để duyệt',async()=>{
      const scene_id=fact.chapter?prompt('Cảnh nguồn chính xác trong chương '+fact.chapter+':','01'):'';
      if(fact.chapter&&!scene_id)return;
      const subject=prompt('Tên chủ thể / ID dữ kiện:',fact.subject||('v4-'+fact.id));
      if(!subject)return;
      const key=['character','knowledge','thread'].includes(fact.kind)?prompt('Key / ID canon hoặc thuộc tính cần ánh xạ:',''):'';
      if(key===null)return;
      const value=fact.kind==='knowledge'?prompt('Trạng thái biết (known, unknown, suspected):','known'):null;
      if(fact.kind==='knowledge'&&value===null)return;
      await request('/api/project/'+qp(pid)+'/creative-import',{value:{id:fact.id,scene_id:scene_id||'',subject,key:key||'',value}});
      alertMessage('Đã nhập đề xuất sang Creative, chưa duyệt tự động.');await loadCreative();
    }));
  }
  if(!data.legacy_pending.length)empty(legacy,'Không có đề xuất V4 mới.');
  const notes=$('creative-notes');notes.replaceChildren();
  for(const note of data.notes){
    const el=item(notes,note.name,note.purpose+' · '+note.expected_effect,'approved');
    el.append(btn('Bỏ ghi chú',async()=>{
      await request('/api/project/'+qp(pid)+'/creative-note',{value:{action:'delete',note_id:note.note_id}});
      await loadCreative();
    },'warn'));
  }
  if(!data.notes.length)empty(notes,'Chưa có ghi chú kỹ thuật được duyệt.');
}
async function creativeDecide(event_id,action,revision){
  const reason=prompt('Lý do quyết định / bằng chứng (tùy chọn):','');
  if(reason===null)return;
  await request('/api/project/'+qp(project)+'/creative-action',{value:{event_id,action,reason,expected_revision:revision}});
  await loadCreative();
}
async function creativePropose(){
  const data=await request('/api/project/'+qp(project)+'/creative');
  if(!data.enabled)throw Error('Creative chưa bật.');
  const payload={
    kind:$('creative-kind').value,subject:$('creative-subject').value,
    value:$('creative-value').value,key:$('creative-key').value,
    chapter_id:$('creative-chapter').value,scene_id:$('creative-scene').value,
    evidence:$('creative-evidence').value,expected_revision:data.revision
  };
  await request('/api/project/'+qp(project)+'/creative-propose',{value:payload});
  $('creative-value').value='';
  alertMessage('Đã lưu đề xuất Creative, cần duyệt trước khi Writer sử dụng.');
  await loadCreative();
}

async function beginAuth(){token=$('auth-input').value.trim();if(!token)return;try{await request('/api/bootstrap');sessionStorage.setItem('novel_token',token);$('auth-modal').hidden=true;await loadProjects();await refreshAll()}catch(e){$('auth-error').textContent=e.message;token=''}}
async function boot(){if(!token){$('auth-modal').hidden=false;return}try{await loadProjects();await refreshAll()}catch(e){token='';sessionStorage.removeItem('novel_token');$('auth-modal').hidden=false;$('auth-error').textContent='Cần xác thực lại: '+e.message}}
for(const b of document.querySelectorAll('[data-panel]'))b.addEventListener('click',()=>view(b.dataset.panel));
for(const b of document.querySelectorAll('[data-go]'))b.addEventListener('click',()=>view(b.dataset.go));
$('auth-submit').addEventListener('click',()=>void beginAuth());$('auth-input').addEventListener('keydown',e=>{if(e.key==='Enter')void beginAuth()});
$('project-select').addEventListener('change',e=>setProject(e.target.value));
function friendlyStoryId(title){
  const base=title.normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/đ/g,'d').replace(/Đ/g,'D')
    .toLowerCase().replace(/[^a-z0-9_-]+/g,'-')
    .replace(/^-+|-+$/g,'').slice(0,40)||'truyen-moi';
  let candidate=base;
  let number=2;
  while(allProjects.some(p=>p.id===candidate)){
    const suffix='-'+number++;
    candidate=base.slice(0,48-suffix.length)+suffix;
  }
  return candidate;
}
$('new-project').addEventListener('click',()=>{
  const dialog=$('new-story-dialog');
  $('new-story-form').reset();
  $('new-story-error').textContent='';
  dialog.showModal();
  $('new-story-name').focus();
});
$('new-story-cancel').addEventListener('click',()=>$('new-story-dialog').close());
$('new-story-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const name=$('new-story-name').value.trim();
  if(!name)return;
  const id=$('new-story-id').value.trim()||friendlyStoryId(name);
  const submit=$('new-story-create');
  submit.disabled=true;
  $('new-story-error').textContent='';
  try{
    const created=await request('/api/projects',{value:{title:name,id}});
    await loadProjects();
    $('new-story-dialog').close();
    setProject(created.id);
    alertMessage('Đã tạo truyện mới: '+created.title);
    view('outline');
  }catch(error){
    $('new-story-error').textContent=error.message||String(error);
  }finally{
    submit.disabled=false;
  }
});
$('refresh-dashboard').addEventListener('click',()=>fire(loadDashboard));
$('save-outline').addEventListener('click',()=>fire(async()=>{const v=JSON.parse($('outline-text').value);await request('/api/project/'+qp(project)+'/outline',{value:{value:v,confirm_existing:$('outline-confirm').checked}});alertMessage('Đã lưu dàn ý');await loadDashboard()}));
$('save-voice').addEventListener('click',()=>fire(async()=>{await request('/api/project/'+qp(project)+'/voice',{value:{text:$('voice-text').value}});alertMessage('Đã lưu Voice Bible')}));
$('create-plan').addEventListener('click',()=>fire(async()=>{const j=await request('/api/project/'+qp(project)+'/job',{value:{kind:'plan',payload:{premise:$('plan-premise').value,chapters:Number($('plan-count').value),cloud:$('plan-cloud').checked}}});alertMessage('Đang xếp hàng lập dàn ý #'+j.id);view('jobs')}));
$('load-candidate').addEventListener('click',()=>fire(async()=>{const x=await request('/api/project/'+qp(project)+'/candidate');if(!x.value)throw Error('Chưa có dàn ý ứng viên');$('outline-text').value=JSON.stringify(x.value,null,2);alertMessage('Đã hiển thị dàn ý ứng viên. Chưa ghi đè tệp hiện tại.')}));
$('accept-candidate').addEventListener('click',()=>fire(async()=>{if(!confirm('Chấp nhận dàn ý ứng viên?'))return;await request('/api/project/'+qp(project)+'/candidate-accept',{value:{}});await loadOutline();alertMessage('Đã chấp nhận dàn ý ứng viên')}));
$('refresh-jobs').addEventListener('click',()=>fire(loadJobs));
$('start-series').addEventListener('click',()=>fire(async()=>{const cc=$('cloud-critic').checked;if(cc&&!confirm('API đám mây có thể phát sinh chi phí và gửi dữ liệu cảnh ra ngoài. Tiếp tục?'))return;const j=await request('/api/project/'+qp(project)+'/job',{value:{kind:'series',payload:{cloud_critic:cc,semantic:$('semantic').checked}}});alertMessage('Đã tạo hàng đợi #'+j.id);await loadJobs()}));
$('reload-drafts').addEventListener('click',()=>fire(loadDrafts));$('draft-chapter').addEventListener('change',()=>{resetScene();$('draft-scene').replaceChildren();void fire(loadDrafts)});$('draft-scene').addEventListener('change',resetScene);
$('open-scene').addEventListener('click',()=>fire(openScene));$('download-chapter').addEventListener('click',()=>fire(downloadChapter));
$('edit-scene').addEventListener('click',()=>fire(async()=>{if(!selectedScene)throw Error('Hãy mở cảnh trước');$('manual-edit-box').hidden=false;$('manual-edit-text').value=$('draft-text').textContent;$('draft-text').hidden=true}));
$('cancel-scene-edit').addEventListener('click',()=>{$('manual-edit-box').hidden=true;$('draft-text').hidden=false});
$('save-scene-edit').addEventListener('click',()=>fire(async()=>{if(!selectedScene)throw Error('Hãy mở cảnh trước');if(!confirm('Lưu bản sửa? Tóm tắt chương sẽ cần duyệt lại.'))return;await request('/api/project/'+qp(project)+'/scene-edit',{value:{...selectedScene,text:$('manual-edit-text').value}});await openScene();alertMessage('Đã lưu bản sửa vào lịch sử phiên bản')}));
$('rewrite-scene').addEventListener('click',()=>fire(async()=>{if(!selectedScene)throw Error('Chọn cảnh để viết lại');if(!confirm('Viết lại cảnh sẽ làm tóm tắt chương cũ mất hiệu lực, giữ bản cũ trong lịch sử. Tiếp tục?'))return;const j=await request('/api/project/'+qp(project)+'/job',{value:{kind:'rewrite',payload:selectedScene}});alertMessage('Đã xếp hàng viết lại #'+j.id);view('jobs')}));
$('reload-memory').addEventListener('click',()=>fire(async()=>{await loadMemory();await loadCreative()}));
$('creative-refresh').addEventListener('click',()=>fire(loadCreative));
$('creative-enable').addEventListener('click',()=>fire(async()=>{
  if(!confirm('Chỉ bật Creative trên dự án sạch, chưa có cảnh/canon. Việc này tạo sidecar bền vững; tiếp tục?'))return;
  await request('/api/project/'+qp(project)+'/creative-enable',{value:{confirm:true}});
  await loadCreative();alertMessage('Creative đã bật. Hãy tạo và duyệt dữ kiện có nguồn.');
}));
$('creative-propose').addEventListener('click',()=>fire(creativePropose));
$('creative-note-add').addEventListener('click',()=>fire(async()=>{
  await request('/api/project/'+qp(project)+'/creative-note',{value:{
    action:'add',name:$('creative-note-name').value,purpose:$('creative-note-purpose').value,
    expected_effect:$('creative-note-effect').value
  }});
  $('creative-note-name').value='';$('creative-note-purpose').value='';$('creative-note-effect').value='';
  await loadCreative();
}));
$('memory-add').addEventListener('click',()=>fire(async()=>{await request('/api/project/'+qp(project)+'/memory',{value:{kind:$('memory-kind').value,subject:$('memory-subject').value,content:$('memory-content').value}});$('memory-content').value='';await loadMemory()}));
$('reload-library').addEventListener('click',()=>fire(loadLibrary));$('library-query').addEventListener('change',()=>fire(loadLibrary));
$('embed-library').addEventListener('click',()=>fire(async()=>{const j=await request('/api/project/'+qp(project)+'/job',{value:{kind:'embed',payload:{limit:30}}});alertMessage('Đã xếp hàng embedding #'+j.id);view('jobs')}));
$('upload-doc').addEventListener('click',()=>fire(async()=>{const f=$('doc-file').files[0];if(!f)throw Error('Hãy chọn tệp');if(f.size>8000000)throw Error('Tệp quá 8 MB');if(!$('doc-rights').checked)throw Error('Cần xác nhận quyền sử dụng');const params=new URLSearchParams({name:f.name,license:$('doc-license').value,rights:'yes'});const r=await fetch('/api/project/'+qp(project)+'/upload?'+params,{method:'POST',headers:{'X-Novel-Token':token,'Content-Type':'application/octet-stream'},body:f});const x=await r.json();if(!r.ok)throw Error(x.error);alertMessage(x.duplicate?'Tệp đã được nhập':'Đã nhập '+x.chunks+' đoạn. Hãy bấm Phân tích.');await loadLibrary()}));
$('create-backup').addEventListener('click',()=>fire(createBackup));
setInterval(()=>{if(token&&project&&document.visibilityState==='visible')void loadJobs().catch(()=>{})},4000);
void boot();
