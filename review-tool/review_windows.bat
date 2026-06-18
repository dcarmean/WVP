@echo off
cd /d "%~dp0"
start "" "http://localhost:8765/review.html"
python -m http.server 8765
