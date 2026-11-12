#!/usr/bin/env python3
"""Audit PPTX/script alignment and source assets; bind results to file hashes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import posixpath
import re
import sys
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def norm(text):
    return re.sub(r'\s+', '', str(text))


def xml_text(tree):
    return ''.join(n.text or '' for n in tree.findall('.//a:t', NS))


def relationships(package, part):
    rel = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part)+'.rels')
    if rel not in package.namelist():
        return {}
    result = {}
    for node in ET.fromstring(package.read(rel)):
        if node.get('TargetMode') == 'External':
            continue
        target = node.get('Target', '')
        target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
        result[node.get('Id')] = (node.get('Type', '').rsplit('/', 1)[-1], target)
    return result


def load_slides(pptx):
    slides = []
    with ZipFile(pptx) as package:
        presentation = ET.fromstring(package.read('ppt/presentation.xml'))
        refs = relationships(package, 'ppt/presentation.xml')
        ids = presentation.find('p:sldIdLst', NS)
        if ids is None:
            raise ValueError('PPTX has no slide list')
        for sid in ids:
            kind, part = refs[sid.get('{'+NS['r']+'}id')]
            if kind != 'slide':
                raise ValueError('Slide reference has wrong relationship type')
            tree = ET.fromstring(package.read(part))
            rels = relationships(package, part)
            notes = ''.join(xml_text(ET.fromstring(package.read(target)))
                            for typ, target in rels.values() if typ == 'notesSlide')
            image_hashes = set()
            for blip in tree.findall('.//a:blip', NS):
                rid = blip.get('{'+NS['r']+'}embed')
                if rid in rels:
                    typ, target = rels[rid]
                    if typ == 'image':
                        image_hashes.add(hashlib.sha256(package.read(target)).hexdigest())
            slides.append({'text': xml_text(tree), 'notes': notes,
                           'hidden': tree.get('show', '1') in ('0', 'false'),
                           'image_hashes': image_hashes})
    return slides


def audit(pptx, script, manifest, assets_manifest=None):
    pptx, script, manifest = [Path(p).resolve() for p in (pptx, script, manifest)]
    findings, fingerprints, statistics = [], {}, {}

    def fail(code, detail, slide=None):
        finding = {'code': code, 'detail': detail}
        if slide is not None:
            finding['slide'] = slide
        findings.append(finding)

    def fingerprint(path):
        path = Path(path).resolve()
        fingerprints[str(path)] = sha256(path)

    for path in (pptx, script, manifest):
        fingerprint(path)
    plan = json.loads(manifest.read_text(encoding='utf-8'))
    markdown = script.read_text(encoding='utf-8')
    if plan.get('schema_version') != 1:
        raise ValueError('Unsupported plan schema_version')
    expected = plan.get('expected_slide_count')
    if type(expected) is not int or expected < 2:
        raise ValueError('expected_slide_count must be an integer >= 2')
    for key in ('max_seconds', 'planned_seconds'):
        if type(plan.get(key)) not in (int, float) or not math.isfinite(plan[key]) or plan[key] <= 0:
            raise ValueError(key+' must be positive and finite')
    if not isinstance(plan.get('presenter'), str) or not plan['presenter'].strip():
        raise ValueError('presenter must be a non-empty string')
    pages = plan.get('slides')
    if not isinstance(pages, list):
        raise ValueError('slides must be an array')
    slides = load_slides(pptx)
    statistics['slide_count'] = len(slides)
    if len(slides) != expected or len(pages) != expected:
        fail('slide_count', 'PPTX, manifest and requested page counts must agree')
    matches = list(re.finditer(r'^## 第(\d+)页 (.+?)\s*$', markdown, re.M))
    if len(matches) != expected:
        fail('script_page_count', 'Markdown page section count differs from requested count')
    sections = [markdown[m.end():matches[i+1].start() if i+1 < len(matches) else len(markdown)]
                for i, m in enumerate(matches)]
    presenter = plan['presenter']
    if norm(presenter) not in norm(slides[0]['text'] if slides else '') or norm(presenter) not in norm(markdown):
        fail('presenter', 'Presenter must appear on the cover and in Markdown')
    if pptx.name not in markdown:
        fail('deck_reference', 'Markdown must name the final PPTX file')
    asset_map = {}
    if assets_manifest is not None:
        assets_manifest = Path(assets_manifest).resolve()
        fingerprint(assets_manifest)
        catalog = json.loads(assets_manifest.read_text(encoding='utf-8'))
        if catalog.get('schema_version') != 1 or not isinstance(catalog.get('assets'), list):
            raise ValueError('Unsupported asset manifest')
        for asset in catalog['assets']:
            aid = asset['id']
            if aid in asset_map:
                fail('duplicate_asset', 'Duplicate asset ID: '+aid)
            asset_map[aid] = asset
            for field, hash_field in [('file', 'sha256'), ('source_pdf', 'source_sha256')]:
                path = (assets_manifest.parent / asset[field]).resolve()
                if not path.is_file():
                    fail('asset_missing', f'{aid}: {field} is missing')
                else:
                    fingerprint(path)
                    if sha256(path) != asset.get(hash_field):
                        fail('asset_hash', f'{aid}: {field} differs from its recorded hash')
            if asset.get('kind') not in ('equation', 'figure') or not asset.get('label'):
                fail('asset_provenance', aid+': missing kind or label')
            if type(asset.get('pdf_page')) is not int or asset['pdf_page'] < 1:
                fail('asset_provenance', aid+': invalid PDF page')
            bbox = asset.get('bbox_points', [])
            if (not isinstance(bbox, list) or len(bbox) != 4 or
                not all(type(v) in (int, float) and math.isfinite(v) for v in bbox) or
                (len(bbox) == 4 and not (0 <= bbox[0] < bbox[2] and 0 <= bbox[1] < bbox[3]))):
                fail('asset_provenance', aid+': invalid crop coordinates')
            if type(asset.get('scale')) not in (int, float) or not math.isfinite(asset['scale']) or not 0 < asset['scale'] <= 16:
                fail('asset_provenance', aid+': invalid render scale')
    for text in plan.get('forbidden_text', ['［', '请替换', '[Paper title']):
        if text and text in markdown:
            fail('residual_text', 'Unexpected placeholder or stale reference text in Markdown: '+text)
    total_seconds = 0
    for index, page in enumerate(pages):
        number = index + 1
        if page.get('number') != number:
            fail('page_order', 'Manifest page numbers must be consecutive', number)
        for key in ('title', 'cue', 'speech', 'source'):
            if not isinstance(page.get(key), str) or not page[key].strip():
                fail('page_field', 'Missing or empty '+key, number)
        seconds = page.get('seconds')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            fail('page_time', 'Page seconds must be finite and positive', number)
        else:
            total_seconds += seconds
        if not isinstance(page.get('asset_ids'), list):
            fail('asset_ids', 'asset_ids must be an array', number)
            declared_assets = []
        else:
            declared_assets = page['asset_ids']
        if index >= len(slides):
            continue
        slide = slides[index]
        if slide['hidden']:
            fail('hidden_slide', 'Requested pages must not be hidden', number)
        if norm(page.get('title', '')) not in norm(slide['text']):
            fail('title_mismatch', 'Title absent from the corresponding PPTX page', number)
        for key in ('title', 'cue', 'speech', 'source'):
            if norm(page.get(key, '')) not in norm(slide['notes']):
                fail('notes_mismatch', key+' absent from the corresponding notes', number)
        time_pattern = r'(?<![\d.])'+re.escape(str(seconds))+r'秒(?!\d)'
        if not re.search(time_pattern, slide['notes']):
            fail('notes_time', 'Page seconds absent from notes', number)
        if index < len(matches):
            if int(matches[index].group(1)) != number or norm(matches[index].group(2)) != norm(page.get('title', '')):
                fail('script_order', 'Markdown page number/title differs', number)
            for key in ('cue', 'speech', 'source'):
                if norm(page.get(key, '')) not in norm(sections[index]):
                    fail('script_mismatch', key+' absent from the corresponding Markdown section', number)
            if not re.search(time_pattern, sections[index]):
                fail('script_time', 'Page seconds absent from Markdown section', number)
        for aid in declared_assets:
            if aid not in asset_map:
                fail('asset_undeclared', 'Missing asset definition: '+str(aid), number)
            elif asset_map[aid].get('sha256') not in slide['image_hashes']:
                fail('asset_embedding', 'Source asset not embedded unchanged on this page: '+aid, number)
        for text in plan.get('forbidden_text', ['［', '请替换', '[Paper title']):
            if text and (text in slide['text'] or text in slide['notes']):
                fail('residual_text', 'Unexpected placeholder or stale reference text: '+text, number)
    statistics['planned_seconds'] = total_seconds
    statistics['source_asset_count'] = len(asset_map)
    if not math.isclose(total_seconds, plan['planned_seconds'], abs_tol=1e-6):
        fail('time_total', 'Page seconds differ from planned_seconds')
    if total_seconds > plan['max_seconds']:
        fail('time_limit', 'Planned duration exceeds the time limit')
    return {'schema_version': 1, 'status': 'fail' if findings else 'pass',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'pptx_sha256': sha256(pptx), 'fingerprints': fingerprints,
            'statistics': statistics, 'findings': findings,
            'limits': 'Structural, text and file-hash checks only. Scientific interpretation, crop semantics, oral timing and visual appearance require human/agent review.'}


def verify_report(path):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if report.get('schema_version') != 1 or report.get('status') != 'pass' or not report.get('fingerprints'):
        raise ValueError('Report is not a successful version 1 audit')
    for name, expected in report['fingerprints'].items():
        file = Path(name)
        if not file.is_file() or sha256(file) != expected:
            raise ValueError('Stale report: input changed or missing: '+name)
    return {'status': 'pass', 'verified_files': len(report['fingerprints']), 'pptx_sha256': report['pptx_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-report', type=Path)
    parser.add_argument('--pptx', type=Path)
    parser.add_argument('--script', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--assets-manifest', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.verify_report and not all([args.pptx, args.script, args.manifest, args.output]):
        parser.error('Supply --verify-report or all of --pptx --script --manifest --output')
    try:
        if args.verify_report:
            if any([args.pptx, args.script, args.manifest, args.assets_manifest, args.output]):
                raise ValueError('--verify-report cannot be combined with audit arguments')
            result = verify_report(args.verify_report)
        else:
            inputs = [p.resolve() for p in [args.pptx, args.script, args.manifest, args.assets_manifest] if p]
            if args.output.resolve() in inputs:
                raise ValueError('Report output must not overwrite an input')
            result = audit(args.pptx, args.script, args.manifest, args.assets_manifest)
            if str(args.output.resolve()) in result['fingerprints']:
                raise ValueError('Report output must not overwrite a source or asset')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    except (ValueError, OSError, KeyError, TypeError, BadZipFile, ET.ParseError) as error:
        print(json.dumps({'status': 'fail', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
