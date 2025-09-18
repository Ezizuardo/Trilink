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

  const searchForm = document.querySelector('[data-search-form]');
  if(searchForm){
    const input = searchForm.querySelector('[data-search-input]');
    const panel = searchForm.querySelector('[data-suggestion-panel]');
    const list = searchForm.querySelector('[data-suggestion-list]');
    let suggestions = [];
    try{
      suggestions = JSON.parse(searchForm.dataset.suggestions || '[]');
    }catch(e){ suggestions = []; }
    const renderSuggestions = (items)=>{
      if(!panel || !list) return;
      list.innerHTML = '';
      const toRender = items.slice();
      toRender.forEach(item=>{
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'suggest-item' + (item.has_course ? ' has-course':'');
        btn.dataset.nickname = item.nickname || '';
        btn.dataset.name = item.name || '';
        btn.dataset.url = item.url || '';
        btn.innerHTML = `<img class="avatar-mini" src="${item.avatar || ''}" alt="${item.name || ''}"><span><strong>${item.name || ''}</strong>${item.nickname ? `<small>@${item.nickname}</small>` : ''}${item.course_title ? `<small>${item.course_title}</small>` : ''}</span>`;
        btn.addEventListener('click', ()=>{
          if(input){
            if(item.nickname){
              input.value = '@' + item.nickname;
            }else if(item.name){
              input.value = item.name;
            }
            panel.hidden = true;
            searchForm.submit();
          }
        });
        list.appendChild(btn);
      });
      panel.hidden = toRender.length === 0;
      if(!panel.hidden){
        panel.scrollTop = 0;
      }
      panel.classList.toggle('scrollable', toRender.length > 5);
    };
    const filter = (value)=>{
      const q = (value || '').trim().toLowerCase();
      if(!q){
        renderSuggestions(suggestions);
        return;
      }
      const filtered = suggestions.filter(item=>{
        const hay = [item.name || '', item.nickname || '', item.course_title || ''].join(' ').toLowerCase();
        return hay.includes(q);
      });
      renderSuggestions(filtered);
    };
    if(input){
      input.addEventListener('focus', ()=>{
        filter(input.value);
      });
      input.addEventListener('input', ()=>{
        filter(input.value);
      });
      input.addEventListener('blur', ()=>{
        setTimeout(()=>{ if(panel) panel.hidden = true; }, 150);
      });
    }
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
    if(player.dataset.locked === '1') return;
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

  const purchaseModal = document.querySelector('[data-purchase-modal]');
  const purchaseLink = purchaseModal ? purchaseModal.querySelector('[data-purchase-telegram]') : null;
  const purchaseContact = purchaseModal ? purchaseModal.querySelector('[data-purchase-contact]') : null;
  const purchaseFallback = purchaseModal ? purchaseModal.querySelector('[data-purchase-contact-fallback]') : null;
  const purchaseClose = purchaseModal ? purchaseModal.querySelector('[data-purchase-close]') : null;
  const buildTelegramLink = (raw)=>{
    const clean = (raw || '').trim();
    if(!clean) return null;
    if(/^https?:\/\//i.test(clean)){
      return {href: clean, label: clean.replace(/^https?:\/\//i, '')};
    }
    if(clean.toLowerCase().startsWith('t.me/')){
      const href = clean.toLowerCase().startsWith('http') ? clean : `https://${clean}`;
      return {href, label: clean};
    }
    if(clean.startsWith('@')){
      return {href: `https://t.me/${clean.slice(1)}`, label: clean};
    }
    return {href: `https://t.me/${clean}`, label: `@${clean}`};
  };
  const showPurchaseModal = (handle)=>{
    if(!purchaseModal) return;
    if(purchaseLink){
      const contact = buildTelegramLink(handle);
      if(contact){
        purchaseLink.href = contact.href;
        purchaseLink.textContent = contact.label;
        purchaseLink.target = '_blank';
        if(purchaseContact) purchaseContact.hidden = false;
        if(purchaseFallback) purchaseFallback.hidden = true;
      }else{
        purchaseLink.removeAttribute('href');
        purchaseLink.removeAttribute('target');
        purchaseLink.textContent = 'в Telegram';
        if(purchaseContact) purchaseContact.hidden = true;
        if(purchaseFallback) purchaseFallback.hidden = false;
      }
    }
    purchaseModal.hidden = false;
  };
  if(purchaseClose){
    purchaseClose.addEventListener('click', ()=>{
      purchaseModal.hidden = true;
    });
  }
  document.querySelectorAll('[data-purchase-button]').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const courseId = btn.dataset.courseId;
      const player = btn.closest('[data-player]');
      if(!courseId) return;
      btn.disabled = true;
      fetch(`/courses/${courseId}/request-access`, {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}})
        .then(res=>res.json().catch(()=>({ok:false})).then(data=>({status:res.status,data})))
        .then(({status,data})=>{
          if(!data || data.ok === false){
            if(data && data.requires_student){
              alert('Необходимо войти как ученик.');
            }else{
              alert((data && data.message) || 'Не удалось отправить заявку.');
            }
            btn.disabled = false;
            return;
          }
          if(player){
            const lock = player.querySelector('.player-lock-content');
            if(lock){
              const handle = (player.dataset.telegram || '').trim();
              const contact = buildTelegramLink(handle);
              const linkMarkup = contact ? ` в Telegram <a href="${contact.href}" target="_blank" rel="noopener">${contact.label}</a>` : '';
              const fallback = contact ? '' : '<p class="muted small">Специалист ещё не указал Telegram. Напишите ему в чат или дождитесь ответа в уведомлениях.</p>';
              lock.innerHTML = `<h3>Заявка на рассмотрении</h3><p>Мы уже отправили специалисту уведомление о вашем запросе.${linkMarkup ? ` Для оплаты свяжитесь${linkMarkup}.` : ' Для оплаты свяжитесь со специалистом.'}</p>${fallback}<p class="muted">Курс откроется после подтверждения оплаты.</p>`;
            }
          }
          showPurchaseModal(player ? player.dataset.telegram : '');
        })
        .catch(()=>{
          alert('Не удалось отправить заявку.');
          btn.disabled = false;
        });
    });
  });

  const deviceAlert = document.querySelector('[data-device-alert]');
  if(deviceAlert){
    const mainModal = deviceAlert.querySelector('[data-device-alert-main]');
    const warnModal = deviceAlert.querySelector('[data-device-alert-warning]');
    const doDismiss = ()=>{
      fetch('/device-alert/dismiss', {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}})
        .finally(()=>{ deviceAlert.remove(); });
    };
    const confirmBtn = deviceAlert.querySelector('[data-device-alert-confirm]');
    if(confirmBtn){
      confirmBtn.addEventListener('click', ()=>{
        if(mainModal) mainModal.hidden = true;
        if(warnModal) warnModal.hidden = false;
      });
    }
    const dismissBtn = deviceAlert.querySelector('[data-device-alert-dismiss]');
    if(dismissBtn){
      dismissBtn.addEventListener('click', ()=>{
        doDismiss();
      });
    }
    const cancelBtn = deviceAlert.querySelector('[data-device-alert-cancel]');
    if(cancelBtn){
      cancelBtn.addEventListener('click', ()=>{
        doDismiss();
      });
    }
    const logoutBtn = deviceAlert.querySelector('[data-device-alert-logout]');
    if(logoutBtn){
      logoutBtn.addEventListener('click', ()=>{
        fetch('/device-alert/terminate', {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}})
          .then(res=>res.json().catch(()=>({})))
          .then(data=>{
            if(data && data.redirect){
              window.location.href = data.redirect;
            }else{
              window.location.reload();
            }
          })
          .catch(()=>{ window.location.reload(); });
      });
    }
  }
})();
