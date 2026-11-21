"""Render the checked B19 assembly walk (check_b19_assembly.py report) as numbered Markdown steps."""
from argparse import ArgumentParser
import json
from pathlib import Path
import re

SECTIONS = {
    'base': '받침', 'hatch': '받침', 'c3': '받침', 'openrb': '받침', 'seat': '받침', 'rotor': '받침',
    'neck': '목과 머리 프레임', 'pitchmotor': '목과 머리 프레임',
    'eyepitch': '눈 상하 모터', 'blinkhorn': '눈꺼풀 모터', 'blink': '눈꺼풀 모터',
    'eyeL': '눈 모듈', 'eyeR': '눈 모듈', 'eyetie': '눈 모듈', 'eyemod': '눈 모듈', 'eyeyaw': '눈 모듈',
    'eye-bearing-left': '눈 상하 베어링', 'eye-bearing-right': '눈 상하 베어링',
    'lidL': '눈꺼풀과 앞 외장', 'lidR': '눈꺼풀과 앞 외장', 'front': '눈꺼풀과 앞 외장', 'camerabench': '코 카메라',
    'jawstay': '턱', 'jawbody': '턱', 'jaw': '턱',
}
BENCH = {'hatch', 'c3', 'openrb', 'seat', 'rotor', 'pitchmotor', 'eyepitch', 'blinkhorn', 'blink', 'eyeL', 'eyeR',
         'eyetie', 'eyemod', 'eyeyaw', 'eye-bearing-left', 'eye-bearing-right',
         'lidL', 'lidR', 'front', 'camerabench', 'jawstay', 'jawbody', 'jaw'}
WORDS = {(1, 0, 0): '오른쪽(+x)', (-1, 0, 0): '왼쪽(−x)', (0, 1, 0): '뒤(+y)', (0, -1, 0): '앞(−y)',
         (0, 0, 1): '위(+z)', (0, 0, -1): '아래(−z)'}


def direction(text):
    numbers = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', text)]
    parts = [WORDS[tuple(int(i == k)*(1 if v > 0 else -1) for i in range(3))]
             for k, v in enumerate(numbers[:3]) if abs(v) > 1e-6]
    if len(parts) == 1:
        return parts[0] + ' 쪽'
    return ' '.join(parts) + ' 사이 비스듬한 방향'


def note_text(note):
    match = re.match(r'(.+): stated approach \((.+?)\) is blocked; \((.+?)\) is clear', note)
    if match:
        what = '너트와 와셔는 ' if re.search(r'Nut|Washer', match.group(1)) else ''
        return f'{what}{direction(match.group(3))}에서 넣어야 다른 부품에 닿지 않습니다.'
    match = re.match(r'(.+) assembly: stated approach \((.+?)\) is blocked; \((.+?)\) is clear', note)
    if match:
        return f'{direction(match.group(3))}에서 넣어야 다른 부품에 닿지 않습니다.'
    if 'straight key reach' in note:
        return '육각렌치가 곧게 들어가는 길이가 짧습니다. 볼포인트 렌치를 씁니다.'
    if 'no open side' in note:
        return '너트를 손이나 공구로 잡을 공간이 없습니다.'
    return note


def render(report):
    lines, section, number, seen = [], None, 0, set()
    for row in report:
        title = SECTIONS[row['context']]
        if title != section:
            section = title
            lines += ['', f'## {title}' + (' (이어서)' if title in seen else ''), '']
            seen.add(title)
        if not row['text']:
            if row['notes'] or row['issues']:
                carry = [f'   - {note_text(n)}' for n in row['notes']]
                lines.extend(line for line in dict.fromkeys(carry) if line not in lines)
                if row['issues'] and '막힘' not in lines[-1]:
                    lines[-1] += ' **— 막힘, 아래 "조립이 막히는 곳" 참조**'
            continue
        number += 1
        bench = ' (작업대)' if row['context'] in BENCH else ''
        flag = ' **— 막힘, 아래 "조립이 막히는 곳" 참조**' if row['issues'] else ''
        lines.append(f'{number}. {row["text"]}{bench}{flag}')
        for note in dict.fromkeys(note_text(n) for n in row['notes']):
            lines.append(f'   - {note}')
    return '\n'.join(lines).strip() + '\n'


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.report.read_text())))
