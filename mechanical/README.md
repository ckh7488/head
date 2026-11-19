# B8 기구 조립

FreeCAD에서 [B8 조립본](R5-B8-Assembly.FCStd)을 엽니다. `revise.py`가 출력을 위한 STL을 생성합니다. 턱의 `Opening`을 0~13°에서 조절할 수 있습니다. [P1S 전체 출력판](R5-B8-P1S.3mf) · [시험판](R5-B8-Fit-P1S.3mf)

부품을 넣는 방향, 너트를 미리 넣을 자리, 가조립에서 확인할 곳은 [조립절차서](ASSEMBLY.md)를 따릅니다.

출력 프로젝트는 P1S 0.4 mm 노즐, PETG HF, 0.20 mm 레이어, 벽 4줄을 사용합니다. 노즐 245 °C, 텍스처 PEI 베드 70 °C, 최대 유량 14 mm³/s를 설정했습니다. 눈꺼풀 레일은 내부 채움 100%입니다. 머리 프레임과 목의 지지 부품은 벽 6줄과 내부 채움 35%로 출력합니다. 13번 균형추 트레이는 선택입니다.

받침과 허브 덮개는 벽 5줄, 내부 채움 35%입니다. 받침의 얕은 아래쪽 홈에 빌드판에서 올라오는 서포트를 쓰고 덮개는 바깥면을 바닥에 놓습니다. 시험판 3번에 같은 설정을 적용했습니다. [바닥 덮개 조립](https://r5-b1-review.ckh.chatgpt.site/b8/assembly/#hatch-nuts)

| 부위 | 제작 전 확인 |
|---|---|
| 눈꺼풀 | 핀 4개, 링크 체결부 6개, 레일 나사 4개의 장착과 회전 여유를 확인. 핀은 축마다 ±0.25 mm 오차를 포함. 한쪽에만 최대 0.04 N·m 저항을 준 MuJoCo 시험에서 좌우 각도 차 최대 0.43°. 같은 하중의 탄성 해석에서 PETG 레일 변위 최대 0.14 mm, Ø4 강철축 비틀림 최대 0.09° |
| 목 | 끄덕임으로 움직이는 머리 약 629 g, 무게중심은 축 앞쪽 4.2 mm. 목의 좌우 회전부에 걸리는 이동 질량은 약 853 g. 균형추 없이 끄덕이는 모델에서 조립 오차를 포함해 최고 요구 토크 0.101 N·m |
| 케이블 | 마찰 0으로 10 N·30초와 20 N·6초를 가한 24개 접촉 해석에서 커넥터 축방향 이동 최대 0.32 mm. PETG 탄성계수 1 GPa 조건에서 트레이 변형 약 0.05 mm |
| 턱 | 힌지 높이 ±0.4 mm와 영점 ±0.7°를 넣은 180개 자세에서 치아 간격 최소 0.77 mm |
| PCB | KiCad STEP의 나사 구멍 6개가 받침과 일치. C3 USB-C 삽입과 허브 덮개 0~30 mm에서 플러그 간섭 0건 |

출력 무게는 G-code에서 서포트와 브림을 제외해 구했습니다. 앞뒤 해골과 턱만 약 314 g입니다. 모터 사양 질량을 사용했고 머리의 나사·배선·접착제에 40 g을 잡았습니다. 목 받침에 아래로 14 N과 앞뒤로 5 N을 가한 탄성 해석에서 베어링 자리의 최대 변위는 약 0.29 mm였습니다. PETG 탄성계수는 1 GPa로 가정했습니다.

구동 검사는 상부 부품·자세 27,052개 조합과 받침·구동부·체결부 4,984개 고체 쌍을 대상으로 했습니다. 조립 중의 목 체결과 외장 간섭은 [조립절차서](ASSEMBLY.md)에 표시했습니다.

## 케이블 고정

전원 고정부에는 AMASS XT30U와 XT60U를 사용합니다. USB-A는 평평한 뒤턱과 15 mm 이상의 몸체가 있는 연장선을 고릅니다. 18 AWG 전원선 두 가닥은 출구에서 가로로 나란히 놓습니다. 표의 단위는 mm입니다.

| 위치 | 뒤턱 최소 | 몸체 최대 | 고정부를 통과하는 선·목 최대 |
|---|---:|---:|---:|
| 5 V XT30U | 10.0 × 5.0 | 10.45 × 5.45 | 7.0 × 3.2 |
| 목 전원 XT60U | 15.0 × 7.7 | 15.75 × 8.45 | 11.1 × 5.0 |
| 카메라·OpenRB USB-A | 12.4 × 7.0 | 18.5 × 10.3 | 6.4 × 5.2 |

케이블 트레이는 M3×16 두 개와 평와셔·일반 너트로 받침에 고정합니다. 덮개는 트레이 아래 홈에 일반 너트 다섯 개를 미리 넣고 M3×16으로 조입니다. 실제 커넥터에 시임을 대어 좌우·상하 유격을 편측 약 0.12 mm로 맞추고 뒤턱을 받침에 밀착시킵니다. 전원을 끄고 케이블을 직선과 45°에서 10 N으로 30초씩 당겨 0.5 mm 이하 이동과 피복 상태를 확인합니다. [허브 극성](../electronics/README.md#전원과-배선)

## 재현

저장소 루트에서 실행합니다. FreeCAD 1.0과 Python 3.12가 필요하며 Linux에서 Gmsh는 `libGLU`를 사용합니다.

```sh
/usr/bin/python3 -m venv build/freecad-venv
build/freecad-venv/bin/pip install trimesh==4.10.1 manifold3d==3.3.2 'scipy<2'
fc() { QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python "$@"; }
fc mechanical/revise.py
fc mechanical/physics/base_clearance.py --cad build/mechanical/R5-B8-Assembly.FCStd
fc mechanical/physics/service_clearance.py build/mechanical/R5-B8-Assembly.FCStd
kicad-cli pcb export step --board-only --user-origin 65x42mm -o build/mechanical/c3.step electronics/c3-rf/C3_Antenna.kicad_pcb
kicad-cli pcb export step --board-only --user-origin 100x80mm -o build/mechanical/hub.step electronics/servo-hub/R5_Servo_Hub.kicad_pcb
fc mechanical/physics/board_clearance.py build/mechanical/R5-B8-Assembly.FCStd build/mechanical/c3.step build/mechanical/hub.step
fc mechanical/physics/export_cad.py --cad build/mechanical/R5-B8-Assembly.FCStd --world build/physics/cad

python3.12 -m venv build/physics-venv
. build/physics-venv/bin/activate
python -m pip install -r mechanical/physics/requirements.txt
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib python mechanical/physics/blink_fit.py build/mechanical/R5-B8-Assembly.FCStd build/physics/cad build/physics/blink-fit.json
python mechanical/physics/check_head.py build/physics/cad build/physics/clearance.json
python mechanical/physics/tolerances.py build/physics/cad build/physics/tolerance.json
mkdir -p build/p1s
bambu-studio --slice 0 --outputdir build/p1s mechanical/R5-B8-P1S.3mf
python mechanical/physics/slicer_mass.py build/p1s/sliced-grams.json build/p1s/plate_{4,5,6,7,8,9,10,12,13}.gcode
python mechanical/physics/multibody.py build/physics/cad build/physics/motion --sliced-grams build/p1s/sliced-grams.json
python mechanical/physics/blink_fea.py build/physics/cad build/physics/blink-fea.json
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/retainer.py build/physics/cad build/physics/retention.json
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
```
