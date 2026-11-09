'use strict';
async function openFolderCompare(host=null){
 let data;if(busy||scanning)return;lock(true);try{data=await api('folder_find')}catch(e){say(e.message);return}finally{lock(false)}if(!data)return;
 let d=host||document.querySelector('#folderCompareDialog');if(!d){d=make('dialog');d.id='folderCompareDialog';document.body.append(d)}d.replaceChildren();
 d.append(make('h2','','비슷한 폴더 찾기'),make('p','','선택한 폴더의 바로 아래 폴더만 비교합니다. 이름의 v0.7.18, Update11 같은 버전·업데이트 번호와 끝의 (2) 같은 복사본 번호를 제외해 비슷한 폴더를 묶습니다. 이름이 비슷하다고 자동 삭제하지 않습니다.'));
 const content=make('div');d.append(content);
 const selected=new Map();
 function updateFolderActions(){
  const bar=$('#actionbar');bar.replaceChildren();if(!selected.size)return;
  bar.append(make('b','',selected.size+'개 폴더 선택'));
  btn(bar,'선택 해제',()=>{selected.clear();for(const box of content.querySelectorAll('[data-folder-choice]'))box.checked=false;updateFolderActions()});
  btn(bar,'선택한 폴더 삭제',async()=>{
   if(busy||scanning)return;lock(true);
   try{
    const preview=await api('folder_bulk_prepare',{ids:[...selected.keys()]});
    if(!confirm('선택한 폴더 '+preview.paths.length+'개를 휴지통으로 옮길까요?\n\n'+preview.paths.join('\n')+'\n\n하위 파일과 폴더도 모두 함께 이동합니다. 내용 비교를 하지 않은 항목도 포함될 수 있습니다. 선택하지 않은 폴더는 유지됩니다.'))return;
    const result=await api('folder_bulk_remove',{token:preview.token,confirmed:true});state=result.state;selected.clear();bar.replaceChildren();
    content.replaceChildren(make('p','','휴지통 이동 '+result.moved.length+'개 · 실패 '+result.failed.length+'개. 목록을 다시 찾아 주세요.'));
    for(const error of result.failed)content.append(make('p','smart-fail',error.path+' — '+error.message));say('폴더 정리가 완료되었습니다. 복원은 Windows 휴지통에서 할 수 있습니다.');
   }catch(e){say(e.message)}finally{lock(false)}
  },'primary');
 }

 if(!data.groups.length)content.append(make('p','','비슷한 이름의 폴더가 없습니다. 비교할 폴더들이 들어 있는 상위 폴더를 검사해 주세요.'));
 for(const g of data.groups){const card=make('section','smart-card');card.append(make('h3','',g.name));
 const controls=make('div','folder-list-controls');const sort=make('select');sort.setAttribute('aria-label',g.name+' 폴더 정렬');
 for(const [value,label] of [['name','이름순'],['date-desc','날짜순 · 최신순'],['date-asc','날짜순 · 오래된 순'],['size-desc','크기순 · 큰 순'],['size-asc','크기순 · 작은 순']]){const option=make('option','',label);option.value=value;sort.append(option)}controls.append(make('span','','이 묶음 정렬'),sort);card.append(controls);
 const entries=make('div','folder-entry-list');card.append(entries);
 function drawEntries(){
  const items=[...g.items].sort((a,b)=>{if(sort.value==='name')return a.name.localeCompare(b.name,'ko',{numeric:true});const key=sort.value.startsWith('date')?'modified':'size';if(a[key]===null)return b[key]===null?0:1;if(b[key]===null)return -1;return (a[key]-b[key])*(sort.value.endsWith('desc')?-1:1)||a.name.localeCompare(b.name,'ko',{numeric:true})});
  entries.replaceChildren();
  for(const item of items){const label=make('label','folder-select-row');const box=make('input');box.type='checkbox';box.dataset.folderChoice=item.id;box.checked=selected.has(item.id);box.disabled=!!item.measure_error;box.setAttribute('aria-label',item.name+' 폴더 선택');box.onchange=()=>{if(box.checked)selected.set(item.id,item.name);else selected.delete(item.id);updateFolderActions()};const text=make('span');text.append(make('b','',item.name),make('small','',item.path),make('small','',item.measure_error?'측정 불가 · '+item.measure_error:'수정 날짜 '+new Date(item.modified*1000).toLocaleString('ko-KR')+' · 하위 파일 합계 '+fmt(item.size)));label.append(box,text);entries.append(label)}
 }
 sort.onchange=drawEntries;drawEntries();
 const details=make('details','folder-compare-option');details.append(make('summary','','폴더 내용 비교 (선택 사항)'));card.append(details);
 const source=make('select'),reference=make('select');source.setAttribute('aria-label','정리할 후보 폴더');reference.setAttribute('aria-label','남길 기준 폴더');
 for(const item of g.items){for(const sel of [source,reference]){const o=make('option','',item.name);o.value=item.id;sel.append(o)}}reference.selectedIndex=g.items.length-1;
 const labelA=make('label','smart-field');labelA.append(make('span','','정리할 후보 폴더'),source);const labelB=make('label','smart-field');labelB.append(make('span','','남길 기준 폴더 (직접 확인해 선택)'),reference);details.append(labelA,labelB);
 const result=make('div');const compareButton=btn(details,'내용 비교',async()=>{
 compareButton.disabled=true;result.replaceChildren();try{const r=await api('folder_compare',{source:source.value,reference:reference.value});
 result.append(make('p','','후보: '+r.source),make('p','','기준: '+r.reference),make('p','','동일 내용 '+r.same+'개 · 후보에만 '+r.only_source.length+'개 · 기준에만 '+r.only_reference.length+'개 · 내용 다름 '+r.different.length+'개'));
 const show=(title,items)=>{if(!items.length)return;const details=make('details');details.append(make('summary','',title+' ('+items.length+')'));const list=make('pre','folder-differences',items.join('\n'));details.append(list);result.append(details)};
 show('후보에만 있는 파일',r.only_source);show('기준에만 있는 파일',r.only_reference);show('같은 경로지만 내용이 다른 파일',r.different);show('후보에만 있는 폴더',r.only_source_dirs);
 result.append(make('p','',r.subset?'후보의 모든 파일·폴더가 기준에 있으며 파일 내용도 같습니다. 이동할 폴더를 다시 확인하세요.':'주의: 후보에만 있는 파일/폴더 또는 내용 차이가 있습니다. 휴지통 이동 시 해당 데이터도 함께 이동합니다.'));
 let ack=null;if(!r.subset){const label=make('label','folder-ack');ack=make('input');ack.type='checkbox';label.append(ack,document.createTextNode('차이를 확인했으며 후보 폴더 전체를 휴지통으로 옮기겠습니다.'));result.append(label)}
 const move=btn(result,'후보 폴더를 휴지통으로 이동',async()=>{if(ack&&!ack.checked){alert('먼저 폴더 차이와 확인 항목을 확인해 주세요.');return}if(!confirm('후보 폴더 전체를 휴지통으로 옮길까요?\n'+r.source+'\n\n기준 폴더는 유지됩니다.'))return;move.disabled=true;try{const v=await api('folder_remove',{token:r.token,confirmed:true,allow_unique:!!ack?.checked});state=v.state;picked.clear();issues.clear();say(v.message);if(!host)d.close();render()}catch(e){result.append(make('p','smart-fail',e.message));move.disabled=false}},'primary');
 }catch(e){result.append(make('p','smart-fail',e.message))}finally{compareButton.disabled=false}
 },'outline-control');source.onchange=reference.onchange=()=>result.replaceChildren();details.append(result);content.append(card)}
 for(const error of data.errors)content.append(make('p','smart-fail',error.path+' — '+error.message));if(!host){btn(d,'닫기',()=>d.close());d.showModal()}
}

function renderFolderPage(){
 $('#hero').replaceChildren();const hero=make('div','hero-copy');hero.append(make('h2','','정리할 폴더들이 들어 있는 위치를 선택하세요'),make('p','',state.root||'선택한 위치의 바로 아래 폴더들을 이름과 버전으로 묶어 비교합니다.'));
 btn(hero,state.root?'다른 위치 선택':'폴더 위치 선택',()=>scan(true),'primary');$('#hero').append(hero);
 $('#section').textContent='폴더 선택 및 정리';$('#tools').replaceChildren();$('#filters').replaceChildren();$('#actionbar').replaceChildren();const list=$('#list');list.replaceChildren();
 const intro=make('section','filter-panel');intro.append(make('h3','filter-panel-title','폴더 찾기 → 체크박스로 선택 → 선택한 폴더 삭제'),make('p','','삭제는 영구 삭제가 아닌 휴지통 이동입니다. 필요한 경우 목록 아래의 내용 비교를 먼저 이용하세요.\n\n각 묶음에서 날짜순·크기순을 선택할 수 있습니다. 날짜는 폴더 자체의 수정 날짜이며, 크기는 하위 파일의 합계입니다.'));list.append(intro);
 const host=make('div','folder-page-results');list.append(host);
 if(state.root)btn(intro,'비슷한 폴더 찾기',()=>openFolderCompare(host),'primary');else host.append(make('p','blank','위에서 폴더들이 들어 있는 위치를 먼저 선택해 주세요.'));
}
