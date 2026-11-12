#!/usr/bin/env python3
"""Create a distributable zip containing only the skill and its license notices."""
import argparse
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'.agents/skills/artifact-template-research-ppt'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='v0.1.0')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', args.version):
        parser.error('Use a semantic version such as v0.1.0')
    out = ROOT/'dist'/f'research-ppt-skill-{args.version}.zip'
    if out.exists():
        parser.error('Archive already exists; choose a new version or move the old archive')
    out.parent.mkdir(exist_ok=True)
    with ZipFile(out, 'x', ZIP_DEFLATED) as z:
        files = [(p, SKILL.name+'/'+p.relative_to(SKILL).as_posix()) for p in sorted(SKILL.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
        files += [(ROOT/name, SKILL.name+'/'+name) for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md')]
        for source, name in files:
            info = ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            z.writestr(info, source.read_bytes())
    print(out)


if __name__ == '__main__':
    main()
