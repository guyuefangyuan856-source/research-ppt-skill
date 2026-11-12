"""Behavioral regression cases; all generated fixtures stay under .work."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'.agents/skills/artifact-template-research-ppt/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_tool = load('audit_report')
crop_tool = load('crop_pdf_asset')
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


class AuditTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.work/tests').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'.work/tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pptx, self.md, self.planfile = [self.root/n for n in ('report.pptx', 'speaker.md', 'plan.json')]
        self.plan = {'schema_version': 1, 'presenter': '测试汇报人', 'expected_slide_count': 2,
                     'max_seconds': 60, 'planned_seconds': 50, 'slides': [
                         {'number': i, 'title': title, 'seconds': 25, 'cue': '指出研究问题',
                          'speech': f'这是第{i}页的完整口语讲稿。', 'source': f'原文 p.{i}', 'asset_ids': []}
                         for i, title in [(1, '研究题目'), (2, '结论与讨论')]]}
        self.save_plan()
        self.save_md()
        self.save_pptx()

    def save_plan(self):
        self.planfile.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf-8')

    def save_md(self):
        self.md.write_text('测试汇报人 report.pptx\n'+''.join(
            f"## 第{p['number']:02}页 {p['title']}\n{p['seconds']}秒\n{p['cue']}\n{p['speech']}\n{p['source']}\n"
            for p in self.plan['slides']), encoding='utf-8')

    def save_pptx(self, order=(1, 2), image_slide=None, image=b'png fixture', hidden=False):
        with ZipFile(self.pptx, 'w') as z:
            z.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'+''.join(f'<p:sldId id="{n+255}" r:id="r{n}"/>' for n in order)+'</p:sldIdLst></p:presentation>')
            z.writestr('ppt/_rels/presentation.xml.rels', f'<Relationships xmlns="{PKG}">'+''.join(f'<Relationship Id="r{n}" Type="{R}/slide" Target="slides/slide{n}.xml"/>' for n in (1, 2))+'</Relationships>')
            for p in self.plan['slides']:
                n = p['number']
                picture = '<p:pic><a:blip r:embed="image"/></p:pic>' if n == image_slide else ''
                z.writestr(f'ppt/slides/slide{n}.xml', f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" show="{0 if hidden and n==2 else 1}"><p:cSld><p:spTree><p:sp><a:t>{p["title"]} 测试汇报人</a:t></p:sp>{picture}</p:spTree></p:cSld></p:sld>')
                rel = f'<Relationship Id="notes" Type="{R}/notesSlide" Target="../notesSlides/notesSlide{n}.xml"/>'
                if n == image_slide:
                    rel += f'<Relationship Id="image" Type="{R}/image" Target="../media/image.png"/>'
                z.writestr(f'ppt/slides/_rels/slide{n}.xml.rels', f'<Relationships xmlns="{PKG}">{rel}</Relationships>')
                text = ' '.join([p['title'], str(p['seconds'])+'秒', p['cue'], p['speech'], p['source']])
                z.writestr(f'ppt/notesSlides/notesSlide{n}.xml', f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><a:t>{text}</a:t></p:notes>')
            if image_slide:
                z.writestr('ppt/media/image.png', image)

    def audit(self, assets=None):
        return audit_tool.audit(self.pptx, self.md, self.planfile, assets)

    def codes(self, report):
        return {f['code'] for f in report['findings']}

    def test_good_report_and_freshness(self):
        result = self.audit()
        self.assertEqual(result['status'], 'pass', result)
        report = self.root/'qa.json'
        report.write_text(json.dumps(result), encoding='utf-8')
        self.assertEqual(audit_tool.verify_report(report)['verified_files'], 3)

    def test_reordered_pptx_uses_logical_order(self):
        self.save_pptx(order=(2, 1))
        self.assertIn('title_mismatch', self.codes(self.audit()))

    def test_script_mismatch(self):
        self.md.write_text(self.md.read_text(encoding='utf-8').replace('这是第2页', '错误讲稿'), encoding='utf-8')
        self.assertIn('script_mismatch', self.codes(self.audit()))

    def test_time_limit(self):
        self.plan['max_seconds'] = 49
        self.save_plan()
        self.assertIn('time_limit', self.codes(self.audit()))

    def test_time_substring_does_not_match_and_script_placeholder(self):
        self.md.write_text(self.md.read_text(encoding='utf-8').replace('25秒', '125秒')+'\n请替换', encoding='utf-8')
        codes = self.codes(self.audit())
        self.assertIn('script_time', codes)
        self.assertIn('residual_text', codes)

    def test_bad_times_and_hidden_slide(self):
        self.plan['slides'][0]['seconds'] = float('nan')
        self.save_plan()
        self.assertIn('page_time', self.codes(self.audit()))
        self.save_pptx(hidden=True)
        self.assertIn('hidden_slide', self.codes(self.audit()))

    def test_stale_report_after_pptx_change(self):
        report = self.root/'qa.json'
        report.write_text(json.dumps(self.audit()), encoding='utf-8')
        self.pptx.write_bytes(self.pptx.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'Stale'):
            audit_tool.verify_report(report)

    def test_stale_report_after_script_change(self):
        report = self.root/'qa.json'
        report.write_text(json.dumps(self.audit()), encoding='utf-8')
        self.md.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Stale'):
            audit_tool.verify_report(report)

    def asset_fixture(self):
        image = self.root/'image.png'
        image.write_bytes(b'png fixture')
        pdf = self.root/'paper.pdf'
        pdf.write_bytes(b'PDF provenance fixture')
        asset = {'id': 'eq', 'file': 'image.png', 'sha256': audit_tool.sha256(image),
                 'source_pdf': 'paper.pdf', 'source_sha256': audit_tool.sha256(pdf),
                 'pdf_page': 1, 'bbox_points': [0, 0, 10, 10], 'scale': 4,
                 'kind': 'equation', 'label': 'Equation (1)'}
        assets = self.root/'assets.json'
        assets.write_text(json.dumps({'schema_version': 1, 'assets': [asset]}), encoding='utf-8')
        self.plan['slides'][0]['asset_ids'] = ['eq']
        self.save_plan()
        return assets

    def test_asset_must_be_on_its_declared_slide(self):
        assets = self.asset_fixture()
        self.save_pptx(image_slide=2)
        self.assertIn('asset_embedding', self.codes(self.audit(assets)))
        self.save_pptx(image_slide=1)
        self.assertEqual(self.audit(assets)['status'], 'pass')

    def test_missing_asset_and_changed_source(self):
        assets = self.asset_fixture()
        (self.root/'image.png').unlink()
        (self.root/'paper.pdf').write_bytes(b'different source')
        codes = self.codes(self.audit(assets))
        self.assertIn('asset_missing', codes)
        self.assertIn('asset_hash', codes)


class CropTests(unittest.TestCase):
    def setUp(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        (ROOT/'.work/tests').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'.work/tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pdf = self.root/'source.pdf'
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        stream = DecodedStreamObject()
        stream.set_data(b'1 0 0 rg 0 50 100 50 re f 0 0 1 rg 0 0 100 50 re f')
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(self.pdf)

    def crop(self, bbox=(10, 10, 40, 40), **overrides):
        args = dict(pdf=self.pdf, page_number=1, bbox=bbox, scale=2,
                    output=self.root/'crop.png', manifest=self.root/'assets.json',
                    asset_id='test', kind='figure', label='Test figure')
        args.update(overrides)
        return crop_tool.crop_asset(**args)

    def test_top_left_coordinates_and_provenance(self):
        from PIL import Image
        entry = self.crop()
        with Image.open(self.root/'crop.png') as image:
            self.assertEqual(image.size, (60, 60))
            self.assertEqual(image.convert('RGB').getpixel((30, 30)), (255, 0, 0))
        self.assertEqual(entry['source_sha256'], crop_tool.sha256(self.pdf))
        self.assertEqual(entry['sha256'], crop_tool.sha256(self.root/'crop.png'))

    def test_outside_or_empty_bbox(self):
        for bbox in [(-1, 0, 10, 10), (0, 0, 101, 50), (5, 5, 5, 6), (0, 0, float('nan'), 50)]:
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                self.crop(bbox)
        self.assertFalse((self.root/'crop.png').exists())

    def test_invalid_page_scale_and_duplicate(self):
        for args in [{'page_number': 0}, {'page_number': 2}, {'scale': float('inf')}, {'scale': 0}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.crop(**args)
        self.crop()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.crop(output=self.root/'other.png')
        with self.assertRaisesRegex(ValueError, 'new .png'):
            self.crop(asset_id='other')


if __name__ == '__main__':
    unittest.main()
