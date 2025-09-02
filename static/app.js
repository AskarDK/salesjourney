// === Telegram linking component (вынесено вверх, чтобы Alpine видел его сразу) ===
window.TELEGRAM_BOT_USERNAME = window.TELEGRAM_BOT_USERNAME || "{{ TELEGRAM_BOT_USERNAME }}";

window.tgLinker = function(){
  return {
    state: { linked:false, chat_id:null, code:null, bot_username:(window.TELEGRAM_BOT_USERNAME || null) },
    loading:false, _pollTimer:null, _pollUntil:0,
    async init(){ await this.fetchStatus(); },
    async fetchStatus(){
      try{
        const r = await fetch('/api/telegram/status', { credentials:'same-origin' });
        const j = await r.json().catch(()=>({}));
        if(j && j.ok){
          this.state.linked = !!j.data?.linked;
          this.state.chat_id = j.data?.chat_id || null;
          this.state.bot_username = j.data?.bot_username || this.state.bot_username;
          if(this.state.linked) this._stopPolling();
        }
      }catch(_e){}
    },
    botDeepLink(){
      const u = this.state.bot_username || (typeof TELEGRAM_BOT_USERNAME !== 'undefined' ? TELEGRAM_BOT_USERNAME : '');
      const code = this.state.code ? encodeURIComponent(this.state.code) : '';
      return u ? `https://t.me/${u}${code ? `?start=${code}` : ''}` : 'https://t.me/';
    },
    async generate(){
      if (this.loading) return;
      this.loading = true;
      try{
        const r = await fetch('/api/telegram/generate', { method:'POST', credentials:'same-origin' });
        const j = await r.json().catch(()=>({}));
        if(!r.ok || !j.ok) throw new Error(j.error || 'Не удалось сгенерировать код');
        this.state.code = j.code;
        this._startPolling(60_000, 3000);
      }catch(e){
        try { Alpine.store('toasts')?.push({title:'Telegram', text:e.message || 'Ошибка', emoji:'⚠️'}); } catch(_){}
      }finally{ this.loading = false; }
    },
    async copyCode(){
      try{
        if (!this.state.code) return;
        await navigator.clipboard.writeText(this.state.code);
        Alpine.store('toasts')?.push({title:'Telegram', text:'Код скопирован', emoji:'📋'});
      }catch(_e){}
    },
    async resetLink(){
      if(!confirm('Сбросить привязку Telegram?')) return;
      this.loading = true;
      try{
        const r = await fetch('/api/telegram/reset', { method:'POST', credentials:'same-origin' });
        const j = await r.json().catch(()=>({}));
        if(!r.ok || !j.ok) throw new Error(j.error || 'Не удалось сбросить привязку');
        this.state.linked = false; this.state.chat_id = null; this.state.code = null;
        Alpine.store('toasts')?.push({title:'Telegram', text:'Привязка сброшена', emoji:'ℹ️'});
      }catch(e){
        Alpine.store('toasts')?.push({title:'Telegram', text:e.message || 'Ошибка', emoji:'⚠️'});
      }finally{ this.loading = false; }
    },
    _startPolling(totalMs=60000, stepMs=3000){
      this._stopPolling(); this._pollUntil = Date.now() + totalMs;
      this._pollTimer = setInterval(async ()=>{
        await this.fetchStatus();
        if(this.state.linked || Date.now() > this._pollUntil){ this._stopPolling(); }
      }, stepMs);
    },
    _stopPolling(){ if(this._pollTimer){ clearInterval(this._pollTimer); this._pollTimer = null; } }
  }
};

// Надёжная регистрация компонента для обоих кейсов (Alpine уже есть / только инициализируется)
(function registerTgLinker(){
  function reg(){
    try{
      if (typeof window.tgLinker === 'function' && window.Alpine?.data) {
        Alpine.data('tgLinker', window.tgLinker);
      }
    }catch(_){}
  }
  if (window.Alpine) reg();
  window.addEventListener('alpine:init', reg);
})();


// ======================== Alpine stores: toasts & fx =========================
document.addEventListener('alpine:init', () => {
  // Toasts
  Alpine.store('toasts', {
    id: 1,
    items: [],
    push(t){ // {title, text, emoji}
      const id = this.id++;
      const item = { id, ...t, show:true };
      this.items.push(item);
      setTimeout(()=>{ this.dismiss(id); }, 4000);
    },
    dismiss(id){
      const it = this.items.find(x=>x.id===id);
      if(!it) return;
      it.show = false;
      setTimeout(()=>{ this.items = this.items.filter(x=>x.id!==id); }, 200);
    }
  });

  // FX: coins & confetti
  Alpine.store('fx', {
    confetti(){
      const c = document.getElementById('confetti');
      if(!c) return;
      const ctx = c.getContext('2d');
      const W = c.width = window.innerWidth;
      const H = c.height = window.innerHeight;
      const N = 180;
      const cols = ['#60a5fa','#a78bfa','#22d3ee','#f472b6','#34d399'];
      const P = Array.from({length:N}, () => ({
        x: Math.random()*W, y: -10, dx: -1+Math.random()*2, dy: 1+Math.random()*3,
        r: 1.5+Math.random()*2.5, col: cols[(Math.random()*cols.length)|0]
      }));
      let t=120;
      (function frame(){
        ctx.clearRect(0,0,W,H);
        P.forEach(p=>{ ctx.fillStyle=p.col; ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,6.28); ctx.fill(); p.x+=p.dx; p.y+=p.dy; });
        if(t-- > 0) requestAnimationFrame(frame); else ctx.clearRect(0,0,W,H);
      })();
    },
    coins(){
      // небольшой спарк
      Alpine.store('toasts').push({title:'+XP', text:'Начислены очки', emoji:'🪙'});
    }
  });

  // Auth store
  Alpine.store('auth', {
    user: null,
    loading: false,
    async refresh(){
      try{
        this.loading = true;
        const r = await fetch('/api/me', { credentials: 'include' });
        if(!r.ok) { this.setUser(null); return; }
        const data = await r.json();
        this.setUser(data && data.user ? data.user : data);
      } catch(e){
        console.error('auth.refresh error', e);
        this.setUser(null);
      } finally {
        this.loading = false;
      }
    },
    setUser(u){
      this.user = u;
      try { hydrateAuthNav(u); } catch(_) {}
      try { renderOnboardingProfileAside(u); } catch(_) {}
      window.dispatchEvent(new CustomEvent('auth:updated', { detail: u }));
    }
  });

  // При старте страницы пробуем подтянуть текущего пользователя
  Alpine.store('auth').refresh();
});

// --------------------------- Navbar hydration -------------------------------
function hydrateAuthNav(user){
  // Ищем контейнер навигации: сначала явный, затем общие варианты
  const nav =
    document.querySelector('[data-nav-auth]') ||
    document.querySelector('#nav-auth') ||
    document.querySelector('header nav') ||
    document.querySelector('nav');

  if(!nav) return;

  // Если пользователь не залогинен — ничего не трогаем
  if(!user || !user.id) return;

  // Пытаемся найти блок авторизации и заменить его на профиль-мини
  let slot =
    nav.querySelector('[data-auth-slot]') ||
    nav.querySelector('#auth-slot') ||
    nav;

  const avatarSrc = `/avatar_svg/${user.id}?preview_level=2`;
  const name = (user.display_name || user.email || 'Профиль')
                .toString().replace(/</g,'&lt;');

  const html = `
    <a href="/profile" data-user-badge class="flex items-center gap-2 group" style="text-decoration:none">
      <img src="${avatarSrc}" alt="" width="28" height="28"
           style="border-radius:9999px;border:1px solid rgba(255,255,255,.15)" />
      <span class="text-sm">${name}</span>
    </a>`.trim();

  // Пробуем убрать ссылки входа/регистрации (если есть)
  [...slot.querySelectorAll('a[href="/login"], a[href="/register"]')]
    .forEach(a => a.parentElement ? a.parentElement.removeChild(a) : a.remove());

  // Если уже есть бейдж — просто обновим
  const badge = slot.querySelector('[data-user-badge]');
  if(badge){
    badge.outerHTML = html;
  } else {
    const wrap = document.createElement('div');
    wrap.innerHTML = html.trim();
    slot.appendChild(wrap.firstChild);
  }
}

// ---------------- Onboarding right-side profile (floating) -------------------
function renderOnboardingProfileAside(user){
  const onbRoot =
    document.querySelector('[data-onboarding-root]') ||
    document.getElementById('onboarding-root') ||
    document.querySelector('[data-page="onboarding"]');
  if(!onbRoot) return;

  const ASIDE_ID = 'onb-profile-aside';
  let aside = document.getElementById(ASIDE_ID);

  // Нет пользователя — убираем панель
  if(!user || !user.id){
    if(aside){
      try { _onbAsideRemovePadding?.(aside); } catch(_) {}
      aside.remove();
    }
    return;
  }

  // Данные
  const avatarSrc = `/avatar_svg/${user.id}?preview_level=2`;
  const xp = user.xp ?? 0;
  const lvl = user.level ?? 1;
  const coins = user.coins ?? 0;
  const nextXp = user.next_level_xp ?? (lvl * 100);
  const pct = Math.max(0, Math.min(100, Math.round((xp / nextXp) * 100)));

  const safeName = String(user.display_name || user.email || 'Профиль').replace(/</g, '&lt;');

  const panelHtml = `
    <aside id="${ASIDE_ID}" data-onb-aside
           class="hidden lg:block fixed right-6 top-24 z-40 rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-slate-900/60 backdrop-blur shadow-xl p-5"
           style="width:clamp(280px,22vw,360px)">
      <div class="flex items-center gap-3 mb-4">
        <img src="${avatarSrc}" class="w-14 h-14 rounded-full ring-1 ring-black/10 dark:ring-white/10" alt="avatar">
        <div>
          <div class="font-semibold text-slate-900 dark:text-white">${safeName}</div>
          <div class="text-xs text-slate-600 dark:text-slate-400">Уровень ${lvl} • ${xp} / ${nextXp} XP</div>
        </div>
      </div>

      <div class="mt-2 h-2 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden" role="progressbar"
           aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Прогресс уровня">
        <div class="h-full" style="width:${pct}%; background:linear-gradient(90deg,#6366f1,#22d3ee,#34d399)"></div>
      </div>

      <div class="mt-3 text-sm text-slate-700 dark:text-slate-300">🪙 Coins: <b>${coins}</b></div>
    </aside>
  `;

  if (aside) {
    aside.outerHTML = panelHtml;
    aside = document.getElementById(ASIDE_ID);
  } else {
    const wrap = document.createElement('div');
    wrap.innerHTML = panelHtml;
    document.body.appendChild(wrap.firstElementChild);
  }
}

// ---------------- Helper: call after onboarding registration step -----------
window.addEventListener('onboarding:registered', async () => {
  if(window.Alpine?.store('auth')){
    await Alpine.store('auth').refresh();
  }
});

// Глобальный помощник тостов (используется везде)
window.toast = function(msg, opts){
  try {
    if (window.Alpine && Alpine.store && Alpine.store('toasts')) {
      Alpine.store('toasts').push({ title: (opts && opts.title) || 'Сообщение', text: msg, emoji: (opts && opts.emoji) || undefined });
      return;
    }
  } catch(_) {}
  if (window.__pushToast) { window.__pushToast({ title: (opts && opts.title) || 'Сообщение', text: msg }); return; }
  alert(msg);
};

// ========================= Публичный онбординг (РАСШИРЕННАЯ ВЕРСИЯ) ==========================
window.OnboardingPage = function (slug, isAuth = false) {
  return {
    /* -------- Состояние -------- */
    slug,
    isAuth,
    sessionId: null,
    currentStep: null,
    coins: 0, xp: 0,

    prizes: [], picked: false,
    interview: null,
    inputValue: "",
    stepsCache: [],
    emptyFlow: false,
    selectedKeys: [],

    /* Регистрация (расширенная) */
    regName: "", regEmail: "", regPassword: "",
    regGender: null, regTermsAccepted: false,

    /* Bundled ask_input */
    bulkReg: { name: "", first_name: "", last_name: "", phone: "", email: "" },
    regStage: { active: false, startedFromStepId: null },
    regCompleted: false,

    /* Правая панель аватара */
    showAvatarPanel: false,
    avatarUrl: '',
    userNameForAvatar: '',
    avatarShown: false,

    // ➕ новое
    currentUserId: null,
    avatarIntro: false,

    /* Приветственная модалка/компания */
    showWelcome: false,
    companyTitle: "",
    companySlug: "",

    /* Конфетти для модалки */
    confetti: { raf: null, t0: 0, duration: 1600, active: false, parts: [] },

    /* Вспомогательное — стадия для прогресса */
    stage: 1,

    /* -------- Инициализация -------- */
    async start() {
      this.companySlug = this.slug || "";
      this.openWelcome();
      this.resolveCompanyTitle().catch(()=>{});

      try {
        const r = await fetch('/api/reg/start', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ slug: this.slug })
        });

        // 🔒 Только для новеньких: сервер вернул 403 — онбординг уже пройден
        if (r.status === 403) {
          const j = await r.json().catch(()=>({}));
          this.toast(j.description || 'Онбординг уже пройден');
          setTimeout(()=>{ window.location.href = '/profile'; }, 1000);
          return;
        }

        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка старта');

        this.sessionId = j.session_id;

        const fromStartName =
          (j.company && j.company.name) || j.company_name ||
          (j.flow && j.flow.company && j.flow.company.name) || j.flow_company_name || "";
        if (fromStartName && !this.companyTitle) this.companyTitle = fromStartName;

        const fromStartSlug =
          (j.company && j.company.slug) || j.company_slug ||
          (j.flow && j.flow.company && j.flow.company.slug) || j.flow_company_slug || "";
        if (fromStartSlug) this.companySlug = fromStartSlug;

        if (j.next_step) {
          this.currentStep = j.next_step;
          this.stepsCache = [j.next_step.id];

          if (this.currentStep?.type === 'first_assignment' && !this.interview) {
            this.loadInterview().catch(()=>{});
          }
          if (this.currentStep.type === 'ask_input') {
            this.regStage.active = true;
            this.regStage.startedFromStepId = this.currentStep.id;
            this.stage = 2;
          } else {
            this.stage = 1;
          }
        } else {
          this.emptyFlow = true;
          this.currentStep = null;
          this.stepsCache = [];
        }
      } catch (e) {
        this.toast(e.message);
      }
    },

    /* -------- Методы UI / helpers -------- */
    toast(msg, opts){ try { window.toast(msg, opts); } catch(_) { alert(msg); } },

    // ➕ новое: мгновенная перерисовка аватара (cache-busting)
    refreshAvatar(){
      if(!this.currentUserId) return;
      this.avatarUrl = `/avatar_svg/${this.currentUserId}?t=${Date.now()}`;
    },
    avatarPreview(g){
      return `/avatar_svg/preview?gender=${encodeURIComponent(g)}`;
    },

    // ➕ новое: мягкая интро-анимация появления панели
    animateAvatarIntro(){
      this.showAvatarPanel = true;
      this.avatarShown = true;
      this.avatarIntro = true;
      this.$nextTick(() => {
        setTimeout(() => { this.avatarIntro = false; }, 2800);
      });
    },

    selectGender(g){ this.regGender = g; },

    async registerFromSection() {
      if (!this.regGender) { this.toast('Пожалуйста, выберите вашего персонажа', { title:'Внимание' }); return; }
      if (!this.regName || !this.regEmail || !this.regPassword) { this.toast('Заполните имя, email и пароль', { title:'Внимание' }); return; }
      if (!this.regTermsAccepted) { this.toast('Необходимо принять условия оферты', { title:'Внимание' }); return; }

      try {
        const r = await fetch('/api/auth/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            email: this.regEmail,
            password: this.regPassword,
            display_name: this.regName,
            gender: this.regGender,
            reg_session_id: this.sessionId
          })
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка регистрации');

        const user = j.user || {};
        this.userNameForAvatar = user.display_name || this.regName;
        this.currentUserId = user.id || 0;

        // >>> гидратация: обновляем навбар и правый сайдбар без перезагрузки
        try { if (window.Alpine?.store('auth')) { Alpine.store('auth').setUser(user); } } catch(_) {}
        window.dispatchEvent(new Event('onboarding:registered'));

        // красивое первое появление + актуальный svg
        this.animateAvatarIntro();
        this.refreshAvatar();

        this.toast('Аккаунт создан! Добро пожаловать!', { title: 'Успех', emoji: '🎉' });

        await this.submitStep({});
      } catch (e) {
        this.toast(e.message, { title: 'Ошибка регистрации' });
      }
    },

    // Пакетная отправка ask_input шагов
    async submitBulkRegistration() {
      if (!this.regStage.active) {
        this.regStage.active = true;
        this.stage = 2;
      }
      if (!this.bulkReg.name || !this.bulkReg.email) {
        this.toast('Укажите имя и email');
        return;
      }

      try {
        let step = this.currentStep;
        const values = {
          first_name: this.bulkReg.first_name?.trim(),
          last_name:  this.bulkReg.last_name?.trim(),
          name:       this.bulkReg.name?.trim(),
          phone:      this.bulkReg.phone?.trim(),
          email:      this.bulkReg.email?.trim(),
        };

        while (step && step.type === 'ask_input') {
          const field = step.ask_field || 'name';
          const value = values[field] ?? '';
          if (!value) { this.toast(`Заполните поле: ${this.labelFor(field)}`); return; }

          const r = await fetch(`/api/reg/step/${step.id}/submit`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ value, reg_session_id: this.sessionId })
          });
          const j = await r.json();
          if (!r.ok) throw new Error(j.description || `Ошибка шага (${field})`);
          this.coins = j.coins || this.coins;
          this.xp    = j.xp    || this.xp;

          step = j.next_step || null;
          if (step) this.stepsCache.push(step.id);
        }

        this.regStage.active = false;
        this.regCompleted = true;
        this.stage = 3;

        this.currentStep = step ? step : { type: 'reward_shop', title: 'Финальный бонус' };
      } catch (e) { this.toast(e.message); }
    },

    /* Переходы между шагами */
    async submitStep(payload) {
      try {
        const r = await fetch(`/api/reg/step/${this.currentStep.id}/submit`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ ...(payload||{}), reg_session_id: this.sessionId })
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка шага');

        this.coins = j.coins || 0;
        this.xp = j.xp || 0;
        this.inputValue = "";

        this.refreshAvatar();

        if (j.next_step) {
          this.currentStep = j.next_step;

          if (this.currentStep?.type === 'first_assignment' && !this.interview) {
            this.loadInterview().catch(()=>{});
          }

          this.stepsCache.push(j.next_step.id);

          if (this.currentStep.type === 'ask_input') {
            this.regStage.active = true;
            this.regStage.startedFromStepId = this.currentStep.id;
            this.stage = 2;
          }
        } else {
          this.currentStep = { type: 'reward_shop', title: 'Финальный бонус' };
        }
      } catch(e) { this.toast(e.message); }
    },

    async finish() {
      try {
        const r = await fetch(`/api/reg/finish`, {method:'POST'});
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка финала');
        this.coins = j.coins_total || this.coins;
        this.prizes = j.prizes || [];
        this.refreshAvatar();
      } catch(e) { this.toast(e.message); }
    },

    async pickReward(itemId, cost) {
      try {
        const r = await fetch(`/api/reg/reward/pick`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({store_item_id: itemId})
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Нельзя выбрать приз');
        this.picked = true;
        this.coins = this.coins - (cost || 0);
        this.refreshAvatar();
        this.toast('Приз выбран!', {emoji:'🎁'});
      } catch(e) { this.toast(e.message); }
    },

    async loadInterview() {
      try {
        const r = await fetch(`/api/reg/interview`);
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка приглашения');
        this.interview = j;
      } catch(e) { this.toast(e.message); }
    },

    async finishAndRegister() {
      if (!this.prizes.length) await this.finish();

      if (!this.regName || !this.regEmail || !this.regPassword) {
        this.toast('Заполните имя, email и пароль', { title:'Внимание' }); return;
      }
      if (!this.regGender) { this.toast('Пожалуйста, выберите вашего персонажа', { title:'Внимание' }); return; }
      if (!this.regTermsAccepted) { this.toast('Необходимо принять условия оферты', { title:'Внимание' }); return; }

      try {
        const r = await fetch('/api/auth/register', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            email: this.regEmail,
            password: this.regPassword,
            display_name: this.regName,
            reg_session_id: this.sessionId,
            gender: this.regGender
          })
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.description || 'Ошибка регистрации');

        const user = j.user || {};
        this.currentUserId = user.id || 0;
        this.userNameForAvatar = user.display_name || this.regName;

        this.refreshAvatar();
        this.animateAvatarIntro();

        this.toast('Аккаунт создан и привязан к компании!', {emoji:'✅'});
      } catch(e) { this.toast(e.message); }
    },

    /* -------- Утилиты -------- */
    async resolveCompanyTitle(){
      const tryEndpoints = [
        `/api/reg/link/${encodeURIComponent(this.slug)}`,
        `/api/reg/link?slug=${encodeURIComponent(this.slug)}`,
        `/api/reg/resolve?slug=${encodeURIComponent(this.slug)}`,
        `/api/reg/info?slug=${encodeURIComponent(this.slug)}`
      ];
      for (const url of tryEndpoints){
        try{
          const r = await fetch(url);
          if (!r.ok) continue;
          const j = await r.json().catch(()=>null);
          const name = (j && j.company && j.company.name) || j?.company_name || j?.name || "";
          const slug = (j && j.company && j.company.slug) || j?.company_slug || j?.slug || this.slug || "";
          if (name) this.companyTitle = name;
          if (slug) this.companySlug = slug;
          if (name || slug) break;
        }catch(_e){}
      }
      if (!this.companyTitle) this.companyTitle = 'Компания';
    },

    companyLink(){ return this.companySlug ? `/company/${this.companySlug}` : '#'; },

    // Приветственная модалка + локальный канвас-конфетти
    openWelcome(){
      this.showWelcome = true;
      document.body.style.overflow = 'hidden';
      this.$nextTick(() => {
        const btn = document.querySelector('.modal-x');
        btn && btn.focus && btn.focus();
        this.launchConfetti();
      });
    },
    closeWelcome(){
      this.showWelcome = false;
      document.body.style.overflow = '';
      this.stopConfetti(true);
    },

    launchConfetti(){
      const canvas = this.$refs?.confetti;
      if (!canvas) return;

      const dpr = Math.max(1, window.devicePixelRatio || 1);
      const rect = canvas.parentElement.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      canvas.style.width = rect.width + 'px';
      canvas.style.height = rect.height + 'px';

      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const colors = ['#22c55e', '#06b6d4', '#6366f1', '#f59e0b', '#ef4444', '#10b981'];
      const w = rect.width, h = rect.height;
      const N = 160;
      const parts = [];
      const rand = (a,b)=> a + Math.random()*(b-a);

      for (let i=0;i<N;i++){
        const angle = rand(-Math.PI/3, -2*Math.PI/3);
        const speed = rand(4, 9);
        parts.push({
          x: w/2 + rand(-60,60),
          y: h*0.75 + rand(-10,10),
          vx: Math.cos(angle)*speed,
          vy: Math.sin(angle)*speed,
          g: rand(0.18, 0.28),
          w: rand(6, 12),
          h: rand(8, 16),
          rot: rand(0, Math.PI*2),
          vr: rand(-0.25, 0.25),
          color: colors[(Math.random()*colors.length)|0],
          alpha: 1,
          va: rand(-0.005, -0.002),
          shape: Math.random() < 0.2 ? 'circle' : 'rect'
        });
      }

      this.confetti.parts = parts;
      this.confetti.active = true;
      this.confetti.t0 = performance.now();

      const step = (t)=>{
        if (!this.confetti.active) return;
        ctx.clearRect(0,0,w,h);
        for (const p of this.confetti.parts){
          p.vy += p.g; p.x += p.vx; p.y += p.vy; p.rot += p.vr;
          p.alpha += p.va; if (p.alpha < 0) p.alpha = 0;

          ctx.save(); ctx.globalAlpha = p.alpha; ctx.translate(p.x, p.y); ctx.rotate(p.rot);
          ctx.fillStyle = p.color;
          if (p.shape === 'circle'){ ctx.beginPath(); ctx.arc(0, 0, p.w*0.6, 0, Math.PI*2); ctx.fill(); }
          else { ctx.fillRect(-p.w/2, -p.h/2, p.w, p.h); }
          ctx.restore();
        }
        const dt = t - this.confetti.t0;
        if (dt > this.confetti.duration || this.confetti.parts.every(p => p.alpha <= 0.02 || p.y > h+40)){
          this.stopConfetti(); return;
        }
        this.confetti.raf = requestAnimationFrame(step);
      };
      this.confetti.raf = requestAnimationFrame(step);
    },
    stopConfetti(clearOnly){
      this.confetti.active = false;
      if (this.confetti.raf){ cancelAnimationFrame(this.confetti.raf); this.confetti.raf = null; }
      if (clearOnly){
        const canvas = this.$refs?.confetti;
        if (canvas){
          const ctx = canvas.getContext('2d');
          const rect = canvas.getBoundingClientRect();
          ctx.clearRect(0,0,rect.width, rect.height);
        }
      }
    },

    youtubeEmbed(u) {
      try {
        if (!u) return '';
        const m1 = u.match(/youtu\.be\/([\w-]+)/);
        const m2 = u.match(/[?&]v=([\w-]+)/);
        const id = (m1 && m1[1]) || (m2 && m2[1]) || '';
        return id ? `https://www.youtube.com/embed/${id}` : u;
      } catch (e) { return u; }
    },

    labelFor(f) {
      return f === 'first_name' ? 'Имя'
        : f === 'last_name' ? 'Фамилия'
        : f === 'name' ? 'Имя и фамилия'
        : f === 'phone' ? 'Телефон'
        : f === 'email' ? 'Email'
        : 'Поле';
    },

    md(src){
      if (!src) return '';
      return src.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
                .replace(/\*(.+?)\*/g, '<i>$1</i>')
                .replace(/\n/g, '<br/>');
    },

    fmtDT(iso){ try{ return new Date(iso).toLocaleString(); } catch { return iso; } },

    downloadICS(){
      if (!this.interview || !this.interview.date_time) return;
      const dt = new Date(this.interview.date_time);
      const dtstart = dt.toISOString().replace(/[-:]/g,'').split('.')[0] + 'Z';
      const dtend = new Date(dt.getTime()+60*60*1000).toISOString().replace(/[-:]/g,'').split('.')[0] + 'Z';
      const summary = 'Собеседование';
      const location = (this.interview.location||'').replace(/\n/g,' ');
      const desc = (this.interview.message||'').replace(/\n/g,' ');
      const ics = [
        'BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//SalesJourney//Onboarding//RU',
        'BEGIN:VEVENT',`DTSTART:${dtstart}`,`DTEND:${dtend}`,
        `SUMMARY:${summary}`,`LOCATION:${location}`,`DESCRIPTION:${desc}`,
        'END:VEVENT','END:VCALENDAR'
      ].join('\r\n');
      const blob = new Blob([ics], {type:'text/calendar'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'interview.ics'; a.click();
      URL.revokeObjectURL(url);
    },

    /* Интересы */
    selectLimit() { return 1; },
    toggleSelect(key) { this.selectedKeys = [key]; },
    selectedOption() {
      const key = this.selectedKeys[0];
      return (this.currentStep?.options || []).find(o => o.key === key) || null;
    },
    submitInterestSelection() {
      if (!this.selectedKeys.length) return;
      this.submitStep({ key: this.selectedKeys[0] });
    },

    /* Текст для first_assignment */
    firstAssignmentInterviewText(){
      const cfgDt = this.currentStep?.config?.date_time || null;
      const invDt = this.interview?.date_time || null;
      const raw = cfgDt || invDt;
      if(!raw) return '—';
      const dt = new Date(raw);
      const now = new Date();
      return (dt.getTime() > now.getTime()) ? this.fmtDT(dt.toISOString()) : 'Время собеседования уточните у рекрутера';
    },

    /* Прогресс (унифицированный) */
    progressPercent() {
      if (this.emptyFlow) return 0;
      const total = 4;
      let done = 0;
      if (this.stepsCache.length > 0) done = 1;
      if (this.regCompleted) done = Math.max(done, 2);
      if (this.avatarShown || this.showAvatarPanel) done = Math.max(done, 3);
      if (this.currentStep && this.currentStep.type === 'reward_shop') done = 4;
      const p = Math.round((done / total) * 100);
      return Math.max(5, Math.min(p, 100));
    }
  }
};

// ========================= Legacy company page model =========================
function partnerCompanyPageLegacy(companyId) {
  return {

    // --- базовое
    companyId,
    get headerSubtitle(){ return this.company ? `${this.company.name} (${this.company.slug})` : 'Нет компаний' },

    // нужно, чтобы шаблон не падал:
    company: null,
    kpi: {},
    leaderboard: [],

    // --- инвайт
    inviteModal: false,
    invite: null,

    // --- вкладки/кнопки
    tab: 'feed',
    tabBtn(kind){
      return `px-3 py-1 rounded-lg border ${this.tab===kind ? 'bg-white/10 border-white/20' : 'border-white/10 hover:bg-white/5'}`;
    },

    // --- лента
    canPost: false,
    newPost: '',
    newPostPreview: '',
    newPinned: false,
    feed: [],

    // --- задачи
    canCreateTasks: false,
    tasks: [],
    taskModal: {
      open: false,
      mode: 'create',
      form: {
        id: null,
        title: '',
        description: '',
        points_xp: 0,
        coins: 0,
        priority: 'normal',
        require_proof: false,
        _due_date: '',
        reward_achievement_id: null,
      },
      members: [],
      selectedIds: [],
      query: '',
    },

    async init() {
      try {
        if (!this.companyId) return;
        await this.loadDashboard();
      } catch (e) {
        console.error(e);
      }
    },

    async loadDashboard(){
      const r = await fetch(`/api/partners/company/${this.companyId}/dashboard`, { credentials: 'same-origin' });
      if(!r.ok){ return; }
      const d = await r.json();
      const dd = d.dashboard || d.data || d;

      this.company     = dd.company || dd.company_info || null;
      this.kpi         = dd.kpi || dd.stats || {};
      this.feed        = dd.feed || dd.company_feed || dd.posts || [];
      this.tasks       = dd.tasks || dd.company_tasks || [];
      this.leaderboard = dd.leaderboard || dd.top || [];

      const perms = dd.permissions || dd.perms || {};
      this.canPost        = !!(perms.can_post ?? perms.post ?? perms.can_create_feed ?? false);
      this.canCreateTasks = !!(perms.can_create_tasks ?? perms.tasks_create ?? perms.can_manage ?? false);
    },

    async fetchInvite() {
      const res = await fetch(`/api/partners/company/${this.companyId}/invite`, { credentials: 'same-origin' });
      if (!res.ok) { this.invite = { active: false }; return; }
      this.invite = await res.json();
    },
    openInviteModal() {
      this.fetchInvite();
      this.inviteModal = true;
    },
    async regenerateInvite() {
      const res = await fetch(`/api/partners/company/${this.companyId}/invite/regenerate`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
      });
      if (res.ok) this.invite = await res.json();
    },
    async deactivateInvite() {
      await fetch(`/api/partners/company/${this.companyId}/invite/deactivate`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
      });
      this.invite = { active: false };
    },

    // --- утилиты
    async copy(text) {
      try { await navigator.clipboard.writeText(text); } catch (e) {}
    },

    // --- заглушки
    async loadFeed(){ /* наполни feed */ },
    async loadTasks(){ /* наполни tasks */ },
    async checkCanPost(){ return false; },
    async checkCanCreateTasks(){ return false; },
  }
}

// ================== Partner page with Onboarding builder =====================
window.partnerCompanyPage = function(companyId){
  const base = partnerCompanyPageLegacy(companyId);
  const baseInit = base.init ? base.init.bind(base) : async () => {};

  const addon = {
    // === Онбординг ===
    onb: {
      flows: [],
      activeFlow: null,
      steps: [],
      links: [],
      tmpOpt: { key: '', title: '' },
    },
    addStepDialog: false,
    editStepDialog: false,
    formStep: { id:null, type:'intro_page', title:'', ask_field:'', coins_award:0, xp_award:0, body_md:'', cfg_date_time:'', cfg_location:'', cfg_message:'' },

    async init(){
      await baseInit();
      await this.loadFlows();
    },

    async loadFlows(){
      try{
        const r = await fetch(`/api/partners/company/${this.companyId}/onboarding/flows`);
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка загрузки флоу');
        this.onb.flows = j.flows || [];
      }catch(e){ toast(e.message); }
    },

    async createFlow(){
      try{
        const name = prompt('Название флоу', 'Онбординг кандидата');
        if(!name) return;
        const r = await fetch(`/api/partners/company/${this.companyId}/onboarding/flows`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ name, final_bonus_coins: 50 })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка создания флоу');
        await this.loadFlows();
        await this.openFlow(j.id);
      }catch(e){ toast(e.message); }
    },

    async openFlow(flowId){
      try{
        const r = await fetch(`/api/partners/onboarding/flows/${flowId}/steps`);
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка открытия флоу');
        this.onb.activeFlow = j.flow;
        this.onb.steps = (j.steps || []).sort((a,b)=>a.order_index-b.order_index);
        this.onb.links = j.links || [];
      }catch(e){ toast(e.message); }
    },

    async saveFlowMeta(){
      try{
        const f = this.onb.activeFlow; if(!f) return;
        const r = await fetch(`/api/partners/onboarding/flows/${f.id}`, {
          method:'PUT', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ name: f.name, final_bonus_coins: f.final_bonus_coins, is_active: !!f.is_active })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка сохранения флоу');
        toast('Сохранено');
      }catch(e){ toast(e.message); }
    },

    toggleFlowActive(e){
      if(!this.onb.activeFlow) return;
      this.onb.activeFlow.is_active = e.target.checked;
    },

    moveStep(idx, delta){
      const arr = this.onb.steps;
      const j = idx + delta;
      if(j<0 || j>=arr.length) return;
      [arr[idx], arr[j]] = [arr[j], arr[idx]];
      arr.forEach((s,i)=> s.order_index = i);
    },

    async saveOrder(){
      try{
        const f = this.onb.activeFlow; if(!f) return;
        const order = this.onb.steps.map(s=>s.id);
        const r = await fetch(`/api/partners/onboarding/flows/${f.id}/reorder`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ order })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка порядка шагов');
        toast('Порядок сохранён');
      }catch(e){ toast(e.message); }
    },

    resetFormStep(){
      this.formStep = { id:null, type:'intro_page', title:'', ask_field:'', coins_award:0, xp_award:0, body_md:'', cfg_date_time:'', cfg_location:'', cfg_message:'' };
    },

    async saveNewStep(){
      try{
        const f = this.onb.activeFlow; if(!f) return;
        const cfg = this.formStep.type==='interview_invite' ? {
          date_time: this.formStep.cfg_date_time || null,
          location: this.formStep.cfg_location || null,
          message: this.formStep.cfg_message || null
        } : {};
        const r = await fetch(`/api/partners/onboarding/flows/${f.id}/steps`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            type: this.formStep.type, title: this.formStep.title, ask_field: this.formStep.ask_field || null,
            body_md: this.formStep.body_md || null, media_url: null,
            is_required: this.formStep.type==='ask_input',
            coins_award: this.formStep.coins_award|0, xp_award: this.formStep.xp_award|0,
            order_index: this.onb.steps.length, config: cfg
          })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка добавления шага');
        this.addStepDialog=false; this.resetFormStep();
        await this.openFlow(f.id);
      }catch(e){ toast(e.message); }
    },

    editStep(s){
      this.formStep = {
        id:s.id, type:s.type, title:s.title||'', ask_field:s.ask_field||'',
        coins_award:s.coins_award||0, xp_award:s.xp_award||0, body_md:s.body_md||'',
        cfg_date_time: (s.config && s.config.date_time) ? s.config.date_time : '',
        cfg_location:  (s.config && s.config.location)  ? s.config.location  : '',
        cfg_message:   (s.config && s.config.message)   ? s.config.message   : ''
      };
      this.editStepDialog = true;
    },

    async updateStep(){
      try{
        const id = this.formStep.id; if(!id) return;
        const cfg = this.formStep.type==='interview_invite' ? {
          date_time: this.formStep.cfg_date_time || null,
          location: this.formStep.cfg_location || null,
          message: this.formStep.cfg_message || null
        } : {};
        const r = await fetch(`/api/partners/onboarding/steps/${id}`, {
          method:'PUT', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            title: this.formStep.title, ask_field: this.formStep.ask_field||null,
            body_md: this.formStep.body_md||null, media_url: null,
            coins_award: this.formStep.coins_award|0, xp_award: this.formStep.xp_award|0,
            config: cfg
          })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка обновления шага');
        this.editStepDialog=false; await this.openFlow(this.onb.activeFlow.id);
      }catch(e){ toast(e.message); }
    },

    async deleteStep(stepId){
      if(!confirm('Удалить шаг?')) return;
      try{
        const r = await fetch(`/api/partners/onboarding/steps/${stepId}`, { method:'DELETE' });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка удаления шага');
        await this.openFlow(this.onb.activeFlow.id);
      }catch(e){ toast(e.message); }
    },

    async addOption(stepId){
      try{
        const o = this.onb.tmpOpt;
        if(!o.key || !o.title) { toast('Укажите key и название'); return; }
        const r = await fetch(`/api/partners/onboarding/steps/${stepId}/options`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ key:o.key, title:o.title })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка добавления опции');
        this.onb.tmpOpt = { key:'', title:'' };
        await this.openFlow(this.onb.activeFlow.id);
      }catch(e){ toast(e.message); }
    },

    async deleteOption(o, stepId){
      if(!confirm('Удалить опцию?')) return;
      try{
        const r = await fetch(`/api/partners/onboarding/options/${o.id}`, { method:'DELETE' });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка удаления опции');
        await this.openFlow(this.onb.activeFlow.id);
      }catch(e){ toast(e.message); }
    },

    async generateLink(){
      try{
        const f = this.onb.activeFlow; if(!f) return;
        const slug = prompt('Slug ссылки (можно оставить пустым)');
        const expires = prompt('Срок (ISO 8601, напр. 2025-12-31T18:00:00) — можно пусто', '');
        const payload = { slug: slug||undefined, expires_at: expires||undefined };
        const r = await fetch(`/api/partners/onboarding/flows/${f.id}/link`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка генерации ссылки');
        await this.openFlow(f.id);
        toast('Ссылка создана');
      }catch(e){ toast(e.message); }
    },

    async deleteLink(linkId){
      if(!confirm('Удалить ссылку?')) return;
      try{
        const r = await fetch(`/api/partners/onboarding/links/${linkId}`, { method:'DELETE' });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Ошибка удаления ссылки');
        await this.openFlow(this.onb.activeFlow.id);
      }catch(e){ toast(e.message); }
    }
  };

  const obj = Object.assign(base, addon);
  return obj;
};

// === HOTFIX: дополнение partnerCompanyPage под привязки из шаблона ===
(function(){
  const orig = window.partnerCompanyPage;
  if (!orig) return;

  window.partnerCompanyPage = function(companyId){
    const vm = orig(companyId);

    // Состояние, которого не хватало
    vm.onbLoading = false;
    vm.onbDrawer  = vm.onbDrawer  || { open: false };
    vm.optDrawer  = vm.optDrawer  || { open: false };

    vm.onb = vm.onb || {};
    vm.onb.statsOpen      = vm.onb.statsOpen      || false;
    vm.onb.stats          = vm.onb.stats          || null;
    vm.onb.sessions       = vm.onb.sessions       || null;
    vm.onb.sessionsQuery  = vm.onb.sessionsQuery  || '';
    vm.onb.statsDays      = vm.onb.statsDays      || 30;
    vm.onb.onlyActive     = vm.onb.onlyActive     || false;
    vm.onb.onlyCompleted  = vm.onb.onlyCompleted  || false;
    vm.onb.optEditor      = vm.onb.optEditor      || null;

    vm.youtubeEmbed = vm.youtubeEmbed || function(u){
      try{
        if(!u) return '';
        const m1 = u.match(/youtu\.be\/([\w-]+)/);
        const m2 = u.match(/[?&]v=([\w-]+)/);
        const id = (m1 && m1[1]) || (m2 && m2[1]) || '';
        return id ? `https://www.youtube.com/embed/${id}` : u;
      }catch(e){ return u; }
    };

    // Дроверы
    vm.openOnbDrawer  = vm.openOnbDrawer  || function(){
      this.onbDrawer.open = true;
      document.body.style.overflow = 'hidden';
      if(!this.onb.flows?.length) this.loadFlows();
    };
    vm.closeOnbDrawer = vm.closeOnbDrawer || function(){
      this.onbDrawer.open = false;
      document.body.style.overflow = '';
    };
    vm.openFlowStats  = vm.openFlowStats  || function(flowId){
      if(!flowId) return;
      this.onb.statsOpen = true;
      this.onb.optEditor = null;
      this.optDrawer.open = true;
      this.loadFlowStats(flowId);
      this.loadFlowSessions(flowId, 1);
    };
    vm.closeOptDrawer = vm.closeOptDrawer || function(){
      this.optDrawer.open = false;
      this.onb.optEditor = null;
      this.onb.statsOpen = false;
    };

    // Оборачиваем loadFlows индикатором
    if (typeof vm.loadFlows === 'function'){
      const _loadFlows = vm.loadFlows.bind(vm);
      vm.loadFlows = async function(){
        this.onbLoading = true;
        try { await _loadFlows(); }
        finally { this.onbLoading = false; }
      };
    }

    // Статистика и сессии
    vm.loadFlowStats = vm.loadFlowStats || async function(flowId){
      try{
        const r = await fetch(`/api/partners/onboarding/flows/${flowId}/stats?days=${this.onb.statsDays}`);
        const j = await r.json();
        this.onb.stats = j;
      }catch(e){ toast(e.message); }
    };
    vm.loadFlowSessions = vm.loadFlowSessions || async function(flowId, page=1){
      try{
        const p = new URLSearchParams();
        p.set('days', String(this.onb.statsDays||30));
        p.set('page', String(page||1));
        p.set('per_page','20');
        if(this.onb.sessionsQuery?.trim()) p.set('q', this.onb.sessionsQuery.trim());
        if(this.onb.onlyActive && !this.onb.onlyCompleted) p.set('only_active','1');
        if(this.onb.onlyCompleted && !this.onb.onlyActive) p.set('only_completed','1');
        const r = await fetch(`/api/partners/onboarding/flows/${flowId}/sessions?`+p.toString());
        const j = await r.json();
        this.onb.sessions = j;
      }catch(e){ toast(e.message); }
    };
    vm.debouncedLoadSessions = vm.debouncedLoadSessions || function(){
      clearTimeout(this._debSess);
      this._debSess = setTimeout(()=>{
        if(this.onb.activeFlow?.id) this.loadFlowSessions(this.onb.activeFlow.id, 1);
      }, 350);
    };

    // Тумблеры активности
    vm.setFlowActive = vm.setFlowActive || (async function(flow, value){
      try{
        const r = await fetch(`/api/partners/onboarding/flows/${flow.id}`, {
          method:'PUT', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ is_active: !!value })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description||'Ошибка');
        flow.is_active = !!value;
      }catch(e){ toast(e.message); }
    });
    vm.toggleStepActive = vm.toggleStepActive || (async function(s, checked){
      try{
        const r = await fetch(`/api/partners/onboarding/steps/${s.id}`, {
          method:'PUT', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ is_active: !!checked })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description||'Ошибка');
        s.is_active = !!checked;
      }catch(e){ toast(e.message); }
    });

    // Левый редактор опции
    vm.editOption = vm.editOption || function(o, stepId){
      this.onb.statsOpen = false;
      this.optDrawer.open = true;
      this.onb.optEditor = {
        step_id: stepId,
        id: (o.id || o.option_id || null),
        key: o.key || o.slug || '',
        title: o.title || '',
        body_md: o.body_md || '',
        media_url: o.media_url || ''
      };
    };
    vm.saveOption = vm.saveOption || async function(){
      const e = this.onb.optEditor;
      if(!e?.id){ toast('ID опции не найден'); return; }
      try{
        const r = await fetch(`/api/partners/onboarding/options/${e.id}`, {
          method:'PUT', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ title:e.title, body_md:e.body_md||null, media_url:e.media_url||null })
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Не удалось обновить опцию');
        toast('Опция обновлена');
        this.closeOptDrawer();
        if(this.onb.activeFlow?.id) await this.openFlow(this.onb.activeFlow.id);
      }catch(err){ toast(err.message); }
    };

    return vm;
  };
})();

// =============== Кнопка с состоянием загрузки (Alpine data) =================
document.addEventListener('alpine:init', () => {
  Alpine.data('loadBtn', () => ({
    loading:false,
    async run(fn){
      if (this.loading) return;
      this.loading = true;
      try { await fn(); } finally { this.loading = false; }
    }
  }));
});

// ================= Toasts & unread notifications (IIFE) ======================
(function () {
  function ensureToastRoot() {
    var id = 'sj-toast-root';
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.style.position = 'fixed';
      el.style.top = '16px';
      el.style.right = '16px';
      el.style.zIndex = '9999';
      el.style.display = 'flex';
      el.style.flexDirection = 'column';
      el.style.gap = '8px';
      document.body.appendChild(el);
    }
    return el;
  }

  function pushToast(opts) {
    var root = ensureToastRoot();
    var box = document.createElement('div');
    box.style.background = 'rgba(15,23,42,0.92)';
    box.style.color = 'white';
    box.style.border = '1px solid rgba(255,255,255,0.1)';
    box.style.borderRadius = '12px';
    box.style.padding = '12px 14px';
    box.style.boxShadow = '0 8px 20px rgba(0,0,0,0.35)';
    box.style.maxWidth = '320px';

    var title = document.createElement('div');
    title.style.fontWeight = '600';
    title.style.marginBottom = '4px';
    title.textContent = opts.title || 'Уведомление';

    var body = document.createElement('div');
    body.style.opacity = '0.9';
    body.style.fontSize = '14px';
    body.textContent = opts.text || '';

    box.appendChild(title);
    box.appendChild(body);
    root.appendChild(box);

    setTimeout(function () {
      if (box && box.parentNode) box.parentNode.removeChild(box);
    }, opts.timeout || 5000);
  }

  // Экспорт для глобального window.toast
  window.__pushToast = pushToast;

  async function notifyUnread() {
    try {
      const r = await fetch('/api/notifications?unread_only=1');
      const j = await r.json();
      const items = Array.isArray(j.notifications) ? j.notifications : [];
      if (!items.length) return;
      items.forEach(n => {
        pushToast({ title: n.title || 'Уведомление', text: n.body || '' });
      });
      await fetch('/api/notifications/read', { method: 'POST' });
    } catch (e) {
      console.warn('notifyUnread failed', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', notifyUnread);
  } else {
    notifyUnread();
  }

  window.SJ = window.SJ || {};
  window.SJ.notifyUnread = notifyUnread;
})();

// =================== Reports Drawer (панель отчётов) =========================
(function () {
  var companyId = (typeof window.SJ_COMPANY_ID !== 'undefined' && window.SJ_COMPANY_ID)
    ? window.SJ_COMPANY_ID
    : (document.body && document.body.dataset && document.body.dataset.companyId ? document.body.dataset.companyId : null);
  if (!companyId) return;

  function createFab() {
    var btn = document.createElement('button');
    btn.id = 'sj-reports-fab';
    btn.textContent = 'Отчёты';
    Object.assign(btn.style, {
      position: 'fixed',
      right: '16px',
      bottom: '16px',
      zIndex: 9998,
      padding: '10px 14px',
      background: '#0F172A',
      color: '#fff',
      border: '1px solid rgba(255,255,255,0.15)',
      borderRadius: '12px',
      boxShadow: '0 10px 24px rgba(0,0,0,0.35)',
      cursor: 'pointer'
    });
    btn.addEventListener('click', openDrawer);
    document.body.appendChild(btn);
  }

  function ensureDrawer() {
    var host = document.getElementById('sj-reports-drawer');
    if (host) return host;

    host = document.createElement('div');
    host.id = 'sj-reports-drawer';
    Object.assign(host.style, {
      position: 'fixed',
      top: '0',
      right: '0',
      height: '100vh',
      width: '520px',
      maxWidth: '92vw',
      background: '#0B1220',
      color: '#E5E7EB',
      borderLeft: '1px solid rgba(255,255,255,0.08)',
      boxShadow: '-16px 0 40px rgba(0,0,0,0.45)',
      transform: 'translateX(100%)',
      transition: 'transform .25s ease',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column'
    });

    host.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.08)">
        <div style="font-weight:600">Отчёты по задачам</div>
        <button id="sj-reports-close" style="color:#9CA3AF;background:transparent;border:none;font-size:20px;cursor:pointer">&times;</button>
      </div>
      <div style="padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,0.06)">
        <button data-sj-filter="submitted" class="sj-tab sj-tab-active">На проверке</button>
        <button data-sj-filter="approved" class="sj-tab">Зачтённые</button>
        <button data-sj-filter="rejected" class="sj-tab">Отклонённые</button>
        <button data-sj-filter="all" class="sj-tab">Все</button>
      </div>
      <div id="sj-reports-list" style="padding:0;overflow:auto;flex:1 1 auto"></div>
      <style>
        #sj-reports-drawer .sj-tab {
          padding: 8px 10px; background:#111827; color:#E5E7EB; border:1px solid rgba(255,255,255,0.08);
          border-radius:10px; cursor:pointer; font-size:13px;
        }
        #sj-reports-drawer .sj-tab-active {
          background:#1F2937; border-color:rgba(255,255,255,0.18);
        }
        .sj-row { display:grid; grid-template-columns: 1fr 1fr auto; gap:8px; padding:12px 16px; border-bottom:1px solid rgba(255,255,255,0.06); }
        .sj-row > div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .sj-pill { font-size:11px; padding:3px 8px; border-radius:9999px; border:1px solid rgba(255,255,255,0.12); display:inline-block }
        .sj-pill.approved { background:rgba(16,185,129,0.18); color:#A7F3D0; border-color:rgba(16,185,129,0.35) }
        .sj-pill.rejected { background:rgba(239,68,68,0.18); color:#FCA5A5; border-color:rgba(239,68,68,0.35) }
        .sj-pill.submitted { background:rgba(99,102,241,0.18); color:#C7D2FE; border-color:rgba(99,102,241,0.35) }
        .sj-actions button {
          padding:6px 10px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); background:#0F172A; color:#E5E7EB; cursor:pointer; margin-left:6px;
        }
        .sj-actions button[disabled] { opacity:0.5; cursor:not-allowed; }
      </style>
    `;

    document.body.appendChild(host);
    host.querySelector('#sj-reports-close').addEventListener('click', closeDrawer);
    host.querySelectorAll('[data-sj-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        host.querySelectorAll('.sj-tab').forEach(b => b.classList.remove('sj-tab-active'));
        btn.classList.add('sj-tab-active');
        loadReports(btn.getAttribute('data-sj-filter'));
      });
    });
    return host;
  }

  function openDrawer() {
    var host = ensureDrawer();
    host.style.transform = 'translateX(0%)';
    loadReports('submitted');
  }
  function closeDrawer() {
    var host = document.getElementById('sj-reports-drawer');
    if (host) host.style.transform = 'translateX(100%)';
  }

  function fmt(dt) {
    if (!dt) return '—';
    try {
      var d = new Date(dt);
      return d.toLocaleString();
    } catch (_) { return dt; }
  }

  async function loadReports(status) {
    const list = document.getElementById('sj-reports-list');
    if (!list) return;
    list.innerHTML = `<div style="padding:16px;color:#9CA3AF">Загрузка...</div>`;
    try {
      const q = new URLSearchParams({ company_id: String(companyId), status: status || 'all' });
      const r = await fetch(`/api/partners/task_reports?` + q.toString());
      const j = await r.json();
      const rows = (j && j.reports) ? j.reports : [];

      if (!rows.length) {
        list.innerHTML = `<div style="padding:16px;color:#9CA3AF">Нет записей</div>`;
        return;
      }

      list.innerHTML = '';
      rows.forEach(row => {
        const wrap = document.createElement('div');
        wrap.className = 'sj-row';
        const pill = `<span class="sj-pill ${row.status}">${row.status.toUpperCase()}</span>`;
        wrap.innerHTML = `
          <div title="${row.task_title || ''}">
            <div style="font-weight:600">${row.task_title || '—'}</div>
            <div style="color:#9CA3AF;font-size:12px">Пользователь: ${row.user_name || row.user_id}</div>
          </div>
          <div>
            <div style="margin-bottom:4px">${pill}</div>
            <div style="color:#9CA3AF;font-size:12px">Отправлено: ${fmt(row.submitted_at)}</div>
            <div style="color:#9CA3AF;font-size:12px">Завершено: ${fmt(row.completed_at)}</div>
          </div>
          <div class="sj-actions" data-actions>
            <button data-approve>Одобрить</button>
            <button data-reject>Отклонить</button>
          </div>
        `;
        const btnApprove = wrap.querySelector('[data-approve]');
        const btnReject  = wrap.querySelector('[data-reject]');

        if (row.status === 'approved') {
          btnApprove.setAttribute('disabled', 'disabled');
        }
        if (row.status === 'rejected') {
          btnReject.setAttribute('disabled', 'disabled');
        }

        btnApprove.addEventListener('click', async () => {
          await review(row, true, wrap);
        });
        btnReject.addEventListener('click', async () => {
          await review(row, false, wrap);
        });

        list.appendChild(wrap);
      });
    } catch (e) {
      list.innerHTML = `<div style="padding:16px;color:#ef4444">Ошибка загрузки</div>`;
      console.warn('loadReports error', e);
    }
  }

  async function review(row, approve, wrapEl) {
    try {
      const res = await fetch(`/api/partners/company/${companyId}/tasks/${row.task_id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: row.user_id, approve: !!approve })
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j && j.description || 'Request failed');

      const status = approve ? 'approved' : 'rejected';
      row.status = status;

      const pill = wrapEl.querySelector('.sj-pill');
      pill.className = 'sj-pill ' + status;
      pill.textContent = status.toUpperCase();

      const btnApprove = wrapEl.querySelector('[data-approve]');
      const btnReject  = wrapEl.querySelector('[data-reject]');
      if (approve) btnApprove.setAttribute('disabled','disabled');
      else btnReject.setAttribute('disabled','disabled');

      try {
        if (typeof pushToast === 'function') {
          pushToast({ title: approve ? 'Зачтено' : 'Отклонено', text: row.task_title || '' });
        } else {
          toast(approve ? 'Зачтено' : 'Отклонено');
        }
      } catch (_) {}
    } catch (e) {
      console.warn('review error', e);
      alert('Не удалось выполнить действие: ' + (e && e.message ? e.message : 'ошибка'));
    }
  }
  createFab();
})();
