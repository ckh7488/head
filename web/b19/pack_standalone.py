"""Pack a checked assembly viewer as one private offline HTML file."""

from argparse import ArgumentParser
import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


VIEWER = Path(__file__).resolve().parent


def build(assets, output, revision, preview=False):
    data = json.loads((assets / 'steps.json').read_bytes())
    model = (assets / 'model.glb').read_bytes()
    if data['revision'] != revision:
        raise ValueError(f'Expected {revision}, found {data["revision"]}')
    if data.get('modelSha256') != sha256(model).hexdigest():
        raise ValueError('GLB and step metadata do not match')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('cadSha256', '')):
        raise ValueError('Viewer has no exact CAD digest')
    if revision == 'B21' and not re.fullmatch(r'[0-9a-f]{64}', data.get('planSha256') or ''):
        raise ValueError('B21 viewer has no checked assembly-plan digest')
    if not preview and any(step['issues'] for step in data['steps']):
        raise ValueError('Resolve assembly issues before packaging production review')
    if revision == 'B21' and not data.get('wires'):
        raise ValueError('B21 viewer has no CAD cable paths')

    data['embeddedModel'] = base64.b64encode(model).decode('ascii')
    text = (VIEWER / 'viewer.js').read_text(encoding='utf-8')
    bundle = subprocess.run(['npx', '--yes', 'esbuild@0.25.12', '--bundle', '--format=esm', '--minify',
                             '--loader=js', '--sourcefile=viewer.js'],
                            input=text, text=True, encoding='utf-8', cwd=VIEWER, capture_output=True, check=True).stdout
    markup = (VIEWER / 'index.html').read_text(encoding='utf-8')
    css = (VIEWER / 'viewer.css').read_text(encoding='utf-8')
    markup = markup.replace('<link rel="stylesheet" href="viewer.css">', '<style>' + css + '</style>')
    markup, count = re.subn(r'\s*<script type="importmap">.*?</script>', '', markup, flags=re.S)
    if count != 1:
        raise ValueError('Viewer import map did not match')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    script = bundle.replace('</script', '<\\/script')
    scripts = f'<script id="embedded-data" type="application/json">{payload}</script>\n'
    scripts += ('<script type="module">\n(async () => {\n' + script +
                '\n})().catch(error => { console.error(error); const label = document.getElementById("loading"); ' +
                'if (label) label.textContent = "3D 모델을 열지 못했습니다. WebGL을 지원하는 브라우저에서 다시 여세요."; });\n</script>')
    markup, count = re.subn(r'<script type="module">.*?</script>', lambda match: scripts, markup, flags=re.S)
    if count != 1:
        raise ValueError('Viewer module did not match')
    license = (VIEWER.parent / 'node_modules' / 'three' / 'LICENSE').read_text(encoding='utf-8')
    markup += ('\n<!--\n' + license + '\nSkull geometry adapted from BoneHub Visible Human Full-Skeleton 3D Bone Models.\n'
               'https://doi.org/10.57967/hf/10464 (CC BY 4.0)\n-->\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markup, encoding='utf-8')
    print(output, output.stat().st_size)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assets', type=Path, help='Directory containing verified model.glb and steps.json')
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='B21')
    parser.add_argument('--preview', action='store_true', help='Include known assembly issues in a private test preview')
    args = parser.parse_args()
    build(args.assets, args.output, args.revision, args.preview)
