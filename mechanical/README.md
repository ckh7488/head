# B15 기구 조립

FreeCAD에서 [B15 조립본](R5-B15-Assembly.FCStd)을 엽니다. `revise.py`가 출력을 위한 STL을 생성합니다. 턱의 `Opening`을 0~13°에서 조절할 수 있습니다. [P1S 전체 출력판](R5-B15-P1S.3mf) · [시험판](R5-B15-Fit-P1S.3mf)

부품을 넣는 순서와 양쪽 공구가 들어가는 방향은 [조립절차서](ASSEMBLY.md)를 따릅니다.

출력 프로젝트는 P1S 0.4 mm 노즐, PETG HF, 0.20 mm 레이어, 벽 4줄을 사용합니다. 노즐 245 °C, 텍스처 PEI 베드 70 °C, 최대 유량 14 mm³/s를 설정했습니다. 눈꺼풀 레일은 내부 채움 100%입니다. 머리 프레임과 목의 지지 부품은 벽 6줄과 내부 채움 35%로 출력합니다. 13번 균형추 트레이는 선택입니다.

받침과 허브 덮개는 벽 5줄, 내부 채움 35%입니다. 받침의 얕은 아래쪽 홈에 빌드판에서 올라오는 서포트를 쓰고 덮개는 바깥면을 바닥에 놓습니다. 시험판 3번에 같은 설정을 적용했습니다. [바닥 덮개 조립](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#hatch-nuts)

| 부위 | 제작 전 확인 |
|---|---|
| 모터 체결부 | 표준 원통머리가 움직이는 부품에 닿는 네 곳에 평평한 홈을 가공. 원통머리 18곳에 지름 0.20 mm와 높이 0.10 mm 여유를 더해 13,420개 조합에서 간섭 0건. 머리 아래 남는 재료 최소 0.85 mm. 실제 모터 나사산과 출력물 강도 확인 후 체결 |
| 눈꺼풀 | 핀 4개, 링크 체결부 6개, 레일 나사 4개의 장착과 회전 여유를 확인. 핀 위치에 축마다 ±0.25 mm 오차를 적용. PETG 탄성계수 1 GPa와 입력 토크 0.04 N·m에서 레일 베어링 자리 최대 변위 0.23 mm |
| 목 | 끄덕임으로 움직이는 머리 약 623 g, 무게중심은 축 앞쪽 4.2 mm. 목의 좌우 회전부에 걸리는 이동 질량은 약 847 g. 균형추 없이 끄덕이는 모델에서 조립 오차를 포함해 최고 요구 토크 0.100 N·m |
| 케이블 | 뒤쪽 스패너 통로 폭 18 mm. XT30U·XT60U 몸체와 열수축 부위, 허브의 JST 공간, 목 회전판의 Ø9 mm 통로를 검사. PETG 탄성계수 1 GPa에서 10–20 N 하중을 준 트레이 최대 변위 0.061 mm |
| 턱 | 힌지 높이 ±0.4 mm와 영점 ±0.7°를 넣은 180개 자세에서 치아 간격 최소 0.77 mm |
| PCB | C3와 허브는 KiCad STEP의 구멍 6개를 대조. OpenRB는 지지점 4개, USB-C를 꽂은 채 내려가는 경로, 보드 바깥 M3 공구 공간을 검사. 실물 홀은 [시험판 4번](R5-B15-Fit-P1S.3mf)에서 먼저 맞춤 |

출력 무게는 G-code에서 서포트와 브림을 제외해 추정했습니다. 앞뒤 해골과 턱만 약 312 g입니다. 모터 사양 질량을 사용했고 머리의 나사·배선·접착제에 40 g을 잡았습니다.

CAD 조립 78단계의 배치 35,665쌍과 체결 위치 72곳의 공구 경로를 검사했습니다. 이미 체결한 부품과 설치한 커넥터를 포함해 간섭 0건이었습니다. 눈꺼풀 크랭크는 바깥 폭 16 mm, 두께 4.2 mm의 스패너로 좌우 15° 경로까지 확인했습니다. [공구가 들어가는 순서](ASSEMBLY.md)

## 케이블 고정

AMASS 두 커넥터에 각 전선의 납땜 컵 간격을 맞춘 둥근 홈을 냈습니다. 표의 단위는 mm입니다. USB-A는 업체가 표기한 몸체 크기로 검사했으며 실물 뒤턱과 뒷목은 시험판에서 확인합니다. [품번과 조립 순서](ASSEMBLY.md#배선)

| 위치 | 뒤턱 검사 크기 | 검사한 몸체 폭 × 높이 | 전선 출구 검사 크기 |
|---|---:|---:|---:|
| 5 V XT30U | 9.7 × 5.0 | 10.5 × 5.9 | Ø4.0 × 2 · 홈 Ø4.6, 중심 간격 5.0 |
| 목 전원 XT60U | 14.6 × 7.2 | 16.0 × 8.6 | Ø5.6 × 2 · 홈 Ø6.2, 중심 간격 7.2 |
| 카메라·OpenRB USB-A | 12.4 × 7.0 | 16.2 × 8.3 | 6.4 × 5.2 |

검사용 몸체의 자리 오차를 좌우·상하 ±0.15 mm로 적용했습니다. 이 상태에서 뒤턱을 받치는 면적은 XT30U에서 트레이와 덮개 각각 최소 6.22 mm², XT60U에서는 각각 최소 20.18 mm²입니다.

덮개를 얹은 뒤 위에서 M3×16을 넣고, 트레이 뒤쪽 열린 공간에서 5.5 mm 스패너로 너트를 잡습니다. [시험판 2번](R5-B15-Fit-P1S.3mf)에서 공구와 실제 커넥터를 맞춥니다. 시임으로 좌우·상하 유격을 편측 약 0.12 mm로 맞추고 커넥터 뒤턱을 밀착시킵니다. 전원을 끄고 케이블을 직선과 45°에서 10 N으로 30초씩 당겨 0.5 mm 이하 이동과 피복 상태를 확인합니다. [허브 극성](../electronics/README.md#전원과-배선)

## 재현

저장소 루트에서 실행합니다. FreeCAD 1.0과 Python 3.12가 필요하며 Linux에서 Gmsh는 `libGLU`를 사용합니다.

```sh
/usr/bin/python3 -m venv build/freecad-venv
build/freecad-venv/bin/pip install trimesh==4.10.1 manifold3d==3.3.2 'scipy<2'
fc() { QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python "$@"; }
fc mechanical/revise.py
fc mechanical/physics/base_clearance.py --cad build/mechanical/R5-B15-Assembly.FCStd
fc mechanical/physics/cable_assembly.py build/mechanical/R5-B15-Assembly.FCStd
fc mechanical/physics/harness_fit.py build/mechanical/R5-B15-Assembly.FCStd
fc mechanical/physics/service_clearance.py build/mechanical/R5-B15-Assembly.FCStd
kicad-cli pcb export step --board-only --user-origin 65x42mm -o build/mechanical/c3.step electronics/c3-rf/C3_Antenna.kicad_pcb
kicad-cli pcb export step --board-only --user-origin 100x80mm -o build/mechanical/hub.step electronics/servo-hub/R5_Servo_Hub.kicad_pcb
fc mechanical/physics/board_clearance.py build/mechanical/R5-B15-Assembly.FCStd build/mechanical/c3.step build/mechanical/hub.step
fc mechanical/physics/export_cad.py --cad build/mechanical/R5-B15-Assembly.FCStd --world build/physics/cad

python3.12 -m venv build/physics-venv
. build/physics-venv/bin/activate
python -m pip install -r mechanical/physics/requirements.txt
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python web/assembly/export_review.py --cad build/mechanical/R5-B15-Assembly.FCStd
node --input-type=module -e 'import {steps,hardware} from "./web/assembly/steps.js"; process.stdout.write(JSON.stringify({steps,hardware}));' > build/physics/assembly-paths.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python mechanical/physics/assembly_sweeps.py build/mechanical/R5-B15-Assembly.FCStd build/physics/cad/world build/physics/assembly-paths.json build/physics/assembly-audit.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python mechanical/physics/tool_paths.py build/mechanical/R5-B15-Assembly.FCStd build/physics/cad/world build/physics/assembly-paths.json build/physics/tool-audit.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python mechanical/physics/motor_head_fit.py build/physics/cad
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python mechanical/physics/blink_fit.py build/mechanical/R5-B15-Assembly.FCStd build/physics/cad build/physics/blink-fit.json
python mechanical/physics/check_head.py build/physics/cad build/physics/clearance.json
python mechanical/physics/tolerances.py build/physics/cad build/physics/tolerance.json
mkdir -p build/p1s
bambu-studio --slice 0 --outputdir build/p1s mechanical/R5-B15-P1S.3mf
python mechanical/physics/slicer_mass.py build/p1s/sliced-grams.json build/p1s/plate_{4,5,6,7,8,9,10,12,13}.gcode
python mechanical/physics/multibody.py build/physics/cad build/physics/motion --sliced-grams build/p1s/sliced-grams.json
python mechanical/physics/blink_fea.py build/physics/cad build/physics/blink-fea.json
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/retainer.py build/physics/cad build/physics/retention.json
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
```
