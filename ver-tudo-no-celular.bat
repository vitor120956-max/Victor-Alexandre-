@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JARVIS - ver tudo no celular
REM Versao: 0.92.9
REM
REM O caminho mais curto: com o celular ja conectado, este arquivo passa o
REM JARVIS por todo o aparelho numa varredura so - anatomia, scanner de
REM problemas e mapa de pastas/particoes - e diz o que nao da sem root.
REM SO LEITURA: nao instala, nao copia arquivo, nao abre tela, nao reinicia.

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   O .venv ainda nao existe. Rode o iniciar-jarvis.bat uma vez;
  echo   ele cria o ambiente e instala o que falta.
  echo.
  pause
  exit /b 1
)

echo.
echo   JARVIS - ver tudo no celular
echo.
echo   O celular precisa estar com:
echo     1. Depuracao USB ligada  (Ajustes -^> Opcoes do desenvolvedor)
echo     2. Cabo de DADOS conectado (nao serve cabo so de carga)
echo     3. "Permitir" tocado na tela do celular quando o aviso aparecer
echo.
echo   Sao 28 leituras e algumas perguntas sobre o que voce ve: 1 a 2 minutos.
echo   Nada e alterado no aparelho.
echo.
echo ------------------------------------------------------------
echo.

".venv\Scripts\python.exe" escanear-celular.py --completo

echo ------------------------------------------------------------
echo.
echo   Copie esta tela e me mande o que aparecer.
echo   O relatorio tambem fica salvo em storage\diagnosticos.
echo.
echo   Quer a tela do celular numa janela do PC? Peca no chat
echo   "espelha o celular aqui" (a skill celular.espelhar cuida do scrcpy).
echo.
pause
