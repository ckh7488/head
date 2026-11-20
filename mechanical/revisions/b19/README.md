# B19 체결품 정의와 조립 불가 지점 수정

[FreeCAD 조립본](R5-B19-review-fixes.FCStd) · [바뀐 출력물](print/) · [정적 검사](review-fixes-check.json) · [구동 중 체결품](hardware-sweep.json) · [머리 간섭](head-clearance.json) · [단계별 조립](assembly-check.json) · [제자리 겹침](static-pairs.json) · [최신 B20](../b20/)

B19는 B18 조립본에서 시작합니다. 이전 개정까지는 모터를 고정하는 나사, 눈 링크 관절, 목 상하축과 머리 프레임 연결처럼 구멍만 있고 넣을 부품이 정해지지 않은 자리가 많았습니다. 그중 일부는 나사를 넣을 공간 자체가 없었습니다. B19는 이런 자리를 모두 CAD에 넣고 구동 범위 전체에서 다른 부품과 겹치지 않는지 확인했습니다. 이어서 조립 순서대로 부품과 나사를 하나씩 넣어 보며 막히는 곳을 찾았습니다.

## 조립이 안 되던 자리

| 자리 | 문제 | B19 |
|---|---|---|
| 목 상하축 ↔ 머리 프레임 09 | 축이 프레임의 둥근 구멍에서 헛돌아 머리가 끄덕이지 않음. 축이 옆으로 빠지는 것도 막지 못함 | 두 축에 Ø3.0 직교 구멍(바깥 끝에서 5.5 mm), Ø3×12 평행핀. 볼트는 허브 아래 1 mm에 앞 해골이 있어 불가 |
| 눈 좌우 모터판 39 ↔ 크래들 12 | 모터판 다리 아래에서 나사를 넣어야 하는데 그 자리를 XL330이 차지함 | 크래들 위 카운터보어에서 M3×16, 모터판 다리를 Ø2.6 탭 구멍으로 |
| 지지대 34 ↔ 프레임 09 | 너트가 놓일 프레임 반대쪽에서 모터 케이스가 0.8 mm 앞에 있음 | 프레임 구멍을 Ø2.6 탭 구멍으로, M3×8 |
| 목 상하 XL430 ↔ 요크 07 | B17 ID5 가드가 모터 고정 구멍 4곳 중 2곳을 덮음 | 가드에 관통 구멍, 그 두 곳은 M2.5×10 |
| 목 좌우 XL430 ↔ 브래킷 05 | 아래쪽 측면 구멍 4곳은 브래킷 다리 패드가 머리 바로 앞을 막아 나사를 넣을 수 없음 | 위쪽 구멍 4곳만 M2.5×8. 브래킷 다리 나사를 모터보다 먼저 조임 |
| 눈 링크 관절 5곳 | 체결품이 없었고, 크랭크 아래 1.1 mm·링크 바깥 0.3~0.65 mm라 너트 자리가 없음 | 4곳은 Ø2×6 핀을 한쪽에 고정하고 주변 면이 빠짐을 막음. 혼–타이바 1곳은 아래에서 M2×8, 위에 와셔와 너트 |
| 출력 혼 16·17·19, 턱 구동팔 38 | 혼 구멍 4개 중 일부는 나사 머리가 링크·크랭크와 겹침 | 겹치는 구멍은 비움. 16은 3개, 나머지는 2개만 조임 |
| 눈꺼풀 혼 19 ↔ 링크 22, 크랭크 21-2 ↔ 링크 22 | 구동 중 출력물끼리 겹침 | 혼과 크랭크의 닿는 끝을 잘라냄. 눈꺼풀 행정 전체에서 겹침 0 |
| 눈꺼풀 크랭크 3곳 | 나사 머리와 크랭크 사이 0.21 mm라 조금만 어긋나도 축을 못 잡음 | 축 평면 0.30 mm로 0.36 mm 확보 |
| 눈꺼풀 간격통 45 ↔ 가운데 크랭크 21-2 | 크랭크 위쪽 클램프 블록이 축 위로 1.05 mm(왼쪽)·0.8 mm(오른쪽) 튀어나와 두 간격통과 0.6~0.8 mm³ 겹침. 왼쪽 간격통은 끝 1 mm가 베어링 턱 안에 들어가 있어, 크랭크와 링크를 단 뒤에는 넣을 길이 없음 | 간격통을 클램프 블록 0.1 mm 앞에서 끝나게 줄이고, 왼쪽은 베어링 쪽도 1.2 mm 줄임. 크랭크는 축 평면의 M3로 고정되므로 간격통이 축 방향을 잡지 않아도 됨 |
| 카메라 브래킷 26 ↔ U20CAM 기판 | 기판 아래 끝이 브래킷 앞 턱에 1.8 mm 묻혀 있음(114 mm³). 그대로 출력하면 기판이 1.8 mm 높게 앉아 렌즈가 코 구멍 중심에서 벗어남 | 기판이 서는 홈(32.4 × 2.3 × 2.1 mm)을 턱에 팜 |
| 눈 타이바 15 ↔ 크래들 12 | 타이바 양끝이 크래들의 ㄷ자 지지대 안에 갇혀 26방향 어디로도 넣을 수 없음. 핀이 타이바 위로 3.25 mm 솟아 있는데 위 여유는 3.55 mm라 핀에 끼운 채로는 옆으로도 못 밂 | 크래들 위 다리에 Ø2.2 구멍 두 개. 타이바를 핀 없이 왼쪽 옆에서 제자리보다 2.5~3 mm 앞 선으로 밀어 넣고, 핀은 나중에 위 구멍으로 밀어 넣음 |
| 턱 30 ↔ 구동팔 38·힌지팔 39 | 턱 안의 팔 자리가 사방으로 막혀 따로 출력한 팔을 끼울 수 없음 | 세 부품을 한 몸으로 출력 |

## 나사 길이

| 자리 | 나사 | 근거 |
|---|---|---|
| XL430 목 좌우 위쪽 4곳, 목 상하 2곳 | M2.5×8 | 벽 4.25~4.3 mm, 케이스 구멍 Ø2.1·깊이 4.0 mm |
| ID5 가드를 지나는 목 상하 2곳 | M2.5×10 | 가드 두께만큼 길게 |
| 브래킷 05 ↔ 받침 01 | M3×8 ×4 | 받침 Ø2.7 탭 구멍 6.6 mm |
| XL330 케이스 | M2×6 ×16 | 판 2.7 mm, 케이스 구멍 10 mm 이상 |
| 출력 혼 16·17 ↔ XL330 혼 | M2×5 ×5 | 혼 구멍 깊이 3.3 mm |
| 출력 혼 19·턱 구동팔 38 ↔ XL330 혼 | M2×6 ×4 | 혼 구멍 깊이 3.3 mm |
| 모터판 42 ↔ 지지대 34, 지지대 34 ↔ 프레임 09 | M3×8 ×4 | Ø2.6~2.7 탭 구멍 |
| 눈 모터판 39 ↔ 크래들 12, 눈 지지대 13 ↔ 프레임 09 | M3×16 ×4 | 카운터보어·프레임 통로 |

M2와 M2.5는 ROBOTIS 모터 쪽 구멍에 맞춘 것입니다. XL430 측면 구멍은 Ø2.1이라 M3를 쓰려면 모터 케이스를 뚫어야 합니다. 출력물끼리의 체결은 모두 M3입니다.

## 빠질 수 있는 핀

헐거운 구멍에 끼우고 양끝을 막는 부품이 없는 핀은 한쪽에만 고정제를 바릅니다. 눈 좌우 Ø2×24는 아래가 비어 있어 중력으로 빠질 수 있으므로 크래들 12 쪽에 바릅니다. 눈 상하 Ø3×13은 바깥 30 mm 안에 막는 부품이 없으므로 지지대 13 쪽에 바릅니다. 턱 Ø4×10은 안쪽으로 5.2 mm 밀리면 힌지팔에서 빠지므로 힌지팔 39 쪽에 바릅니다.

## 다시 출력할 부품

| 부품 | 파일 | 바뀐 곳 |
|---|---|---|
| 09 머리 프레임 | [09_head_frame-B19.stl](print/09_head_frame-B19.stl) | 지지대 34 자리 두 곳을 Ø2.6 탭 구멍으로 |
| 12 눈 크래들 | [12_eye_tilt_cradle-B19.stl](print/12_eye_tilt_cradle-B19.stl) | 모터판 다리 자리 관통과 Ø6.2 카운터보어, 타이바 핀을 넣는 Ø2.2 구멍 두 개 |
| 39 눈 좌우 모터판 | [xl330_eye_yaw_front_plate-B19.stl](print/xl330_eye_yaw_front_plate-B19.stl) | 다리 구멍 Ø3.12 → Ø2.6 탭 |
| ID5 가드 | [ID5-keeper-B19.stl](print/ID5-keeper-B19.stl) | 모터 고정 구멍 위치에 Ø3.0 관통 구멍 두 곳 |
| 19 눈꺼풀 혼 | [19_blink_servo_horn-B19.stl](print/19_blink_servo_horn-B19.stl) | 링크 22와 겹치는 끝을 잘라냄 |
| 21-2 가운데 크랭크 | [21_blink_shaft_crank_2-B19.stl](print/21_blink_shaft_crank_2-B19.stl) | 링크 22와 겹치는 모서리를 잘라냄 |
| 45 간격통 왼쪽·오른쪽 | [왼쪽](print/45_blink_shaft_spacer_left-B19.stl) · [오른쪽](print/45_blink_shaft_spacer_right-B19.stl) | 크랭크 클램프 블록과 베어링 턱을 피하도록 짧게 |
| 26 카메라 브래킷 | [26_u20cam_slotted_bracket-B19.stl](print/26_u20cam_slotted_bracket-B19.stl) | 기판이 서는 홈 |
| 30·38·39 턱 한 몸 | [30_38_39_jaw_one_piece-B19.3mf](print/30_38_39_jaw_one_piece-B19.3mf) | 턱과 두 팔을 합침. 팔이 맞닿기만 하는 이음이 STL에서는 열린 모서리로 읽혀 3MF로 냄 |

## 검사

- 새 체결품과 핀 32개를 구동 자세 전체(목 상하 −15°~+6°, 눈 상하 ±8°, 눈 좌우 ±20°, 눈꺼풀 0~91°, 턱 0~13°)에서 주변 부품과 맞대 봤습니다. 겹침 0건입니다.
- 받침에 고정되는 나사는 목 좌우 ±62°에서 회전부와 최소 3.69 mm 떨어집니다.
- 저장소의 기존 머리 간섭 검사(26,408개 자세)를 B19에서 다시 돌렸습니다. 겹침 0건입니다.
- 조립 순서 122단계를 차례로 확인했습니다. 단계마다 부품·나사·너트·핀을 넣는 길, 육각렌치가 곧게 들어가는 길이, 너트를 잡을 방향을 봤습니다. 막히는 단계는 없습니다.
- 같은 움직임 그룹 안의 부품끼리는 기존 구동 검사가 건너뛰었습니다. B19에서는 모든 부품 쌍의 제자리 겹침을 따로 계산했고, 나사가 탭 구멍에 물리는 자리와 검사용 여유 형상을 빼면 겹침이 없습니다. ROBOTIS 모터와 앞 해골 메시는 닫힌 입체가 아니어서 30쌍은 부피를 잴 수 없었습니다. 모터에 붙는 판·혼·나사, 모터 단자에 꽂힌 하네스, 코 받침 25와 앞 해골 28이 맞닿는 자리입니다.
- B18까지 쓰던 `export_cad.py`는 자체 배치를 가진 메시(턱 기어 등)를 약 2 mm 어긋나게 내보냈습니다. 고친 뒤 턱 기어 사이 최소 거리는 1.14 mm입니다.
- 나사 구멍 깊이와 판 두께는 CAD의 ROBOTIS STEP 형상에서 잰 값입니다. 첫 조립에서 나사 하나씩 물림을 확인합니다.

## 재현

FreeCAD 모듈과 [기구 검사 의존성](../../physics/requirements.txt)이 있는 Python으로 저장소 루트에서 실행합니다. 구동 검사에는 `python-fcl`, `shapely`, `manifold3d`가 더 필요합니다. 조립 검사의 `hardware.json`은 `web/assembly/steps.js`의 단계와 체결품 목록을 JSON으로 저장한 것입니다.

```sh
python mechanical/build_b19_review_fixes.py --output build/R5-B19-review-fixes.FCStd --report build/b19-check.json --stl build/b19-print
python mechanical/physics/export_cad.py --cad build/R5-B19-review-fixes.FCStd --world build/b19-cad
node --input-type=module -e "const m=await import('./web/assembly/steps.js'); process.stdout.write(JSON.stringify({steps:m.steps,hardware:m.hardware}))" > build/hardware.json
cd mechanical/physics
python check_b19_hardware.py ../../build/b19-cad ../../build/b19-print/hardware-spec.json ../../build/b19-sweep.json
python check_head.py ../../build/b19-cad ../../build/b19-clearance.json
python check_b19_assembly.py --revision b19 ../../build/b19-cad ../../build/hardware.json ../../build/b19-print/hardware-spec.json ../../build/b19-assembly.json
python render_b19_assembly.py ../../build/b19-assembly.json ../../build/b19-steps.md
python check_static_pairs.py ../../build/b19-cad ../../build/b19-static.json
cd ../..
python web/b19/build_b19_viewer.py build/b19-cad build/hardware.json mechanical/revisions/b19/print/hardware-spec.json build/b19-assembly.json --revision B19 --output build/b19-viewer
```
