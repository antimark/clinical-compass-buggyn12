@echo off
setlocal
cd /d "%~dp0.."
if "%CC_CONDA_ENV%"=="" set "CC_CONDA_ENV=clinical-compass"
call conda run --no-capture-output -n "%CC_CONDA_ENV%" python scripts/validate_full.py %*
exit /b %ERRORLEVEL%
