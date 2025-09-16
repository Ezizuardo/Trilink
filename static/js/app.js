(function(){
  function setTheme(checked){
    const theme = checked ? 'dark':'light';
    document.documentElement.setAttribute('data-theme', theme);
    fetch('/set-theme/'+theme).catch(()=>{});
    try{ localStorage.setItem('trilink-theme', theme);}catch(e){}
  }
  const t2=document.getElementById('themeToggleMenu');
  if(t2){ t2.addEventListener('change', e=>{ setTheme(t2.checked); }); }
  try{
    const saved = localStorage.getItem('trilink-theme');
    if(saved){
      document.documentElement.setAttribute('data-theme', saved);
      if(t2) t2.checked=(saved==='dark');
    }
  }catch(e){}

  const menu = document.querySelector('.avatar-menu');
  if(menu){
    const btn = menu.querySelector('.avatar-button');
    const drop = menu.querySelector('.dropdown');
    const close = ()=> menu.classList.remove('open');
    if(btn){
      btn.addEventListener('click', evt=>{
        evt.preventDefault();
        evt.stopPropagation();
        menu.classList.toggle('open');
      });
    }
    if(drop){
      drop.addEventListener('click', evt=>{
        if(evt.target.closest('a')) close();
      });
    }
    document.addEventListener('click', evt=>{
      if(!menu.contains(evt.target)) close();
    });
  }
})();