# AI QA Agent

This repository contains a React/Vite frontend and a Python FastAPI backend for an AI QA automation project.

## Running the application

### Recommended: Use the Windows Terminal script

From the repository root (`C:\Users\2000189345\Documents\agent creation`):

1. Open PowerShell.
2. Run:
   ```powershell
   .\backend\start-dev-wt.ps1
   ```

If you are already inside the `backend` folder, run:

```powershell
.\start-dev-wt.ps1
```

If PowerShell prevents script execution, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\start-dev-wt.ps1
```

This will:
- create the backend virtual environment if needed
- install backend and frontend dependencies
- open two Windows Terminal tabs
  - Backend: `http://127.0.0.1:8000`
  - Frontend: `http://localhost:5173`

### Direct commands without scripts

If you want to run servers manually in separate terminals:

#### Backend

```powershell
cd "C:\Users\2000189345\Documents\agent creation\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### Frontend

```powershell
cd "C:\Users\2000189345\Documents\agent creation\frontend"
npm install
npm run dev
```

### Important note

Make sure you run the backend command from the `backend` folder. If you run `python -m uvicorn app.main:app` from the repository root, Python will not find the `app` package and you will get `ModuleNotFoundError: No module named 'app'`.

## Frontend URL

Open this URL in your browser after the frontend server starts:

- http://localhost:5173

## Backend URL

The backend API is available at:

- http://127.0.0.1:8000

If you want to access the API root directly in your browser, go to:

- http://127.0.0.1:8000/

## Run generated Selenium tests

Install the backend Python dependencies:

```powershell
cd "C:\Users\2000189345\Documents\agent creation\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then run pytest against the generated test file (for example):

```powershell
pytest -q tests/test_generated.py
```

The generated Selenium tests will use `webdriver-manager` to automatically download the matching ChromeDriver.
