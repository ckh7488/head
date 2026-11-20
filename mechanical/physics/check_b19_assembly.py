"""Walk the B19 assembly procedure step by step and check every move against the parts already in place.

Each step places parts, drives screws, starts nuts or pushes pins. The checker keeps one
set of installed parts per work context (the base, the neck on the bench, the eye module
on the bench and so on) and tests:

* placing: the moving group swept along its insertion offset against the installed parts;
* screws: the shank (at 0.38 × the nominal size, so tap holes count as open) and head
  swept in along the screw axis, then a straight hex key from the head outwards;
* nuts: the nut swept along its approach, then whether an open-end spanner or fingers can
  reach it from any side;
* pins: the pin swept in along its approach.

Run export_cad.py --world on the B19 assembly and dump steps.js hardware first (see the B19
README). The report lists every collision and every screw whose key has less than 12 mm of
straight access.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

import fcl
import manifold3d as md
import numpy as np
from shapely.geometry import Polygon
import trimesh as tr
from trimesh.collision import mesh_to_BVH

FLEXIBLE = ('Harness', 'RearLead', 'CableTie', 'HubPlug', 'HubRearClearance', 'InputXT', 'SupplyXT30',
            'CameraUSB', 'ControlUSB', 'HubBolt', 'Ballast')
OVERLAP_LIMIT = .05
KEY_RADIUS = {2: .8, 2.5: 1.05, 3: 1.3}
HEAD = {2: (1.93, 2.), 2.5: (2.25, 2.5), 3: (2.78, 3.)}
NUT = {2: (4., 1.6), 2.5: (5., 2.), 3: (5.5, 2.4)}
SPANNER_WIDTH = {2: 7., 2.5: 8., 3: 9.}
KEY_REACH = 35.
KEY_WARN = 12.

# Fasteners modelled as CAD objects: name -> (size, length, seat, axis)
CAD_SCREWS = {
    'ID5KeeperScrew1': (2, 8., (17., 23.1, 84.), (0, -1, 0)),
    'ID5KeeperScrew2': (2, 8., (17., 23.1, 108.), (0, -1, 0)),
}
XL330_CASE = 6.


def g(prefix, n, start=0):
    return [f'{prefix}{i}' for i in range(start, start+n)]


def step(sid, ctx, text, **kw):
    return dict(id=sid, ctx=ctx, text=text, **kw)


PLAN = [
    # ---------------- base ----------------
    step('base-cup', 'base', '받침 01을 작업대에 뒤집어 놓지 않고 바로 세웁니다.', place=(['Part000'], (0, 0, 0))),
    step('rear-guide', 'base', 'USB 두 개와 전원 꼬리선을 받침 뒤 벽으로 뺀 뒤, 열린 케이블 가이드 40을 받침 뒤에서 수평으로 밀어 넣습니다.',
         place=(['CableSaddle'], (0, 26, 0))),
    step('rear-guide-bolts', 'base', '뒤에서 M3×16 두 개를 넣고, 받침 안쪽에서 평와셔와 너트를 잡아 조입니다.',
         nuts=(['clipWasher0', 'clipWasher1', 'clipNut0', 'clipNut1'], (0, -14, 0)), bolts=['clipBolt0', 'clipBolt1']),
    step('rear-cover', 'base', '케이블을 안내 홈에 놓고 타이를 건 뒤, 덮개 42를 위에서 닫습니다.', place=(['CableGate'], (0, 0, 25))),
    step('rear-cover-bolts', 'base', '덮개 위에서 M3×16 다섯 개를 넣고 뒤쪽 열린 턱에서 너트를 스패너로 잡아 조입니다.',
         nuts=(g('cableNut', 5), (0, 0, -11)), bolts=g('cableBolt', 5)),
    step('hub-board', 'hatch', '작업대에서 허브를 바닥 덮개 35의 네 기둥에 얹습니다.',
         place=(['HubHolder'], (0, 0, 0))),
    step('hub-board-place', 'hatch', '허브 기판과 부품을 위에서 내립니다.',
         place=(['HubPCB', 'HubBodyJ1', 'HubBodyJ2', 'HubBodyJ3', 'HubBodyJ4', 'HubBodyJ5', 'HubBodyJ6', 'HubBodyJ7',
                 'HubBodyJ8', 'HubBodyF1', 'HubBodyF2', 'HubBodyC1', 'HubBodyC2', 'HubBodyR1', 'HubBodyR2', 'HubBodyR3',
                 'HubBodyD1', 'HubBodyD2'], (0, 0, 26))),
    step('hub-bolts', 'hatch', '덮개 아래에서 5.5 mm 소켓에 M3 너트를 담아 대고, 기판 쪽에서 M3×8 네 개를 조입니다.',
         nuts=(g('hubNut', 4), (0, 0, -17)), bolts=g('hubBolt', 4)),
    step('hatch-fit', 'base', '허브를 단 바닥 덮개를 받침 아래에서 들어 올려 맞춥니다.', merge=('hatch', (0, 0, -30))),
    step('hatch-bolts', 'base', '받침 아래에서 M3×8 네 개를 넣고, 옆 창으로 스패너를 넣어 너트를 잡습니다.',
         nuts=(g('hatchNut', 4), (0, 0, 17)), bolts=g('hatchBolt', 4)),
    step('c3-board', 'c3', '선택 · C3 보드를 왼쪽 캐리어 27의 두 기둥에 올리고 M2×8과 M2 너트로 조입니다.',
         place=(['Part071'], (0, 0, 0))),
    step('c3-board-place', 'c3', 'C3 보드를 올립니다.', place=(['Part070'], (0, 0, 26))),
    step('c3-bolts', 'c3', '위에서 M2×8 두 개, 아래에서 M2 너트.', nuts=(g('c3Nut', 2), (0, 0, -13)), bolts=g('c3Bolt', 2)),
    step('c3-carrier', 'base', '왼쪽 캐리어를 받침에 내립니다.', merge=('c3', (0, 0, 36))),
    step('c3-carrier-bolts', 'base', '받침 아래에서 M3×8 네 개, 위에서 소켓으로 너트.',
         nuts=(g('carrierNut', 4), (0, 0, 18)), bolts=g('carrierBolt', 4)),
    step('openrb-plate', 'openrb', '오른쪽 캐리어 27을 작업대에 둡니다.', place=(['Part072'], (0, 0, 0))),
    step('openrb-board', 'openrb', 'USB-C를 먼저 꽂은 OpenRB를 네 기둥에 올립니다.', place=(['Part069', 'OpenRBUSB'], (0, 0, 26))),
    step('openrb-bolts', 'openrb', '위에서 M2×8 네 개, 아래에서 4 mm 소켓으로 M2 너트.',
         nuts=(g('openrbNut', 4), (0, 0, -13)), bolts=g('openrbBolt', 4)),
    step('openrb-carrier', 'base', 'OpenRB 캐리어를 받침에 내립니다.', merge=('openrb', (0, 0, 36))),
    step('openrb-carrier-bolts', 'base', '받침 아래에서 M3×8 네 개, 위에서 소켓으로 너트.',
         nuts=(g('carrierNut', 4, 4), (0, 0, 18)), bolts=g('carrierBolt', 4, 4)),
    step('yaw-brackets', 'base', '브래킷 05 두 개를 받침에 내립니다.', place=(['Part008', 'Part009'], (0, 0, 30))),
    step('yaw-bracket-feet', 'base', '위에서 M3×8 네 개로 브래킷 다리를 받침의 탭 구멍에 조입니다. 모터 고정 나사 머리가 이 길을 막으므로 모터보다 먼저 합니다.',
         bolts=g('YawBracketFoot', 4)),
    step('yaw-motor', 'base', 'XL430 ID4를 두 브래킷 사이로 위에서 내리고 왼쪽 창에서 JST를 꽂습니다.', place=(['Part017'], (0, 0, 34))),
    step('yaw-side-screws', 'base', '받침 안에서 브래킷 바깥쪽 위 구멍 네 곳에 M2.5×8을 조입니다. 아래 구멍은 브래킷 다리에 머리가 걸려 쓰지 않습니다.',
         bolts=g('XL430YawSideL', 2) + g('XL430YawSideR', 2)),
    step('bearing-bench', 'seat', '작업대에서 베어링 받침 02에 6816을 올립니다.', place=(['Part001'], (0, 0, 0))),
    step('bearing-place', 'seat', '', place=(['Part006'], (0, 0, 28))),
    step('bearing-keepers', 'seat', '외륜 눌림판 41 세 개를 올립니다.',
         place=(['YawBearingRetainer1', 'YawBearingRetainer2', 'YawBearingRetainer3'], (0, 0, 12))),
    step('keeper-bolts', 'seat', '아래에서 M3×8 세 개, 위에서 소켓으로 너트.',
         nuts=(g('keeperNut', 3), (0, 0, 14)), bolts=g('keeperBolt', 3)),
    step('bearing-seat', 'base', '베어링을 단 받침 02를 받침의 세 기둥에 내립니다.', merge=('seat', (0, 0, 33))),
    step('bearing-seat-bolts', 'base', '바닥 통로로 M3×16 세 개, 위에서 소켓으로 너트.',
         nuts=(g('seatNut', 3), (0, 0, 19)), bolts=g('seatBolt', 3)),
    step('rotor-bench', 'rotor', '작업대에서 회전판 04의 볼트 자리 서포트를 뺍니다.', place=(['Part007'], (0, 0, 0))),
    step('rotor-studs', 'rotor', '아래에서 M3×16 네 개를 세우고 위에서 너트로 고정합니다.',
         nuts=(g('rotorNut', 4), (0, 0, 17)), bolts=g('mastStud', 4)),
    step('rotor', 'base', '볼트를 세운 회전판을 베어링 내륜에 내립니다.', merge=('rotor', (0, 0, 26))),
    step('rotor-horn', 'base', '모터 혼 구멍을 맞추고 위에서 M2×8 네 개를 조입니다.', bolts=g('hornBolt', 4)),
    step('base-deck', 'base', '상판 03을 위에서 내립니다.', place=(['Part002'], (0, 0, 29))),
    step('base-deck-bolts', 'base', '바닥 바깥 세 통로로 M3×8, 위에서 소켓으로 너트.',
         nuts=(g('lidNut', 3), (0, 0, 19)), bolts=g('lidBolt', 3)),
    # ---------------- neck and head frame on the bench ----------------
    step('mast', 'neck', '작업대에 목 기둥 06을 세웁니다.', place=(['Part010'], (0, 0, 0))),
    step('yoke', 'neck', '요크 07을 기둥 위에 얹습니다.', place=(['Part011'], (0, 0, 28))),
    step('yoke-bolts', 'neck', '옆 통로에서 스패너로 너트를 잡고 위에서 M3×16 세 개를 조입니다.',
         nuts=(['yokeNut0', 'yokeNut1'], (-18, 0, 0)), nuts2=(['yokeNut2'], (18, 0, 0)), bolts=g('yokeBolt', 3)),
    step('id5-nuts', 'neck', '요크의 모터 장착면 쪽 홈에 ID5 가드용 M2 너트 두 개를 넣습니다.',
         nuts=(['ID5KeeperNut1', 'ID5KeeperNut2'], (0, -8, 0))),
    step('pitch-horn-bench', 'pitchmotor', '작업대에서 XL430 ID5에 08번 클램프를 M2×8 네 개로 조입니다.',
         place=(['Part018'], (0, 0, 0))),
    step('pitch-horn-place', 'pitchmotor', '', place=(['Part016'], (21, 0, 0))),
    step('pitch-horn-bolts', 'pitchmotor', '', bolts=g('pitchHornBolt', 4)),
    step('pitch-motor', 'neck', '클램프를 단 모터를 요크 위에서 내려 넣습니다.', merge=('pitchmotor', (0, 0, 52))),
    step('pitch-side-screws', 'neck', '요크 바깥 두 곳(x 23 mm)에 M2.5×8을 조입니다.', bolts=['XL430PitchSide0', 'XL430PitchSide1']),
    step('id5-keeper', 'neck', 'ID5 플러그를 꽂고 B19 ID5 가드를 바깥에서 댑니다.', place=(['ID5EHKeeper'], (0, 10, 0))),
    step('id5-keeper-screws', 'neck', '가드를 M2×8 두 개로 요크 안 너트에, M2.5×10 두 개로 모터에 조입니다.',
         bolts=['ID5KeeperScrew1', 'ID5KeeperScrew2', 'XL430PitchKeeper0', 'XL430PitchKeeper1']),
    step('pitch-bearings', 'neck', '688 두 개를 요크 양끝 바깥에서 넣습니다.',
         place=(['Part012'], (-19, 0, 0)), place2=(['Part014'], (19, 0, 0))),
    step('head-frame', 'neck', '두 베어링 사이로 머리 프레임 09를 위에서 내립니다.', place=(['Part019'], (0, 0, 31))),
    step('neck-pins', 'neck', 'Ø8 축을 양쪽에서 끼웁니다. 오른쪽 D-flat을 클램프에 맞춥니다.',
         pins=(['Part013'], (-24, 0, 0)), pins2=(['Part015'], (24, 0, 0))),
    step('neck-dowels', 'neck', '축의 직교 구멍을 프레임 세로 구멍에 맞추고 위에서 Ø3×12 평행핀을 밀어 넣습니다.',
         pins=(['PitchPinDowelLeft', 'PitchPinDowelRight'], (0, 0, 16))),
    step('eye-pitch-stay', 'neck', '머리 뒤에서 지지대 34를 프레임에 댑니다.', place=(['Part064'], (0, 35, 0))),
    step('eye-pitch-stay-screws', 'neck', '뒤에서 M3×8 두 개로 지지대를 프레임 탭 구멍에 조입니다.',
         bolts=['EyePitchStayFrame0', 'EyePitchStayFrame1']),
    step('blink-rail', 'neck', '빈 레일 24를 앞에서 밀어 프레임에 댑니다.', place=(['Part063'], (0, -27, 0))),
    step('blink-rail-bolts', 'neck', '뒤에서 M3×16 네 개, 앞쪽 통로에서 소켓으로 너트.',
         nuts=(g('railNut', 4), (0, -24, 0)), bolts=g('railBolt', 4)),
    step('blink-bearings', 'neck', 'MR104ZZ 두 개를 레일 가운데에서 바깥쪽으로 눌러 넣습니다.',
         place=(['Part050'], (18, 0, 0)), place2=(['Part052'], (-18, 0, 0))),
    # eye pitch motor with its horn and link on the bench
    step('eye-pitch-motor-bench', 'eyepitch', '작업대에서 눈 상하 XL330을 모터판 42에 M2×6 네 개로 조입니다.',
         place=(['Part041'], (0, 0, 0))),
    step('eye-pitch-plate', 'eyepitch', '', place=(['Part042'], (18, 0, 0))),
    step('eye-pitch-case-screws', 'eyepitch', '', bolts=g('eyePitchHead', 4)),
    step('eye-pitch-horn', 'eyepitch', '혼 17을 모터 혼에 대고 M2×5 두 개를 조입니다. (10, 145)·(16, 151) 구멍은 링크에 닿으므로 비웁니다.',
         place=(['Part043'], (18, 0, 0))),
    step('eye-pitch-horn-screws', 'eyepitch', '', bolts=['EyePitchHornScrew0', 'EyePitchHornScrew1']),
    step('eye-pitch-link-pin', 'eyepitch', '혼 바깥 구멍에 Ø2×6 핀을 고정제로 세웁니다.', pins=(['EyePitchLinkHornPin'], (8, 0, 0))),
    step('eye-pitch-link', 'eyepitch', '링크 18의 위쪽 구멍을 핀에 끼웁니다.', place=(['Part044'], (6, 0, 0))),
    step('eye-pitch-motor', 'neck', '모터·혼·링크를 머리 정면에서 비스듬히 밀어 넣습니다.', merge=('eyepitch', (8, -32, 0))),
    step('eye-pitch-plate-screws', 'neck', '모터판 위 두 곳에 M3×8을 지지대 탭 구멍에 조입니다.', bolts=['eyePitchHead4', 'eyePitchHead5']),
    # blink motor on the bench
    step('blink-motor-bench', 'blink', '작업대에서 눈꺼풀 XL330을 모터판 46에 M2×6 네 개로 조입니다.', place=(['Part045'], (0, 0, 0))),
    step('blink-plate', 'blink', '', place=(['Part046'], (14, 0, 0))),
    step('blink-case-screws', 'blink', '', bolts=g('blinkMotorHead', 4)),
    step('blink-horn-link', 'blinkhorn', '작업대에서 혼 19와 구동 링크 22를 M2×8·와셔·너트로 먼저 연결합니다. 나사 머리는 혼의 모터 쪽 홈에 들어갑니다.',
         place=(['Part047'], (0, 0, 0)), place2=(['Part056'], (8, 0, 0))),
    step('blink-horn-link-nut', 'blinkhorn', '', nuts=(['middleNut0', 'middleWasher0'], (13, 0, 0)), bolts=['middleServo0']),
    step('blink-center-crank', 'blinkhorn', '가운데 크랭크 21-2를 링크에 M2×8로 연결합니다.', place=(['Part054'], (10, 0, 0))),
    step('blink-center-crank-nut', 'blinkhorn', '', nuts=(['linkNutPos0', 'linkWasherPos0'], (12, 0, 0)), bolts=['centerLink0']),
    step('blink-horn', 'blink', '링크를 단 혼을 모터 혼에 대고 M2×6 두 개를 조입니다. 나머지 두 구멍은 링크·크랭크에 닿으므로 비웁니다.',
         merge=('blinkhorn', (8, 0, 0))),
    step('blink-horn-screws', 'blink', '', bolts=['BlinkHornScrew0', 'BlinkHornScrew1']),
    step('blink-motor', 'neck', '모터판을 앞에서 레일에 댑니다.', merge=('blink', (0, -31, 0))),
    step('blink-motor-bolts', 'neck', '양옆에서 M3×16과 너트로 모터판을 고정합니다.',
         nuts=(g('blinkPlateNut', 2), (-12, 0, 0)), bolts=g('blinkPlateBolt', 2)),
    step('blink-spacers', 'neck', 'B19 간격통 45 두 개를 끼웁니다. 긴 왼쪽 것은 앞에서 곧게, 짧은 오른쪽 것은 앞 아래에서 비스듬히 넣어 가운데 크랭크 양옆에 둡니다. 축을 넣은 뒤 간격통이 축 방향으로 1 mm 남짓 노는 것은 정상입니다. 크랭크는 축 평면을 누르는 M3로 고정됩니다.',
         place=(['BlinkCollarLeft'], (0, -12, 0)), place2=(['BlinkCollarRight'], (0, -10, -10))),
    step('blink-shaft', 'neck', 'Ø4×112 축을 왼쪽에서 베어링·간격통·가운데 크랭크에 통과시킵니다.', pins=(['Part048'], (-87, 0, 0))),
    step('blink-outer-cranks', 'neck', '양끝 크랭크를 끼웁니다.', place=(['Part053'], (-16, 0, 0)), place2=(['Part055'], (16, 0, 0))),
    step('blink-clamps', 'neck', '앞에서 스패너로 크랭크 너트를 잡고 위에서 M3×8 세 개를 조입니다.',
         nuts=(g('crankNut', 3), (0, -15, 0)), bolts=g('crankBolt', 3)),
    # eye module on the bench
    step('eye-cradle', 'eyemod', '작업대에 B19 크래들 12를 둡니다.', place=(['Part024'], (0, 0, 0))),
    step('eyeball-L', 'eyemod', '왼쪽 안구를 크래들 앞에서 곧게 밀어 넣습니다.', place=(['Part029', 'Part030', 'Part031'], (0, -40, 0))),
    step('eyeball-R', 'eyemod', '오른쪽 안구도 같은 방법으로 넣습니다.', place=(['Part033', 'Part034', 'Part035'], (0, -40, 0))),
    step('eye-yaw-pins', 'eyemod', '위에서 Ø2×24 핀을 넣고 크래들 위쪽에만 고정제를 바릅니다.', pins=(['Part032', 'Part036'], (0, 0, 23))),
    step('eye-tie', 'eyemod', '두 안구 크랭크 구멍 안쪽에 경화가 느린 고정제(에폭시 등)를 넘치지 않게 조금 넣어 둡니다. 타이바 15를 핀 없이 크래들 왼쪽 바깥에서 넣습니다. 높이는 제자리 그대로, 앞뒤로는 제자리보다 2.5~3 mm 앞쪽 선을 따라 오른쪽 끝까지 민 뒤 뒤로 당겨 두 안구 크랭크 구멍 위에 맞춥니다. 제자리 선에서 곧게 밀면 왼쪽 ㄷ자 지지대의 뒤 기둥에 걸립니다.',
         path=(['Part037'], [(-110, -2.7, 0), (0, -2.7, 0), (0, 0, 0)])),
    step('eye-tie-pins', 'eyemod', '고정제가 굳기 전에 크래들 위 Ø2.2 구멍으로 Ø2×6 핀을 넣고, Ø1.5~2 mm 막대로 타이바를 지나 크랭크 구멍 바닥까지 밀어 넣습니다. 핀에는 고정제를 바르지 않습니다. 타이바가 핀 위에서 돌아야 합니다.',
         pins=(['EyeYawTiePinL', 'EyeYawTiePinR'], (0, 0, 9))),
    step('eye-mounts', 'eyemod', '양쪽 지지대 13을 대고 바깥에서 Ø3×13 핀을 넣습니다. 지지대 쪽에만 고정제.',
         place=(['Part025'], (-10, 0, 0)), place2=(['Part027'], (10, 0, 0))),
    step('eye-mount-pins', 'eyemod', '', pins=(['Part026'], (-18, 0, 0)), pins2=(['Part028'], (18, 0, 0))),
    step('eye-yaw-motor-bench', 'eyeyaw', '작업대에서 눈 좌우 XL330과 모터판 39를 M2×6 네 개로 조입니다.', place=(['Part038'], (0, 0, 0))),
    step('eye-yaw-plate', 'eyeyaw', '', place=(['Part039'], (0, 0, 17))),
    step('eye-yaw-case-screws', 'eyeyaw', '', bolts=g('eyeYawHead', 4)),
    step('eye-yaw-horn', 'eyeyaw', '혼 16을 대고 M2×5 세 개를 조입니다. (-11.8, -35.5) 구멍은 눈틀에 닿으므로 비웁니다.',
         place=(['Part040'], (0, 0, 10))),
    step('eye-yaw-horn-screws', 'eyeyaw', '', bolts=g('EyeYawHornScrew', 3)),
    step('eye-yaw-motor', 'eyemod', '모터·모터판을 크래들 아래에서 올려 다리를 맞춥니다.', merge=('eyeyaw', (0, 0, -25))),
    step('eye-yaw-feet', 'eyemod', '크래들 위 카운터보어에서 M3×16 두 개를 모터판 다리에 조입니다.', bolts=['EyeYawFoot0', 'EyeYawFoot1']),
    step('eye-tie-bolt', 'eyemod', '혼 아래에서 M2×8을 올려 혼과 타이바를 지나게 하고, 타이바 위에서 평와셔와 M2 너트를 옆으로 넣어 조입니다.',
         bolts=['EyeYawTieHorn'], nuts=(['EyeYawTieHornWasher', 'EyeYawTieHornNut'], (0, 10, 0))),
    step('eye-module', 'neck', '눈 모듈을 머리 프레임 앞에서 뒤로 밀어 넣습니다.', merge=('eyemod', (0, -64, 0))),
    step('eye-mount-screws', 'neck', '바깥에서 M3×16으로 지지대 13 두 개를 프레임 통로에 조입니다.',
         bolts=['CradleMountFrameL', 'CradleMountFrameR']),
    step('eye-pitch-link-pin2', 'neck', '크래들 바깥 귀의 안쪽에서 Ø2×6 핀을 밀어 링크 아래 구멍까지 넣습니다.',
         pins=(['EyePitchLinkCradlePin'], (-7, 0, 0))),
    # lids, jaw, front shell
    step('lid-left', 'lidL', '작업대에서 왼쪽 눈틀 31과 눈꺼풀 32를 맞춥니다.', place=(['Part076', 'Part078'], (0, 0, 0))),
    step('lid-left-pins', 'lidL', 'Ø2×8 핀 두 개를 넣고 눈틀 쪽에만 고정제.', pins=(['Part058'], (-13, 0, 0)), pins2=(['Part061'], (13, 0, 0))),
    step('lid-right', 'lidR', '오른쪽도 같은 방법으로 조립합니다.', place=(['Part077', 'Part079'], (0, 0, 0))),
    step('lid-right-pins', 'lidR', '', pins=(['Part059'], (-13, 0, 0)), pins2=(['Part062'], (13, 0, 0))),
    step('blink-lid-links', 'neck', '양쪽 짧은 링크 23을 크랭크에 M2×8·와셔·너트로 연결합니다.',
         place=(['Part057'], (-12, 0, 0)), place2=(['Part060'], (12, 0, 0))),
    step('blink-lid-link-nuts', 'neck', '', nuts=(['linkNutPos1', 'linkWasherPos1'], (12, 0, 0)),
         nuts2=(['linkNutNeg0', 'linkWasherNeg0'], (-12, 0, 0)), bolts=['centerLink1', 'rightLink0']),
    step('front-skull', 'front', '작업대에 앞 해골 28을 둡니다.', place=(['Part073', 'Part065', 'Part080'], (0, 0, 0))),
    step('camera', 'front', '카메라와 브래킷을 열린 뒤 위에서 비스듬히 내립니다.', place=(['Part066', 'Part067', 'Part068'], (0, 66, 45))),
    step('orbits', 'front', '핀을 끼운 두 눈틀을 뒤에서 눈구멍으로 밀어 넣습니다.', merge=('lidL', (0, 84, 0)), merge2=('lidR', (0, 84, 0))),
    step('front-shell', 'neck', '눈꺼풀을 닫아 둔 앞 외장을 정면에서 밀어 맞춥니다.', merge=('front', (0, -84, 0)), closed_lids=True),
    step('blink-lower-joints', 'neck', '아래에서 4 mm 스패너로 너트를 잡고 옆에서 M2×8로 링크 아래 끝을 조입니다.',
         nuts=(['linkLeftLowerNut0', 'linkWasherPos2'], (0, 0, -13)), nuts2=(['linkRightLowerNut0', 'linkWasherNeg1'], (0, 0, -13)),
         bolts=['centerLower0', 'rightLower0']),
    step('jaw-motor-bench', 'jaw', '작업대에서 턱 XL330을 턱 받침 36에 M2×6 네 개로 조입니다.',
         place=(['Jaw_36_left_jaw_servo_stay'], (0, 0, 0))),
    step('jaw-motor', 'jaw', '', place=(['Jaw_XL330_M288_Jaw'], (16, 0, 0))),
    step('jaw-motor-screws', 'jaw', '', bolts=g('jawMotorHead', 4)),
    step('jaw-body-arm', 'jawbody', 'B19 턱은 턱 30·구동팔 38·힌지팔 39를 한 몸으로 출력한 것입니다. 작업대에 둡니다.',
         place=(['Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm'], (0, 0, 0))),
    step('jaw-arm', 'jaw', '턱을 모터 혼에 맞춥니다.', merge=('jawbody', (-10, 0, 0))),
    step('jaw-arm-screws', 'jaw', '구동팔을 모터 혼에 M2×6 두 개로 조입니다. (-9, 86)·(-3, 92) 구멍은 요크에 닿으므로 비웁니다.',
         bolts=g('JawHornScrew', 2)),
    step('jaw-body', 'jaw', '오른쪽 받침 37과 MR104ZZ를 맞춥니다.',
         place=(['Jaw_37_right_jaw_bearing_stay', 'Jaw_MR104ZZ_jaw_right'], (15, 0, 0))),
    step('jaw-pin', 'jaw', '안쪽에서 Ø4×10 핀을 베어링과 힌지팔로 밀어 넣고 힌지팔 쪽에만 고정제.',
         pins=(['Jaw_Pin_jaw_4x10'], (-15, 0, 0))),
    step('jaw-to-head', 'neck', '머리를 높게 받치고 턱 조립체를 아래에서 올립니다.', merge=('jaw', (0, 0, -76))),
    # head onto the base
    step('head-on-base', 'base', '작업대에서 조립한 머리를 기둥째 들어 회전판의 볼트 위에 내립니다.', merge=('neck', (0, 0, 36))),
    step('mast-nuts', 'base', '열린 통로로 스패너를 넣어 아래 너트를 잡고 위쪽 너트 네 개를 조입니다.', nuts=(g('mastNut', 4), (0, 0, 17))),
    step('rear-skull', 'base', '배선을 마치고 뒤 해골 29를 이음면에 수직으로 밀어 넣습니다.', place=(['Part074'], (0, 68, 0))),
]


def cylinder(radius, height, start, axis):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    mesh = tr.creation.cylinder(radius=radius, height=height, sections=28)
    mesh.apply_transform(tr.geometry.align_vectors([0, 0, 1], axis))
    mesh.apply_translation(np.asarray(start, float) + axis*height/2)
    return mesh


def hexagon(width, height, start, axis, hole):
    radius = width / np.sqrt(3)
    outline = Polygon([(radius*np.cos(a), radius*np.sin(a)) for a in np.arange(6)*np.pi/3 + np.pi/6])
    outline = outline.difference(Polygon([(hole*np.cos(a), hole*np.sin(a)) for a in np.linspace(0, 2*np.pi, 24, endpoint=False)]))
    mesh = tr.creation.extrude_polygon(outline, height)
    mesh.apply_transform(tr.geometry.align_vectors([0, 0, 1], np.asarray(axis, float)))
    mesh.apply_translation(start)
    return mesh


def screw_mesh(size, length, seat, axis):
    radius, height = HEAD[size]
    axis = np.asarray(axis, float)
    head = cylinder(radius, height, np.asarray(seat) - axis*height, axis)
    shank = cylinder(.38*size, length, seat, axis)
    return tr.boolean.union([head, shank], engine='manifold')


class World:
    def __init__(self, cad, hardware, spec):
        self.world = cad/'world'
        self.rows = {row['id']: row for row in hardware if not row.get('tool')}
        self.screws = dict(CAD_SCREWS)
        for item in spec:
            shapes = item['shapes']
            if shapes[0][0] != 'cyl' or len(shapes) < 2:
                continue
            radius, height, start, axis = shapes[0][1:]
            size = min(HEAD, key=lambda s: abs(HEAD[s][0]-radius))
            seat = np.asarray(start) + np.asarray(axis)*(height+.05)
            self.screws[item['name']] = (size, round(shapes[1][2]+.1, 2), tuple(seat), tuple(axis))
        self.cache = {}

    def screw(self, name):
        if name in self.screws:
            return self.screws[name]
        row = self.rows[name]
        if name.startswith('crankBolt'):
            return row['size'], row['length'] - .15, tuple(row['seat'][:2]) + (row['seat'][2] + .15,), tuple(row['axis'])
        if row['type'] == 'head':
            length = XL330_CASE if row['size'] == 2 else 8.
            return row['size'], length, tuple(row['seat']), tuple(row['axis'])
        return row['size'], row['length'], tuple(row['seat']), tuple(row['axis'])

    closed = False
    limit = OVERLAP_LIMIT

    def mesh(self, name):
        if self.closed and name in ('Part078', 'Part079'):
            key = ('closed', name)
            if key not in self.cache:
                self.closed = False
                lid = self.mesh(name).copy()
                self.closed = True
                lid.apply_transform(tr.transformations.rotation_matrix(np.pi/2, (1, 0, 0), (0, -39, 119)))
                self.cache[key] = lid
            return self.cache[key]
        if name in self.cache:
            return self.cache[name]
        if name in self.screws or (name in self.rows and self.rows[name]['type'] in ('bolt', 'head')):
            mesh = screw_mesh(*self.screw(name))
        elif name in self.rows:
            row = self.rows[name]
            axis = np.asarray(row['axis'], float)
            if row['type'] == 'nut':
                width, height = NUT[row['size']]
                mesh = hexagon(width, height, row['seat'], axis, row['size']/2)
            else:
                outer, height = {2: (2.5, .3), 3: (3.5, .5)}[row['size']]
                mesh = hexagon(outer*np.sqrt(3), height, row['seat'], axis, row['size']/2+.1)
        else:
            mesh = tr.load_mesh(self.world/f'{name}.stl')
        if not len(mesh.faces):
            mesh = None
        self.cache[name] = mesh
        return mesh


def solid(mesh):
    return md.Manifold(md.Mesh(np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.uint32)))


def overlap(a, b, shift):
    try:
        return (solid(a).translate(shift) ^ solid(b)).volume()
    except Exception:
        return None


def sweep(world, moving, fixed, offset, final_only=False, limit=None):
    """Move the meshes in `moving` from `offset` to their final place. Return colliding pairs."""
    offset = np.asarray(offset, float)
    distance = np.linalg.norm(offset)
    fractions = [0.] if final_only or distance < 1e-9 else np.linspace(1., 0., max(2, int(np.ceil(distance/.5))+1))
    request = fcl.CollisionRequest()
    hits = {}
    for a in moving:
        ma = world.mesh(a)
        if ma is None:
            continue
        oa = fcl.CollisionObject(mesh_to_BVH(ma))
        lo = np.minimum(ma.bounds[0], ma.bounds[0]+offset) - .2
        hi = np.maximum(ma.bounds[1], ma.bounds[1]+offset) + .2
        for b in fixed:
            mb = world.mesh(b)
            if mb is None or np.any(hi < mb.bounds[0]) or np.any(lo > mb.bounds[1]):
                continue
            ob = fcl.CollisionObject(mesh_to_BVH(mb))
            for f in fractions:
                shift = offset*f
                oa.setTransform(fcl.Transform(shift))
                if not fcl.collide(oa, ob, request, fcl.CollisionResult()):
                    continue
                volume = overlap(ma, mb, shift)
                if volume is None or volume > (limit or world.limit):
                    hits[(a, b)] = {'at_mm': round(float(np.linalg.norm(shift)), 1),
                                    'overlap_mm3': None if volume is None else round(volume, 3)}
                    break
    return hits


def sweep_shifted(world, moving, fixed, shift, base):
    """Sweep parts that sit at `base` (relative to their CAD place) by `shift` back toward `base`."""
    saved = {}
    for a in moving:
        saved[a] = world.cache.get(a)
        world.cache[a] = world.mesh(a).copy().apply_translation(base) if saved[a] is None else saved[a].copy().apply_translation(base)
    try:
        return sweep(world, moving, fixed, shift)
    finally:
        for a in moving:
            if saved[a] is None:
                world.cache.pop(a, None)
            else:
                world.cache[a] = saved[a]


def key_access(world, name, installed):
    size, _, seat, axis = world.screw(name)
    axis = np.asarray(axis, float)
    top = np.asarray(seat) - axis*HEAD[size][1]
    probe = cylinder(KEY_RADIUS[size], 2., top - axis*2.05, -axis)
    obj = fcl.CollisionObject(mesh_to_BVH(probe))
    request = fcl.CollisionRequest()
    others = []
    for b in installed:
        mb = world.mesh(b)
        if mb is None or b == name:
            continue
        reach_lo = np.minimum(top, top - axis*KEY_REACH) - 3
        reach_hi = np.maximum(top, top - axis*KEY_REACH) + 3
        if np.any(reach_hi < mb.bounds[0]) or np.any(reach_lo > mb.bounds[1]):
            continue
        others.append((b, fcl.CollisionObject(mesh_to_BVH(mb))))
    for travel in np.arange(0., KEY_REACH, .5):
        obj.setTransform(fcl.Transform(-axis*travel))
        for b, ob in others:
            if fcl.collide(obj, ob, request, fcl.CollisionResult()):
                return round(float(travel), 1), b
    return KEY_REACH, None


def spanner_access(world, name, installed):
    """Open directions around a nut for an open-end spanner or fingers."""
    row = world.rows.get(name)
    if row is None or row['type'] != 'nut':
        return None
    axis = np.asarray(row['axis'], float)
    size = row['size']
    width, height = NUT[size]
    centre = np.asarray(row['seat']) + axis*height/2
    ref = np.array([1., 0, 0]) if abs(axis[0]) < .9 else np.array([0, 1., 0])
    u = np.cross(axis, ref); u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    request = fcl.CollisionRequest()
    nearby = []
    for b in installed:
        mb = world.mesh(b)
        if mb is None or b == name or np.any(centre+30 < mb.bounds[0]) or np.any(centre-30 > mb.bounds[1]):
            continue
        nearby.append(fcl.CollisionObject(mesh_to_BVH(mb)))
    open_dirs = []
    for angle in np.arange(0, 360, 30):
        d = np.cos(np.radians(angle))*u + np.sin(np.radians(angle))*v
        jaw = tr.creation.box(extents=(SPANNER_WIDTH[size], height*.9, 20.))
        frame = np.column_stack([np.cross(d, axis), axis, d])
        transform = np.eye(4)
        transform[:3, :3] = frame
        transform[:3, 3] = centre + d*(width/2 + 1. + 10.)
        jaw.apply_transform(transform)
        ob = fcl.CollisionObject(mesh_to_BVH(jaw))
        if not any(fcl.collide(ob, o, request, fcl.CollisionResult()) for o in nearby):
            open_dirs.append(int(angle))
    return open_dirs


DIRECTIONS = [np.array(v, float)/np.linalg.norm(v) for v in
              sorted({(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)} - {(0, 0, 0)},
                     key=lambda v: abs(v[0])+abs(v[1])+abs(v[2]))]


def find_clear(world, parts, rigid, offset):
    """Try the stated approach first, then the six axis directions at the same distance."""
    hits = sweep(world, parts, rigid, offset)
    if not hits:
        return None, {}
    distance = max(np.linalg.norm(offset), 15.)
    for d in DIRECTIONS:
        if not sweep(world, parts, rigid, d*distance):
            return tuple((d*distance).round(1).tolist()), hits
    return False, hits


def socket_open(world, name, rigid):
    """A box spanner or socket along the nut axis, from the side away from the screw head."""
    row = world.rows.get(name)
    if row is None or row['type'] != 'nut':
        return True
    axis = np.asarray(row['axis'], float)
    width, height = NUT[row['size']]
    radius = {2: 3.7, 2.5: 4.2, 3: 4.65}[row['size']]
    for sign in (1, -1):
        start = np.asarray(row['seat']) + (axis*height if sign > 0 else np.zeros(3)) + sign*axis*.3
        tube = cylinder(radius, 20., start, sign*axis)
        hole = cylinder(radius-1.1, 20.2, start - sign*axis*.1, sign*axis)
        socket = tr.boolean.difference([tube, hole], engine='manifold')
        ob = fcl.CollisionObject(mesh_to_BVH(socket))
        request = fcl.CollisionRequest()
        blocked = False
        for b in rigid:
            mb = world.mesh(b)
            if mb is None or b == name:
                continue
            if np.any(socket.bounds[1] < mb.bounds[0]) or np.any(socket.bounds[0] > mb.bounds[1]):
                continue
            if fcl.collide(ob, fcl.CollisionObject(mesh_to_BVH(mb)), request, fcl.CollisionResult()):
                blocked = True
                break
        if not blocked:
            return True
    return False


def run(cad, hardware, spec):
    world = World(cad, hardware, spec)
    installed = {}
    report = []
    for st in PLAN:
        ctx = installed.setdefault(st['ctx'], [])
        world.limit = st.get('limit', OVERLAP_LIMIT)
        rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        issues = []
        notes = []
        for key in ('merge', 'merge2'):
            if key in st:
                other, offset = st[key]
                moving = [p for p in installed.pop(other) if not p.startswith(FLEXIBLE)]
                world.closed = st.get('closed_lids', False)
                alternative, hits = find_clear(world, moving, rigid, offset)
                world.closed = False
                if alternative:
                    notes.append(f'{other} assembly: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                    hits = {}
                for (a, b), hit in hits.items():
                    issues.append(f'{a} ↔ {b} while moving in ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
                ctx.extend(moving)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for key in ('place', 'place2', 'pins', 'pins2'):
            if key in st:
                parts, offset = st[key]
                alternative, hits = find_clear(world, parts, rigid, offset)
                if alternative:
                    notes.append(f'{", ".join(parts)}: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                elif alternative is False:
                    for (a, b), hit in hits.items():
                        issues.append(f'{a} ↔ {b} while moving in ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
                ctx.extend(parts)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        if 'path' in st:
            parts, points = st['path']
            for start, end in zip(points, points[1:]):
                shift = np.asarray(start, float) - np.asarray(end, float)
                moving_end = np.asarray(end, float)
                for (a, b), hit in sweep_shifted(world, parts, rigid, shift, moving_end).items():
                    issues.append(f'{a} ↔ {b} on the path segment ending at {tuple(end)} ({hit["overlap_mm3"]} mm³)')
            ctx.extend(parts)
            rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for key in ('nuts', 'nuts2'):
            if key in st:
                parts, offset = st[key]
                alternative, hits = find_clear(world, parts, rigid, offset)
                if alternative:
                    notes.append(f'{", ".join(parts)}: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                    hits = {}
                for (a, b), hit in hits.items():
                    issues.append(f'{a} ↔ {b} while placing the nut ({hit["at_mm"]} mm, {hit["overlap_mm3"]} mm³)')
                ctx.extend(parts)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for name in st.get('bolts', []):
            size, length, seat, axis = world.screw(name)
            approach = -np.asarray(axis, float)*(length+3.)
            for (a, b), hit in sweep(world, [name], rigid, approach).items():
                issues.append(f'{a} ↔ {b} while driving the screw ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
            ctx.append(name)
            rigid.append(name)
            reach, blocker = key_access(world, name, rigid)
            if reach < KEY_WARN:
                notes.append(f'{name}: straight key reach {reach} mm (blocked by {blocker})')
        for key in ('nuts', 'nuts2'):
            if key in st:
                for nut in st[key][0]:
                    dirs = spanner_access(world, nut, rigid)
                    if dirs == [] and not socket_open(world, nut, rigid):
                        notes.append(f'{nut}: no open side for a spanner, fingers or a socket; needs a pocket that holds it')
        row = {'id': st['id'], 'context': st['ctx'], 'text': st['text'], 'issues': issues, 'notes': notes}
        report.append(row)
        print(st['id'], 'CLEAR' if not issues else issues, notes if notes else '', flush=True)
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='export_cad.py --world output for B19')
    parser.add_argument('hardware', type=Path, help='steps.js hardware dumped as JSON {"hardware": [...]}')
    parser.add_argument('spec', type=Path, help='hardware-spec.json from build_b19_review_fixes.py')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    data = json.loads(args.hardware.read_text())
    result = run(args.cad, data['hardware'], json.loads(args.spec.read_text()))
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    bad = [row['id'] for row in result if row['issues']]
    print(f'{len(result)} steps, {len(bad)} with collisions', bad)
