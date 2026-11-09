'use strict';
let smartState={root:'',current:'.',items:[],favorites:[],demo:false},smartReport=[],smartResult=null;
const smartDraft={};
function smartRemember(){for(const e of document.querySelectorAll('[data-smart]'))smartDraft[e.dataset.smart]=e.value}
function smartField(parent,label,key,value='',options=null){
 const box=make('label','smart-field');box.append(make('span','',label));
 const input=make(options?'select':'input');input.dataset.smart=key;
 if(options)for(const [v,t] of options){const o=make('option','',t);o.value=v;input.append(o)}
 const examples={folderName:'예: 업무',number:'예: 2 (01~98)',when:'예: 2026_11 또는 2026-4Q',fileName:'예: 웹사이트_기획안.txt',category:'예: 회의록, 기획안, 양식',date:'예: 2026_11_04',text:'문서 내용을 입력하세요',source:'예: 02_업무/기획안_v1.0.txt',target:'예: 02_업무/웹사이트_기획안_v1.0.txt'};
 if(!options){input.placeholder=examples[key]||value;input.value=Object.hasOwn(smartDraft,key)?smartDraft[key]:'';}else input.value=Object.hasOwn(smartDraft,key)?smartDraft[key]:value;
 input.oninput=()=>smartDraft[key]=input.value;box.append(input);parent.append(box);return input
}
function smartData(key){return smartDraft[key]||''}
async function smartRun(op,extra={}){
 smartRemember();
 await work(async()=>{
  const data=await api('smart',{op,...extra});smartState=data;
  if(data.result)smartResult=data.result;
  if(data.report)smartReport=data.report;
  say(data.result?data.result['안내 메시지']:'목록을 갱신했어요.');
 });
}
async function smartChoose(){smartRemember();await work(async()=>{const data=await api('smart_pick');if(!data.cancel){smartState=data;smartReport=[];smartResult=null;say('관리 폴더를 선택했어요. 기존 파일은 변경하지 않았습니다.')}})}
async function smartMutation(op,extra){
 smartRemember();
 if(['move','rename','archive','revise'].includes(op)){
  if(!await modal('선택한 항목을 변경할까요?',(extra.source||'')+'\n기존 파일의 경로 또는 새 버전 파일이 변경됩니다.','적용하기'))return;
 }
 return smartRun(op,extra);
}
function renderSmart(){
 $('#hero').replaceChildren();const h=make('div','hero-copy');
 h.append(make('h2','',smartState.demo?'가상 테스트 작업 공간':smartState.root?'관리 폴더가 선택되었어요':'안전하게 정리 기준을 적용해요'),make('p','',smartState.root||'먼저 가상 테스트로 규칙을 확인하거나 관리할 폴더를 선택하세요.'));
 btn(h,'관리 폴더 선택',smartChoose,'primary');btn(h,'가상 테스트 실행',()=>smartRun('demo'));$('#hero').append(h);
 $('#section').textContent='파일/폴더 정리 작업';$('#tools').replaceChildren();$('#filters').replaceChildren();$('#list').replaceChildren();$('#actionbar').replaceChildren();
 const panel=$('#list');
 const note=make('p','smart-note','기준 폴더는 깊이 0입니다. 최대 5단계 · 99_아카이브 전용 · 금지어 차단 · 즐겨찾기 5개. 기존 파일은 명령을 적용할 때만 변경하며, 기존 ‘파일 정리’ 메뉴에는 영향을 주지 않습니다.');panel.append(note);
 if(smartResult){const result=make('section','smart-result');for(const key of ['실행 결과','적용된 경로/파일명','안내 메시지'])result.append(make('p','',key+': '+smartResult[key]));panel.append(result)}
 if(smartReport.length){const box=make('section','smart-report');box.append(make('h3','','가상 테스트 결과'));
 for(const r of smartReport)box.append(make('p',r.passed?'smart-pass':'smart-fail',(r.passed?'통과 · ':'실패 · ')+r.test+' — '+r.message));panel.append(box)}
 if(!smartState.root){panel.append(make('p','blank','가상 테스트는 별도 임시 폴더에 샘플 파일을 생성합니다. 실제 문서는 건드리지 않습니다.'));return}
 const fav=make('section','smart-card');fav.append(make('h3','',`즐겨찾기 (${smartState.favorites.length}/5)`),make('p','smart-note','이 앱 내부 즐겨찾기입니다. Windows 퀵 액세스와는 별개입니다.'));
 for(const path of smartState.favorites){const row=make('div','smart-line');row.append(make('span','',path));btn(row,'제거',()=>smartRun('favorite',{action:'remove',target:path}));fav.append(row)}
 btn(fav,'현재 폴더 즐겨찾기',()=>smartRun('favorite',{action:'add',target:smartState.current}));panel.append(fav);
 const browser=make('section','smart-card');browser.append(make('h3','','현재 위치: '+smartState.current),make('p','sort-caption','정렬: 폴더 우선 · 이름순'));
 const nav=make('div','smart-line');btn(nav,'처음 폴더',()=>smartRun('list',{folder:'.'}));btn(nav,'상위 폴더',()=>{const a=smartState.current.split(/[\\/]/);a.pop();smartRun('list',{folder:a.join('/')||'.'})});btn(nav,'새로고침',()=>smartRun('list'));browser.append(nav);
 if(!smartState.items.length)browser.append(make('p','smart-note','비어 있는 폴더입니다.'));
 for(const item of smartState.items){const row=make('div','smart-file');const text=make('div','text');text.append(make('b','',(item.folder?'폴더 · ':'파일 · ')+item.name),make('small','',item.path));row.append(text);
  if(item.link){row.append(make('span','','링크: 작업 제외'))}
  else{if(item.folder)btn(row,'열기',()=>smartRun('list',{folder:item.path}));btn(row,'선택',()=>{smartRemember();smartDraft.source=item.path;smartDraft.target=item.path;say('아래 이동/이름 변경 양식에 선택한 경로를 넣었어요.');render()});btn(row,'즐겨찾기',()=>smartRun('favorite',{action:'add',target:item.path}));}browser.append(row)
 }panel.append(browser);
 const forms=make('div','smart-grid');
 const folder=make('section','smart-card');folder.append(make('h3','','폴더 만들기'));
 smartField(folder,'폴더 이름','folderName','새폴더');smartField(folder,'종류','kind','general',[['general','일반 폴더'],['media','사진/영상'],['project','단기 프로젝트'],['archive','아카이브']]);
 smartField(folder,'일반 폴더 번호 (1~98)','number','1');smartField(folder,'시간 접두사 (미입력 시 현재 날짜)','when','');
 folder.append(make('p','smart-note','미디어: 2026 또는 2026_11 / 프로젝트: 2026-4Q'));
 btn(folder,'폴더 생성',()=>{smartRemember();smartRun('mkdir',{name:smartData('folderName'),kind:smartData('kind'),number:smartData('number'),when:smartData('when')})},'primary');forms.append(folder);
 const file=make('section','smart-card');file.append(make('h3','','새 텍스트 문서 만들기'));
 smartField(file,'파일명 (.txt/.md/.csv)','fileName','기획안.txt');smartField(file,'분류 키워드 (선택)','category','');smartField(file,'서류 날짜 YYYY_MM_DD','date','');smartField(file,'새 문서/수정본 내용','text','가상 문서 내용');
 file.append(make('p','smart-note','문서는 검색용 키워드가 필요하며 정산·증빙·계약은 실제 날짜를 지정하세요.'));
 btn(file,'문서 생성',()=>{smartRemember();smartRun('create',{name:smartData('fileName'),category:smartData('category'),date:smartData('date'),text:smartData('text')})},'primary');forms.append(file);
 const move=make('section','smart-card');move.append(make('h3','','이동 · 이름 변경 · 보관'));
 smartField(move,'원본 경로 (기준 폴더 기준)','source','');smartField(move,'대상 전체 경로 (기준 폴더 기준)','target','');
 move.append(make('p','smart-note','목록의 선택 버튼으로 원본을 지정하세요. 대상 폴더는 먼저 생성해야 합니다. 날짜와 분류는 위 문서 양식의 값을 사용합니다.'));
 btn(move,'이동/이름 변경',()=>{smartRemember();smartMutation('move',{source:smartData('source'),target:smartData('target'),category:smartData('category'),date:smartData('date')})},'primary');
 btn(move,'보관',()=>{smartRemember();smartMutation('archive',{source:smartData('source')})});
 btn(move,'수정본 저장',()=>{smartRemember();smartMutation('revise',{source:smartData('source'),text:smartData('text')})});forms.append(move);for(const card of forms.children){const actions=make('div','smart-actions');actions.append(...card.querySelectorAll(':scope>button'));card.append(actions)}panel.append(forms);
}
