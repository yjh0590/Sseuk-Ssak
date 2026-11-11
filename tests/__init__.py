import sys
from pathlib import Path

# 테스트 대상 모듈은 배포 폴더의 app/ 에 있다
APP = next(Path(__file__).resolve().parents[1].glob('Sseuk-Ssak-*/app'))
sys.path.insert(0, str(APP))
