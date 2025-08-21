// =======================
// admin.js (final)
// =======================

// Глобальный компонент, чтобы x-data="adminApp()" его видел
window.adminApp = function () {
  const CREATE_COURSE_URL = '/api/admin/training/courses';

  return {
    // --------- СТЕЙТ ---------
    section: 'users',
    nav: [
      { key: 'users',       label: 'Пользователи' },
      { key: 'companies',   label: 'Компании' },
      { key: 'courses',     label: 'Курсы' },
      { key: 'store',       label: 'Магазин' },
      { key: 'avatars',     label: 'Аватары' },
      { key: 'achievements',label: 'Ачивки' },
      { key: 'contests',    label: 'Конкурсы' },
      { key: 'audit',       label: 'Аудит' },
      { key: 'events',      label: 'События' },
    ],

    users: [],
    companies: [],
    courses: [],
    store: [],
    avatarItems: [],
    achievements: [],
    contests: [],
    audit: [],
    events: [],

    filters: { userEmail:'', userName:'', eventsUserId: '' },

    modal: null,

    forms: {
      user:    { email:'', password:'', display_name:'', gender:'any' },
      company: { name:'', slug:'', plan:'starter' },
      course: {
        title:'', description:'', content_md:'', youtube_url:'',
        pass_score:80, max_attempts:3, xp_reward:50,
        questions: [] // интерактивный билдер
      },
      store:   { type:'skin', title:'', cost_coins:0, min_level:1, stock:null, payload:'' },
      avatar:  { slot:'', key:'', gender:'any', min_level:1, asset_url:'' },
      ach:     { code:'', title:'', points:50, rarity:'common', description:'' },
      contest: { title:'', start_at:'', end_at:'', prize:'', min_rating:0, is_company_only:false },
    },

    // --------- LIFECYCLE ---------
    async init() {
      await this.loadSection();
    },

    // --------- НАВИГАЦИЯ / СЕКЦИИ ---------
    async loadSection(){
      switch(this.section){
        case 'users':       await this.loadUsers(); break;
        case 'companies':   await this.loadCompanies(); break;
        case 'courses':     await this.loadCourses(); break;
        case 'store':       await this.loadStore(); break;
        case 'avatars':     await this.loadAvatarItems(); break;
        case 'achievements':await this.loadAchievements(); break;
        case 'contests':    await this.loadContests(); break;
        case 'audit':       await this.loadAudit(); break;
        case 'events':      await this.loadEvents(); break;
      }
    },
    async sync(){ await this.loadSection(); },

    // --------- USERS ----------
    async loadUsers(){
      const params = new URLSearchParams();
      if(this.filters.userEmail) params.set('email', this.filters.userEmail);
      if(this.filters.userName)  params.set('name', this.filters.userName);
      const r = await fetch('/api/admin/users?'+params.toString());
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.users = j.users || [];
    },
    openUser(id){
      Alpine.store('toasts')?.push({title:'Открыть юзера', text:`ID ${id}`, emoji:'👤'});
    },
    async removeUser(id){
      if(!confirm('Удалить пользователя #' + id + '?')) return;
      const r = await fetch('/api/admin/users/'+id,{method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.users = this.users.filter(u=>u.id!==id);
      Alpine.store('toasts')?.push({title:'ОК', text:'Пользователь удалён', emoji:'🗑️'});
    },

    // --------- COMPANIES ----------
    async loadCompanies(){
      const r = await fetch('/api/admin/companies');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.companies = j.companies || [];
    },
    async regenJoin(id){
      const r = await fetch(`/api/admin/companies/${id}/regen_code`, {method:'POST'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.companies = this.companies.map(c=> c.id===id ? j.company : c);
      Alpine.store('toasts')?.push({title:'Готово', text:'Код регенерирован', emoji:'🔑'});
    },
    async removeCompany(id){
      if(!confirm('Удалить компанию #' + id + '?')) return;
      const r = await fetch('/api/admin/companies/'+id,{method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.companies = this.companies.filter(c=>c.id!==id);
      Alpine.store('toasts')?.push({title:'ОК', text:'Компания удалена', emoji:'🗑️'});
    },
    async assignCoursePrompt(companyId){
      const cid = prompt('ID курса для назначения компании #' + companyId + ':');
      if(!cid) return;
      const r = await fetch(`/api/admin/companies/${companyId}/assign_course`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({course_id: Number(cid)})
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      Alpine.store('toasts')?.push({title:'ОК', text:'Курс назначен', emoji:'🎓'});
    },

    // --------- COURSES ----------
    async loadCourses(){
      const r = await fetch('/api/admin/training/courses');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.courses = j.courses || [];
    },
    async editCourse(id){
      const title = prompt('Новое название (пусто — без изменений):');
      const payload = {};
      if(title) payload.title = title;
      if(Object.keys(payload).length===0) return;
      const r = await fetch(`/api/admin/training/courses/${id}`, {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadCourses();
      Alpine.store('toasts')?.push({title:'ОК', text:'Курс обновлён', emoji:'✏️'});
    },
    async deleteCourse(id){
      if(!confirm('Удалить курс #' + id + '?')) return;
      const r = await fetch('/api/admin/training/courses/'+id,{method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadCourses();
      Alpine.store('toasts')?.push({title:'ОК', text:'Курс удалён', emoji:'🗑️'});
    },

    // --------- STORE ----------
    async loadStore(){
      const r = await fetch('/api/admin/store_items');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.store = j.items || [];
    },
    editStoreItem(i){
      const title = prompt('Название', i.title);
      if(title==null) return;
      const cost = Number(prompt('Цена (coins)', i.cost_coins));
      const minl = Number(prompt('Мин.уровень', i.min_level));
      const rbody = { title, cost_coins: cost, min_level: minl };
      fetch('/api/admin/store_items/'+i.id, {
        method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(rbody)
      })
        .then(r=>r.json()).then(async j=>{
          if(j.error) return this.err(j);
          await this.loadStore();
          Alpine.store('toasts')?.push({title:'ОК', text:'Товар обновлён', emoji:'✏️'});
        });
    },
    async deleteStoreItem(id){
      if(!confirm('Удалить товар #' + id + '?')) return;
      const r = await fetch('/api/admin/store_items/'+id, {method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadStore();
      Alpine.store('toasts')?.push({title:'ОК', text:'Товар удалён', emoji:'🗑️'});
    },

    // --------- AVATARS ----------
    async loadAvatarItems(){
      const r = await fetch('/api/admin/avatar_items');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.avatarItems = j.items || [];
    },
    async deleteAvatarItem(id){
      if(!confirm('Удалить ассет #' + id + '?')) return;
      const r = await fetch('/api/admin/avatar_items/'+id, {method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadAvatarItems();
      Alpine.store('toasts')?.push({title:'ОК', text:'Ассет удалён', emoji:'🧩'});
    },

    // --------- ACHIEVEMENTS ----------
    async loadAchievements(){
      const r = await fetch('/api/admin/achievements');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.achievements = j.achievements || [];
    },
    async deleteAchievement(id){
      if(!confirm('Удалить ачивку #' + id + '?')) return;
      const r = await fetch('/api/admin/achievements/'+id, {method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadAchievements();
      Alpine.store('toasts')?.push({title:'ОК', text:'Ачивка удалена', emoji:'🏆'});
    },

    // --------- CONTESTS ----------
    async loadContests(){
      const r = await fetch('/api/admin/contests');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.contests = j.contests || [];
    },
    async deleteContest(id){
      if(!confirm('Удалить конкурс #' + id + '?')) return;
      const r = await fetch('/api/admin/contests/'+id, {method:'DELETE'});
      const j = await r.json();
      if(!r.ok) return this.err(j);
      await this.loadContests();
      Alpine.store('toasts')?.push({title:'ОК', text:'Конкурс удалён', emoji:'🥇'});
    },

    // --------- AUDIT / EVENTS ----------
    async loadAudit(){
      const r = await fetch('/api/admin/audit');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.audit = j.audit || [];
    },
    async loadEvents(){
      const params = new URLSearchParams();
      if(this.filters.eventsUserId) params.set('user_id', this.filters.eventsUserId);
      const r = await fetch('/api/admin/score_events?'+params.toString());
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.events = j.events || [];
    },

    // --------- МОДАЛКИ ----------
    openModal(name){
      this.modal = name;
      if (name === 'createCourse') this.ensureCourseInit();
    },
    closeModal(){ this.modal = null; },

    // гарантируем структуру формы курса
    ensureCourseInit() {
      if (!this.forms.course) {
        this.forms.course = {
          title:'', description:'', content_md:'', youtube_url:'',
          pass_score:80, max_attempts:3, xp_reward:50, questions:[]
        };
      }
      if (!Array.isArray(this.forms.course.questions)) this.forms.course.questions = [];
    },

    // --------- БИЛДЕР КВИЗА (ИНТЕРАКТИВ) ----------
    addQuestion(){
      this.ensureCourseInit();
      this.forms.course.questions.push({
        text: '',
        options: [{ text: '', is_correct: false }]
      });
      this.$nextTick(() => {
        const sc = document.getElementById('createCourseScroll');
        if (sc) sc.scrollTo({ top: sc.scrollHeight, behavior: 'smooth' });
      });
    },
    removeQuestion(qIdx){
      this.forms.course.questions.splice(qIdx, 1);
    },
    addOption(qIdx){
      const q = this.forms.course.questions[qIdx];
      if (!Array.isArray(q.options)) q.options = [];
      q.options.push({ text: '', is_correct: false });
    },
    removeOption(qIdx, oIdx){
      const q = this.forms.course.questions[qIdx];
      if (!Array.isArray(q.options)) return;
      q.options.splice(oIdx, 1);
    },

    // --------- CREATE ACTIONS ----------
    async createUser(){
      const r = await fetch('/api/admin/users', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(this.forms.user)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadUsers();
      Alpine.store('toasts')?.push({title:'ОК', text:'Пользователь создан', emoji:'✅'});
      this.forms.user = { email:'', password:'', display_name:'', gender:'any' };
    },

    async createCompany(){
      const r = await fetch('/api/admin/companies', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(this.forms.company)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadCompanies();
      Alpine.store('toasts')?.push({title:'ОК', text:'Компания создана', emoji:'🏢'});
      this.forms.company = { name:'', slug:'', plan:'starter' };
    },

    async createCourse(){
      try{
        this.ensureCourseInit();

        const payload = {
          title: (this.forms.course.title || '').trim(),
          description: this.forms.course.description || '',
          content_md: this.forms.course.content_md || '',
          youtube_url: this.forms.course.youtube_url || '',
          pass_score: Number(this.forms.course.pass_score) || 80,
          max_attempts: Number(this.forms.course.max_attempts) || 3,
          xp_reward: Number(this.forms.course.xp_reward) || 50,
          scope: 'global',
          questions: (this.forms.course.questions || []).map(q => ({
            text: (q.text || '').trim(),
            options: (q.options || []).map(o => ({
              text: (o.text || '').trim(),
              is_correct: !!o.is_correct
            }))
          }))
        };

        const r = await fetch(CREATE_COURSE_URL, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        const j = await r.json();
        if(!r.ok) throw new Error(j.description || 'Не удалось создать курс');

        Alpine.store('toasts')?.push({ title:'Курс создан', text: payload.title, emoji:'🎓' });
        this.closeModal();
        this.forms.course = {
          title:'', description:'', content_md:'', youtube_url:'',
          pass_score:80, max_attempts:3, xp_reward:50, questions:[]
        };
        await this.loadCourses();
      }catch(e){
        this.err({ description: e.message || String(e) });
      }
    },

    async createStoreItem(){
      const d = this.forms.store;
      let payload = null;
      try{ payload = d.payload ? JSON.parse(d.payload) : null; }catch(_){ payload = null; }
      const body = {
        type:d.type, title:d.title,
        cost_coins:Number(d.cost_coins)||0,
        min_level:Number(d.min_level)||1,
        stock: d.stock===''? null: Number(d.stock),
        payload
      };
      const r = await fetch('/api/admin/store_items', {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadStore();
      Alpine.store('toasts')?.push({title:'ОК', text:'Товар создан', emoji:'🛍️'});
      this.forms.store = { type:'skin', title:'', cost_coins:0, min_level:1, stock:null, payload:'' };
    },

    async createAvatarItem(){
      const r = await fetch('/api/admin/avatar_items', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(this.forms.avatar)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadAvatarItems();
      Alpine.store('toasts')?.push({title:'ОК', text:'Ассет добавлен', emoji:'🧩'});
      this.forms.avatar = { slot:'', key:'', gender:'any', min_level:1, asset_url:'' };
    },

    async createAchievement(){
      const r = await fetch('/api/admin/achievements', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(this.forms.ach)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadAchievements();
      Alpine.store('toasts')?.push({title:'ОК', text:'Ачивка создана', emoji:'🏆'});
      this.forms.ach = { code:'', title:'', points:50, rarity:'common', description:'' };
    },

    async createContest(){
      const d = this.forms.contest;
      const startISO = d.start_at ? new Date(d.start_at).toISOString() : new Date().toISOString();
      const endISO   = d.end_at   ? new Date(d.end_at).toISOString()   : new Date(Date.now()+7*864e5).toISOString();
      const body = {
        title:d.title, start_at:startISO, end_at:endISO,
        prize:d.prize||null,
        min_rating: d.min_rating? Number(d.min_rating): null,
        is_company_only: !!d.is_company_only
      };
      const r = await fetch('/api/admin/contests', {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
      });
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.closeModal(); await this.loadContests();
      Alpine.store('toasts')?.push({title:'ОК', text:'Конкурс создан', emoji:'🥇'});
      this.forms.contest = { title:'', start_at:'', end_at:'', prize:'', min_rating:0, is_company_only:false };
    },

    // --------- HELPERS ----------
    err(j){
      const msg = j && (j.description || j.error || JSON.stringify(j)) || 'Ошибка';
      Alpine.store('toasts')?.push({title:'Ошибка', text: msg, emoji:'⚠️'});
    },
  };
};

// Stores и регистрация происходят при инициализации Alpine
document.addEventListener('alpine:init', () => {
  // Toasts Store
  if (!Alpine.store('toasts')) {
    Alpine.store('toasts', {
      _id: 1,
      items: [],
      push(t) {
        const id = this._id++;
        this.items.push({ id, show: true, title: t.title || '', text: t.text || '', emoji: t.emoji || '✨' });
        setTimeout(() => this.dismiss(id), 4000);
      },
      dismiss(id) {
        const it = this.items.find(x => x.id === id);
        if (!it) return;
        it.show = false;
        setTimeout(() => { this.items = this.items.filter(x => x.id !== id); }, 200);
      }
    });
  }

  // FX Store (не обязателен, но пригодится)
  if (!Alpine.store('fx')) {
    Alpine.store('fx', {
      confetti() {
        const cvs = document.getElementById('confetti');
        if (!cvs) return;
        const ctx = cvs.getContext('2d');
        const W = cvs.width = window.innerWidth;
        const H = cvs.height = window.innerHeight;
        const N = 160, parts = Array.from({ length: N }, () => ({
          x: Math.random() * W,
          y: -10,
          dx: -1 + Math.random() * 2,
          dy: 1 + Math.random() * 3,
          r: 1.5 + Math.random() * 2.5
        }));
        let t = 120;
        (function frame() {
          ctx.clearRect(0, 0, W, H);
          parts.forEach(p => {
            ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
            p.x += p.dx; p.y += p.dy;
          });
          if (t-- > 0) requestAnimationFrame(frame); else ctx.clearRect(0, 0, W, H);
        })();
      }
    });
  }
});
