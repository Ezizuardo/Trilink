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

  const videoForm = document.querySelector('[data-video-list]');
  if(videoForm){
    const itemsWrap = videoForm.querySelector('.video-items');
    const tpl = document.getElementById('videoItemTemplate');
    const addBtn = videoForm.querySelector('[data-video-add]');
    const updateRemoveState = ()=>{
      const items = itemsWrap.querySelectorAll('[data-video-item]');
      items.forEach((item, idx)=>{
        const removeBtn = item.querySelector('[data-video-remove]');
        const fileInput = item.querySelector('input[type="file"]');
        if(removeBtn){
          removeBtn.style.display = items.length <= 1 ? 'none' : '';
        }
        if(fileInput){
          fileInput.required = idx === 0;
        }
      });
    };
    const bindRemove = (node)=>{
      const btn = node.querySelector('[data-video-remove]');
      if(btn){
        btn.addEventListener('click', ()=>{
          const siblings = itemsWrap.querySelectorAll('[data-video-item]');
          if(siblings.length <= 1) return;
          node.remove();
          updateRemoveState();
        });
      }
    };
    const addItem = ()=>{
      if(!tpl) return;
      const clone = tpl.content.firstElementChild.cloneNode(true);
      itemsWrap.appendChild(clone);
      bindRemove(clone);
      updateRemoveState();
    };
    itemsWrap.querySelectorAll('[data-video-item]').forEach(item=> bindRemove(item));
    updateRemoveState();
    if(addBtn){
      addBtn.addEventListener('click', ()=>{
        addItem();
      });
    }
    if(!itemsWrap.querySelector('[data-video-item]')){
      addItem();
    }
  }

  document.querySelectorAll('[data-preview-hover]').forEach(box=>{
    const video = box.querySelector('video');
    if(!video) return;
    let timer;
    box.addEventListener('mouseenter', ()=>{
      clearTimeout(timer);
      video.currentTime = 0;
      video.play().catch(()=>{});
    });
    box.addEventListener('mouseleave', ()=>{
      timer = setTimeout(()=>{
        video.pause();
        try{ video.currentTime = 0; }catch(e){}
      }, 80);
    });
  });

  document.querySelectorAll('[data-course-player]').forEach(player=>{
    const video = player.querySelector('[data-video]') || player.querySelector('video');
    const qualitySelect = player.querySelector('[data-quality-select]');
    const playlist = Array.from(player.querySelectorAll('[data-playlist] .playlist-item'));
    if(!video || !playlist.length) return;
    const sourceEl = video.querySelector('source');
    const setSource = src => {
      if(sourceEl){
        sourceEl.src = src;
      }
      video.src = src;
      video.load();
    };
    const loadSources = sources => {
      if(!sources || !sources.length) return;
      if(qualitySelect){
        qualitySelect.innerHTML = '';
        sources.forEach((s, idx)=>{
          const opt = document.createElement('option');
          opt.value = s.src;
          opt.textContent = s.quality;
          if(idx===0) opt.selected = true;
          qualitySelect.appendChild(opt);
        });
      }
      setSource(sources[0].src);
    };
    playlist.forEach(item=>{
      item.addEventListener('click', ()=>{
        playlist.forEach(p=>p.classList.remove('active'));
        item.classList.add('active');
        const sources = JSON.parse(item.dataset.sources || '[]');
        const poster = item.dataset.poster;
        if(poster){ video.setAttribute('poster', poster); }
        loadSources(sources);
      });
    });
    if(qualitySelect){
      qualitySelect.addEventListener('change', evt=>{
        const src = evt.target.value;
        setSource(src);
        video.play().catch(()=>{});
      });
    }
    const initialSources = JSON.parse(playlist[0].dataset.sources || '[]');
    loadSources(initialSources);
  });
})();