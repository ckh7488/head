# B2 기구 및 물리 검증

`R5-B2-Assembly.FCStd`가 현재 설계본입니다. `revise.py`는 `inputs/`의 B1 턱 조립본을 입력으로 사용해 B2 조립본과 받침·케이블 시험용 STL을 `build/mechanical/`에 생성합니다. CAD 트리의 턱 `Opening` 속성으로 0~14° 열림을 확인할 수 있습니다.

| 항목 | 확인값 |
|---|---|
| 받침·보드·덮개 | 목 좌우 −60~+60°, 덮개 0~30 mm에서 고체 1,876쌍 검사 통과 |
| 눈꺼풀 | 오른쪽 링크가 2° 표본에서 눈 상하 모터와 겹침. MuJoCo에서 약 1.3°에 정지 |
| 턱 | 도면상 닫힘에서 치아 간격 0.87 mm. 힌지 ±0.4 mm와 영점 ±0.7° 오차를 적용하면 닿는 조합이 있으며, 1° 더 연 자세에서 최소 0.89 mm |
| 목 | 머리 0.75 kg, 무게중심이 끄덕임 축 앞 30 mm인 조건에서 최대 약 0.28 N·m 필요 |
| 케이블 | 45°로 10 N을 가한 해석에서 받침 변위는 볼트 두 개로 지지할 때 0.008~0.010 mm. 낮은 마찰 조건에서는 10 N 이전에 미끄러짐 |

## 시험편과 조립

- **케이블** · 시험편을 P1S 0.4 mm, PETG HF, 레이어 0.20 mm, 벽 4줄로 출력합니다. 실제 케이블마다 22 mm가량의 EPDM 라이너와 4.8 mm 스트랩 두 개를 씁니다. M3×18 두 개, Ø7 mm 와셔, 잠금너트로 받침을 고정합니다. 전원을 끄고 직선과 옆 45°에서 각각 10 N을 30초 유지합니다. 이동 0.5 mm 이하, 피복 눌림과 커넥터 이동이 없는 상태를 통과로 봅니다.
- **목** · 6816 외륜은 고정 받침과 고정판 3개에, 내륜은 회전판에 닿게 조립합니다. 시임으로 씰에 닿지 않게 맞추고 회전판 들뜸 0.25~0.65 mm를 확인합니다. 오른쪽 Ø8 축 D-flat으로 토크를 받고 옆 나사로 빠짐을 막습니다. 실제 머리의 무게중심을 재고 축 고정부에 0.35 N·m를 서서히 걸어 밀림·갈라짐을 봅니다. 목 전 범위와 덮개 30 mm 열림에서 케이블이 당기는지도 확인합니다.
- **눈·턱** · XL330 케이스 나사 삽입은 3 mm 이내, XL430 혼은 3.5 mm 이내입니다. 턱 모터 혼은 왼쪽, Ø4 핀과 MR104ZZ는 오른쪽입니다. 본딩 전에 힌지 축을 맞춰 손으로 돌리고 실물 치아 간격으로 닫힘을 정합니다. 오른쪽 눈꺼풀 링크는 수정 후 눈과 목을 함께 움직여 다시 검사합니다.

## 재현

아래는 저장소 루트에서 실행합니다. `fc`는 Debian에서 FreeCAD 1.0 모듈을 불러오는 예입니다. 다른 설치에서는 FreeCAD Python 경로를 맞춥니다. 해석은 Python 3.12와 Linux Gmsh용 `libGLU`를 사용합니다.

```sh
fc() { PYTHONPATH=/usr/lib/freecad-python3/lib /usr/bin/python3 "$@"; }
fc mechanical/revise.py
fc mechanical/physics/base_clearance.py
fc mechanical/physics/export_cad.py build/physics/cad

python3.12 -m venv build/physics-venv
. build/physics-venv/bin/activate
python -m pip install -r mechanical/physics/requirements.txt
python mechanical/physics/multibody.py build/physics/cad build/physics/motion
python mechanical/physics/jaw_clearance.py build/physics/cad build/physics/jaw
python mechanical/physics/cable_fea.py build/physics/cad build/physics/fea
python mechanical/physics/grip.py build/physics/grip
```
