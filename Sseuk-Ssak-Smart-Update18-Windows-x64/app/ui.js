'use strict';
const $=s=>document.querySelector(s);
const menus=['파일 정리','정크 파일','폴더 용량','이전 버전 보관함 복원','크롬 다운로드','파일 구조화','폴더 정리'];
const titles=['어떤 파일을 정리할까요?','오래된 임시 파일을 찾아볼까요?','어느 폴더가 가장 클까요?','어떤 파일을 되돌릴까요?','최신 다운로드 파일만 남길까요?','파일과 폴더에 정리 기준을 적용해요','비슷한 폴더를 비교하고 정리해요'];
const subtitles=['폴더를 살펴보고 정리할 파일만 직접 골라요.','사용자 Temp와 선택한 폴더의 임시 파일·캐시를 확인해요.','폴더를 열어 안쪽에서 차지하는 용량까지 확인해요.','보관한 파일을 처음 있던 위치로 복원해요.','크롬 다운로드 목록의 실제 파일을 비교하고 최신 파일을 남겨요.','최대 5단계 · 날짜와 버전 관리 · 아카이브 · 즐겨찾기 5개','비슷한 이름의 폴더를 찾아 비교하고, 필요 없는 폴더만 휴지통으로 옮겨요.'];
const paths=['M3 6h7l2 3h9v11H3z','M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 10v7m4-7v7','M3 20h18M5 16v-4m6 4V7m6 9V3','M3 5h18v5H3zM5 11v9h14v-9m-10 2h6','M3 12a9 9 0 1 0 3-6M3 4v5h5m4-3v6l4 2','M9 3h6v5H9zM3 16h6v5H3zM15 16h6v5h-6zM12 8v4M6 16v-4h12v4','M3 7h7l2 2h9v11H3zM3 7V4h7l2 3M8 13h8m-8 3h5'];
const art='<svg class="art" aria-hidden="true" viewBox="0 0 150 120"><ellipse cx="76" cy="107" rx="56" ry="6" fill="#e5adb5"/><g transform="rotate(-8 76 71)"><path d="M19 34q0-6 7-6h31l10 11h54q7 0 7 7v51H19z" fill="#bd4a5a"/><rect x="35" y="21" width="66" height="66" rx="8" fill="#fff" transform="rotate(6 64 54)"/><path d="M46 39h40m-40 8h32" stroke="#e0b9bd" stroke-width="4" stroke-linecap="round"/><path d="M18 54q0-7 8-7h105q5 0 4 8l-9 42q-1 7-9 7H30q-8 0-9-8z" fill="#e77c88"/><path d="M37 61h31" stroke="#ffd2d9" stroke-width="4" stroke-linecap="round"/></g><path d="m124 12 3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill="#c44c61"/></svg>';
const icon=i=>'<svg aria-hidden="true" class="ico" viewBox="0 0 24 24"><path d="'+paths[i]+'"/></svg>';
const make=(tag,cls='',text='')=>{const x=document.createElement(tag);x.className=cls;x.textContent=text;return x};
function btn(parent,text,fn,cls=''){const x=make('button',cls,text);x.onclick=fn;x.disabled=busy;parent.append(x);return x}
function tile(i){const x=make('span','tile');x.innerHTML=icon(i);return x}
let state, page=0, filter='같은 이름',picked=new Set(),issues=new Map(),busy=false,rank=[],dir='',limit=80,checked=new Set();
let rankSort='size-desc',historyPaths=[],historyPosition=-1;
const parentPath=p=>p.replace(/[\\/][^\\/]+[\\/]?$/,'');
const scope=()=>menus[page]+':'+filter;
const fmt=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toLocaleString('ko-KR',{maximumFractionDigits:i?1:0})+' '+['B','KB','MB','GB','TB'][i]};
let category='전체',extension='',across=false;
const typeGroups={문서:['pdf','hwp','hwpx','doc','docx','xls','xlsx','ppt','pptx','txt','csv'],사진:['jpg','jpeg','png','gif','webp','heic','bmp','svg'],영상:['mp4','mov','mkv','avi','webm'],음악:['mp3','wav','m4a','flac','aac'],압축파일:['zip','7z','rar','tar','gz']};
const ext=r=>(r.name.includes('.')?r.name.split('.').pop().toLowerCase():'');
const type=r=>Object.keys(typeGroups).find(k=>typeGroups[k].includes(ext(r)))||'기타';
const eligible=r=>!r.protected;
const rows=()=>page===0?state.files.filter(r=>r.kind===filter&&(category==='전체'||type(r)===category)&&(!extension||ext(r)===extension)):page===1?state.junk:page===2?rank:page===3?state.stash:[];
const marked=()=>rows().filter(r=>picked.has(r.id)&&eligible(r));
function say(s){$('#status').textContent=s}
async function api(action,data={}){
 const r=await fetch('api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const result=await r.json();if(!r.ok)throw Error(result.error||'앱을 다시 실행해 주세요.');
 if(result.state_patch){
  if(result.file_updates){const updates=new Map(result.file_updates.map(row=>[row.id,row]));state={...state,files:state.files.map(row=>updates.has(row.id)?{...row,...updates.get(row.id)}:row)}}
  return {...state,...result.state_patch}
 }
 return result
}
function lock(on){busy=on;document.body.classList.toggle('busy',on);for(const e of document.querySelectorAll('button,input:not(#reduce)'))e.disabled=on}
async function work(fn){if(busy||scanning)return;lock(true);try{await fn()}catch(e){say(e.message)}finally{lock(false);render()}}
async function modal(title,detail,action){
 const d=document.querySelector('dialog:not(#progressDialog)');$('#dialogTitle').textContent=title;$('#dialogDesc').textContent=detail;
 const a=$('#dialogBtns');a.replaceChildren();const no=btn(a,'닫기',()=>d.close('no'));if(action)btn(a,action,()=>d.close('yes'),'primary');
 d.returnValue='';d.showModal();no.focus();
 return new Promise(resolve=>d.addEventListener('close',()=>resolve(d.returnValue==='yes'),{once:true}))
}
function motionOff(){return $('#reduce').checked||matchMedia('(prefers-reduced-motion: reduce)').matches}
$('#reduce').checked=localStorage.getItem('reduce')==='1';$('#reduce').onchange=()=>{localStorage.setItem('reduce',$('#reduce').checked?'1':'0')};
let scanning=false;
async function scan(pick=false){
 if(busy||scanning)return;
 const mode=page===1?'junk':'files', old=state.root;
 const detail=$('#scanDetail'),panel=$('#scanPanel');
 scanning=true;
 panel.hidden=false;
 detail.textContent=pick||(!old&&mode==='files')?'선택 창에서 검사할 폴더를 골라 주세요.':'폴더 안의 파일을 확인하고 있어요.';
 say('');
 render();
 try{
  const result=await streamAction('scan',{pick,mode,across},message=>{detail.textContent=message});
  if(result.cancel){say('폴더 선택을 취소했어요.');return}
  if(old!==result.root)checked.clear();
  checked.add(mode);
  state=result;
  dir=result.root;historyPaths=dir?[dir]:[];historyPosition=dir?0:-1;
  rank=[];
  limit=80;
  picked.clear();
  issues.clear();
  if(page===2)rank=await api('rank',{path:dir});
  say('검사가 끝났어요.'+(result.logs.length?' 확인할 항목 '+result.logs.length+'개':''));
 }catch(error){say(error.message)}
 finally{scanning=false;panel.hidden=true;render()}
}
async function switchTo(i){if(busy)return;
 if(scanning){page=i;picked.clear();limit=80;render();return}
 await work(async()=>{page=i;picked.clear();limit=80;say('');if(i===2){if(!dir||!historyPaths.length){dir=state.root;historyPaths=dir?[dir]:[];historyPosition=dir?0:-1}rank=await api('rank',{path:dir})}})}
function render(){
 if(!state)return;
 const firstFilePage=page===0&&!state.root;document.body.classList.toggle('file-welcome',firstFilePage);$('.content').hidden=firstFilePage;
 const nav=$('nav'),emptyButton=$('#emptyRecycle');nav.replaceChildren();[0,6,5,1,2,3,4].forEach(i=>{const n=menus[i];const b=btn(nav,'',()=>switchTo(i),'navbtn'+(i===page?' active':''));b.innerHTML=icon(i);b.append(document.createTextNode(n));if(i===page)b.setAttribute('aria-current','page')});
 emptyButton.className='navbtn';emptyButton.innerHTML=icon(1);emptyButton.append(document.createTextNode('휴지통 비우기'));emptyButton.disabled=busy||scanning;nav.append(emptyButton);
 const space=$('#spaceOverview');space.hidden=!state.root||page===4;const refresh=state.root&&page!==4&&page!==5?{label:'용량 다시 측정',onClick:()=>work(async()=>{state=await api('refresh_space',{compact:true});say('현재 드라이브 용량을 다시 측정했어요. 이전 정리 전후 비교는 초기화했습니다.')})}:null;
 renderStorage(space,state.storage_comparison||{before:state.storage_current||[],after:[],moved:{}},'all',refresh);
 let resetBar=$('#resetToolbar');if(!resetBar){resetBar=make('div','reset-toolbar');resetBar.id='resetToolbar';$('.heading').append(resetBar)}resetBar.replaceChildren();
 if(page===0&&state.root){btn(resetBar,'다시 검사',()=>scan(false),'outline-control');btn(resetBar,'선택 초기화',resetFileSelection,'outline-control')}
 $('#crumb').textContent=menus[page];$('#title').textContent=titles[page];$('#sub').textContent=subtitles[page];
 if(page===5){space.hidden=true;renderSmart();return}
 if(page===6){space.hidden=true;renderFolderPage();return}
 const hero=$('#hero');hero.replaceChildren();hero.insertAdjacentHTML('beforeend',art);
 const h=make('div','hero-copy'),heading=page===4?'다운로드 파일과 기록 정리':page===1?'오래된 임시 파일 검사':state.root?(state.root_name||state.root.split(/[\\/]/).pop()||state.root):'정리할 폴더를 골라 주세요';
 h.append(make('h2','',heading),make('p','',page===4?'선택한 실제 파일을 휴지통으로 옮기고 성공한 항목의 기록만 지워요.':page===1?'7일 이상 지난 임시 파일과 확인 가능한 캐시를 찾아요.':state.root||'다운로드, 바탕 화면, 문서 중 한 곳부터 시작해요.'));hero.append(h);
 if(page===4){btn(h,'다운로드 파일 확인',clearChrome,'primary')}
 else{btn(h,page===1?'정크 파일 찾기':state.root?'다시 검사하기':'폴더 선택하기',()=>scan(false),picked.size?'':'primary');if(state.root||page===1)btn(h,'다른 폴더 선택',()=>scan(true))}
 if(page===0&&!state.root){
  h.replaceChildren(make('div','welcome-step','STEP 01 · 폴더 선택'),make('h2','','정리할 폴더를 골라 주세요'),make('p','','다운로드, 바탕 화면, 문서 등 정리하고 싶은 폴더부터 시작하세요. 폴더를 선택하면 안에 있는 파일을 검사하고 결과를 보여드립니다.'));
  btn(h,'폴더 선택하고 검사하기',()=>scan(true),'primary');h.append(make('small','welcome-safety','검사만으로 파일이 이동하거나 삭제되지는 않습니다.'));
  $('#filters').replaceChildren();$('#list').replaceChildren();$('#tools').replaceChildren();$('#actionbar').replaceChildren();return;
 }
 const items=rows(),tools=$('#tools'),filters=$('#filters');tools.replaceChildren();filters.replaceChildren();
 $('#section').textContent=page===4?'크롬 연결':page===2?'폴더별 사용량':page===3?'보관한 파일':(!state.root&&page===0?'이런 파일을 찾을 수 있어요':'검사 결과');
 if(page===0&&state.root)for(const f of state.filters){const b=btn(filters,f,()=>{filter=f;picked.clear();limit=80;say('');render()},'chip'+(f===filter?' on':''));b.setAttribute('aria-pressed',String(filter===f))}
 if(page===0){
  const bar=make('div','typebar');
  for(const c of ['전체',...Object.keys(typeGroups),'기타'])btn(bar,c,()=>{category=c;extension='';picked.clear();render()},'chip'+(c===category?' on':''));
  const select=make('select');select.setAttribute('aria-label','확장자 필터');
  for(const e of ['',...new Set([...Object.values(typeGroups).flat(),'html','htm','js','ts','tsx','jsx','css','py','json','md',...(state.extensions||[])])].sort()){
   const option=make('option','',e?'.'+e:'모든 확장자');option.value=e;select.append(option);
  }
  select.value=extension;select.onchange=()=>{extension=select.value;picked.clear();render()};select.disabled=busy;bar.append(select);
  const label=make('label'),check=make('input');check.type='checkbox';check.checked=across;check.disabled=busy||scanning;check.onchange=()=>{across=check.checked;picked.clear();scan(false)};label.append(check,document.createTextNode('하위 폴더 사이의 같은 이름 파일 비교'));bar.append(label);
  filters.append(bar);if(across)filters.append(make('p','cross-folder-note','폴더 간 비교가 켜져 있습니다. 선택한 위치와 모든 하위 폴더에서 이름이 같은 파일을 비교합니다. 공통 단어 묶기는 끄고 기본 이름 방식으로 사용하세요. 내용이 같다는 의미는 아니므로 남길 파일을 확인하세요.'));
  if(filter==='같은 이름'){
   const grouping=make('div','typebar');
   const similarLabel=make('label'),similarBox=make('input');similarBox.type='checkbox';similarBox.checked=!!state.similar_names;similarBox.disabled=busy||scanning||state.word_mode!=='off';similarLabel.append(similarBox,document.createTextNode('비슷한 이름 모아보기'));grouping.append(similarLabel);
   const wordSelect=make('select');wordSelect.setAttribute('aria-label','공통 단어 묶기');for(const [value,label] of [['off','공통 단어 묶기 끔'],['auto','자동 · 공통 단어 2개 이상'],['manual','직접 입력한 문구로 묶기']]){const o=make('option','',label);o.value=value;wordSelect.append(o)}wordSelect.value=state.word_mode||'off';wordSelect.hidden=true;const modeButtons=make('div','group-mode-buttons');for(const [value,label] of [['off','기본 이름'],['auto','공통 단어 자동'],['manual','문구 직접 입력']]){const choice=btn(modeButtons,label,()=>{wordSelect.value=value;for(const item of modeButtons.children)item.setAttribute('aria-pressed',String(item.dataset.mode===value));keyword.hidden=value!=='manual';applyButton.hidden=value!=='manual';similarLabel.hidden=value!=='off';if(value!=='manual')applyGrouping()},'group-mode-button');choice.dataset.mode=value;choice.setAttribute('aria-pressed',String(wordSelect.value===value));}grouping.append(modeButtons);
   const keyword=make('input','group-keyword');keyword.placeholder='묶을 문구: 예) Sseuk-Ssak';keyword.setAttribute('aria-label','묶을 문구');keyword.maxLength=100;keyword.value=state.word_keyword||'';
   const applyGrouping=()=>work(async()=>{state=await api('grouping',{word_mode:wordSelect.value,keyword:keyword.value,similar:similarBox.checked});picked.clear();issues.clear();limit=80;say('묶기 기준을 적용했어요. 내용이 같은 파일인지는 별도로 확인하세요.')});
   similarBox.onchange=applyGrouping;grouping.append(wordSelect,keyword);const applyButton=btn(grouping,'묶기 적용',applyGrouping,'outline-control');keyword.hidden=wordSelect.value!=='manual';applyButton.hidden=wordSelect.value!=='manual';similarLabel.hidden=wordSelect.value!=='off';keyword.onkeydown=e=>{if(e.key==='Enter')applyGrouping()};filters.append(grouping,make('p','filter-note','공통 단어는 관련 후보입니다. 같은 폴더·형식·플랫폼끼리 비교하며 내용이 같다는 의미는 아닙니다.'));
   const policy=make('div','typebar');policy.append(make('b','','남길 기준'));
   for(const [value,label] of [['version','높은 버전'],['date','수정 날짜'],['number','괄호 숫자'],['manual','직접 지정']]){
    const b=btn(policy,label,()=>setKeeper({mode:value}),'chip'+(state.keeper_mode===value?' on':''));b.disabled=busy||scanning;b.setAttribute('aria-pressed',String(state.keeper_mode===value));
   }
   filters.append(policy,make('p','filter-note',state.keeper_mode==='version'?'이름의 v1.2 같은 버전 숫자가 가장 큰 파일을 추천합니다. 버전이 없으면 수정 날짜를 비교합니다.':state.keeper_mode==='number'?'괄호 숫자가 가장 큰 파일을 남겨요. 숫자는 내용의 최신 여부를 보장하지 않아요.':state.keeper_mode==='manual'?'각 묶음에서 ‘이 파일 남기기’를 누르세요. 지정하지 않은 묶음은 선택되지 않아요.':'수정 날짜가 가장 늦은 파일을 남겨요. 날짜가 같으면 직접 지정해 주세요.'));
  }
 }
 const shown=sortRows(items).slice(0,limit),shownEligible=shown.filter(eligible),moreHidden=items.length>shown.length;
  const selectionLabel=(page===0&&filter==='같은 이름'?'남길 파일 제외하고 선택':'전체 선택')+(moreHidden?' (화면의 '+shownEligible.length+'개)':'');
  const selectionButton=page!==2&&items.length&&filterAllowed()?btn(tools,picked.size?'선택 해제':selectionLabel,()=>{picked=picked.size?new Set():new Set(shownEligible.map(r=>r.id));render()}):null;
 if(page===2){
  const back=btn(tools,'← 뒤로',()=>navigateHistory(-1));back.disabled=busy||historyPosition<=0;
  const forward=btn(tools,'앞으로 →',()=>navigateHistory(1));forward.disabled=busy||historyPosition>=historyPaths.length-1;
  const up=btn(tools,'상위 폴더',()=>enter(parentPath(dir)||state.root));up.disabled=busy||!dir||dir===state.root;
  const select=make('select','rank-sort');select.setAttribute('aria-label','폴더 용량 정렬');
  for(const [value,label] of [['size-desc','크기 · 큰 순'],['size-asc','크기 · 작은 순'],['date-desc','수정 날짜 · 최신순'],['date-asc','수정 날짜 · 오래된 순']]){const option=make('option','',label);option.value=value;select.append(option)}
  select.value=rankSort;select.disabled=busy||scanning;select.onchange=()=>{rankSort=select.value;render()};tools.append(select);
  const all=make('label','rank-select-all'),box=make('input');box.type='checkbox';box.setAttribute('aria-label','현재 폴더 전체 선택');const candidates=shownEligible;box.checked=!!candidates.length&&candidates.every(r=>picked.has(r.id));box.indeterminate=candidates.some(r=>picked.has(r.id))&&!box.checked;box.disabled=busy||scanning||!candidates.length;box.onchange=()=>{picked=box.checked?new Set(candidates.map(r=>r.id)):new Set();render()};all.append(box,document.createTextNode('전체 선택'));filters.append(all,make('p','filter-note',dir+' · 폴더 열기로 이동 · 날짜는 각 파일/폴더 자체의 수정 날짜예요.'));
 }
 if(state.logs.length)btn(tools,'검사 기록',()=>modal('검사 기록',state.logs.slice(0,30).join('\n')));
 const list=$('#list');list.replaceChildren();
 if(page!==4){const sortText=page===2?({'size-desc':'크기 큰 순','size-asc':'크기 작은 순','date-desc':'수정 날짜 최신순','date-asc':'수정 날짜 오래된 순'}[rankSort]):page===0&&['같은 이름','작업 버전','변환 파일'].includes(filter)?'묶음 이름순 · 묶음 안은 '+(filter==='같은 이름'?'남길 파일 우선 · ':'')+'크기 큰 순':'크기 큰 순';list.append(make('p','sort-caption','정렬: '+sortText));}
 if(page===3)list.append(make('p','restore-help','이전 버전이 별도 보관함에 옮겨 둔 파일만 원래 위치로 복원합니다. 현재 휴지통으로 옮긴 파일은 Windows 휴지통에서, 99_아카이브 파일은 파일 구조화에서 관리하세요. 선택한 폴더에 이전 보관함이 없으면 목록은 비어 있습니다.'));

 if(page===4){guide(4,'크롬 다운로드 연결 도우미 등록','크롬 다운로드 정리를 쓸 때만 필요해요. 압축을 푼 폴더의 ‘크롬 다운로드 연결 도우미’를 등록하세요.');if(state.chrome_report)btn(list,'최근 기록 정리 결과 보기',()=>showChromeResult(state.chrome_report));btn(list,'크롬 연결 도우미 등록하기',()=>work(async()=>{const v=await api('setup');try{await navigator.clipboard.writeText(v.path)}catch{}say('크롬의 개발자 모드 → 압축해제된 확장 프로그램 로드 → '+v.path)}));}
 else if(!state.root&&page===0){guide(5,'복사본','이름이 달라도 내용이 같은 파일을 찾아요.');guide(3,'풀어둔 ZIP','압축을 푼 폴더에 모든 파일이 있는지 비교해요.');guide(0,'작업 버전','초안과 최종본을 같은 묶음에서 살펴봐요.')}
 else if(!items.length){list.append(make('p','blank',page===1&&!checked.has('junk')?'정크 파일 찾기를 눌러 검사를 시작하세요.':page===3?'보관한 파일이 여기에 표시돼요.':page===2?'검사하면 폴더별 용량을 볼 수 있어요.':'현재 분류에 표시할 파일이 없어요.'))}
 else{
  let group='';const groupCounts=new Map();for(const item of items)if(item.group)groupCounts.set(item.group,(groupCounts.get(item.group)||0)+1);
 for(const r of shown){
  if(r.group&&r.group!==group){group=r.group;list.append(make('h3','group',group.split(/[\\/]/).pop().replace(/\s*\(\d+\)(?=\.[^.]+$|$)/,'')+' · '+groupCounts.get(group)+'개 버전'))}
 const row=make('div','row'+(picked.has(r.id)?' selected':''));if(r.id)row.dataset.id=r.id;
  if(filterAllowed()&&eligible(r)){let box=make('input');box.type='checkbox';box.checked=picked.has(r.id);box.setAttribute('aria-label',r.name+' 선택');box.onchange=()=>{if(box.checked)picked.add(r.id);else picked.delete(r.id);row.classList.toggle('selected',box.checked);footer();if(selectionButton)selectionButton.textContent=picked.size?'선택 해제':selectionLabel;if(page===2){const all=filters.querySelector('.rank-select-all input');all.checked=!!shownEligible.length&&shownEligible.every(r=>picked.has(r.id));all.indeterminate=shownEligible.some(r=>picked.has(r.id))&&!all.checked}};row.onclick=e=>{if(!busy&&e.target!==box&&!e.target.closest('button'))box.click()};row.append(box)}
 else{row.append(tile(r.folder?0:5));row.tabIndex=0;row.onclick=()=>r.folder?enter(r.path):reveal(r.path);row.onkeydown=e=>{if(e.key==='Enter')row.click()}}
 const t=make('div','text'),p=make('small','',r.path);p.title=r.path;t.append(make('b','',r.name),p);
 const problem=issues.get(r.path);t.append(make('em',problem?'error':'',problem||[r.note,r.date,r.folder?r.count+'개 파일':''].filter(Boolean).join(' · ')));row.append(t,make('div','amount',fmt(r.size)));
 if(page===0){const open=btn(row,'파일 열기',()=>{},'file-open');open.onclick=e=>{e.stopPropagation();work(async()=>{const v=await api('open_file',{id:r.id});if(v.preview&&await modal(v.preview.title,v.preview.detail,'탐색기에서 위치 보기'))await api('reveal',{path:r.path})})};open.setAttribute('aria-label',r.name+' 파일 열기')}
 if(page===2){const open=btn(row,r.folder?'폴더 열기':'파일 위치',()=>{});open.onclick=e=>{e.stopPropagation();r.folder?enter(r.path):reveal(r.path)}}
 if(page===0&&filter==='같은 이름'){
  const keeper=btn(row,'이 파일 남기기',e=>{},'keep-button');keeper.onclick=e=>{e.stopPropagation();setKeeper({id:r.id})};keeper.disabled=busy||scanning;
  if(r.note.startsWith('남길 파일 ·')){row.classList.add('keeper-row');keeper.textContent='남길 파일';keeper.disabled=true}
 }
 list.append(row)
 }
 if(limit<items.length)btn(list,'다음 80개 보기',()=>{limit+=80;render()},'more')
 }
 if(page===0)frameFileFilters();
 footer()
 if(scanning){
  for(const control of document.querySelectorAll('#hero button,#actionbar button,#list input,#list button:not(.more),#tools button'))control.disabled=true;
 }
}
async function setKeeper(value){await work(async()=>{state=await api('keeper',{...value,compact:true});picked.clear();issues.clear();say('남길 파일을 갱신했어요. 정리할 파일을 선택하세요.')})}
function sortRows(items){
 const ordered=items.slice();
 if(page===0&&['같은 이름','작업 버전','변환 파일'].includes(filter))ordered.sort((a,b)=>a.group.localeCompare(b.group,'ko')||(filter==='같은 이름'?Number(b.protected)-Number(a.protected):0)||b.size-a.size);
 else if(page===2)ordered.sort((a,b)=>(rankSort.startsWith('date')?(a.modified||0)-(b.modified||0):a.size-b.size)*(rankSort.endsWith('desc')?-1:1)||a.name.localeCompare(b.name,'ko'));
 else ordered.sort((a,b)=>b.size-a.size);
 return ordered;
}
function filterAllowed(){return page!==0||filter!=='ZIP 확인'}
function guide(i,n,s){const g=make('div','guide'),t=make('div','text');t.append(make('b','',n),make('small','',s));g.append(tile(i),t);$('#list').append(g)}
function footer(){const a=$('#actionbar');a.replaceChildren();const m=marked();if(!m.length)return;
 a.append(make('b','',m.length.toLocaleString()+'개 선택 · '+fmt(m.reduce((s,r)=>s+r.size,0))));
 if(m.length===1){btn(a,'파일 위치',()=>reveal(m[0].reveal||m[0].path));if(m[0].compare)btn(a,'비교 위치',()=>reveal(m[0].compare))}
 btn(a,page===3?'원래 위치로 복원':'휴지통으로 이동',()=>apply(page===3?'restore':'trash'),'primary')}
function reveal(path){return work(()=>api('reveal',{path}))}
function enter(path){return work(async()=>{const next=await api('rank',{path});rank=next;dir=path;historyPaths=historyPaths.slice(0,historyPosition+1);historyPaths.push(path);historyPosition=historyPaths.length-1;limit=80;picked.clear()})}
function navigateHistory(delta){const target=historyPosition+delta;if(target<0||target>=historyPaths.length)return;return work(async()=>{const path=historyPaths[target];rank=await api('rank',{path});dir=path;historyPosition=target;picked.clear();limit=80})}
function showChromeResult(v){
 const entry=r=>({name:r.name,path:r.path,date:r.date||'',size:r.size??null,kind:'다운로드 기록',reason:r.reason});
 showCleanupResult({remaining:(v.remaining||[]).map(entry),moved:(v.deleted||[]).map(entry),failed:[...(v.failed||[]),...(v.record_failed||[])].map(entry),storage:v.storage},v.file_cleanup?'휴지통 이동':'지운 기록');
 $('#resultHeading').textContent=v.file_cleanup?'다운로드 파일 정리 결과':'다운로드 기록 정리 결과';
 $('#resultWindow > p').textContent=v.file_cleanup?'실제 파일은 휴지통으로 이동했어요. 기록 정리 실패 항목은 이유를 확인하세요.':'이전 버전에서 기록만 지운 결과예요.';
 $('#resultWindow th:nth-child(2)').textContent=v.file_cleanup?'파일 수정 날짜':'다운로드 날짜';
}
async function clearChrome(){let result;await work(async()=>{say('열린 크롬 탭에서 목록을 확인하고 지울 기록을 선택하세요.');await api('chrome');let v;do{await new Promise(r=>setTimeout(r,1500));v=await api('chrome_status')}while(v.running);if(v.state)state=v.state;state.chrome_report=v;say('다운로드 파일 '+v.deleted.length+'개를 휴지통으로 옮겼어요.'+(v.save_warning||''));result=v});if(result)showChromeResult(result)}
const progressDialog=$('#progressDialog');
progressDialog.addEventListener('cancel',e=>e.preventDefault());
function updateProgress(p) {
 const percent=p.total?Math.min(99,Math.floor(p.done*100/p.total)):0;
 if(p.phase==='finalizing')$('#progressTitle').textContent='정리 결과를 준비하고 있어요.';
 $('#progressPercent').textContent=percent+'%';
 $('#progressCount').textContent=p.done.toLocaleString()+' / '+p.total.toLocaleString()+'개';
 $('#progressMeter').value=percent;
 $('#progressFile').textContent=p.file;
 $('#progressFile').title=p.file;
 $('#progressHint').textContent='처리 완료 '+p.success+'개 · 실패 '+p.failed+'개';
}
async function applyWithProgress(data) {
 updateProgress({done:0,total:data.ids.length,success:0,failed:0,file:'파일 상태 확인 중'});
 $('#progressTitle').textContent=data.op==='restore'?'파일을 복원하고 있어요.':'휴지통으로 옮기고 있어요.';
 progressDialog.showModal();
 try {
  const result=await streamAction('apply',data,updateProgress);
  $('#progressPercent').textContent='100%';$('#progressMeter').value=100;
  return result;
 }finally{progressDialog.close()}
}
async function streamAction(action,data,onProgress){
  const response=await fetch('api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(!response.ok)throw Error('작업을 시작하지 못했어요. 목록을 다시 검사해 주세요.');
  const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='',result;
  function handle(line) {
   if(!line.trim())return;
   const message=JSON.parse(line);
   if(message.error)throw Error(message.error);
   if(message.progress)onProgress(message.progress);
   if(message.result)result=message.result;
  }
  while(true) {
   const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
   let split;
   while((split=buffer.indexOf('\n'))>=0){handle(buffer.slice(0,split));buffer=buffer.slice(split+1)}
   if(result){await reader.cancel();break}
   if(done){handle(buffer);break}
  }
  if(!result)throw Error('작업 결과를 받지 못했어요. 파일을 다시 검사해 주세요.');
  return result;
}
function showCleanupResult(report,label){
 $('#resultHeading').textContent='정리 결과';$('#resultWindow > p').textContent='남은 항목과 이동한 파일을 확인하세요.';$('#resultWindow th:nth-child(2)').textContent='수정한 날짜';
 let resultPage=1;
 function changeResultPage(value){resultPage=value;$('#resultGraphPage').hidden=value!==1;$('#resultDetailPage').hidden=value!==2;$('#resultPageNumber').textContent=value+' / 2';$('#resultPrevious').hidden=value===1;$('#resultNext').hidden=value===2;$('#resultWindow').scrollTop=0}
 $('#resultPrevious').onclick=()=>changeResultPage(1);$('#resultNext').onclick=()=>changeResultPage(2);
 const volumes=report.storage?.before||[];const volumeNav=$('#resultVolumeNav');volumeNav.replaceChildren();
 function drawVolume(index){const before=volumes[index];renderStorage($('#storageResult'),before?{...report.storage,before:[before],after:(report.storage.after||[]).filter(v=>v.volume===before.volume)}:null,'graphs');if(!before)$('#storageResult').textContent='이 작업에는 디스크 용량 비교 정보가 없어요.'}
 if(volumes.length>1){const select=make('select','rank-sort');select.setAttribute('aria-label','비교할 드라이브');volumes.forEach((v,i)=>{const o=make('option','',v.volume);o.value=i;select.append(o)});select.onchange=()=>drawVolume(Number(select.value));volumeNav.append(select)}
 drawVolume(0);renderStorage($('#storageTypes'),report.storage,'types');changeResultPage(1);
 const dialog=$('#resultWindow'), tabs=$('#resultTabs'), body=$('#resultBody'), pager=$('#resultPager');
 const groups=[['remaining','남은 항목'],['moved',label],['failed','실패']];
 let active=report.remaining.length?'remaining':report.moved.length?'moved':'failed', offset=0;
 let largestFirst=true;
 const sortButton=$('#sizeOrder');
 function sortReport(){
  for(const [key] of groups)report[key].sort((a,b)=>{
   if(a.size===null)return b.size===null?0:1;
   if(b.size===null)return -1;
   return largestFirst?b.size-a.size:a.size-b.size;
  });
  sortButton.textContent=largestFirst?'크기 · 큰 순 ▼':'크기 · 작은 순 ▲';
  sortButton.title=largestFirst?'작은 순으로 보기':'큰 순으로 보기';
  sortButton.parentElement.setAttribute('aria-sort',largestFirst?'descending':'ascending');
 }
 sortButton.onclick=()=>{largestFirst=!largestFirst;offset=0;sortReport();display()};
 sortReport();
 const pageSize=Math.max(1,Math.min(5,Math.floor((innerHeight-440)/62)));
 function display(){
  body.replaceChildren(); pager.replaceChildren();
  for(const button of tabs.children)button.setAttribute('aria-pressed',String(button.dataset.group===active));
  const items=report[active];
  for(const item of items.slice(offset,offset+pageSize)){
   const row=make('tr'), cell=make('td');
   cell.append(make('strong','',item.name),make('small','',item.path));
   if(item.reason)cell.append(make('small','error',item.reason));
   row.append(cell,make('td','',item.date),make('td','',item.kind),make('td','',item.size===null?'—':fmt(item.size)));
   body.append(row);
  }
  if(!items.length){const cell=make('td','','해당하는 항목이 없어요.');cell.colSpan=4;const row=make('tr');row.append(cell);body.append(row)}
  if(items.length>pageSize){
   if(offset)btn(pager,'이전',()=>{offset-=pageSize;display()});
   pager.append(make('span','',(offset+1)+'–'+Math.min(offset+pageSize,items.length)+' / '+items.length));
   if(offset+pageSize<items.length)btn(pager,'다음',()=>{offset+=pageSize;display()});
  }
  body.closest('.result-scroll').scrollTop=0;
 }
 tabs.replaceChildren();
 for(const [key,title] of groups){
  const button=btn(tabs,title+' '+report[key].length+'개',()=>{active=key;offset=0;display()});
  button.dataset.group=key;
 }
 display();dialog.showModal();
}
async function apply(op){
 const m=marked(),label={trash:'휴지통으로 이동',restore:'원래 위치로 복원'}[op];if(!m.length)return;
 if(!await modal(label+'할까요?',m.length+'개 · '+fmt(m.reduce((s,r)=>s+r.size,0))+'\n'+({trash:page===2?'선택한 폴더는 안의 파일까지 모두 휴지통으로 이동해요. Windows 휴지통에서 복원할 수 있어요.':'Windows 휴지통에서 복원할 수 있어요.',restore:'기존 파일과 충돌하면 건너뛰어요.'})[op],label))return;
 let report;
 await work(async()=>{const selected=[...document.querySelectorAll('.row.selected')].filter(el=>{let b=el.getBoundingClientRect();return b.bottom>0&&b.top<innerHeight});const anim=op==='trash'&&!motionOff();const anims=[];
 try{
 if(anim&&selected.length){let end=Math.min(innerHeight,$('#list').getBoundingClientRect().bottom)-54;selected.forEach((el,i)=>{el.style.zIndex='1';const dy=Math.max(0,end-el.getBoundingClientRect().top-i*2);anims.push(el.animate([{transform:'none'},{transform:'translateY('+dy+'px)'}],{duration:290,easing:'ease-out',fill:'forwards'}))});await Promise.all(anims.map(a=>a.finished))}
 say('파일 상태를 확인하고 있어요…');const v=await applyWithProgress({ids:m.map(r=>r.id),op});
 if(anim&&!motionOff()){const next=selected.map(el=>{let t=getComputedStyle(el).transform;return el.animate([{transform:t},{transform:v.ok.includes(el.dataset.id)?'translateX(110%) '+(t==='none'?'':t):'none'}],{duration:270,easing:'ease-in',fill:'forwards'})});anims.push(...next);await Promise.all(next.map(a=>a.finished))}
 report=v.report;state=v.state;if(page===2)rank=await api('rank',{path:dir});const failed=new Set();for(const r of m){if(v.errors[r.id]){issues.set(r.path,v.errors[r.id]+' · 파일 위치를 확인한 뒤 다시 시도하세요.');failed.add(r.path)}else issues.delete(r.path)}
 picked=new Set(rows().filter(r=>failed.has(r.path)).map(r=>r.id));say(label+' '+v.ok.length+'개 · 실패 '+failed.size+'개')
 }finally{anims.forEach(a=>a.cancel())}});
 if(report)showCleanupResult(report,label);
}
$('#repairDownloads').onclick=async()=>{if(busy||scanning)return;if(!await modal('다운로드 표시 이름을 복구할까요?','다운로드의 Windows 기본 표시 이름·아이콘과 폴더 속성을 복구해요. 기존 설정은 백업하며 실제 폴더명과 안의 파일은 바꾸지 않아요.','다운로드 표시 복구'))return;let result;await work(async()=>{result=await api('repair_downloads');say('다운로드 표시 설정 복구를 마쳤어요.')});if(result)await modal('다운로드 표시 설정을 복구했어요.',result.message)};
api('init').then(v=>{state=v;render()}).catch(e=>say(e.message));setInterval(()=>!busy&&!scanning&&fetch('api/ping',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{}),15000);

$('#emptyRecycle').onclick=async()=>{
 if(busy||scanning)return;
 let info;await work(async()=>{info=await api('recycle_info')});if(!info)return;
 if(!await modal('휴지통을 완전히 비울까요?','대상: 현재 사용자의 모든 드라이브 휴지통\n현재 용량: '+(info.size===null?'측정하지 못했어요.':fmt(info.size))+'\n\n쓱-싹으로 옮긴 파일뿐 아니라 기존 휴지통 파일도 영구 삭제돼요. 휴지통에서 복원할 수 없어요.','영구 삭제하기'))return;
 let result;await work(async()=>{say('휴지통을 비우고 있어요. Windows 진행 창을 확인하세요.');result=await api('empty_recycle',{confirmed:true});state=result.state;say(result.error||'휴지통 비우기를 마쳤어요.')});
 if(result)await modal(result.error?'휴지통에 남은 파일을 확인해 주세요.':'휴지통 비우기 결과',(result.error||'Windows 휴지통 비우기를 완료했어요.')+'\n남은 휴지통 용량: '+(result.remaining===null?'측정하지 못했어요.':fmt(result.remaining)));
};

function frameFileFilters(){
 const filters=$('#filters'),nodes=[...filters.children];filters.replaceChildren();
 const groups={};
 function section(key,title){if(!groups[key]){const box=make('section','filter-panel');box.append(make('h3','filter-panel-title',title));const inner=make('div','filter-panel-body');box.append(inner);filters.append(box);groups[key]=inner}return groups[key]}
 for(const node of nodes){
  const text=node.textContent||'';
  if(node.classList.contains('chip'))section('class','01 · 파일 분류').append(node);
  else if(node.classList.contains('typebar')){
   if(node.querySelector('.group-mode-buttons'))section('group','03 · 묶는 방식').append(node);
   else if(text.includes('남길 기준'))section('keep','04 · 남길 기준').append(node);
   else section('type','02 · 파일 종류와 검색 범위').append(node);
  }else if(node.classList.contains('filter-note'))section(text.includes('공통 단어')?'group':'keep',text.includes('공통 단어')?'03 · 묶는 방식':'04 · 남길 기준').append(node);
  else section('type','02 · 파일 종류와 검색 범위').append(node);
 }
}

async function resetFileSelection(){
 if(!await modal('선택과 검사 결과를 초기화할까요?','선택한 폴더·검사 결과·묶기 설정을 비우고 처음 화면으로 돌아갑니다. 실제 파일을 삭제하거나 이전 정리를 되돌리지는 않습니다.','초기화'))return;
 await work(async()=>{state=await api('reset');page=0;filter='같은 이름';picked.clear();issues.clear();checked.clear();rank=[];dir='';historyPaths=[];historyPosition=-1;across=false;category='전체';extension='';limit=80;say('초기화했습니다. 정리할 폴더를 다시 선택하세요.')});
}
