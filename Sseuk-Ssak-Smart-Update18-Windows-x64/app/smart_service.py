"""Independent smart organization API; never imports or starts desktop services."""
import tempfile
from pathlib import Path
from smart_rules import Organizer, RuleViolation

class SmartService:
    def __init__(self):
        self.root = None
        self.manager = None
        self.current = '.'
        self.demo = False

    def select(self, root, demo=False):
        candidate = Path(root).resolve()
        if not candidate.is_dir():
            raise RuleViolation('존재하는 관리 폴더를 선택해 주세요.')
        manager = Organizer(candidate)
        # Fail before changing the current session on invalid state.
        manager.load_favorites()
        self.root, self.manager = candidate, manager
        self.current, self.demo = '.', demo
        return self.snapshot()

    def snapshot(self):
        if not self.manager:
            return {'root':'', 'current':'.', 'items':[], 'favorites':[], 'demo':False}
        folder = self.manager.path(self.current)
        if not folder.is_dir():
            self.current = '.'
            folder = self.root
        items = []
        for p in sorted(folder.iterdir(), key=lambda x:(not x.is_dir(),x.name.casefold())):
            if p.name == '.smart_organizer.json':
                continue
            items.append({'name':p.name,'path':str(p.relative_to(self.root)), 'folder':p.is_dir(), 'link':p.is_symlink() or p.is_junction() if hasattr(p,'is_junction') else p.is_symlink()})
        return {'root':str(self.root), 'current':self.current, 'items':items,
                'favorites':self.manager.load_favorites(), 'demo':self.demo}

    def handle(self, data):
        op = data.get('op', 'list')
        if op == 'demo':
            return self.make_demo()
        if not self.manager:
            if op == 'list': return self.snapshot()
            raise RuleViolation('먼저 관리 폴더를 선택하거나 가상 테스트를 시작해 주세요.')
        m = self.manager
        if op == 'list':
            if 'folder' in data:
                p = m.path(data['folder'])
                if not p.is_dir(): raise RuleViolation('폴더가 존재하지 않습니다.')
                self.current = str(p.relative_to(self.root))
            return self.snapshot()
        if op == 'mkdir':
            result = m.mkdir(self.current, data['name'], data.get('kind','general'), int(data['number']) if data.get('number') else None, data.get('when') or None)
        elif op == 'create':
            if Path(data['name']).suffix.lower() not in {'.txt','.md','.csv'}:
                raise RuleViolation('새 텍스트 문서는 .txt, .md, .csv 확장자로 생성해 주세요.')
            result = m.create(str(Path(self.current)/data['name']), data.get('text',''), data.get('category') or None, data.get('date') or None)
        elif op in ('move','rename'):
            result = m.transfer(data['source'], data['target'], data.get('category') or None, data.get('date') or None)
        elif op == 'revise':
            if Path(data['source']).suffix.lower() not in {'.txt','.md','.csv'}:
                raise RuleViolation('수정본 저장은 텍스트 문서(.txt/.md/.csv)만 지원합니다.')
            result = m.save_revision(data['source'], data.get('text',''))
        elif op == 'archive':
            result = m.archive(data['source'])
        elif op == 'favorite':
            result = m.favorite(data['action'], data['target'])
        else:
            raise RuleViolation('지원하지 않는 정리 작업입니다.')
        return dict(self.snapshot(), result=result)

    def make_demo(self):
        # A new dedicated directory is used each time. Existing user files are untouched.
        root = Path(tempfile.mkdtemp(prefix='SseukSsak-Smart-Demo-'))
        self.select(root, demo=True)
        m = self.manager
        report = []
        def check(label, fn, reject=False):
            try:
                value = fn()
                report.append({'test':label, 'passed':not reject, 'message':value.get('실행 결과','완료')})
            except (ValueError, OSError) as exc:
                report.append({'test':label, 'passed':reject, 'message':str(exc)})
        check('일반 폴더 넘버링',lambda:m.mkdir('.', '업무', number=2))
        check('미디어 시간 접두사',lambda:m.mkdir('.', '여행', kind='media', when='2026_11'))
        check('단기 프로젝트 분기 접두사',lambda:m.mkdir('.', '개편', kind='project', when='2026-4Q'))
        check('문서 생성 v1.0',lambda:m.create('02_업무/기획안.txt','가상 기획안'))
        check('수정본 v1.1',lambda:m.save_revision('02_업무/기획안_v1.0.txt','가상 수정본'))
        check('금지어 차단',lambda:m.create('02_업무/최종_기획안.txt'),True)
        check('계약 날짜 누락 차단',lambda:m.create('02_업무/근로계약서.txt'),True)
        check('계약 날짜 병합',lambda:m.create('02_업무/근로계약서.txt',document_date='2026_11_04'))
        current='.'
        for i in range(5):
            current=m.mkdir(current,'깊이테스트',number=1)['적용된 경로/파일명']
        check('6단계 폴더 생성 차단',lambda:m.mkdir(current,'초과',number=1),True)
        check('99번 일반 폴더 차단',lambda:m.mkdir('.','일반',number=99),True)
        check('아카이브 이동',lambda:m.archive('02_업무/기획안_v1.0.txt'))
        favorites=['02_업무','2026_11_여행','2026-4Q_개편','01_깊이테스트','99_아카이브']
        for item in favorites: m.favorite('add',item)
        check('즐겨찾기 6개째 차단',lambda:m.favorite('add','02_업무/기획안_v1.1.txt'),True)
        return dict(self.snapshot(), report=report, result={'실행 결과':'가상 테스트 완료','적용된 경로/파일명':str(root),'안내 메시지':f'{sum(x["passed"] for x in report)}/{len(report)}개 검사 통과. 테스트 파일은 이 임시 폴더에만 생성되며 종료 후에도 남습니다.'})
