# B3 기구 및 물리 검증

`R5-B3-Assembly.FCStd`를 FreeCAD에서 엽니다. `revise.py`는 `inputs/`의 B1 조립본에서 B3와 변경 부품 STL을 생성합니다. CAD 트리의 턱 `Opening`은 닫힘 기준에서 0~13° 움직입니다.

| 항목 | 확인값 |
|---|---|
| 받침·보드·덮개 | 고체 1,876쌍 검사 통과. 목 좌우 −60~+60°, 덮개 0~30 mm |
| 눈·눈꺼풀 | 위쪽 공용축과 짧은 링크. 링크와 눈 받침 사이 최소 0.45 mm. MuJoCo에서 토크 상한과 마찰을 바꿔 60회 왕복 |
| 턱 | 뒤쪽 외장과 오른쪽 베어링 받침에 여유를 냄. 힌지 높이 ±0.4 mm와 영점 ±0.7°의 180개 자세에서 치아 간격 최소 0.77 mm |
| 목 | 머리 0.75 kg, 무게중심이 끄덕임 축 앞 30 mm인 조건에서 최대 약 0.28 N·m 필요 |
| 케이블 | 45°로 10 N을 가한 해석에서 받침 변위는 볼트 두 개로 지지할 때 0.008~0.010 mm. 낮은 마찰 조건에서는 10 N 이전에 미끄러짐 |

상부 조립체는 부품 쌍과 자세 조합 26,830건을 검사해 충돌 0건을 확인했습니다. 기존 두 모터 간섭은 고체 쌍 2,565건으로 다시 확인했습니다. 눈꺼풀 한쪽 링크가 모터의 0.12 N·m를 전부 받는 조건에서 축 방향 하중은 약 19 N이며, PETG 유효 탄성계수 1.45 GPa로 계산한 좌굴 하중은 약 82 N입니다.

## 시험편과 조립

- **눈꺼풀** · P1S용 맞춤 시험편은 PETG HF 약 26 g, 예상 2시간 27분입니다. Orbit 받침에 Ø2 핀을 끼워 손으로 90° 움직이고 링크 끝과 와셔가 걸리는지 확인합니다. Ø4 축에 MR104ZZ를 넣을 때 바깥쪽 턱이 외륜을 받습니다. 안쪽의 Ø4 칼라와 시임은 내륜만 받치고, 축에 예압이 걸리지 않게 맞춥니다. [눈꺼풀 시험편](R5-B3-Blink-Fit-P1S.3mf)
- **케이블** · 시험편을 P1S 0.4 mm, PETG HF, 레이어 0.20 mm, 벽 4줄로 출력합니다. 실제 케이블마다 22 mm가량의 EPDM 라이너와 4.8 mm 스트랩 두 개를 씁니다. M3×18 두 개, Ø7 mm 와셔, 잠금너트로 받침을 고정합니다. 전원을 끄고 직선과 옆 45°에서 각각 10 N을 30초 유지합니다. 이동 0.5 mm 이하, 피복 눌림과 커넥터 이동이 없는 상태를 통과로 봅니다.
- **목** · 6816 외륜은 고정 받침과 고정판 3개에, 내륜은 회전판에 닿게 조립합니다. 시임으로 씰에 닿지 않게 맞추고 회전판 들뜸 0.25~0.65 mm를 확인합니다. 오른쪽 Ø8 축 D-flat으로 토크를 받고 옆 나사로 빠짐을 막습니다. 실제 머리의 무게중심을 재고 축 고정부에 0.35 N·m를 서서히 걸어 밀림·갈라짐을 봅니다. 목 전 범위와 덮개 30 mm 열림에서 케이블이 당기는지도 확인합니다.
- **턱** · 왼쪽 모터 혼과 오른쪽 Ø4 핀을 같은 축으로 맞춥니다. 본딩 전에 손으로 움직여 턱 뒤쪽을 확인하고 치아 간격을 재서 닫힘을 정합니다. XL330 케이스 나사 삽입은 3 mm 이내, XL430 혼은 3.5 mm 이내입니다.

## 재현

아래는 저장소 루트에서 실행합니다. `fc`는 Debian에서 FreeCAD 1.0 모듈을 불러오는 예입니다. 해석은 Python 3.12와 Linux Gmsh용 `libGLU`를 사용합니다.

```sh
/usr/bin/python3 -m venv build/freecad-venv
build/freecad-venv/bin/pip install trimesh==4.10.1 manifold3d==3.3.2 'scipy<2'
fc() { PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python "$@"; }
fc mechanical/revise.py
fc mechanical/physics/base_clearance.py
fc mechanical/physics/export_cad.py --world build/physics/cad

python3.12 -m venv build/physics-venv
. build/physics-venv/bin/activate
python -m pip install -r mechanical/physics/requirements.txt
python mechanical/physics/check_head.py build/physics/cad build/physics/clearance.json
python mechanical/physics/multibody.py build/physics/cad build/physics/motion
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
python mechanical/physics/grip.py build/physics/grip
```
