(() => {
  'use strict';
  const data = window.DIAN_WIKI;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const paths = {
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="m20 3 .5 1.5L22 5l-1.5.5L20 7l-.5-1.5L18 5l1.5-.5Z"/>',
    moon:'<path d="M20.5 13.5A8.5 8.5 0 0 1 10.5 3a9 9 0 1 0 10 10.5Z"/>',
    sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    'arrow-up-right':'<path d="M6 18 18 6M6 6h12v12"/>',
    'arrow-right':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
    'arrow-down':'<path d="M12 4v16m-6-6 6 6 6-6"/>',
    'arrow-up':'<path d="M12 20V4m-6 6 6-6 6 6"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    x:'<path d="m6 6 12 12M6 18 18 6"/>',
    cloud:'<path d="M6 18a4 4 0 0 1-1-7.9A7 7 0 0 1 18.7 9a4.5 4.5 0 0 1-.2 9H6Z"/>',
    folder:'<path d="M3 7V5h6l2 2h10v13H3V7Z"/><path d="M3 10h18"/>',
    play:'<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4V8Z"/>',
    film:'<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4m10-8h4m-4 8h4"/>',
    grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    activity:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
    bookmark:'<path d="M6 3h12v18l-6-4-6 4V3Z"/>',
    heart:'<path d="M20.5 4.5a5 5 0 0 0-7 0L12 6l-1.5-1.5a5 5 0 0 0-7 7L12 20l8.5-8.5a5 5 0 0 0 0-7Z"/>',
    music:'<path d="M9 17V5l11-2v12M9 8l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2.5"/><ellipse cx="17" cy="16" rx="3" ry="2.5"/>',
    key:'<circle cx="8" cy="8" r="5"/><path d="m12 12 9 9m-3-3 2-2m-5-1 2-2"/>',
    users:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m1 4a5 5 0 0 1 3 4v3"/>',
    shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
    message:'<path d="M21 16a2 2 0 0 1-2 2H8l-5 3V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v11Z"/><path d="M7 8h10M7 12h6"/>',
    sliders:'<path d="M4 6h6m4 0h6M4 12h11m4 0h1M4 18h2m4 0h10"/><circle cx="12" cy="6" r="2"/><circle cx="17" cy="12" r="2"/><circle cx="8" cy="18" r="2"/>',
    link:'<path d="m10 13 4-4m-7 6-1 1a4 4 0 0 1-5.7-5.7l4-4A4 4 0 0 1 10 6m4 12a4 4 0 0 0 5.7-.3l4-4A4 4 0 0 0 18 8l-1 1" transform="translate(0 -1) scale(.9)"/>',
    home:'<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3V10Z"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    gift:'<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13"/><path d="M12 8H8a3 3 0 1 1 3-3l1 3Zm0 0h4a3 3 0 1 0-3-3l-1 3Z"/>',
    medal:'<circle cx="12" cy="9" r="6"/><path d="m8 14-2 7 6-3 6 3-2-7"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    check:'<path d="m5 12 4 4L19 6"/>',
    ticket:'<path d="M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4V5Z"/><path d="M15 5v3m0 3v2m0 3v3"/>',
    server:'<rect x="3" y="3" width="18" height="7" rx="1"/><rect x="3" y="14" width="18" height="7" rx="1"/><path d="M7 6.5h.1M7 17.5h.1M12 7h5m-5 11h5"/>'
  };
  function icon(name){return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'+(paths[name]||paths.bookmark)+'</svg>';}
  function icons(scope=document){$$('[data-icon]',scope).forEach(el=>{el.outerHTML=icon(el.dataset.icon);});}
  function escape(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function stored(k,f){try{return localStorage.getItem(k)||f;}catch{return f;}}
  function save(k,v){try{localStorage.setItem(k,v);}catch{}}
  function toast(message){const t=$('#toast');t.textContent=message;t.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.remove('show'),2300);}
  function setMotion(quiet){root.dataset.motion=quiet?'quiet':'full';root.classList.toggle('js-motion',!quiet);$('#motionToggle').setAttribute('aria-pressed',String(quiet));$('#motionToggle').setAttribute('aria-label',quiet?'开启完整动效':'开启安静模式');}
  let manualQuiet=stored('dian-wiki-motion-v2','')==='quiet';
  setMotion(manualQuiet||reduced.matches);
  reduced.addEventListener('change',()=>setMotion(manualQuiet||reduced.matches));
  $('#motionToggle').addEventListener('click',()=>{manualQuiet=root.dataset.motion!=='quiet';save('dian-wiki-motion-v2',manualQuiet?'quiet':'full');setMotion(manualQuiet||reduced.matches);toast(manualQuiet?'已开启安静模式':reduced.matches?'系统已设置减少动态效果':'已开启完整动效');});
  function setTheme(theme){root.dataset.theme=theme;$('#themeToggle').innerHTML=icon(theme==='dark'?'sun':'moon');$('#themeToggle').setAttribute('aria-label',theme==='dark'?'切换浅色主题':'切换深色主题');$('meta[name="theme-color"]').content=theme==='dark'?'#0b1018':'#edf1f6';}
  setTheme(stored('dian-wiki-theme-v2','dark'));
  $('#themeToggle').addEventListener('click',()=>{const t=root.dataset.theme==='dark'?'light':'dark';setTheme(t);save('dian-wiki-theme-v2',t);});
  icons();

  const featureTabs=$('#featureTabs'),featureStage=$('#featureStage');
  data.groups.forEach((g,i)=>{const b=document.createElement('button');b.type='button';b.className='feature-tab';b.id='feature-tab-'+g.id;b.dataset.group=g.id;b.setAttribute('role','tab');b.setAttribute('aria-controls','featureStage');b.setAttribute('aria-selected',String(i===0));b.innerHTML=icon(g.icon)+escape(g.label);featureTabs.append(b);});
  function feature(group,animate=true){const g=data.groups.find(g=>g.id===group)||data.groups[0];$$('button',featureTabs).forEach(b=>b.setAttribute('aria-selected',String(b.dataset.group===g.id)));featureStage.setAttribute('aria-labelledby','feature-tab-'+g.id);featureStage.dataset.group=g.id;const n=data.groups.indexOf(g)+1;const covers={automate:['dune','interstellar','arrival'],media:['blade-runner','soul','inception'],extend:['inception','dune','soul'],operate:['arrival','blade-runner','interstellar']}[g.id];featureStage.innerHTML='<article class="feature-manifesto '+(animate?'switch-enter':'')+'"><span class="eyebrow">DIAN115 / '+escape(g.label)+'</span><h3>'+escape(g.title)+'</h3><p>'+escape(g.subtitle)+'</p><div class="manifesto-media" aria-hidden="true">'+covers.map(c=>'<img src="assets/'+c+'.jpg" alt="" loading="lazy">').join('')+'</div><span class="manifesto-symbol" aria-hidden="true"></span><span class="manifesto-number" aria-hidden="true">0'+n+'</span><small>DISCOVER MORE. ENJOY MORE.</small></article><div class="feature-items">'+g.items.map((item,i)=>'<button type="button" class="feature-item '+(animate?'switch-enter':'')+'" data-doc="'+item.id+'"><span class="item-num">0'+(i+1)+'</span><span><h4>'+escape(item.title)+'</h4><p>'+escape(item.desc)+'</p></span>'+icon('arrow-up-right')+'</button>').join('')+'</div>';save('dian-wiki-feature',g.id);}
  feature(stored('dian-wiki-feature','automate'),false);
  featureTabs.addEventListener('click',e=>{const b=e.target.closest('button');if(b)feature(b.dataset.group);});
  function arrowTabs(el,callback){el.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const bs=$$('button',el),index=bs.indexOf(document.activeElement);if(index<0)return;e.preventDefault();let n=e.key==='Home'?0:e.key==='End'?bs.length-1:(index+(e.key==='ArrowRight'?1:-1)+bs.length)%bs.length;bs[n].focus();callback(bs[n]);});}
  arrowTabs(featureTabs,b=>feature(b.dataset.group));

  const setupSteps=$('#setupSteps'),setupDetail=$('#setupDetail');
  data.setup.forEach((s,i)=>{const b=document.createElement('button');b.type='button';b.className='setup-step';b.id='setup-step-'+i;b.dataset.step=i;b.setAttribute('role','tab');b.setAttribute('aria-controls','setupDetail');b.innerHTML='<span>0'+(i+1)+'</span><div><b>'+s.title+'</b><small>'+s.short+'</small></div>';setupSteps.append(b);});
  const chips=[['Host 网络 · 推荐','/config','/媒体库'],['115','CD2 / AURA','Emby'],['识别与命名','STRM','播放验证'],['订阅与来源','通知','用户门户']];
  function setup(index,animate=true){const n=Number(index),s=data.setup[n];if(!s)return;$$('button',setupSteps).forEach(b=>b.setAttribute('aria-selected',String(Number(b.dataset.step)===n)));setupDetail.setAttribute('aria-labelledby','setup-step-'+n);setupDetail.innerHTML='<div class="'+(animate?'switch-enter':'')+'"><span class="eyebrow">STEP 0'+(n+1)+' / DIAN115</span><h3>'+s.short+'</h3><p>'+s.text+'</p><div class="setup-chips">'+chips[n].map(c=>'<span>'+c+'</span>').join('')+'</div></div><button type="button" class="text-link" data-doc="'+s.doc+'">阅读这一步的完整教程 '+icon('arrow-right')+'</button><span class="setup-number" aria-hidden="true">0'+(n+1)+'</span>';}
  setup(0,false);setupSteps.addEventListener('click',e=>{const b=e.target.closest('button');if(b)setup(b.dataset.step);});arrowTabs(setupSteps,b=>setup(b.dataset.step));

  const portalGroups=[['all','全部入口'],['core','账户'],['media','观影'],['social','社区'],['support','支持']];
  const portalIcons={overview:'home',account:'users','115':'cloud',media:'film',requests:'search',server:'server',watchlist:'heart',history:'clock',checkin:'check',shop:'gift',community:'message',achievements:'activity',badges:'medal',resources:'folder',messages:'bell',tickets:'ticket'};
  const portalFilters=$('#portalFilters'),portalGrid=$('#portalGrid'),portalDetail=$('#portalDetail');let portalFilter='all',portalSelected='overview';
  portalGroups.forEach(([id,label])=>{const b=document.createElement('button');b.type='button';b.className='portal-filter';b.id='portal-filter-'+id;b.dataset.filter=id;b.setAttribute('role','tab');b.setAttribute('aria-controls','portalGrid');b.setAttribute('aria-selected',String(id==='all'));b.textContent=label;portalFilters.append(b);});
  portalGrid.setAttribute('role','tabpanel');
  function portalSelect(id){const p=data.portal.find(p=>p.id===id);if(!p)return;portalSelected=id;$$('.portal-tile',portalGrid).forEach(b=>{const on=b.dataset.portal===id;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});portalDetail.classList.remove('changing');portalDetail.innerHTML='<h4>'+p.title+'</h4><p>'+p.desc+'</p><a href="'+data.demo+'portal/#/'+p.id+'" target="_blank" rel="noopener noreferrer">在 Demo 中体验 '+icon('arrow-up-right')+'</a>';void portalDetail.offsetWidth;portalDetail.classList.add('changing');}
  function portalRender(filter,animate=true){portalFilter=filter;$$('button',portalFilters).forEach(b=>b.setAttribute('aria-selected',String(b.dataset.filter===filter)));const items=data.portal.filter(p=>filter==='all'||p.group===filter);portalGrid.setAttribute('aria-labelledby','portal-filter-'+filter);portalGrid.innerHTML=items.map((p,i)=>'<button type="button" class="portal-tile '+(animate?'switch-enter':'')+'" style="animation-delay:'+Math.min(i*.025,.25)+'s" data-portal="'+p.id+'">'+icon(portalIcons[p.id])+'<span>'+p.title+'</span></button>').join('');portalSelect(items.some(p=>p.id===portalSelected)?portalSelected:items[0].id);}
  portalRender('all',false);portalFilters.addEventListener('click',e=>{const b=e.target.closest('button');if(b)portalRender(b.dataset.filter);});portalGrid.addEventListener('click',e=>{const b=e.target.closest('button');if(b)portalSelect(b.dataset.portal);});arrowTabs(portalFilters,b=>portalRender(b.dataset.filter));

  const reader=$('#readerDialog'),readerContent=$('#readerContent'),readerToc=$('#readerToc');let lastMainHash='#top',activeDoc='';
  const dialogTimers=new WeakMap();
  function openDialog(d){clearTimeout(dialogTimers.get(d));dialogTimers.delete(d);d.classList.remove('is-closing');if(!d.open)d.showModal();}
  function closeDialog(d,after=()=>{},immediate=false){if(!d?.open){after();return;}if(dialogTimers.has(d)){if(!immediate)return;clearTimeout(dialogTimers.get(d));dialogTimers.delete(d);}const finish=()=>{dialogTimers.delete(d);d.classList.remove('is-closing');d.close();after();};if(immediate||root.dataset.motion==='quiet'){finish();return;}d.classList.add('is-closing');dialogTimers.set(d,setTimeout(finish,260));}
  let readerObserver,readerScrollFrame=0;
  function updateReaderProgress(){readerScrollFrame=0;const total=reader.scrollHeight-reader.clientHeight;$('#readerProgress').style.transform='scaleX('+(total>0?reader.scrollTop/total:1)+')';const sections=$$('.reader-section',readerContent);let current=sections[0]?.id;const edge=reader.getBoundingClientRect().top+135;sections.forEach(section=>{if(section.getBoundingClientRect().top<=edge)current=section.id;});$$('a',readerToc).forEach(a=>{const selected=a.getAttribute('href')==='#'+current;a.classList.toggle('current',selected);if(selected)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
  function animateReader(){readerObserver?.disconnect();readerContent.classList.remove('doc-enter');void readerContent.offsetWidth;readerContent.classList.add('doc-enter');$$(':scope > .eyebrow,:scope > h1,:scope > .reader-lead',readerContent).forEach((el,i)=>el.style.setProperty('--reader-delay',i*55+'ms'));$$('a',readerToc).forEach((el,i)=>el.style.setProperty('--reader-delay',Math.min(i*45,270)+'ms'));const blocks=$$(':scope > .reader-section,:scope > .code-block,:scope > .reader-plugin-list > article,:scope > .reader-donation,:scope > .reader-next',readerContent);if('IntersectionObserver'in window){readerObserver=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('reader-visible');readerObserver.unobserve(entry.target);}});},{root:reader,threshold:0,rootMargin:'0px 0px -15px 0px'});blocks.forEach((el,i)=>{el.classList.add('reader-reveal');el.style.setProperty('--reader-delay',Math.min(i*45,180)+'ms');readerObserver.observe(el);});}updateReaderProgress();}
  reader.addEventListener('scroll',()=>{if(!readerScrollFrame)readerScrollFrame=requestAnimationFrame(updateReaderProgress);},{passive:true});
  reader.addEventListener('close',()=>readerObserver?.disconnect());
  window.addEventListener('resize',()=>{if(reader.open)updateReaderProgress();},{passive:true});
  function docLink(id){return '#guide/'+encodeURIComponent(id);}
  const routeOverrides={discover:'automation/discovery',subscribe:'automation/subscriptions',organize:'automation/organizing',strm:'automation/portable-strm',music:'automation/music',accounts:'resources/accounts','my-media':'resources/media',pt:'resources/sites',cd2:'control/settings?focus=cd2',paths:'control/settings',flaresolverr:'control/settings','push-assistant':'resources/plugins/push-assistant'};
  function demoForDoc(id){const item=data.groups.flatMap(g=>g.items).find(x=>x.id===id);return data.demo+'#/'+(routeOverrides[id]||item?.route||'overview');}
  function codeBlock(label,value){return '<div class="code-block"><span class="code-label">'+escape(label)+'</span><button type="button" class="copy-code">复制配置</button><pre><code>'+escape(value)+'</code></pre></div>';}
  function guideSection([title,text,extra],i){let html='<section class="reader-section" id="reader-section-'+i+'"><h2>'+escape(title)+'</h2><p>'+escape(text)+'</p>';if(extra?.code){const sample=data.codeSamples[extra.code];if(sample)html+=codeBlock(sample.label,sample.text);}if(extra?.table){const t=extra.table;html+='<div class="guide-table-wrap"><table class="guide-table"><thead><tr>'+t.headers.map(h=>'<th scope="col">'+escape(h)+'</th>').join('')+'</tr></thead><tbody>'+t.rows.map(row=>'<tr>'+row.map((cell,j)=>'<td data-label="'+escape(t.headers[j])+'">'+escape(cell)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}if(extra?.guides)html+='<div class="guide-related">'+extra.guides.map(id=>'<button type="button" class="button button-outline" data-doc="'+id+'">'+escape(data.docs[id].title)+icon('arrow-right')+'</button>').join('')+'</div>';return html+'</section>';}
  function showDoc(id,updateHash=true){const d=data.docs[id];if(!d)return;activeDoc=id;if(updateHash&&!location.hash.startsWith('#guide/'))lastMainHash=location.hash||'#top';readerToc.innerHTML='<strong>本页内容</strong>'+d.sections.map(([title],i)=>'<a href="#reader-section-'+i+'">'+escape(title)+'</a>').join('');readerContent.innerHTML='<span class="eyebrow">'+d.kicker+'</span><h1 id="readerTitle">'+escape(d.title)+'</h1><p class="reader-lead">'+escape(d.lead)+'</p>'+d.sections.map(guideSection).join('');
    if(d.pluginList)readerContent.insertAdjacentHTML('beforeend','<div class="reader-plugin-list">'+data.plugins.map(([title,desc,route])=>'<article><h3>'+title+'</h3><p>'+desc+'</p><a class="text-link" href="'+data.demo+'#/resources/plugins/'+route+'" target="_blank" rel="noopener noreferrer">打开演示入口 '+icon('arrow-up-right')+'</a></article>').join('')+'</div>');
    if(d.portalList)readerContent.insertAdjacentHTML('beforeend','<div class="reader-plugin-list">'+data.portal.map(p=>'<article><h3>'+p.title+'</h3><p>'+p.desc+'</p></article>').join('')+'</div>');
    if(d.donation)readerContent.insertAdjacentHTML('beforeend','<div class="reader-donation"><a href="assets/payment-qr.png" target="_blank" rel="noopener noreferrer"><img src="assets/payment-qr.png" alt="DIAN115 官方捐赠收款二维码" width="525" height="502"><span>打开二维码原图 ↗</span></a><div><h2>捐赠支持 DIAN115</h2><div class="donation-prices"><div><span>个人版</span><strong>¥199</strong></div><div><span>S.O. 版</span><strong>¥499</strong></div></div><p>按对应金额扫码捐赠，付款备注填写可正常收信的邮箱，通过该邮箱接收授权码；收到 License Key 后即可激活。</p></div></div>');
    if(d.contact)readerContent.insertAdjacentHTML('beforeend','<div class="reader-next"><a class="button button-outline" href="https://t.me/succt" target="_blank" rel="noopener noreferrer">遇到问题？联系 @succt '+icon('arrow-up-right')+'</a><a class="button button-outline" href="https://t.me/dian115group" target="_blank" rel="noopener noreferrer">加入交流群 '+icon('arrow-up-right')+'</a></div>');
    else readerContent.insertAdjacentHTML('beforeend','<div class="reader-next"><a class="button button-outline" href="'+(id==='portal'?data.demo+'portal/':id==='music'?data.demo+'music/':demoForDoc(id))+'" target="_blank" rel="noopener noreferrer">去在线 Demo 体验 '+icon('arrow-up-right')+'</a><button type="button" class="text-link" data-close="readerDialog">返回首页 '+icon('arrow-right')+'</button></div>');
    openDialog(reader);reader.scrollTop=0;animateReader();if(updateHash)history.pushState({doc:id},'',docLink(id));}
  function closeReader(immediate=false){closeDialog(reader,()=>{activeDoc='';if(location.hash.startsWith('#guide/'))history.replaceState(null,'',lastMainHash);},immediate);}
  reader.addEventListener('cancel',e=>{e.preventDefault();closeReader();});
  readerToc.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;e.preventDefault();const el=$(a.getAttribute('href'),readerContent);if(el)el.scrollIntoView({behavior:root.dataset.motion==='quiet'?'auto':'smooth',block:'start'});});
  document.addEventListener('click',async e=>{
    const doc=e.target.closest('[data-doc]');if(doc){showDoc(doc.dataset.doc);return;}
    const close=e.target.closest('[data-close]');if(close){if(close.dataset.close==='readerDialog')closeReader();else closeDialog(document.getElementById(close.dataset.close));return;}
    const copy=e.target.closest('.copy-code');if(copy){const value=$('code',copy.closest('.code-block')).textContent;try{await navigator.clipboard.writeText(value);copy.textContent='已复制';toast('配置已复制');setTimeout(()=>copy.textContent='复制',2000);}catch{const selection=getSelection();const range=document.createRange();range.selectNodeContents($('code',copy.closest('.code-block')));selection.removeAllRanges();selection.addRange(range);toast('已选中内容，请使用 Ctrl / ⌘ C 复制');}}
  });
  [reader,$('#searchDialog')].forEach(d=>d.addEventListener('click',e=>{if(e.target!==d)return;const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom){if(d===reader)closeReader();else closeDialog(d);}}));
  function syncHash(){if(location.hash.startsWith('#guide/'))showDoc(decodeURIComponent(location.hash.slice(7)),false);else if(reader.open&&activeDoc)closeDialog(reader,()=>activeDoc='');}
  window.addEventListener('popstate',syncHash);window.addEventListener('hashchange',syncHash);syncHash();

  const searchDialog=$('#searchDialog'),searchInput=$('#searchInput'),searchResults=$('#searchResults');let searchIndex=0;
  const searchDocs=Object.entries(data.docs).map(([id,d])=>({id,title:d.title,lead:d.lead,hay:[d.title,d.lead,...d.sections.flatMap(([title,text,extra])=>[title,text,extra?.code?data.codeSamples[extra.code]?.text:'',extra?.table?[...extra.table.headers,...extra.table.rows.flat()].join(' '):''])].join(' ').toLowerCase()}));
  function renderSearch(){const q=searchInput.value.trim().toLowerCase();const rank=d=>(d.title.toLowerCase().includes(q)?100:0)+(d.lead.toLowerCase().includes(q)?20:0);const results=q?searchDocs.filter(d=>d.hay.includes(q)).sort((a,b)=>rank(b)-rank(a)).slice(0,15):searchDocs.filter(d=>['about','deploy','connections','organize','portal','so','license'].includes(d.id));searchIndex=0;searchResults.innerHTML=results.length?results.map((d,i)=>'<button type="button" class="search-result '+(i===0?'active':'')+'" style="--result-delay:'+Math.min(i*35,210)+'ms" data-result="'+d.id+'">'+icon('film')+'<span><b>'+escape(d.title)+'</b><small>'+escape(d.lead)+'</small></span>'+icon('arrow-up-right')+'</button>').join(''):'<p class="search-empty">没有找到这页。试试“整理”“账号”“门户”或“授权”。</p>';}
  function openSearch(){renderSearch();openDialog(searchDialog);searchInput.focus();}
  searchDialog.addEventListener('cancel',e=>{e.preventDefault();closeDialog(searchDialog);});
  $$('.search-open').forEach(b=>b.addEventListener('click',openSearch));searchInput.addEventListener('input',renderSearch);searchResults.addEventListener('click',e=>{const b=e.target.closest('button');if(b){closeDialog(searchDialog,()=>{},true);showDoc(b.dataset.result);}});
  searchInput.addEventListener('keydown',e=>{const results=$$('.search-result',searchResults);if(!results.length)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();searchIndex=(searchIndex+(e.key==='ArrowDown'?1:-1)+results.length)%results.length;results.forEach((b,i)=>b.classList.toggle('active',i===searchIndex));results[searchIndex].scrollIntoView({block:'nearest'});}if(e.key==='Enter'){e.preventDefault();closeDialog(searchDialog,()=>{},true);showDoc(results[searchIndex].dataset.result);}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(searchDialog.open){e.preventDefault();closeDialog(searchDialog);}else if(reader.open){e.preventDefault();closeReader();}return;}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(reader.open)closeReader(true);openSearch();}});

  const menuToggle=$('#menuToggle'),mobileMenu=$('#mobileMenu');
  function closeMenu(){mobileMenu.hidden=true;menuToggle.setAttribute('aria-expanded','false');menuToggle.innerHTML=icon('menu');}
  menuToggle.addEventListener('click',()=>{const on=mobileMenu.hidden;mobileMenu.hidden=!on;menuToggle.setAttribute('aria-expanded',String(on));menuToggle.innerHTML=icon(on?'x':'menu');});mobileMenu.addEventListener('click',e=>{if(e.target.closest('a'))closeMenu();});
  let tick=false;const progress=$('#readingProgress'),chapters=$$('.chapter'),chapterLinks=$$('#chapterNav a');
  function onScroll(){const y=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight;progress.style.transform='scaleX('+(h?y/h:0)+')';$('#siteHeader').classList.toggle('scrolled',y>25);$('#backTop').classList.toggle('visible',y>700);let current='';for(const c of chapters){if(c.getBoundingClientRect().top<=window.innerHeight*.35)current=c.id;}chapterLinks.forEach(a=>{const on=a.getAttribute('href')==='#'+current;a.classList.toggle('active',on);if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});tick=false;}
  window.addEventListener('scroll',()=>{if(!tick){requestAnimationFrame(onScroll);tick=true;}},{passive:true});onScroll();$('#backTop').addEventListener('click',()=>window.scrollTo({top:0,behavior:root.dataset.motion==='quiet'?'auto':'smooth'}));
  if('IntersectionObserver'in window){const io=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in-view');io.unobserve(e.target);}}),{threshold:.08});$$('.reveal').forEach(el=>io.observe(el));}else $$('.reveal').forEach(el=>el.classList.add('in-view'));
  $$('.magnetic').forEach(el=>{el.addEventListener('pointermove',e=>{if(!finePointer.matches||root.dataset.motion==='quiet')return;const r=el.getBoundingClientRect();el.style.translate=((e.clientX-r.left)/r.width-.5)*6+'px '+((e.clientY-r.top)/r.height-.5)*6+'px';});el.addEventListener('pointerleave',()=>el.style.translate='0 0');});
})();
