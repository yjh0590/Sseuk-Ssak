const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const compact = r => ({id:r.id,name:r.filename.split(/[\\/]/).pop(),path:r.filename,date:r.startTime,size:r.fileSize});
let active=false;
chrome.action.onClicked.addListener(()=>chrome.tabs.create({url:chrome.runtime.getURL('help.html')}));
async function preview(){
 await chrome.downloads.search({state:'complete',limit:0});
 await wait(10500);
 await chrome.downloads.search({state:'complete',limit:0});
 await wait(1800);
 return {items:(await chrome.downloads.search({state:'complete',limit:0})).map(compact)};
}
async function erase(msg){
 if(!Array.isArray(msg.ids)||msg.ids.length>100000||msg.ids.some(id=>!Number.isSafeInteger(id)))throw Error('선택한 목록을 다시 확인해 주세요.');
 const result={deleted:[],failed:[]};
 for(const id of new Set(msg.ids)){
  let record={id,name:String(id),path:'',date:'',size:null};
  try{
   const [item]=await chrome.downloads.search({id});
   if(!item)throw Error('기록이 이미 없어졌어요.');
   record=compact(item);
   if(item.state!=='complete')throw Error('완료되지 않은 기록이라 남겼어요.');
   const gone=await chrome.downloads.erase({id,state:'complete'});
   if(!gone.includes(id))throw Error('파일 상태가 바뀌었거나 기록을 지우지 못했어요.');
   result.deleted.push(record);
  }catch(e){result.failed.push({...record,reason:e.message})}
 }
 return result;
}
async function authorize(msg, sender) {
  const url = new URL(sender.url);
  if (sender.frameId !== 0 || url.protocol !== "http:" || url.hostname !== "127.0.0.1" ||
      !/^\/oddz-clean\/[a-f0-9]{48}$/.test(url.pathname) || url.search || url.hash ||
      !["preview","erase"].includes(msg?.task) || !Number.isSafeInteger(msg.expires) ||
      msg.expires - Date.now()/1000 > 1800 || msg.expires < Date.now()/1000 ||
      !/^[0-9a-f]{64}$/.test(msg.proof)) throw Error("앱에서 다시 실행해 주세요.");
  const res = await fetch(chrome.runtime.getURL("pair.json"), {cache:"no-store"});
  if (!res.ok) throw Error("앱의 ‘처음 연결’에서 도우미 폴더를 다시 확인해 주세요.");
  const bytes = hex => Uint8Array.from(hex.match(/../g), x => parseInt(x,16));
  const key = await crypto.subtle.importKey("raw",bytes(await res.json()), {name:"HMAC",hash:"SHA-256"},false,["verify"]);
  const valid = await crypto.subtle.verify("HMAC",key,bytes(msg.proof),new TextEncoder().encode(url.href+"|"+msg.expires));
  if(msg.task==='erase'){
    if(!Array.isArray(msg.ids)||msg.ids.some(id=>!Number.isSafeInteger(id))||!(/^[0-9a-f]{64}$/.test(msg.eraseProof||'')))throw Error('파일 이동 결과를 확인해 주세요.');
    const payload=[...msg.ids].sort((a,b)=>a-b).join(',');
    if(!await crypto.subtle.verify('HMAC',key,bytes(msg.eraseProof),new TextEncoder().encode(url.href+'|'+msg.expires+'|'+payload)))throw Error('휴지통 이동을 확인한 기록만 지울 수 있어요.');
  }
  if (!valid) throw Error("현재 앱 폴더의 chrome-helper를 다시 등록해 주세요.");
}
chrome.runtime.onMessageExternal.addListener((msg,sender,reply)=>{
 (async()=>{
  await authorize(msg,sender);
  if(active)throw Error('진행 중인 작업이 끝난 뒤 다시 시도하세요.');
  active=true;
  try{return msg.task==='preview'?await preview():await erase(msg)}finally{active=false}
 })().then(result=>reply({ok:true,...result}),e=>reply({ok:false,error:e.message}));
 return true;
});
