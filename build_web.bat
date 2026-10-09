@echo off
setlocal

rem Rebuilds the OpenLaraBW WebAssembly build using the current contents of DATA\.
rem Run this any time the TR2 data files (DATA\ASSAULT.TR2, DATA\TITLE.tr2, DATA\MAIN.SFX, DATA\TITLE.PCX) change.

set "PROJECT_ROOT=%~dp0"
set "EMSDK_ENV=%PROJECT_ROOT%..\emsdk\emsdk_env.bat"
set "WEB_SRC_DIR=%PROJECT_ROOT%engine\src\platform\web"
set "OUT_DIR=%PROJECT_ROOT%web"

if not exist "%EMSDK_ENV%" (
    echo [ERROR] emsdk_env.bat not found at "%EMSDK_ENV%"
    exit /b 1
)

call "%EMSDK_ENV%"
if errorlevel 1 (
    echo [ERROR] Failed to initialize emsdk environment.
    exit /b 1
)

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

pushd "%WEB_SRC_DIR%"

set "SRC=main.cpp ../../libs/stb_vorbis/stb_vorbis.c ../../libs/tinf/tinflate.c"
set "FLAGS=-s WASM=1 -s ALLOW_MEMORY_GROWTH=1 -O3 -ffast-math -Wno-deprecated-register -fmax-type-align=2 -std=c++11 -s USE_WEBGL2=1 -s EXPORTED_RUNTIME_METHODS=ccall,cwrap,getValue,setValue -s EXPORTED_FUNCTIONS=_malloc,_main -Wall -Wno-invalid-source-encoding -I../../"
set "PRELOAD=--preload-file ../../../../DATA/ASSAULT.TR2@/assault.TR2 --preload-file ../../../../DATA/TITLE.tr2@/title.TR2 --preload-file ../../../../DATA/MAIN.SFX@/audio/2/MAIN.SFX --preload-file ../../../../DATA/TITLE.PCX@/data/TITLE.PCX"

echo Building OpenLaraBW...
em++ %SRC% %FLAGS% -o ../../../../web/OpenLaraBW.html --shell-file shell_inkraider.html %PRELOAD%
set "BUILD_RESULT=%ERRORLEVEL%"

popd

if not "%BUILD_RESULT%"=="0" (
    echo [ERROR] Build failed with exit code %BUILD_RESULT%.
    exit /b %BUILD_RESULT%
)

echo.
echo Build succeeded. Output: %OUT_DIR%\OpenLaraBW.html
endlocal
