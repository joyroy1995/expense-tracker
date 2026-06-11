# Expense Tracker

Track daily expenses in BDT with LLM-powered auto-categorization. Supports English, Bengali, and Banglish.

**Live:** `https://your-app-name.onrender.com`

## Features

- **Natural Language Input** — Type "rickshaw 50 tk" or "badam 30 taka" in English/Bangla/Banglish
- **Auto-Categorization** — Gemini AI + keyword fallback detects category from text
- **Dashboard** — Category pie chart, monthly bar chart, breakdown table
- **Monthly Summary** — View expenses grouped by month

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python Flask |
| Database | PostgreSQL (Neon.tech) / SQLite (local) |
| AI | Google Gemini API |
| Hosting | Render |
| Frontend | HTML, CSS, JavaScript, Chart.js |

## Local Development

```bash
git clone <your-repo-url>
cd expense-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export GEMINI_API_KEY="your-gemini-api-key"
export APP_USERNAME="admin"
export APP_PASSWORD="admin123"
export SECRET_KEY="random-secret"

python app.py
```

Open http://localhost:5000. Uses SQLite locally (no DATABASE_URL needed).

## Deploy to Render + Neon

### 1. Get Free PostgreSQL from Neon

1. Go to https://neon.tech and sign up (free)
2. Click **Create a project** (name it `expense-tracker`)
3. Copy the **connection string** from the dashboard. It looks like:
   ```
   postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/expenses?sslmode=require
   ```

### 2. Deploy on Render

1. Push your code to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/expense-tracker.git
   git push -u origin main
   ```

2. Go to https://render.com and sign up (free)

3. Click **New +** → **Web Service**

4. Connect your GitHub repo

5. **Configure:**
   - **Name:** `expense-tracker` (becomes `expense-tracker.onrender.com`)
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free

6. **Add Environment Variables** in Render dashboard:
   ```
   DATABASE_URL = postgresql://user:pass@ep-xxx.neon.tech/expenses?sslmode=require
   GEMINI_API_KEY = your-gemini-api-key
   SECRET_KEY = random-secret-string
   APP_USERNAME = admin
   APP_PASSWORD = your-secure-password
   ```

7. Click **Create Web Service**

8. Wait for deploy. Visit `https://expense-tracker.onrender.com`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No (local) | PostgreSQL URL from Neon. Leave empty for SQLite |
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `SECRET_KEY` | Yes | Flask session secret |
| `APP_USERNAME` | Yes | Login username |
| `APP_PASSWORD` | Yes | Login password |

## Project Structure

```
expense-tracker/
├── app.py              # Flask routes and auth
├── config.py           # Settings and env vars
├── database.py         # SQLAlchemy database layer
├── llm_service.py      # Gemini + keyword categorization
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment config
├── Procfile            # Process config
├── .env.example        # Env var template
├── templates/
│   ├── login.html
│   ├── index.html
│   └── dashboard.html
└── static/
    ├── style.css
    └── script.js
```
