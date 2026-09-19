import {versionsFor, chooseVersion, timelineFor, frameAt, keepRange} from './editor-model.mjs';
const $ = s => document.querySelector(s), ctx = $('#preview').getContext('2d');
const storageKey = `sprite-editor:v1:${location.pathname.replace(/[^/]*$/, '')}`;
let saved;
try { saved = JSON.parse(localStorage.getItem(storageKey)) || {}; } catch { saved = {}; }
saved.choices ||= {}; saved.drafts ||= {}; saved.catalog ||= {};
let plan, action = saved.action || null, tab = 'work', version, entry;
let frames = [], images = [], manifest, atlas, draft, draftKey, timeline = [], index = 0;
let shiftAnchor = null;
let playing = false, elapsed = 0, started = 0, serial = 0, audioReady = false;
const sound = $('#sound');
function persist() { try { localStorage.setItem(storageKey, JSON.stringify(saved)); }
  catch { $('#message').textContent = '浏览器存储不可用；请导出当前剪辑方案以保留修改。'; } }
function button(text, fn) { const b = document.createElement('button'); b.textContent = text; b.onclick = fn; return b; }
function message(text) { $('#message').textContent = text; }
async function json(path) { const r = await fetch(path, {cache:'no-store'}); if (!r.ok) throw Error(`无法加载 ${path}`); return r.json(); }
function stop() { playing = false; sound.pause(); $('#play').textContent = '播放'; }
function totalDuration() { const tail = timeline.at(-1); return tail ? tail.start + tail.duration : 0; }
function rate() { return draft.speed * draft.fps / (manifest?.fps || entry.fps || 4); }
function syncSound(force = false) {
  const cue = timeline[draft.audioStart - 1];
  if (!playing || !draft.audioEnabled || !audioReady || !cue || elapsed < cue.start) { sound.pause(); return; }
  const offset = (elapsed - cue.start) * rate();
  if (Number.isFinite(sound.duration) && offset >= sound.duration) { sound.pause(); return; }
  sound.playbackRate = Math.max(.0625, Math.min(16, rate()));
  if (force || Math.abs(sound.currentTime - offset) > .15) sound.currentTime = offset;
  if (sound.paused) sound.play().catch(() => {
    message('音效暂时无法播放，请再次点击播放或检查音频文件。');
  });
}
function play() {
  if (!draft || !timeline.length) return;
  if (elapsed >= totalDuration()) elapsed = 0;
  playing = true; started = performance.now() - elapsed * 1000;
  $('#play').textContent = '暂停'; syncSound(true); draw();
}
function seek(i) {
  stop(); index = i;
  elapsed = timeline.find(f => f.index === i)?.start || 0; draw();
}
function saveDraft() { saved.drafts[draftKey] = draft; persist(); }
function updateTimeline() {
  timeline = timelineFor(frames, draft);
  draft.audioStart = Math.max(1, Math.min(draft.audioStart || 1, timeline.length || 1));
  $('#audio-start').max = timeline.length || 1; $('#audio-start').value = draft.audioStart;
  $('#play').disabled = !timeline.length;
  $('#restart').disabled = $('#prev').disabled = $('#next').disabled = !timeline.length;
  $('#selection-summary').textContent = `保留 ${timeline.length} / ${frames.length} 帧 · 时长 ${totalDuration().toFixed(3)} 秒`;
  $('#timeline').replaceChildren(...timeline.map((f, n) => {
    const b = button(`${n+1} · 原 ${f.index+1}`, () => seek(f.index));
    b.dataset.timelineFrame = f.index; b.style.flexGrow = f.duration;
    b.title = `${f.start.toFixed(3)}–${(f.start+f.duration).toFixed(3)} 秒`;
    b.setAttribute('aria-label', `播放顺序 ${n+1}，原第 ${f.index+1} 帧，${b.title}`); return b;
  }));
  $('#timeline-empty').hidden = !!timeline.length;
  const included = new Set(timeline.map(f => f.index));
  document.querySelectorAll('.frame-card').forEach(card => {
    const i = Number(card.dataset.frame), kept = !draft.excluded.includes(i);
    card.classList.toggle('excluded', !kept); card.classList.toggle('outside', kept && !included.has(i));
    card.querySelector('.keep').setAttribute('aria-pressed', String(kept));
    card.querySelector('.remove').setAttribute('aria-pressed', String(!kept));
    card.querySelector('.frame-label').textContent = `${i+1} · ${!kept ? '已排除' : included.has(i) ? `播放 ${timeline.findIndex(f=>f.index===i)+1}` : '范围外'}`;
  });
}
function changed() {
  const resume = playing; stop(); updateTimeline(); index = timeline[0]?.index ?? index; elapsed = 0;
  saveDraft(); draw(); if (resume && timeline.length) play();
}
function setKept(i, kept) {
  const wasPlaying = playing;
  const excluded = new Set(draft.excluded); kept ? excluded.delete(i) : excluded.add(i);
  draft.excluded = [...excluded].sort((a,b)=>a-b); changed();
  if (!wasPlaying) seek(i);
}
function selectFrame(i, event, keep = false) {
  if (event.shiftKey && tab==='work' && draft) {
    const start = shiftAnchor ?? i;
    shiftAnchor = shiftAnchor === null ? i : null;
    draft.excluded = keepRange(draft.excluded, start, i);
    stop(); changed(); seek(i);
  } else {
    shiftAnchor = null;
    if (keep) setKept(i, true); else seek(i);
  }
}
function draw() {
  ctx.clearRect(0,0,576,576); ctx.imageSmoothingEnabled = false;
  if (frames.length) {
    const cell = frames[index]?.cell, im = images[index];
    if (cell && atlas?.complete && atlas.naturalWidth) {
      const crop = manifest?.derivation?.crop;
      const width = manifest?.derivation?.canvas_width || manifest?.canvas?.width || plan.workbench?.canvasWidth || cell.width;
      const height = manifest?.derivation?.canvas_height || manifest?.canvas?.height || plan.workbench?.canvasHeight || cell.height;
      const scale = Math.min(ctx.canvas.width/width, ctx.canvas.height/height);
      ctx.drawImage(atlas, cell.x, cell.y, cell.width, cell.height,
        (ctx.canvas.width-width*scale)/2+(crop?.[0] || 0)*scale,
        (ctx.canvas.height-height*scale)/2+(crop?.[1] || 0)*scale, cell.width*scale, cell.height*scale);
    } else if (im?.complete && im.naturalWidth) {
      const scale = Math.min(ctx.canvas.width/im.naturalWidth, ctx.canvas.height/im.naturalHeight);
      ctx.drawImage(im,(ctx.canvas.width-im.naturalWidth*scale)/2,(ctx.canvas.height-im.naturalHeight*scale)/2,im.naturalWidth*scale,im.naturalHeight*scale);
    }
  }
  const position = timeline.findIndex(f=>f.index===index);
  $('#frame').textContent = !timeline.length ? `原第 ${index+1} 帧 · 仅查看；没有可播放帧，请勾选至少一帧` :
    `原第 ${index+1} 帧 · ${position < 0 ? '已排除 / 仅查看' : `播放 ${position+1} / ${timeline.length}`} · ${elapsed.toFixed(2)} 秒`;
  document.querySelectorAll('[data-frame]').forEach(b=>b.classList.toggle('current',Number(b.dataset.frame)===index));
  document.querySelectorAll('[data-timeline-frame]').forEach(b=>b.classList.toggle('current',Number(b.dataset.timelineFrame)===index));
}
function buildFilmstrip(base) {
  $('#filmstrip').replaceChildren(...frames.map((f,i)=>{
    const card = document.createElement('div'); card.className = 'frame-card'; card.dataset.frame = i;
    const keep = button('✓',event=>selectFrame(i,event,true)); keep.className = 'keep'; keep.title = `保留第 ${i+1} 帧`;
    keep.setAttribute('aria-label',keep.title);
    const remove = button('×',()=>{shiftAnchor=null;setKept(i,false);}); remove.className = 'remove'; remove.title = `排除第 ${i+1} 帧`;
    remove.setAttribute('aria-label',remove.title);
    const view = button('',event=>selectFrame(i,event)); view.className='frame-view'; view.setAttribute('aria-label',`查看第 ${i+1} 帧`);
    if (f.cell && atlas) {
      const tile = document.createElement('span'), c=f.cell;
      const ratio=112/Math.max(c.width,c.height);
      tile.style.width=`${c.width*ratio}px`;tile.style.height=`${c.height*ratio}px`;
      tile.className='tile'; tile.style.backgroundImage=`url("${atlas.src}")`;
      tile.style.backgroundSize=`${manifest.atlas.width*ratio}px ${manifest.atlas.height*ratio}px`;
      tile.style.backgroundPosition=`-${c.x*ratio}px -${c.y*ratio}px`;view.append(tile);
    } else { const im = document.createElement('img'); im.src=base+f.file; im.alt=''; im.loading='lazy'; view.append(im); }
    const label=document.createElement('span'); label.className='frame-label';
    view.append(label); card.append(keep,remove,view); return card;
  }));
}
function numeric(id, value, fn) { const el=$(id);el.value=value;
 el.oninput=()=>{if(el.value!=='' && el.validity.valid){fn(Number(el.value));changed();}};
 el.onchange=()=>{
  const n=Number(el.value); el.value=Math.max(Number(el.min),Math.min(Number(el.max),Number.isFinite(n)?n:value));fn(Number(el.value));changed();
}; }
async function render() {
  shiftAnchor=null;
  const ticket=++serial;stop(); frames=[];images=[];atlas=null;manifest=null;audioReady=false;
  sound.removeAttribute('src'); sound.load(); $('#play').disabled=true;
  $('#filmstrip').replaceChildren(); $('#timeline').replaceChildren(); ctx.clearRect(0,0,576,576);
  entry=plan.actions.find(a=>a.action===action)||plan.actions[0];action=entry.action;
  const versions=versionsFor(entry,saved.catalog[action]);saved.catalog[action]=versions;persist();
  const selected=chooseVersion(versions,saved.choices[action]);
  version=tab==='work'?versions.find(v=>v.key===selected):entry[tab==='confirmed'?'confirmed':'binding'];
  $('#actions').replaceChildren(...plan.actions.map((a,i)=>{
    const b=button(`${i+1}. ${a.name}`,()=>{action=a.action;saved.action=action;persist();render().catch(showError);});b.classList.toggle('active',a.action===action);return b;
  }));
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  $('#title').textContent=entry.name;$('#budget').textContent='即时逐帧编辑 · 图片播放 + 独立音效';
  function versionButton(v, label) {
    const active=(version?.key||'reference')===v;
    const b=button(`${active?'✓ ':''}${label}`,()=>{saved.choices[action]=v;tab='work';persist();render().catch(showError);});
    b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));return b;
  }
  $('#candidates').replaceChildren(...(entry.frames?.length?[versionButton('reference','原版关键帧参考')]:[]),...versions.map((v,i)=>versionButton(v.key,`${v.label} · 待确认${i===versions.length-1?' · 最新':''}`)));
  $('#candidates').hidden=tab!=='work';
  $('#status').textContent=tab==='confirmed'?'仅展示工程适配器核验过的人工确认版本。':tab==='game'?'仅展示工程适配器提供的实际游戏绑定。':'版本由旧到新排列。勾选、排除后即可播放；每个版本的剪辑独立保存。';
  if(tab!=='work' && !version){
    timeline=[];draft=null;$('#selection-summary').textContent=tab==='confirmed'?'尚无已确认版本':'尚无游戏绑定记录';
    $('#frame').textContent='';$('#detail').textContent='';$('#resources').replaceChildren();
    document.querySelectorAll('#editing input,#editing select,#audio-controls input,#keep-all,#exclude-all,#export,#restart,#prev,#next').forEach(el=>el.disabled=true);
    message('原版参考与待确认剪辑不会自动成为确认或绑定记录。');return;
  }
  let base='';
  if(version){
    const m=await json(version.manifest);if(ticket!==serial)return;
    manifest=m;frames=m.frames.map(f=>({...f,duration_ticks:f.duration_ticks ?? (f.duration_seconds ? f.duration_seconds*m.fps : 1)}));base=version.manifest.slice(0,version.manifest.lastIndexOf('/')+1);
    if(m.atlas?.path && frames.every(f=>f.cell)){
      atlas=new Image();atlas.onload=()=>{if(ticket===serial)draw();};atlas.onerror=()=>message('图集加载失败，请检查素材文件。');atlas.src=base+m.atlas.path;
    }
    if(m.audio?.present && m.audio.path){sound.src=base+m.audio.path;audioReady=true;}
  }else frames=(entry.frames || []).map(file=>({file,duration_ticks:1}));
  if(!atlas)images=frames.map(f=>{const im=new Image();im.onload=()=>{if(ticket===serial)draw();};im.src=base+f.file;return im;});
  const fingerprint=JSON.stringify(manifest || frames);
  draftKey=JSON.stringify([action,version?.key||'reference',fingerprint]);
  draft={excluded:[],start:1,end:frames.length,fps:manifest?.fps||entry.fps||4,speed:1,loop:manifest?.loop??entry.loop,
    timing:'original',audioStart:1,audioEnabled:true,...(tab==='work'?saved.drafts[draftKey]:{})};
  if (![.5,1,2,3,4,5].includes(draft.speed)) draft.speed=1;
  $('#start').max=$('#end').max=frames.length;
  numeric('#start',draft.start,n=>{draft.start=Math.round(n);draft.end=Math.max(draft.start,draft.end);$('#end').value=draft.end;});
  numeric('#end',draft.end,n=>{draft.end=Math.round(n);draft.start=Math.min(draft.start,draft.end);$('#start').value=draft.start;});
  numeric('#fps',draft.fps,n=>draft.fps=n);
  numeric('#audio-start',draft.audioStart,n=>draft.audioStart=Math.round(n));
  for(const id of ['speed','timing']){$('#'+id).value=draft[id];$('#'+id).onchange=()=>{draft[id]=id==='speed'?Number($('#'+id).value):$('#'+id).value;changed();};}
  $('#loop').checked=draft.loop;$('#loop').onchange=()=>{draft.loop=$('#loop').checked;changed();};
  $('#audio-enabled').checked=draft.audioEnabled;$('#audio-enabled').disabled=!audioReady;
  $('#audio-enabled').onchange=()=>{draft.audioEnabled=$('#audio-enabled').checked;changed();};
  $('#audio-start').disabled=!audioReady;$('#audio-status').textContent=audioReady?'当前版本音效 · 随循环重新触发，结束或暂停时停止':'当前版本没有音轨';
  $('#resources').replaceChildren();
  for(const [href,label] of [[entry.prompt,'动作提示词'],[entry.opening,'生成首帧']]) {
    if(!href)continue;const a=document.createElement('a');a.href=href;a.target='_blank';a.textContent=label;$('#resources').append(a);
  }
  $('#detail').textContent=`${frames.length} 张原始帧 · 左上 ✓ 保留，右上 × 排除；点图片放大查看。保留原停留时长，或切换为每帧等长。`;
  message('剪辑自动保存在当前浏览器；导出方案可交给我继续制作。原素材不变，剪辑仍待确认。');
  buildFilmstrip(base);
  document.querySelectorAll('#editing input,#editing select,#keep-all,#exclude-all,#export,.keep,.remove').forEach(el=>el.disabled=tab!=='work');
  $('#audio-enabled').disabled=tab!=='work'||!audioReady;$('#audio-start').disabled=tab!=='work'||!audioReady;
  updateTimeline();index=timeline[0]?.index||0;elapsed=0;draw();
}
function showError(e){stop();timeline=[];draft=null;$('#play').disabled=$('#restart').disabled=true;message(e.message);}
$('#play').onclick=()=>{if(playing){elapsed=(performance.now()-started)/1000;stop();}else play();};
$('#restart').onclick=()=>{elapsed=0;index=timeline[0]?.index||0;play();};
function step(delta){if(!timeline.length)return;const pos=timeline.findIndex(f=>f.index===index);seek(timeline[(Math.max(pos,0)+delta+timeline.length)%timeline.length].index);}
$('#prev').onclick=()=>step(-1);$('#next').onclick=()=>step(1);
$('#keep-all').onclick=()=>{if(!draft)return;shiftAnchor=null;draft.excluded=[];changed();};
$('#exclude-all').onclick=()=>{if(!draft)return;shiftAnchor=null;draft.excluded=frames.map((_,i)=>i);changed();};
$('#export').onclick=()=>{
  if(!draft || tab!=='work')return;
  const value={schema:'sprite-edit-decision.v1',action,version:version?.key||'reference',approval:'pending_human_review',
    source_manifest:version?.manifest||null,source_atlas_sha256:manifest?.atlas?.sha256||null,source_snapshot:manifest||frames,...draft,
    selected_frames_1based:timeline.map(f=>f.index+1),timeline:timeline.map(f=>({frame_1based:f.index+1,start_seconds:f.start,duration_seconds:f.duration})),
    audio:{path:sound.getAttribute('src')||null,start_playback_frame_1based:draft.audioStart,enabled:draft.audioEnabled},preview_mode:'frames-and-audio'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`${action}-sprite-edit.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render().catch(showError);});
document.addEventListener('keydown',e=>{
  if (!['ArrowLeft','ArrowRight'].includes(e.key) || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.isComposing) return;
  const target=e.target;
  if (target.closest('input,select,textarea') || target.isContentEditable || !frames.length) return;
  e.preventDefault();
  // Keyboard inspection follows every card, including excluded/out-of-range frames.
  seek((index+(e.key==='ArrowLeft'?-1:1)+frames.length)%frames.length);
  const card=$('#filmstrip').querySelector(`[data-frame="${index}"]`);
  card?.querySelector('.frame-view')?.focus({preventScroll:true});
  card?.scrollIntoView({block:'nearest',inline:'nearest'});
});
window.addEventListener('blur',()=>{shiftAnchor=null;});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
sound.onerror=()=>{audioReady=false;message('当前音轨无法加载，帧图仍可正常播放。');};
function tick(now){
  if(playing&&timeline.length){
    elapsed=(now-started)/1000;const duration=totalDuration();
    if(elapsed>=duration){
      if(draft.loop){elapsed%=duration;started=now-elapsed*1000;sound.pause();syncSound(true);}
      else {elapsed=duration;index=timeline.at(-1).index;stop();draw();}
    }
    if(playing){index=timeline[Math.max(0,frameAt(timeline,elapsed))].index;syncSound();draw();}
  }
  requestAnimationFrame(tick);
}
async function refresh(initial=false){
  const p=await json('production-plan.json');
  if(!p.actions?.length)throw Error('工作台需要至少一个动作');
  document.querySelector('h1').textContent=document.title=p.title||'Sprite 即时编辑工作台';
  const changed=JSON.stringify(plan)!==JSON.stringify(p);plan=p;
  if(initial||changed)await render();
}
refresh(true).then(()=>requestAnimationFrame(tick)).catch(showError);
setInterval(()=>refresh().catch(()=>{}),10000);
