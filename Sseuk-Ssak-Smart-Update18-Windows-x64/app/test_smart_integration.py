import tempfile
import unittest
import shutil
from pathlib import Path
from smart_service import SmartService
from smart_rules import RuleViolation

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s=SmartService()
        self.s.select(self.tmp.name)

    def test_ui_workflow(self):
        self.s.handle({'op':'mkdir','name':'업무','kind':'general','number':'2'})
        self.s.handle({'op':'list','folder':'02_업무'})
        r=self.s.handle({'op':'create','name':'기획안.txt','text':'원본'})
        self.assertEqual(r['items'][0]['name'],'기획안_v1.0.txt')
        self.s.handle({'op':'revise','source':'02_업무/기획안_v1.0.txt','text':'수정'})
        self.s.handle({'op':'favorite','action':'add','target':'02_업무/기획안_v1.0.txt'})
        r=self.s.handle({'op':'archive','source':'02_업무/기획안_v1.0.txt'})
        self.assertEqual(r['favorites'],[str(Path('99_아카이브')/'기획안_v1.0.txt')])
        self.assertEqual((Path(self.tmp.name)/'99_아카이브'/'기획안_v1.0.txt').read_text(encoding='utf-8'),'원본')

    def test_binary_write_rejected(self):
        with self.assertRaises(RuleViolation):self.s.handle({'op':'create','name':'기획안.pdf'})
        p=Path(self.tmp.name)/'보고서.pdf';p.write_bytes(b'%PDF-test')
        with self.assertRaises(RuleViolation):self.s.handle({'op':'revise','source':'보고서.pdf','text':'bad'})
        self.assertEqual(p.read_bytes(),b'%PDF-test')
        self.s.handle({'op':'rename','source':'보고서.pdf','target':'업무_보고서.pdf'})
        self.assertEqual(p.with_name('업무_보고서.pdf').read_bytes(),b'%PDF-test')

    def test_demo(self):
        r=self.s.handle({'op':'demo'})
        self.addCleanup(shutil.rmtree,r['root'])
        self.assertEqual(len(r['report']),12)
        self.assertTrue(all(x['passed'] for x in r['report']))
        self.assertTrue(r['demo'])
        self.assertEqual(len(r['favorites']),5)
        print('\nDEMO REPORT:')
        for item in r['report']:print(item['test'], 'PASS' if item['passed'] else 'FAIL', item['message'])

    def test_static_wiring(self):
        base=Path(__file__).parent
        html=(base/'index.html').read_text(encoding='utf-8')
        js=(base/'ui.js').read_text(encoding='utf-8')
        desktop=(base/'desktop.py').read_text(encoding='utf-8')
        self.assertLess(html.index('src="smart_ui.js"'),html.index('src="ui.js"'))
        self.assertIn('파일 구조화',js)
        self.assertIn('[0,6,5,1,2,3,4].forEach',js)
        self.assertIn('if(page===5){space.hidden=true;renderSmart();return}',js)
        self.assertIn("'smart_ui.js':'smart_ui.js'",desktop)
        self.assertIn("if a=='smart':return smart.handle(v)",desktop)

if __name__=='__main__':unittest.main()
