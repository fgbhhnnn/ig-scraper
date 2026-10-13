const $=id=>document.getElementById(id);
const api=async(u,b)=>{const r=await fetch(u,b===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()};
const lines=id=>$(id).value.split(/\n/).map(s=>s.trim()).filter(Boolean);
const words=id=>$(id).value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function msg(id,t,ok){$(id).textContent=t;$(id).className=ok?'ok':'err'}
function show(p){document.querySelectorAll('section').forEach(s=>s.hidden=s.id!=='p-'+p);document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('on',a.dataset.p===p));if(p==='results')loadResults();if(p==='comments'){cLoad();cPoll()}if(p==='ai'){aList();aPoll()}localStorage.page=p}
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
 if(c.has_cookie)checkCookie('instagram');else ckPill('instagram',0,'未填写');ckPill('facebook',c.has_fb_cookie,c.has_fb_cookie?'已保存':'未填写');ckPill('tiktok',c.has_tt_cookie,c.has_tt_cookie?'已保存':'未填写');$('tt_device_id').value=c.tt_device_id||'';$('tt_user_agent').value=c.tt_user_agent||'';$('tt_ms_token').placeholder=c.tt_ms_token_set?'已保存（留空=保持不变）':$('tt_ms_token').placeholder;$('tt_delay_min').value=c.tt_delay_min;$('tt_delay_max').value=c.tt_delay_max;['ai_fps','ai_max_images','ai_stt_model','ai_vision','ai_comment_pages','ai_comments_send'].forEach(k=>$(k).value=c[k]??'');loadSigner()}
async function fetchModels(){msg('mmsg','获取中…',1);const d=await api('/api/models',{ai_base:$('ai_base').value,ai_key:$('ai_key').value});
 if(!d.ok)return msg('mmsg',d.error);const cur=$('ai_model').value;$('ai_model').innerHTML=d.models.map(m=>`<option ${m===cur?'selected':''}>${esc(m)}</option>`).join('');msg('mmsg','✅ 共 '+d.models.length+' 个模型',1)}
async function saveSettings(){const b={ai_base:$('ai_base').value.trim(),ai_model:$('ai_model_manual').value.trim()||$('ai_model').value,delay_min:+$('delay_min').value||1.5,delay_max:+$('delay_max').value||3,fb_delay_min:+$('fb_delay_min').value||1.5,fb_delay_max:+$('fb_delay_max').value||3,tt_delay_min:+$('tt_delay_min').value||1.5,tt_delay_max:+$('tt_delay_max').value||3,port:+$('port').value||8765,ai_fps:+$('ai_fps').value||1,ai_max_images:$('ai_max_images').value?+$('ai_max_images').value:'',ai_stt_model:$('ai_stt_model').value.trim(),ai_vision:$('ai_vision').value,ai_comment_pages:+$('ai_comment_pages').value||5,ai_comments_send:+$('ai_comments_send').value||120};
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
const SEL=new Set();let R=[],sk='question_count',sd=-1;
async function loadResults(){const p=new URLSearchParams({platform:$('f_platform').value,content_type:$('f_ctype').value});if($('only_run').checked&&lastRun)p.set('run_id',lastRun);R=await api('/api/results?'+p);renderResults()}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;sd=sk===k?-sd:-1;sk=k;renderResults()});
function renderResults(){const q=$('q').value.toLowerCase();let rs=R.filter(r=>!q||[r.account,r.caption,r.sample_questions,r.source].join(' ').toLowerCase().includes(q));
 rs.sort((a,b)=>{const x=a[sk],y=b[sk];return(typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y)))*sd});
 $('rcount').textContent=`共 ${rs.length} 条（数据库 ${R.length} 条）`;
 $('tb').innerHTML=rs.map(r=>{const fb=r.platform==='facebook',tt=r.platform==='tiktok';const k=r.platform+'|'+r.shortcode;return`<tr><td><input type="checkbox" class="sel" value="${esc(k)}" ${SEL.has(k)?'checked':''} onchange="this.checked?SEL.add(this.value):SEL.delete(this.value)" style="width:auto"></td><td><span class="tag ${fb?'fb':tt?'tt':'ig'}">${fb?'Facebook':tt?'TikTok':'Instagram'}</span></td><td>${r.content_type==='post'?'帖子':'视频'}</td>
 <td>${fb?esc(r.account):`<a href="${tt?'https://www.tiktok.com/@':'https://www.instagram.com/'}${esc(r.account)}${tt?'':'/'}" target="_blank">${esc(r.account)}</a>`}</td><td><a href="${esc(r.url)}" target="_blank">${fb?'打开':esc(r.shortcode)}</a></td>
 <td class="cap">${esc((r.caption||'').slice(0,120))}</td><td class="n">${(r.plays?r.plays.toLocaleString():'-')}</td><td class="n">${(r.likes||0).toLocaleString()}</td><td class="n">${r.comment_count}</td><td class="n">${r.shares==null?'-':r.shares.toLocaleString()}</td><td class="n"><b>${r.question_count}</b></td>
 <td class="q">${esc(r.sample_questions).replace(/ \|\| /g,'<br>')}</td><td>${esc(r.publish_date)}</td><td>${esc(r.source)}</td><td>${r.content_type==='post'?'':`<button class="ghost" onclick="aGo({key:'${esc(k)}'})">🤖 AI 分析</button>`}</td></tr>`}).join('')}
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

function platUI(){const p=$('platform').value;document.querySelectorAll('#p-task [data-plat]').forEach(e=>e.hidden=!e.dataset.plat.split(' ').includes(p))}
document.addEventListener('DOMContentLoaded',()=>{$('platform').addEventListener('change',platUI);setTimeout(platUI,300);const h=$('c_help');if(!localStorage.getItem('c_help_seen')){h.open=true;localStorage.setItem('c_help_seen','1')}});

async function ttDiag(){const p=$('ttdiag');p.hidden=false;p.textContent='诊断中…（约 5~10 秒）';const d=await api('/api/tt/diag',{});p.textContent=(d.lines||[]).join('\n')}

async function visionTest(){msg('vmsg','测试中…（发送一张红色圆形图片）',1);const d=await api('/api/ai/vision_test',{ai_base:$('ai_base').value,ai_key:$('ai_key').value,ai_model:$('ai_model_manual').value.trim()||$('ai_model').value});msg('vmsg',d.msg,d.ok)}
function md(t){let h=esc(t||'');h=h.replace(/^(\|.*\|)\n\|[-:| ]+\|\n((?:\|.*\|\n?)*)/gm,(m,hd,body)=>{const row=(l,tg)=>'<tr>'+l.trim().slice(1,-1).split('|').map(c=>`<${tg}>${c.trim()}</${tg}>`).join('')+'</tr>';return'<table class="mdt">'+row(hd,'th')+body.trim().split('\n').map(l=>row(l,'td')).join('')+'</table>'});
 return h.replace(/^### (.*)$/gm,'<h4>$1</h4>').replace(/^## (.*)$/gm,'<h3>$1</h3>').replace(/^# (.*)$/gm,'<h2>$1</h2>').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/^[-*] (.*)$/gm,'• $1').replace(/\n/g,'<br>').replace(/(<\/(h2|h3|h4|table)>)<br>/g,'$1')}
let aLogN=0,aTimer=null,AID=null,AREC=null;
async function aGo(b){const d=await api('/api/analyze/start',b);if(!d.ok)return alert(d.error);aLogN=0;$('a_log').textContent='';show('ai')}
function aStart(){const u=$('a_url').value.trim();if(!u)return alert('请粘贴视频链接');aGo({url:u})}
async function aPoll(){clearTimeout(aTimer);const s=await api('/api/analyze/status?since='+aLogN);if(s.log_total<aLogN){aLogN=0;$('a_log').textContent=''}
 $('a_stage').textContent=s.stage;$('a_bar').style.width=(s.target?s.scanned/s.target*100:0)+'%';
 if(s.logs.length){$('a_log').textContent+=s.logs.join('\n')+'\n';$('a_log').scrollTop=1e9}aLogN=s.log_total;
 if(s.running)aTimer=setTimeout(aPoll,1500);else if(aPoll.was){aList();if(s.result_id)aOpen(s.result_id)}aPoll.was=s.running}
async function aList(){const L=await api('/api/analyses');$('a_list').innerHTML=L.length?L.map(a=>`<div class="ai-item ${a.id===AID?'on':''}" onclick="aOpen(${a.id})"><b>#${a.id} ${PN[a.platform]||a.platform} @${esc(a.account)}</b>${a.has_replica?' 🎬':''}<br><span class="hint">${esc(a.created_at)} · ${a.vision?'识图':'纯文字'} · ${a.frames} 张图</span><br><span class="hint">${esc((a.caption||'').slice(0,50))}</span></div>`).join(''):'<p class="hint">还没有分析记录</p>'}
async function aOpen(id){AID=id;const a=AREC=await api('/api/analyses/'+id);const M=JSON.parse(a.meta||'{}');$('a_view').hidden=false;
 $('a_title').innerHTML=`#${a.id} ${PN[a.platform]||''} @${esc(a.account)} · <a href="${esc(a.url)}" target="_blank">打开原视频</a>`;
 $('a_meta').textContent=`播放 ${M.plays??'-'} · 点赞 ${M.likes??'-'} · 评论 ${M.comments??'-'} · 时长 ${(+M.duration||0).toFixed(1)}s · 截图 ${a.frames} 张 · 评论 ${M.comment_n??0} 条(提问 ${M.question_n??0}) · ${a.vision?'识图分析':'纯文字分析'} ${a.note||''} · ${a.created_at}`;
 $('a_profile').innerHTML=md(a.profile);$('a_replica').innerHTML=md(a.replica||'');$('a_product').value=a.product||localStorage.a_product||'';aList()}
async function aRep(){if(!AID)return;localStorage.a_product=$('a_product').value;msg('a_rmsg','生成中…（约 30 秒 ~ 2 分钟）',1);const d=await api('/api/analyses/'+AID+'/replicate',{product:$('a_product').value});if(!d.ok)return msg('a_rmsg',d.error);msg('a_rmsg','✅ 已生成并保存',1);aOpen(AID)}
async function aCopy(w){if(!AREC)return;let t=w==='profile'?AREC.profile:w==='replica'?(AREC.replica||''):await(await fetch('/api/analyses/'+AID+'/md?raw=1')).text();
 try{await navigator.clipboard.writeText(t)}catch(e){const x=document.createElement('textarea');x.value=t;document.body.appendChild(x);x.select();document.execCommand('copy');x.remove()}alert('已复制')}
async function aDel(){if(AID&&confirm('删除这条分析记录？')){await api('/api/analyses/'+AID+'/delete',{});AID=null;$('a_view').hidden=true;aList()}}
