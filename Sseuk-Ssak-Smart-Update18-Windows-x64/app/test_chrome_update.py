import tempfile
import unittest
from pathlib import Path
from engine import Row
from download_versions import group_key,choose_downloads
from chrome_files import Session

class ChromeUpdateTests(unittest.TestCase):
    def row(self,name,stamp=1):
        p=Path('/downloads')/name
        return Row('같은 이름',p,10,(10,stamp,0,0),'',None,group_key(p,True))

    def test_numeric_version_latest(self):
        rows=[self.row(f'Sseuk-Ssak-v0.7.{v}-Portable-Windows-x64.zip') for v in [2,10,11,12,13,14,15,16,17,18]]
        self.assertEqual(len({r.group for r in rows}),1)
        chosen=choose_downloads(rows,'version',{})
        leaders=[r for r in chosen if r.detail.startswith('남길 파일 ·')]
        self.assertEqual(len(leaders),1)
        self.assertIn('v0.7.18-',leaders[0].path.name)
        self.assertEqual(sum(bool(r.keep) for r in chosen),9)

    def test_toggle_and_identity_boundaries(self):
        a=Path('/downloads/Sseuk-Ssak-v0.7.18-Portable-Windows-x64.zip')
        b=Path('/downloads/Sseuk-Ssak-v0.7.17-Portable-Windows-x64.zip')
        self.assertNotEqual(group_key(a,False),group_key(b,False))
        self.assertEqual(group_key(a,True),group_key(b,True))
        for other in ['Sseuk-Ssak-v0.7.17-Progress-Windows-x64.zip','Sseuk-Ssak-v0.7.17-Portable-Windows-arm64.zip','Sseuk-Ssak-v0.7.17-Portable-Windows-x64.exe']:
            self.assertNotEqual(group_key(a,True),group_key(a.with_name(other),True))
        self.assertNotEqual(group_key(a,True),group_key(Path('/other')/b.name,True))

    def test_copy_tie_break(self):
        rows=[self.row('App-v0.7.18.zip',1),self.row('App-v0.7.18 (1).zip',2),self.row('App-v0.7.17.zip',3)]
        chosen=choose_downloads(rows,'version',{})
        self.assertEqual([r.path.name for r in chosen if r.detail.startswith('남길 파일 ·')],['App-v0.7.18 (1).zip'])
        rows=[self.row('App-v1.0.zip',1),self.row('App-v1.0 (1).zip',1)]
        chosen=choose_downloads(rows,'version',{})
        self.assertFalse(any(r.keep for r in chosen))
        self.assertFalse(any(r.detail.startswith('남길 파일 ·') for r in chosen))

    def test_policy_keeps_ids(self):
        s=Session()
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/f'App-v1.{i}.zip' for i in [0,1]]
            for p in paths:p.write_bytes(b'fake zip for test only')
            s.rows=[self.row(p.name,i)._replace(path=p,group=group_key(p,False)) for i,p in enumerate(paths)]
            s.ids={str(i):r.path for i,r in enumerate(s.rows)}
            old=dict(s.ids)
            snap=s.policy({'similar':True})
            self.assertTrue(snap['similar'])
            self.assertEqual(s.ids,old)
            self.assertEqual(len({r['group'] for r in snap['items']}),1)
            self.assertTrue(all('modified' in r for r in snap['items']))
            snap=s.policy({'similar':False})
            self.assertEqual(len({r['group'] for r in snap['items']}),2)
            self.assertTrue(all(p.exists() for p in paths))

    def test_html_wiring(self):
        html=Path(__file__).with_name('chrome-progress.html').read_text(encoding='utf-8')
        self.assertNotIn('renderStorage(',html)
        self.assertNotIn('id="storage"',html)
        for key in ['pageSize','sortOrder','similarNames']:
            self.assertIn('id="'+key+'"',html)
        for n in [10,50,100]:self.assertIn('value="'+str(n)+'"',html)
        self.assertIn('flat.slice(groupPage*pageSize',html)
        self.assertIn("addEventListener('dragstart'",html)

if __name__=='__main__':unittest.main()
