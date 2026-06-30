@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================
echo   LLM Debate Studio Factory Reset
echo ============================================
echo.
echo 这个脚本会永久清理本项目目录中的以下内容：
echo 1. 所有辩论记录：data\debates\*.json
echo 2. 所有详情/错误日志：logs\details\*.md、logs\errors\*.md
echo 3. 历史旧日志：logs\debate_*_detail.log、logs\debate_*_simple.log
echo 4. 所有本地软配置与 API Key：data\settings.json
echo 5. 项目目录中的 .env（如果存在）
echo.
echo 注意：该操作不可恢复。
echo.
set /p CONFIRM=输入 RESET 并回车以继续，否则直接关闭窗口： 

if /I not "%CONFIRM%"=="RESET" (
  echo.
  echo 已取消，没有执行任何清理。
  echo.
  pause
  exit /b 0
)

echo.
echo 正在清理项目数据...

if not exist "data" mkdir "data"
if not exist "data\debates" mkdir "data\debates"
if not exist "logs" mkdir "logs"
if not exist "logs\details" mkdir "logs\details"
if not exist "logs\errors" mkdir "logs\errors"

del /q /f "data\debates\*.json" 2>nul
del /q /f "logs\details\*.md" 2>nul
del /q /f "logs\errors\*.md" 2>nul
del /q /f "logs\debate_*_detail.log" 2>nul
del /q /f "logs\debate_*_simple.log" 2>nul

if exist "data\settings.json" del /q /f "data\settings.json"
if exist ".env" del /q /f ".env"
if exist "__pycache__" rmdir /s /q "__pycache__"

echo.
echo 已恢复到项目初始空白状态。
echo 下次启动时，系统会重新生成默认 settings.json。
echo.
pause
