# R5 기구 설계와 조립

[B22 FreeCAD·P2S 출력판과 검사](revisions/b22/) · [B21 FreeCAD·P2S 출력판과 검사](revisions/b21/) · [이전 CAD 개정](revisions/)

## B15 조립

FreeCAD에서 [B15 조립본](R5-B15-Assembly.FCStd)을 엽니다. `revise.py`가 출력을 위한 STL을 생성합니다. 턱의 `Opening`을 0~13°에서 조절할 수 있습니다. [P2S 전체판](R5-B15-P2S.3mf) · [P2S 시험판](R5-B15-Fit-P2S.3mf)

B22 조립 순서와 공구 방향은 [B22 조립 절차서](revisions/b22/assembly.md)에 있습니다. [B21 조립 절차서](ASSEMBLY.md)

## P2S 출력 설정

[B21 출력판과 변경 부품](revisions/b21/#출력과-조립)을 확인합니다. 이 절의 출력 시간과 사용량은 B15 프로젝트 기준입니다.

3MF를 Bambu Studio에서 **프로젝트로 열고**, **P2S 0.4 mm · Textured PEI Plate · Bambu PETG HF**를 확인합니다. 모델 방향, 판 배치, 부품별 서포트가 저장돼 있습니다. 배치를 유지하고 한 장씩 슬라이스합니다. 같은 PETG HF를 서포트에도 사용하며 단일 스풀로 출력할 수 있습니다. [P2S 프린터 프리셋](https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/machine/Bambu%20Lab%20P2S%200.4%20nozzle.json) · [PETG HF 프리셋](https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/Bambu%20PETG%20HF%20%40BBL%20P2S%200.4%20nozzle.json)

기본은 **0.20 mm 레이어, 벽 4줄, 자이로이드 내부 채움 20%**입니다. 노즐은 첫 층 230 °C, 이후 245 °C, 베드는 70 °C입니다. 큰 외장 표면과 첫 층을 위해 외벽 100 mm/s, 첫 층 외곽 35 mm/s, 최대 유량 14 mm³/s로 설정했습니다. 받침과 맞춤 부품의 설정은 아래와 같이 저장했습니다.

| 부품 | 출력 방향과 설정 |
|---|---|
| 1번 받침, 11번 바닥 덮개 | 바닥면을 플레이트에 두고 벽 5줄과 채움 35%. 받침 서포트는 빌드판에서만 세움 |
| 4번 앞 해골, 5번 뒤 해골과 턱 | 저장된 방향을 사용. 앞 해골은 얼굴이 위를 향하고, 외장에는 트리 서포트 적용 |
| 6·7번 목 기둥, 머리 프레임, 요크, 피치 클램프 | 벽 6줄과 채움 35%. 7번 눈꺼풀 레일은 채움 100% |
| 8번 눈꺼풀 축 간격통 | 세로로 놓고 바깥 브림 4 mm 적용 |
| 11번 케이블 트레이 | 트레이 바닥을 플레이트 쪽으로 두고, 빌드판에서만 서포트를 세움 |
| 13번 균형추 트레이 | 균형추를 달 때 사용 |

구매 기준은 **Bambu PETG HF 같은 색 1 kg 두 롤**입니다. Bambu Studio가 산출한 양과 시간에는 브림과 서포트가 포함됩니다.

| 출력 범위 | 필라멘트 | 예상 시간 |
|---|---:|---:|
| 전체판 1–12번 | 약 1.16 kg | 약 60시간 31분 |
| 시험판 1–4번 | 약 229 g | 약 12시간 45분 |
| 선택 13번 균형추 트레이 | 약 34 g | 약 1시간 49분 |

출력 검사는 [층별 출력 경로](#출력-경로-검사), 조립 검사는 [배선과 체결품을 단 상태의 구동 검사](ASSEMBLY.md#배선과-체결품을-단-상태의-구동-검사)에 기록했습니다.

## 기구 검증

| 부위 | 제작 전 확인 |
|---|---|
| 모터 체결부 | 표준 원통머리가 움직이는 부품에 닿는 네 곳에 평평한 홈을 가공. 원통머리 18곳에 지름 0.20 mm와 높이 0.10 mm 여유를 더해 13,420개 조합에서 간섭 0건. 머리 아래 남는 재료 최소 0.85 mm. 실제 모터 나사산과 출력물 강도 확인 후 체결 |
| 눈꺼풀 | 핀 4개, 링크 체결부 6개, 레일 나사 4개의 장착과 회전 여유를 확인. 핀 위치에 축마다 ±0.25 mm 오차를 적용. PETG 탄성계수 1 GPa와 입력 토크 0.04 N·m에서 레일 베어링 자리 최대 변위 0.23 mm |
| 목 | 볼트 머리와 모터 사이 최소 0.70 mm. PETG 탄성계수 1 GPa로 계산한 최대 변위는 모터 브래킷 0.125 mm, 요크 0.069 mm. 각각 약 19 N과 20 N을 가한 계산. MuJoCo에서 균형추 없이 끄덕이는 조건의 최고 요구 토크는 0.100 N·m |
| 케이블 | 뒤쪽 스패너 통로 폭 18 mm. XT30U·XT60U 몸체와 열수축 부위, 허브의 JST 공간, 목 회전판의 Ø9 mm 통로를 검사. PETG 탄성계수 1 GPa에서 10–20 N 하중을 준 트레이 최대 변위 0.061 mm |
| 턱 | 힌지 높이 ±0.4 mm와 영점 ±0.7°를 넣은 180개 자세에서 치아 간격 최소 0.77 mm |
| PCB | C3와 허브는 KiCad STEP의 구멍 6개를 대조. OpenRB는 지지점 4개, USB-C를 꽂은 채 내려가는 경로, 보드 바깥 M3 공구 공간을 검사. 홀 맞춤은 [시험판 4번](R5-B15-Fit-P2S.3mf)에서 확인 |

기구 계산에는 모터 사양 질량을 사용했고 머리의 나사·배선·접착제에 40 g을 잡았습니다.

CAD 조립 80단계의 배치 35,684쌍과 체결 위치 72곳의 공구 경로를 검사했습니다. 기구 구동은 부품·자세 조합 26,408개, 배선을 포함한 구동은 자세 148개를 검사했습니다. 이 검사에서 구동 간섭은 0건이었습니다. 눈꺼풀 크랭크는 바깥 폭 16 mm, 두께 4.2 mm의 스패너로 좌우 15° 경로까지 확인했습니다. [공구가 들어가는 순서](ASSEMBLY.md)

## 케이블 고정

AMASS 두 커넥터에 각 전선의 납땜 컵 간격을 맞춘 둥근 홈을 냈습니다. 아래 표는 B15 시험판 검사용 치수이며 단위는 mm입니다. 구매품 검토 화면은 StarTech 암 커넥터 도면의 몸체 16.0 × 9.1 mm와 Ø4.8 mm 케이블을 사용합니다. 실물 뒤턱과 뒷목은 시험판에서 확인합니다. [품번과 조립 순서](ASSEMBLY.md#배선)

| 위치 | 뒤턱 검사 크기 | 검사한 몸체 폭 × 높이 | 전선 출구 검사 크기 |
|---|---:|---:|---:|
| 5 V XT30U | 9.7 × 5.0 | 10.5 × 5.9 | Ø4.0 × 2 · 홈 Ø4.6, 중심 간격 5.0 |
| 목 전원 XT60U | 14.6 × 7.2 | 16.0 × 8.6 | Ø5.6 × 2 · 홈 Ø6.2, 중심 간격 7.2 |
| 카메라·OpenRB USB-A | 12.4 × 7.0 | 16.2 × 8.3 | 6.4 × 5.2 |

검사용 몸체의 자리 오차를 좌우·상하 ±0.15 mm로 적용했습니다. 이 상태에서 뒤턱을 받치는 면적은 XT30U에서 트레이와 덮개 각각 최소 6.22 mm², XT60U에서는 각각 최소 20.18 mm²입니다.

작업대에서 전원 암수와 덮개까지 조립한 트레이가 받침 뒤에서 26 mm 들어가는 경로를 0.5 mm 간격으로 검사했습니다. 트레이의 좌우·상하 ±0.12 mm 오차와 USB-A 안쪽 끝 17.0 × 9.8 mm를 적용했습니다. 바뀐 케이블·바닥 덮개 조립 10단계에서 배치 3,195쌍을 검사해 간섭 0건이었습니다. [받침과 트레이 조립](ASSEMBLY.md#받침)

덮개를 얹은 뒤 위에서 M3×16을 넣고, 트레이 뒤쪽 열린 공간에서 5.5 mm 스패너로 너트를 잡습니다. [시험판 2번](R5-B15-Fit-P2S.3mf)에서 공구와 실제 커넥터를 맞춥니다. 시임으로 좌우·상하 유격을 편측 약 0.12 mm로 맞추고 커넥터 뒤턱을 밀착시킵니다. 전원을 끄고 케이블을 직선과 45°에서 10 N으로 30초씩 당겨 0.5 mm 이하 이동과 피복 상태를 확인합니다. [허브 극성](../electronics/README.md#전원과-배선)

## 출력 경로 검사

Bambu Studio 2.9.1.70에서 P2S 0.4 mm·PETG HF·0.20 mm로 전체판 13장과 시험판 4장을 슬라이스했습니다. 17장 모두 슬라이스 경고와 고립 압출 시작점이 0건입니다. 아래 기록은 슬라이스와 CAD 기준입니다.

| 출력판 | 확인한 내용 |
|---|---|
| 시험 2 · 케이블 고정 벽 | 닫힌 메시를 사용하며 돌출부 아래에는 일반 서포트 적용. P2S 시험판 4장 모두 슬라이스 경고와 고립 압출 경로 0건 |
| 전체 1 · 받침 | 스패너 입구 사이를 45° 경사로 연결. Z 16.6 mm 오류 위치 두 곳의 새 경로는 서포트 없이 아래층과 각각 약 12 mm² 겹침. P2S 고립 압출 경로 0건 |
| 전체 4 · 앞 해골 | 앞 해골 안쪽 세 구간을 경사로 다듬어 네 곳의 떠 있는 외벽 시작을 없앴습니다. 표면이 닫힌 메시 한 개로 만들고 슬라이스 전체를 검사했습니다. |
| 전체 6 · 목 기둥·머리 프레임 | 목 기둥의 0.35 mm 가장자리와 머리 프레임의 0.10 mm 가장자리가 일부 층에서 빠짐 |
| 전체 7 · 모터 앞판 | 눈·눈꺼풀 모터 앞판 3개의 약 0.10 mm 잔여벽이 출력 경로에서 빠짐 |
| 전체 8 · 목 회전판 | M3 머리가 들어가는 네 자리에 모델 압출이 지나가지 않습니다. 아래 Ø6.1 mm 입구로 서포트를 제거합니다. |
| 전체 8 / 시험 1 · 눈꺼풀 축 | 크랭크 3개와 간격통 2개의 0.30 mm 막을 폭 3.16 mm의 열린 홈으로 바꿨습니다. Ø4 mm 축은 옆으로 빠지지 않으며 끝에서 끼웁니다. |
| 전체 3 / 시험 4 · OpenRB 캐리어 | USB 쪽 가장자리의 약 0.15 mm 잔여벽이 출력 경로에서 빠짐 |

받침 뒤쪽 트레이 체결부 두 곳에 Ø3 mm 검사봉 경로를 막는 압출은 없습니다. 받침의 바닥 덮개 체결부 네 곳과 시험판 2번 시편의 뒤쪽 두 곳은 Ø2 mm 직선 공구로 서포트에 접근할 수 있습니다.

수정한 받침과 목 부품은 각각 솔리드 한 개입니다. 출력용 앞 해골은 하나의 닫힌 메시입니다.

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
fc mechanical/physics/installed_fit.py mechanical/R5-B15-Assembly.FCStd
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
mkdir -p build/p2s-full build/p2s-fit
bambu-studio --slice 0 --outputdir build/p2s-full mechanical/R5-B15-P2S.3mf
bambu-studio --slice 0 --outputdir build/p2s-fit mechanical/R5-B15-Fit-P2S.3mf
python mechanical/physics/slicer_mass.py build/p2s-full/sliced-grams.json build/p2s-full/plate_{4,5,6,7,8,9,10,12,13}.gcode
python mechanical/physics/multibody.py build/physics/cad build/physics/motion --sliced-grams build/p2s-full/sliced-grams.json
python mechanical/physics/blink_fea.py build/physics/cad build/physics/blink-fea.json
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/retainer.py build/physics/cad build/physics/retention.json
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
```
