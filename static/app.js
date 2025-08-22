
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

// Кнопка с состоянием загрузки: <button x-data="loadBtn()" @click="run(save)">
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

// --- Toasts (правый верх) и показ непрочитанных уведомлений ---
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
    box.style.background = 'rgba(15,23,42,0.92)'; // slate-900/90
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

  async function notifyUnread() {
    try {
      const r = await fetch('/api/notifications?unread_only=1');
      const j = await r.json();
      const items = Array.isArray(j.notifications) ? j.notifications : [];
      if (!items.length) return;
      // показываем как «ачивки»: заголовок + текст
      items.forEach(n => {
        pushToast({ title: n.title || 'Уведомление', text: n.body || '' });
      });
      // пометить прочитанными
      await fetch('/api/notifications/read', { method: 'POST' });
    } catch (e) {
      console.warn('notifyUnread failed', e);
    }
  }

  // Автозапуск при загрузке страницы
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', notifyUnread);
  } else {
    notifyUnread();
  }

  // Экспорт на всякий случай
  window.SJ = window.SJ || {};
  window.SJ.notifyUnread = notifyUnread;
})();

// ====== Reports Drawer (Панель отчётов) ======
(function () {
  // Работает на странице партнёра/компании. Требуется SJ_COMPANY_ID.
  var companyId = (typeof window.SJ_COMPANY_ID !== 'undefined') ? window.SJ_COMPANY_ID : null;
  if (!companyId) return;

  // Создаём плавающую кнопку "Отчёты"
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

  // Рисуем drawer справа
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
      background: '#0B1220', // почти slate-950
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
    // по умолчанию — submitted
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
        const actions = wrap.querySelector('[data-actions]');
        const btnApprove = wrap.querySelector('[data-approve]');
        const btnReject  = wrap.querySelector('[data-reject]');

        // Прячем/блокируем кнопки по статусу
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
      // /api/partners/company/<company_id>/tasks/<task_id>/review  body: {user_id, approve}
      const res = await fetch(`/api/partners/company/${companyId}/tasks/${row.task_id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: row.user_id, approve: !!approve })
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j && j.description || 'Request failed');

      // Обновляем UI
      const status = approve ? 'approved' : 'rejected';
      row.status = status;

      const pill = wrapEl.querySelector('.sj-pill');
      pill.className = 'sj-pill ' + status;
      pill.textContent = status.toUpperCase();

      const btnApprove = wrapEl.querySelector('[data-approve]');
      const btnReject  = wrapEl.querySelector('[data-reject]');
      if (approve) btnApprove.setAttribute('disabled','disabled');
      else btnReject.setAttribute('disabled','disabled');

      // тост
      if (window.SJ && typeof window.SJ.notifyUnread === 'function') {
        // уведомления пользователю создаёт сервер — наши тосты покажутся при их первом заходе
      }
      // локальный тост для ревьюера:
      try {
        // использую ранее добавленный пуш-тост, если присутствует
        if (window.SJ && window.SJ.notifyUnread) {
          // ничего не делаем — notifyUnread триггерится на вход
        }
        // внутренний лёгкий тост:
        if (typeof pushToast === 'function') {
          pushToast({ title: approve ? 'Зачтено' : 'Отклонено', text: row.task_title || '' });
        }
      } catch (_) {}
    } catch (e) {
      console.warn('review error', e);
      // fallback сообщение
      alert('Не удалось выполнить действие: ' + (e && e.message ? e.message : 'ошибка'));
    }
  }

  createFab();
})();
