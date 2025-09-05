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
      { key: 'partners',    label: 'Партнёры' },
      { key: 'admins',      label: 'Админы' },
      { key: 'courses',     label: 'Курсы' },
      { key: 'store',       label: 'Магазин' },
      { key: 'avatars',     label: 'Аватары' },
      { key: 'achievements',label: 'Ачивки' },
      { key: 'contests',    label: 'Конкурсы' },
      { key: 'events',      label: 'События' },
      { key: 'onboarding',  label: 'Онбординг (системный)' },
      { key: 'audit',       label: 'Аудит' },
    ],

    users: [],
    companies: [],
    partners: [],
    admins: [],
    courses: [],
    store: [],
    avatarItems: [],
    achievements: [],
    contests: [],
    audit: [],
    events: [],

    filters: { userEmail:'', userName:'', userCompany:'', eventsUserId: '' },

    modal: null,

    selectedUsers: new Set(),
    bulk: { companyId: null, xp: 50, coins: 50 },

    // ------- ЕДИНЫЙ forms (без дубликатов ключа) -------
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
      partner: { email:'', password:'', display_name:'' },
      admin:   { email:'', password:'' },
      contest: { title:'', description:'', start_at:'', end_at:'', prize:'', min_rating:0, max_participants:null, is_company_only:false },
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
        case 'partners':    await this.loadPartners(); break;
        case 'admins':      await this.loadAdmins(); break;
        case 'courses':     await this.loadCourses(); break;
        case 'store':       await this.loadStore(); break;
        case 'avatars':     await this.loadAvatarItems(); break;
        case 'achievements':await this.loadAchievements(); break;
        case 'contests':    await this.loadContests(); break;
        case 'events':      await this.loadEvents(); break;
        case 'onboarding':  await this.loadOnboardingSystem(); break;
        case 'audit':       await this.loadAudit(); break;
      }
    },

    async sync(){ await this.loadSection(); },

    // ===================== USERS =====================
    async loadUsers(){
      const params = new URLSearchParams();
      if(this.filters.userEmail)   params.set('email', this.filters.userEmail);
      if(this.filters.userName)    params.set('name',  this.filters.userName);
      if(this.filters.userCompany) params.set('company', this.filters.userCompany);
      const r = await fetch('/api/admin/users?'+params.toString());
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.users = j.users || [];
      this.selectedUsers.clear();
    },
    clearUserFilters(){ this.filters.userEmail=''; this.filters.userName=''; this.filters.userCompany=''; },
    toggleSelectAll(e){
      if(e.target.checked){ this.users.forEach(u=>this.selectedUsers.add(u.id)); }
      else this.selectedUsers.clear();
    },
    toggleSelectUser(id, e){
      if(e.target.checked) this.selectedUsers.add(id); else this.selectedUsers.delete(id);
    },
    async grantXP(id){
      const val = prompt('Сколько XP начислить?', this.bulk.xp);
      if(!val) return;
      const r = await fetch(`/api/admin/users/${id}/xp`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({amount:+val})});
      const j = await r.json(); if(!r.ok) return this.err(j);
      Alpine.store('toasts')?.push({title:'XP', text:`+${val} XP юзеру #${id}`, emoji:'⚡'});
      await this.loadUsers();
    },
    async grantCoins(id){
      const val = prompt('Сколько coins начислить?', this.bulk.coins);
      if(!val) return;
      const r = await fetch(`/api/admin/users/${id}/coins`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({amount:+val})});
      const j = await r.json(); if(!r.ok) return this.err(j);
      Alpine.store('toasts')?.push({title:'Coins', text:`+${val} монет юзеру #${id}`, emoji:'🪙'});
      await this.loadUsers();
    },
    async bulkGrantXP(){
      const val = prompt('Сколько XP начислить выбранным?', this.bulk.xp);
      if(!val) return;
      for(const id of this.selectedUsers){
        await fetch(`/api/admin/users/${id}/xp`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({amount:+val})});
      }
      Alpine.store('toasts')?.push({title:'Готово', text:`XP выдано ${this.selectedUsers.size} пользователям`, emoji:'✅'});
      await this.loadUsers();
    },
    async bulkGrantCoins(){
      const val = prompt('Сколько coins начислить выбранным?', this.bulk.coins);
      if(!val) return;
      for(const id of this.selectedUsers){
        await fetch(`/api/admin/users/${id}/coins`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({amount:+val})});
      }
      Alpine.store('toasts')?.push({title:'Готово', text:`Coins выданы ${this.selectedUsers.size} пользователям`, emoji:'✅'});
      await this.loadUsers();
    },
    async bulkAssignCompany(){
      if(!this.bulk.companyId) return alert('Укажите company_id');
      for(const id of this.selectedUsers){
        await fetch(`/api/admin/users/${id}/assign_company`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({company_id:+this.bulk.companyId})});
      }
      Alpine.store('toasts')?.push({title:'Готово', text:`Компания назначена ${this.selectedUsers.size} пользователям`, emoji:'🏢'});
      await this.loadUsers();
    },
    async bulkDeleteUsers(){
      if(!confirm(`Удалить ${this.selectedUsers.size} пользователей?`)) return;
      for(const id of this.selectedUsers){
        await fetch(`/api/admin/users/${id}`, {method:'DELETE'});
      }
      Alpine.store('toasts')?.push({title:'Удалены', text:`${this.selectedUsers.size} пользователей`, emoji:'🗑️'});
      await this.loadUsers();
    },
    exportUsersCSV(){
      const rows = [['id','display_name','email','level','xp','coins','company']];
      for(const u of this.users){ rows.push([u.id,u.display_name,u.email,u.level,u.xp,u.coins,(u.company||'')]); }
      const csv = rows.map(r=>r.map(x=>String(x).replaceAll('"','""')).map(x=>`"${x}"`).join(',')).join('\n');
      const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'}); const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href=url; a.download='users.csv'; a.click(); URL.revokeObjectURL(url);
    },
    async importUsersCSV(ev){
      const file = ev.target.files?.[0]; if(!file) return;
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter(Boolean); if(!lines.length) return;
      const header = lines[0].split(',').map(h=>h.replace(/(^"|"$)/g,'').trim());
      const idx = {email: header.indexOf('email'), display_name: header.indexOf('display_name'), password: header.indexOf('password'), gender: header.indexOf('gender')};
      if(idx.email<0 || idx.display_name<0 || idx.password<0) return alert('CSV должен содержать колонки: email, display_name, password [,gender]');
      for(let i=1;i<lines.length;i++){
        const cols = lines[i].split(',').map(c=>c.replace(/(^"|"$)/g,''));
        const payload = { email: cols[idx.email], display_name: cols[idx.display_name], password: cols[idx.password], gender: idx.gender>=0?cols[idx.gender]:null };
        await fetch('/api/admin/users', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
      }
      Alpine.store('toasts')?.push({title:'Импорт', text:'CSV загружен', emoji:'📥'});
      await this.loadUsers();
    },

    // ===================== PARTNERS =====================
    async loadPartners(){
      const r = await fetch('/api/admin/partners'); const j = await r.json(); if(!r.ok) return this.err(j);
      this.partners = j.partners || [];
    },
    async createPartner(){
      const d = this.forms.partner;
      const r = await fetch('/api/admin/partners', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email:d.email, password:d.password, display_name:d.display_name})});
      const j = await r.json(); if(!r.ok) return this.err(j);
      this.forms.partner = {email:'', password:'', display_name:''};
      await this.loadPartners();
      Alpine.store('toasts')?.push({title:'Партнёр', text:'Создан', emoji:'🤝'});
    },
    async deletePartner(id){
      if(!confirm('Удалить партнёра #' + id + '?')) return;
      const r = await fetch('/api/admin/partners/'+id, {method:'DELETE'}); const j = await r.json(); if(!r.ok) return this.err(j);
      await this.loadPartners();
      Alpine.store('toasts')?.push({title:'Партнёр', text:'Удалён', emoji:'🗑️'});
    },

    // ===================== ADMINS =====================
    async loadAdmins(){
      const r = await fetch('/api/admin/admin_users'); const j = await r.json(); if(!r.ok) return this.err(j);
      this.admins = j.admins || [];
    },
    async createAdmin(){
      const d = this.forms.admin;
      const r = await fetch('/api/admin/admin_users', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email:d.email, password:d.password})});
      const j = await r.json(); if(!r.ok) return this.err(j);
      this.forms.admin = {email:'', password:''};
      await this.loadAdmins();
      Alpine.store('toasts')?.push({title:'Админ', text:'Добавлен', emoji:'🛡️'});
    },
    async deleteAdmin(id){
      if(!confirm('Удалить админа #' + id + '?')) return;
      const r = await fetch('/api/admin/admin_users/'+id, {method:'DELETE'}); const j = await r.json(); if(!r.ok) return this.err(j);
      await this.loadAdmins();
      Alpine.store('toasts')?.push({title:'Админ', text:'Удалён', emoji:'🗑️'});
    },

    // ===================== System Onboarding (SJ default) =====================
    onbSysSteps: [],
    async loadOnboardingSystem(){
      const r = await fetch('/api/admin/onboarding/system_default/steps');
      const j = await r.json();
      if(!r.ok) return this.err(j);
      this.onbSysSteps = j.steps || [];
    },
    moveUp(id){
      const i = this.onbSysSteps.findIndex(s=>s.id===id); if(i>0){ const tmp=this.onbSysSteps[i-1]; this.onbSysSteps[i-1]=this.onbSysSteps[i]; this.onbSysSteps[i]=tmp; }
    },
    moveDown(id){
      const i = this.onbSysSteps.findIndex(s=>s.id===id); if(i>=0 && i<this.onbSysSteps.length-1){ const tmp=this.onbSysSteps[i+1]; this.onbSysSteps[i+1]=this.onbSysSteps[i]; this.onbSysSteps[i]=tmp; }
    },
    async reorderDefaultSteps(){
      // локально проставим order_index
      this.onbSysSteps = this.onbSysSteps.map((s,idx)=>({...s, order_index: idx+1}));
      const order = this.onbSysSteps.map(s=>s.id);
      const r = await fetch('/api/admin/onboarding/system_default/steps', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ op:'reorder', order })
      });
      const j = await r.json().catch(()=>({}));
      if(!r.ok) return this.err(j);
      Alpine.store('toasts')?.push({title:'ОК', text:'Порядок сохранён', emoji:'✅'});
    },
    async createDefaultStep(){
      const payload = { op:'create', type:'intro_page', title:'Новый шаг', order_index: (this.onbSysSteps?.length||0)+1, is_required:false, coins_award:0, xp_award:0 };
      const r = await fetch('/api/admin/onboarding/system_default/steps', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await r.json().catch(()=>({}));
      if(!r.ok) return this.err(j);
      Alpine.store('toasts')?.push({title:'ОК', text:'Шаг создан', emoji:'🧩'});
      await this.loadOnboardingSystem();
    },
    async deleteDefaultStep(id){
      const r = await fetch('/api/admin/onboarding/system_default/steps', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ op:'delete', id })
      });
      const j = await r.json().catch(()=>({}));
      if(!r.ok) return this.err(j);
      await this.loadOnboardingSystem();
    },

    // ===================== COMPANIES =====================
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

    // ===================== COURSES =====================
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

    // ===================== STORE =====================
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

    // ===================== AVATARS =====================
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

    // ===================== ACHIEVEMENTS =====================
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

    // ===================== CONTESTS =====================
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

    // ХЕЛПЕР: превращает 'YYYY-MM-DDTHH:mm' (или Date) в 'YYYY-MM-DDTHH:mm:ss±hh:mm'
toIsoWithOffset(input){
  // уже ISO с Z/offset — оставляем как есть
  if (typeof input === 'string' && /Z$|[+-]\d{2}:\d{2}$/.test(input)) return input;

  let dt;
  if (input instanceof Date) {
    dt = new Date(input.getTime());
  } else if (typeof input === 'string' && input) {
    // поддержка 'YYYY-MM-DDTHH:mm' и 'YYYY-MM-DDTHH:mm:ss'
    const [d, t='00:00'] = input.split('T');
    const [Y,M,D] = d.split('-').map(Number);
    const [h,m,s='00'] = t.split(':').map(Number);
    dt = new Date(Y, (M||1)-1, D||1, h||0, m||0, s||0);
  } else {
    dt = new Date();
  }

  const pad = (n)=> String(n).padStart(2,'0');
  const Y = dt.getFullYear();
  const M = pad(dt.getMonth()+1);
  const D = pad(dt.getDate());
  const h = pad(dt.getHours());
  const m = pad(dt.getMinutes());
  const s = pad(dt.getSeconds());

  // смещение «восток = +», getTimezoneOffset возвращает минуты ЗАПАД от UTC (поэтому ставим минус)
  const offMin = -dt.getTimezoneOffset();
  const sign = offMin >= 0 ? '+' : '-';
  const abs = Math.abs(offMin);
  const oh = pad(Math.floor(abs/60));
  const om = pad(abs%60);

  return `${Y}-${M}-${D}T${h}:${m}:${s}${sign}${oh}:${om}`;
},

async createContest(){
  const d = this.forms.contest;

  const startISO = d.start_at ? this.toIsoWithOffset(d.start_at) : this.toIsoWithOffset(new Date());
  const endISO   = d.end_at
    ? this.toIsoWithOffset(d.end_at)
    : this.toIsoWithOffset(new Date(Date.now()+7*864e5)); // +7 дней по локали

  const body = {
    title: d.title,
    start_at: startISO,
    end_at: endISO,
    prize: d.prize || null,
    min_rating: d.min_rating ? Number(d.min_rating) : null,
    max_participants: d.max_participants ? Number(d.max_participants) : null,
    is_company_only: !!d.is_company_only
  };

  const r = await fetch('/api/admin/contests', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  const j = await r.json();
  if(!r.ok) return this.err(j);

  // загрузка изображения приза (как было)
  const img = this.$refs?.contestPrizeImage?.files?.[0];
  if (img && j?.contest?.id){
    const fd = new FormData();
    fd.append('image', img);
    const up = await fetch(`/api/admin/contests/${j.contest.id}/prize_image`, { method:'POST', body: fd });
    const uj = await up.json(); if(!up.ok) return this.err(uj);
  }

  this.closeModal(); await this.loadContests();
  Alpine.store('toasts')?.push({title:'ОК', text:'Конкурс создан', emoji:'🥇'});
  this.forms.contest = { title:'', start_at:'', end_at:'', prize:'', min_rating:0, max_participants:null, is_company_only:false };
},

    // ===================== AUDIT / EVENTS =====================
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

    // ===================== МОДАЛКИ =====================
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

    // ===================== БИЛДЕР КВИЗА =====================
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

    // ===================== CREATE ACTIONS =====================
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

    // --------- HELPERS ----------
    err(j){
      const msg = j && (j.description || j.error || JSON.stringify(j)) || 'Ошибка';
      console.error('Admin error:', j);
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

  // FX Store (опц.)
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
