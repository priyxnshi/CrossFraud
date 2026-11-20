'use strict';
const app = document.querySelector('#app');
const icons = {
  network:'<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h6a3 3 0 0 1 3 3v6M6 9v6a3 3 0 0 0 3 3h6"/>',
  overview:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  shield:'<path d="M12 22s7-3 7-10V5l-7-3-7 3v7c0 7 7 10 7 10z"/><path d="M12 8v5m0 3h.01"/>',
  message:'<path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 9 9 0 0 1-3.8-.9L3 21l1.9-5.7a9 9 0 0 1-.9-3.8A8.4 8.4 0 0 1 12.5 3h.5a8.4 8.4 0 0 1 8 8z"/>',
  card:'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20m-15 5h4"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  chart:'<path d="M3 3v18h18M8 16v-3m5 3V8m5 8V5"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4M5 5l3 3m8 8 3 3M5 19l3-3m8-8 3-3"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0"/>',
  activity:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
};
const icon = (key) => '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24">' + icons[key] + '</svg>';
const nav = [['overview','Overview','overview'],['alerts','Risk Alerts','shield'],['messages','Message Intelligence','message'],['payments','Payment Intelligence','card'],['correlation','Cross-Platform Correlation','network'],['investigations','Investigations','folder'],['analytics','Analytics & Reports','chart'],['settings','Settings','settings']];
const esc = (v) => String(v ?? 'Unavailable').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = (v) => !v ? 'Unavailable' : String(v).replaceAll('_',' ').replace(/^\w/, c=>c.toUpperCase());
const flat = (v) => String(v ?? '').toLowerCase();
const fmt = (v) => typeof v === 'number' ? v.toLocaleString('en-IN') : '—';
const score = (v) => typeof v === 'number' ? v.toFixed(3) : '—';
const pct = (v) => typeof v === 'number' ? (100*v).toFixed(1)+'%' : '—';
const money = (v) => typeof v === 'number' ? new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(v) : '—';
const day = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'});
const clock = new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'});
function instant(v){return new Date(typeof v === 'string' && /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(v) ? v.replace(' ','T')+'+05:30' : v);}
const time = (v) => v && !isNaN(instant(v)) ? clock.format(instant(v))+' IST' : 'Unavailable';
function dateKey(v){if(!v || isNaN(instant(v)))return '';const parts=Object.fromEntries(day.formatToParts(instant(v)).map(x=>[x.type,x.value]));return parts.year+'-'+parts.month+'-'+parts.day;}
const badge = (v, color) => '<span class="badge '+esc(color || v)+'">'+esc(pretty(v))+'</span>';
const logo = '<a class="logo" href="#" aria-label="CrossFraud home"><span class="mark">'+icon('network')+'</span><span>CrossFraud</span></a>';
const count = (rows, fn) => rows.reduce((out,row)=>{const key=fn(row);out[key]=(out[key]||0)+1;return out;},Object.create(null));
const entries = (object) => Object.entries(object || {}).sort((a,b)=>b[1]-a[1]);
const go = (route, args='') => '#'+route+(args?'?'+args:'');
const query = (key,v) => new URLSearchParams({[key]:v}).toString();
const detailLink = (route,id,label='View details') => '<a class="linktext" href="'+go(route,query('id',id))+'">'+esc(label)+'</a>';
const button = (text,href,primary=false) => '<a class="btn'+(primary?' primary':'')+'" href="'+href+'">'+esc(text)+'</a>';
const page = (title, desc, extra='') => '<div class="pagehead"><div><h1>'+esc(title)+'</h1><p>'+esc(desc)+'</p></div>'+extra+'</div>';
const section = (title, content, sub='') => '<section class="card"><div class="cardhead"><div><h2>'+esc(title)+'</h2>'+(sub?'<p>'+esc(sub)+'</p>':'')+'</div></div>'+content+'</section>';
const kpi = (title,value,sub,key,href) => '<a class="card kpi" href="'+href+'">'+icon(key)+'<span>'+esc(title)+'</span><strong>'+esc(value)+'</strong><small>'+esc(sub)+'</small></a>';
const facts = (pairs) => '<dl class="facts">'+pairs.map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd></div>').join('')+'</dl>';
const note = (v) => '<p class="notice">'+esc(v)+'</p>';
const DISCLAIMER = 'Risk scores are indicators for human review and do not establish fraud or individual wrongdoing.';
const D = {alerts:[], conversations:[], payments:[], coverage:{}, evaluation:{}};
let pending, viewToken=0;
async function request(path, body) {
  if (window.crossfraudDemo) return window.crossfraudDemo(path, body);
  const response = await fetch(path, body === undefined ? undefined : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed ('+response.status+')');
  return data;
}
function hydrate(){
  if (!pending) pending=Promise.all([request('/alerts'),request('/catalog')]).then(([alerts,catalog])=>{Object.assign(D,catalog,{alerts:alerts.alerts});}).catch(err=>{pending=null;throw err;});
  return pending;
}
function refs(a) {
  return {conversation:a.kind==='messaging_warning'?a.entity_id:a.evidence?.match?.selected?.conversation_id,
          transaction:a.kind==='payment_time_review'?a.entity_id:undefined};
}
const chat = (id) => D.conversations.find(row=>row.id===id);
const payment = (id) => D.payments.find(row=>row.id===id);
const pattern = (a) => chat(refs(a).conversation)?.category;
const byChat = (id) => D.alerts.find(a=>refs(a).conversation===id);
const byPayment = (id) => D.alerts.find(a=>refs(a).transaction===id);
const statusGroup = (a) => {
  const match=a.evidence?.match;
  if(match?.status==='ambiguous') return 'Ambiguous matches';
  if(match?.selected) return match.selected.confidence>=.9?'Strong matches':'Possible matches';
  if(match?.candidates?.length) return 'Possible matches';
  return 'No matches';
};

function landing(){
  const feature = (symbol,title,text)=>'<article class="card">'+icon(symbol)+'<h3>'+esc(title)+'</h3><p>'+esc(text)+'</p></article>';
  const caps = [
    ['message','Messaging intelligence','Review conversation evidence available when a warning was generated.'],
    ['card','Payment intelligence','Inspect UPI payment attempts, amounts and event-time status.'],
    ['network','Cross-platform correlation','Compare addresses, amounts and timing. Ambiguous candidates remain open for review.'],
    ['shield','Human-led investigations','Record review decisions and notes beside the evidence that informed them.']];
  app.innerHTML='<header class="sitebar"><div class="landing">'+logo+'<nav aria-label="Website"><a href="#site-overview">Overview</a><a href="#site-flow">How It Works</a><a href="#site-tech">Technology</a><a href="#site-about">About</a><a href="#settings">Sign In</a>'+button('Get Started','#overview',true)+'</nav></div></header><main id="content" class="landing">'+
    '<section class="hero" id="site-overview"><div><span class="tag">Cross-platform fraud intelligence</span><h1>Connecting the Dots. Detecting Fraud Before It Escalates.</h1><p>CrossFraud combines messaging intelligence and payment transaction evidence to identify potential cross-platform fraud, surface suspicious connections, and provide explainable risk alerts.</p><div class="row">'+button('Explore Dashboard','#overview',true)+button('How It Works','#site-flow')+'</div></div><div class="diagram"><div class="card">'+icon('message')+' <strong>Messaging Intelligence</strong></div><span aria-hidden="true">│</span><div class="card">'+icon('network')+' <strong>Cross-Platform Correlation</strong></div><span aria-hidden="true">│</span><div class="card">'+icon('card')+' <strong>Payment Risk Intelligence</strong></div></div></section>'+
    '<section class="grid two"><article class="card"><h2>Fragmented fraud detection</h2><p>A chat team may see grooming without knowing that a transfer followed. A payment team may see an attempt without the conversation that prompted it.</p></article><article class="card"><h2>Unified messaging and payment evidence</h2><p>CrossFraud brings both timelines into one review workspace. A chat can raise a warning on its own. An observed payment can add corroborating evidence.</p></article></section>'+
    '<section id="site-flow"><h2>How CrossFraud works</h2><div class="flow">'+[['Detect','Score the chat visible at the decision time.'],['Correlate','Compare the quoted details with observed payment attempts.'],['Evaluate','Rank the evidence and surface uncertainty.'],['Alert','Present the evidence for human review.']].map(([a,b])=>'<div class="step"><strong>'+a+'</strong><small>'+b+'</small></div>').join('')+'</div></section>'+
    '<section id="site-tech"><h2>Capabilities</h2><div class="grid two sep">'+caps.map(x=>feature(...x)).join('')+'</div></section>'+
    '<section id="site-about"><h2>Explainable AI and human-led investigation</h2><p>'+DISCLAIMER+' The local research demo uses synthetic data and shows the evidence available at each decision point.</p>'+button('Open Analyst Workspace','#overview',true)+'</section><footer>'+logo+'<span class="muted">Local research prototype · Synthetic data</span></footer></main>';
}
function frame(route,title,content){
  app.innerHTML='<div class="shell"><aside class="sidebar">'+logo+'<nav aria-label="Workspace">'+nav.map(([id,text,symbol])=>'<a href="#'+id+'" aria-label="'+text+'" title="'+text+'" '+(route===id?'aria-current="page"':'')+'>'+icon(symbol)+'<span>'+text+'</span></a>').join('')+'</nav><small>Local analyst workspace</small></aside><div><header class="top"><div class="crumb">Workspace / <strong>'+esc(title)+'</strong></div><div class="toolbar"><form id="global"><input name="q" type="search" aria-label="Global search" placeholder="Search alerts or records"></form><span class="tag">Synthetic data</span><button class="iconbtn" type="button" id="notifications" aria-label="Notifications">'+icon('bell')+'</button><a class="avatar" href="#settings" aria-label="Analyst profile">AN</a></div></header><main id="content" class="content">'+content+'</main></div></div><dialog class="dialog" id="dialog"></dialog>';
  document.querySelector('#global').onsubmit=(event)=>{event.preventDefault();const term=event.target.elements.q.value.trim();if(term)location.hash=go('search',query('q',term));};
  document.querySelector('#notifications').onclick=()=>{
    const fresh=D.alerts.filter(a=>a.review_outcome==='unresolved');
    const dialog=document.querySelector('#dialog');
    dialog.innerHTML='<form method="dialog" class="cardhead"><h2>Notifications</h2><button class="btn">Close</button></form><p>'+fmt(fresh.length)+' unresolved synthetic alerts</p><div class="sep">'+button('Open review queue',go('alerts',query('review','unresolved')),true)+'</div>';
    dialog.querySelector('a').onclick=()=>dialog.close();dialog.showModal();
  };
}
function table(columns, rows, sorter=false){
  if (!rows.length) return '<p class="empty">No records match the current filters.</p>';
  return '<div class="tablewrap" tabindex="0" aria-label="Scrollable table"><table><thead><tr>'+columns.map(([key,title])=>'<th scope="col">'+(sorter&&key?'<button type="button" data-sort="'+esc(key)+'">'+esc(title)+'</button>':esc(title))+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+columns.map(([key,,render])=>'<td>'+(render?render(row):esc(row[key]))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}
const alertColumns = [
  ['id','Alert ID',r=>detailLink('alert',r.id,r.id.slice(0,8))],['pattern','Synthetic scenario / alert type',r=>esc(pretty(r.pattern))],
  ['conversation','Conversation',r=>r.conversation?detailLink('message',r.conversation,r.conversation):'—'],
  ['transaction','Transaction',r=>r.transaction?detailLink('payment',r.transaction,r.transaction):'—'],
  ['score','Risk score',r=>score(r.score)],['level','Risk level',r=>badge(r.level)],
  ['when','Detection time',r=>esc(time(r.when))],['review','Review status',r=>badge(r.review)],
  [null,'Action',r=>detailLink('alert',r.id)]
];
function alertRows(){return D.alerts.map(a=>({id:a.alert_id,pattern:pattern(a)||a.kind,...refs(a),score:a.risk_score,level:a.risk_level,when:a.event_time_utc,review:a.review_outcome}));}
function filters(config,params){
  return '<div id="filters" class="filters"><input aria-label="Search records" type="search" data-filter="q" placeholder="Search records" value="'+esc(params.get('q')||'')+'">'+
    config.map(([key,label,options])=> options===null?'<input type="date" aria-label="'+esc(label)+'" data-filter="'+key+'" value="'+esc(params.get(key)||'')+'">':
      '<select aria-label="'+esc(label)+'" data-filter="'+key+'"><option value="">'+esc(label)+'</option>'+options.map(value=>'<option value="'+esc(value)+'"'+(params.get(key)===value?' selected':'')+'>'+esc(pretty(value))+'</option>').join('')+'</select>').join('')+'</div>';
}
function records(title, rows, columns, config, params){
  let pageIndex=0, key=null, sign=1;
  const size=15;
  return {html:'<section class="card tablecard"><div class="tablehead"><h2>'+esc(title)+'</h2></div>'+filters(config,params)+'<div id="results"></div></section>',
  bind(){
    const target=document.querySelector('#results');
    function draw(){
      const values=Object.fromEntries([...document.querySelectorAll('[data-filter]')].map(el=>[el.dataset.filter,el.value]));
      let shown=rows.filter(r=>Object.entries(values).every(([field,value])=>!value ||
        (field==='q'?Object.values(r).some(item=>flat(item).includes(flat(value))):field==='date'?dateKey(r.when)===value:r[field]===value)));
      if(key)shown.sort((a,b)=>sign*(typeof a[key]==='number'&&typeof b[key]==='number'?a[key]-b[key]:String(a[key]??'').localeCompare(String(b[key]??''))));
      const pages=Math.max(1,Math.ceil(shown.length/size)); pageIndex=Math.min(pageIndex,pages-1);
      target.innerHTML=table(columns,shown.slice(pageIndex*size,pageIndex*size+size),true)+'<div class="pager"><small>'+fmt(shown.length)+' records · Page '+(pageIndex+1)+' of '+pages+'</small><div class="row"><button type="button" class="btn" data-page="-1" '+(!pageIndex?'disabled':'')+'>Previous</button><button type="button" class="btn" data-page="1" '+(pageIndex+1===pages?'disabled':'')+'>Next</button></div></div>';
      target.querySelectorAll('[data-sort]').forEach(el=>{el.closest('th').setAttribute('aria-sort',key===el.dataset.sort?(sign===1?'ascending':'descending'):'none');el.onclick=()=>{sign=key===el.dataset.sort?-sign:1;key=el.dataset.sort;draw();};});
      target.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>{pageIndex+=Number(el.dataset.page);draw();});
    }
    document.querySelector('#filters').oninput=()=>{pageIndex=0;draw();}; draw();
  }};
}
function bars(values, destination, accent='#3977c8'){
  const maximum=Math.max(1,...values.map(x=>x[1]));
  return '<div class="bars">'+values.map(([label,n])=>{
    const content='<span>'+esc(pretty(label))+'</span><span class="track"><i style="width:'+100*n/maximum+'%;--accent:'+accent+'"></i></span><strong>'+fmt(n)+'</strong>';
    const href=destination?.(label);
    return href?'<a class="bar" href="'+href+'" title="'+esc(label)+' · '+fmt(n)+'">'+content+'</a>':'<div class="bar">'+content+'</div>';
  }).join('')+'</div>';
}
function trend(){
  const values=count(D.alerts,a=>dateKey(a.event_time_utc));const dates=Object.keys(values).sort();
  if(!dates.length)return '<p class="empty">No dated alerts.</p>';
  const max=Math.max(1,...Object.values(values)),start=Date.parse(dates[0]),end=Date.parse(dates.at(-1));
  const points=dates.map(d=>[30+(Date.parse(d)-start)/Math.max(1,end-start)*458,127-values[d]/max*102,d]);
  return '<svg class="trend" viewBox="0 0 518 150" role="group" aria-label="Alerts over time">'+[25,51,77,103,127].map(y=>'<path d="M25 '+y+' H496" stroke="#e5eaf1"/>').join('')+
    '<polyline fill="none" stroke="#3977c8" stroke-width="3" points="'+points.map(p=>p.slice(0,2).join(',')).join(' ')+'"/>'+points.map(([x,y,d])=>'<a href="'+go('alerts',query('date',d))+'" aria-label="'+d+', '+values[d]+' alerts"><circle cx="'+x+'" cy="'+y+'" r="5" fill="#2457a7"><title>'+d+' · '+values[d]+' alerts</title></circle></a>').join('')+
    '</svg><div class="chartcaption"><span>'+esc(dates[0])+'</span><span>'+esc(dates.at(-1))+'</span></div>';
}
function riskDonut(){
  const levels=count(D.alerts,a=>a.risk_level),total=D.alerts.length, high=100*(levels.high||0)/Math.max(1,total), medium=100*(levels.medium||0)/Math.max(1,total);
  return '<div class="donut-wrap"><div class="donut" style="background:conic-gradient(#b33850 0 '+high+'%,#ce8b2a '+high+'% '+(high+medium)+'%,#2c9574 '+(high+medium)+'% 100%)"><div><strong>'+total+'</strong><small>Alerts</small></div></div><div class="legend">'+[['high','#b33850'],['medium','#ce8b2a'],['low','#2c9574']].map(([level,color])=>'<a href="'+go('alerts',query('level',level))+'"><i class="dot" style="--accent:'+color+'"></i>'+pretty(level)+' · '+(levels[level]||0)+'</a>').join('')+'</div></div>';
}
function overview(){
  const methods=D.evaluation.methods||{}, matching=D.evaluation.matching||{};
  const high=D.alerts.filter(a=>a.risk_level==='high').length;
  const avg=D.alerts.length ? D.alerts.reduce((sum,a)=>sum+a.risk_score,0)/D.alerts.length:null;
  return page('Overview','Synthetic data / research mode',button('Review alerts','#alerts',true))+
    '<div class="grid kpis">'+[
      ['Conversations analysed',fmt(D.conversations.length),'Synthetic dataset','message','#messages'],['Transactions analysed',fmt(D.payments.length),'Synthetic UPI attempts','card','#payments'],
      ['High-risk alerts',fmt(high),'Saved alert examples','shield',go('alerts',query('level','high'))],['Successful correlations',fmt(matching.true_links),'Held-out reference links','network','#correlation'],['Average risk score',score(avg),'Across saved alerts','activity','#alerts']
    ].map(x=>kpi(...x)).join('')+'</div>'+
    '<div class="grid two charts">'+section('Risk distribution',riskDonut(),'Saved synthetic alerts')+section('Alerts over time',trend(),'Select a date to drill into alerts')+'</div>'+
    '<div class="grid three charts">'+section('Messaging vs payment',bars([['Messaging only',methods.messaging_only?.test?.confusion_matrix?.tp||0],['Payment only',methods.payment_only?.test?.confusion_matrix?.tp||0],['Combined',methods.combined?.test?.confusion_matrix?.tp||0]],()=> '#analytics'),'Fraud cases flagged in the same holdout')+
    section('Scam scenario distribution',bars(entries(count(D.conversations.filter(x=>x.scenario_is_scam),x=>x.category)).slice(0,6),key=>go('messages',query('category',key))),'Synthetic generator labels')+
    section('Correlation performance',facts([['Reference pairs',fmt(matching.reference_links_in_cohort)],['Correct links',fmt(matching.true_links)],['Precision',pct(matching.precision)],['Recall',pct(matching.recall)]]),'Held-out replay')+'</div>'+
    '<section class="card tablecard"><div class="tablehead"><h2>Recent risk alerts</h2>'+button('All alerts','#alerts')+'</div>'+table(alertColumns,alertRows().sort((a,b)=>instant(b.when)-instant(a.when)).slice(0,6))+'</section>';
}
function alertPage(params,investigations=false){
  const rows=alertRows();
  const list=records(investigations?'Investigation queue':'Alert queue',rows,alertColumns,[['level','All risk levels',['high','medium','low']],['date','Detection date',null],['pattern','All categories',[...new Set(rows.map(x=>x.pattern))].sort()],['review','All review outcomes',['unresolved','confirmed','dismissed']]],params);
  const stats=investigations?['unresolved','confirmed','dismissed']:['high','medium','low'];
  return {html:page(investigations?'Investigations':'Risk Alerts',investigations?'Review alert evidence and maintain a local decision history.':'Filter, sort and review stored synthetic alerts.')+
    '<div class="grid '+(investigations?'three':'kpis')+' charts">'+(investigations?'':kpi('Total alerts',rows.length,'Saved examples','overview','#alerts'))+stats.map(item=>kpi(pretty(item),rows.filter(r=>(investigations?r.review:r.level)===item).length,'Saved examples','shield',go(investigations?'investigations':'alerts',query(investigations?'review':'level',item)))).join('')+'</div>'+list.html,bind:list.bind};
}
function messagePage(params){
  const rows=D.conversations.map(c=>{const a=byChat(c.id);return {...c,when:c.start,score:a?.risk_score,level:a?.risk_level,indicators:a?.evidence?.credential_request_messages?'Credential request':a?.evidence?.urgency_messages?'Urgency':a?'Evidence attached':'Unavailable',linked:a&&refs(a).transaction?'Linked':'Unavailable'};});
  const columns=[['id','Conversation',r=>detailLink('message',r.id,r.id)],['platform','Platform',r=>esc(pretty(r.platform))],['category','Synthetic scenario',r=>esc(pretty(r.category))],['indicators','Detected indicators'],['score','Risk score',r=>score(r.score)],['level','Risk level',r=>r.level?badge(r.level):badge('unknown')],['linked','Linked transaction'],[null,'Action',r=>detailLink('message',r.id)]];
  const list=records('Conversations',rows,columns,[['platform','All platforms',['telegram','whatsapp']],['category','All scenarios',Object.keys(count(rows,r=>r.category)).sort()]],params);
  return {html:page('Message Intelligence','Inspect synthetic conversations and the evidence attached to saved alerts.')+
    '<div class="grid two charts">'+kpi('Conversations analysed',fmt(rows.length),'Synthetic dataset','message','#messages')+kpi('Conversations with review alerts',fmt(rows.filter(r=>r.score!==undefined).length),'Saved evidence only','shield','#alerts')+'</div><div class="grid two charts">'+
    section('Scam scenario distribution',bars(entries(count(rows.filter(x=>x.scenario_is_scam),x=>x.category)).slice(0,8),v=>go('messages',query('category',v))))+section('Primary language coverage',bars(entries(D.coverage.primary_language).slice(0,8)),'Synthetic population profiles')+'</div>'+list.html,bind:list.bind};
}
function paymentPage(params){
  const rows=D.payments.map(p=>({...p,when:p.timestamp,score:byPayment(p.id)?.risk_score}));
  const columns=[['id','Transaction',r=>detailLink('payment',r.id,r.id)],['sender','Sender reference'],['receiver','Receiver reference'],['amount','Amount',r=>esc(money(r.amount))],['type','Payment type'],['status','Attempt status',r=>badge(r.status,r.status==='failed'?'medium':'blue')],['when','Attempt time',r=>esc(time(r.when))],['score','Risk score',r=>score(r.score)]];
  const list=records('UPI payment attempts',rows,columns,[['type','All payment types',Object.keys(count(rows,r=>r.type))],['status','All statuses',Object.keys(count(rows,r=>r.status))],['date','Attempt date',null]],params);
  return {html:page('Payment Intelligence','Inspect synthetic payment attempts, with masked sender and receiver references.')+
    '<div class="grid two charts">'+kpi('Transactions analysed',fmt(rows.length),'Synthetic dataset','card','#payments')+kpi('Transactions flagged for review',fmt(rows.filter(r=>r.score!==undefined).length),'Saved evidence only','shield','#alerts')+'</div><div class="grid three charts">'+
    section('Status distribution',bars(entries(count(rows,r=>r.status)),v=>go('payments',query('status',v))))+
    section('Payment types',bars(entries(count(rows,r=>r.type)),v=>go('payments',query('type',v))))+
    section('Amount distribution',bars(entries(count(rows,r=>r.amount<500?'Below ₹500':r.amount<2000?'₹500 to ₹1,999':r.amount<10000?'₹2,000 to ₹9,999':'₹10,000 or more'))))+'</div>'+list.html,bind:list.bind};
}
function correlation(params){
  const matching=D.evaluation.matching||{};
  const groups=['Strong matches','Possible matches','Ambiguous matches','No matches'];
  const payments=D.alerts.filter(a=>a.kind==='payment_time_review');
  const selected= params.get('group') || '';
  const shown=payments.filter(a=>!selected||statusGroup(a)===selected);
  return page('Cross-Platform Correlation','Inspect observed links between chat requests and payment attempts.')+
    '<div class="grid three charts">'+[
      ['Reference linked attempts',fmt(matching.reference_links_in_cohort),'Held-out replay','network','#analytics'],
      ['Correct links',fmt(matching.true_links),'Held-out replay','shield','#analytics'],
      ['Link recall',pct(matching.recall),'Held-out replay','activity','#analytics']
    ].map(x=>kpi(...x)).join('')+'</div><section class="card"><div class="cardhead"><h2>Saved payment alert links</h2></div><div class="row summaryline">'+
    button('All matches','#correlation',!selected)+groups.map(group=>button(group+' ('+payments.filter(a=>statusGroup(a)===group).length+')',go('correlation',query('group',group)),selected===group)).join('')+'</div></section><div class="stack sep">'+
    (shown.length?shown.map(a=>{
      const link=a.evidence.match?.selected, pair=refs(a);
      return section(a.entity_id,flow([['Conversation',pair.conversation||'No accepted match'],['Quoted details',link?pretty(link.identifier_evidence):'Insufficient evidence'],['UPI attempt',money(a.evidence.amount_inr)],['Risk assessment',pretty(a.risk_level)]])+
        facts([['Confidence',link?score(link.confidence):'Unavailable'],['Amount difference',link?money(link.amount_difference_inr):'Unavailable'],['Elapsed time',link?Math.round(link.delay_minutes)+' min':'Unavailable'],['Candidate count',fmt(a.evidence.match?.candidates?.length||0)]])+'<div class="sep">'+detailLink('alert',a.alert_id,'Open investigation')+'</div>',statusGroup(a));
    }).join(''):'<p class="empty">No saved alerts in this match group.</p>')+'</div>';
}
function flow(steps){return '<div class="flow">'+steps.map(([label,value])=>'<div class="step"><strong>'+esc(label)+'</strong><small>'+esc(value)+'</small></div>').join('<span class="connector" aria-hidden="true">―</span>')+'</div>';}
function paymentFacts(p, evidence){
  return p?facts([['Transaction ID',p.id],['Amount',money(p.amount)],['Payment type',pretty(p.type)],['Attempt status',pretty(p.status)],['Sender reference',p.sender],['Receiver reference',p.receiver],['Attempt time',time(p.timestamp)],['UPI identifier match',evidence?.match?.selected?pretty(evidence.match.selected.identifier_evidence):'Unavailable']]):note('No observed payment is included in this alert.');
}
function messageView(detail, fallback){
  if(!detail)return '<p class="empty">'+esc(fallback)+'</p>';
  return facts([['Conversation',detail.id],['Platform',pretty(detail.platform)]])+'<div class="messages">'+
    (detail.messages.length?detail.messages.map(m=>'<div class="message '+(m.indicators.length?'flag':m.speaker==='Counterparty'?'counter':'')+'"><small>'+esc(m.speaker)+' · '+esc(time(m.time))+'</small>'+esc(m.text)+
    (m.indicators.length?'<small>'+esc(m.indicators.join(' · '))+'</small>':'')+'</div>').join(''):'<p class="muted">No visible messages at this cutoff.</p>')+'</div>';
}
function reviewBox(alert,notes){
  return '<section class="card review"><h2>Human review</h2><div class="sep">'+badge(alert.review_outcome)+'</div><div class="row sep">'+
    [['confirmed','Mark as Confirmed'],['dismissed','Dismiss Alert'],['unresolved','Mark as Unresolved']].map(([value,label])=>'<button type="button" class="btn'+(value==='unresolved'?' primary':'')+'" data-outcome="'+value+'">'+label+'</button>').join('')+
    '</div><form id="note"><textarea name="note" aria-label="Investigation note" placeholder="Add an investigation note" rows="3" maxlength="1000" required></textarea><button class="btn" type="submit">Save note</button></form>'+
    '<p class="muted sep" id="review-status" role="status"></p><h3 class="sep">Investigation notes</h3>'+
    (notes.length?'<ul>'+notes.map(row=>'<li>'+esc(row.note)+' <small>· '+esc(time(row.recorded_at_utc))+'</small></li>').join('')+'</ul>':'<p class="muted">No notes recorded.</p>')+
    '<h3 class="sep">Decision history</h3>'+(alert.review_history.length?'<ul>'+[...alert.review_history].reverse().map(row=>'<li>'+esc(pretty(row.outcome))+' <small>· '+esc(time(row.recorded_at_utc))+'</small></li>').join('')+'</ul>':'<p class="muted">No decisions recorded.</p>')+'</section>';
}
function bindReview(id){
  const endpoint='/alerts/'+encodeURIComponent(id);
  const status=document.querySelector('#review-status');
  async function save(action, body){
    const form=document.querySelector('.review');
    const controls=[...form.querySelectorAll('button')];
    controls.forEach(x=>x.disabled=true);
    try{
      const result=await request(endpoint+'/'+action,body);
      if(action==='review')D.alerts=D.alerts.map(a=>a.alert_id===result.alert_id?result:a);
      if(form.isConnected){await render();const message=document.querySelector('#review-status');if(message)message.textContent=action==='notes'?'Note saved.':'Decision saved.';}
    }catch(error){if(status.isConnected)status.textContent=error.message;}
    finally{controls.forEach(x=>x.disabled=false);}
  }
  document.querySelectorAll('[data-outcome]').forEach(el=>el.onclick=()=>save('review',{outcome:el.dataset.outcome}));
  document.querySelector('#note').onsubmit=(event)=>{event.preventDefault();const note=event.target.elements.note.value.trim();if(note)save('notes',{note});else status.textContent='Enter a note before saving.';};
}
function casePage(a,conversation,notes){
  const e=a.evidence||{},r=refs(a), p=payment(r.transaction), match=e.match, selected=match?.selected;
  const pre=a.kind==='messaging_warning';
  const riskFactors=[
    ['Urgency indicators',e.urgency_messages],['Credential requests',e.credential_request_messages],['Suspicious links',e.suspicious_link_messages],
    ['Payment requests',e.payment_request_messages],['New beneficiary',typeof e.new_beneficiary==='boolean'?(e.new_beneficiary?'Yes':'No'):undefined],
    ['UPI match',selected?pretty(selected.identifier_evidence):undefined],['Corroboration bonus',e.corroboration_bonus===undefined?undefined:score(e.corroboration_bonus)]
  ].filter(([,val])=>val!==undefined);
  const steps=[
    [conversation?.messages[0]?.time,'First observed message'],
    [e.conversation_observed_at_utc,'Messaging score available'],
    [selected?.request_time_utc,'Payment request quoted'],
    [p?.timestamp,'Payment attempt'],
    [a.event_time_utc,pre?'Messaging warning generated':'Payment-time alert generated'],
  ].filter(([stamp])=>stamp).sort((x,y)=>instant(x[0])-instant(y[0]));
  const evidenceStatus=pre?'Messaging warning · no payment scored':'At payment attempt';
  const candidates=(match?.candidates||[]).filter(item=>item!==selected && item.conversation_id!==selected?.conversation_id);
  return page('Alert '+a.alert_id.slice(0,8),evidenceStatus+' · '+time(a.event_time_utc),button('Back to risk alerts','#alerts'))+
    '<div class="row summaryline">'+badge(a.risk_level)+badge(a.review_outcome)+'<span class="tag">Risk score '+score(a.risk_score)+'</span></div><div class="split sep"><div class="stack">'+
    section('Risk assessment',facts([['Overall score',score(a.risk_score)],['Decision threshold',score(a.threshold)],['Classification',pretty(a.risk_level)],['Review status',pretty(a.review_outcome)]])+
        '<p class="notice">'+esc(pre?'This warning scores a visible conversation prefix.':pretty(e.combined_basis||'Payment-time evidence'))+'</p><p class="muted">Scores are uncalibrated. A match confidence measures the strength of a link as scored by the prototype.</p>')+
    section('Messaging evidence',messageView(conversation,'No conversation evidence was linked to this alert.')+
      (r.conversation?'<div class="sep">'+detailLink('message',r.conversation,'Open full synthetic conversation')+'</div>':''),'Visible up to the alert decision time')+
    section('Payment evidence',paymentFacts(p,e))+
    section('Cross-platform correlation',flow([['Messaging conversation',r.conversation||'Unavailable'],['Extracted details',selected?pretty(selected.identifier_evidence):'Unavailable'],['UPI transaction',r.transaction||'Unavailable'],['Risk assessment',pretty(a.risk_level)]])+
      facts([['Match status',pretty(match?.status)],['Match confidence',score(selected?.confidence)],['Amount difference',selected?money(selected.amount_difference_inr):'Unavailable'],['Time difference',selected?Math.round(selected.delay_minutes)+' min':'Unavailable']])+
      '<p class="muted sep">'+esc(match?.reason||'A payment match was unavailable at this decision point.')+'</p>'+
      (selected?'<ul>'+[...(selected.support||[]),...(selected.conflicts||[])].map(x=>'<li>'+esc(pretty(x))+'</li>').join('')+'</ul>':'')+
      (candidates.length?'<h3 class="sep">Other candidates</h3><ul>'+candidates.map(c=>'<li>'+esc(c.conversation_id)+' · '+score(c.confidence)+' · '+esc((c.conflicts||[]).join(', ')||'No listed conflicts')+'</li>').join('')+'</ul>':'')
    )+'</div><div class="stack">'+section('Event timeline','<ol class="timeline">'+steps.map(([stamp,title])=>'<li><strong>'+esc(title)+'</strong><br><small>'+esc(time(stamp))+'</small></li>').join('')+'</ol><p class="muted">Settlement completion is unavailable in attempt-time evidence.</p>')+
    section('Explainable risk factors',riskFactors.length?facts(riskFactors):note('No individual factor contributions were exported.'))+reviewBox(a,notes)+'</div></div><p class="disclaimer">'+DISCLAIMER+'</p>';
}
function messageDetail(entity,conversation){
  const row=chat(entity);
  const alerts=D.alerts.filter(a=>refs(a).conversation===entity);
  return page('Conversation '+entity,'Synthetic message analysis',button('Back to messages','#messages'))+
  '<div class="split">'+section('Conversation history',messageView(conversation,'No conversation data available.'),'Complete historical record. Alert investigations show only the evidence available at the decision cutoff.')+
  '<div class="stack">'+section('Conversation details',facts([['Platform',pretty(row?.platform)],['Synthetic scenario',pretty(row?.category)],['First message',time(row?.start)]]))+
  section('Associated alerts',alerts.length?'<ul>'+alerts.map(a=>'<li>'+detailLink('alert',a.alert_id,a.alert_id.slice(0,8))+' · '+esc(pretty(a.kind))+'</li>').join('')+'</ul>':'<p class="muted">No saved alert with this conversation.</p>')+'</div></div>';
}
function paymentDetail(entity){
  const p=payment(entity),a=byPayment(entity);
  return page('Transaction '+entity,'Synthetic UPI attempt',button('Back to payments','#payments'))+'<div class="split">'+
    section('Payment details',paymentFacts(p,a?.evidence))+section('Risk and correlation',a?facts([['Risk score',score(a.risk_score)],['Risk level',pretty(a.risk_level)],['Match status',pretty(a.evidence.match?.status)]])+
    '<div class="sep">'+detailLink('alert',a.alert_id,'Open investigation')+'</div>':note('No saved review alert is attached to this attempt.'))+'</div>';
}
function analytics(params){
  const methods=D.evaluation.methods||{};
  const chosen=params.get('model') in methods?params.get('model'):'combined';
  const m=methods[chosen]?.test||{}, matrix=m.confusion_matrix||{};
  const baseline=Object.entries(methods).map(([id,result])=>({id,...result.test}));
  return page('Analytics & Reports','Synthetic-data prototype evaluation · Common held-out replay',button('View catalog and evaluation JSON',window.crossfraudDemo?'/demo.json':'/catalog'))+
    '<div class="row summaryline charts">'+Object.keys(methods).map(id=>button(pretty(id),go('analytics',query('model',id)),chosen===id)).join('')+'</div>'+
    '<div class="grid kpis">'+[['Precision',m.precision],['Recall',m.recall],['F1',m.f1],['PR-AUC',m.pr_auc]].map(([label,val])=>kpi(label,score(val),pretty(chosen),'chart',go('analytics',query('model',chosen)))).join('')+'</div>'+
    '<div class="grid two charts">'+section('Confusion matrix',table([['actual','Actual'],['negative','Predicted legitimate'],['positive','Predicted fraud']],[{actual:'Legitimate',negative:fmt(matrix.tn),positive:fmt(matrix.fp)},{actual:'Fraud',negative:fmt(matrix.fn),positive:fmt(matrix.tp)}]))+
    section('False positives and early warning',facts([['False alerts',fmt(matrix.fp)],['False alerts per 1,000 cases',score(m.false_alerts_per_1000_cases)],['Pre-payment warnings',fmt(m.early_warning?.warned_before_attempt)],['Median lead time',m.early_warning?.median_lead_minutes?Math.round(m.early_warning.median_lead_minutes)+' min':'Unavailable']]))+'</div>'+
    '<div class="grid two charts">'+section('Regional coverage',bars(entries(D.coverage.region)),'Synthetic participant profiles')+section('Language coverage',bars(entries(D.coverage.primary_language).slice(0,10)),'Synthetic participant profiles')+
    section('Scenario coverage',bars(entries(count(D.conversations.filter(r=>r.scenario_is_scam),r=>r.category)).slice(0,8),v=>go('messages',query('category',v))),'Generator labels')+
    section('Temporal evaluation',facts(Object.entries(D.evaluation.partitions||{}).map(([key,row])=>[pretty(key),fmt(row.conversations)+' conversations · '+fmt(row.payments)+' attempts'])))+'</div>'+
    section('Detector comparison',table([['id','Detector',x=>esc(pretty(x.id))],['n','Cases'],['precision','Precision',x=>score(x.precision)],['recall','Recall',x=>score(x.recall)],['f1','F1',x=>score(x.f1)],['pr_auc','PR-AUC',x=>score(x.pr_auc)]],baseline))+
    '<p class="disclaimer">Evaluation covers a small synthetic holdout. The results do not establish performance on real-world fraud.</p>';
}
function search(params){
  const q=params.get('q')||'';
  const includes=(row)=>Object.values(row).some(value=>flat(value).includes(flat(q)));
  const results=alertRows().filter(includes);
  const messages=D.conversations.filter(includes),payments=D.payments.filter(includes);
  return page('Search results','Results for “'+q+'”')+'<div class="stack">'+section('Alerts · '+results.length,table(alertColumns,results.slice(0,10)))+
    section('Conversations · '+messages.length,table([['id','Conversation',x=>detailLink('message',x.id,x.id)],['platform','Platform'],['category','Scenario',x=>esc(pretty(x.category))]],messages.slice(0,10))+button('Open conversation results',go('messages',query('q',q))))+
    section('Transactions · '+payments.length,table([['id','Transaction',x=>detailLink('payment',x.id,x.id)],['type','Type'],['amount','Amount',x=>money(x.amount)]],payments.slice(0,10))+button('Open transaction results',go('payments',query('q',q))))+'</div>';
}
function settings(){
  return page('Settings','Local analyst profile and demo environment')+'<div class="grid two">'+
    section('Analyst profile',facts([['Role','Demo analyst'],['Access','Local review workspace'],['Time zone','Asia/Kolkata (IST)']])+note('The local demo uses a shared analyst workspace. No account or credentials are required.')+button('Open workspace','#overview',true))+
    section('Environment',facts([['Data source','Synthetic'],['Scope','Research mode'],['Review storage',window.crossfraudDemo?'This browser':'Local SQLite']])+'<p class="disclaimer">'+DISCLAIMER+'</p>')+'</div>';
}
async function render(){
  const token=++viewToken;
  const [route,qs]=location.hash.slice(1).split('?'),params=new URLSearchParams(qs),entity=params.get('id');
  if(!route||route.startsWith('site-')){if(!document.querySelector('.sitebar'))landing();if(route)document.getElementById(route)?.scrollIntoView();else window.scrollTo(0,0);return;}
  const title=nav.find(item=>item[0]===route)?.[1]||({alert:'Alert investigation',message:'Conversation details',payment:'Transaction details',search:'Search'})[route]||'Workspace';
  try{
    if(!D.alerts.length)frame(route,title,'<p class="boot" role="status">Loading synthetic workspace…</p>');
    await hydrate(); if(token!==viewToken)return;
    let content, bind;
    if(route==='overview')content=overview();
    else if(route==='alerts'||route==='investigations')({html:content,bind}=alertPage(params,route==='investigations'));
    else if(route==='messages')({html:content,bind}=messagePage(params));
    else if(route==='payments')({html:content,bind}=paymentPage(params));
    else if(route==='correlation')content=correlation(params);
    else if(route==='analytics')content=analytics(params);
    else if(route==='settings')content=settings();
    else if(route==='search')content=search(params);
    else if(route==='payment'&&payment(entity))content=paymentDetail(entity);
    else if(route==='message'&&chat(entity))content=messageDetail(entity,await request('/conversations/'+encodeURIComponent(entity)));
    else if(route==='alert'){
      const alert=D.alerts.find(a=>a.alert_id===entity);
      if(alert){
        const {conversation}=refs(alert);
        const [messages,notes]=await Promise.all([conversation?request('/conversations/'+encodeURIComponent(conversation)+'?'+query('cutoff',dateKey(alert.event_time_utc)+' '+new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(instant(alert.event_time_utc)))):null,request('/alerts/'+encodeURIComponent(entity)+'/notes')]);
        content=casePage(alert,messages,notes);bind=()=>bindReview(entity);
      }
    }
    if(token!==viewToken)return;
    frame(route,title,content||page('Record unavailable','This record is not in the local synthetic dataset.',button('Return to overview','#overview')));
    bind?.();
  }catch(error){
    if(token===viewToken){frame(route,title,page('Workspace unavailable',error.message)+'<button class="btn primary" id="retry">Retry</button>');document.querySelector('#retry').onclick=render;}
  }
}
document.querySelector('.skip').onclick=(event)=>{
  event.preventDefault();
  const target=document.querySelector('#content');
  target.tabIndex=-1; target.focus();
};
window.addEventListener('hashchange',()=>{window.scrollTo(0,0);render();});
render();
