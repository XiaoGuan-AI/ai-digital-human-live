[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$out = @()
Get-Process msedge -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowTitle -ne '' } |
  ForEach-Object { $out += ("{0}`t{1}" -f $_.Id, $_.MainWindowTitle) }
$out | Set-Content -Path "D:\Projects\ai-digital-human-live\logs\_edge_windows.txt" -Encoding UTF8
$out
