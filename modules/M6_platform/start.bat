@echo off
chcp 65001 >nul
echo ========================================
echo   EduNUWA M6 Platform - 启动脚本
echo ========================================
echo.

REM 检查 DEEPSEEK_API_KEY
if "%DEEPSEEK_API_KEY%"=="" (
    echo [警告] 未设置 DEEPSEEK_API_KEY 环境变量
    echo AI 聊天将使用模拟回复模式
    echo 如需真实 AI 回复，请设置: set DEEPSEEK_API_KEY=your_key
    echo.
)

REM 清理可能残留、占用 5000 端口的旧后端进程（避免多进程抢端口导致前端拿到 HTML）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo [1/2] 启动后端服务 (Flask :5000)...
start "EduNUWA-Backend" cmd /c "cd /d %~dp0backend && D:\anaconda3\envs\edu\python.exe app.py"

echo [2/2] 启动前端服务 (Vite :3000)...
start "EduNUWA-Frontend" cmd /c "cd /d %~dp0frontend && npm run dev"

echo.
echo 启动完成!
echo 后端 API: http://localhost:5000/api/v1
echo 前端页面: http://localhost:3000
echo.
echo 按任意键退出...
pause >nul
