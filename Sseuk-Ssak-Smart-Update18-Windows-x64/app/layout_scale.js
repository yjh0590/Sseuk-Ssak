
(()=>{
 const REFERENCE_WIDTH=1440;
 function resizeLayout(){
  const width=document.documentElement.clientWidth;
  const scale=Math.min(1,width/REFERENCE_WIDTH);
  document.documentElement.classList.add('proportional-layout');
  document.documentElement.style.setProperty('--app-scale',String(scale));
  document.documentElement.style.setProperty('--layout-width',Math.max(REFERENCE_WIDTH,width/scale)+'px');
  document.documentElement.style.setProperty('--layout-height',(window.innerHeight/scale)+'px');
 }
 window.addEventListener('resize',resizeLayout);resizeLayout();
})();
