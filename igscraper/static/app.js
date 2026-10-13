const $=id=>document.getElementById(id);
const api=async(u,b)=>{const r=await fetch(u,b===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()};
const lines=id=>$(id).value.split(/\n/).map(s=>s.trim()).filter(Boolean);
const words=id=>$(id).value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function msg(id,t,ok){$(id).textContent=t;$(id).className=ok?'ok':'err'}
function show(p){document.querySelectorAll('section').forEach(s=>s.hidden=s.id!=='p-'+p);document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.dataset.p===p));if(p==='results')loadResults();if(p==='run')poll();if(p==='comments'){cLoad();cPoll()}if(p==='ai'){aList();aPoll()}localStorage.page=p}
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
 if(c.has_cookie)checkCookie('instagram');else ckPill('instagram',0,'未填写');ckPill('facebook',c.has_fb_cookie,c.has_fb_cookie?'已保存':'未填写');ckPill('tiktok',c.has_tt_cookie,c.has_tt_cookie?'已保存':'未填写');$('tt_device_id').value=c.tt_device_id||'';$('tt_user_agent').value=c.tt_user_agent||'';$('tt_ms_token').placeholder=c.tt_ms_token_set?'已保存（留空=保持不变）':$('tt_ms_token').placeholder;$('tt_delay_min').value=c.tt_delay_min;$('tt_delay_max').value=c.tt_delay_max;['ai_fps','ai_max_images','ai_stt_model','ai_vision','ai_comment_pages','ai_comments_send','ai_stt_provider','el_lang'].forEach(k=>$(k).value=c[k]??'');$('el_model').value=c.el_model||'scribe_v2';$('el_key').value='';$('el_key').placeholder=c.el_key_masked?'已保存 '+c.el_key_masked+'（留空=保持不变）':'sk_…';sttShow();loadSigner()}
async function fetchModels(){msg('mmsg','获取中…',1);const d=await api('/api/models',{ai_base:$('ai_base').value,ai_key:$('ai_key').value});
 if(!d.ok)return msg('mmsg',d.error);const cur=$('ai_model').value;$('ai_model').innerHTML=d.models.map(m=>`<option ${m===cur?'selected':''}>${esc(m)}</option>`).join('');msg('mmsg','✅ 共 '+d.models.length+' 个模型',1)}
async function saveSettings(){const b={ai_base:$('ai_base').value.trim(),ai_model:$('ai_model_manual').value.trim()||$('ai_model').value,delay_min:+$('delay_min').value||1.5,delay_max:+$('delay_max').value||3,fb_delay_min:+$('fb_delay_min').value||1.5,fb_delay_max:+$('fb_delay_max').value||3,tt_delay_min:+$('tt_delay_min').value||1.5,tt_delay_max:+$('tt_delay_max').value||3,port:+$('port').value||8765,ai_fps:+$('ai_fps').value||1,ai_max_images:$('ai_max_images').value?+$('ai_max_images').value:'',ai_stt_model:$('ai_stt_model').value.trim(),ai_stt_provider:$('ai_stt_provider').value,el_key:$('el_key').value.trim(),el_model:$('el_model').value,el_lang:$('el_lang').value,ai_vision:$('ai_vision').value,ai_comment_pages:+$('ai_comment_pages').value||5,ai_comments_send:+$('ai_comments_send').value||120};
 if($('ai_key').value)b.ai_key=$('ai_key').value.trim();await api('/api/config',b);$('ai_key').value='';msg('smsg','✅ 已保存',1);loadCfg()}
function merge(id,arr){const old=$('ai_append').checked?lines(id):[];const s=new Set(old.map(x=>x.toLowerCase()));arr.forEach(x=>{if(!s.has(x.toLowerCase())){s.add(x.toLowerCase());old.push(x)}});$(id).value=old.join('\n');chipRender(id)}
async function aiExpand(){msg('aimsg','AI 裂变中…（约 10-60 秒）',1);const d=await api('/api/expand',{keywords:lines('keywords'),hashtags:lines('hashtags'),info:lines('phrases')});
 if(!d.ok)return msg('aimsg',d.error);merge('keywords',d.keywords);merge('hashtags',d.hashtags);merge('phrases',d.comment_phrases);
 msg('aimsg',`✅ 关键词 ${d.keywords.length}、标签 ${d.hashtags.length}、评论短语 ${d.comment_phrases.length}`,1)}
const FKEYS=['cf_expr','cf_min','cf_pages','tt_comment_pages','fb_comment_pages','platform','content_type','mode','max_videos','search_pages','comment_pages','min_comments','min_plays','date_from','date_to','must_words','exclude_words','keywords','hashtags','phrases'];
function params(){FKEYS.forEach(k=>localStorage['f_'+k]=$(k).value);['skip_existing','use_default_rules','question_mark','fb_fetch_views'].forEach(k=>localStorage['f_'+k]=$(k).checked?1:0);
 return{platform:$('platform').value,content_type:$('content_type').value,fb_fetch_views:$('fb_fetch_views').checked,fb_comment_pages:+$('fb_comment_pages').value||2,tt_comment_pages:+$('tt_comment_pages').value||2,mode:$('mode').value,max_videos:+$('max_videos').value,search_pages:+$('search_pages').value||0,comment_pages:+$('comment_pages').value,min_comments:+$('min_comments').value,min_plays:+$('min_plays').value,
 date_from:$('date_from').value,date_to:$('date_to').value,must_words:words('must_words'),exclude_words:words('exclude_words'),keywords:lines('keywords'),hashtags:lines('hashtags'),comment_phrases:lines('phrases'),
 cf_expr:$('cf_expr').value.trim(),cf_min:+$('cf_min').value||1,cf_pages:+$('cf_pages').value||5,skip_existing:$('skip_existing').checked,use_default_rules:$('use_default_rules').checked,question_mark:$('question_mark').checked}}
function restore(){if(localStorage.sp_v!=='2'){if(['4','3',''].includes(localStorage.f_search_pages))delete localStorage.f_search_pages;localStorage.sp_v='2'}FKEYS.forEach(k=>{if(localStorage['f_'+k]!==undefined)$(k).value=localStorage['f_'+k]});['skip_existing','use_default_rules','question_mark','fb_fetch_views'].forEach(k=>{if(localStorage['f_'+k]!==undefined)$(k).checked=localStorage['f_'+k]==='1'})}
async function startTask(){if(!taskValid())return msg('tmsg','请先修正标红的项');const d=await api('/api/task/start',params());if(!d.ok)return msg('tmsg',d.error);logN=0;LOGS=[];$('r_log').innerHTML='';lastRun=d.run_id;show('run');poll()}
async function stopTask(){await api('/api/task/stop',{})}
let logN=0,timer=null,lastRun=null;
let LOGS=[],LGF='all';
function lvl(t){if(/❌|⛔|出错|失败/.test(t))return'err';if(/429|限流|风控|⚠️|等待/.test(t))return'warn';if(/✅/.test(t))return'ok';if(/^— |^· |跳过|不足|无提问|不符合条件/.test(t))return'skip';if(/开始|结束|已登录|搜索/.test(t))return'step';return'info'}
const LIC={err:'✖',warn:'⚠',ok:'✔',skip:'·',step:'▸',info:'•'};
function logLine(l){const m=l.match(/^(\d\d:\d\d:\d\d) ([\s\S]*)$/)||[0,'',l];const lv=lvl(m[2]);let t=esc(m[2].replace(/^(✅|❌|⛔|⚠️|— )\s*/,'')).replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank">$1</a>');return`<div class="lg ${lv}" data-l="${lv}"><span class="lt">${m[1]}</span><span class="li">${LIC[lv]}</span><span class="lm">${t}</span></div>`}
function logRender(add){const box=$('r_log');const f=x=>LGF==='all'||lvl(x)===LGF||(LGF==='warn'&&lvl(x)==='warn');
 if(add)box.insertAdjacentHTML('beforeend',add.filter(f).map(logLine).join(''));else box.innerHTML=LOGS.filter(f).map(logLine).join('')||'<p class="hint">暂无日志</p>';if($('lg_auto').checked)box.scrollTop=1e9}
document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('#lg_f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#lg_f button').forEach(x=>x.classList.toggle('on',x===b));LGF=b.dataset.l;logRender()})});
function logCopy(){cp(LOGS.join('\n'))}function logClear(){$('r_log').innerHTML='';LOGS=[]}
const fmtT=s=>{s=Math.max(0,Math.round(s));return s>=3600?Math.floor(s/3600)+'时'+Math.floor(s%3600/60)+'分':s>=60?Math.floor(s/60)+'分'+String(s%60).padStart(2,'0')+'秒':s+'秒'};
let runS=null;
async function poll(){clearTimeout(timer);const s=await api('/api/task/status?since='+logN);runS=s;
 if(s.log_total<logN){logN=0;LOGS=[];$('r_log').innerHTML=''}
 if(s.logs.length){if(!LOGS.length&&logN===0)$('r_log').innerHTML='';LOGS.push(...s.logs);logRender(s.logs)}else if(!LOGS.length)$('r_log').innerHTML='<p class="hint">暂无日志</p>';logN=s.log_total;if(s.run_id)lastRun=s.run_id;
 runRender(s);if(s.running)timer=setTimeout(poll,1500)}
function runRender(s){const P=s.platform;$('rp_plat').textContent=PN[P]||'—';$('rp_plat').className='badge '+(P||'');
 const srcs=s.sources||[];$('rp_title').textContent=s.run_id?(s.cf_expr?'按评论筛选抓取':'同行内容抓取'):'还没有运行任务';$('rp_kw').innerHTML=srcs.slice(0,6).map(x=>`<span class="kwc">${esc(x.src)}</span>`).join('')+(srcs.length>6?`<span class="hint">等 ${srcs.length} 个</span>`:'');
 const st=s.running?'run':!s.run_id?'idle':s.error?'err':s.stage==='已停止'?'stop':'done';$('rp_state').className='state '+st;$('rp_state').textContent={run:'● 运行中',idle:'空闲',err:'出错',stop:'已停止',done:'✓ 已完成'}[st];$('rp_stop').hidden=!s.running;
 const el=s.started?((s.ended||Date.now()/1000)-s.started):0;$('rp_start').textContent=s.started?new Date(s.started*1000).toTimeString().slice(0,5):'-';$('rp_elapsed').textContent=s.started?fmtT(el):'-';
 const pr=s.target?Math.min(1,s.matched/s.target):0;$('rp_eta_w').hidden=!(s.running&&s.matched>0&&pr<1);if(s.running&&s.matched>0)$('rp_eta').textContent='约 '+fmtT(el/pr*(1-pr));
 $('rp_stage').textContent=s.stage;$('rp_kept').textContent=s.matched;$('rp_target').textContent=s.target;$('rp_keptlbl').textContent=s.cf_expr?'条已保留（评论命中）':'条已保存（有提问）';
 $('r_bar').style.width=(pr*100)+'%';$('r_bar').className=st==='run'?'live':st==='err'?'bad':'';$('r_cur').textContent=s.current||'-';$('r_cur').href=s.current||'#';
 const T=[['🔎','搜到内容',s.searched||0,''],['🧐',s.cf_expr?'已检查（读评论）':'已检查评论区',s.scanned,''],[ '💾',s.cf_expr?'保留（命中）':'已保存',s.matched,'ok'],['⏭','跳过已有',s.skipped,''],['🚫','不符合条件',s.filtered||0,'',Object.entries(s.filter_why||{}).map(([k,n])=>k+' '+n).join('，')],['💬','读取评论',s.comments||0,''],['⚠','错误 / 限流',`${s.errors||0} / ${s.ratelimits||0}`,(s.errors||s.ratelimits)?'bad':'']];
 if(s.cf_expr)T.push(['🎯','命中率',s.scanned?Math.round(s.matched/s.scanned*100)+'%':'-','']);
 $('rp_tiles').innerHTML=T.map(t=>`<div class="tile ${t[3]}" title="${esc(t[4]||'')}"><span class="ti">${t[0]}</span><div><b>${typeof t[2]==='number'?t[2].toLocaleString():esc(t[2])}</b><i>${t[1]}</i></div></div>`).join('');
 $('rp_srcw').hidden=!srcs.length;$('rp_srcn').textContent=srcs.length?`${srcs.filter(x=>x.state==='done').length}/${srcs.length} 完成`:'';const mk=Math.max(1,...srcs.map(x=>x.checked));
 $('rp_srcs').innerHTML=srcs.map(x=>`<div class="src ${x.state}"><span class="sd"></span><span class="sn" title="${esc(x.src)}">${esc(x.src)}</span><div class="sbar"><i style="width:${x.checked/mk*100}%"></i><b style="width:${x.kept/mk*100}%"></b></div><span class="sv">${x.kept}<small>/${x.checked} · 搜到 ${x.found}${x.filtered?' · 不符 '+x.filtered:''}</small></span></div>`).join('');
 const R=s.recent||[];$('rp_recent').innerHTML=R.length?R.map(v=>`<a class="rc" href="${esc(v.url)}" target="_blank"><div class="rct">${v.cover?`<img src="${esc(v.cover)}" referrerpolicy="no-referrer" onerror="this.remove()">`:''}<span>${v.platform==='tiktok'?'♪':'▶'}</span></div><div class="rcb"><b>@${esc(v.account)}</b><div class="hint">${esc((v.caption||'').slice(0,40))}</div><div class="rcs"><span>▶ ${fmtN(v.plays)}</span><span>♥ ${fmtN(v.likes)}</span><span>💬 ${fmtN(v.comment_count)}</span><span class="hit">${v.cf_count!=null?'命中 '+v.cf_count:'提问 '+(v.question_count||0)}</span></div></div></a>`).join(''):'<p class="hint">还没有保存的内容</p>'}
setInterval(()=>{if(runS&&runS.running&&!$('p-run').hidden)runRender(runS)},1000);
const SEL=new Set();let R=[],sk='question_count',sd=-1;
async function loadResults(){const p=new URLSearchParams({platform:$('f_platform').value,content_type:$('f_ctype').value});if($('only_run').checked&&lastRun)p.set('run_id',lastRun);R=await api('/api/results?'+p);renderResults()}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;sd=sk===k?-sd:-1;sk=k;renderResults()});
function renderResults(){const q=$('q').value.toLowerCase();let rs=R.filter(r=>!q||[r.account,r.caption,r.sample_questions,r.source].join(' ').toLowerCase().includes(q));
 rs.sort((a,b)=>{const x=a[sk],y=b[sk];return(typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y)))*sd});
 $('rcount').textContent=`共 ${rs.length} 条（数据库 ${R.length} 条）`;
 $('tb').innerHTML=rs.map(r=>{const fb=r.platform==='facebook',tt=r.platform==='tiktok';const k=r.platform+'|'+r.shortcode;return`<tr><td><input type="checkbox" class="sel" value="${esc(k)}" ${SEL.has(k)?'checked':''} onchange="this.checked?SEL.add(this.value):SEL.delete(this.value)" style="width:auto"></td><td><span class="tag ${fb?'fb':tt?'tt':'ig'}">${fb?'Facebook':tt?'TikTok':'Instagram'}</span></td><td>${r.content_type==='post'?'帖子':'视频'}</td>
 <td>${fb?esc(r.account):`<a href="${tt?'https://www.tiktok.com/@':'https://www.instagram.com/'}${esc(r.account)}${tt?'':'/'}" target="_blank">${esc(r.account)}</a>`}</td><td><a href="${esc(r.url)}" target="_blank">${fb?'打开':esc(r.shortcode)}</a></td>
 <td class="cap">${esc((r.caption||'').slice(0,120))}</td><td class="n">${(r.plays?r.plays.toLocaleString():'-')}</td><td class="n">${(r.likes||0).toLocaleString()}</td><td class="n">${r.comment_count}</td><td class="n">${r.shares==null?'-':r.shares.toLocaleString()}</td><td class="n"><b>${r.question_count}</b></td>
 <td class="q">${esc(r.sample_questions).replace(/ \|\| /g,'<br>')}</td><td class="n">${r.cf_count==null?'-':`<details class="cfd"><summary><b>${r.cf_count}</b> 条</summary><div>${esc(r.cf_samples||'').split(' || ').map(x=>`<p>${x}</p>`).join('')}</div></details>`}</td><td>${esc(r.publish_date)}</td><td>${esc(r.source)}</td><td>${r.content_type==='post'?'':`<button class="ghost" onclick="aGo({key:'${esc(k)}'})">🤖 AI 分析</button>`}</td></tr>`}).join('')}
function exp(f){const p=new URLSearchParams({fmt:f,q:$('q').value,platform:$('f_platform').value,content_type:$('f_ctype').value});if($('only_run').checked&&lastRun)p.set('run_id',lastRun);location.href='/api/export?'+p}
async function clearDb(){if(confirm('确定清空本地数据库？（包括「已抓过」记录）')){await api('/api/results/clear',{});loadResults()}}
async function quitApp(){if(confirm('退出程序？')){await api('/api/quit',{});document.body.innerHTML='<h2 style="padding:40px">程序已退出，可以关闭此页面。</h2>'}}
restore();loadCfg();show(location.hash.slice(1)||localStorage.page||'cookie');api('/api/task/status').then(s=>{if(s.running){show('run');poll()}});

async function loadSigner(){const d=await api('/api/tt/signer');$('ttsign').textContent=d.msg;$('ttsign').className=d.ok?'ok':'err'}
async function ttSigner(f){$('ttsign').textContent='安装中…';let d;if(f){const fd=new FormData();fd.append('file',f);d=await(await fetch('/api/tt/signer',{method:'POST',body:fd})).json()}else d=await api('/api/tt/signer',{});$('ttsign').textContent=d.msg;$('ttsign').className=d.ok?'ok':'err'}

function selAll(v){document.querySelectorAll('.sel').forEach(c=>{c.checked=v;v?SEL.add(c.value):SEL.delete(c.value)})}
const cParams=()=>({max_comments:+$('c_max').value||0,max_pages:+$('c_pages').value||0,replies:$('c_replies').checked,phrases:$('c_phr').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean)});
async function cGo(b){const d=await api('/api/ctask/start',Object.assign(cParams(),b));if(!d.ok)return alert(d.error);cLogN=0;$('c_log').textContent='';cRun=d.run_id;show('comments')}
function crawlSel(){if(!SEL.size)return alert('请先勾选要爬评论的内容');cGo({keys:[...SEL]})}
function crawlFiltered(){if(!confirm('将爬取当前筛选条件下的全部内容的评论，确定？'))return;cGo({use_filtered:1,q:$('q').value,platform:$('f_platform').value,content_type:$('f_ctype').value})}
function cStart(){const u=$('c_urls').value.split(/\n/).map(s=>s.trim()).filter(Boolean);if(!u.length)return alert('请粘贴链接');cGo({urls:u})}
let cLogN=0,cTimer=null,cRun=null,cT2=null;
async function cPoll(){clearTimeout(cTimer);const s=await api('/api/ctask/status?since='+cLogN);if(s.log_total<cLogN){cLogN=0;$('c_log').textContent=''}
 $('c_stage').textContent=s.stage;$('c_done').textContent=s.scanned+' / '+s.target;$('c_total').textContent=s.matched;$('c_bar').style.width=(s.target?s.scanned/s.target*100:0)+'%';
 if(s.logs.length){$('c_log').textContent+=s.logs.join('\n')+'\n';$('c_log').scrollTop=1e9}cLogN=s.log_total;if(s.run_id)cRun=s.run_id;
 if(s.running){cTimer=setTimeout(cPoll,1500);if(Date.now()-(cPoll.last||0)>5000){cPoll.last=Date.now();cLoad()}}else if(cPoll.wasRunning)cLoad();cPoll.wasRunning=s.running}
function cQ(){const p=new URLSearchParams({expr:$('c_expr').value,platform:$('c_plat').value,ex_words:$('c_exw').value,ex_users:$('c_exu').value,hide_author:$('c_hauthor').checked?1:0,hide_spam:$('c_hspam').checked?1:0,only_matched:$('c_onlym').checked?1:0});if($('c_run').checked&&cRun)p.set('run_id',cRun);return p}
function cLoadSoon(){clearTimeout(cT2);cT2=setTimeout(cLoad,300)}
const PN={instagram:'Instagram',facebook:'Facebook',tiktok:'TikTok'};
async function cLoad(){const d=await api('/api/comments?'+cQ());if(!d.ok){$('c_err').textContent='❌ '+d.error;return}$('c_err').textContent='';
 $('c_count').textContent=`共 ${d.total} 条`+(d.total>d.rows.length?`（表格显示前 ${d.rows.length} 条，导出包含全部）`:'');
 const mx=Math.max(1,...d.langs.map(l=>l.n));$('c_langs').innerHTML=d.langs.slice(0,20).map(l=>`<div class="lb"><span>${esc(l.name)} (${esc(l.lang)})</span><i style="width:${l.n/mx*300}px"></i><b>${l.n}</b></div>`).join('');
 $('c_tb').innerHTML=d.rows.map(r=>`<tr class="${r.matched?'m':''}"><td>${PN[r.platform]||r.platform}</td><td><a href="${esc(r.post_url)}" target="_blank">打开</a></td><td>${esc(r.account)}</td><td>${esc(r.commenter)}</td><td class="q">${esc(r.text)}</td><td>${esc(r.lang_name)}</td><td>${esc(r.region)}</td><td class="n">${r.likes}</td><td>${esc(r.ctime)}</td><td>${r.is_reply?'↳':''}</td><td>${r.matched?'✅':''}</td></tr>`).join('')}
function cExp(f,all){const p=cQ();p.set('fmt',f);if(all)p.set('all','1');location.href='/api/comments/export?'+p}
async function cClear(){if(confirm('确定清空评论库？')){await api('/api/comments/clear',{});cLoad()}}

function platUI(){const p=$('platform').value;document.querySelectorAll('#p-task [data-plat]').forEach(e=>e.hidden=!e.dataset.plat.split(' ').includes(p));document.querySelectorAll('.pcard').forEach(c=>c.classList.toggle('on',c.dataset.p===p));taskSum()}
document.addEventListener('DOMContentLoaded',()=>{$('platform').addEventListener('change',platUI);setTimeout(platUI,300);const h=$('c_help');if(!localStorage.getItem('c_help_seen')){h.open=true;localStorage.setItem('c_help_seen','1')}});

async function ttDiag(){const p=$('ttdiag');p.hidden=false;p.textContent='诊断中…（约 5~10 秒）';const d=await api('/api/tt/diag',{});p.textContent=(d.lines||[]).join('\n')}

function sttShow(){const v=$('ai_stt_provider').value;document.querySelectorAll('.stt-openai').forEach(e=>e.hidden=v!=='openai');document.querySelectorAll('.stt-el').forEach(e=>e.hidden=v!=='elevenlabs')}
async function sttTest(){msg('stmsg','测试中…（发送 1.5 秒测试音频）',1);const d=await api('/api/ai/stt_test',{el_key:$('el_key').value.trim(),el_model:$('el_model').value});msg('stmsg',d.msg,d.ok)}
async function visionTest(){msg('vmsg','测试中…（发送一张红色圆形图片）',1);const d=await api('/api/ai/vision_test',{ai_base:$('ai_base').value,ai_key:$('ai_key').value,ai_model:$('ai_model_manual').value.trim()||$('ai_model').value});msg('vmsg',d.msg,d.ok)}
let aLogN=0,aTimer=null,AID=null,AREC=null;
async function aGo(b){const d=await api('/api/analyze/start',b);if(!d.ok)return alert(d.error);aLogN=0;$('a_log').textContent='';show('ai')}
function aStart(){const u=$('a_url').value.trim();if(!u)return alert('请粘贴视频链接');aGo({url:u})}
async function aPoll(){clearTimeout(aTimer);const s=await api('/api/analyze/status?since='+aLogN);if(s.log_total<aLogN){aLogN=0;$('a_log').textContent=''}
 $('a_stage').textContent=s.stage;$('a_bar').style.width=(s.target?s.scanned/s.target*100:0)+'%';
 if(s.logs.length){$('a_log').textContent+=s.logs.join('\n')+'\n';$('a_log').scrollTop=1e9}aLogN=s.log_total;
 if(s.running)aTimer=setTimeout(aPoll,1500);else if(aPoll.was){aList();if(s.result_id)aOpen(s.result_id)}aPoll.was=s.running}
const ICONS=[['高光','✨'],['钩子','🎣'],['结构','🧱'],['视觉','🎨'],['卖点','💎'],['人群','🎯'],['情绪','❤️'],['评论','💬'],['爆款','🔥'],['公式','🧪'],['分镜','🎬'],['文案','✍️'],['标签','🏷️'],['封面','🖼️'],['发布','📅']];
const fmtN=n=>n==null||n===''?'-':n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e4?(n/1e3).toFixed(1)+'K':(+n).toLocaleString();
function mdHtml(t){return DOMPurify.sanitize(marked.parse(t||'',{gfm:true,breaks:true}))}
function splitSec(t){const out=[];let cur={title:'',body:[]};(t||'').split('\n').forEach(l=>{const m=l.match(/^##\s+(.*)/);if(m){if(cur.title||cur.body.join('').trim())out.push(cur);cur={title:m[1].trim(),body:[]}}else cur.body.push(l)});if(cur.title||cur.body.join('').trim())out.push(cur);return out.map(x=>({title:x.title,body:x.body.join('\n').trim()}))}
function decorate(root){const W=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('code,pre,a,.ts')?2:1});const ns=[];while(W.nextNode())ns.push(W.currentNode);
 const re=/(\d{1,3}(?:\.\d{1,2})?\s*(?:s|秒)?\s*[–\-~～至]\s*\d{1,3}(?:\.\d{1,2})?\s*(?:s|秒)|\b\d{1,3}(?:\.\d{1,2})?s\b)/g;
 ns.forEach(n=>{if(!re.test(n.nodeValue))return;re.lastIndex=0;const f=document.createElement('span');f.innerHTML=esc(n.nodeValue).replace(re,'<span class="ts">$1</span>');n.replaceWith(...f.childNodes)});root.querySelectorAll('.ts').forEach(tsBind);
 root.querySelectorAll('code').forEach(c=>{if(!c.closest('pre'))c.classList.add('quote')});
 const W2=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('.blank')?2:1});const bs=[];while(W2.nextNode())if(/【[^】]*】/.test(W2.currentNode.nodeValue))bs.push(W2.currentNode);
 bs.forEach(n=>{const f=document.createElement('span');f.innerHTML=esc(n.nodeValue).replace(/【([^】]*)】/g,(m,x)=>`<span class="blank" title="需要你自己填写">${x||'待填写'}</span>`);n.replaceWith(...f.childNodes)});
 root.querySelectorAll('pre').forEach(p=>{const b=document.createElement('button');b.className='pre-copy';b.textContent='复制';b.onclick=()=>cp(p.innerText.replace(/\n?复制$/,''));p.classList.add('has-copy');p.appendChild(b)});root.querySelectorAll('table').forEach(t=>{const w=document.createElement('div');w.className='tblw';t.replaceWith(w);w.appendChild(t)})}
function storyboard(body){const m=body.match(/^\|.*\|\s*\n\|[\s:|-]+\|\s*\n(?:\|.*\|\s*\n?)+/m);if(!m)return null;const rows=m[0].trim().split('\n').filter((l,i)=>i!==1).map(l=>l.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim()));
 const hd=rows.shift();const cards=rows.map(r=>`<div class="shot"><div class="shot-h"><span class="shot-no">${esc(r[0])}</span><span class="ts big">${esc(r[1]||'')}</span></div>${hd.slice(2).map((h,i)=>r[i+2]?`<div class="shot-f${h.includes('原')?' orig':''}"><label>${esc(h)}</label><div>${mdHtml(r[i+2])}</div></div>`:'').join('')}${origStrip(r[r.length-1]||'')}</div>`).join('');
 return{before:body.slice(0,m.index),cards,after:body.slice(m.index+m[0].length)}}
function renderSecs(kind,text){const box=$('a_'+kind),toc=$('toc_'+kind);const secs=splitSec(text);if(kind==='profile'||!text){}
 box.innerHTML=secs.map((x,i)=>{const ic=(ICONS.find(k=>x.title.includes(k[0]))||[0,'📝'])[1];const title=x.title||'概述';let bodyH;const sb=x.title.includes('分镜')&&storyboard(x.body);
  bodyH=sb?mdHtml(sb.before)+`<div class="board">${sb.cards}</div>`+mdHtml(sb.after):x.title.includes('高光')&&hlHtml(x.body)?hlHtml(x.body):kind==='replica'&&x.title.includes('标签')?tagsHtml(x.body):kind==='replica'&&x.title.includes('封面')?coverHtml(x.body):kind==='replica'&&x.title.includes('发布建议')?tipsHtml(x.body):mdHtml(x.body);
  return`<details class="card" open id="${kind}_s${i}"><summary class="card-h"><span class="ic">${ic}</span><h4>${esc(title.replace(/（.*?）$/,''))}</h4><span class="sub">${esc((title.match(/（(.*?)）$/)||['',''])[1])}</span><button class="ghost sm" onclick="event.preventDefault();secCopy('${kind}',${i})">复制</button><span class="chev">▾</span></summary><div class="card-b md2">${bodyH}</div></details>`}).join('');
 decorate(box);toc.innerHTML=secs.length>1?'<b>目录</b>'+secs.map((x,i)=>`<a onclick="document.getElementById('${kind}_s${i}').open=true;document.getElementById('${kind}_s${i}').scrollIntoView({behavior:'smooth',block:'start'})">${(ICONS.find(k=>x.title.includes(k[0]))||[0,'📝'])[1]} ${esc((x.title||'概述').replace(/（.*?）$/,'').replace(/^[一二三四五六七八九十]+、/,''))}</a>`).join(''):'';SECS[kind]=secs;$('pane_'+kind).classList.toggle('notoc',secs.length<=1)}
const SECS={};let FT=[],FTMAX=3;
function tsParse(s){s=String(s).replace(/：/g,':');const mm=[...s.matchAll(/(\d+):(\d{1,2}(?:\.\d+)?)/g)].map(m=>+m[1]*60+ +m[2]);if(mm.length)return mm.slice(0,2);return [...s.matchAll(/(\d{1,3}(?:\.\d{1,2})?)/g)].map(m=>+m[1]).slice(0,2)}
function nearF(t){if(!FT.length)return null;let b=FT[0];for(const f of FT)if(Math.abs(f.t-t)<Math.abs(b.t-t))b=f;return Math.abs(b.t-t)<=FTMAX?b:null}
function rangeF(a,b,n){if(b==null||b<=a){const f=nearF(a);return f?[f]:[]}const fs=FT.filter(f=>f.t>=a-0.01&&f.t<=b+0.01);if(!fs.length){const f=nearF(a);return f?[f]:[]}if(fs.length<=n)return fs;return Array.from({length:n},(_,i)=>fs[Math.round(i*(fs.length-1)/(n-1))])}
function tsBind(el){if(!FT.length||el.dataset.tb)return;if(!el.closest('#a_profile,.shot-f.orig'))return;const ts=tsParse(el.textContent);if(!ts.length||!nearF(ts[0]))return;el.dataset.tb=1;el.classList.add('has-f');el.dataset.a=ts[0];if(ts[1]!=null)el.dataset.b=ts[1]}
function fpop(el,pin){let p=$('fpop');if(!p){p=document.createElement('div');p.id='fpop';document.body.appendChild(p)}const a=+el.dataset.a,b=el.dataset.b!=null?+el.dataset.b:null;const fs=rangeF(a,b,3);if(!fs.length)return;
 p.innerHTML=fs.map(f=>`<figure><img src="${f.img}"><figcaption>${f.t.toFixed(2)}s</figcaption></figure>`).join('');p.className='show'+(pin?' pin':'');const r=el.getBoundingClientRect();const w=fs.length*164+16;let x=Math.min(window.innerWidth-w-8,Math.max(8,r.left));let y=r.bottom+6;if(y+320>window.innerHeight)y=Math.max(8,r.top-326);p.style.left=x+'px';p.style.top=y+'px'}
document.addEventListener('mouseover',e=>{const el=e.target.closest&&e.target.closest('.ts.has-f');const p=$('fpop');if(el)fpop(el);else if(p&&!p.classList.contains('pin')&&!e.target.closest('#fpop'))p.className=''});
document.addEventListener('click',e=>{const el=e.target.closest&&e.target.closest('.ts.has-f');const p=$('fpop');if(el){e.preventDefault();fpop(el,true)}else if(p&&!e.target.closest('#fpop'))p.className=''});
function hlHtml(body){const L=body.split('\n').map(l=>l.match(/^\s*[-*\d.]+\s*`?\**\s*(\d+(?:\.\d+)?)\s*(?:s|秒)?(?:\s*[–\-~～]\s*\d+(?:\.\d+)?\s*(?:s|秒)?)?\**\s*[｜|]\s*([^｜|]+?)\s*[｜|]\s*(.+?)`?\s*$/)).filter(Boolean);if(L.length<2)return'';
 return'<div class="hlg">'+L.map(m=>{const t=+m[1],f=nearF(t);return`<div class="hl">${f?`<img src="${f.img}" onclick="hlZoom(this)">`:'<div class="hl-noimg">无截图</div>'}<div class="hl-b"><div class="hl-h"><span class="ts">${t}s</span><b>${esc(m[2].replace(/\*/g,''))}</b></div><p>${esc(m[3].replace(/\*\*/g,''))}</p></div></div>`}).join('')+'</div>'}
function hlZoom(img){let z=$('fzoom');if(!z){z=document.createElement('div');z.id='fzoom';z.onclick=()=>z.className='';document.body.appendChild(z)}z.innerHTML=`<img src="${img.src}">`;z.className='show'}
function origStrip(cell){if(!FT.length)return'';const m=String(cell).match(/(\d+(?:\.\d+)?)\s*(?:s|秒)?\s*(?:[–\-~～至]\s*(\d+(?:\.\d+)?))?\s*(?:s|秒)/);if(!m)return'';const fs=rangeF(+m[1],m[2]!=null?+m[2]:null,4);if(!fs.length)return'';
 return`<div class="shot-orig"><label>原视频对应画面</label><div class="so-strip">${fs.map(f=>`<figure><img src="${f.img}" onclick="hlZoom(this)"><figcaption>${f.t.toFixed(1)}s</figcaption></figure>`).join('')}</div></div>`}
function transView(t){const box=$('a_trans');box.hidden=!t;if(!t)return;const L=t.split('\n').filter(x=>x.trim());const timed=/^\[\d+:\d/.test(L[0]||'');
 $('a_trans_sub').textContent=timed?`${L.length} 句 · 带时间戳`:`${t.length} 字`;box.open=false;
 $('a_trans_b').innerHTML=timed?'<div class="tlines">'+L.map(l=>{const m=l.match(/^\[([^\]]+)\]\s*(.*)$/);return m?`<div class="tl"><span class="ts">${esc(m[1])}</span><span>${esc(m[2])}</span></div>`:`<div class="tl"><span></span><span>${esc(l)}</span></div>`}).join('')+'</div>':`<p class="tplain">${esc(t)}</p>`}
function secCopy(kind,i){const x=SECS[kind][i];cp((x.title?'## '+x.title+'\n\n':'')+x.body)}
async function cp(t){try{await navigator.clipboard.writeText(t)}catch(e){const x=document.createElement('textarea');x.value=t;document.body.appendChild(x);x.select();document.execCommand('copy');x.remove()}toast('已复制')}
function toast(t){let e=$('toast');if(!e){e=document.createElement('div');e.id='toast';document.body.appendChild(e)}e.textContent=t;e.className='show';clearTimeout(toast.t);toast.t=setTimeout(()=>e.className='',1500)}
function aTab(k){['profile','replica'].forEach(x=>{$('t_'+x).classList.toggle('on',x===k);$('pane_'+x).hidden=x!==k});$('a_trans').classList.toggle('off',k!=='profile')}
async function aList(){const L=await api('/api/analyses');$('a_list').innerHTML=L.length?L.map(a=>`<div class="hcard ${a.id===AID?'on':''}" onclick="aOpen(${a.id})"><div class="hthumb">${a.thumb?`<img src="${a.thumb}">`:`<span>${a.platform==='tiktok'?'♪':a.platform==='facebook'?'f':'◎'}</span>`}</div><div class="hbody"><div class="htop"><span class="badge ${a.platform}">${PN[a.platform]||a.platform}</span><span class="hid">#${a.id}</span></div><b>@${esc(a.account)}</b><div class="hcap">${esc((a.caption||'').slice(0,60))}</div><div class="hmeta">${esc(a.created_at.slice(5,16))} · ${a.vision?'识图':'纯文字'} · ${a.frames} 帧${a.has_replica?' · <i>已复刻</i>':''}</div></div></div>`).join(''):'<p class="hint" style="padding:12px">还没有分析记录</p>'}
async function aOpen(id){AID=id;const a=AREC=await api('/api/analyses/'+id);const M=JSON.parse(a.meta||'{}');$('a_view').hidden=false;$('a_empty').hidden=true;
 $('a_plat').textContent=PN[a.platform]||a.platform;$('a_plat').className='badge '+a.platform;$('a_title').textContent='@'+a.account;$('a_link').href=a.url;
 $('a_thumb').innerHTML=M.thumb?`<img src="${M.thumb}">`:`<span>${a.platform==='tiktok'?'♪':'▶'}</span>`;
 const ch=[['▶','播放',fmtN(M.plays)],['♥','点赞',fmtN(M.likes)],['💬','评论',fmtN(M.comments)],['↗','分享',fmtN(M.shares)],['⏱','时长',(+M.duration||0).toFixed(1)+'s'],['🖼','截图',a.frames+' 帧'],['❓','提问评论',`${M.question_n??0}/${M.comment_n??0}`],['📅','发布',M.date||'-']];
 $('a_chips').innerHTML=ch.map(c=>`<span class="chip"><i>${c[0]}</i>${c[1]} <b>${esc(c[2])}</b></span>`).join('')+`<span class="chip ${a.vision?'ok':'warn'}">${a.vision?'✓ 识图分析':'⚠ 纯文字分析'}</span>`;
 $('a_cap').textContent=a.caption||'';let th=M.hook_thumbs||[];try{const ft=JSON.parse(a.fthumbs||'[]').filter(x=>x.t<3);if(ft.length)th=ft}catch(e){}$('a_hook').hidden=!th.length;$('a_hookstrip').innerHTML=th.map(x=>`<figure><img src="${x.img}"><figcaption>${x.t.toFixed(2)}s</figcaption></figure>`).join('');
 try{FT=JSON.parse(a.fthumbs||'[]')}catch(e){FT=[]}FTMAX=3;if(!FT.length){FT=(M.hook_thumbs||[]).slice();FTMAX=0.3}FT.sort((x,y)=>x.t-y.t); transView(a.transcript||'');renderSecs('profile',a.profile);renderSecs('replica',a.replica||'');repVersions(a);rfLoad();repPoll(id);aList()}
async function aCopy(w){if(!AREC)return;cp(w==='profile'?AREC.profile:w==='replica'?(AREC.replica||''):await(await fetch('/api/analyses/'+AID+'/md?raw=1')).text())}
async function aDel(){if(AID&&confirm('删除这条分析记录？')){await api('/api/analyses/'+AID+'/delete',{});AID=null;$('a_view').hidden=true;$('a_empty').hidden=false;aList()}}

function tagsHtml(body){const all=[];let h='',chips=[];const flush=()=>{if(chips.length){h+=`<div class="tagcloud">${chips.map(t=>`<button class="tagchip" onclick="cp('${t}')" title="点击复制">${esc(t)}</button>`).join('')}</div>`;chips=[]}};
 body.split('\n').forEach(l=>{const ts=l.match(/#[\p{L}\p{N}_]+/gu);if(ts&&ts.length>=2){const lbl=l.replace(/#[\p{L}\p{N}_]+/gu,'').replace(/[`\s,，、]+/g,' ').replace(/^[-*]\s*/,'').trim();if(lbl){flush();h+=`<div class="tg-l">${esc(lbl.replace(/[:：]$/,''))}</div>`}ts.forEach(t=>{if(!all.includes(t))all.push(t);chips.push(t)})}else if(l.trim()){if(/^\*\*.*\*\*[:：]?$|^#{3,4}\s|^[^\s].{0,20}[（(]\d+[)）][:：]?$/.test(l.trim())){flush();h+=`<div class="tg-l">${esc(l.replace(/[*#]/g,'').trim())}</div>`}else{flush();h+=mdHtml(l)}}});flush();
 return`<div class="tg-bar"><span class="hint">共 ${all.length} 个标签，点击单个复制</span><button class="ghost sm" onclick="cp('${all.join(' ')}')">复制全部标签</button></div>`+h}
function coverHtml(body){const parts=body.split(/\n(?=\*\*方案|#{3,4}\s*方案|方案\s*\d)/);if(parts.length<3)return mdHtml(body);const intro=/方案/.test(parts[0].slice(0,12))?'':parts.shift();const tail=parts.length?parts[parts.length-1].split(/\n\n(?!\s)/):[];let outro='';if(tail.length>1){outro=tail.slice(1).join('\n\n');parts[parts.length-1]=tail[0]}
 return mdHtml(intro)+`<div class="covers">${parts.map((p,i)=>{const t=(p.split('\n')[0]||'').replace(/[*#]/g,'').trim();return`<div class="cover"><div class="cv-n">${i+1}</div><div class="cv-t">${esc(t)}</div><div class="md2">${mdHtml(p.split('\n').slice(1).join('\n'))}</div></div>`}).join('')}</div>`+mdHtml(outro)}
function tipsHtml(body){const parts=body.split(/\n(?=\*\*[^*\n]{2,30}\*\*\s*$|#{3,4}\s)/m);if(parts.length<2)return mdHtml(body);const IC=[['时间','🕒'],['置顶','📌'],['回复','💬'],['话术','💬'],['注意','⚠️'],['复测','🔁']];
 return`<div class="tips">${parts.filter(p=>p.trim()).map(p=>{const ls=p.trim().split('\n');const t=ls[0].replace(/[*#]/g,'').trim();const ic=(IC.find(k=>t.includes(k[0]))||[0,'✅'])[1];return`<div class="tip"><div class="tip-h"><span>${ic}</span><b>${esc(t)}</b></div><div class="md2">${mdHtml(ls.slice(1).join('\n'))}</div></div>`}).join('')}</div>`}
const RF=['name','points','price','custom','market','duration','shoot','extra'];
function rfMode(m){$('rf_form').hidden=m!=='form';$('rf_free').hidden=m==='form';$('rf_m_form').classList.toggle('on',m==='form');$('rf_m_free').classList.toggle('on',m!=='form');localStorage.rf_mode=m}
async function rfLoad(){const p=await api('/api/product');RF.forEach(k=>{if(p[k]!=null)$('rf_'+k).value=p[k]});if(p.free)$('a_product').value=p.free;rfMode(p.mode||localStorage.rf_mode||'form')}
function rfGet(){const m=$('rf_form').hidden?'free':'form';const p={mode:m};if(m==='form')RF.forEach(k=>p[k]=$('rf_'+k).value.trim());else p.free=$('a_product').value.trim();return p}
let repTimer=null;
async function aRep(){if(!AID)return;const p=rfGet();if(p.mode==='form'?!RF.some(k=>p[k]):!p.free)return msg('a_rmsg','请至少填写产品名称或卖点');
 const d=await api('/api/analyses/'+AID+'/replicate',{product:p});if(!d.ok)return msg('a_rmsg',d.error);msg('a_rmsg','',1);repPoll(AID)}
async function repPoll(id){clearTimeout(repTimer);if(id!==AID)return;const s=await api('/api/analyses/'+id+'/replicate/status');const on=s.running;$('rep_prog').hidden=!on;$('rf_btn').disabled=on;$('rf_btn').textContent=on?'⏳ 生成中…':'✨ 生成复刻脚本';
 if(on){const e=Math.floor(s.elapsed);$('rp_time').textContent=Math.floor(e/60)+':'+String(e%60).padStart(2,'0');$('rp_bar').style.width=Math.min(95,e/180*100)+'%';if(s.text){$('rp_prev').innerHTML=mdHtml(s.text);decorate($('rp_prev'));$('rp_prev').scrollTop=1e9}repTimer=setTimeout(()=>repPoll(id),1000)}
 else if(repPoll.was===id){repPoll.was=null;if(s.error)return msg('a_rmsg','❌ '+s.error);msg('a_rmsg',`✅ 已生成并保存（用时 ${Math.round(s.elapsed)} 秒）`,1);await aOpen(id);aTab('replica')}
 if(on)repPoll.was=id}
function repVersions(a){const vs=JSON.parse(a.replicas||'[]');if(!vs.length&&a.replica)vs.push({at:a.created_at,product:a.product,text:a.replica});const box=$('rep_vers');box.hidden=vs.length<1;
 box.innerHTML=vs.length?`<span class="hint">历史版本：</span>`+vs.map((v,i)=>`<button class="vchip ${i===vs.length-1?'on':''}" title="${esc((v.product||'').slice(0,200))}" onclick="repShow(${i})">版本 ${i+1}<small>${esc((v.at||'').slice(5,16))}</small></button>`).join(''):'';REPV=vs}
let REPV=[];
function repShow(i){document.querySelectorAll('.vchip').forEach((b,j)=>b.classList.toggle('on',i===j));renderSecs('replica',REPV[i].text);AREC.replica=REPV[i].text}

document.addEventListener('DOMContentLoaded',()=>{const e=$('cf_expr');if(!e)return;let t;e.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(async()=>{const v=e.value.trim();if(!v){$('cf_err').textContent='';return}const d=await api('/api/cfilter/check?expr='+encodeURIComponent(v));$('cf_err').textContent=d.ok?'✓ 语法正确':'❌ '+d.error;$('cf_err').className=d.ok?'ok':'err'},400)})});

function pickPlat(p){$('platform').value=p;localStorage.f_platform=p;platUI()}
function chipRender(id){const w=$(id+'_chips');if(!w)return;const L=lines(id);w.querySelector('.chips-l').innerHTML=L.map((x,i)=>`<span class="kchip">${esc(x)}<button onclick="chipDel('${id}',${i})" title="删除">×</button></span>`).join('');w.querySelector('.chip-n').textContent=L.length?L.length+' 个':'';taskSum()}
function chipAdd(id,txt){const L=lines(id),s=new Set(L.map(x=>x.toLowerCase()));txt.split(/[\n,，]/).map(x=>x.trim().replace(id==='hashtags'?/^#/:/^$/,'')).filter(Boolean).forEach(x=>{if(!s.has(x.toLowerCase())){s.add(x.toLowerCase());L.push(x)}});$(id).value=L.join('\n');chipRender(id)}
function chipDel(id,i){const L=lines(id);L.splice(i,1);$(id).value=L.join('\n');chipRender(id)}
function chipify(id){const ta=$(id);ta.hidden=true;const w=document.createElement('div');w.className='chipbox';w.id=id+'_chips';w.innerHTML='<div class="chips-l"></div><input placeholder="输入后回车添加…"><span class="chip-n"></span><button class="ghost sm clr" title="清空">清空</button>';ta.after(w);
 const inp=w.querySelector('input');inp.onkeydown=e=>{if((e.key==='Enter'||e.key===','||e.key==='，')&&inp.value.trim()){e.preventDefault();chipAdd(id,inp.value);inp.value=''}else if(e.key==='Backspace'&&!inp.value){const L=lines(id);if(L.length)chipDel(id,L.length-1)}};
 inp.onpaste=e=>{const t=(e.clipboardData||window.clipboardData).getData('text');if(/[\n,，]/.test(t)){e.preventDefault();chipAdd(id,t)}};inp.onblur=()=>{if(inp.value.trim()){chipAdd(id,inp.value);inp.value=''}};
 w.onclick=e=>{if(e.target===w||e.target.classList.contains('chips-l'))inp.focus()};w.querySelector('.clr').onclick=()=>{if(confirm('清空这个列表？')){ta.value='';chipRender(id)}};chipRender(id)}
function taskSum(){if(!$('sb_sum'))return;const p=$('platform').value,m=$('mode').value;const nk=m!=='hashtag'?lines('keywords').length:0,nt=m!=='keyword'?lines('hashtags').length:0;const cf=$('cf_expr').value.trim();
 const parts=[`<span class="badge ${p}">${PN[p]}</span>`,nk?`${nk} 个关键词`:'',nt?`${nt} 个标签`:'',`目标 <b>${+$('max_videos').value||0}</b> 条`,p!=='tiktok'?{video:'视频',post:'帖子',both:'视频+帖子'}[$('content_type').value]:'',cf?'<span class="on">评论筛选已开</span>':'',$('skip_existing').checked?'跳过已有':''].filter(Boolean);
 $('sb_sum').innerHTML=parts.join('<i>·</i>');$('cf_state').textContent=cf?'已启用':'未启用';$('cf_state').classList.toggle('on',!!cf);$('tag_w').classList.toggle('dim',m==='keyword');$('kw_w').classList.toggle('dim',m==='hashtag');
 $('mv_hint').textContent=cf?'评论命中筛选的视频保存够这么多条就停止':'有提问的内容保存够这么多条就停止'}
function taskValid(){let ok=true;const set=(id,t)=>{$(id).textContent=t;if(t)ok=false};const m=$('mode').value;
 set('v_kw',m!=='hashtag'&&!lines('keywords').length?'请至少添加一个关键词':'');set('v_tag',m!=='keyword'&&!lines('hashtags').length?'请至少添加一个标签':'');
 set('v_mv',!(+$('max_videos').value>=1)?'至少 1 条':'');set('v_date',$('date_from').value&&$('date_to').value&&$('date_from').value>$('date_to').value?'结束日期早于开始日期':'');
 if($('cf_err').classList.contains('err')&&$('cf_err').textContent.startsWith('❌'))ok=false;return ok}
document.addEventListener('DOMContentLoaded',()=>{['keywords','hashtags','phrases'].forEach(chipify);document.querySelectorAll('#p-task input,#p-task select,#p-task textarea').forEach(e=>{e.addEventListener('input',()=>{taskSum();if(document.querySelector('#p-task .verr:not(:empty)'))taskValid()});e.addEventListener('change',taskSum)});setTimeout(()=>{['keywords','hashtags','phrases'].forEach(chipRender);platUI()},350)});
