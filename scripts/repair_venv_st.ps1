# Repair venv-st: restore pristine torch stack, precise-patch offenders.
$ErrorActionPreference = 'Continue'
$env:UV_CACHE_DIR = 'D:\develop\workspace\lingnan-curator\.uv-cache'
Set-Location D:\develop\workspace\lingnan-curator
$st = 'D:\develop\workspace\lingnan-curator\models\vendor\venv-st\Scripts\python.exe'
$sp = 'D:\develop\workspace\lingnan-curator\models\vendor\venv-st\Lib\site-packages'

Write-Output '=== [1/4] reinstall torch stack from cache (pristine) ==='
uv pip install --python $st --reinstall-package torch --reinstall-package torchvision torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121 2>&1 | Select-Object -Last 1

Write-Output '=== [2/4] facexlib + gfpgan (--no-deps, retry after earlier abort) ==='
uv pip install --python $st --no-deps "basicsr==1.4.2" "facexlib==0.3.0" "gfpgan==1.3.8" --no-build 2>&1 | Select-Object -Last 2
Write-Output '(basicsr build expected to fail again; vendored copy already in site-packages)'
& $st -c "import facexlib, gfpgan" 2>&1 | Select-Object -Last 1

Write-Output '=== [3/4] precise patch: import-statement form only ==='
$hits = Get-ChildItem $sp -Recurse -Filter *.py |
  Select-String -Pattern 'from torchvision\.transforms\.functional_tensor import' -List
foreach ($h in $hits) {
  $p = $h.Path
  (Get-Content $p -Raw) -replace 'from torchvision\.transforms\.functional_tensor import', 'from torchvision.transforms.functional import' |
    Set-Content $p -Encoding utf8
  Write-Output ("patched: " + $p.Substring($sp.Length))
}

Write-Output '=== [4/4] import probe ==='
& $st -c "import torch, numpy, librosa, basicsr, facexlib, gfpgan, imageio_ffmpeg, face_alignment; print('ST deps OK cuda=', torch.cuda.is_available())" 2>&1 | Select-Object -Last 3
