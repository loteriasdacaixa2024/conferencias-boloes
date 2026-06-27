@echo off
echo Abrindo os terminais de servidores...

:: Define a pasta principal do projeto (onde estao os arquivos python)
set "RAIZ=D:\Loterias\AnalisePorPosicao-DiaDeSorte-Only"

:: Abre o Windows Terminal dividido em dois (Split-Pane Horizontal)
"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" -d "%RAIZ%" powershell -NoExit -Command ".\.venv\Scripts\activate\; clear\; Write-Host -ForegroundColor Green '========================================'\; Write-Host -ForegroundColor Green '      SERVIDOR PRINCIPAL (app.py)'\; Write-Host -ForegroundColor Green '========================================'\; Write-Host 'Pressione ENTER para ligar...'\; Read-Host\; python app.py" ; split-pane -H -d "%RAIZ%" powershell -NoExit -Command ".\.venv\Scripts\activate\; clear\; Write-Host -ForegroundColor Cyan '========================================'\; Write-Host -ForegroundColor Cyan '   EXTRATOR DE BOLOES - Caixa (API)'\; Write-Host -ForegroundColor Cyan '========================================'\; Write-Host '[1] site: login + modalidade + filtros + ENTER'\; Write-Host 'Modalidade vem da API (MEGA_SENA...) - M1-M9 opcional'\; Write-Host 'Pressione ENTER para rodar...'\; Read-Host\; python -u conferencias-boloes\script\baixar_boloes-API.py"
