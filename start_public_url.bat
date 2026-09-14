@echo off
title RecruitPro Public URL Tunnel
echo ============================================================
echo Starting Cloudflare Tunnel for RecruitPro (Port 5000)...
echo Make sure your Flask app (python app.py) is running!
echo ============================================================
echo.
"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:5000
pause
