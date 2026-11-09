"""배포 준비 스크립트. 저장소에는 소스만 두고, 런타임과 ZIP은 여기서 만든다. (Python 3.9+ 아무 버전으로 실행)

  py build.py runtime   python.org 공식 MSI(서명 검증)에서 app/python 런타임을 만든다 (인터넷 필요)
  py build.py dist      dist/ 에 배포용 ZIP 생성 (런타임이 없으면 먼저 만든다)

쓱-싹.exe가 app/python/pythonw.exe -E -s -B desktop.py 를 실행하므로 런타임 위치는 고정이다.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = next(ROOT.glob('Sseuk-Ssak-*-Windows-x64'))
RUNTIME = PKG / 'app' / 'python'
# python.org에 서명된 Windows 바이너리가 있는 최신 3.13. 3.13.18부터는 보안 수정 전용이라 소스만 배포된다.
PY_VERSION = '3.13.17'
MSIS = ('core', 'exe', 'lib', 'tcltk')
CACHE = ROOT / 'build' / f'python-{PY_VERSION}'
TOP_FILES = [
    'python.exe',
    'pythonw.exe',
    'python3.dll',
    'python313.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'LICENSE.txt',
]
# 사용 중에 생기는 개인 설정/결과. 배포 ZIP에 절대 넣지 않는다.
PERSONAL = {'chrome-last-result.json', 'pair.json', 'display-backup', '__pycache__'}


def verify(path, publisher='Python Software Foundation'):
    """Authenticode 서명이 유효하고 서명자가 publisher인지 확인한다."""
    r = subprocess.run(
        [
            'powershell.exe',
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            '$s=Get-AuthenticodeSignature -LiteralPath $env:SIGNED_FILE; "$($s.Status)|$($s.SignerCertificate.Subject)"',
        ],
        env={**os.environ, 'SIGNED_FILE': str(path)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    status, _, subject = r.stdout.strip().partition('|')
    if status != 'Valid' or not subject.startswith(f'CN={publisher},'):
        sys.exit(f'서명 검증 실패: {path} ({status or r.stderr.strip()} {subject})')


def runtime():
    msi_dir, staging = CACHE / 'msi', CACHE / 'files'
    msi_dir.mkdir(parents=True, exist_ok=True)
    for name in MSIS:
        msi = msi_dir / f'{name}.msi'
        if not msi.exists():
            print(f'다운로드: {name}.msi')
            urllib.request.urlretrieve(f'https://www.python.org/ftp/python/{PY_VERSION}/amd64/{name}.msi', msi)
        verify(msi)
    if staging.exists():
        shutil.rmtree(staging)
    for name in MSIS:  # 관리자 설치(/a): 시스템에 설치하지 않고 파일만 푼다
        subprocess.run(f'msiexec /a "{msi_dir / name}.msi" /qn TARGETDIR="{staging}"', check=True)

    def skip(directory, names):
        out = {n for n in names if n == '__pycache__' or n.endswith(('.lib', '.ico', '.cat', '.msi'))}
        if Path(directory) == staging / 'Lib':
            out.add('site-packages')
        if Path(directory) == staging / 'tcl':
            out.add('nmake')  # Tcl 빌드 도구. 실행에 쓰이지 않고 공식 MSI에서도 서명이 없다
        return out

    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    for name in TOP_FILES:
        shutil.copy2(staging / name, RUNTIME / name)
    for name in ('DLLs', 'Lib', 'tcl'):
        shutil.copytree(staging / name, RUNTIME / name, ignore=skip)
    verify(RUNTIME / 'python.exe')
    print(f'런타임 준비 완료: 공식 서명된 Python {PY_VERSION} → {RUNTIME}')


def dist():
    if not (RUNTIME / 'pythonw.exe').is_file():
        runtime()
    version = json.loads((PKG / '크롬 다운로드 연결 도우미' / 'manifest.json').read_text(encoding='utf-8'))['version']
    out = ROOT / 'dist' / f'Sseuk-Ssak-v{version}-Portable-Windows-x64.zip'
    out.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PKG.rglob('*')):
            rel = p.relative_to(PKG)
            if p.is_file() and not PERSONAL & set(rel.parts):
                z.write(p, Path(out.stem) / rel)
                count += 1
    print(f'{out} ({count}개 파일, {out.stat().st_size / 1024**2:.1f} MB)')


if __name__ == '__main__':
    commands = {'runtime': runtime, 'dist': dist}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
