'use strict';
function renderStorage(container,data,mode="all"){
 container.replaceChildren();if(!data?.before?.length)return;
 const make=(tag,text,cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e};
 const fmt=n=>{let i=0;while(Math.abs(n)>=1024&&i<4){n/=1024;i++}return n.toLocaleString('ko-KR',{maximumFractionDigits:1})+' '+['B','KB','MB','GB','TB'][i]};
 if(mode!=='types'){
 container.append(make('h2',data.after?.length?'정리 전후 용량':'드라이브 용량'),make('p','회색은 실제 빈 공간, 보라색은 Windows가 보고한 휴지통 용량이에요. 휴지통으로 이동해도 빈 공간은 바로 늘지 않아요.'));
 for(const before of data.before){
  const after=data.after?.find(x=>x.volume===before.volume);
  const section=make('section','');section.append(make('h3',before.volume));const pair=make('div','','storage-pair');
  for(const [title,v] of (after?[['정리 전',before],['정리 후',after]]:[['현재 용량',before]])){
   const card=make('div','','storage-card');card.append(make('h3',title));
   if(v.error){card.append(make('p',v.error));pair.append(card);continue}
   const recycled=Math.min(v.used,Math.max(0,v.recycle||0));const used=Math.max(0,v.used-recycled),end=v.total?(used+recycled)/v.total*100:0,first=v.total?used/v.total*100:0;
   const chart=make('div','','storage-donut');chart.style.background=`conic-gradient(#C93645 0% ${Number(first.toFixed(6))}%,#8B6BC1 ${Number(first.toFixed(6))}% ${Number(end.toFixed(6))}%,#DCE0E5 ${Number(end.toFixed(6))}% 100%)`;
   chart.setAttribute('role','img');chart.setAttribute('aria-label',title+': 사용 중 '+fmt(used)+', 휴지통 '+(v.recycle===null?'측정 불가':fmt(v.recycle))+', 빈 공간 '+fmt(v.free));
   const hole=make('div','','storage-hole');hole.append(make('small','빈 공간'),make('strong',fmt(v.free)));chart.append(hole);card.append(chart);
   const legend=make('div','','storage-legend');
   for(const [label,color] of [['전체 용량 '+fmt(v.total),'#247C86'],['사용 중 '+fmt(used),'#C93645'],['휴지통 '+(v.recycle===null?'측정 불가 · 사용 중에 포함':fmt(v.recycle)),'#8B6BC1'],['빈 공간 '+fmt(v.free),'#DCE0E5']]){const line=make('p','');const swatch=make('span','','storage-swatch');swatch.style.background=color;swatch.setAttribute('aria-hidden','true');line.append(swatch,document.createTextNode(label));if(label.startsWith('전체 용량')){line.classList.add('storage-total');line.style.color='#247C86';line.style.fontWeight='700'}legend.append(line)}
   card.append(legend);
   if(v.recycle>0&&v.total&&v.recycle/v.total<0.005)card.append(make('p','휴지통 비율이 0.5% 미만이라 원형 그래프에서 보라색이 거의 보이지 않을 수 있어요. 보라색 범례의 수치를 확인하세요.','storage-tiny-note'));
   pair.append(card);
  }
  section.append(pair);
  if(after&&!before.error&&!after.error){const delta=after.free-before.free;section.append(make('p','실제 빈 공간 변화 '+(delta>=0?'+':'−')+fmt(Math.abs(delta))+' · 다른 앱의 디스크 사용도 반영될 수 있어요.'))}
  container.append(section);
 }
 }
 if(mode==='graphs')return;
 const colors=['#C93645','#329AB8','#5870CB','#4C9678','#C28B36','#747F8A'];const types=make('div','','storage-types');
 Object.entries(data.moved||{}).forEach(([name,size],i)=>{const card=make('div','','storage-type');card.style.borderLeft='4px solid '+colors[i%colors.length];card.append(make('b',name),make('span',fmt(size)+' 이동'));types.append(card)});
 if(Object.keys(data.moved||{}).length)container.append(make('h3','휴지통으로 이동한 파일'),types,make('p','종류별 수치는 이동에 성공한 파일의 논리 용량이며, 드라이브에서 실제 확보한 공간과는 달라요. 휴지통 측정에 실패하면 사용 중에 포함해 표시해요.'));
}
