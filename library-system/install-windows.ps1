# ============================================================
#  NEXUS 图书馆数字管理系统 · Windows 一键安装
#  作用：把本文件夹复制到 D:\NexusLibrary，并在桌面创建快捷方式
#  用法：右键本文件 →「使用 PowerShell 运行」
#        或在 PowerShell 里执行： .\install-windows.ps1
# ============================================================
$ErrorActionPreference = 'Stop'

# 目标目录（如需改安装位置，改这里即可）
$dest = 'D:\NexusLibrary'
$src  = $PSScriptRoot

Write-Host ''
Write-Host '  NEXUS 图书馆系统 · 安装程序' -ForegroundColor Cyan
Write-Host '  ----------------------------------------'

# 1) 检查 D 盘是否存在
if (-not (Test-Path 'D:\')) {
    Write-Host '  [错误] 未检测到 D 盘，请改用其它盘符（编辑脚本里的 $dest）。' -ForegroundColor Red
    Read-Host '  按回车退出'; exit 1
}

# 2) 复制文件到 D 盘
Write-Host "  正在复制文件到 $dest ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path (Join-Path $src '*') -Destination $dest -Recurse -Force
Write-Host '  [✓] 文件复制完成' -ForegroundColor Green

# 3) 在桌面创建快捷方式（指向 index.html，用默认浏览器打开）
$index   = Join-Path $dest 'index.html'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop '图书馆管理系统.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath       = $index
$sc.WorkingDirectory = $dest
$sc.Description       = 'NEXUS 图书馆数字管理系统'
# 用系统自带的图书馆/书本图标（可按需替换）
$sc.IconLocation     = "$env:SystemRoot\System32\imageres.dll,174"
$sc.Save()
Write-Host "  [✓] 桌面快捷方式已创建：图书馆管理系统" -ForegroundColor Green

Write-Host '  ----------------------------------------'
Write-Host '  安装完成！双击桌面「图书馆管理系统」即可打开。' -ForegroundColor Cyan
Write-Host ''
Read-Host '  按回车退出'
