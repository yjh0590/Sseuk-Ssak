import tempfile
import unittest
from pathlib import Path
from engine import Row
from local_groups import organize_rows, choose_keepers

class Update4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
    def make(self,name,stamp=1,kind='전체 파일'):
        p=self.base/name;p.write_text('example',encoding='utf-8')
        return Row(kind,p,7,(7,stamp,0,0),'original',None,'')
    def test_auto_local(self):
        rows=[self.make('매출_보고서_2025.txt'),self.make('매출_보고서_2026.txt',2),self.make('별개_파일.txt')]
        out=organize_rows(rows,'auto')
        self.assertEqual(len([r for r in out if r.kind=='전체 파일']),3)
        grouped=[r for r in out if r.kind=='같은 이름']
        self.assertEqual(len(grouped),2)
        self.assertEqual(grouped[0].keep,rows[1].path)
        self.assertEqual([r.detail for r in out if r.kind=='전체 파일'],['original']*3)
        self.assertTrue(all(r.path.exists() for r in rows))
    def test_manual_and_version(self):
        rows=[self.make('Sseuk-Ssak-v0.7.9.zip'),self.make('Sseuk-Ssak-v0.7.18.zip',2)]
        out=organize_rows(rows,'manual','Sseuk-Ssak',False,'version')
        same=[r for r in out if r.kind=='같은 이름']
        self.assertEqual(same[0].keep,rows[1].path)
        self.assertIsNone(same[1].keep)
        self.assertEqual(len(organize_rows(rows,'off')),2)
        self.assertEqual(len([r for r in organize_rows(rows,similar=True,keeper_mode='version') if r.kind=='같은 이름']),2)
    def test_no_resurrect_deleted(self):
        rows=[self.make('apple-banana-v1.0.txt'),self.make('apple-banana-v1.1.txt')]
        rows[0].path.unlink()
        out=organize_rows(rows,'auto')
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].path,rows[1].path)
    def test_non_same_untouched_version_mode(self):
        rows=[self.make('App-v1.0.zip',kind='작업 버전'),self.make('App-v2.0.zip',kind='전체 파일')]
        self.assertEqual(choose_keepers(rows,'version'),rows)
    def test_controls(self):
        b=Path(__file__).parent
        ui=(b/'ui.js').read_text(encoding='utf-8')
        self.assertIn("api('grouping'",ui)
        self.assertIn("$('#resultPrevious').hidden=value===1",ui)
        self.assertIn("$('#resultNext').hidden=value===2",ui)
        self.assertIn('정렬: ',ui)
        self.assertIn('Windows 휴지통',ui)
        smart=(b/'smart_ui.js').read_text(encoding='utf-8')
        self.assertIn('input.placeholder=examples[key]',smart)
        self.assertIn("smartDraft[key]:''",smart)
        self.assertIn('폴더 우선 · 이름순',smart)
        storage=(b/'storage.js').read_text(encoding='utf-8')
        self.assertIn('storage-swatch',storage)
        self.assertIn('0.5% 미만',storage)

if __name__=='__main__':unittest.main()
