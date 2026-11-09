#!/usr/bin/env python3
"""스마트 파일 정리 도구. Python 3.10+, 외부 의존성 없음."""

import argparse
import json
import re
from datetime import date
from pathlib import Path

MAX_DEPTH = 5
MAX_FAVORITES = 5
ARCHIVE = '99_아카이브'
DEPTH_WARNING = '폴더 깊이는 최대 5단계까지만 허용됩니다.'
FAVORITES_WARNING = '즐겨찾기는 최대 5개까지만 등록 가능합니다. 기존 항목을 삭제 후 추가해 주세요.'
KEYWORDS = (
    '회의록',
    '기획안',
    '양식',
    '보고서',
    '제안서',
    '계획서',
    '문서',
    '계약',
    '정산',
    '증빙',
    '영수증',
    '세금계산서',
)
FINANCIAL = ('정산', '증빙', '계약', '영수증', '세금계산서')
DOCUMENT_EXTS = {
    '.pdf',
    '.doc',
    '.docx',
    '.hwp',
    '.hwpx',
    '.txt',
    '.md',
    '.odt',
    '.ppt',
    '.pptx',
    '.xls',
    '.xlsx',
    '.csv',
}
VERSION = re.compile(r'_v(\d+)\.(\d+)$')


class RuleViolation(ValueError):
    pass


class Organizer:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = self.root / '.smart_organizer.json'

    def result(self, action, path=None, message='정리 기준을 적용했습니다.'):
        return {
            '실행 결과': action,
            '적용된 경로/파일명': str(path.relative_to(self.root)) if path else '-',
            '안내 메시지': message,
        }

    def path(self, relative):
        p = Path(relative)
        if p.is_absolute() or '..' in p.parts:
            raise RuleViolation('관리 폴더 내부의 상대 경로만 허용됩니다.')
        q = self.root / p
        # 링크를 통한 관리 범위 이탈과 우회 작업 방지
        for node in [q, *q.parents]:
            if node == self.root:
                break
            if node.is_symlink() or (hasattr(node, 'is_junction') and node.is_junction()):
                raise RuleViolation('심볼릭 링크 경로는 사용할 수 없습니다.')
        if not q.resolve().is_relative_to(self.root):
            raise RuleViolation('관리 폴더 밖으로 접근할 수 없습니다.')
        if q == self.state:
            raise RuleViolation('내부 설정 파일은 직접 변경할 수 없습니다.')
        return q

    def valid_component(self, name):
        if not name or name in {'.', '..'} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((' ', '.')):
            raise RuleViolation('사용할 수 없는 이름입니다.')
        if name.split('.')[0].upper() in {
            'CON',
            'PRN',
            'AUX',
            'NUL',
            *[f'COM{i}' for i in range(1, 10)],
            *[f'LPT{i}' for i in range(1, 10)],
        }:
            raise RuleViolation('운영체제 예약 이름은 사용할 수 없습니다.')

    def folder_name(self, name):
        self.valid_component(name)
        if name == ARCHIVE:
            return
        if name.startswith('99'):
            raise RuleViolation('99번 폴더는 99_아카이브(종료/보관) 전용입니다.')
        if re.fullmatch(r'(?:0[1-9]|[1-8][0-9]|9[0-8])_.+', name):
            return
        if re.fullmatch(r'\d{4}(?:_(?:0[1-9]|1[0-2]))?_.+', name):
            return
        if re.fullmatch(r'\d{4}-[1-4]Q_.+', name):
            return
        raise RuleViolation(
            '일반 폴더는 01~98_이름, 미디어는 YYYY_이름 또는 YYYY_MM_이름, 단기 프로젝트는 YYYY-nQ_이름을 사용하세요.'
        )

    def check_folders(self, folder):
        parts = folder.relative_to(self.root).parts
        if len(parts) > MAX_DEPTH:
            raise RuleViolation(DEPTH_WARNING + ' 상위 폴더로 통합해 주세요.')
        for part in parts:
            self.folder_name(part)

    def parent(self, p):
        self.check_folders(p.parent)
        if not p.parent.is_dir():
            raise RuleViolation('상위 폴더를 먼저 생성해 주세요.')

    def mkdir(self, parent, name, kind='general', number=None, when=None):
        base = self.path(parent)
        if not base.is_dir():
            raise RuleViolation('상위 폴더가 존재하지 않습니다.')
        self.valid_component(name)
        if kind == 'archive':
            full = ARCHIVE
        elif kind == 'general':
            if number is None or not 1 <= number <= 98:
                raise RuleViolation('일반 폴더 번호는 1~98이어야 합니다.')
            full = f'{number:02d}_{name}'
        elif kind == 'media':
            prefix = when or date.today().strftime('%Y_%m')
            if not re.fullmatch(r'\d{4}(?:_(?:0[1-9]|1[0-2]))?', prefix):
                raise RuleViolation('미디어 날짜는 YYYY 또는 YYYY_MM 형식이어야 합니다.')
            full = f'{prefix}_{name}'
        elif kind == 'project':
            prefix = when or f'{date.today().year}-{(date.today().month - 1) // 3 + 1}Q'
            if not re.fullmatch(r'\d{4}-[1-4]Q', prefix):
                raise RuleViolation('프로젝트 날짜는 YYYY-nQ 형식이어야 합니다.')
            full = f'{prefix}_{name}'
        else:
            raise RuleViolation('알 수 없는 폴더 종류입니다.')
        p = self.path(str(base.relative_to(self.root) / full))
        self.check_folders(p)
        p.mkdir()  # 기존 폴더는 덮어쓰지 않음
        return self.result('폴더 생성 완료', p)

    def normalize_file(self, name, category=None, document_date=None):
        self.valid_component(name)
        if category and any(word in category for word in ('최종', '진짜', '마지막')):
            raise RuleViolation('분류에도 최종·진짜·마지막을 사용할 수 없습니다.')
        if any(word in name for word in ('최종', '진짜', '마지막')):
            raise RuleViolation("파일명에 '최종', '진짜', '마지막'을 사용할 수 없습니다. 버전 번호를 사용하세요.")
        p = Path(name)
        stem, ext = p.stem, p.suffix
        if category:
            self.valid_component(category)
            if category not in stem:
                stem = category + '_' + stem
        if any(word in stem for word in FINANCIAL):
            dates = re.findall(r'(?<!\d)\d{4}_\d{2}_\d{2}(?!\d)', stem)
            for token in dates:
                try:
                    date.fromisoformat(token.replace('_', '-'))
                except ValueError:
                    raise RuleViolation('파일명에 유효하지 않은 날짜가 있습니다.')
            if not dates:
                if not document_date:
                    raise RuleViolation('정산·증빙·계약 서류는 --date YYYY_MM_DD로 실제 서류 날짜를 지정해 주세요.')
                try:
                    if not re.fullmatch(r'\d{4}_\d{2}_\d{2}', document_date):
                        raise ValueError()
                    date.fromisoformat(document_date.replace('_', '-'))
                except ValueError:
                    raise RuleViolation('날짜는 유효한 YYYY_MM_DD 형식이어야 합니다.')
                stem = document_date + '_' + stem
        if ext.lower() in DOCUMENT_EXTS and not any(word in stem for word in KEYWORDS):
            raise RuleViolation(
                '일반 문서는 회의록·기획안·양식 등 키워드를 포함하세요. --category로 지정할 수 있습니다.'
            )
        return stem + ext

    def versioned(self, dest, revision=False):
        match = VERSION.search(dest.stem)
        base = dest.stem[: match.start()] if match else dest.stem
        major, minor = (int(match[1]), int(match[2])) if match else (1, 0)
        if revision:
            minor += 1
        while True:
            candidate = dest.with_name(f'{base}_v{major}.{minor}{dest.suffix}')
            if not candidate.exists():
                return candidate
            minor += 1

    def create(self, target, text='', category=None, document_date=None):
        raw = self.path(target)
        dest = raw.with_name(self.normalize_file(raw.name, category, document_date))
        self.parent(dest)
        dest = self.versioned(dest)
        # 배타적 생성: 기존 데이터 절대 덮어쓰기 금지
        with dest.open('x', encoding='utf-8') as f:
            f.write(text)
        return self.result('파일 생성 완료', dest)

    def save_revision(self, source, text):
        src = self.path(source)
        if not src.is_file():
            raise RuleViolation('원본 파일이 없습니다.')
        self.normalize_file(src.name)
        self.parent(src)
        dest = self.versioned(src, revision=True)
        with dest.open('x', encoding='utf-8') as f:
            f.write(text)
        return self.result('수정본 저장 완료', dest, '원본을 유지하고 버전 번호를 증가시켰습니다.')

    def transfer(self, source, target, category=None, document_date=None):
        src, dest = self.path(source), self.path(target)
        if src == self.root or not src.exists():
            raise RuleViolation('기준 폴더는 이동할 수 없으며 원본이 존재해야 합니다.')
        if src.is_dir():
            self.check_folders(dest)
            if dest == src or dest.is_relative_to(src):
                raise RuleViolation('폴더를 자기 자신 또는 하위 경로로 이동할 수 없습니다.')
            for child in src.rglob('*'):
                if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()):
                    raise RuleViolation('심볼릭 링크를 포함한 폴더는 이동할 수 없습니다.')
                mapped = dest / child.relative_to(src)
                if child.is_dir():
                    self.check_folders(mapped)
                else:
                    self.check_folders(mapped.parent)
                    self.normalize_file(child.name)
            if dest.exists():
                raise RuleViolation('동일한 대상 경로가 이미 존재합니다. 폴더 병합은 자동 수행하지 않습니다.')
        else:
            dest = dest.with_name(self.normalize_file(dest.name, category, document_date))
            if dest == src:
                raise RuleViolation('원본과 대상 경로가 같습니다.')
            if dest.exists():
                dest = self.versioned(dest)
        self.parent(dest)
        # rename은 다른 파일시스템으로의 무조건 복사/삭제를 피함
        self.load_favorites()  # 설정 오류는 실제 이동 전에 발견
        src.rename(dest)
        self.update_favorites(src, dest)
        return self.result('이동/이름 변경 완료', dest)

    def archive(self, source):
        src = self.path(source)
        archive = self.root / ARCHIVE
        if src == self.root or src == archive or src.is_relative_to(archive):
            raise RuleViolation('기준 폴더 또는 이미 보관된 항목은 보관할 수 없습니다.')
        if not src.exists():
            raise RuleViolation('원본이 없습니다.')
        if archive.is_symlink():
            raise RuleViolation('아카이브는 심볼릭 링크일 수 없습니다.')
        archive.mkdir(exist_ok=True)
        return self.transfer(source, str(Path(ARCHIVE) / src.name))

    def load_favorites(self):
        if self.state.is_symlink():
            raise RuleViolation('설정 파일은 심볼릭 링크일 수 없습니다.')
        if not self.state.exists():
            return []
        data = json.loads(self.state.read_text(encoding='utf-8'))
        items = data['favorites']
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items) or len(items) > MAX_FAVORITES:
            raise RuleViolation('즐겨찾기 설정 형식이 잘못되었습니다.')
        return items

    def store_favorites(self, items):
        if self.state.is_symlink():
            raise RuleViolation('설정 파일은 심볼릭 링크일 수 없습니다.')
        self.state.write_text(json.dumps({'favorites': items}, ensure_ascii=False, indent=2), encoding='utf-8')

    def update_favorites(self, src, dest):
        items = self.load_favorites()
        old, new = src.relative_to(self.root), dest.relative_to(self.root)
        updated = []
        for item in items:
            p = Path(item)
            updated.append(str(new / p.relative_to(old)) if p == old or p.is_relative_to(old) else item)
        if updated != items:
            self.store_favorites(updated)

    def favorite(self, action, target=None):
        items = self.load_favorites()
        if action == 'list':
            return {
                '실행 결과': '즐겨찾기 조회 완료',
                '적용된 경로/파일명': items,
                '안내 메시지': f'{len(items)}/{MAX_FAVORITES}개 등록됨 (이 도구 내부 즐겨찾기)',
            }
        p = self.path(target)
        rel = str(p.relative_to(self.root))
        if action == 'add':
            if not p.exists():
                raise RuleViolation('존재하는 항목만 등록할 수 있습니다.')
            if rel not in items:
                if len(items) >= MAX_FAVORITES:
                    raise RuleViolation(FAVORITES_WARNING)
                items.append(rel)
        elif action == 'remove':
            if rel in items:
                items.remove(rel)
        else:
            raise RuleViolation('알 수 없는 즐겨찾기 명령입니다.')
        self.store_favorites(items)
        return self.result('즐겨찾기 변경 완료', p)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='관리할 루트 폴더 (깊이 0)')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('mkdir')
    p.add_argument('parent')
    p.add_argument('name')
    p.add_argument('--kind', choices=['general', 'media', 'project', 'archive'], default='general')
    p.add_argument('--number', type=int)
    p.add_argument('--when')
    for command in ('create', 'move', 'rename'):
        p = sub.add_parser(command)
        if command != 'create':
            p.add_argument('source')
        p.add_argument('target')
        p.add_argument('--category')
        p.add_argument('--date', dest='document_date')
        if command == 'create':
            p.add_argument('--text', default='')
    p = sub.add_parser('revise')
    p.add_argument('source')
    p.add_argument('--text', required=True)
    p = sub.add_parser('archive')
    p.add_argument('source')
    p = sub.add_parser('favorite')
    p.add_argument('action', choices=['add', 'remove', 'list'])
    p.add_argument('target', nargs='?')
    args = vars(parser.parse_args())
    root = args.pop('root')
    command = args.pop('command')
    try:
        manager = Organizer(root)
        if command == 'favorite' and args['action'] != 'list' and not args['target']:
            raise RuleViolation('대상 경로를 지정해 주세요.')
        method = {'rename': 'transfer', 'move': 'transfer', 'revise': 'save_revision'}.get(command, command)
        print(json.dumps(getattr(manager, method)(**args), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {'실행 결과': '처리 거부/실패', '적용된 경로/파일명': '-', '안내 메시지': str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
