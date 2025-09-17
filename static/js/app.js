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

  function setupPreview(container){
    if(!container || container.dataset.previewReady) return container?container._previewController:null;
    const video = container.querySelector('video');
    let source = container.dataset.previewSrc || (video ? (video.dataset.previewFragment || video.getAttribute('data-preview-fragment') || '') : '');
    if(!video || !source) return null;
    let timer = null;
    let markers = [];
    const resetMarkers = ()=>{
      const duration = video.duration;
      if(duration && isFinite(duration)){
        markers = [0.05,0.3,0.55,0.8].map(p=>{
          const t = duration * p;
          const maxT = Math.max(duration - 0.3, 0.2);
          return Math.min(Math.max(t, 0.2), maxT);
        });
      }
    };
    const start = ()=>{
      if(!source) return;
      video.muted = true;
      video.playsInline = true;
      const go = ()=>{
        resetMarkers();
        try{ video.play(); }catch(e){}
        if(!timer && markers.length){
          let idx = 0;
          timer = setInterval(()=>{
            if(!video.duration || !markers.length) return;
            idx = (idx + 1) % markers.length;
            video.currentTime = markers[idx];
          }, 1400);
        }
        container.classList.add('preview-active');
      };
      if(video.src !== source){
        video.src = source;
      }
      video.currentTime = 0;
      if(video.readyState >= 1){
        go();
      }else{
        video.addEventListener('loadedmetadata', go, {once:true});
        video.load();
      }
    };
    const stop = ()=>{
      if(timer){ clearInterval(timer); timer = null; }
      video.pause();
      video.currentTime = 0;
      container.classList.remove('preview-active');
    };
    const controller = {
      start,
      stop,
      setSource(newSrc){
        if(!newSrc || newSrc === source) return;
        stop();
        source = newSrc;
        container.dataset.previewSrc = newSrc;
        video.src = newSrc;
        video.load();
      }
    };
    container.addEventListener('mouseenter', start);
    container.addEventListener('mouseleave', stop);
    container.addEventListener('touchstart', start, {passive:true});
    container.addEventListener('touchend', stop);
    container.dataset.previewReady = '1';
    container._previewController = controller;
    return controller;
  }

  function initCourseForm(){
    const wrapper = document.querySelector('.course-form-wrapper');
    if(!wrapper) return;
    const previewBlock = wrapper.querySelector('[data-preview]');
    const previewImage = previewBlock ? previewBlock.querySelector('.preview-image') : null;
    const previewInput = wrapper.querySelector('[data-preview-input]');
    let tempUrl = null;
    if(previewInput && previewImage){
      previewInput.addEventListener('change', ()=>{
        const file = previewInput.files && previewInput.files[0];
        if(!file) return;
        if(tempUrl) URL.revokeObjectURL(tempUrl);
        tempUrl = URL.createObjectURL(file);
        previewImage.style.backgroundImage = `url('${tempUrl}')`;
      });
      window.addEventListener('beforeunload', ()=>{ if(tempUrl) URL.revokeObjectURL(tempUrl); });
    }
    const editor = wrapper.querySelector('[data-playlist]');
    if(!editor) return;
    const itemsWrap = editor.querySelector('[data-playlist-items]') || editor;
    const orderField = editor.querySelector('#videoOrder');
    const updateOrder = ()=>{
      if(!orderField) return;
      const ids = Array.from(editor.querySelectorAll('.playlist-row[data-video-id]')).map(el=>el.dataset.videoId);
      orderField.value = ids.join(',');
    };
    updateOrder();
    editor.querySelectorAll('[data-move]').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const row = btn.closest('.playlist-row');
        if(!row) return;
        const dir = btn.dataset.move;
        if(dir==='up' && row.previousElementSibling){
          row.parentNode.insertBefore(row, row.previousElementSibling);
        }else if(dir==='down' && row.nextElementSibling){
          row.parentNode.insertBefore(row.nextElementSibling, row);
        }
        updateOrder();
      });
    });
    const observer = new MutationObserver(updateOrder);
    observer.observe(itemsWrap, {childList:true});
  }

  function initCoursePlayer(){
    const shell = document.querySelector('[data-player]');
    if(!shell) return;
    const playerVideo = shell.querySelector('.player-video');
    const previewContainer = shell.querySelector('[data-player-preview]');
    const startButton = shell.querySelector('[data-start-preview]');
    const previewController = previewContainer ? setupPreview(previewContainer) : null;
    if(playerVideo){
      playerVideo.querySelectorAll('source').forEach(src=>src.remove());
      const first = shell.dataset.previewSrc;
      if(first){
        playerVideo.src = first;
        playerVideo.dataset.currentSrc = first;
        playerVideo.load();
        playerVideo.pause();
      }
      if(previewContainer){
        playerVideo.classList.add('hidden');
      }
    }
    if(startButton && previewController){
      startButton.addEventListener('click', ()=>{
        previewController.start();
        startButton.style.display='none';
      });
    }else if(startButton && !previewController){
      startButton.style.display='none';
    }
    const playlist = document.querySelector('[data-course-playlist]');
    if(playlist){
      playlist.querySelectorAll('.playlist-thumb').forEach(setupPreview);
    }
    const changeVideo = (src, index)=>{
      if(!playerVideo || !src) return;
      const items = playlist ? playlist.querySelectorAll('.playlist-item') : [];
      items.forEach(item=>{
        item.classList.toggle('active', item.dataset.index === String(index));
      });
      if(playerVideo.dataset.currentSrc !== src){
        playerVideo.pause();
        playerVideo.src = src;
        playerVideo.load();
        playerVideo.dataset.currentSrc = src;
      }
      playerVideo.classList.remove('hidden');
      playerVideo.play().catch(()=>{});
      if(previewContainer){
        previewContainer.classList.add('hidden');
      }
      if(previewController){
        previewController.setSource(src);
        previewController.stop();
      }
    };
    if(playlist){
      playlist.addEventListener('click', evt=>{
        const item = evt.target.closest('.playlist-item');
        if(!item) return;
        evt.preventDefault();
        changeVideo(item.dataset.videoSrc, item.dataset.index);
      });
    }
    if(playerVideo){
      const qualitySelect = shell.querySelector('[data-quality-select]');
      const applyQuality = value=>{
        ['quality-1080','quality-720','quality-480'].forEach(cls=>playerVideo.classList.remove(cls));
        playerVideo.classList.add('quality-'+value);
        playerVideo.dataset.qualityState = value;
      };
      if(qualitySelect){
        qualitySelect.addEventListener('change', ()=>applyQuality(qualitySelect.value));
        applyQuality(qualitySelect.value);
      }
      playerVideo.addEventListener('play', ()=>{
        if(previewContainer){
          previewContainer.classList.add('hidden');
        }
        if(previewController){
          previewController.stop();
        }
      });
      playerVideo.addEventListener('ended', ()=>{
        if(previewContainer){
          previewContainer.classList.remove('hidden');
        }
      });
    }
  }

  document.querySelectorAll('[data-preview-card]').forEach(setupPreview);
  document.querySelectorAll('.playlist-thumb').forEach(setupPreview);
  document.querySelectorAll('.public-course-preview').forEach(setupPreview);
  document.querySelectorAll('.person-preview').forEach(setupPreview);
  initCourseForm();
  initCoursePlayer();
})();