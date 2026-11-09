import unittest
from pathlib import Path
from engine import Row
from download_versions import word_groups, word_tokens, choose_downloads
from chrome_files import Session

class WordTests(unittest.TestCase):
    def rows(self,*names):
        return [Row('같은 이름',Path('/files')/n,10,(10,i,0,0),'',None,'') for i,n in enumerate(names)]
    def test_auto(self):
        rows=word_groups(self.rows('Sseuk-Ssak-v0.7.17-Portable-Windows-x64.zip','Sseuk-Ssak-v0.7.18-Portable-Windows-x64.zip','Other-App-Windows-x64.zip'),'auto')
        self.assertEqual(rows[0].group,rows[1].group)
        self.assertNotEqual(rows[0].group,rows[2].group)
        out=choose_downloads(rows,'version',{})
        self.assertIn('남길 파일 ·',out[1].detail)
    def test_no_generic_or_chain(self):
        rows=word_groups(self.rows('Report-Windows-Setup-v1.0.zip','Other-Windows-Setup-v1.1.zip'),'auto')
        self.assertNotEqual(rows[0].group,rows[1].group)
        rows=word_groups(self.rows('apple-banana-note.txt','apple-banana-cherry-date.txt','cherry-date-note.txt'),'auto')
        self.assertNotEqual(rows[0].group,rows[2].group)
    def test_manual(self):
        rows=word_groups(self.rows('Sseuk-Ssak-v1.0.zip','SSEUK-SSAK-v1.1.zip','Other.zip'),'manual','sseuk-ssak')
        self.assertEqual(rows[0].group,rows[1].group)
        self.assertNotEqual(rows[0].group,rows[2].group)
        with self.assertRaises(ValueError):word_groups(rows,'manual',' ')
        with self.assertRaises(ValueError):word_groups(rows,'wrong','a')
        with self.assertRaises(ValueError):word_groups(rows,'manual','a'*101)
    def test_boundaries(self):
        rows=self.rows('apple-banana-x64.zip','apple-banana-arm64.zip','apple-banana-x64.exe')
        rows.append(rows[0]._replace(path=Path('/other')/rows[0].path.name))
        for mode in ['auto','manual']:
            out=word_groups(rows,mode,'apple')
            self.assertEqual(len({r.group for r in out}),4)
    def test_korean(self):
        rows=word_groups(self.rows('매출_보고서_2025.txt','매출_보고서_2026.txt'),'auto')
        self.assertEqual(rows[0].group,rows[1].group)
        self.assertEqual(word_tokens(Path('파일_설치_Windows_x64_2026.txt')),[])
    def test_session_switch(self):
        s=Session();s.rows=self.rows('apple-banana-v1.0.zip','apple-banana-v1.1.zip');s.ids={'1':s.rows[0].path,'2':s.rows[1].path}
        snap=s.policy({'word_mode':'auto','keyword':''})
        self.assertEqual(len({r['group'] for r in snap['items']}),1)
        old=list(s.rows)
        with self.assertRaises(ValueError):s.policy({'word_mode':'manual','keyword':''})
        self.assertEqual(s.rows,old)
        self.assertEqual(s.word_mode,'auto')
        s.policy({'word_mode':'off','keyword':''})
        self.assertEqual(len({r.group for r in s.rows}),2)
        self.assertEqual(set(s.ids),{'1','2'})

if __name__=='__main__':unittest.main()
