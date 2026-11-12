#!/usr/bin/env python3
"""Validate the public skill bundle without requiring Codex's private runtime."""
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'.agents/skills/artifact-template-research-ppt'


def check():
    errors = []
    text = (SKILL/'SKILL.md').read_text(encoding='utf-8')
    chunks = text.split('---', 2)
    if len(chunks) != 3 or chunks[0].strip():
        raise ValueError('SKILL.md requires YAML frontmatter')
    meta = yaml.safe_load(chunks[1])
    if meta.get('name') != SKILL.name or not re.fullmatch(r'[a-z0-9-]{1,63}', meta['name']):
        errors.append('Skill name is invalid or differs from its folder')
    if not isinstance(meta.get('description'), str) or not 20 <= len(meta['description']) <= 1024:
        errors.append('Missing or oversized skill description')
    agent = yaml.safe_load((SKILL/'agents/openai.yaml').read_text(encoding='utf-8'))
    interface = agent['interface']
    if not 25 <= len(interface['short_description']) <= 64:
        errors.append('UI short_description must have 25–64 characters')
    if '$'+SKILL.name not in interface['default_prompt']:
        errors.append('Default prompt must explicitly invoke the skill')
    if agent.get('policy', {}).get('allow_implicit_invocation', True) is not True:
        errors.append('Automatic invocation should remain enabled')
    manifest = json.loads((SKILL/'artifact-template.json').read_text(encoding='utf-8'))
    if manifest['schemaVersion'] != 1 or manifest['kind'] != 'presentation':
        errors.append('Template manifest kind/version mismatch')
    for key in ('reference', 'preview'):
        target = (SKILL/manifest[key]).resolve()
        if not target.is_relative_to(SKILL.resolve()) or not target.is_file():
            errors.append('Missing or unsafe template '+key)
    for file in SKILL.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            if '://' not in target and not (file.parent/target.split('#')[0]).is_file():
                errors.append('Broken reference in '+file.name+': '+target)
    if (SKILL/manifest['preview']).read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        errors.append('Preview is not a PNG')
    ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main', 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with ZipFile(SKILL/manifest['reference']) as z:
        tree = ET.fromstring(z.read('ppt/presentation.xml'))
        size = tree.find('p:sldSz', ns)
        if size.attrib.get('cx') != '12192000' or size.attrib.get('cy') != '6858000':
            errors.append('Reference slide dimensions changed')
        if len(tree.find('p:sldIdLst', ns)) != 19:
            errors.append('Expected 19 reference slides')
        for name in z.namelist():
            if name.endswith('.xml'):
                raw = z.read(name).decode('utf-8')
                if any(t in raw for t in ['周馨怡', '中断风险下供应链', 'MAPPO', 'Multi-agent reinforcement', '宇航 马']):
                    errors.append('Stale source content in '+name)
    result = {'status': 'fail' if errors else 'pass', 'errors': errors}
    print(json.dumps(result, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(check())
