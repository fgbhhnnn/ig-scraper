const $=id=>document.getElementById(id);
const api=async(u,b)=>{const r=await fetch(u,b===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()};
const lines=id=>$(id).value.split(/\n/).map(s=>s.trim()).filter(Boolean);
const words=id=>$(id).value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function msg(id,t,ok){$(id).textContent=t;$(id).className=ok?'ok':'err'}
function show(p){document.querySelectorAll('section').forEach(s=>s.hidden=s.id!=='p-'+p);document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.dataset.p===p));if(p==='results')loadResults();localStorage.page=p}
document.querySelectorAll('nav a').forEach(a=>a.onclick=()=>show(a.dataset.p));
const PK={instagram:['ckstat','IG: '],facebook:['fbstat','FB: '],tiktok:['ttstat','TT: ']};
function ckPill(p,ok,t){const e=$(PK[p][0]);e.textContent=PK[p][1]+t;e.className='pill '+(ok?'ok':'bad')}
const CKI=p=>({facebook:['fbcookie','fbmsg'],tiktok:['ttcookie','ttmsg']}[p]||['cookie','ckmsg']);
async function saveCookie(p){const[ta,mm]=CKI(p);msg(mm,'校验中…',1);const b={platform:p,cookie:$(ta).value};if(p==='tiktok'){['tt_device_id','tt_user_agent'].forEach(k=>b[k]=$(k).value);if($('tt_ms_token').value)b.tt_ms_token=$('tt_ms_token').value}const d=await api('/api/cookie',b);
 if(d.ok){msg(mm,'✅ 有效，已保存。登录用户 ID：'+d.user_id,1);ckPill(p,1,'已登录');$(ta).value=''}else{msg(mm,d.error);ckPill(p,0,'无效')}}
async function checkCookie(p){const[,mm]=CKI(p);msg(mm,'检测中…',1);const d=await api('/api/cookie/check?platform='+p);
 d.ok?(msg(mm,'✅ 当前 Cookie 有效，用户 ID：'+d.user_id,1),ckPill(p,1,'已登录')):(msg(mm,'❌ '+(d.error||'无效')),ckPill(p,0,d.error==='未填写'?'未填写':'无效'))}
async function loadCfg(){const c=await api('/api/config');$('addr').textContent='http://127.0.0.1:'+c.running_port;$('port').value=c.port;$('ai_base').value=c.ai_base;$('ai_key').placeholder=c.ai_key_masked?('已保存 '+c.ai_key_masked+'（留空=不变）'):'sk-…';
 $('ai_model').innerHTML=c.ai_model?`<option>${esc(c.ai_model)}</option>`:'<option value="">(先获取模型)</option>';$('delay_min').value=c.delay_min;$('fb_delay_min').value=c.fb_delay_min;$('fb_delay_max').value=c.fb_delay_max;$('delay_max').value=c.delay_max;$('ddir').textContent='数据目录：'+c.data_dir;
 if(c.has_cookie)checkCookie('instagram');else ckPill('instagram',0,'未填写');ckPill('facebook',c.has_fb_cookie,c.has_fb_cookie?'已保存':'未填写');ckPill('tiktok',c.has_tt_cookie,c.has_tt_cookie?'已保存':'未填写');$('tt_device_id').value=c.tt_device_id||'';$('tt_user_agent').value=c.tt_user_agent||'';$('tt_ms_token').placeholder=c.tt_ms_token_set?'已保存（留空=保持不变）':$('tt_ms_token').placeholder;$('tt_delay_min').value=c.tt_delay_min;$('tt_delay_max').value=c.tt_delay_max;loadSigner()}
async function fetchModels(){msg('mmsg','获取中…',1);const d=await api('/api/models',{ai_base:$('ai_base').value,ai_key:$('ai_key').value});
 if(!d.ok)return msg('mmsg',d.error);const cur=$('ai_model').value;$('ai_model').innerHTML=d.models.map(m=>`<option ${m===cur?'selected':''}>${esc(m)}</option>`).join('');msg('mmsg','✅ 共 '+d.models.length+' 个模型',1)}
async function saveSettings(){const b={ai_base:$('ai_base').value.trim(),ai_model:$('ai_model_manual').value.trim()||$('ai_model').value,delay_min:+$('delay_min').value||1.5,delay_max:+$('delay_max').value||3,fb_delay_min:+$('fb_delay_min').value||1.5,fb_delay_max:+$('fb_delay_max').value||3,tt_delay_min:+$('tt_delay_min').value||1.5,tt_delay_max:+$('tt_delay_max').value||3,port:+$('port').value||8765};
 if($('ai_key').value)b.ai_key=$('ai_key').value.trim();await api('/api/config',b);$('ai_key').value='';msg('smsg','✅ 已保存',1);loadCfg()}
function merge(id,arr){const old=$('ai_append').checked?lines(id):[];const s=new Set(old.map(x=>x.toLowerCase()));arr.forEach(x=>{if(!s.has(x.toLowerCase())){s.add(x.toLowerCase());old.push(x)}});$(id).value=old.join('\n')}
async function aiExpand(){msg('aimsg','AI 裂变中…（约 10-60 秒）',1);const d=await api('/api/expand',{keywords:lines('keywords'),hashtags:lines('hashtags'),info:lines('phrases')});
 if(!d.ok)return msg('aimsg',d.error);merge('keywords',d.keywords);merge('hashtags',d.hashtags);merge('phrases',d.comment_phrases);
 msg('aimsg',`✅ 关键词 ${d.keywords.length}、标签 ${d.hashtags.length}、评论短语 ${d.comment_phrases.length}`,1)}
const FKEYS=['tt_comment_pages','fb_comment_pages','platform','content_type','mode','max_videos','search_pages','comment_pages','min_comments','min_plays','date_from','date_to','must_words','exclude_words','keywords','hashtags','phrases'];
function params(){FKEYS.forEach(k=>localStorage['f_'+k]=$(k).value);['skip_existing','use_default_rules','question_mark','fb_fetch_views'].forEach(k=>localStorage['f_'+k]=$(k).checked?1:0);
 return{platform:$('platform').value,content_type:$('content_type').value,fb_fetch_views:$('fb_fetch_views').checked,fb_comment_pages:+$('fb_comment_pages').value||2,tt_comment_pages:+$('tt_comment_pages').value||2,mode:$('mode').value,max_videos:+$('max_videos').value,search_pages:+$('search_pages').value,comment_pages:+$('comment_pages').value,min_comments:+$('min_comments').value,min_plays:+$('min_plays').value,
 date_from:$('date_from').value,date_to:$('date_to').value,must_words:words('must_words'),exclude_words:words('exclude_words'),keywords:lines('keywords'),hashtags:lines('hashtags'),comment_phrases:lines('phrases'),
 skip_existing:$('skip_existing').checked,use_default_rules:$('use_default_rules').checked,question_mark:$('question_mark').checked}}
function restore(){FKEYS.forEach(k=>{if(localStorage['f_'+k]!==undefined)$(k).value=localStorage['f_'+k]});['skip_existing','use_default_rules','question_mark','fb_fetch_views'].forEach(k=>{if(localStorage['f_'+k]!==undefined)$(k).checked=localStorage['f_'+k]==='1'})}
async function startTask(){const d=await api('/api/task/start',params());if(!d.ok)return msg('tmsg',d.error);logN=0;$('r_log').textContent='';lastRun=d.run_id;show('run');poll()}
async function stopTask(){await api('/api/task/stop',{})}
let logN=0,timer=null,lastRun=null;
async function poll(){clearTimeout(timer);const s=await api('/api/task/status?since='+logN);
 if(s.log_total<logN){logN=0;$('r_log').textContent=''}
 $('r_stage').textContent=s.stage;$('r_matched').textContent=s.matched+' / '+s.target;$('r_scanned').textContent=s.scanned;$('r_skipped').textContent=s.skipped;
 $('r_bar').style.width=Math.min(100,s.target?s.matched/s.target*100:0)+'%';$('r_cur').textContent=s.current;$('r_cur').href=s.current||'#';
 if(s.logs.length){$('r_log').textContent+=s.logs.join('\n')+'\n';$('r_log').scrollTop=1e9}logN=s.log_total;if(s.run_id)lastRun=s.run_id;
 if(s.running)timer=setTimeout(poll,1500)}
let R=[],sk='question_count',sd=-1;
async function loadResults(){const p=new URLSearchParams({platform:$('f_platform').value,content_type:$('f_ctype').value});if($('only_run').checked&&lastRun)p.set('run_id',lastRun);R=await api('/api/results?'+p);renderResults()}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;sd=sk===k?-sd:-1;sk=k;renderResults()});
function renderResults(){const q=$('q').value.toLowerCase();let rs=R.filter(r=>!q||[r.account,r.caption,r.sample_questions,r.source].join(' ').toLowerCase().includes(q));
 rs.sort((a,b)=>{const x=a[sk],y=b[sk];return(typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y)))*sd});
 $('rcount').textContent=`共 ${rs.length} 条（数据库 ${R.length} 条）`;
 $('tb').innerHTML=rs.map(r=>{const fb=r.platform==='facebook',tt=r.platform==='tiktok';return`<tr><td><span class="tag ${fb?'fb':tt?'tt':'ig'}">${fb?'Facebook':tt?'TikTok':'Instagram'}</span></td><td>${r.content_type==='post'?'帖子':'视频'}</td>
 <td>${fb?esc(r.account):`<a href="${tt?'https://www.tiktok.com/@':'https://www.instagram.com/'}${esc(r.account)}${tt?'':'/'}" target="_blank">${esc(r.account)}</a>`}</td><td><a href="${esc(r.url)}" target="_blank">${fb?'打开':esc(r.shortcode)}</a></td>
 <td class="cap">${esc((r.caption||'').slice(0,120))}</td><td class="n">${(r.plays?r.plays.toLocaleString():'-')}</td><td class="n">${(r.likes||0).toLocaleString()}</td><td class="n">${r.comment_count}</td><td class="n">${r.shares==null?'-':r.shares.toLocaleString()}</td><td class="n"><b>${r.question_count}</b></td>
 <td class="q">${esc(r.sample_questions).replace(/ \|\| /g,'<br>')}</td><td>${esc(r.publish_date)}</td><td>${esc(r.source)}</td></tr>`}).join('')}
function exp(f){const p=new URLSearchParams({fmt:f,q:$('q').value,platform:$('f_platform').value,content_type:$('f_ctype').value});if($('only_run').checked&&lastRun)p.set('run_id',lastRun);location.href='/api/export?'+p}
async function clearDb(){if(confirm('确定清空本地数据库？（包括「已抓过」记录）')){await api('/api/results/clear',{});loadResults()}}
async function quitApp(){if(confirm('退出程序？')){await api('/api/quit',{});document.body.innerHTML='<h2 style="padding:40px">程序已退出，可以关闭此页面。</h2>'}}
restore();loadCfg();show(location.hash.slice(1)||localStorage.page||'cookie');api('/api/task/status').then(s=>{if(s.running){show('run');poll()}});

async function loadSigner(){const d=await api('/api/tt/signer');$('ttsign').textContent=d.msg;$('ttsign').className=d.ok?'ok':'err'}
async function ttSigner(f){$('ttsign').textContent='安装中…';let d;if(f){const fd=new FormData();fd.append('file',f);d=await(await fetch('/api/tt/signer',{method:'POST',body:fd})).json()}else d=await api('/api/tt/signer',{});$('ttsign').textContent=d.msg;$('ttsign').className=d.ok?'ok':'err'}
