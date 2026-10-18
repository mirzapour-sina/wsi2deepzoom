$i = 1
Get-ChildItem -File | ForEach-Object { Rename-Item $_ -NewName "File$i$($_.Extension)"; $i++ }