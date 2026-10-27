@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
where conda >nul 2>nul
if errorlevel 1 (
  echo ERROR: conda not found. Open Anaconda/Miniforge Prompt and run conda env create -f environment.yml 1>&2
  exit /b 127
)
if not defined CC_CONDA_ENV set "CC_CONDA_ENV=clinical-compass"
if not defined CC_DB_PATH set "CC_DB_PATH=%CD%\backend\data\dev.sqlite"
if not defined CC_PORT set "CC_PORT=8000"
set "CC_DEMO_MODE=1"
if not defined CC_APP_ENV set "CC_APP_ENV=synthetic_dev"
rem The already implemented clinical evaluation APIs are on only in explicit
rem synthetic_dev. Authentication, consent, CSRF, and doctor approval stay on.
if /I "%CC_APP_ENV%"=="synthetic_dev" (
  if not defined CC_CI_API_V1 set "CC_CI_API_V1=1"
  if not defined CC_CI_REVIEW_V1 set "CC_CI_REVIEW_V1=1"
  if not defined CC_CI_PROPOSALS_V1 set "CC_CI_PROPOSALS_V1=1"
  if not defined CC_CI_REFERRALS_V1 set "CC_CI_REFERRALS_V1=1"
  if not defined CC_CI_CHAT_V1 set "CC_CI_CHAT_V1=1"
  if not defined CC_CI_SAFETY_V1 set "CC_CI_SAFETY_V1=1"
)
if not defined CC_PUBLIC_BASE_URL set "CC_PUBLIC_BASE_URL=http://127.0.0.1:%CC_PORT%"
if not defined CC_SECRET_KEY for /f "delims=" %%k in ('call conda run -n "%CC_CONDA_ENV%" python -c "import secrets; print(secrets.token_urlsafe(48))"') do set "CC_SECRET_KEY=%%k"
if not defined CC_SECRET_KEY (
  echo ERROR: could not generate demo secret. Check that the Conda environment exists. 1>&2
  exit /b 1
)
set "PYTHONPATH=%CD%\backend;%PYTHONPATH%"
echo Synthetic-only Clinical Compass demo; Conda environment: %CC_CONDA_ENV%
echo Live UI: http://127.0.0.1:%CC_PORT%/
call conda run --no-capture-output -n "%CC_CONDA_ENV%" python backend\run.py
exit /b %ERRORLEVEL%
