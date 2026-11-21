"""Install and align the fixed eye-pitch mounts before the cradle enters the head."""


ALIGNMENT_FLAG = 'eye_bearing_alignment'


def plan(steps, layout):
    from check_b19_assembly import step

    geometry = layout['motion_geometry']['eye_pitch_bearings']
    supports = geometry['supports']
    superseded = {'eye-mounts', 'eye-mount-pins', 'eye-mount-screws'}
    revised = []
    for item in steps:
        if item['id'] in superseded:
            continue
        if item['id'] != 'eye-module':
            revised.append(item)
            continue

        for support in supports:
            side = support['side']
            label = '왼쪽' if side == 'left' else '오른쪽'
            context = f'eye-bearing-{side}'
            revised.extend([
                step(f'eye-bearing-bracket-{side}', context,
                     f'작업대에 {label} 13번 지지대를 포켓이 위를 향하게 놓습니다.',
                     place=([support['bracket']], (0, 0, 0))),
                step(f'eye-bearing-insert-{side}', context,
                     '외륜이 들어갈 원통 벽에만 천천히 굳는 고정제를 얇게 바릅니다. 베어링을 단턱에 앉히고 바깥 면으로 튀어나오지 않는지 확인합니다.',
                     pins=([support['bearing']], tuple(support['insertion_mm']))),
            ])
        for support in supports:
            side = support['side']
            label = '왼쪽' if side == 'left' else '오른쪽'
            revised.extend([
                step(f'eye-bearing-frame-{side}', 'neck',
                     f'{label} 지지대를 앞에서 머리 프레임의 자리에 밀어 넣습니다.',
                     merge=(f'eye-bearing-{side}', item['merge'][1])),
                step(f'eye-bearing-frame-bolt-{side}', 'neck',
                     '바깥에서 2.5 mm 육각렌치로 M3×16 한 개를 조입니다.',
                     bolts=[support['bolt']]),
            ])
        revised.append(step(
            'eye-bearing-align', 'neck',
            '눈 모듈을 넣기 전에 베어링 두 개에 Ø3×150 연마봉을 통과시켜 정렬합니다. 봉은 손으로 미끄러지는 것을 쓰고, 고정제가 굳은 뒤 뺍니다.',
            **{ALIGNMENT_FLAG: geometry['frame_alignment_jig']},
        ))
        revised.append(dict(item, text='크래들 양쪽 핀 구멍 안쪽에만 고정제를 소량 묻힙니다. 지지대 사이로 눈 모듈을 정면에서 밀어 넣습니다.'))
        left, right = supports
        revised.append(step(
            'eye-mount-pins', 'neck',
            '내륜에 손으로 미끄러지는 깨끗한 Ø3×13 연마핀을 바깥에서 넣습니다. 크래들과 핀이 붙고 내륜이 깨끗한 상태에서 눈 상하가 손으로 부드럽게 도는지 확인합니다.',
            pins=([left['pin']], (-18, 0, 0)), pins2=([right['pin']], (18, 0, 0)),
        ))
    return revised


def axis_gauge(world, installed, station):
    from check_b19_assembly import cylinder, sweep

    length = station['length_mm']
    diameter = station['diameter_mm']
    y, z = station['axis_yz_mm']
    fixture = 'EyePitchAlignmentGauge'
    world.cache[fixture] = cylinder(diameter/2, length, (-length/2, y, z), (1, 0, 0))
    try:
        hits = sweep(world, [fixture], installed, station['feed_offset_mm'], limit=1e-6)
    finally:
        world.cache.pop(fixture)
    return {'status': 'fail' if hits else 'pass', 'tool_diameter_mm': diameter, 'tool_length_mm': length,
            'route_offset_mm': station['feed_offset_mm'],
            'interferences': [{'parts': list(pair), **hit} for pair, hit in hits.items()]}
