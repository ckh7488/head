"""Illustrate current B25 assembly from its CAD export and documented practices."""
import json
from pathlib import Path

import numpy as np
import trimesh

import check_b19_assembly as C

ROOT = Path(__file__).resolve().parents[2]
B25 = ROOT / 'mechanical' / 'revisions' / 'b25'
JAW_SCREWS = (
    ('JawExteriorScrewLeft', 12., (-71.55, -32.5, 103.5), (-1, 0, 0)),
    ('JawExteriorScrewRight', 12., (74.55, -8.75, 103.5), (1, 0, 0)),
    ('JawAntiRockScrew', 40., (-68.6, 13.2, 103.5), (0, 1, 0)),
)
JAW_INSERTS = ('JawExteriorInsertLeft', 'JawExteriorInsertRight', 'JawAntiRockInsert')
HUB_J1 = ('A4J1FemaleEnvelope', 'A4J1CupPositiveEnvelope', 'A4J1CupGroundEnvelope')
HUB_J2 = ('A4J2FemaleEnvelope', 'A4J2CupPositiveEnvelope', 'A4J2CupGroundEnvelope')
A4_HATCH_LEADS = ('A4W8', 'A4W9', 'A4XT60ExternalMate')
A4_STATION_WASHERS = tuple(f'A4StationFastener{i}' for i in (2, 3, 6, 7))
A4_STATION_NUTS = ('A4StationFastener4', 'A4StationFastener8')
A4_WAGOS = ('A4WagoPositive', 'A4WagoGround')
A4_FIXED_LEADS = ('A4W6', 'A4W6SupplyCup', 'A4W7', 'A4W7SupplyCup',
                  'A4W35', 'A4W35SocketCup', 'A4W36', 'A4W36SocketCup')
A4_INLET_SCREWS = ('A4InletBolt1', 'A4InletBolt2')
A4_INLET_INSERTS = ('A4InletInsert1', 'A4InletInsert2')
CABLE_GUIDE_BENCH = 'cable-guide-bench'
CAMERA_END = ('CameraEatonHeadTie', 'CameraEatonHeadSplice', 'CameraEatonHeadFixedLeg', 'CameraOEMHeadTail')
VIEWS = (
    ('start', '첫 단계', 'base-cup'),
    ('rear-power', '뒤 12 V 소켓과 WAGO', 'a4-wago-wires'),
    ('hub-lock', 'A4 허브와 J2 고정편', 'hub-bolts'),
    ('hatch', '바닥 덮개와 정비 플러그', 'a4-hatch-leads'),
    ('eye-pitch-bearings', '눈 상하 베어링 정렬', 'eye-bearing-align'),
    ('neck-pitch-coupling', '목 상하 축 체결', 'pitch-drive-lock'),
    ('jaw-stay', '강화한 오른쪽 턱 받침 37', 'jaw-bearing-fit'),
    ('jaw-frame', '턱 고정용 프레임 09', 'jaw-frame-inserts'),
    ('jaw-retention', '턱 모듈 세 점 체결', 'jaw-retention-three'),
    ('camera-wire', 'Eaton 카메라 배선', 'camera-route-set'),
    ('rear-skull', '뒤 외장 체결', 'rear-skull-lock'),
    ('final', '조립 완료', 'final-view'),
)
LABELS = {
    'Part019': '09 머리 프레임', 'Part073': '28 앞 외장', 'Part074': '29 뒤 외장',
    'Jaw_37_right_jaw_bearing_stay': '37 오른쪽 턱 받침 · 보강부 포함',
    'Jaw_36_left_jaw_servo_stay': '36 왼쪽 턱 모터 받침', 'CableSaddle': '40 뒤 케이블 가이드',
    'CableGate': '42 뒤 케이블 덮개', 'HubHolder': '35 허브 바닥 덮개', 'HubPCB': 'A4 허브 기판',
    'HubBodyJ1': 'J1 · 5 V XT30', 'HubBodyJ2': 'J2 · 12 V XT30', 'A4J2LeverKeeper': 'J2 플러그 고정편',
    'HubBolt3': 'H3 M3×12 원통머리', 'HubBolt4': 'H4 M3×12 원통머리',
    'JawExteriorScrewLeft': '왼쪽 M3×12 원통머리', 'JawExteriorScrewRight': '오른쪽 M3×12 원통머리',
    'JawAntiRockScrew': '뒤쪽 M3×40 원통머리', 'RearSkullScrewLeft': '뒤 외장 왼쪽 M3×18',
    'RearSkullScrewRight': '뒤 외장 오른쪽 M3×16', 'A4WagoPositive': 'WAGO 221-412 · 12 V +',
    'A4WagoGround': 'WAGO 221-412 · GND', 'A4XT60ExternalSocket': 'XT60E-F · 외부 정비 소켓',
    'A4XT60ExternalMate': 'XT60U-M · 덮개 정비 플러그', 'InputXT60Mate': 'XT60U-M · 외부 12 V 입력',
    'EatonCableNeutral': 'Eaton 550 mm · 중립 배선', 'CameraUSB': 'U20CAM 순정 USB-A 꼬리',
    **{name: f'턱 프레임 {side} TC-M3×3.0 인서트' for name,side in zip(JAW_INSERTS, ('왼쪽','오른쪽','뒤쪽'))},
    **{f'A4W{n}': f'W{n} · 12 V {kind}' for n,kind in ((6,'공급 +'),(7,'공급 GND'),(8,'J2 +'),(9,'J2 GND'),
                                                           (35,'고정 소켓 +'),(36,'고정 소켓 GND'))},
}


def setup(layout, world):
    def read(name):
        return json.loads((B25 / name).read_text())

    world.apply_b25_heat_set_screws()
    catalog = read('xl330-case-screws.json')['seats']
    for name, site in catalog.items():
        world.screws[name] = 2, site['oem_tapping_screw_length_mm'], site['seat_mm'], site['axis']
    if read('design.json')['cad_sha256'] != layout['source_sha256']:
        raise ValueError('B25 viewer expects the current revision CAD export')
    native_screw_rows = [(name, 3, length, seat, [-v for v in outward]) for name,length,seat,outward in JAW_SCREWS]
    for n, x in ((1, .26), (5, 25.26)):
        native_screw_rows.append((f'A4StationFastener{n}', 3, 30., (x, 173.5, -74.6), (0, 1, 0)))
    for n, (x,y) in enumerate(((-25.5, 174.7), (-1.5, 172.)), 1):
        native_screw_rows.append((f'A4InletBolt{n}', 3, 12., (x,y,-50.), (0,0,-1)))
    for n,(x,y) in enumerate(((-30.8,46.2),(-30.8,72.8),(30.8,46.2),(30.8,72.8)), 1):
        length = 12 if n > 2 else 8
        native_screw_rows.append((f'HubBolt{n}', 3, length, (x,y,-70.5 if n > 2 else -72.5), (0,0,-1)))
    for site in layout['motion_geometry']['rear_skull_retention']['stations'].values():
        native_screw_rows.append((site['screw'], 3, site['length_mm'], site['seat_mm'], site['axis']))
    for name,size,length,seat,axis in native_screw_rows:
        world.screws[name] = size,length,seat,axis
    heat = read('heat-set-checks.json')
    return catalog, heat['socket_head_sites'], heat['pin_retainer_sites']


def plan(layout, heat_screws, heat_retainers, world):
    # Host first on the workbench, then show the insert aligned with its CAD axis.
    inserts = {}
    for name,site in {**heat_screws, **heat_retainers}.items():
        axis = site['axis'] if 'axis' in site else world.neutral_screw(name)[3]
        inserts.setdefault(site['host'], []).append((name + 'Insert', (-12*np.asarray(axis)).tolist()))
    step = C.step
    result = []
    rear_inserts = layout['motion_geometry']['rear_cable_service_nuts']['insert_names']
    for old in C.assembly_plan('b25', layout):
        sid,ctx = old['id'],old['ctx']
        if sid.startswith('c3-'):
            continue
        row = dict(old)
        if sid == 'camera-base-feed':
            row.pop('camera_feed')
            row['text'] = 'Eaton 가동선의 맨 끝을 받침 오른쪽 통로로 보내고 위에서 받습니다. 순정 USB-A 꼬리는 바깥에 둡니다.'
        elif sid == 'camera-rotor-feed':
            row.pop('camera_feed')
            row['text'] = '회전판을 내리기 전에 Eaton 선의 맨 끝을 앞쪽 구멍 아래에서 위로 통과시킵니다. 피복을 열린 곡면에 얹습니다.'
        elif sid == 'rear-guide':
            guide, offset = row.pop('place')
            result.extend([
                step('rear-guide-bench', CABLE_GUIDE_BENCH, '빈 케이블 가이드 40을 작업대에 놓습니다.',
                     place=(guide, (0, 0, 0))),
                step('rear-cover-service-nuts', CABLE_GUIDE_BENCH,
                     '40번 가이드 위에서 뒤 배선 덮개용 M3 인서트 다섯 개를 수직으로 열압입합니다.',
                     place=(rear_inserts, (0, 0, 15))),
                step('a4-inlet-inserts', CABLE_GUIDE_BENCH,
                     '40번 가이드의 12 V 입력 단자 받침에 M3 인서트 두 개를 위에서 열압입합니다.',
                     place=(A4_INLET_INSERTS, (0, 0, 12))),
            ])
            row.update(text='인서트를 식힌 뒤 OpenRB USB와 5 V 꼬리를 뒤로 빼고, 40번 가이드를 받침 뒤에서 밀어 넣습니다.',
                       merge=(CABLE_GUIDE_BENCH, offset))
        elif sid == 'rear-cover':
            row['text'] = '정비용 XT60E-F를 달고, 외부 입력 XT60U-M의 두 턱을 홈에 걸어 둡니다. USB와 5 V 전원선을 홈에 놓고 42번 덮개를 위에서 닫습니다.'
        elif sid == 'hub-board-place':
            row['text'] = 'A4 허브 기판과 부품을 35번 바닥 덮개 위에 얹습니다. 기판의 J1은 5 V, J2는 12 V입니다.'
        elif sid == 'hub-bolts':
            row.update(text='H1·H2의 M3×8, J2 고정편을 통과하는 H3·H4의 M3×12를 조입니다. 아래에는 일반 M3 육각너트를 씁니다.',
                       bolts=[f'HubBolt{n}' for n in range(1,5)])
            result.extend([
                step('a4-hub-plugs', ctx, '작업대에서 전원을 분리한 뒤 J1과 J2의 XT30U-F를 꽂습니다. J2 적색은 패드 2, 흑색은 패드 1입니다.',
                     place=(HUB_J1 + HUB_J2, (0,12,0))),
                step('a4-hub-inlet-keeper', ctx, 'J2 플러그의 뒤턱을 고정편이 잡는 위치에 맞춥니다.',
                     place=(('A4J2LeverKeeper',), (0,0,15))),
            ])
        elif sid == 'hatch-fit':
            row['text'] = '정비 XT60 플러그를 바깥 대기 위치에 둔 상태에서 A4 허브가 달린 덮개를 받침 아래에서 올립니다.'
        elif sid == 'camera-bracket-bench':
            row['text'] = '작업대에 코 카메라 브래킷 26을 놓습니다. 코 트레이용 타이는 폭 2.10 mm, 두께 0.47 mm 이하로 준비합니다.'
        elif sid == 'camera':
            row['text'] = '순정 키 플러그를 카메라 기판에 꽂습니다. 카메라 모듈을 뒤 위에서 비스듬히 내려 코받침에 댑니다.'
        elif sid == 'camera-tray-bolts':
            row['text'] = 'M3×8 두 개로 코 트레이의 인서트에 카메라 브래킷을 고정합니다. 위에서 2.5 mm 육각렌치를 사용합니다.'
        elif sid == 'camera-nose-guide':
            row.update(text='코 트레이 슬롯의 작은 타이로 Eaton 외피를 고정한 뒤 가동 선재와 순정 꼬리선을 접합합니다. 접합부는 가동 구간 바깥에 놓습니다.',
                       place=(CAMERA_END,(0,8,8)))
        elif sid == 'camera-route-set':
            row.pop('camera_tail_mount', None)
            row.update(text='Eaton 고정점 사이 550 mm를 배치합니다. 표시된 3D 선은 목이 정면일 때의 경로입니다. 움직이는 외피는 Ø3.00 mm 이하로 재고 가이드에서 R18 이상을 유지합니다.',
                       place=(('EatonCableNeutral','EatonRearStationarySplice'),(0,0,0)))
        elif sid == 'jaw-stay-bench':
            row['text'] = '보강된 37번 오른쪽 턱 받침을 작업대에 둡니다. 위치결정 보스가 손상되지 않았는지 살핍니다.'
        elif sid == 'jaw-to-head':
            row['text'] = '머리를 높게 받치고, 조립된 턱 모듈을 아래에서 올려 09번 프레임의 위치결정면에 대 봅니다.'
        elif sid == 'rear-skull-lock':
            row.pop('place')
            row.pop('place2')
            row['bolts'] = ['RearSkullScrewLeft','RearSkullScrewRight']
        if sid == 'rear-cover-service-nuts':
            result.append(step('a4-socket-body', 'base', '40번 가이드에서 12 V 정비용 XT60E-F를 결합면 쪽에서 끼웁니다.',
                               place=(('A4XT60ExternalSocket',),(0,-25,0))))
            result.append(step('a4-socket-fix', 'base', '정비 소켓 양쪽에 평와셔와 M3 너트를 댑니다. 뒤쪽 너트를 5.5 mm 스패너로 잡고 M3×30 두 개를 조입니다.',
                               place=(A4_STATION_WASHERS + A4_STATION_NUTS,(0,10,0)),
                               bolts=['A4StationFastener1','A4StationFastener5']))
            result.append(step('a4-inlet-body', 'base', '외부 12 V 입력 XT60U-M 몸체를 위에서 내리고 두 턱을 40번 가이드의 아래 홈에 맞춥니다.',
                               place=(('InputXT60Mate',),(0,0,18))))
            continue
        result.append(row)
        hosts = [name for role in ('place','place2') if role in old for name in old[role][0] if name in inserts]
        if hosts:
            mounted = [(name,offset) for host in hosts for name,offset in inserts.pop(host)]
            result.append(step(f'{sid}-heat-inserts',ctx,'이 부품의 M3 인서트를 작업대에서 구멍과 같은 축으로 열압입합니다.',
                               insert_moves=mounted))
        if sid == 'rear-cover-bolts':
            result.extend([
                step('a4-inlet-fix',ctx,'외부 12 V 입력 XT60U-M의 두 턱이 걸린 채로 덮개를 M3×12 두 개로 고정합니다.',bolts=A4_INLET_SCREWS),
                step('a4-wago-holders',ctx,'12 V +와 GND용 WAGO 221-412를 뒤쪽 받침에 놓습니다. 단자 입구는 Y=230 mm입니다.',
                     place=(A4_WAGOS,(0,0,20))),
                step('a4-wago-wires',ctx,'W6·W7은 외부 입력에서 올라와 선반을 지납니다. W35·W36은 정비 소켓에서 같은 극의 WAGO로 연결합니다. 11 mm를 탈피하고 마지막 6 mm를 곧게 넣습니다.',
                     place=(A4_FIXED_LEADS,(0,0,0))),
            ])
        if sid == 'hatch-bolts':
            result.append(step('a4-hatch-leads',ctx,'덮개가 닫힌 뒤 정비용 XT60을 연결합니다. W8·W9는 설계상 피복 노출 경로가 각각 170.58 mm입니다. 그림은 덮개를 닫은 상태의 선 배치입니다.',
                               place=(A4_HATCH_LEADS,(0,0,0))))
        if sid == 'head-frame':
            result.append(step('jaw-frame-inserts',ctx,'09번 프레임의 턱 고정점 세 곳에 TC-M3×3.0 인서트를 열압입합니다.',
                               insert_moves=[(name,(16*np.asarray(outward)).tolist()) for name,(_,_,_,outward) in zip(JAW_INSERTS,JAW_SCREWS)]))
        if sid == 'jaw-to-head':
            result.append(step('jaw-retention-three',ctx,'양쪽 M3×12를 바깥에서 넣고, 뒤쪽 M3×40 전나사를 뒤에서 조입니다. 뒤 외장 29를 끼우기 전에 2.5 mm 육각렌치로 마칩니다.',
                               bolts=[name for name,*_ in JAW_SCREWS]))
        if sid == 'mast-nuts':
            result.append(step('internal-connectors',ctx,'눈 좌우와 턱 모터의 JST, 턱 데이터 분기 커넥터를 배선도에 맞춰 연결합니다.',
                               place=(('HarnessID1EH','HarnessID6EH','HarnessWdata'),(0,0,0))))
        if sid == 'rear-skull-lock':
            result.append(step('a4-input-plug',ctx,'조립과 무전원 극성 확인을 마친 뒤 외부 12 V 어댑터의 XT60을 입력 단자에 연결합니다.',
                               place=(('InputXT60',),(0,18,0))))
    if inserts:
        raise ValueError(f'Unshown B25 inserts: {sorted(inserts)}')
    return result


def screw_model(size, length, seat, axis):
    """Round-head envelope for the supplied ROBOTIS pan-head tapping screw."""
    seat,axis = np.asarray(seat),np.asarray(axis)
    return trimesh.util.concatenate((C.cylinder(2., 2., seat-2*axis, axis), C.cylinder(1., length, seat, axis)))


def tools_for(row, world, models, catalog):
    choices = []
    for name in row.get('bolts', []):
        size,_,seat,axis = world.screw(name)
        point, outward = np.asarray(seat,float), -np.asarray(axis,float)
        if name in catalog:
            tip, radius, length = point + 2*outward, 1.5, 30.
            label = f'십자 드라이버 · {name}'
        else:
            key = world.headless.get(name, {2: 1.5, 2.5: 2., 3: 2.5}.get(size))
            if key is None:
                continue
            tip = point if name in world.headless else point + C.HEAD[size][1]*outward
            radius, length = key/np.sqrt(3), 30.
            label = f'{key:g} mm 육각렌치 · {LABELS.get(name,name)}'
        ident = f'illustrated-tool-{row["id"]}-{name}'
        models[ident] = C.cylinder(radius,length,tip,outward)
        choices.append([{'id': ident,'nut': label,'kind': 'illustration','size': size,
                         'seat': tip.tolist(),'path': [(14*outward).tolist(),[0,0,0]]}])
    if row['id'] == 'a4-socket-fix':
        from shapely.geometry import Polygon
        from check_b21_tools import arm_frame
        profile = Polygon([(-5.75,-3),(-2.8,-3),(-2.8,2.2),(2.8,2.2),(2.8,-3),(5.75,-3),
                           (5.75,2.5),(2.6,7),(2.6,37),(-2.6,37),(-2.6,7),(-5.75,2.5)])
        for index,x in enumerate((.26,25.26),1):
            tip = [x,195.,-74.6]
            direction = [0.,0.,-1.]
            ident = f'illustrated-spanner-a4-{index}'
            mesh = trimesh.creation.extrude_polygon(profile, 2.5)
            mesh.apply_transform(arm_frame((0.,1.,0.),direction,tip))
            models[ident] = mesh
            choices.append([{'id': ident,'nut': f'5.5 mm 스패너 · 정비 소켓 너트 {index}',
                             'kind': 'illustration','size': 3,'seat': tip,'path': [[0,0,-12],[0,0,0]]}])
    return choices


def finish(name):
    if name.endswith('Insert') or name.startswith('A4InletInsert'):
        return 'link'
    if name.startswith(('A4Wago','HubBodyJ','A4J','A4XT60','HarnessID')):
        return 'terminal' if name.startswith('A4Wago') else 'connector'
    if name == 'HarnessWdata':
        return 'terminal'
    if name.startswith(('A4W', 'RearLead')):
        return 'return-wire' if name.startswith(('A4W7','A4W9','A4W36')) else 'feed-wire'
    if name.startswith(('Eaton','CameraEaton','CameraOEM')):
        return 'camera-wire'
    if name == 'HubPCB':
        return 'pcb'
    if name == 'A4J2LeverKeeper':
        return 'frame'
    return None
