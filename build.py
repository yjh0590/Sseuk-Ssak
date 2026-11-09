"""배포 준비 스크립트. 저장소에는 소스만 두고, 런타임과 ZIP은 여기서 만든다.

  py -3.13 build.py runtime   이 Python 3.13 설치본에서 app/python 런타임을 다시 복사
  py -3.13 build.py dist      dist/ 에 배포용 ZIP 생성 (런타임이 없으면 먼저 복사)

쓱-싹.exe가 app/python/pythonw.exe -E -s -B desktop.py 를 실행하므로 런타임 위치는 고정이다.
"""

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = next(ROOT.glob('Sseuk-Ssak-*-Windows-x64'))
RUNTIME = PKG / 'app' / 'python'
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


def runtime():
    if sys.version_info[:2] != (3, 13):
        sys.exit('Python 3.13으로 실행해 주세요: py -3.13 build.py runtime')
    src = Path(sys.base_prefix)

    def skip(directory, names):
        out = {n for n in names if n == '__pycache__' or n.endswith(('.lib', '.ico', '.cat'))}
        if Path(directory) == src / 'Lib':
            out |= {'test', 'site-packages'}  # 표준 라이브러리 테스트와 사용자 설치 패키지는 제외
        return out

    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    for name in TOP_FILES:
        shutil.copy2(src / name, RUNTIME / name)
    for name in ('DLLs', 'Lib', 'tcl'):
        shutil.copytree(src / name, RUNTIME / name, ignore=skip)
    print(f'런타임 복사 완료: Python {sys.version.split()[0]} → {RUNTIME}')


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
