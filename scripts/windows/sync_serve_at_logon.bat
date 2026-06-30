@echo off
REM 开机自启 sync serve — 供「任务计划程序」调用
REM 若 Python 不在 PATH，请把下面 PY 改成完整路径，例如：
REM set PY=C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\python.exe

set PY=python
set ROOT=%~dp0..\..
cd /d "%ROOT%"

REM 可选：写入日志（排查用）
set LOG=%ROOT%\data\sync\serve.log
echo [%date% %time%] starting sync serve >> "%LOG%"

"%PY%" app.py sync serve --host 0.0.0.0 --port 8765 >> "%LOG%" 2>&1
