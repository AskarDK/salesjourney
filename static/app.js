(function () {
  function mountStores() {
    // --- TOASTS ---
    const toasts = {
      _id: 1,
      items: [],
      push(t) {
        const id = this._id++;
        this.items.push({
          id,
          show: true,
          title: t.title || '',
          text: t.text || '',
          emoji: t.emoji || '✨'
        });
        setTimeout(() => this.dismiss(id), 4000);
      },
      dismiss(id) {
        const it = this.items.find(x => x.id === id);
        if (!it) return;
        it.show = false;
        setTimeout(() => {
          this.items = this.items.filter(x => x.id !== id);
        }, 200);
      }
    };

    // --- FX ---
    const fx = {
      confetti() {
        const c = document.getElementById('confetti');
        if (!c) return;
        const ctx = c.getContext('2d');
        const W = (c.width = window.innerWidth);
        const H = (c.height = window.innerHeight);
        const N = 160;
        const parts = Array.from({ length: N }, () => ({
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
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
            p.x += p.dx;
            p.y += p.dy;
          });
          if (t-- > 0) requestAnimationFrame(frame);
          else ctx.clearRect(0, 0, W, H);
        })();
      },
      coins() {
        if (window.Alpine?.store('toasts')) {
          Alpine.store('toasts').push({ title: '+XP', text: 'Начислены очки', emoji: '🪙' });
        }
      }
    };

    Alpine.store('toasts', toasts);
    Alpine.store('fx', fx);
  }

  // монтируем сторы независимо от порядка загрузки Alpine
  if (window.Alpine) {
    mountStores();
  } else {
    document.addEventListener('alpine:init', mountStores, { once: true });
  }
})();

// static/app.js
window.addEventListener('alpine:init', () => {
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
      const P = Array.from({length:N}, ()=>({
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
});

function partnerCompanyPage(companyId) {
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

    // --- вкладки/кнопки в правой колонке и левой части (чтобы Alpine-переменные существовали)
    tab: 'feed',
tabBtn(kind){
  return `px-3 py-1 rounded-lg border ${this.tab===kind ? 'bg-white/10 border-white/20' : 'border-white/10 hover:bg-white/5'}`;
},

    // --- лента компании
    canPost: false,        // выставь true по своей логике прав
    newPost: '',
    newPostPreview: '',
    newPinned: false,
    feed: [],

    // --- задачи компании
    canCreateTasks: false, // выставь true по своей логике прав
    tasks: [],
    taskModal: {
      open: false,
      mode: 'create', // 'create' | 'edit'
      form: {
        id: null,
        title: '',
        description: '',
        points_xp: 0,
        coins: 0,
        priority: 'normal',     // 'low' | 'normal' | 'high'
        require_proof: false,
        _due_date: '',          // строка даты для инпута
        reward_achievement_id: null,
      },
      members: [],
      selectedIds: [],
      query: '',
    },

async init() {
  try {
    if (!this.companyId) return; // <- чтобы не было запроса /dashboard с null
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

    // --- заглушки (если шаблон уже вызывает эти методы — чтобы не падал)
    async loadFeed(){ /* наполни feed */ },
    async loadTasks(){ /* наполни tasks */ },
    async checkCanPost(){ return false; },
    async checkCanCreateTasks(){ return false; },
  }
}
