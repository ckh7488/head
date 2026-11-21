"""Check each assembly move against the parts already installed.

Each step places parts, drives screws, starts nuts or pushes pins. The checker keeps one
set of installed parts per work context (the base, the neck on the bench, the eye module
on the bench and so on) and tests:

* placing: the moving group swept along its insertion offset against the installed parts;
* screws: the shank (at 0.38 × the nominal size, so tap holes count as open) and head
  swept in along the screw axis, then a straight hex key from the head outwards;
* nuts: the nut swept along its approach, then whether an open-end spanner or fingers can
  reach it from any side;
* pins: the pin swept in along its approach;
* eye tie bar: clearance around the horizontal approach, including transverse misalignment.

Run export_cad.py --world on the assembly and dump steps.js hardware first. The report lists
collisions and short tool access. Pass --revision b19 to reproduce the earlier plan.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
import re
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
PATH_SAMPLE_MM = .25
EYE_TIE_TRAVEL_ERRORS_MM = {'slide': .5, 'lower': .15}
KEY_RADIUS = {2: .8, 2.5: 1.05, 3: 1.3}
B21_KEY_RADII = {2: .89, 2.5: 1.17, 3: 1.48}
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


B19_PLAN = [
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

B20_CHANGES = {
    'neck-pins': {
        'text': '접착제를 바르기 전에 실측한 Ø3 연마 평행핀이 두 축의 직교 구멍에 잘 들어가는지 확인합니다. Ø8 축을 양쪽에서 끼우고 오른쪽 D-flat을 08번 클램프에 맞춥니다.',
    },
    'neck-dowels': {
        'text': '축의 직교 구멍을 프레임 허브 세로 구멍에 맞추고 위에서 Ø3×12 평행핀을 넣습니다. 위아래 끝이 허브 면에서 각각 0.4 mm 들어가게 맞춥니다. 손으로 움직여 걸림을 확인한 뒤 핀은 회전하는 허브 안에만 고정합니다. 고정제가 베어링에 닿지 않게 하고, 오른쪽 D-flat 끝과 08번 클램프는 K2 에폭시로 고정합니다. 경화 후 손으로 다시 움직여 확인합니다.',
    },
    'eye-cradle': {
        'text': '작업대에 B20 크래들 12를 둡니다.',
    },
    'eye-tie': {
        'text': '두 눈을 정면으로 둡니다. 핀을 끼우지 않은 타이바 15의 들어가는 쪽 구멍 중심을 크래들 왼쪽 입구의 표시 홈에 맞춥니다. 타이바 윗면을 입구 천장보다 약 1.5 mm 낮게 두고 오른쪽으로 수평으로 밉니다. 두 크랭크 구멍과 좌우 위치가 맞으면 뒤로 밀면서 내려 구멍을 맞춥니다. 고정제 없이 경로를 확인한 뒤 타이바를 빼고, 크랭크 구멍에 경화가 느린 고정제를 소량 넣어 다시 끼웁니다.',
        'path': (['Part037'], [(-110, -2.8, .8), (0, -2.8, .8), (0, 0, 0)]),
    },
    'eye-yaw-feet': {
        'text': '모터판 39 다리의 Ø2.6 구멍은 조립 전에 M3 탭을 냅니다. 크래들 위 카운터보어에서 M3×16 두 개를 모터판 다리의 탭에 조입니다.',
    },
}
PLAN = [dict(row, **B20_CHANGES.get(row['id'], {})) for row in B19_PLAN]

B21_CHANGES = {
    'rear-guide-bolts': {
        'text': '뒤에서 M3×16 두 개를 넣습니다. 받침 위로 5.5 mm 소켓을 내려 넣고 안쪽에서 뒤쪽 너트에 밀어 끼워 잡습니다.',
        'socket_inset_mm': 8.,
    },
    'rotor-studs': {
        'text': '아래에서 M3×16 네 개를 올립니다. 위 너트의 평평한 두 면을 앞뒤로 향하게 하고 스패너로 움직이지 않게 잡습니다. 아래에서 2.5 mm 육각렌치로 볼트를 조입니다.',
        'set_nut_phases': dict.fromkeys(g('rotorNut', 4), -30),
        'paired_drivers': list(zip(g('rotorNut', 4), g('mastStud', 4), strict=True)),
    },
    'c3-board': {'text': '선택 · 왼쪽 C3 캐리어 27을 작업대에 둡니다.'},
    'c3-bolts': {'text': 'C3 클램프 두 개를 M3×8 나사와 일반 M3 너트로 고정합니다.'},
    'id5-keeper': {'text': 'ID5 플러그를 꽂고 가드를 바깥에서 댑니다.'},
    'id5-keeper-screws': {
        'text': '가드를 새 M3 탭 두 곳에 M3×8로 고정하고, 본체에 물리는 두 곳은 모터 규격 M2.5×10으로 조입니다.',
    },
    'blink-horn': {
        'text': '링크를 단 혼을 모터의 출력 플랜지에 댑니다. 모터 전원을 끈 상태에서 플랜지를 돌려 두 나사 구멍을 먼저 맞춥니다.',
    },
    'blink-horn-link': {
        'text': '작업대에서 혼 19와 구동 링크 22의 핀 구멍을 맞춥니다.',
    },
    'blink-horn-link-nut': {
        'text': '연마 핀을 넣고 링크가 돌아가는지 확인합니다. M3 무두나사는 핀이 옆으로 빠지지 않게 막는 깊이까지만 조입니다.',
        'pins': (['BlinkPivotServo'], (10, 0, 0)),
        'nuts': ([], (0, 0, 0)),
        'bolts': ['BlinkPivotServoRetainer'],
    },
    'blink-center-crank': {
        'text': '가운데 크랭크 21-2와 구동 링크의 핀 구멍을 맞춥니다.',
    },
    'blink-center-crank-nut': {
        'text': '평행핀과 M3 무두나사를 끼워 링크를 연결합니다.',
        'pins': (['BlinkPivotDrive'], (10, 0, 0)),
        'nuts': ([], (0, 0, 0)),
        'bolts': ['BlinkPivotDriveRetainer'],
    },
    'eye-cradle': {'text': '작업대에 눈 크래들 12를 둡니다.'},
    'eye-tie-bolt': {
        'text': '눈 좌우 혼의 아래쪽에서 평행핀을 넣고 M3 무두나사를 끼워 타이바를 연결합니다. 연결부가 손으로 움직이는지 확인합니다.',
        'pins': (['EyeYawDrivePivot'], (0, 0, -10)),
        'nuts': ([], (0, 0, 0)),
        'bolts': ['EyeYawDrivePivotRetainer'],
    },
    'blink-lid-links': {
        'text': '양쪽 짧은 링크 23을 크랭크에 대고 핀 구멍을 맞춥니다.',
    },
    'blink-lid-link-nuts': {
        'text': '양쪽 크랭크 관절의 평행핀을 가운데 쪽에서 넣고 M3 무두나사로 빠짐을 막습니다.',
        'pins': (['BlinkPivotUpperL'], (10, 0, 0)),
        'pins2': (['BlinkPivotUpperR'], (-10, 0, 0)),
        'nuts': ([], (0, 0, 0)),
        'nuts2': ([], (0, 0, 0)),
        'bolts': ['BlinkPivotUpperLRetainer', 'BlinkPivotUpperRRetainer'],
    },
    'blink-lower-joints': {
        'text': '두 눈을 정면으로 둡니다. 전원을 끈 상태에서 링크와 양쪽 눈꺼풀을 완전히 닫아 핀 구멍을 맞춥니다. 가운데 쪽에서 평행핀과 M3 무두나사를 끼운 뒤 손으로 열고 닫아 걸림을 확인합니다.',
        'blink_deg': 90.,
        'blink_access_checks_deg': [85., 87.5],
        'pins': (['BlinkPivotLowerL'], (10, 0, 0)),
        'pins2': (['BlinkPivotLowerR'], (-10, 0, 0)),
        'nuts': ([], (0, 0, 0)),
        'nuts2': ([], (0, 0, 0)),
        'bolts': ['BlinkPivotLowerLRetainer', 'BlinkPivotLowerRRetainer'],
    },
    'mast-nuts': {
        'text': '기둥 옆 열린 통로로 5.5 mm 스패너 두 개를 넣습니다. 아래 너트를 한 스패너로 잡고, 위 너트를 다른 스패너로 조입니다. 네 곳을 같은 방법으로 조입니다.',
        'paired_nuts': list(zip(g('rotorNut', 4), g('mastNut', 4), strict=True)),
    },
    'jaw-body': {
        'text': '턱의 오른쪽 받침 37과 베어링을 뒤쪽 위에서 비스듬히 내려 맞춥니다.',
        'place': (['Jaw_37_right_jaw_bearing_stay', 'Jaw_MR104ZZ_jaw_right'], (0, 12, 12)),
    },
}

SPANNER_STAGES = {'rear-cover-bolts', 'hatch-bolts', 'rotor-studs', 'yoke-bolts', 'blink-clamps', 'mast-nuts'}
SOCKET_STAGES = {'rear-guide-bolts', 'hub-bolts', 'c3-bolts', 'c3-carrier-bolts', 'openrb-bolts', 'openrb-carrier-bolts',
                 'keeper-bolts', 'bearing-seat-bolts', 'base-deck-bolts', 'blink-rail-bolts'}


def b21_plan():
    revised = []
    for original in PLAN:
        sid = original['id']
        if sid == 'id5-nuts':
            continue
        if sid == 'c3-bolts':
            revised.append(step('c3-clamps', 'c3', 'C3 기판 양쪽에 클램프를 위에서 댑니다.',
                                place=(g('C3Clamp', 2), (0, 0, 15))))
        row = dict(original, **B21_CHANGES.get(sid, {}))
        for role in ('nuts', 'nuts2'):
            if role in row and not row[role][0]:
                row.pop(role)
        mode = ('spanner',) if sid in SPANNER_STAGES else ('socket',) if sid in SOCKET_STAGES else ('socket', 'spanner')
        targets = [name for role in ('nuts', 'nuts2') for name in row.get(role, ([], None))[0]
                   if 'washer' not in name.lower()]
        if sid == 'mast-nuts':
            targets += g('rotorNut', 4)
        if targets:
            row['hold_nuts'] = dict.fromkeys(targets, mode)
        revised.append(row)
    return revised


B22_CHANGES = {
    'head-frame': {
        'text': '머리 프레임 09를 정면으로 두고 두 베어링 사이로 위에서 수직으로 내립니다.',
    },
    'blink-lid-links': {
        'text': '양쪽 짧은 링크 23을 앞쪽 아래에서 비스듬히 올려 크랭크와 핀 구멍을 맞춥니다.',
        'place': (['Part057'], (0., -10.6, -10.6)),
        'place2': (['Part060'], (0., -10.6, -10.6)),
    },
}


def b22_plan():
    plan = []
    for row in b21_plan():
        if row['id'] == 'jaw-body':
            plan.extend((
                step('jaw-stay-bench', 'jawstay', '오른쪽 턱 베어링 받침 37을 작업대에 둡니다.',
                     place=(['Jaw_37_right_jaw_bearing_stay'], (0, 0, 0))),
                step('jaw-bearing-fit', 'jawstay',
                     '받침 바깥쪽에서 MR104를 곧게 넣고 외륜만 눌러 안쪽 단턱까지 앉힙니다. 고정제는 외륜과 받침 사이에만 바릅니다.',
                     place=(['Jaw_MR104ZZ_jaw_right'], (24, 0, 0))),
                step('jaw-body', 'jaw',
                     '베어링을 넣은 오른쪽 받침 37을 뒤쪽 위에서 비스듬히 내려 맞춥니다.',
                     merge=('jawstay', (0, 12, 12))),
            ))
            continue
        plan.append(dict(row, **B22_CHANGES.get(row['id'], {})))
        if row['id'] == 'neck-dowels':
            plan.extend((
                step('pitch-stop-link', 'neck',
                     '목을 정면에 두고 뒤에서 강철판을 넣어 원형 구멍은 아래쪽, 긴 구멍은 위쪽에 맞춥니다.',
                     place=(['PitchLimitLink'], (0, 30, 0))),
                step('pitch-stop-pins', 'neck',
                     '프레임 안쪽에서 바깥쪽으로 Ø4×20 평행핀 두 개를 넣고 뒤에서 M3 무두나사를 조입니다. 전원을 끈 채 목을 움직여 양 끝에서 핀이 슬롯 끝에 먼저 닿는지 확인합니다.',
                     pins=(['PitchLimitLowerPin'], (27, 0, 0)),
                     pins2=(['PitchLimitUpperPin'], (27, 0, 0)),
                     bolts=['PitchLimitLowerRetainer', 'PitchLimitUpperRetainer']),
            ))
    return plan


PLANS = {'b19': B19_PLAN, 'b20': PLAN, 'b21': b21_plan(), 'b22': b22_plan(), 'b23': b22_plan(), 'b24': b22_plan(), 'b25': b22_plan()}
B22_INTEGRAL_PRINTS = {
    'front-skull-with-nasal-tray': frozenset(('Part073', 'Part065')),
    'jaw-with-hinge-arms': frozenset(('Jaw_30_moving_jaw', 'Jaw_38_left_jaw_drive_arm', 'Jaw_39_right_jaw_pivot_arm')),
}
B22_CAMERA_PATH_CHECKS = {
    'camera-pcb-fit': ('camera_pcb_clearance', (.20, .20, 0.)),
    'camera-bezel': ('bezel_insertion_clearance', (.30,)*6),
}


def assembly_plan(revision, layout=None):
    plan = PLANS[revision]
    if revision in ('b23', 'b24', 'b25') and (not layout or not layout['motion_geometry'].get('camera_cable')):
        raise ValueError('Assembly requires the final camera route and service cover geometry')
    if revision not in ('b22', 'b23', 'b24', 'b25') or not layout or not layout['motion_geometry'].get('camera_cable'):
        return plan
    geometry = layout['motion_geometry']
    plug_feed = geometry['camera_cable'].get('plug_feed', {})
    pcb_mount = geometry.get('camera_pcb_mount', {})
    changes = {
        'rear-guide': 'OpenRB USB와 전원선 꼬리를 뒤로 빼고, 열린 가이드 40을 받침 뒤에서 밀어 넣습니다. 카메라 선은 이미 오른쪽 통로에 있습니다.',
        'rear-cover': 'OpenRB USB와 전원선을 기존 가이드 홈에 놓고 타이를 건 뒤 덮개 42를 닫습니다.',
        'camera': '브래킷의 타이 자리에 폭 2.5 mm 케이블 타이를 먼저 끼워 둡니다. 앞 외장에 카메라를 넣기 전에 작은 플러그를 연결합니다. 받침을 작업대 가까이에 두고 바깥쪽 USB-A에서 여분을 풀어 둔 채 카메라와 브래킷을 뒤 위에서 내려 넣습니다.',
    }
    after = {
        'base-cup': step('camera-base-feed', 'base',
                         '받침이 열린 상태에서 작은 카메라 플러그를 뒤 오른쪽 통로의 낮은 쪽으로 수평으로 넣습니다. 긴 변을 가로로 두고, 받침 위에서 플러그를 받아 안쪽에 둡니다. 큰 USB-A는 밖에 둡니다.',
                         camera_feed=plug_feed.get('base', {'start_mm': [55., 100., -68.5],
                                                            'end_mm': [55., 55., -68.5],
                                                            'body_mm': [7.7, 5.2, 4.5], 'cross_tolerance_mm': .2})),
        'rotor-studs': step('camera-rotor-feed', 'rotor',
                            '회전판을 베어링에 내리기 전에 작은 플러그를 회전판 앞쪽 구멍 아래에서 위로 뺍니다. 선 외피를 열린 곡면에 얹어 손으로 부드럽게 미끄러지는지 확인합니다.',
                            camera_feed=plug_feed.get('rotor', {'start_mm': [0., -36.3, -57.],
                                                               'end_mm': [0., -36.3, -24.],
                                                               'body_mm': [7.7, 4.5, 5.2], 'cross_tolerance_mm': .2})),
        'camera': step('camera-nose-guide', 'front',
                       '카메라를 자리에 댄 뒤 외피를 브래킷 위로 열린 홈에 얹습니다. 외피가 원래 모양을 유지하도록 미리 끼운 타이로 가볍게 잡습니다. 나머지 선은 목 쪽으로 내려 둡니다.'),
        'mast-nuts': step('camera-route-set', 'base',
                          '머리 뒷덮개를 닫기 전에 카메라 선을 배선도대로 놓습니다. 회전판 가이드에서는 외피가 양 끝 사이 약 51 mm 자유롭게 미끄러지게 하고, 남는 길이는 가림막 밖에서 정리합니다. 가림막 뒤 판을 조립할 때 카메라 외피만 오른쪽 분할 홈에 얹습니다. 출구 아래 바깥 면에 접착식 타이 마운트를 붙이고, USB-A 몸체 바로 앞의 외피를 재사용 타이로 받칩니다.',
                          camera_tail_mount={'seat_mm': [56.5, 150., -69.5], 'body_mm': [14., 3., 14.],
                                             'jacket_grip_y_mm': [152.5, 155.5]}),
    }
    camera_bench = []
    if pcb_mount.get('insertion_offsets_mm'):
        sides = ('Left', 'Right')
        washers, nuts, screws = ([f'CameraPCB{kind}{side}' for side in sides]
                                 for kind in ('Washer', 'Nut', 'Screw'))
        camera_bench = [
            step('camera-bracket-bench', 'camerabench',
                 '작업대에 코 카메라 브래킷 26을 놓습니다. 아래가 열린 타이 홈에 폭 2.5 mm 타이를 걸어 둡니다.',
                 place=(['Part066'], (0, 0, 0))),
            step('camera-pcb-fit', 'camerabench',
                 '렌즈를 단 카메라를 약 9 mm 들어 렌즈를 타원형 구멍 윗부분에 넣습니다. 기판을 아래로 내린 뒤 앞쪽으로 가볍게 눌러 자리에 맞춥니다.',
                 path=(['Part067', 'Part068'], pcb_mount['insertion_offsets_mm'])),
            step('camera-pcb-washers', 'camerabench',
                 '윗쪽 두 구멍의 브래킷 앞면에 M3 평와셔를 한 개씩 댑니다.',
                 nuts=(washers, (0, -15, 0))),
            step('camera-pcb-screws', 'camerabench',
                 '앞에서 4 mm 소켓으로 M2 너트를 잡고 뒤에서 1.5 mm 육각렌치로 M2×8 두 개를 조입니다.',
                 nuts=(nuts, (0, -15, 0)), bolts=screws,
                 hold_nuts={name: ('socket',) for name in nuts},
                 paired_drivers=list(zip(nuts, screws))),
        ]
        changes['camera'] = '카메라를 앞 외장에 넣기 전에 작은 플러그를 연결합니다. 받침을 가까이 두고 USB-A 쪽 여분을 풀어 둔 채 카메라 모듈을 뒤 위에서 비스듬히 내려 코받침에 댑니다.'
    result = []
    for row in plan:
        stage = row['id']
        if stage in ('lid-left', 'lid-right') and camera_bench:
            frame, lid = row['place'][0]
            side = '왼쪽' if stage == 'lid-left' else '오른쪽'
            result.append(dict(row, text=f'작업대에 {side} 눈틀을 놓습니다. 눈꺼풀을 열린 자세 그대로 뒤에서 곧게 밀어 넣습니다.',
                               place=([frame], (0, 0, 0)), place2=([lid], (0, 60, 0))))
        elif stage == 'jaw-body-arm' and camera_bench:
            result.append(dict(row, text='턱 30과 구동팔 38, 힌지팔 39를 한 몸으로 출력한 부품을 작업대에 놓습니다.',
                               integral_print='jaw-with-hinge-arms'))
        elif stage == 'front-skull' and camera_bench:
            result.append(step(stage, 'front', '코받침 25가 붙어서 출력된 앞 외장 28을 작업대에 놓습니다.',
                               place=(['Part073', 'Part065'], (0, 0, 0)), integral_print='front-skull-with-nasal-tray'))
            result.append(step('camera-bezel', 'front',
                               '코 테두리 33을 앞쪽 아래에서 대고 오른쪽 위로 비켜 넣습니다. 안쪽 턱을 지난 뒤 가운데로 밀어 맞춥니다. 접합부에 에폭시를 소량 바르고 테이프로 자리를 잡아 굳힙니다.',
                               path=(['Part080'], [(-2., -25., -4.25), (-2., -8., -4.25),
                                                  (1.5, -4.5, -.75), (2.5, -3., .75), (2.5, -1., .75),
                                                  (1.75, -.25, .5), (0., 0., 0.)])))
        elif stage == 'camera' and camera_bench:
            result.extend(camera_bench)
            result.append(step('camera', 'front', changes[stage], merge=('camerabench', (0, 66, 45))))
            result.append(step('camera-tray-bolts', 'front',
                               '위에서 2.5 mm 육각렌치로 M3×8 두 개를 코받침 25의 탭 구멍에 조입니다.',
                               bolts=['CameraTrayScrewLeft', 'CameraTrayScrewRight']))
        else:
            result.append(dict(row, text=changes.get(stage, row['text'])))
        if stage in after:
            result.append(after[stage])
    if revision == 'b22':
        return result
    service = b23_service_plan(result, layout)
    if revision == 'b23':
        return service
    current = b24_plan(service, layout)
    return b25_plan(current, geometry) if revision == 'b25' else current


def b23_service_plan(plan, layout):
    from check_b23_service import service_metadata

    rear, bottom = service_metadata(layout)
    yaw_shim = layout['motion_geometry'].get('yaw_inner_race_shim')
    yaw_limit = layout['motion_geometry'].get('yaw_limit', {})
    eye_rephase = layout['motion_geometry'].get('eye_pitch', {}).get('phase_deg')
    rear_nuts = g('cableNut', 5)
    # The tightened plain M3 nut is 2.4 mm tall against the −62 mm cover face.
    paused = {name: (0., 0., round(rear['parked_bottom_z_mm'] + 64.4, 3)) for name in rear_nuts}
    result = []
    for row in plan:
        sid = row['id']
        if sid == 'rear-cover':
            result.append(step('rear-cover-service-nuts', 'base',
                               '일반 M3 육각너트 다섯 개를 가이드 뒤 창으로 하나씩 수평으로 넣고 아래 받침 홈에 놓습니다.',
                               path=(rear_nuts, [(0, 24, 3.55), (0, 0, 3.55), (0, 0, 0)]),
                               actor_offsets=paused))
            row = dict(row, actor_offsets=paused)
        elif sid == 'rear-cover-bolts':
            row = step(sid, 'base',
                       '위에서 M3×16 다섯 개를 손으로 먼저 걸어 너트를 올립니다. 뒤에서 5.5 mm 오픈 스패너로 잡고 위에서 2.5 mm 육각렌치로 조입니다. 스패너 머리는 폭 13 mm, 두께 4.2 mm 이하여야 합니다.',
                       bolts=row['bolts'])
        elif sid == 'hatch-bolts':
            row = step(sid, 'base', '받침 밑에서 2.5 mm 육각렌치로 M3×8 네 개를 조입니다. 안쪽 너트는 고정판이 잡아줍니다.',
                       bolts=row['bolts'])
        elif sid == 'yaw-side-screws' and yaw_shim:
            row = dict(row, text='위쪽의 M2.5×8 네 개를 손으로 걸어 둡니다. 회전판을 올려 높이를 맞출 때까지 모터가 아래위로 조금 움직여야 합니다.')
        elif sid == 'bearing-seat-bolts' and yaw_limit.get('pad_actors'):
            row = dict(row, text='바닥에서 M3×16 세 개를 넣고 위에서 5.5 mm 소켓으로 너트를 잡습니다. 양옆의 정지 블록을 바깥쪽과 앞쪽으로 가볍게 붙여 둔 상태로 조입니다.')
        elif sid == 'eye-pitch-horn' and eye_rephase is not None:
            row = dict(row, text='눈 상하 모터 혼에 17번을 장착합니다. 출력 혼의 표시와 구멍 두 개를 맞추고 M2×5 두 개를 조입니다.')
        elif sid == 'camera-route-set':
            row = dict(row, text='머리 뒷덮개를 닫기 전에 카메라 선을 배선도대로 놓습니다. 회전판 가이드 안에서 외피가 약 51 mm 움직일 수 있게 둡니다. USB-A 바로 앞 외피를 받침 뒤 고정 지지대의 타이로 잡고 여분은 바깥에서 정리합니다.')
        result.append(row)
        if sid == 'bearing-seat' and (pads := yaw_limit.get('pad_actors')):
            result.append(step('yaw-stop-pads', 'base',
                               '베어링이 들어간 받침에 좌우 정지 블록을 위에서 한 개씩 내려 놓습니다. 각 블록의 돌기를 받침 홈에 맞추고 다음 단계의 기존 M3 나사와 너트로 고정합니다.',
                               place=(pads, yaw_limit['pad_insert_offset_mm'])))
        if sid == 'bearing-seat-bolts' and yaw_shim:
            result.append(step('yaw-inner-shim', 'base', '베어링 내륜 위에 두께 0.1 mm PET 링을 평평하게 놓습니다.',
                               place=([yaw_shim['actor']], yaw_shim['shim_insert_offset_mm'])))
        if sid == 'rotor-horn' and yaw_shim:
            result.append(step('yaw-side-tighten', 'base',
                               '회전판을 손으로 눌러 PET 링에 앉힌 뒤 긴 2 mm 볼 육각렌치를 받침 옆 구멍에 넣어 ID4 나사 네 개를 조입니다. 앞쪽 구멍은 곧게, 뒤쪽은 앞쪽으로 약 10° 기울입니다. 회전판이 가볍게 도는지 확인합니다.',
                               yaw_driver_adjustment=True))
        if sid == 'camera-base-feed':
            result.append(step('hatch-service-nuts', 'base', '바닥 덮개용 M3 육각너트 네 개를 받침 위에서 육각 자리에 넣습니다.',
                               nuts=(g('hatchNut', 4), (0, 0, 17))))
            result.append(step('hatch-service-keepers', 'base',
                               'Ø2.5 mm 파일럿 두 곳에 M3 탭을 냅니다. 왼쪽과 오른쪽 너트 고정판을 위에서 내려 놓고 M3×8 한 개씩으로 고정합니다.',
                               place=([cap['keeper'] for cap in bottom], (0, 0, 17)),
                               bolts=[cap['screw'] for cap in bottom]))
    return result


def b24_plan(plan, layout):
    geometry = layout['motion_geometry']
    coupler = geometry.get('pitch_coupler')
    if coupler:
        result = []
        for stage in plan:
            if stage['id'] != 'neck-dowels':
                result.append(stage)
                continue
            result.append(dict(stage, text='양쪽 프레임 허브에 Ø3×12 핀을 넣어 바깥으로 튀어나오지 않게 약 0.4 mm씩 안에 둡니다. 움직임을 확인한 뒤 핀은 함께 회전하는 허브에만 고정합니다.'))
            result.append(step('pitch-drive-lock', 'neck',
                               '오른쪽 목 축의 M3 탭과 클램프 위의 구멍을 맞춥니다. 위에서 일반 M3×8 한 개를 넣고 2.5 mm 육각렌치로 조입니다. 나사와 축은 접착 없이 분리할 수 있게 둡니다.',
                               bolts=[coupler['actor']]))
    else:
        result = plan
    if geometry.get('eye_pitch_bearings'):
        from b24_eye_bearing_assembly import plan as eye_plan

        return eye_plan(result, layout)
    return result


def b25_plan(plan, geometry):
    rear = geometry['rear_skull_retention']['stations']
    labels = {
        'eye-yaw-motor-bench': (
            '작업대에서 ID1 XL330-M077-T를 모터판 39에 맞춥니다. '
            '동봉 PHS M2×8 TAP은 eyeYawHead0·eyeYawHead2·eyeYawHead3, '
            'PHS M2×6 TAP은 eyeYawHead1에 씁니다.'
        ),
        'eye-pitch-motor-bench': (
            '작업대에서 ID2 XL330-M077-T를 모터판 42에 맞춥니다. '
            'eyePitchHead0~eyePitchHead3에 동봉 PHS M2×8 TAP 네 개를 씁니다.'
        ),
        'blink-motor-bench': (
            '작업대에서 ID3 XL330-M077-T를 모터판 46에 맞춥니다. '
            '동봉 PHS M2×8 TAP은 blinkMotorHead1·blinkMotorHead3, '
            'PHS M2×6 TAP은 blinkMotorHead0·blinkMotorHead2에 씁니다.'
        ),
        'jaw-motor-bench': (
            '작업대에서 ID6 XL330-M288-T를 턱 받침 36에 맞춥니다. '
            '동봉 PHS M2×8 TAP은 jawMotorHead1·jawMotorHead2, '
            'PHS M2×6 TAP은 jawMotorHead0·jawMotorHead3에 씁니다.'
        ),
        'c3-board': 'RF 실험 참고용입니다. B25 조립에서는 C3 보드와 왼쪽 캐리어 관련 단계를 건너뜁니다.',
    }
    result = []
    for row in plan:
        if row['id'] in labels:
            row = dict(row, text=labels[row['id']])
        elif row['id'].startswith('c3-'):
            row = dict(row, text=f"RF 실험 참고 · {row['text']}")
        if row['id'] == 'rear-skull':
            result.append(step('rear-skull-nuts', 'base',
                               '뒤 외장을 끼우기 전에 프레임 양쪽 열린 슬롯으로 M3 육각너트를 넣습니다.',
                               place=([rear['left']['nut'], rear['right']['nut']], (0., 35., 0.))))
        result.append(row)
        if row['id'] == 'rear-skull':
            left = rear['left']['length_mm']
            right = rear['right']['length_mm']
            result.append(step('rear-skull-lock', 'base',
                               f'왼쪽 M3×{left:g}, 오른쪽 M3×{right:g} 원통머리 나사를 밖에서 넣고 2.5 mm 육각렌치로 조입니다.',
                               place=([rear['left']['screw']], (-28., 0., 0.)),
                               place2=([rear['right']['screw']], (28., 0., 0.))))
    return result


def plan_hash(plan):
    return sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def zero_offset_print_issues(stage, printed):
    issues = []
    for role in ('place', 'place2'):
        if role not in stage:
            continue
        names, offset = stage[role]
        simultaneous = printed.intersection(names)
        if not any(offset) and len(simultaneous) > 1:
            fused = B22_INTEGRAL_PRINTS.get(stage.get('integral_print'))
            if simultaneous != fused:
                issues.append(f'Separate printed parts require a checked insertion: {", ".join(sorted(simultaneous))}')
    return issues


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
        self.headless = {}
        self.native_hardware = {item['name'] for item in spec if item['name'].startswith(
            ('CameraPCB', 'CameraTrayScrew', 'ServiceHatchNutKeeper', 'PitchDriveScrew'))}
        self.neutral_nuts = {}
        self.layout = None
        self.actor_offsets = {}
        for item in spec:
            shapes = item['shapes']
            if item.get('kind') == 'set_screw':
                ((section, radius, length, start, outward),) = shapes
                if section != 'cyl' or item['key_af_mm'] <= 0:
                    raise ValueError(f'Invalid headless fastener geometry: {item["name"]}')
                axis = np.asarray(outward, float)
                end = np.asarray(start) + axis*length
                self.screws[item['name']] = (2*radius, length, tuple(end), tuple(-axis))
                self.headless[item['name']] = item['key_af_mm']
                continue
            if item.get('kind') in ('pin', 'retainer', 'washer', 'nut'):
                continue
            if shapes[0][0] != 'cyl' or len(shapes) < 2:
                continue
            radius, height, start, axis = shapes[0][1:]
            size = min(HEAD, key=lambda s: abs(HEAD[s][0]-radius))
            seat = np.asarray(start) + np.asarray(axis)*(height+.05)
            self.screws[item['name']] = (size, round(shapes[1][2]+.1, 2), tuple(seat), tuple(axis))
        self.cache = {}

    def reference_nut(self, name):
        return self.neutral_nuts[name] if name in self.neutral_nuts else self.mesh(name)

    def accept_nut(self, name, mesh):
        if name not in self.neutral_nuts:
            self.neutral_nuts[name] = self.mesh(name)
        self.cache[name] = mesh

    def neutral_screw(self, name):
        if name in self.screws:
            return self.screws[name]
        row = self.rows[name]
        if name.startswith('crankBolt'):
            return row['size'], row['length'] - .15, tuple(row['seat'][:2]) + (row['seat'][2] + .15,), tuple(row['axis'])
        if row['type'] == 'head':
            length = XL330_CASE if row['size'] == 2 else 8.
            return row['size'], length, tuple(row['seat']), tuple(row['axis'])
        return row['size'], row['length'], tuple(row['seat']), tuple(row['axis'])

    blink_pose = None

    def blink_transform(self, name):
        if self.blink_pose is None:
            return None
        kind = self.layout['world_motion'].get(name, '')
        if name.startswith(('crankBolt', 'crankNut')):
            kind = 'blink_shaft_crank'
        if not kind.startswith(('blink_', 'lid')):
            return None
        from check_head import pose

        return pose(kind, (0., 0., 0., self.blink_pose, 0.), self.layout)

    def screw(self, name):
        size, length, seat, axis = self.neutral_screw(name)
        motion = self.blink_transform(name)
        if motion is not None:
            seat = tuple(motion[:3, :3] @ np.asarray(seat) + motion[:3, 3])
            axis = tuple(motion[:3, :3] @ np.asarray(axis))
        return size, length, seat, axis

    closed = False
    limit = OVERLAP_LIMIT

    def mesh(self, name):
        mesh = self.mesh_at_seat(name)
        if name not in self.actor_offsets:
            return mesh
        return mesh.copy().apply_translation(self.actor_offsets[name])

    def mesh_at_seat(self, name):
        motion = self.blink_transform(name)
        if motion is not None:
            key = ('blink', self.blink_pose, name)
            if key not in self.cache:
                saved = self.blink_pose
                self.blink_pose = None
                try:
                    self.cache[key] = self.mesh(name).copy().apply_transform(motion)
                finally:
                    self.blink_pose = saved
            return self.cache[key]
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
        if name in self.headless or name in self.native_hardware:
            mesh = tr.load_mesh(self.world/f'{name}.stl')
        elif name in self.screws or (name in self.rows and self.rows[name]['type'] in ('bolt', 'head')):
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
        if not isinstance(mesh, tr.Trimesh) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
            if not name.startswith(FLEXIBLE):
                raise ValueError(f'{name}: missing or invalid assembly mesh')
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


def native_pin_passage(source, cad_sha256, moving, fixed, offset):
    """Prove a round pin's complete straight insertion with a native swept solid."""
    result = {'parts': [moving, fixed], 'offset_mm': list(offset), 'cad_sha256': cad_sha256}
    if sha256(source.read_bytes()).hexdigest() != cad_sha256:
        raise ValueError('Native assembly source differs from the checked world export')
    try:
        import FreeCAD as App
        import Part

        from export_cad import world_shape
    except ImportError:
        return dict(result, status='unknown', reason='FreeCAD native shape kernel unavailable')
    doc = App.openDocument(str(source.resolve()))
    try:
        moving_obj, fixed_obj = (doc.getObject(name) for name in (moving, fixed))
        if any(obj is None or obj.TypeId != 'Part::Feature' for obj in (moving_obj, fixed_obj)):
            return dict(result, status='unknown', reason='both parts must be native solids')
        pin, host = map(world_shape, (moving_obj, fixed_obj))
        if not pin.isValid() or not host.isValid() or not pin.Solids or not host.Solids:
            return dict(result, status='unknown', reason='invalid native solid')
        axis = App.Vector(*offset)
        travel = axis.Length
        if travel <= 0 or np.count_nonzero(offset) != 1:
            return dict(result, status='unknown', reason='pin path must be along one Cartesian axis')
        axis.normalize()
        surfaces = (face.Surface for face in pin.Faces)
        round_faces = [surf for surf in surfaces if surf.__class__.__name__ == 'Cylinder'
                       and abs(surf.Axis.dot(axis)) > 1 - 1e-10]
        if not round_faces:
            return dict(result, status='unknown', reason='missing coaxial cylindrical pin face')
        cyl = max(round_faces, key=lambda surf: surf.Radius)
        bounds = pin.BoundBox
        corners = (App.Vector(bounds.XMin, bounds.YMin, bounds.ZMin),
                   App.Vector(bounds.XMax, bounds.YMax, bounds.ZMax))
        lo, hi = sorted(vertex.dot(axis) for vertex in corners)
        start = cyl.Center + axis * (lo - cyl.Center.dot(axis))
        nominal = Part.makeCylinder(cyl.Radius, hi - lo, start, axis)
        outside = pin.cut(nominal).Volume
        if outside > 1e-7:
            return dict(result, status='unknown', reason='cylinder does not contain the complete pin',
                        material_outside_mm3=outside)
        swept = Part.makeCylinder(cyl.Radius, hi - lo + travel, start, axis)
        volume = swept.common(host).Volume
        gap = swept.distToShape(host)[0]
        return dict(result, status='pass' if volume <= 1e-7 else 'fail',
                    diameter_mm=2*cyl.Radius, pin_length_mm=hi-lo,
                    material_outside_mm3=outside, swept_overlap_mm3=volume, swept_gap_mm=gap)
    finally:
        App.closeDocument(doc.Name)


def camera_tray_head_passage(source, cad_sha256, world, names):
    """Check a spinning M3 socket head at every point from entry to its seating face."""
    if source is None:
        return {name: {'status': 'unknown', 'reason': 'native assembly required'} for name in names}
    if sha256(source.read_bytes()).hexdigest() != cad_sha256:
        raise ValueError('Native assembly source differs from the checked world export')
    try:
        import FreeCAD as App
        import Part

        from export_cad import world_shape
    except ImportError:
        return {name: {'status': 'unknown', 'reason': 'FreeCAD native shape kernel unavailable'} for name in names}
    doc = App.openDocument(str(source.resolve()))
    try:
        bracket = world_shape(doc.Part066)
        result = {}
        for name in names:
            size, length, seat, axis = world.screw(name)
            if size != 3 or tuple(axis) != (0., 0., -1.) or not bracket.isValid():
                result[name] = {'status': 'unknown', 'reason': 'invalid top-down camera bracket screw'}
                continue
            radius, height = HEAD[size]
            swept = Part.makeCylinder(radius, length+3.+height, App.Vector(*seat), App.Vector(0, 0, 1))
            overlap = swept.common(bracket).Volume
            result[name] = {'status': 'pass' if overlap <= 1e-7 else 'fail',
                            'swept_overlap_mm3': overlap, 'head_diameter_mm': 2*radius}
        return result
    finally:
        App.closeDocument(doc.Name)


def jaw_bearing_passage(world, moving, fixed, offset):
    """Bound the entire bearing translation by one swept circumscribed cylinder."""
    result = {'parts': [moving, fixed], 'offset_mm': list(offset)}
    distance, dy, dz = offset
    if distance <= 0 or dy != 0 or dz != 0:
        return dict(result, status='unknown', reason='bearing insertion must run from outside along X')
    bearing, stay = world.mesh(moving), world.mesh(fixed)
    if not bearing.is_volume or not stay.is_volume:
        return dict(result, status='unknown', reason='bearing and stay must be closed solids')
    x0, x1 = bearing.bounds[:, 0]
    y, z = bearing.bounds[:, 1:].mean(axis=0)
    radius = np.linalg.norm(bearing.vertices[:, 1:] - (y, z), axis=1).max()
    sections = 128
    envelope = tr.creation.cylinder(radius=radius / np.cos(np.pi / sections),
                                    height=x1-x0+distance, sections=sections)
    envelope.apply_transform(tr.geometry.align_vectors((0, 0, 1), (1, 0, 0)))
    envelope.apply_translation(((x0+x1+distance)/2, y, z))
    swept, host, moving_body = map(solid, (envelope, stay, bearing))
    if any(body.is_empty() for body in (swept, host, moving_body)):
        return dict(result, status='unknown', reason='unusable solid mesh')
    outside = (moving_body - swept).volume()
    overlap = (swept ^ host).volume()
    if outside > 1e-7:
        return dict(result, status='unknown', reason='envelope does not cover the full bearing',
                    material_outside_mm3=outside)
    return dict(result, status='pass' if overlap <= 1e-7 else 'fail',
                measured_diameter_mm=float(2*radius), swept_overlap_mm3=overlap,
                material_outside_mm3=outside)


def camera_feed_segment(world, fixed, start, end, body, reserve):
    travel = abs(end-start)
    if np.count_nonzero(travel) != 1 or np.any(body <= 0) or reserve < 0:
        raise ValueError('Invalid straight camera connector feed')
    swept = tr.creation.box(body + travel + 2*reserve*(travel == 0))
    swept.apply_translation((start+end)/2)
    probe = fcl.CollisionObject(mesh_to_BVH(swept))
    request = fcl.DistanceRequest()
    gap, closest = float('inf'), None
    for name in fixed:
        other = world.mesh(name)
        lo, hi = other.bounds
        box_gap = np.linalg.norm(np.maximum(np.maximum(swept.bounds[0]-hi, lo-swept.bounds[1]), 0.))
        if box_gap > gap:
            continue
        if box_gap == 0. and np.any(np.all((other.vertices > swept.bounds[0]) &
                                          (other.vertices < swept.bounds[1]), axis=1)):
            gap, closest = 0., name
            break
        obstacle = fcl.CollisionObject(mesh_to_BVH(other))
        distance = fcl.distance(probe, obstacle, request, fcl.DistanceResult())
        if distance < gap:
            gap, closest = distance, name
    return gap, closest


def camera_feed_passage(world, fixed, feed):
    start, end, body = (np.asarray(feed[key], float) for key in ('start_mm', 'end_mm', 'body_mm'))
    reserve = float(feed['cross_tolerance_mm'])
    gap, closest = camera_feed_segment(world, fixed, start, end, body, reserve)
    if 'pull_end_mm' in feed:
        pull_end = np.asarray(feed['pull_end_mm'], float)
        pull_gap, pull_closest = camera_feed_segment(world, fixed, end, pull_end, body, reserve)
        if pull_gap < gap:
            gap, closest = pull_gap, pull_closest
    status = 'pass' if closest is not None and np.isfinite(gap) and gap > 0 else 'fail'
    return dict(feed, status=status, minimum_clearance_mm=float(gap) if np.isfinite(gap) else None,
                closest_part=closest)


def sweep_shifted(world, moving, fixed, shift, base):
    """Sweep parts that sit at `base` (relative to their CAD place) by `shift` back toward `base`."""
    saved = {}
    for a in moving:
        saved[a] = world.cache.get(a)
        world.cache[a] = world.mesh_at_seat(a).copy().apply_translation(base)
    try:
        return sweep(world, moving, fixed, shift)
    finally:
        for a in moving:
            if saved[a] is None:
                world.cache.pop(a, None)
            else:
                world.cache[a] = saved[a]


def closed_clearance_mesh(world, name):
    mesh = world.mesh(name)
    if mesh.is_volume:
        return mesh
    if name == 'Part073':
        key = ('closed_clearance', name)
        if key not in world.cache:
            pieces = sorted(mesh.split(only_watertight=False), key=lambda part: len(part.faces), reverse=True)
            if pieces and pieces[0].is_volume and all(
                    len(part.faces) == 2 and part.volume == 0. and part.area == 0. for part in pieces[1:]):
                world.cache[key] = pieces[0]
            else:
                raise ValueError(f'{name}: skull contains components with unresolved material')
        return world.cache[key]
    raise ValueError(f'{name}: clearance requires a closed, oriented mesh')


def travel_clearance(world, moving, fixed, start, end, *, starts_outside, sample_mm=PATH_SAMPLE_MM):
    """Lower-bound clearance between separated meshes along a straight translation."""
    length = np.linalg.norm(np.subtract(end, start))
    count = max(1, int(np.ceil(length / sample_mm)))
    positions = np.linspace(start, end, count + 1)
    request = fcl.DistanceRequest()
    nearest = np.inf
    nearest_pair = None
    nearest_position = None
    for a in moving:
        ma = closed_clearance_mesh(world, a)
        oa = fcl.CollisionObject(mesh_to_BVH(ma))
        lows, highs = ma.bounds[:, None, :] + positions
        for b in fixed:
            mb = closed_clearance_mesh(world, b)
            # Positive separation at the start rules out containment that surface tests miss.
            bounds_distances = np.linalg.norm(np.maximum(np.maximum(
                mb.bounds[0] - highs, lows - mb.bounds[1]), 0), axis=1)
            if starts_outside and bounds_distances[0] <= 0:
                raise ValueError(f'{a} and {b}: clearance travel must begin outside the assembly')
            ob = fcl.CollisionObject(mesh_to_BVH(mb))
            for position, bounds_gap in zip(positions, bounds_distances):
                if bounds_gap >= nearest:
                    continue
                oa.setTransform(fcl.Transform(position))
                distance = fcl.distance(oa, ob, request, fcl.DistanceResult())
                if not np.isfinite(distance):
                    raise ValueError(f'{a} and {b}: invalid clearance result')
                if distance < nearest:
                    nearest, nearest_pair, nearest_position = max(0., distance), [a, b], position
    if nearest_pair is None:
        raise ValueError('Clearance travel requires both moving and fixed geometry')
    # Every unsampled position differs from a sampled position by at most half a step.
    lower_bound = max(0., nearest - length / (2 * count))
    return nearest, lower_bound, nearest_pair, nearest_position.round(3).tolist()


def key_access(world, name, installed, radii=KEY_RADIUS):
    size, _, seat, axis = world.screw(name)
    axis = np.asarray(axis, float)
    headless = world.headless.get(name)
    top = np.asarray(seat) - axis*(0 if headless else HEAD[size][1])
    radius = headless/np.sqrt(3) + .02 if headless else radii[size]
    probe = cylinder(radius, 2., top - axis*2.05, -axis)
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


def find_clear(world, parts, rigid, offset, *, strict=False):
    """Try the stated approach first, then axis and diagonal directions."""
    hits = sweep(world, parts, rigid, offset)
    if not hits:
        return None, {}
    if strict:
        return False, hits
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


def blink_access_cases(world, step, obstacles):
    results = []
    nominal = world.blink_pose
    try:
        for angle in step['blink_access_checks_deg']:
            world.blink_pose = angle
            seated = list(obstacles)
            issues = []
            for key in ('pins', 'pins2'):
                pins, offset = step[key]
                issues.extend(sweep(world, pins, seated, offset))
                seated.extend(pins)
            for screw in step['bolts']:
                size, length, _, axis = world.screw(screw)
                issues.extend(sweep(world, [screw], seated, -np.asarray(axis)*(length+3.)))
                seated.append(screw)
                reach, blocker = key_access(world, screw, seated)
                if reach < KEY_WARN:
                    issues.append((screw, blocker))
            results.append({'blink_deg': angle, 'status': 'fail' if issues else 'pass', 'blocking_pairs': issues})
    finally:
        world.blink_pose = nominal
    return results


def run(cad, hardware, spec, revision='b19', source=None, hatch_paths=None):
    world = World(cad, hardware, spec)
    cad_sha256 = None
    release_geometry = revision in ('b22', 'b23', 'b24', 'b25')
    strict_approach = revision in ('b23', 'b24', 'b25')
    qualified_tools = revision in ('b21', 'b22', 'b23', 'b24', 'b25')
    if revision in ('b20', 'b21', 'b22', 'b23', 'b24', 'b25'):
        world.layout = json.loads((cad/'cad_parts.json').read_text())
        cad_sha256 = world.layout['source_sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', cad_sha256):
            raise ValueError('Invalid exported CAD source hash')
    plan = assembly_plan(revision, world.layout)
    populated_camera = bool(world.layout and world.layout['motion_geometry'].get('camera_pcb_mount', {})
                            .get('insertion_offsets_mm'))
    printed = {part['name'] for part in world.layout['parts'] if part.get('printed')} if populated_camera else set()
    pitch_pin_axes = {item['name']: np.asarray(item['shapes'][0][4], float)
                      for item in spec if item.get('kind') == 'pin' and item['name'].startswith('PitchLimit')}
    if qualified_tools:
        from check_b21_tools import ToolCheck

        tools = ToolCheck(world, hardware)
    installed = {}
    nut_entries = {}
    report = []
    for st in plan:
        world.blink_pose = st.get('blink_deg')
        world.actor_offsets = st.get('actor_offsets', {})
        if qualified_tools:
            for nut, phase in st.get('set_nut_phases', {}).items():
                tools.require_nut_phase(nut, phase)
        ctx = installed.setdefault(st['ctx'], [])
        world.limit = st.get('limit', OVERLAP_LIMIT)
        rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        fitted_before_step = tuple(rigid)
        issues = zero_offset_print_issues(st, printed)
        notes = []
        approach_notes = issues if release_geometry else notes
        clearance = None
        frame_clearance = None
        pitch_link_clearance = None
        bearing_insertion = None
        camera_path_clearance = None
        lid_clearance = None
        native_pin_checks = []
        tools_checked = {}
        drivers_checked = {}
        paired_checked = {}
        driver_pairs = {}
        front_link_clearance = None
        for key in ('merge', 'merge2'):
            if key in st:
                other, offset = st[key]
                moving = [p for p in installed.pop(other) if not p.startswith(FLEXIBLE)]
                world.closed = st.get('closed_lids', False)
                alternative, hits = find_clear(world, moving, rigid, offset, strict=strict_approach)
                if strict_approach and st['id'] == 'front-shell':
                    supports = ('Part044', 'EyePitchLinkCradlePin')
                    if 'Part073' not in moving or not set(supports) <= set(rigid):
                        raise ValueError('Front skull insertion must include the completed eye link and pin')
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, ['Part073'], supports, offset, (0, 0, 0), starts_outside=False, sample_mm=.10)
                    front_link_clearance = {'parts': pair, 'offset_mm': position, 'sampled_minimum_mm': nearest,
                                            'continuous_lower_bound_mm': lower_bound, 'required_mm': .20}
                    if lower_bound < .20:
                        issues.append('Front skull insertion lacks 0.20 mm clearance past the seated eye link and pin')
                world.closed = False
                if alternative:
                    approach_notes.append(f'{other} assembly: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                    hits = {}
                for (a, b), hit in hits.items():
                    issues.append(f'{a} ↔ {b} while moving in ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
                ctx.extend(moving)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for key in ('place', 'place2', 'pins', 'pins2'):
            if key in st:
                parts, offset = st[key]
                if qualified_tools and key in ('pins', 'pins2'):
                    alternative, hits = False, sweep(world, parts, rigid, offset)
                    if release_geometry and source and st['id'] in ('neck-pins', 'neck-dowels'):
                        for (a, b), mesh_hit in list(hits.items()):
                            proof = native_pin_passage(source, cad_sha256, a, b, offset)
                            native_pin_checks.append(dict(proof, mesh_hit=mesh_hit))
                            if proof['status'] == 'pass':
                                del hits[a, b]
                    if release_geometry and st['id'] == 'pitch-stop-pins':
                        axis = -np.asarray(offset) / np.linalg.norm(offset)
                        for part in parts:
                            if part not in pitch_pin_axes or not np.allclose(axis, pitch_pin_axes[part]):
                                issues.append(f'{part}: documented approach differs from the open end of the pin bore')
                else:
                    alternative, hits = find_clear(world, parts, rigid, offset, strict=strict_approach)
                if alternative:
                    approach_notes.append(f'{", ".join(parts)}: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                elif alternative is False:
                    for (a, b), hit in hits.items():
                        issues.append(f'{a} ↔ {b} while moving in ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
                if release_geometry and st['id'] == 'head-frame' and key == 'place':
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, parts, ['Part011'], offset, (0., 0., 0.), starts_outside=False, sample_mm=.10)
                    frame_clearance = {'parts': pair, 'offset_mm': position, 'sampled_min_mm': round(nearest, 3),
                                       'continuous_lower_bound_mm': round(lower_bound, 3)}
                    if lower_bound <= 0:
                        issues.append('Head frame has no verified continuous clearance past the yoke')
                if release_geometry and st['id'] == 'pitch-stop-link' and key == 'place':
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, parts, ['Part011', 'Part019'], offset, (0., 0., 0.), starts_outside=False, sample_mm=.10)
                    pitch_link_clearance = {'parts': pair, 'offset_mm': position, 'sampled_min_mm': round(nearest, 3),
                                            'continuous_lower_bound_mm': round(lower_bound, 3)}
                    if lower_bound <= 0:
                        issues.append('Pitch limit link has no verified continuous passage between clevises')
                if release_geometry and st['id'] == 'jaw-bearing-fit' and key == 'place':
                    bearing_insertion = jaw_bearing_passage(world, parts[0], rigid[0], offset)
                    if bearing_insertion['status'] != 'pass':
                        issues.append(f'MR104 complete outer insertion: {bearing_insertion["status"]}')
                if st['id'] in ('lid-left', 'lid-right') and key == 'place2':
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, parts, rigid, offset, (0, 0, 0), starts_outside=False, sample_mm=.025)
                    lid_clearance = {'parts': pair, 'offset_mm': position, 'sampled_min_mm': round(nearest, 3),
                                     'continuous_lower_bound_mm': round(lower_bound, 3)}
                    if lower_bound < .20:
                        issues.append(f'{pair[0]} ↔ {pair[1]}: no continuous eyelid insertion clearance')
                ctx.extend(parts)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        if 'path' in st:
            parts, points = st['path']
            for start, end in zip(points, points[1:]):
                shift = np.asarray(start, float) - np.asarray(end, float)
                moving_end = np.asarray(end, float)
                for (a, b), hit in sweep_shifted(world, parts, rigid, shift, moving_end).items():
                    issues.append(f'{a} ↔ {b} on the path segment ending at {tuple(end)} ({hit["overlap_mm3"]} mm³)')
            if revision in ('b20', 'b21', 'b22', 'b23', 'b24', 'b25') and st['id'] == 'eye-tie':
                clearance = {}
                legs = zip(EYE_TIE_TRAVEL_ERRORS_MM.items(), points[:-1], points[1:], strict=True)
                for (leg, error), start, end in legs:
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, parts, rigid, start, end, starts_outside=(leg == 'slide'))
                    clearance[leg] = {
                        'parts': pair,
                        'offset_mm': position,
                        'sampled_min_mm': round(nearest, 3),
                        'continuous_lower_bound_mm': round(lower_bound, 3),
                        'required_transverse_error_per_axis_mm': error,
                    }
                    if lower_bound < np.sqrt(2) * error:
                        issues.append(f'{pair[0]} ↔ {pair[1]}: eye tie {leg} clearance only {lower_bound:.3f} mm; '
                                      f'allow ±{error:g} mm on both transverse axes')
            if st['id'] in B22_CAMERA_PATH_CHECKS:
                field, reserves = B22_CAMERA_PATH_CHECKS[st['id']]
                camera_path_clearance = []
                for start, end, reserve in zip(points[:-1], points[1:], reserves, strict=True):
                    nearest, lower_bound, pair, position = travel_clearance(
                        world, parts, rigid, start, end, starts_outside=False, sample_mm=.02)
                    camera_path_clearance.append({
                        'parts': pair, 'start_mm': start, 'end_mm': end, 'closest_offset_mm': position,
                        'required_clearance_mm': reserve,
                        'sampled_min_mm': round(nearest, 4),
                        'continuous_lower_bound_mm': round(lower_bound, 4),
                    })
                    if lower_bound <= 0 or lower_bound < reserve:
                        issues.append(f'{pair[0]} ↔ {pair[1]}: camera insertion lacks {reserve:g} mm clearance')
            ctx.extend(parts)
            rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for key in ('nuts', 'nuts2'):
            if key in st:
                parts, offset = st[key]
                alternative, hits = find_clear(world, parts, rigid, offset, strict=strict_approach)
                if qualified_tools:
                    for name in parts:
                        nut_entries[name] = (alternative or offset, tuple(rigid))
                if alternative:
                    approach_notes.append(f'{", ".join(parts)}: stated approach {tuple(offset)} is blocked; {alternative} is clear')
                    hits = {}
                for (a, b), hit in hits.items():
                    issues.append(f'{a} ↔ {b} while placing the nut ({hit["at_mm"]} mm, {hit["overlap_mm3"]} mm³)')
                ctx.extend(parts)
                rigid = [p for p in ctx if not p.startswith(FLEXIBLE)]
        for name in st.get('bolts', []):
            size, length, seat, axis = world.screw(name)
            if release_geometry and st['id'] == 'pitch-stop-pins' and not np.allclose(axis, (0., -1., 0.)):
                issues.append(f'{name}: hex-key approach is not the documented rear opening')
            approach = -np.asarray(axis, float)*(length+3.)
            for (a, b), hit in sweep(world, [name], rigid, approach).items():
                issues.append(f'{a} ↔ {b} while driving the screw ({hit["at_mm"]} mm from seated, {hit["overlap_mm3"]} mm³)')
            ctx.append(name)
            rigid.append(name)
            radii = B21_KEY_RADII if qualified_tools else KEY_RADIUS
            reach, blocker = key_access(world, name, rigid, radii)
            if reach < KEY_WARN:
                notes.append(f'{name}: straight key reach {reach} mm (blocked by {blocker})')
            if qualified_tools:
                status = 'pass' if reach >= KEY_WARN else 'unknown'
                drivers_checked[name] = {'status': status, 'straight_key_reach_mm': reach, 'blocker': blocker}
                if status != 'pass':
                    issues.append(f'{name}: driver route unknown')
        if qualified_tools:
            for nut, modes in st.get('hold_nuts', {}).items():
                def rotated_entry(mesh):
                    if nut not in nut_entries:
                        return False
                    offset, obstacles = nut_entries[nut]
                    saved = world.mesh(nut)
                    world.cache[nut] = mesh
                    try:
                        return not sweep(world, [nut], obstacles, offset)
                    finally:
                        world.cache[nut] = saved

                tools_checked[nut] = tools.hold(nut, rigid, modes, rotated_entry, st.get('socket_inset_mm'))
                status = tools_checked[nut]['status']
                if status != 'pass':
                    issues.append(f'{nut}: holding-tool route {status}')
            for first, second in st.get('paired_nuts', ()):
                pair = f'{first}/{second}'
                paired_checked[pair] = tools.hold_together(first, second)
                status = paired_checked[pair]['status']
                if status != 'pass':
                    issues.append(f'{pair}: paired-tool route {status}')
            for nut, bolt in st.get('paired_drivers', ()):
                pair = f'{nut}/{bolt}'
                reach = drivers_checked[bolt]['straight_key_reach_mm']
                if reach < KEY_WARN:
                    driver_pairs[pair] = {'status': 'unknown', 'reason': 'no straight driver reach'}
                else:
                    size, _, seat, axis = world.screw(bolt)
                    axis = np.asarray(axis)
                    tip = np.asarray(seat)-axis*(HEAD[size][1]+.05)
                    driver = cylinder(radii[size], reach, tip, -axis)
                    driver_pairs[pair] = tools.hold_and_drive(nut, driver)
                status = driver_pairs[pair]['status']
                if status != 'pass':
                    issues.append(f'{pair}: holding-tool and key route {status}')
        else:
            for key in ('nuts', 'nuts2'):
                if key in st:
                    for nut in st[key][0]:
                        dirs = spanner_access(world, nut, rigid)
                        if dirs == [] and not socket_open(world, nut, rigid):
                            notes.append(f'{nut}: no open side for a spanner, fingers or a socket; needs a pocket that holds it')
        row = {'id': st['id'], 'context': st['ctx'], 'text': st['text'], 'issues': issues, 'notes': notes}
        if clearance is not None:
            row['insertion_clearance'] = clearance
        if frame_clearance is not None:
            row['head_frame_clearance'] = frame_clearance
        if pitch_link_clearance is not None:
            row['pitch_link_clearance'] = pitch_link_clearance
        if bearing_insertion is not None:
            row['bearing_insertion'] = bearing_insertion
        if camera_path_clearance is not None:
            row[field] = camera_path_clearance
        if lid_clearance is not None:
            row['lid_insertion_clearance'] = lid_clearance
        if world.actor_offsets:
            row['actor_offsets'] = world.actor_offsets
        if front_link_clearance is not None:
            row['front_link_clearance'] = front_link_clearance
        if 'integral_print' in st:
            row['integral_print'] = st['integral_print']
        if native_pin_checks:
            row['native_pin_passages'] = native_pin_checks
        if tools_checked:
            row['tool_access'] = tools_checked
        if drivers_checked:
            row['driver_access'] = drivers_checked
        if paired_checked:
            row['paired_tool_access'] = paired_checked
        if driver_pairs:
            row['paired_driver_access'] = driver_pairs
        if world.blink_pose is not None:
            row['blink_deg'] = world.blink_pose
        if st.get('blink_access_checks_deg'):
            row['blink_access_cases'] = blink_access_cases(world, st, fitted_before_step)
            for case in row['blink_access_cases']:
                if case['status'] != 'pass':
                    issues.append(f'pin or key interference at {case["blink_deg"]:g}° lid position')
        if 'camera_feed' in st:
            camera_feed = camera_feed_passage(world, fitted_before_step, st['camera_feed'])
            row['camera_feed'] = camera_feed
            if camera_feed['status'] != 'pass':
                issues.append(f'Camera connector feed blocked by {camera_feed["closest_part"]}')
        if 'camera_tail_mount' in st:
            row['camera_tail_mount'] = st['camera_tail_mount']
        if st.get('yaw_driver_adjustment'):
            from check_b23_service import yaw_driver_adjustment

            check = yaw_driver_adjustment(source, world)
            row['yaw_driver_adjustment'] = check
            if check['status'] != 'pass':
                issues.append('The four side screws have no verified final driver route')
        if revision in ('b24', 'b25') and st['id'] == 'pitch-horn-bolts' and world.layout['motion_geometry'].get('pitch_coupler'):
            from check_b24_pitch_coupler import oem_head_approaches

            check = oem_head_approaches(source, cad_sha256, world, st['bolts'])
            row['pitch_horn_head_approaches'] = check
            if check['status'] != 'pass':
                issues.append('The stock pitch horn screws have no continuous head or tip clearance')
        if revision in ('b24', 'b25') and st['id'] == 'pitch-drive-lock':
            from check_b24_pitch_coupler import key_approach

            check = key_approach(world, rigid, st['bolts'][0])
            row['pitch_drive_key'] = check
            if check['status'] != 'pass':
                issues.append('The 2.5 mm neck-drive hex key cannot be placed and turned')
        if revision in ('b24', 'b25') and 'eye_bearing_alignment' in st:
            from b24_eye_bearing_assembly import axis_gauge

            check = axis_gauge(world, fitted_before_step, st['eye_bearing_alignment'])
            row['eye_bearing_alignment'] = check
            if check['status'] != 'pass':
                issues.append('The stock alignment rod does not pass through both eye-pitch bearings')
        if st['id'] == 'camera-tray-bolts':
            heads = camera_tray_head_passage(source, cad_sha256, world, st['bolts'])
            row['camera_tray_head_passage'] = heads
            for name, head in heads.items():
                if head['status'] != 'pass':
                    issues.append(f'{name}: continuous socket head passage {head["status"]}')
        report.append(row)
        print(st['id'], 'CLEAR' if not issues else issues, notes if notes else '', flush=True)
    if strict_approach:
        from check_b23_service import check_service

        covers = check_service(source, world, installed['base'], hardware, hatch_paths)
        for row in report:
            if (service := covers.get(row['id'])) is not None:
                tool_access = service.pop('tool_access', None)
                if tool_access:
                    row['tool_access'] = tool_access
                row['service_access'] = service
                if service['status'] != 'pass':
                    contacts = [hit['parts'] for hit in service['cover_collisions']]
                    fasteners = [entry['bolt'] for entry in service['fasteners'] if entry['status'] != 'pass']
                    row['issues'].append(f'Cover service {service["status"]}: {contacts or fasteners or "hatch cable paths"}')
                print(row['id'], 'SERVICE', service['status'].upper(), flush=True)
    if cad_sha256 is not None:
        report[0]['cad_sha256'] = cad_sha256
    if qualified_tools:
        report[0]['plan_sha256'] = plan_hash(plan)
    return report


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('cad', type=Path, help='export_cad.py --world output for the selected revision')
    parser.add_argument('hardware', type=Path, help='steps.js hardware dumped as JSON {"hardware": [...]}')
    parser.add_argument('spec', type=Path, help='hardware-spec.json from build_b19_review_fixes.py')
    parser.add_argument('report', type=Path)
    parser.add_argument('--revision', choices=PLANS, default='b19')
    parser.add_argument('--source', type=Path, help='native assembly for resolving round pin mesh artifacts')
    parser.add_argument('--hatch-paths', type=Path, help='B23 hatch cable centerlines at all six lowering positions')
    args = parser.parse_args()
    data = json.loads(args.hardware.read_text())
    result = run(args.cad, data['hardware'], json.loads(args.spec.read_text()), args.revision, args.source, args.hatch_paths)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    bad = [row['id'] for row in result if row['issues']]
    print(f'{len(result)} steps, {len(bad)} with blocking issues', bad)
    if bad:
        raise SystemExit(1)
