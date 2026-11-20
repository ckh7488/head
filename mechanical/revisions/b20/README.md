# R5 B20 제작과 조립

[FreeCAD 조립본](R5-B20-Assembly.FCStd) · [Bambu P2S 전체판](R5-B20-P2S.3mf) · [크래들 STL](print/12_eye_tilt_cradle-B20.stl) · [조립 절차](../../ASSEMBLY.md) · [부품표](../../BOM.csv) · [3D 조립 화면](../../../web/README.md#b20-조립-순서)

- 눈을 정면으로 둔 상태에서 타이바의 들어가는 쪽 구멍을 크래들 왼쪽 입구의 표시 홈에 맞춥니다. 수평으로 밀고 마지막에 뒤쪽 아래로 내립니다. 안구·크래들 피벗과 핀 구멍은 같은 위치에 있습니다.
- P2S의 0.4 mm 노즐, Textured PEI Plate, Bambu PETG HF 기준입니다. Bambu Studio에서 3MF를 프로젝트로 엽니다. 1~12번은 기본 부품, 13번은 선택 균형추입니다. 5번 판의 턱은 양쪽 팔과 한 몸이고, 8번 판에 ID5 가드가 있습니다.
- 크래들 서포트를 떼고 눈을 넣기 전에 위쪽 핀 가이드 두 곳에 Ø2 핀이 손으로 통과하는지 봅니다. 구멍에 잔여물이 있으면 Ø2.2 비트를 손으로 돌려 윗다리만 정리합니다.
- 목의 두 Ø3×12 핀은 축과 프레임을 연결합니다. 핀과 축 구멍을 건식으로 맞추고 허브 안에 고정합니다. 오른쪽 D-flat은 클램프 보어 안에서 고정하고 클램프와 모터 혼을 연결하는 나사는 분리할 수 있게 둡니다.

## 검증 기록

[조립 경로](assembly-check.json) · [구동 자세](head-clearance.json) · [구동 중 체결품](hardware-sweep.json) · [제자리 겹침](static-pairs.json) · [출력 경로](slicing-check.json) · [턱 주변 배선](wiring-corners.json)

Bambu Studio에서 형상이 바뀐 5·6·7·8·11·12번 판을 새로 슬라이스했습니다. 여섯 판은 각 판의 슬라이서 경고와 0.20 mm 격자에서 검출된 고립 압출 시작점이 모두 0건입니다. 나머지 일곱 판은 B16에서 검증한 메시·배치·설정을 사용합니다.

타이바를 옆으로 미는 구간은 CAD에서 앞뒤·상하 각각 ±0.5 mm, 마지막 안착 구간은 이동 방향을 가로지르는 두 축에서 각각 ±0.15 mm 치우침을 검사합니다. 공구 접근은 CAD의 공구 형상 기준입니다. 실제 핀·탭 끼움과 접착 강도는 실물 확인 항목입니다. 구매품의 열린 메시 때문에 겹침 부피를 계산할 수 없었던 30쌍은 제자리 검사 기록에 표시됩니다.

조립 뷰어의 마지막 단계에는 CAD에 모델링한 내부 배선 경로 20개와 후면 연결부가 표시됩니다. 전선 길이와 단자는 [전선 재단표](../../WIRING-CUT-LIST.csv)를 따릅니다.

배선 경로 계산에서 바닥 덮개를 닫고 목 좌우 +60°·상하 +6°, 눈 상하 −8°, 턱 13°를 겹치면 ID3 전원과 ID5 세 가닥이 턱에 닿습니다. `jaw_clack.py`는 목 두 축이 각 중립 ±2° 이내로 확인될 때 턱 시험을 시작합니다. 시험 중 머리를 정면에 받칩니다. 목과 턱을 동시에 끝까지 구동하려면 턱 근처의 배선 고정 구조를 해결해야 합니다.

## 재현

저장소 루트에서 FreeCAD 모듈과 [기구 검사 의존성](../../physics/requirements.txt), [시험 의존성](../../../tests/requirements.txt)을 사용할 수 있는 Python으로 실행합니다.

```sh
mkdir -p build/b20/print
python mechanical/build_b20.py --output build/b20/assembly.FCStd --stl build/b20/print/12_eye_tilt_cradle-B20.stl
python mechanical/physics/export_cad.py --world --cad build/b20/assembly.FCStd build/b20/cad
node --input-type=module -e 'import {steps,hardware} from "./web/assembly/steps.js"; process.stdout.write(JSON.stringify({steps,hardware}));' > build/b20/hardware.json
spec=mechanical/revisions/b19/print/hardware-spec.json
python mechanical/physics/check_b19_assembly.py --revision b20 build/b20/cad build/b20/hardware.json "$spec" build/b20/assembly-check.json
python mechanical/physics/check_head.py build/b20/cad build/b20/head-clearance.json
python mechanical/physics/check_b19_hardware.py build/b20/cad "$spec" build/b20/hardware-sweep.json
python mechanical/physics/check_static_pairs.py build/b20/cad build/b20/static-pairs.json --baseline mechanical/revisions/b19/static-pairs.json
python web/b19/build_b19_viewer.py build/b20/cad build/b20/hardware.json "$spec" build/b20/assembly-check.json --revision B20 --assembly-cad build/b20/assembly.FCStd --output build/b20/viewer
python mechanical/build_b20_print.py build/b20/R5-B20-P2S.3mf --cradle build/b20/print/12_eye_tilt_cradle-B20.stl
bambu-studio --slice 0 --outputdir build/b20/slices build/b20/R5-B20-P2S.3mf
python -m pytest -q
```
