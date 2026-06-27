@echo off

echo Abrindo os terminais de servidores...

:: Detecta automaticamente a pasta raiz do projeto
for %%i in ("%~dp0..") do set "RAIZ=%%~fi"

:: Abre o Windows Terminal dividido em dois (Split-Pane Horizontal) — identico ao original
"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" -d "%RAIZ%" powershell -NoExit -Command ".\.venv\Scripts\activate\; clear\; Write-Host -ForegroundColor Green '========================================'\; Write-Host -ForegroundColor Green ' SERVIDOR PRINCIPAL (app.py)'\; Write-Host -ForegroundColor Green '========================================'\; Write-Host 'Pressione ENTER para ligar...'\; Read-Host\; python app.py" ; split-pane -H -d "%RAIZ%" powershell -NoExit -Command ".\.venv\Scripts\activate\; clear\; Write-Host -ForegroundColor Cyan '========================================'\; Write-Host -ForegroundColor Cyan ' EXTRATOR DE BOLOES - Caixa (API)'\; Write-Host -ForegroundColor Cyan '========================================'\; Write-Host '[1] Terminal pedira: MODALIDADE e CONCURSO (antes do Edge abrir)'\; Write-Host '[2] Edge abre -> LOGIN -> modalidade -> filtros -> ENTER'\; Write-Host '[3] JSON cresce em tempo real em json-boloes\'\; Write-Host 'Pressione ENTER para rodar...'\; Read-Host\; python -u conferencias-boloes\script\baixar_boloes-API.py"
