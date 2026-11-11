import tempfile
import unittest
from pathlib import Path
from smart_rules import Organizer, RuleViolation


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.o = Organizer(self.tmp.name)
        self.root = Path(self.tmp.name)

    def test_depth(self):
        parent = '.'
        for i in range(5):
            result = self.o.mkdir(parent, '업무', number=1)
            parent = result['적용된 경로/파일명']
        with self.assertRaisesRegex(RuleViolation, '최대 5단계'):
            self.o.mkdir(parent, '초과', number=1)

    def test_numbering(self):
        with self.assertRaises(RuleViolation):
            self.o.mkdir('.', '업무', number=99)
        self.o.mkdir('.', '여행', kind='media', when='2025_03')
        self.o.mkdir('.', '개편', kind='project', when='2026-3Q')
        self.assertTrue((self.root / '2025_03_여행').is_dir())
        with self.assertRaises(RuleViolation):
            self.o.mkdir('.', '여행', kind='media', when='2025_13')

    def test_naming(self):
        for word in ('최종', '진짜', '마지막'):
            with self.assertRaises(RuleViolation):
                self.o.create(f'기획안_{word}.txt')
        with self.assertRaises(RuleViolation):
            self.o.create('내용.txt')
        r = self.o.create('내용.txt', category='회의록')
        self.assertEqual(r['적용된 경로/파일명'], '회의록_내용_v1.0.txt')

    def test_date(self):
        with self.assertRaises(RuleViolation):
            self.o.create('근로계약서.txt')
        with self.assertRaises(RuleViolation):
            self.o.create('근로계약서.txt', document_date='2026_02_30')
        r = self.o.create('근로계약서.txt', document_date='2026_11_04')
        self.assertEqual(r['적용된 경로/파일명'], '2026_11_04_근로계약서_v1.0.txt')

    def test_versions(self):
        a = self.o.create('기획안.txt', '원본')['적용된 경로/파일명']
        b = self.o.save_revision(a, '수정')['적용된 경로/파일명']
        c = self.o.create('기획안.txt', '추가')['적용된 경로/파일명']
        self.assertEqual(b, '기획안_v1.1.txt')
        self.assertEqual(c, '기획안_v1.2.txt')
        self.assertEqual((self.root / a).read_text(encoding='utf-8'), '원본')

    def test_archive_and_favorites(self):
        a = self.o.create('회의록.txt')['적용된 경로/파일명']
        self.o.favorite('add', a)
        r = self.o.archive(a)
        self.assertTrue((self.root / r['적용된 경로/파일명']).exists())
        self.assertEqual(self.o.favorite('list')['적용된 경로/파일명'], [r['적용된 경로/파일명']])
        for i in range(4):
            p = self.o.create(f'회의록_{i}.txt')['적용된 경로/파일명']
            self.o.favorite('add', p)
        extra = self.o.create('회의록_추가.txt')['적용된 경로/파일명']
        with self.assertRaisesRegex(RuleViolation, '최대 5개'):
            self.o.favorite('add', extra)
        self.o.favorite('remove', self.o.favorite('list')['적용된 경로/파일명'][0])
        self.o.favorite('add', extra)

    def test_subtree_depth(self):
        self.o.mkdir('.', '소스', number=1)
        self.o.mkdir('01_소스', '하위', number=1)
        parent = '.'
        for i in range(4):
            parent = self.o.mkdir(parent, '대상', number=2)['적용된 경로/파일명']
        with self.assertRaises(RuleViolation):
            self.o.transfer('01_소스', parent + '/01_소스')
        self.assertTrue((self.root / '01_소스').exists())

    def test_security(self):
        for p in ('../회의록.txt', '/회의록.txt', '.smart_organizer.json'):
            with self.assertRaises(RuleViolation):
                self.o.create(p)
        try:
            (self.root / '01_링크').symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'심볼릭 링크를 만들 권한이 없어요 (개발자 모드 또는 관리자 필요): {exc}')
        with self.assertRaises(RuleViolation):
            self.o.create('01_링크/회의록.txt')


if __name__ == '__main__':
    unittest.main()
