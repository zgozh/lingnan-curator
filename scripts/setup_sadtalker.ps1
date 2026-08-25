# SadTalker standalone env setup (py3.10 + cu121). ASCII only (PS5.1-safe).
# Idempotent: skips steps already done.
$ErrorActionPreference = 'Continue'
$env:UV_CACHE_DIR = 'D:\develop\workspace\lingnan-curator\.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = 'D:\develop\workspace\lingnan-curator\.uv-cache\pythons'
Set-Location D:\develop\workspace\lingnan-curator

$st = 'D:\develop\workspace\lingnan-curator\models\vendor\venv-st\Scripts\python.exe'
if (-not (Test-Path $st)) {
  Write-Output '=== [1/5] venv ==='
  uv venv models/vendor/venv-st --python 3.10 2>&1 | Select-Object -Last 1
} else { Write-Output '=== [1/5] venv exists, skip ===' }

Write-Output '=== [2/5] torch cu121 ==='
& $st -c "import torch" 2>$null
if ($LASTEXITCODE -ne 0) {
  uv pip install --python $st torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121 2>&1 | Select-Object -Last 1
} else { Write-Output 'torch ok, skip' }

Write-Output '=== [3/5] explicit deps (no basicsr-chain/gradio) ==='
# numba pinned 0.57.1: last mainline compatible with numpy 1.23, avoids sdist build
uv pip install --python $st setuptools "numpy==1.23.4" "face_alignment==1.3.5" "imageio==2.19.3" "imageio-ffmpeg==0.4.7" "librosa==0.9.2" "numba==0.57.1" "resampy==0.3.1" "pydub==0.25.1" "scipy==1.10.1" "kornia==0.6.8" tqdm "yacs==0.1.8" pyyaml "joblib==1.1.0" "scikit-image==0.19.3" safetensors 2>&1 | Select-Object -Last 2

Write-Output '=== [4/5] basicsr chain --no-deps + functional_tensor patch ==='
& $st -c "import basicsr" 2>$null
if ($LASTEXITCODE -ne 0) {
  uv pip install --python $st --no-deps "basicsr==1.4.2" "facexlib==0.3.0" "gfpgan==1.3.8" 2>&1 | Select-Object -Last 1
} else { Write-Output 'basicsr ok, skip install (patch still runs)' }
$ft = Get-ChildItem -Recurse -Filter functional_tensor.py -Path models/vendor/venv-st/Lib/site-packages/basicsr -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ft) {
  (Get-Content $ft.FullName -Raw) -replace 'torchvision.transforms.functional_tensor', 'torchvision.transforms.functional' | Set-Content $ft.FullName -Encoding utf8
  Write-Output 'patched functional_tensor(st)'
} else { Write-Output 'WARN st functional_tensor missing (basicsr not installed?)' }

Write-Output '=== [5/5] import probe ==='
& $st -c "import torch, numpy, librosa, basicsr, facexlib, gfpgan, imageio_ffmpeg, face_alignment; print('ST deps OK cuda=', torch.cuda.is_available())" 2>&1 | Select-Object -Last 3
