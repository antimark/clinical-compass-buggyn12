@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."
where conda >nul 2>nul
if errorlevel 1 (
  echo ERROR: conda not found. Open Anaconda/Miniforge Prompt and run conda env create -f environment.yml 1>&2
  exit /b 127
)
if not defined CC_CONDA_ENV set "CC_CONDA_ENV=clinical-compass"
set "PYTHONPATH=%CD%\backend;%PYTHONPATH%"
call conda run --no-capture-output -n "%CC_CONDA_ENV%" python -m compileall -q backend migrations
if errorlevel 1 exit /b 1
call conda run --no-capture-output -n "%CC_CONDA_ENV%" python -m pytest -q
if errorlevel 1 exit /b 1
set "JS_TESTS="
for %%F in (frontend\dist\tests\*.cjs) do set "JS_TESTS=!JS_TESTS! %%F"
if not defined JS_TESTS (
  echo ERROR: no Node test files found. 1>&2
  exit /b 2
)
call conda run --no-capture-output -n "%CC_CONDA_ENV%" node --test !JS_TESTS!
if errorlevel 1 exit /b 1
call conda run --no-capture-output -n "%CC_CONDA_ENV%" node --check frontend\dist\assets\js\live_app.js
exit /b %ERRORLEVEL%
