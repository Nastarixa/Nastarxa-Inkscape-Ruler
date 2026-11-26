@echo off
setlocal
rem Use the managed installer so preset INX files and metadata are installed too.
if not defined APPDATA set "APPDATA=%USERPROFILE%\AppData\Roaming"
set "DST=%APPDATA%\inkscape\extensions\nastarixa.inkscape.ruler"
if not exist "%DST%" mkdir "%DST%"
call "%~dp0install_managed.bat" %*
endlocal
