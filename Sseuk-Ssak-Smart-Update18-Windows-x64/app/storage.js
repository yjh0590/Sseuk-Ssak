'use strict';
// action: {label,onClick} — 첫 카드 머리글 오른쪽에 넣는 버튼 (예: 용량 다시 측정)
function renderStorage(container,data,mode="all",action=null){
 container.replaceChildren();if(!data?.before?.length)return;
 const make=(tag,text,cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e};
 const fmt=n=>{let i=0;while(Math.abs(n)>=1024&&i<4){n/=1024;i++}return n.toLocaleString('ko-KR',{maximumFractionDigits:1})+' '+['B','KB','MB','GB','TB'][i]};
 const NS='http://www.w3.org/2000/svg';
 const svgEl=(tag,attrs)=>{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e};
 // 도넛 조각과 범례 줄을 같은 키로 묶어 서로 강조한다.
 const link=(card,key,on)=>{for(const e of card.querySelectorAll(`[data-part="${key}"]`))e.classList.toggle('is-hot',on)};
 if(mode!=='types'){
 container.append(make('h2',data.after?.length?'정리 전후 용량':'드라이브 용량'),make('p','회색은 실제 빈 공간, 보라색은 Windows가 보고한 휴지통 용량이에요. 휴지통으로 이동해도 빈 공간은 바로 늘지 않아요.'));
 for(const before of data.before){
  const after=data.after?.find(x=>x.volume===before.volume);
  const section=make('section','');section.append(make('h3',before.volume));const pair=make('div','','storage-pair');
  for(const [title,v] of (after?[['정리 전',before],['정리 후',after]]:[['현재 용량',before]])){
   const card=make('div','','storage-card');const head=make('div','','storage-card-head');head.append(make('h3',title));card.append(head);
   if(action&&!container.querySelector('.storage-action')){const b=make('button',action.label,'outline-control storage-action');b.type='button';b.onclick=action.onClick;head.append(b)}
   if(v.error){card.append(make('p',v.error));pair.append(card);continue}
   const recycled=Math.min(v.used,Math.max(0,v.recycle||0));const used=Math.max(0,v.used-recycled);
   const recycleText=v.recycle===null?'측정 불가 · 사용 중에 포함':fmt(v.recycle);
   const parts=[['used','사용 중',used,'#C93645',fmt(used)],['recycle','휴지통',recycled,'#8B6BC1',recycleText],['free','빈 공간',Math.max(0,v.total-used-recycled),'#DCE0E5',fmt(v.free)]];
   const body=make('div','','storage-body');
   const chart=make('div','','storage-donut');
   const svg=svgEl('svg',{viewBox:'0 0 120 120',class:'storage-ring',role:'img','aria-label':title+': 사용 중 '+fmt(used)+', 휴지통 '+(v.recycle===null?'측정 불가':fmt(v.recycle))+', 빈 공간 '+fmt(v.free)});
   const ring=svgEl('g',{transform:'rotate(-90 60 60)'});let start=0;
   for(const [key,label,value,color,text] of parts){
    const pct=v.total?value/v.total*100:0;if(pct<=0)continue;
    const seg=svgEl('circle',{cx:60,cy:60,r:47,fill:'none',stroke:color,'stroke-width':16,pathLength:100,'stroke-dasharray':`${pct} ${100-pct}`,'stroke-dashoffset':-start,class:'storage-seg','data-part':key});
    const tip=svgEl('title',{});tip.textContent=`${label} ${text} (${pct.toLocaleString('ko-KR',{maximumFractionDigits:1})}%)`;seg.append(tip);
    seg.addEventListener('mouseenter',()=>link(card,key,true));seg.addEventListener('mouseleave',()=>link(card,key,false));
    ring.append(seg);start+=pct;
   }
   svg.append(ring);chart.append(svg);
   const hole=make('div','','storage-hole');hole.append(make('small','빈 공간'),make('strong',fmt(v.free)));chart.append(hole);
   const legend=make('div','','storage-legend');
   const total=make('p','');const totalSwatch=make('span','','storage-swatch');totalSwatch.style.background='#247C86';totalSwatch.setAttribute('aria-hidden','true');total.append(totalSwatch,document.createTextNode('전체 용량 '+fmt(v.total)));total.classList.add('storage-total');total.style.color='#247C86';total.style.fontWeight='700';legend.append(total);
   for(const [key,label,,color,text] of parts){const line=make('p','');line.dataset.part=key;const swatch=make('span','','storage-swatch');swatch.style.background=color;swatch.setAttribute('aria-hidden','true');line.append(swatch,document.createTextNode(label+' '+text));line.addEventListener('mouseenter',()=>link(card,key,true));line.addEventListener('mouseleave',()=>link(card,key,false));legend.append(line)}
   if(v.recycle>0&&v.total&&v.recycle/v.total<0.005)legend.append(make('p','휴지통 비율이 0.5% 미만이라 원형 그래프에서 보라색이 거의 보이지 않을 수 있어요. 보라색 범례의 수치를 확인하세요.','storage-tiny-note'));
   body.append(chart,legend);card.append(body);
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
