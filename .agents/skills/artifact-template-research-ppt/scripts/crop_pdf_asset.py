#!/usr/bin/env python3
"""Crop a source PDF using top-left point coordinates and record provenance."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def crop_asset(pdf, page_number, bbox, scale, output, manifest, asset_id,
               kind='figure', label='', printed_page=None):
    import pypdfium2 as pdfium

    pdf, output, manifest = [Path(p).resolve() for p in (pdf, output, manifest)]
    if not asset_id.strip() or not label.strip():
        raise ValueError('Asset ID and label must not be empty')
    if output.suffix.lower() != '.png' or output.exists():
        raise ValueError('Output must be a new .png file')
    if len({pdf, output, manifest}) != 3:
        raise ValueError('PDF, PNG and manifest must be different files')
    if not isinstance(page_number, int) or page_number < 1:
        raise ValueError('PDF page numbers start at 1')
    if not math.isfinite(scale) or not 0 < scale <= 16:
        raise ValueError('Scale must be finite and in (0, 16]')
    if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
        raise ValueError('Bounding box needs four finite coordinates')
    if kind not in ('equation', 'figure'):
        raise ValueError('Kind must be equation or figure')
    catalog = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'schema_version': 1, 'assets': []}
    if catalog.get('schema_version') != 1 or not isinstance(catalog.get('assets'), list):
        raise ValueError('Unsupported asset manifest')
    if any(a['id'] == asset_id for a in catalog['assets']):
        raise ValueError('Duplicate asset ID: ' + asset_id)
    with pdfium.PdfDocument(pdf) as doc:
        if page_number > len(doc):
            raise ValueError('PDF page is out of range')
        page = doc[page_number - 1]
        try:
            width, height = page.get_size()
            left, top, right, bottom = bbox
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError('Bounding box is empty or outside the PDF page')
            bitmap = page.render(scale=scale, crop=(left, height-bottom, width-right, top))
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents accidental overwrites on retry.
                with output.open('xb') as stream:
                    bitmap.to_pil().save(stream, format='PNG')
            finally:
                bitmap.close()
        finally:
            page.close()
    entry = {'id': asset_id, 'kind': kind, 'label': label,
             'file': os.path.relpath(output, manifest.parent).replace('\\', '/'),
             'sha256': sha256(output),
             'source_pdf': os.path.relpath(pdf, manifest.parent).replace('\\', '/'),
             'source_sha256': sha256(pdf), 'pdf_page': page_number,
             'printed_page': printed_page, 'bbox_points': list(bbox), 'scale': scale}
    catalog['assets'].append(entry)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace the previous catalog until the new catalog is complete.
    staging = manifest.with_name(manifest.name + '.new')
    try:
        with staging.open('x', encoding='utf-8') as stream:
            json.dump(catalog, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        staging.replace(manifest)
    except Exception:
        # A saved PNG without a catalog is harmless; report the error for repair.
        raise
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--page', required=True, type=int)
    parser.add_argument('--bbox', required=True, type=float, nargs=4, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'))
    parser.add_argument('--scale', type=float, default=4)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--id', required=True)
    parser.add_argument('--kind', choices=['equation', 'figure'], default='figure')
    parser.add_argument('--label', required=True)
    parser.add_argument('--printed-page')
    args = parser.parse_args()
    try:
        result = crop_asset(args.pdf, args.page, args.bbox, args.scale, args.output,
                            args.manifest, args.id, args.kind, args.label, args.printed_page)
    except (ValueError, OSError, ImportError, KeyError) as error:
        print(json.dumps({'status': 'fail', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({'status': 'pass', 'asset': result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
