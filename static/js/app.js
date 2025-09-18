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
    const editMode = videoForm.dataset.editMode === '1';
    const updateRemoveState = ()=>{
      const items = itemsWrap.querySelectorAll('[data-video-item]');
      items.forEach((item, idx)=>{
        const removeBtn = item.querySelector('[data-video-remove]');
        const fileInput = item.querySelector('input[type="file"]');
        if(removeBtn){
          removeBtn.style.display = !editMode && items.length <= 1 ? 'none' : '';
        }
        if(fileInput){
          fileInput.required = !editMode && idx === 0;
        }
      });
    };
    const bindRemove = node => {
      const btn = node.querySelector('[data-video-remove]');
      if(btn){
        btn.addEventListener('click', ()=>{
          const siblings = itemsWrap.querySelectorAll('[data-video-item]');
          if(!editMode && siblings.length <= 1) return;
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
    if(!itemsWrap.querySelector('[data-video-item]') && !editMode){
      addItem();
    }
  }

  document.querySelectorAll('[data-player]').forEach(player=>{
    const video = player.querySelector('[data-video]') || player.querySelector('video');
    const qualitySelect = player.querySelector('[data-quality-select]');
    const downloadLink = player.querySelector('[data-download-target]');
    const sourceEl = video ? video.querySelector('source') : null;
    if(!video) return;
    const container = player.closest('.course-main');
    const lessonButtons = container ? Array.from(container.querySelectorAll('[data-lesson-rail] .lesson-card')) : [];
    const setSource = (src)=>{
      if(sourceEl){
        sourceEl.src = src;
      }
      video.src = src;
      video.load();
    };
    const loadSources = (sources)=>{
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
      if(downloadLink){
        downloadLink.href = sources[0].download || downloadLink.href;
      }
      setSource(sources[0].src);
    };
    lessonButtons.forEach(btn=>{
      btn.addEventListener('click', ()=>{
        lessonButtons.forEach(el=> el.classList.remove('active'));
        btn.classList.add('active');
        const sources = JSON.parse(btn.dataset.sources || '[]');
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
    if(lessonButtons.length){
      const initialSources = JSON.parse(lessonButtons[0].dataset.sources || '[]');
      loadSources(initialSources);
    }
    video.addEventListener('dblclick', evt=>{
      const rect = video.getBoundingClientRect();
      const midpoint = rect.width / 2;
      const offset = evt.clientX - rect.left;
      const delta = offset > midpoint ? 10 : -10;
      try{
        video.currentTime = Math.max(0, video.currentTime + delta);
      }catch(e){}
    });
  });

  document.querySelectorAll('[data-accordion-group]').forEach(group=>{
    group.querySelectorAll('.accordion-toggle').forEach(toggle=>{
      toggle.addEventListener('click', ()=>{
        const item = toggle.closest('.accordion-item');
        if(!item) return;
        const isOpen = item.classList.contains('open');
        if(isOpen){
          item.classList.remove('open');
        }else{
          item.classList.add('open');
        }
      });
    });
  });
})();
