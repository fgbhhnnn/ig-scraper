# Windows 端到端自动更新测试：旧 exe(当前版本) -> 新 exe(9.9.9)，路径含空格和中文
$ErrorActionPreference = 'Stop'
$dir = 'C:\upd test\更新 测试'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item dist_old\Social-Scraper.exe "$dir\Social-Scraper.exe"
New-Item -ItemType Directory -Force -Path srv | Out-Null
Copy-Item dist_new\Social-Scraper.exe srv\new.exe
$srv = Start-Process python -ArgumentList '-m','http.server','8000','--directory','srv' -PassThru -WindowStyle Hidden
$env:IGS_UPDATE_ALLOW_LOCAL = '1'
Start-Process "$dir\Social-Scraper.exe" -WorkingDirectory $dir
function Ping8765 { try { (Invoke-RestMethod http://127.0.0.1:8765/api/ping -TimeoutSec 3) } catch { $null } }
for ($i=0; $i -lt 90; $i++) { $p = Ping8765; if ($p) { break }; Start-Sleep 1 }
if (-not $p) { throw '旧版本没有启动' }
Write-Host "old version: $($p.version)"
$old = $p.version
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/update/download -ContentType 'application/json' -Body '{"url":"http://127.0.0.1:8000/new.exe"}' | Out-Host
for ($i=0; $i -lt 120; $i++) { $s = Invoke-RestMethod http://127.0.0.1:8765/api/update/status; if ($s.state -ne 'downloading') { break }; Start-Sleep 1 }
Write-Host "download: $($s.state) $($s.error)"
if ($s.state -ne 'ready') { throw '下载失败' }
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/update/apply -ContentType 'application/json' -Body '{}' | Out-Host
Start-Sleep 3
$ok = $false
for ($i=0; $i -lt 120; $i++) { $p = Ping8765; if ($p -and $p.version -ne $old) { $ok = $true; break }; Start-Sleep 1 }
Write-Host '---- update.log ----'; Get-Content "$dir\update.log" -Encoding UTF8 -ErrorAction SilentlyContinue | Out-Host
Write-Host '---- files ----'; Get-ChildItem $dir | Out-Host
Write-Host '---- cmd processes ----'; Get-Process cmd -ErrorAction SilentlyContinue | Out-Host
Stop-Process -Id $srv.Id -ErrorAction SilentlyContinue
if (-not $ok) { throw "更新后新版本没有启动（ping=$($p | ConvertTo-Json -Compress)）" }
Write-Host "UPDATED OK: $old -> $($p.version)"
Start-Sleep 3
if (Test-Path "$dir\Social-Scraper.exe.old") { Write-Host 'WARN: .old 未清理' } else { Write-Host '.old 已清理' }
if (Test-Path "$dir\_update.bat") { throw '_update.bat 没有删除' }
