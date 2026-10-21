@echo off
rem Abre a Vatty com dois cliques. Na primeira vez prepara tudo sozinho (leva uns minutos).
chcp 65001 >nul
cd /d "%~dp0"
title Vatty

if not exist ".venv\Scripts\python.exe" (
  echo Primeira vez: preparando a Vatty. Isso leva uns minutos...
  py -3.14 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Nao achei o Python 3.14. Instale em https://www.python.org/downloads/
    echo marcando "Add python.exe to PATH", e clique de novo neste arquivo.
    pause
    exit /b 1
  )
)

echo Conferindo as pecas da Vatty...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -e ".[gravacao]"
if errorlevel 1 (
  echo.
  echo A instalacao falhou. Mande um print desta janela.
  pause
  exit /b 1
)

rem O YouTube muda toda hora: yt-dlp velho e a causa numero 1 de bloqueio. Sem internet, segue assim mesmo.
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -U "yt-dlp[default,curl-cffi]" >nul 2>&1
where deno >nul 2>&1 || where node >nul 2>&1 || (
  echo.
  echo Aviso: sem o Deno o YouTube bloqueia mais. Para instalar: winget install DenoLand.Deno
)

echo.
".venv\Scripts\python.exe" -m vatty.cli ui
pause
