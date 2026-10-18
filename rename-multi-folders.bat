$i = 1
Get-ChildItem -Directory | ForEach-Object { Rename-Item $_ -NewName "Folder$i$($_.Extension)"; $i++ }