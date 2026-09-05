@echo off
REM SENTINEL one-shot setup (Windows). Run once from E:\senfin.
setlocal
cd /d "%~dp0"

echo [1/4] Python check...
python --version || (echo Python 3.10+ required. Install from python.org & exit /b 1)

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || exit /b 1

echo [3/4] Environment file...
if not exist .env (
  copy .env.example .env
  echo Created .env - edit SUPABASE_URL / SUPABASE_KEY / NVIDIA_API_KEY to enable live services.
) else (
  echo .env already exists - skipping.
)

echo [4/4] Initializing database...
python -c "from app.services.store import init_db; from app.services.evidence_store import init as init_ev; from app.graph import agent_store; init_db(); init_ev(); agent_store.init_graph_tables(); print('DB ready:', 'database/sentinel.db')" || exit /b 1

echo.
echo SETUP COMPLETE. Start the platform with:
echo   uvicorn app.main:app --host 127.0.0.1 --port 8000
echo   Dashboard: http://127.0.0.1:8000/   (Next.js alt: npm run dev --prefix frontend-app)
echo   Stream: POST /stream/start  Simulate: POST /simulate  Reports: GET /reports
endlocal
