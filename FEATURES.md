# Expense Tracker — Features & Guide

A personal expense tracking web app for Bangladeshi users with LLM-powered auto-categorization, natural language Q&A, receipt scanning, voice input, budget management, and spending forecasts. Supports English, Bengali, and Banglish.

---

## Tech Stack

| Layer          | Technology                                                    |
|----------------|---------------------------------------------------------------|
| Backend        | Python Flask 3.x                                              |
| Database       | PostgreSQL (Neon) / SQLite (local) via SQLAlchemy             |
| AI / LLM       | Groq (`llama-3.1-8b-instant`, `llama-4-scout-17b-16e-instruct`, `whisper-large-v3-turbo`), Gemini 2.0 Flash (fallback) |
| Frontend       | HTML + CSS + Vanilla JS + Chart.js                            |
| Auth           | Session-based (werkzeug password hashing)                     |
| Push           | Web Push API via `pywebpush` + VAPID                          |
| Export         | CSV, XLSX (`openpyxl`), PDF (`fpdf2`)                         |
| Hosting        | Render (Free) + Neon PostgreSQL                               |

---

## Quick Start

```bash
git clone <repo-url>
cd expense-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Required: at least one AI provider
export GROQ_API_KEY="gsk_..."
# OR for fallback:
export GEMINI_API_KEY="AIza..."

# Optional
export SECRET_KEY="random-secret"
export APP_USERNAME="admin"
export APP_PASSWORD="admin123"

python app.py
# → http://localhost:5000
# Uses SQLite locally (no DATABASE_URL needed)
```

---

## Features

### 1. Expense Management

Add, edit, delete, and view expenses with full CRUD support.

- **Quick Add** — Type a description like `rickshaw 50 tk` or `মুরগি ২২০ টাকা` and the AI extracts category + amount automatically
- **Bulk Add** — Confirm split items from the AI Chat to save multiple expenses at once
- **Edit in-place** — Tap any expense row to edit description, amount, category, or date
- **Delete** — Swipe or tap delete on any expense
- **Date picker** — Browse expenses by specific date, month, or year
- **Search** — Full-text search across descriptions

**API endpoints:**
- `POST /api/add_expense` — add a single expense
- `POST /api/expenses/bulk` — add multiple expenses at once
- `DELETE /api/delete_expense/<id>` — delete an expense
- `GET /api/expenses/<date>` — list expenses for a date
- `GET /api/expenses/month` — list expenses grouped by month
- `GET /api/expenses/monthly-totals` — aggregate totals per month
- `GET /api/expenses/category-totals` — totals by category for a month
- `GET /api/expenses/category-breakdown` — paginated expenses for a specific category + month

### 2. Natural Language Input (AI-Powered)

Type expenses in everyday language — the system extracts category and amount using a **two-tier approach**:

1. **Learned categories** — If you've previously corrected a keyword (e.g., `murgi → Food`), that mapping takes immediate effect via `check_learned()` (no API call)
2. **Groq LLM** (`llama-3.1-8b-instant`) — Sends the description to the LLM with a structured prompt that knows:
   - 17 categories (Food, Transport, Shopping, Bills, Entertainment, Health, Education, Rent, Dining Out, Fruits, Groceries, Travel, Personal Care, Gifts, Investment, Savings, Other)
   - Bengali/Banglish vocabulary for vegetables, meats, fruits, dining
   - Bengali numeral recognition (১→1, ২→2, etc.)
3. **Keyword fallback** — If API is unavailable, falls back to `keyword_category()` — a 16-category regex keyword matcher with 500+ Bangla/Banglish keywords

**API endpoint:**
- `POST /api/predict_expense` — predict category + amount from description

### 3. Voice Input

Record audio directly in the browser and transcribe it to text.

- Uses the **MediaStream Recording API** in the browser
- Sends audio blob to `POST /api/transcribe`
- Backend uses **Groq Whisper** (`whisper-large-v3-turbo`) for transcription
- Transcribed text is then parsed through the expense extraction pipeline

**API endpoint:**
- `POST /api/transcribe` — upload audio file, returns transcribed text

### 4. Receipt Scanning

Take a photo of a receipt or upload from the gallery; the system extracts line items, totals, store name, and date.

**Pipeline:**
1. **Client-side compression** — Image resized to 1200px max, 70% JPEG quality before upload
2. **Primary: Groq Vision** (`meta-llama/llama-4-scout-17b-16e-instruct` → falls back to `llama-3.2-11b-vision-preview`) — Extracts structured JSON with items, store, and date
3. **Fallback: Gemini 2.0 Flash** — If both Groq vision models fail, tries Gemini
4. **Local categorization** — Each item is categorized using `keyword_category()` (no extra API calls — avoids rate limits)
5. **Editable preview** — Extracted items appear in the chat card with editable description, amount, and date fields

**API endpoint:**
- `POST /api/scan_receipt` — upload receipt image, returns `{store, date, items: [{description, amount, category}]}`

### 5. AI Chat (Ask AI)

A ChatGPT-style interface for expense-related questions and actions.

**What it can do:**

| Intent | Detection | Action |
|--------|-----------|--------|
| **Log expense** | `is_question()` returns `False` | Extracts expense via `predict_expense()`, shows editable preview, user confirms to save |
| **Set budget** | `detect_budget_intent()` regex patterns | Calls `POST /api/budgets/set` with category + amount |
| **Ask question** | `is_question()` returns `True` | Routes through the Q&A pipeline |
| **Split expense** | `split_expenses()` via LLM | Splits "gorur mangsho 500 ar mach 300" into individual items |

**Q&A Pipeline (`_run_qa_pipeline()`):**
1. **Date extraction** — `extract_date_reference()` parses "yesterday", "goto mashe", "ajke", "last week", "25 tarikhe", etc.
2. **Question decomposition** — `decompose_question()` breaks compound questions ("how much on food and what was my biggest transport expense?") into sub-questions
3. **SQL generation** — `generate_sql()` asks Groq to produce a SQL query from the NL question, using the live DB schema
4. **SQL correction** — If the first query fails, `correct_sql()` asks Groq to fix the error
5. **SQL safety** — `_validate_sql()` rejects anything that isn't SELECT, contains `--`/`/*`/`DROP`/`DELETE`/etc.
6. **Format answer** — `format_answer()` generates a programmatic answer dict (text + type + metadata) without an LLM call
7. **LLM answer** (fallback) — `answer_from_results()` asks Groq to write a natural-language answer from the SQL results

**Date reference patterns supported:**
- English: `yesterday`, `today`, `last week`, `this month`, `N days ago`, `last Monday`
- Banglish: `kalke`, `ajke`, `goto mash`, `ei shoptaho`, `25 tarikhe`, `koyekdin age`
- Bengali: `গতকাল`, `আজকে`, `গত মাসে`, `এই সপ্তাহে`, `পরশু`

**API endpoint:**
- `POST /api/chat` — send a message, get back expense predictions, Q&A answers, or budget confirmations
- `POST /api/ask` — direct Q&A endpoint (returns text + optional chart data)

### 6. Expense Splitting

Split a combined description like `gorur mangsho 500 ar mach 300, rickshaw 50` into individual line items.

- Uses Groq LLM with the `SPLIT_PROMPT` that knows about Bangla separators (`ar`, `ও`, `and`, `+`)
- Strips trailing monetary amounts from each item description via `_clean_split_desc()`
- Applies learned category overrides after LLM split

**API endpoint:**
- `POST /api/split_expense` — split a description into items

### 7. Budget Management

Set monthly budgets per category and track spending vs. budget in real-time.

- Supports **per-category budgets** (Food, Transport, etc.) and an **overall/total budget** (`__overall__`)
- Budget usage percentage displayed in the budgets view
- **Auto-alerts** — Push notification sent when spending reaches ≥80% of budget
- Budget intent can be set via the AI Chat: "set food budget 5000" or "overall budget 30000"

**API endpoints:**
- `GET /api/budgets` — list budgets with spent amounts and percentages
- `POST /api/budgets/set` — create or update a budget
- `DELETE /api/budgets/<id>` — delete a budget
- `GET /api/budgets/status` — get budget status for the current month

### 8. Recurring Transactions

Define recurring expenses (rent, subscriptions, etc.) and auto-create them when due.

- Supports `daily`, `weekly`, `monthly`, `yearly`, or custom intervals
- Auto-processing via `POST /api/recurring/process`
- Push notification sent when recurring expenses are auto-created
- Next-date computation handles monthly rollovers correctly

**API endpoints:**
- `GET /api/recurring` — list recurring transactions
- `POST /api/recurring` — create a recurring transaction
- `PUT /api/recurring/<id>` — update a recurring transaction
- `DELETE /api/recurring/<id>` — delete a recurring transaction
- `POST /api/recurring/process` — process due recurring transactions

### 9. Spending Forecast

AI-powered end-of-month spending projection with confidence scoring.

**Input data:** current month daily totals, previous month daily totals, category breakdown, known fixed monthly expenses (detected by comparing last month's unique expenses), and overall budget.

**How it works:**
1. Collects current daily totals, previous month data, and category breakdown
2. Detects known fixed monthly expenses (expenses from last month that haven't been recorded yet this month)
3. Invokes `generate_forecast()` → sends all data to Groq with a structured prompt
4. Returns `projected`, `best_case`, `worst_case`, `confidence` (high/medium/low), `reasoning`, and `notes`
5. Falls back to linear projection if AI is unavailable

**API endpoint:**
- `GET /api/forecast` — returns forecast with projected total, daily avg, budget status, and AI reasoning

### 10. Dashboard & Charts

Visualize spending with interactive charts.

- **Pie chart** — Category breakdown for the selected month
- **Bar chart** — Daily spending trend
- **Monthly summary table** — Category-wise totals with counts
- **Year-over-year comparison** — Monthly bar chart
- **Budget vs. actual** — Bar comparison for each category
- **Date navigation** — Browse by month/year

**API endpoints:**
- `GET /api/dashboard` — aggregated dashboard data (totals, category breakdown, daily totals)
- `GET /api/index` — home page data (recent expenses, today's total)

### 11. Calendar View

Visual calendar showing daily expense totals, with color intensity based on spending amount.

**API endpoint:**
- `GET /api/expenses/daily-totals` — daily totals for a given month

### 12. Export

Download expenses as CSV, XLSX, or PDF with optional search filtering.

**Formats:**
- **CSV** — UTF-8 encoded, comma-separated
- **XLSX** — Formatted Excel workbook with styled header row and totals
- **PDF** — Printable PDF with month and year header

**API endpoint:**
- `GET /api/export/<csv|xlsx|pdf>?year=&month=&search=` — download exported file

### 13. Push Notifications

Web Push notifications via the Push API and Service Worker.

- **Subscribe/Unsubscribe** — users can opt in to push notifications
- **Daily Digest** — Automatic daily summary sent each morning (yesterday's total, month-to-date, daily average, top category, budget alerts)
- **Budget Alerts** — Instant notification when spending reaches ≥80% of a category budget
- **Recurring Alerts** — Notification when recurring transactions are auto-processed
- **Admin Digest Trigger** — Superusers can trigger digest for all users

**API endpoints:**
- `GET /api/notifications/vapid-public-key` — get VAPID public key for client subscription
- `POST /api/notifications/subscribe` — subscribe to push
- `POST /api/notifications/unsubscribe` — unsubscribe
- `POST /api/notifications/check-digest` — check and send daily digest for current user
- `POST /api/notifications/daily-digest` — send digests to all users (cron endpoint, protected by `CRON_SECRET`)

### 14. Multi-User & Roles

- **Registration** — New users sign up with username + password
- **Roles** — `user` (standard) and `superuser` (admin)
- **Admin panel** — Superusers can view/delete users, change roles, and trigger notifications
- **Data isolation** — Users see only their own expenses (superusers can view all)
- **Password reset** — Token-based password reset flow

**API endpoints:**
- `POST /api/register` — create new user
- `POST /api/login` — authenticate
- `POST /api/logout` — end session
- `POST /api/forgot-password` — request password reset
- `GET /api/reset/<token>` — validate reset token
- `POST /api/reset-password/<token>` — complete password reset
- `GET /api/profile` — get current user profile
- `POST /api/profile/change-password` — change password
- `GET /api/admin/users` — list all users (superuser only)
- `POST /api/admin/users/<id>/change-role` — change user role (superuser only)
- `POST /api/admin/users/<id>/delete` — delete user (superuser only)
- `POST /api/admin/notifications/daily-digest/trigger` — trigger digest for all users (superuser only)

### 15. Dark Mode

- Automatically follows system preference (`prefers-color-scheme`)
- Manual toggle persisted in `localStorage`
- CSS custom properties for all themed colors

### 16. PWA Support

Progressive Web App with offline-capable service worker.

- **Manifest** — `manifest.json` with app icon, theme color, display mode
- **Service Worker** — `sw.js` caches CSS, JS, and app shell for offline access
- **iOS Support** — `apple-mobile-web-app-capable` meta tag, apple touch icons
- **Cache busting** — File mtime appended to CSS/JS URLs as `?v=<timestamp>` to force refresh after deployment

---

## Project Structure

```
expense-tracker/
├── app.py                # Flask application — routes, auth, middleware
├── config.py             # Environment variables, seed categories, colors
├── database.py           # SQLAlchemy schema, queries, migrations
├── llm/                  # AI/LLM package (modular refactor of llm_service.py)
│   ├── __init__.py       # Re-exports all 18 public symbols
│   ├── config.py         # Groq client helpers (_get_client, _has_api_key)
│   ├── categories.py     # Constants: CATEGORIES, keyword_category(), extract_amount_fallback()
│   ├── expenses.py       # extract_expense(), predict_expense(), date reference parsing
│   ├── split.py          # split_expenses(), _clean_split_desc()
│   ├── budget.py         # detect_budget_intent() — regex-based budget detection
│   ├── qa/__init__.py    # SQL generation, correction, answer formatting
│   ├── decompose.py      # Question decomposition, compose_answers(), is_question()
│   ├── forecast.py       # generate_forecast() — AI spending forecast
│   ├── transcribe.py     # transcribe_audio() — Whisper transcription
│   └── receipt.py        # scan_receipt() — Groq Vision + Gemini fallback
├── export_service.py     # CSV, XLSX, PDF generation
├── llm_service.py        # Compatibility stub → from llm import *
├── requirements.txt
├── Procfile              # gunicorn start command
├── render.yaml           # Render deployment config
├── .env                  # Local environment variables (gitignored)
├── templates/
│   └── index.html        # SPA shell with sidebar nav, theme toggle
└── static/
    ├── script.js          # SPA client (~3044 lines) — all UI logic
    ├── style.css          # Full app styles (~3329 lines)
    ├── sw.js              # Service Worker for offline + push
    └── manifest.json      # PWA manifest
```

---

## Database Schema

### Tables

| Table               | Purpose                                  |
|---------------------|------------------------------------------|
| `expenses`          | Core expense records                     |
| `users`             | User accounts + roles                    |
| `budgets`           | Monthly budget per category per user     |
| `learned_categories` | User-corrected keyword→category mappings |
| `push_subscriptions` | Web Push subscription endpoints          |
| `password_resets`   | Token-based password reset flow          |
| `recurring_transactions` | Recurring/periodic expenses          |

### `expenses`

| Column      | Type    | Notes                      |
|-------------|---------|----------------------------|
| id          | SERIAL  | Primary key                |
| date        | TEXT    | YYYY-MM-DD format          |
| description | TEXT    | Cleaned expense description |
| amount      | REAL    | In BDT                     |
| category    | TEXT    | One of 17 categories       |
| user_id     | INTEGER | FK → users.id              |
| created_at  | TIMESTAMP | Auto on insert           |

### `budgets`

| Column    | Type    | Notes                 |
|-----------|---------|-----------------------|
| id        | SERIAL  | Primary key           |
| user_id   | INTEGER | FK → users.id         |
| category  | TEXT    | Category name or `__overall__` |
| amount    | REAL    | Monthly budget in BDT |
| created_at / updated_at | TIMESTAMP |        |

---

## Environment Variables

| Variable                | Required | Default | Description |
|-------------------------|----------|---------|-------------|
| `GROQ_API_KEY`          | Yes*     | —       | Groq API key (primary AI provider) |
| `GEMINI_API_KEY`        | No       | —       | Gemini API key (fallback for vision) |
| `SECRET_KEY`            | Yes      | `change-this-to-a-random-secret-key` | Flask session secret |
| `APP_USERNAME`          | Yes      | `admin` | First superuser username |
| `APP_PASSWORD`          | Yes      | `admin123` | First superuser password |
| `DATABASE_URL`          | No       | SQLite  | PostgreSQL connection string (Neon) |
| `DATABASE_PATH`         | No       | `expenses.db` | SQLite file path |
| `VAPID_PRIVATE_KEY`     | No       | —       | VAPID private key for push notifications |
| `VAPID_PUBLIC_KEY`      | No       | —       | VAPID public key |
| `VAPID_CLAIM_EMAIL`     | No       | `mailto:admin@expenses.app` | VAPID claim email |
| `VAPID_APPLICATION_SERVER_KEY` | No | —    | Alternative VAPID key format |
| `CRON_SECRET`           | No       | —       | Secret for cron-triggered digest endpoint |
| `TIMEZONE`              | No       | `Asia/Dhaka` | Application timezone |

> * `GROQ_API_KEY` is the primary provider. Without it, expense extraction falls back to keyword matching, Q&A/forecast/split return `None`, and receipt scanning uses Gemini (if configured).

---

## AI Decision Flow

```
User Input
    │
    ├── Audio File → transcribe_audio() [Whisper]
    │                   │
    │                   └── Text → (same as text input below)
    │
    ├── Receipt Image → scan_receipt()
    │                       │
    │                       ├── Groq Vision (llama-4-scout)
    │                       │     └── Fallback: llama-3.2-11b-vision
    │                       ├── Gemini 2.0 Flash (fallback)
    │                       └── keyword_category() per item (no extra API)
    │
    └── Text Input (chat or add-expense)
            │
            ├── detect_budget_intent() → matches budget pattern? → set budget
            │
            ├── is_question() → true → Q&A Pipeline
            │   ├── extract_date_reference()
            │   ├── decompose_question() [for compound queries]
            │   ├── generate_sql() → _validate_sql() → execute → format_answer()
            │   └── correct_sql() [on error]
            │
            ├── split_expenses() → multiple items? → show in chat for confirmation
            │
            └── predict_expense() / extract_expense()
                ├── check_learned() [local, instant]
                ├── Groq LLM (llama-3.1-8b-instant)
                └── keyword_category() + extract_amount_fallback() [fallback]
```

---

## API Route Summary

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/login` | — | Authenticate |
| POST | `/api/logout` | ✓ | End session |
| POST | `/api/register` | — | Create account |
| GET | `/api/me` | ✓ | Current user info |
| GET | `/api/profile` | ✓ | User profile |
| POST | `/api/profile/change-password` | ✓ | Change password |
| POST | `/api/forgot-password` | — | Request reset |
| GET | `/api/reset/<token>` | — | Validate reset token |
| POST | `/api/reset-password/<token>` | — | Complete reset |
| GET | `/api/index` | ✓ | Home page data |
| GET | `/api/dashboard` | ✓ | Dashboard aggregates |
| POST | `/api/add_expense` | ✓ | Add single expense |
| POST | `/api/expenses/bulk` | ✓ | Bulk add expenses |
| DELETE | `/api/delete_expense/<id>` | ✓ | Delete expense |
| GET | `/api/expenses/<date>` | ✓ | Expenses by date |
| GET | `/api/expenses/month` | ✓ | Expenses by month |
| GET | `/api/expenses/monthly-totals` | ✓ | Monthly aggregates |
| GET | `/api/expenses/category-totals` | ✓ | Category totals by month |
| GET | `/api/expenses/category-breakdown` | ✓ | Paginated category detail |
| GET | `/api/expenses/daily-totals` | ✓ | Daily totals for calendar |
| GET | `/api/categories` | ✓ | List categories + colors |
| POST | `/api/predict_expense` | ✓ | Predict category + amount |
| POST | `/api/chat` | ✓ | AI Chat message |
| POST | `/api/ask` | ✓ | Direct Q&A query |
| GET | `/api/suggestions` | ✓ | Smart suggestions |
| POST | `/api/split_expense` | ✓ | Split expense description |
| POST | `/api/transcribe` | ✓ | Transcribe audio |
| POST | `/api/scan_receipt` | ✓ | Scan receipt image |
| GET | `/api/forecast` | ✓ | Spending forecast |
| GET/POST | `/api/budgets` | ✓ | List/set budgets |
| DELETE | `/api/budgets/<id>` | ✓ | Delete budget |
| GET | `/api/budgets/status` | ✓ | Budget usage status |
| GET/POST | `/api/recurring` | ✓ | List/create recurring |
| PUT/DELETE | `/api/recurring/<id>` | ✓ | Update/delete recurring |
| POST | `/api/recurring/process` | ✓ | Process due recurring |
| GET | `/api/export/<fmt>` | ✓ | Export (csv/xlsx/pdf) |
| GET | `/api/notifications/vapid-public-key` | — | Get VAPID public key |
| POST | `/api/notifications/subscribe` | ✓ | Subscribe to push |
| POST | `/api/notifications/unsubscribe` | ✓ | Unsubscribe from push |
| POST | `/api/notifications/check-digest` | ✓ | Get daily digest |
| POST | `/api/notifications/daily-digest` | — | Cron-triggered digest |
| POST | `/api/learn` | ✓ | Learn keyword→category |
| GET | `/api/admin/users` | ★ | List all users |
| POST | `/api/admin/users/<id>/change-role` | ★ | Change user role |
| POST | `/api/admin/users/<id>/delete` | ★ | Delete user |
| POST | `/api/admin/notifications/daily-digest/trigger` | ★ | Trigger digest for all |

> ✓ = login_required, ★ = superuser_required

---

## Deployment (Render + Neon)

1. Create a free PostgreSQL database on [Neon](https://neon.tech)
2. Push code to GitHub
3. Create a **Web Service** on [Render](https://render.com):
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app`
   - Add env vars: `DATABASE_URL`, `GROQ_API_KEY`, `SECRET_KEY`, `APP_USERNAME`, `APP_PASSWORD`
4. Render automatically provisions SSL and a public URL
5. The app auto-detects `DATABASE_URL` presence and switches to PostgreSQL; without it, SQLite is used

---

## Cache Busting

CSS and JS URLs include a `?v=<file-mtime>` query parameter generated by the `_static_version()` context processor. This ensures the browser always loads the latest version after a deployment without requiring manual version bumps.
