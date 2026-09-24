@echo off
cd /d "%~dp0"
cls
echo ========================================================
echo   [Misa Family Trip] GitHub Upload Helper
echo ========================================================
echo.
echo   * Starting git push to GitHub...
echo   * If a browser/screen popup appears, please click [Sign in] or [Authorize].
echo.
git push -u origin main
echo.
if %ERRORLEVEL% equ 0 (
    echo ========================================================
    echo   [SUCCESS] Upload complete!
    echo ========================================================
) else (
    echo ========================================================
    echo   [NOTICE] Upload failed or was canceled.
    echo ========================================================
)
echo.
pause