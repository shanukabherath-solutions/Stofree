@echo off
REM Builds dist\Stofree\Stofree.exe  (run from the project folder on Windows)
setlocal
if not exist .venv ( py -3.11 -m venv .venv || goto :err )
call .venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip || goto :err
pip install -r requirements-build.txt || goto :err
REM Regenerate the multi-resolution ICO from the supplied logo.png (logo.png is not modified)
python tools\make_icon.py || goto :err
pyinstaller --noconfirm --clean packaging\stofree.spec || goto :err
echo.
echo Build complete: dist\Stofree\Stofree.exe
goto :eof
:err
echo Build failed.
exit /b 1
