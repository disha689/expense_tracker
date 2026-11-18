# Spendly

![Tests](https://github.com/disha689/expense_tracker/actions/workflows/tests.yml/badge.svg)

A simple, private expense tracker. Add what you spend, see it on a calendar, set budgets, and watch a pie chart turn orange or red when you get close to a limit or go over it.

It is a small full-stack project: a Python (FastAPI) backend with raw SQL, a plain HTML/CSS/JavaScript front end with no framework, PostgreSQL in production and SQLite on a laptop, and automated tests that run on both databases.

> The live version is protected by a password, and the screenshots below use made-up demo data.

![Home page with the phone preview](docs/screenshots/home.png)

## Features

- **Expenses**: add, edit, delete, with category, note and date.
- **Calendar**: a dot marks every day that has expenses. Click a day to see only that day, or move between months.
- **Budgets**: one budget per month, plus a budget for each category. Bars are green, turn orange at 80% and red when you are over. Budgets carry forward to the next months until you change them.
- **Pie chart** of spending by category. Its colors change with your budget status.
- **Recurring expenses** such as rent, Wi-Fi or subscriptions. They are added on their day each month, past months are filled in, and nothing is ever added twice.
- **Bill scan**: take a photo of a bill and the amount, date and a category guess are filled in for you to check. The photo is read in the browser and is not stored.
- **CSV export and import**, with protection against spreadsheet formula injection.
- **Login** with a single password.
- **Works on phones**, with a sticky top menu and a profile circle (your photo stays in your own browser).

![Dashboard with budgets, calendar and recurring expenses](docs/screenshots/dashboard.png)

<p>
  <img src="docs/screenshots/mobile.png" alt="Phone view" width="260">
  <img src="docs/screenshots/login.png" alt="Login page" width="520">
</p>

## Tech stack

| Part | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic |
| Database | PostgreSQL online, SQLite on a laptop (the same SQL runs on both) |
| Front end | HTML, CSS and JavaScript in one page, Tesseract.js for bill scanning |
| Tests | pytest, run on SQLite and on PostgreSQL |
| CI | GitHub Actions |
| Hosting | Render (web service) and Neon (PostgreSQL) |

## Project structure

```
app/
  main.py        routes (expenses, budgets, recurring, CSV)
  crud.py        all database logic
  database.py    connections and tables for SQLite and PostgreSQL
  schemas.py     request and response models
  auth.py        password hashing, login cookie, login limits
  security.py    login check in front of the whole app
  static/        index.html, login.html, logo.svg
tests/           automated tests
make_password.py        creates your password (saved as a hash in .env)
migrate_to_postgres.py   copies a local expenses.db into PostgreSQL
tracker.py               the original command-line version
```

## Run it on your computer

These commands are for Windows PowerShell.

```powershell
git clone https://github.com/disha689/expense_tracker.git
cd expense_tracker
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
python make_password.py
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and log in with the password you just chose. Your data is kept in a local `expenses.db` file.

If you open the page before running `make_password.py`, it will tell you the password is not set yet.

## Tests

```powershell
python -m pytest
```

This runs on SQLite and needs nothing else. To run the same tests on PostgreSQL as well, point `TEST_DATABASE_URL` at an empty test database (its tables are dropped and re-created for every test, so never use a database that holds real data):

```powershell
$env:TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/test_db"
python -m pytest
```

GitHub Actions runs both versions on every push.

## Settings

Settings are read from environment variables, or from a `.env` file that is never uploaded to GitHub.

| Name | What it does |
|---|---|
| `APP_PASSWORD_HASH` | Hash of your password. Created by `make_password.py`. |
| `SESSION_SECRET` | Secret that signs the login cookie. Also created by `make_password.py`. |
| `DATABASE_URL` | PostgreSQL connection string. If it is not set, SQLite is used. |
| `COOKIE_SECURE` | Set to `1` on a real website so the login cookie is only sent over HTTPS. |
| `TEST_DATABASE_URL` | Used only by the tests, as described above. |
| `AUTH_DISABLED` | Switches the login off. For automated tests only, never on a server. |

## Deploying

The live site runs on Render (web service) with a Neon PostgreSQL database.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
- Health check path: `/healthz`
- Environment variables: `PYTHON_VERSION`, `DATABASE_URL`, `APP_PASSWORD_HASH`, `SESSION_SECRET`, `COOKIE_SECURE=1`

To move data from a local `expenses.db` into an empty online database, run `python migrate_to_postgres.py`. It asks for the connection string, copies everything in one step, and refuses to run if the online database already has data.

## Security notes

- The password is stored only as a PBKDF2-SHA256 hash. The login cookie is signed, `HttpOnly`, `SameSite=Lax`, and `Secure` on HTTPS.
- Requests that change data are rejected when they come from another website.
- Wrong passwords are limited per address and across all addresses together.
- Every page and API route needs a login, except the login page and a plain health check.

## Limitations

- It is a single-user app: there is one password and no separate accounts.
- On free hosting the app sleeps after a while without visitors, so the first page load can take about a minute.
- Bill scanning works best on a clear, straight photo. Blurry or tilted bills can give a wrong amount, which is why you always check it before saving.
- Recurring expenses are added when the page is opened, not by a background job.
- Login limits are kept in memory and start fresh when the server restarts.

## Roadmap

- Install on a phone like an app
- A read-only demo mode with sample data
- More accurate bill reading
- Separate accounts for more than one person

## Author

Built by Disha Soni.
[GitHub](https://github.com/disha689) · [LinkedIn](https://www.linkedin.com/in/disha-soni-a5219330b/)