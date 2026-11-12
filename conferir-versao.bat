@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - conferir versao
echo.
echo   JARVIS - conferir versao e tela
echo   Versao deste arquivo: 0.89.3
echo.
echo   Nao instala, nao baixa e nao altera nada: so le e responde.
echo   Use quando a tela parecer velha ou faltar algum cartao.
echo.
echo ------------------------------------------------------------
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" verificar_versao.py %*
) else (
  py -3 verificar_versao.py %* 2>nul || python verificar_versao.py %*
)
echo.
echo ------------------------------------------------------------
echo.
echo   Copie esta tela e me mande se algo aparecer errado.
echo   Para parar de ler: feche esta janela no X.
echo.
pause
