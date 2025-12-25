@echo off
REM Installation script for Video Editing Automation System (Windows)

echo =======================================================================
echo VIDEO EDITING AUTOMATION SYSTEM - INSTALLATION SCRIPT (WINDOWS)
echo =======================================================================
echo.

REM STEP 1: Check Python
echo =======================================================================
echo STEP 1: Checking Python Installation
echo =======================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

python --version
echo [OK] Python is installed
echo.

REM Check pip
where pip >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pip is not installed
    echo.
    echo Please reinstall Python and ensure pip is included
    pause
    exit /b 1
)

echo [OK] pip is installed
echo.

REM STEP 2: Check FFmpeg
echo =======================================================================
echo STEP 2: Checking FFmpeg Installation
echo =======================================================================
echo.

where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] FFmpeg is not installed or not in PATH
    echo.
    echo Please install FFmpeg:
    echo 1. Download from: https://www.gyan.dev/ffmpeg/builds/
    echo 2. Extract the archive
    echo 3. Add the bin folder to your system PATH
    echo.
    echo Or install via Chocolatey:
    echo    choco install ffmpeg
    echo.
    pause
    exit /b 1
)

ffmpeg -version | findstr /C:"ffmpeg version"
echo [OK] FFmpeg is installed
echo.

where ffprobe >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] FFprobe is not installed (should come with FFmpeg)
    pause
    exit /b 1
)

echo [OK] FFprobe is installed
echo.

REM STEP 3: Create virtual environment
echo =======================================================================
echo STEP 3: Setting Up Python Virtual Environment
echo =======================================================================
echo.

if exist "venv" (
    echo [INFO] Virtual environment already exists
) else (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

echo.
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat
echo [OK] Virtual environment activated
echo.

REM STEP 4: Install Python dependencies
echo =======================================================================
echo STEP 4: Installing Python Dependencies
echo =======================================================================
echo.

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
echo.

echo [INFO] Installing required packages (this may take several minutes)...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [OK] All Python dependencies installed
echo.

REM STEP 5: Verify installations
echo =======================================================================
echo STEP 5: Verifying Installation
echo =======================================================================
echo.

echo [INFO] Verifying Flask installation...
python -c "import flask; print('Flask version:', flask.__version__)"
if %ERRORLEVEL% EQU 0 (
    echo [OK] Flask is working
) else (
    echo [ERROR] Flask verification failed
)
echo.

echo [INFO] Verifying Whisper installation...
python -c "import whisper; print('Whisper OK')"
if %ERRORLEVEL% EQU 0 (
    echo [OK] Whisper is working
) else (
    echo [ERROR] Whisper verification failed
)
echo.

REM STEP 6: Create necessary directories
echo =======================================================================
echo STEP 6: Creating Required Directories
echo =======================================================================
echo.

if not exist "uploads" mkdir uploads
echo [OK] Created: uploads\

if not exist "temp" mkdir temp
echo [OK] Created: temp\

if not exist "output" mkdir output
echo [OK] Created: output\

if not exist "sample_data" mkdir sample_data
echo [OK] Created: sample_data\

echo.

REM STEP 7: Final summary
echo =======================================================================
echo INSTALLATION COMPLETE
echo =======================================================================
echo.
echo [SUCCESS] All components installed successfully!
echo.
echo =======================================================================
echo NEXT STEPS:
echo =======================================================================
echo.
echo 1. Start the API server:
echo    python backend\api.py
echo.
echo 2. Open your browser to:
echo    http://localhost:5000
echo.
echo 3. Or use the backend directly:
echo    python backend\main.py
echo.
echo =======================================================================
echo NOTES:
echo =======================================================================
echo.
echo  * Virtual environment is in: .\venv
echo  * To activate it: venv\Scripts\activate.bat
echo  * To deactivate: deactivate
echo.
echo  * Upload files to: .\uploads
echo  * Output videos in: .\output
echo  * Temporary files in: .\temp
echo.
echo  * For sample data, add test files to: .\sample_data
echo.
echo =======================================================================
echo.

pause
