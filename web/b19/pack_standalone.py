"""Pack a checked assembly viewer as one private offline HTML file."""

from argparse import ArgumentParser
import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


VIEWER = Path(__file__).resolve().parent


def load_assets(assets, revision, preview):
    data = json.loads((assets / 'steps.json').read_bytes())
    model = (assets / 'model.glb').read_bytes()
    if data['revision'] != revision:
        raise ValueError(f'Expected {revision}, found {data["revision"]}')
    if data.get('modelSha256') != sha256(model).hexdigest():
        raise ValueError('GLB and step metadata do not match')
    if data.get('illustration') and not preview:
        raise ValueError('CAD illustrations require preview packaging')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('cadSha256', '')):
        raise ValueError('Viewer has no exact CAD digest')
    has_qualified_tools = revision in ('B21', 'B22', 'B23', 'B24', 'B25')
    if has_qualified_tools and not re.fullmatch(r'[0-9a-f]{64}', data.get('planSha256') or ''):
        raise ValueError(f'{revision} viewer has no checked assembly-plan digest')
    if not preview and any(step['issues'] for step in data['steps']):
        raise ValueError('Resolve assembly issues before packaging production review')
    if has_qualified_tools and not data.get('wires'):
        raise ValueError(f'{revision} viewer has no CAD cable paths')
    if revision in ('B22', 'B23', 'B24', 'B25') and not preview:
        stops = data.get('stops', [])
        angles = sorted(stop['firstContactDegrees'] for stop in stops)
        if len(angles) != 2 or not angles[0] < 0 < angles[-1]:
            raise ValueError(f'{revision} viewer needs checked stops in both pitch directions')
        if any({'head', 'anchor'} - stop.get('contactPose', {}).keys() for stop in stops):
            raise ValueError(f'{revision} viewer has no checked pitch pose for a stop')
    if revision in ('B23', 'B24', 'B25') and not preview:
        states = data.get('wireStates', [])
        if not data.get('finalView') or len(states) < 3 or not all(state['fullHarness'] for state in states):
            raise ValueError(f'{revision} production viewer needs assembled wiring and all checked comparison paths')
        service_checked = {step['id'] for step in data['steps'] if step.get('serviceChecked')}
        if not {'rear-cover-bolts', 'hatch-bolts'} <= service_checked:
            raise ValueError(f'{revision} production viewer needs both checked cover service paths')
        yaw = next((step for step in data['steps'] if step['id'] == 'yaw-side-tighten'), None)
        if yaw and len(yaw.get('toolPaths', [])) != 4:
            raise ValueError(f'{revision} production viewer needs the four checked yaw driver positions')
    if revision in ('B24', 'B25') and not preview:
        by_stage = {step['id']: step for step in data['steps']}
        eye = by_stage.get('eye-bearing-align', {})
        neck = by_stage.get('pitch-drive-lock', {})
        if not any(move.get('temporary') for move in eye.get('moves', [])) or not neck.get('toolPaths'):
            raise ValueError('B24 production viewer needs both checked pitch-axis tool paths')

    return data, model


def bundle_viewer():
    text = (VIEWER / 'viewer.js').read_text(encoding='utf-8')
    return subprocess.run(['npx', '--yes', 'esbuild@0.25.12', '--bundle', '--format=esm', '--minify',
                           '--loader=js', '--sourcefile=viewer.js'],
                          input=text, text=True, encoding='utf-8', cwd=VIEWER, capture_output=True, check=True).stdout


def credits():
    license = (VIEWER.parent / 'node_modules' / 'three' / 'LICENSE').read_text(encoding='utf-8')
    return ('\n<!--\n' + license + '\nSkull geometry adapted from BoneHub Visible Human Full-Skeleton 3D Bone Models.\n'
            'https://doi.org/10.57967/hf/10464 (CC BY 4.0)\n-->\n')


def build(assets, output, revision, preview=False, hosted=False):
    data, model = load_assets(assets, revision, preview)
    bundle = bundle_viewer()
    markup = (VIEWER / 'index.html').read_text(encoding='utf-8')
    if preview and not data.get('illustration'):
        status = '<span class="sub" id="step-count"></span>'
        markup = markup.replace(status, status + '<span class="sub">중간 검토본</span>')
    markup, count = re.subn(r'\s*<script type="importmap">.*?</script>', '', markup, flags=re.S)
    if count != 1:
        raise ValueError('Viewer import map did not match')
    css = (VIEWER / 'viewer.css').read_text(encoding='utf-8')
    if hosted:
        output.mkdir(parents=True, exist_ok=True)
        if revision == 'B25':
            markup = markup.replace('<html lang="ko">', '<html lang="ko" data-hosted="b25">')
        (output/'index.html').write_text(markup + credits(), encoding='utf-8')
        (output/'viewer.css').write_text(css, encoding='utf-8')
        (output/'viewer.js').write_text(bundle, encoding='utf-8')
        (output/'model.glb').write_bytes(model)
        (output/'steps.json').write_bytes((assets/'steps.json').read_bytes())
        print(output)
        return
    data['embeddedModel'] = base64.b64encode(model).decode('ascii')
    markup = markup.replace('<link rel="stylesheet" href="viewer.css">', '<style>' + css + '</style>')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    script = bundle.replace('</script', '<\\/script')
    scripts = f'<script id="embedded-data" type="application/json">{payload}</script>\n'
    scripts += ('<script type="module">\n(async () => {\n' + script +
                '\n})().catch(error => { console.error(error); const label = document.getElementById("loading"); ' +
                'if (label) label.textContent = "3D 모델을 열지 못했습니다. WebGL을 지원하는 브라우저에서 다시 여세요."; });\n</script>')
    markup, count = re.subn(r'<script type="module">.*?</script>', lambda match: scripts, markup, flags=re.S)
    if count != 1:
        raise ValueError('Viewer module did not match')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markup + credits(), encoding='utf-8')
    print(output, output.stat().st_size)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('assets', type=Path, help='Directory containing verified model.glb and steps.json')
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='B21')
    parser.add_argument('--preview', action='store_true', help='Include known assembly issues in a private test preview')
    parser.add_argument('--hosted', action='store_true', help='Write a split viewer folder for a static HTTP server')
    args = parser.parse_args()
    build(args.assets, args.output, args.revision, args.preview, args.hosted)
