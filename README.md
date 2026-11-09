# Sseuk-Ssak
쓱싹 컴퓨터 파일 정리 프로그램 (Windows x64 포터블)

## 구조
```
Sseuk-Ssak-Smart-Update18-Windows-x64/   배포 폴더
├─ 쓱-싹.exe                             실행 파일 (app\python\pythonw.exe -E -s -B desktop.py 실행)
├─ README_처음_사용하기.{txt,html}        사용자 안내
├─ 폴더_여러개_정리_안내.txt
├─ 크롬 다운로드 연결 도우미/             크롬 확장 (압축해제된 확장으로 등록)
└─ app/                                  앱 본체 (Python + HTML/JS UI)
   ├─ desktop.py                         진입점 · 로컬 서버 · App(작업별 메서드)
   ├─ python/                            Python 3.13 런타임 (git 미포함, build.py가 생성)
   ├─ 사용법.txt                         상세 사용법 및 변경 이력
   └─ fonts/
tests/                                   단위 테스트 (배포에 포함하지 않음)
build.py                                 런타임 복사 · 배포 ZIP 생성
```

## 처음 받았을 때
Python 3.9 이상 아무 버전과 인터넷 연결이 있으면 됩니다.
```
py build.py runtime     # app/python 런타임 생성
```
python.org의 공식 Python 3.13.17 MSI를 받아 **Python Software Foundation 서명을 검증한 뒤** 설치 없이 파일만 풀어 씁니다(`msiexec /a`).
3.13.18부터는 보안 수정 전용 릴리스라 Windows 바이너리가 배포되지 않으므로, 서명된 최신 버전인 3.13.17로 고정했습니다(`build.py`의 `PY_VERSION`).

## 테스트
```
Sseuk-Ssak-Smart-Update18-Windows-x64\app\python\python.exe -m unittest discover -s tests -t .
```
`test_security`는 심볼릭 링크를 만들므로 관리자 권한 또는 Windows 개발자 모드가 필요합니다.

## 포맷 · 린트
설정은 `ruff.toml`에 있습니다.
```
ruff format .
ruff check .
```

## 배포
```
py build.py dist        # dist/Sseuk-Ssak-v<버전>-Portable-Windows-x64.zip
```
버전은 `크롬 다운로드 연결 도우미/manifest.json`의 `version`을 씁니다.
개인 데이터(`pair.json`, `chrome-last-result.json`, `display-backup/`)와 캐시는 ZIP에서 자동으로 빠집니다.
