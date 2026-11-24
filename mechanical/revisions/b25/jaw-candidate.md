# B25 턱 고정과 닫힘 제한 후보

양쪽 턱 받침 36·37을 움직이는 머리 프레임 09에 체결합니다. 받침마다 ISO 4762 M3×16, M3 육각너트, Ø6.0 mm 스틸 시임 와셔를 씁니다. 0.60 mm 깊이의 홈에 기준 두께 0.20 mm 와셔를 넣어 탭의 압축 하중을 턱 받침으로 전달합니다. 기존 B25 조립본과 프로젝트에서 별도 후보를 생성합니다. [검사 결과](jaw-candidate-checks.json)

이 시안의 너트 슬롯은 양쪽 M3 너트가 돌지 않게 잡으므로 5.5 mm 스패너가 들어갈 자리가 없습니다. 개방된 너트 자리와 공구 접근을 설계한 뒤 조립본에 반영합니다.

1. 머리 프레임을 조립하기 전에 양쪽 고정 탭의 옆 홈에 M3 너트를 넣습니다. 턱 팔을 달기 전에 받침 36·37의 아래쪽 카운터보어에 M3×16을 넣어 볼트 머리 통과 공간을 확보합니다.
2. 양쪽 받침의 Ø2.5 mm 파일럿을 M3×0.5로 마감하고 작업대에서 M3×12 평끝 무두나사로 닫힘을 맞춥니다. 보정 영점에 스토퍼와 팔 사이의 틈을 두고, 두 팔의 첫 접촉을 맞춘 뒤 각 나사 위에서 M3×3 무두나사로 잠급니다. 조립 후에는 눈 크래들이 수직 공구 접근을 가리므로 다시 맞출 때 턱 모듈을 분리합니다.
3. 앞 외장을 정면에서 밀어 넣고 턱 모듈을 아래에서 올립니다. 받침의 상단 홈에 스틸 시임 와셔를 놓고 두 탭의 원통 끝을 맞춥니다. 아래쪽에서 2.5 mm 육각 비트로 볼트 두 개를 조입니다. 작업대 검사의 초기 조임 토크는 0.05 N·m입니다. 턱 모듈을 분리할 때는 전원을 끄고 ID6 JST 플러그를 빼서 옆으로 옮깁니다. 턱을 받치고 볼트를 4 mm 풀어 모듈을 아래로 내립니다. 플러그를 연결한 상태에서는 모터와 플러그가 걸립니다.
4. 전원을 넣기 전에 머리 프레임을 받쳐 좌우 받침을 각각 5 N으로 30초씩 아래로 당깁니다. 재조립 10회 뒤 같은 검사를 하고 시임과 볼트의 움직임, 탭의 층간 균열, 영점 변화를 기록합니다. 전원을 끈 상태에서 턱 양쪽에 닫힘 하중을 각각 가해 스토퍼를 대고 앞니 양쪽으로 0.5 mm 필러 게이지를 통과시킵니다. 닫힘 영점에서 두 팔과 스토퍼 사이의 틈을 확인하고 최대 열림까지 손으로 왕복합니다.

FreeCAD에서 경로와 머리 고정을 확인했습니다. 두 볼트 체결 형상이 받침을 0.25 mm 내려 본 위치에서 이탈을 막습니다. 탭 한 개에 5 N을 가한 단순 보 계산에서 공칭 굽힘 응력은 왼쪽 약 9.5 MPa, 오른쪽 약 14.1 MPa입니다. 와셔 위에 연속 재료가 있는 압축 기둥은 왼쪽 0.95 mm, 오른쪽 3.60 mm이고 유효 너트 면적의 98.0%를 지지합니다. 마찰 계수에 따른 단순 조임 계산에서는 0.05 N·m와 토크 계수 0.15로 평균 압축 응력이 약 6.5 MPa입니다. 출력층, 응력 집중, 너트 홈과 반복 탈착을 포함한 강도는 실물에서 확인합니다. 6번 판의 일반 서포트를 제거한 뒤 너트 홈과 공구 통로를 확인합니다. Bambu Studio 슬라이스는 4·6·9번 판에서 완료했습니다.

바뀐 체결 탭과 인접 부품의 삽입을 0.20 mm 이하 간격으로 재현했습니다. 이 쌍들의 연속 거리 하한은 외장 삽입 0.140 mm, 턱 받침 삽입 약 0.100 mm입니다. 체결 탭 주변 작동 간격을 검사할 때는 눈 상하 −8.4~+8.4°, 목 상하 −17.21~+7.13°, 턱 −0.5~+9.71°를 표본 범위로 사용했습니다. 턱의 기존 개방 스토퍼는 명목 7.46°에서 닿습니다. 치아 간격 계산에는 보정 고저차 ±0.4 mm, 영점 각도 오차 ±0.7°, 반 틱 양자화를 포함했습니다. 닫힘 복구 모델과 스토퍼 접촉 각도는 검사 결과에 함께 기록했습니다.

MuJoCo 재생은 슬라이서가 계산한 모델 질량과 B24 스토퍼 모델을 사용합니다. 새 닫힘 스토퍼는 CAD에서 접촉 위치를 확인했습니다. 닫히는 방향으로 축에서 58 mm 떨어진 얼굴에 1 N이 걸리면, 먼저 닿는 스토퍼 한 곳에 약 5.3–5.8 N이 전달됩니다. 정지 토크와 PWM 상한으로 계산한 모터 단독 하중도 약 8.5–9.4 N입니다. 실물에서는 축 기준의 하중을 기록하고, 한쪽 스토퍼씩 하중을 받쳐 잠금 전후 각도와 앞니 필러 게이지 간극을 확인합니다.

## 재현

FreeCAD Python에서 FreeCAD, NumPy, trimesh, manifold3d, python-fcl, lxml을 사용할 수 있는 환경을 사용합니다. 스크립트와 저장 보고서는 입력 파일의 SHA-256을 기록합니다.

```sh
export PYTHONPATH=mechanical:mechanical/physics:/usr/lib/freecad-python3/lib
export QT_QPA_PLATFORM=offscreen
out=build/b25-jaw
python mechanical/build_b25_jaw_candidate.py "$out"
python mechanical/physics/check_b25_jaw_retention.py \
  mechanical/revisions/b25/R5-B25-Assembly.FCStd "$out/R5-B25-Jaw-Assembly.FCStd" "$out/retention.json"
python mechanical/physics/export_cad.py --world --cad "$out/R5-B25-Jaw-Assembly.FCStd" "$out/cad"
python mechanical/physics/check_b25_jaw_close_stop.py "$out/cad" "$out/closure-stops.json"
python mechanical/physics/check_b24_jaw_close.py "$out/cad" control/openrb/R5B1/R5B1.ino "$out/teeth.json"
```

4·5·6·9번 판을 각각 슬라이스합니다. 5번 판은 기존 B25에서 같은 외형으로 다시 삼각화한 출력판을 사용합니다. 5번 판 수치 없이 비교하면 B24 뒤 외장 질량을 이어 씁니다. 일체형 앞 외장과 코받침은 합산 압출량에서 기존 코받침 질량을 빼 구분합니다.

```sh
for plate in 4 5 6 9; do
  mkdir -p "$out/slice-$plate"
  bambu-studio --slice "$plate" --outputdir "$out/slice-$plate" "$out/R5-B25-Jaw-P2S.3mf"
done
python mechanical/physics/slicer_mass.py "$out/parts.json" \
  "$out/slice-4/plate_4.gcode" "$out/slice-5/plate_5.gcode" \
  "$out/slice-6/plate_6.gcode" "$out/slice-9/plate_9.gcode"
python mechanical/physics/b25_jaw_replay_masses.py mechanical/revisions/b24/sliced-grams.json \
  "$out/masses.json" "$out/parts.json"
python mechanical/physics/b23_motion_replay.py "$out/cad" "$out/masses.json" \
  mechanical/revisions/b24/jaw-stop.json "$out/replay" --jaw-minimum-voltage 4.07
```

## 뒤쪽 너트 자리 시안

일반 M3 너트를 뒤에서 넣도록 고정 위치를 옮긴 시안을 별도로 검사했습니다. 턱 삽입과 오른쪽 공구 접근에 간섭이 남았습니다. [뒤쪽 턱 고정 검사](jaw-relocated-mount.md)
