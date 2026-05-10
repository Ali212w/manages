# manages — Frontend Redesign (najm2 look & feel)

This is the **same Flask backend you sent**, with the frontend visually
re-skinned to match `najm2-frontend` (Tailwind / shadcn / Alpine.js look).

> **Backend is 100 % untouched.** No route, model, service, blueprint,
> migration, schema, API, i18n key, CSRF or `url_for()` was modified.
> Only templates + CSS + a small Alpine.js app file were added/edited.

---

## What changed

### New files
| File | Purpose |
|---|---|
| `app/static/css/najm2.css` (~2 437 lines) | Full design system — HSL tokens, dark mode via `data-theme="dark"`, sidebar/header/cards/forms/buttons/tables/auth/landing styling. Loaded **last** so its `:root` tokens win. |
| `app/static/js/najm2-app.js` | Tiny vanilla JS for: theme toggle (with `localStorage` + no-FOUC inline bootstrap), sidebar collapse / mobile overlay, sidebar group accordion, dropdowns, copy-to-clipboard. |
| `app/templates/components/_macros.html` | Reusable Jinja2 macros: `button`, `card`, `stat_card`, `badge`, `alert`, `form_field`, `empty_state`, `page_header`. |
| `app/templates/auth_base.html` | New auth shell with decorative orbs + theme toggle. |
| `app/templates/layouts/dashboard_layout.html` | Legacy alias → `layouts/base.html`. |

### Edited files (visual only — same blocks / context)
- `app/templates/base.html` — public/marketing shell, Inline theme bootstrap (no FOUC).
- `app/templates/layouts/base.html` — authenticated app shell (sidebar + header + content).
- `app/templates/partials/{header,sidebar,footer}.html` — modern header (search / theme / lang / notifications / user menu), sidebar (groups, section titles), minimal footer.
- `app/templates/auth/{login,register_company,register_user,forgot-password,reset_password}.html` — fully redesigned auth pages.
- **Section bases turned into 2-line pass-throughs** to the unified shell — propagates the new design to ~240 child templates automatically:
  - `company/base.html`, `employee/base.html`, `platform/base.html`,
    `client/base.html`, `consultant/base.html`, `supplier/base.html`,
    `communication/base_chat.html`, `layouts/auth_base.html`.

### Untouched
Everything in `app/routes/`, `app/models/`, `app/services/`, `app/forms/`,
`app/utils/`, `migrations/`, `translations/`, `config.py`, `run.py`,
`requirements.txt`. **No backend logic changed.**

---

## Design tokens (HSL CSS variables)

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --primary:    221 83% 53%;     /* blue-600 */
  --primary-foreground: 210 40% 98%;
  --accent:     158 64% 40%;     /* emerald-600 */
  --muted:      210 40% 96%;
  --border:     214 32% 91%;
  --ring:       221 83% 53%;
  /* + radius / shadows / spacing tokens */
}
[data-theme="dark"] {
  --background: 222 47% 8%;
  --foreground: 210 40% 98%;
  /* etc. — full dark palette */
}
```

All UI surfaces read from these — flip `data-theme="dark"` and the whole
app re-skins. The theme is auto-bootstrapped from `localStorage` /
`prefers-color-scheme` *before* the first paint (no FOUC).

---

## How to run

The redesign requires **no setup changes**. Run the project the same way you
did before:

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask db upgrade                    # if you have an empty DB
python run.py                       # or: flask run
```

Open <http://localhost:5000>. Click the moon/sun icon in the header to
toggle dark mode.

---

## Verification

Two automated smoke tests were run against the bundle:

1. **Jinja2 parse — all 383 templates: OK, 0 errors.**
2. **Render with stubbed context — 21 key templates** (base layouts +
   header/sidebar/footer + all auth pages + section bases + landing):
   **all OK, 0 errors.**

The visual quality should be checked by booting the app — the templates
themselves are syntactically clean and all `url_for()` / CSRF / i18n
calls were preserved verbatim.

---

## Notes & follow-ups

- A handful of section/feature pages still use the old Bootstrap
  utility classes inside `{% block content %}`. They render fine
  (Bootstrap is still loaded), but for a 100 % visual match you can
  gradually rewrite per-page bodies to use the new design tokens. The
  framework + section bases are already there — incremental work only.
- Heavy 3rd-party libs (DataTables / Select2 / ApexCharts / Flatpickr)
  are still loaded for backward compatibility with existing pages.
