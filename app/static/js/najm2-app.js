/* ============================================================
   najm2-app.js — Frontend behavior for the redesigned UI
   Provides: theme toggle, sidebar toggle, toast helpers,
             dropdowns/modal compatibility (via Bootstrap JS),
             Alpine helpers (registered if Alpine present)
   No jQuery required, but compatible if jQuery is loaded.
   ============================================================ */

(function () {
  'use strict';

  // ---------------------------------------------------------------
  // 1. THEME (light / dark)
  // ---------------------------------------------------------------
  const THEME_KEY = 'najm2-theme';

  function getTheme() {
    return localStorage.getItem(THEME_KEY)
      || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }

  function applyTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem(THEME_KEY, theme);
    // update icon
    document.querySelectorAll('[data-theme-icon]').forEach(el => {
      el.classList.toggle('fa-moon', theme === 'light');
      el.classList.toggle('fa-sun', theme === 'dark');
    });
  }

  function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  // initialize on load (before first paint to avoid FOUC)
  applyTheme(getTheme());

  window.najm2 = window.najm2 || {};
  window.najm2.toggleTheme = toggleTheme;
  window.najm2.applyTheme = applyTheme;

  // ---------------------------------------------------------------
  // 2. SIDEBAR (mobile open/close + collapse)
  // ---------------------------------------------------------------
  function openSidebar() {
    const s = document.querySelector('.app-sidebar');
    const o = document.querySelector('.sidebar-overlay');
    if (s) s.classList.add('open');
    if (o) o.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    const s = document.querySelector('.app-sidebar');
    const o = document.querySelector('.sidebar-overlay');
    if (s) s.classList.remove('open');
    if (o) o.classList.remove('open');
    document.body.style.overflow = '';
  }

  function toggleSidebar() {
    const s = document.querySelector('.app-sidebar');
    if (!s) return;
    s.classList.contains('open') ? closeSidebar() : openSidebar();
  }

  window.najm2.openSidebar = openSidebar;
  window.najm2.closeSidebar = closeSidebar;
  window.najm2.toggleSidebar = toggleSidebar;

  // ---------------------------------------------------------------
  // 3. TOAST helpers
  // ---------------------------------------------------------------
  function ensureToastStack() {
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(message, type) {
    type = type || 'info';
    const icons = {
      success: 'check-circle',
      error: 'times-circle',
      warning: 'exclamation-triangle',
      info: 'info-circle'
    };
    const stack = ensureToastStack();
    const t = document.createElement('div');
    t.className = 'toast';
    t.innerHTML =
      '<i class="toast-icon ' + type + ' fas fa-' + (icons[type] || 'info-circle') + '"></i>' +
      '<div class="flex-1">' +
        '<div class="toast-title">' + (typeof message === 'string' ? message : message.title || '') + '</div>' +
        (message.description ? '<div class="toast-message">' + message.description + '</div>' : '') +
      '</div>';
    stack.appendChild(t);
    setTimeout(() => {
      t.style.opacity = '0';
      t.style.transform = 'translateY(-8px)';
      t.style.transition = 'all 200ms';
      setTimeout(() => t.remove(), 220);
    }, 4200);
  }

  window.najm2.toast = toast;

  // back-compat with toastr.* calls used in legacy templates
  if (!window.toastr) {
    window.toastr = {
      success: (m) => toast(m, 'success'),
      error: (m) => toast(m, 'error'),
      warning: (m) => toast(m, 'warning'),
      info: (m) => toast(m, 'info'),
      options: {}
    };
  }

  // ---------------------------------------------------------------
  // 4. AUTO-DISMISS FLASH alerts
  // ---------------------------------------------------------------
  function autoDismissAlerts() {
    document.querySelectorAll('.alert.alert-dismissible').forEach(alert => {
      if (alert.dataset.persist) return;
      setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transition = 'opacity 250ms';
        setTimeout(() => alert.remove(), 280);
      }, 5000);
    });
    // close buttons
    document.querySelectorAll('.alert .btn-close').forEach(btn => {
      btn.addEventListener('click', () => btn.closest('.alert')?.remove());
    });
  }

  // ---------------------------------------------------------------
  // 5. SIDEBAR group toggles (collapsible nav sections)
  // ---------------------------------------------------------------
  function initSidebarGroups() {
    document.querySelectorAll('.sidebar-group-toggle').forEach(toggle => {
      toggle.addEventListener('click', (e) => {
        e.preventDefault();
        const group = toggle.closest('.sidebar-group');
        if (group) group.classList.toggle('open');
      });
    });
  }

  // ---------------------------------------------------------------
  // 6. INIT after DOM ready
  // ---------------------------------------------------------------
  function init() {
    // Theme toggle button
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });
    // Sidebar toggle button
    document.querySelectorAll('[data-sidebar-toggle]').forEach(btn => {
      btn.addEventListener('click', toggleSidebar);
    });
    // Sidebar overlay click closes
    document.querySelectorAll('.sidebar-overlay').forEach(o => {
      o.addEventListener('click', closeSidebar);
    });
    // Close sidebar when nav link clicked on mobile
    document.querySelectorAll('.app-sidebar .sidebar-link').forEach(l => {
      l.addEventListener('click', () => {
        if (window.matchMedia('(max-width: 1024px)').matches) {
          closeSidebar();
        }
      });
    });

    initSidebarGroups();
    autoDismissAlerts();

    // mark active sidebar link based on current path
    const path = window.location.pathname;
    document.querySelectorAll('.app-sidebar a[href]').forEach(link => {
      const href = link.getAttribute('href');
      if (!href || href === '#' || href === '/') return;
      if (path === href || path.startsWith(href + '/')) {
        link.classList.add('active');
        const grp = link.closest('.sidebar-group');
        if (grp) grp.classList.add('open');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ---------------------------------------------------------------
  // 7. Optional Alpine.js component registrations
  // ---------------------------------------------------------------
  document.addEventListener('alpine:init', () => {
    if (!window.Alpine) return;
    window.Alpine.data('dropdown', () => ({
      open: false,
      toggle() { this.open = !this.open; },
      close() { this.open = false; }
    }));
    window.Alpine.data('tabs', (initial) => ({
      active: initial || 0,
      set(i) { this.active = i; },
      is(i) { return this.active === i; }
    }));
    window.Alpine.data('passwordToggle', () => ({
      visible: false,
      toggle() { this.visible = !this.visible; }
    }));
  });

})();
