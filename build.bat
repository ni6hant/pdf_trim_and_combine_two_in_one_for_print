@echo off
REM Run this on a Windows machine with Python 3.10+ installed.
REM Builds a much smaller standalone PDFTrimmer.exe into the "dist" folder.
REM
REM Optional: to shrink the exe further with UPX, download UPX from
REM https://github.com/upx/upx/releases, unzip it, and set UPX_DIR below to
REM the folder containing upx.exe. Leave blank to skip UPX.

set UPX_DIR=

REM --- Use a clean virtual environment so no unrelated packages get bundled ---
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

set UPX_FLAG=
if not "%UPX_DIR%"=="" set UPX_FLAG=--upx-dir "%UPX_DIR%"

pyinstaller --onefile --noconsole --name PDFTrimmer ^
    --collect-all pymupdf ^
    --exclude-module matplotlib ^
    --exclude-module scipy ^
    --exclude-module pandas ^
    --exclude-module IPython ^
    --exclude-module notebook ^
    --exclude-module pytest ^
    %UPX_FLAG% ^
    main.py

echo.
echo Build finished. Find the exe at dist\PDFTrimmer.exe
pause
