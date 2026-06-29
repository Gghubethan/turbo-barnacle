@echo off
chcp 65001 >nul
REM ============================================================
REM  NEXUS 图书馆系统 · 一键安装（双击运行本文件）
REM  绕过 PowerShell 执行策略调用 install-windows.ps1
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-windows.ps1"
