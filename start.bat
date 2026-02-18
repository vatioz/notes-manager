@echo off
echo Installing Notes Manager dependencies...
pip install -r requirements.txt

echo.
echo Starting Notes Manager...
python app.py

pause
