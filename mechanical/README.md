# B5 기구 조립

FreeCAD에서 [B5 조립본](R5-B5-Assembly.FCStd)을 엽니다. `revise.py`가 출력을 위한 STL을 생성합니다. 턱의 `Opening`을 0~13°에서 조절할 수 있습니다. [P1S 전체 출력판](R5-B5-P1S.3mf) · [시험판](R5-B5-Fit-P1S.3mf)

출력 프로젝트는 P1S 0.4 mm 노즐, PETG HF, 0.20 mm 레이어, 벽 4줄을 사용합니다. 노즐 245 °C, 텍스처 PEI 베드 70 °C, 최대 유량 14 mm³/s를 설정했습니다.

| 부위 | 제작 전 확인 |
|---|---|
| 눈꺼풀 | 힌지 받침 간격 0.93 mm. 상대 조립 위치가 축마다 ±0.25 mm 어긋나면 계산상 최소 0.50 mm. MuJoCo 60회 왕복 |
| 목 | CAD 무게 조건에서 균형추 0장, 최대 0.092 N·m. 0.75 kg 머리와 축 앞 30 mm 무게중심 조건에서 12장, 오차를 포함해 최대 0.183 N·m |
| 케이블 | 마찰 0으로 10 N·30초와 20 N·6초를 가한 24개 접촉 해석에서 커넥터 축방향 이동 최대 0.32 mm. PETG 탄성계수 1 GPa 조건에서 트레이 변형 약 0.05 mm |
| 턱 | 힌지 높이 ±0.4 mm와 영점 ±0.7°를 넣은 180개 자세에서 치아 간격 최소 0.77 mm |
| PCB | KiCad STEP의 나사 구멍 6개가 받침과 일치. C3 USB-C 삽입과 허브 덮개 0~30 mm에서 플러그 간섭 0건 |

상부 27,052개 부품·자세 조합, 받침과 구동부·체결부 고체 쌍 4,867개에서 간섭이 없었습니다.

## 조립

- **눈꺼풀** · Ø2 × 9.5 mm 핀을 끼워 손으로 90° 움직입니다. Ø4 축의 MR104ZZ 외륜은 받침 턱으로, 내륜은 Ø4 칼라와 시임으로 고정합니다. 축이 자유롭게 돌도록 맞춥니다.
- **목** · 6816 외륜은 고정판 3개에, 내륜은 회전판에 받칩니다. 회전판 들뜸은 0.25~0.65 mm로 맞춥니다. 끄덕임 축은 Ø8 D-flat에서 힘을 받고 옆 나사가 축을 고정합니다. 균형추 트레이는 머리 프레임 뒤의 인서트 4개에 M3×8로 고정합니다. 외장과 모터를 조립한 뒤 전원을 끄고 수평에서 균형을 잡도록 연강판을 0~12장 추가합니다. 누름판을 맨 위 강철판에 대고 두 나사로 고정합니다. 목 전체 각도와 서비스 덮개 30 mm 개방에 걸쳐 케이블에 여유를 둡니다.
- **턱** · 왼쪽 혼과 오른쪽 Ø4 핀을 같은 축으로 맞춥니다. 본딩 전에 손으로 움직여 뒤쪽과 치아가 닿지 않는 닫힘 위치를 찾습니다. XL330 케이스 나사 삽입은 3 mm 이내, XL430 혼은 3.5 mm 이내입니다.
- **보드** · C3는 부품 면 위, USB-C 입구 앞쪽으로 두고 M2×5 두 개로 고정합니다. 허브는 밑 덮개에 M3×5로 고정합니다. 덮개를 내릴 수 있게 안쪽에 배선 여유를 둡니다. [전원·배선](../electronics/README.md)

### 케이블 고정

전원 고정부에는 AMASS XT30U와 XT60U를 사용합니다. USB-A는 평평한 뒤턱과 15 mm 이상의 몸체가 있는 연장선을 고릅니다. 18 AWG 전원선 두 가닥은 출구에서 가로로 나란히 놓습니다. 표의 단위는 mm입니다.

| 위치 | 뒤턱 최소 | 몸체 최대 | 고정부를 통과하는 선·목 최대 |
|---|---:|---:|---:|
| 5 V XT30U | 10.0 × 5.0 | 10.45 × 5.45 | 7.0 × 3.2 |
| 목 전원 XT60U | 15.0 × 7.7 | 15.75 × 8.45 | 11.1 × 5.0 |
| 카메라·OpenRB USB-A | 12.4 × 7.0 | 18.5 × 10.3 | 6.4 × 5.2 |

케이블 트레이는 M3×18 두 개와 평와셔·잠금너트로 받침에 고정합니다. 덮개는 M3 인서트를 넣고 M3×12 다섯 개로 조입니다. 실제 커넥터에 시임을 대어 좌우·상하 유격을 편측 약 0.12 mm로 맞추고 뒤턱을 받침에 밀착시킵니다. 전원을 끄고 케이블을 직선과 45°에서 10 N으로 30초씩 당겨 0.5 mm 이하 이동과 피복 상태를 확인합니다. [허브 극성](../electronics/README.md#전원과-배선)

## 재현

저장소 루트에서 실행합니다. FreeCAD 1.0과 Python 3.12가 필요하며 Linux에서 Gmsh는 `libGLU`를 사용합니다.

```sh
/usr/bin/python3 -m venv build/freecad-venv
build/freecad-venv/bin/pip install trimesh==4.10.1 manifold3d==3.3.2 'scipy<2'
fc() { QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python "$@"; }
fc mechanical/revise.py
fc mechanical/physics/base_clearance.py --cad build/mechanical/R5-B5-Assembly.FCStd
kicad-cli pcb export step --board-only --user-origin 65x42mm -o build/mechanical/c3.step electronics/c3-rf/C3_Antenna.kicad_pcb
kicad-cli pcb export step --board-only --user-origin 100x80mm -o build/mechanical/hub.step electronics/servo-hub/R5_Servo_Hub.kicad_pcb
fc mechanical/physics/board_clearance.py build/mechanical/R5-B5-Assembly.FCStd build/mechanical/c3.step build/mechanical/hub.step
fc mechanical/physics/export_cad.py --cad build/mechanical/R5-B5-Assembly.FCStd --world build/physics/cad

python3.12 -m venv build/physics-venv
. build/physics-venv/bin/activate
python -m pip install -r mechanical/physics/requirements.txt
python mechanical/physics/check_head.py build/physics/cad build/physics/clearance.json
python mechanical/physics/tolerances.py build/physics/cad build/physics/tolerance.json
python mechanical/physics/multibody.py build/physics/cad build/physics/motion
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/retainer.py build/physics/cad build/physics/retention.json
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
```
