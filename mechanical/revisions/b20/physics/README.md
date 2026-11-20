# R5 B20 하중과 움직임

B20의 P2S 모델 압출량으로 부품 질량을 구하고, CAD에서 무게중심·관성·받침 위치를 뽑았습니다. 목과 턱은 MuJoCo에서 중력과 관성, 마찰과 모터 토크 제한을 넣어 계산했습니다. 링크와 축은 힘이 전달되는 방향을 따로 계산했고, 크래들·목 허브·턱 팔은 실제 형상으로 탄성 해석했습니다.

**사용 조건은 무접촉 운전을 기본으로 하고, 우발적인 접촉은 가볍게 한쪽을 만지는 정도까지입니다.** 이번 계산은 눈꺼풀 한쪽에 0.25·0.5·1 N을 적용합니다. 1 N은 가벼운 접촉을 살펴보기 위한 계산값입니다. 보호 케이스로 접촉을 막는 구성이라면 내부 마찰과 배선이 주요 부하입니다. 걸림 실험은 움직임을 멈춰야 할 때 모터에 힘이 남으면 어디가 먼저 변형되는지 보는 별도 조건입니다.

## 평소 움직임과 가벼운 접촉

- 목 상하축이 움직이는 질량은 약 612 g입니다. 펌웨어에 맞춘 속도에서 필요 토크는 기본 조건 0.055 N·m, 앞쪽에 75 g을 더하고 전압·출력을 낮춘 조건 0.132 N·m였습니다. 두 조건에서 목 상하 모터는 토크 한계에 닿지 않았습니다. 턱은 같은 조건에서 최대 추종 오차가 1.71°에서 5.76°로 늘었습니다. [목과 턱 동역학](dynamics.json)
- 눈꺼풀은 무접촉 조건에서 90.0°까지 닫혔습니다. 닫힘 직전에 회전축에서 약 14 mm 떨어진 한쪽에 0.25·0.5·1 N을 가했을 때 마지막 각도는 각각 89.6°·89.2°·88.4°였습니다. 1 N에서 모터 토크는 최대 0.021 N·m였고, 가정한 한계는 0.085 N·m입니다. [접촉 하중별 비교](blink-load.json) · [눈꺼풀 레일 탄성 해석](blink-rail.json)
- 턱은 목을 중립에 고정하고 58 mm 지점에 150 ms 동안 0.25·0.5·1 N을 가했을 때 최대 0.90°·1.81°·3.70° 늦었습니다. 1 N에서는 하중을 가한 시간의 36% 동안 모터가 출력 한계에 닿았고 모델은 계속 닫히는 방향으로 움직였습니다. 투명 케이스를 쓰면 턱에 손이 닿는 상황을 피할 수 있습니다. 손이 닿는 구성에서는 접촉 시 정지 동작을 별도로 검증합니다. [턱 접촉 동역학](jaw-touch.json)
- 눈 링크는 물림 유격과 힘을 받을 때 핀 위치가 얼마나 어긋나는지 봤습니다. 실제 눈꺼풀 링크 구멍은 약 Ø2.40 mm이고 축은 Ø2 mm입니다. 매끈한 핀이 들어가는 완성 구멍을 Ø2.08–2.10 mm로 놓은 계산에서는 가운데 링크의 한쪽 유격 각도가 7.9°에서 1.5–1.8°로 줄었습니다. 맞물리는 다른 구멍의 유격과 실제 출력 끼움은 별도입니다. [링크·축 계산](blink-load.json)
- 한쪽 눈에 힘이 몰리면 중앙 모터판과 안구 아래 지지대가 서로 어긋납니다. 안구가 닿기 시작하는 값은 부드럽게 지지한 모델과 시험 자세에서 약 0.02–0.03 N·m였습니다. 단단하게 지지한 모델에서는 같은 시험에서 훨씬 더 높은 하중까지 접촉하지 않았습니다. 조립부 지지 강성이 확인되어야 실제 눈 접촉 하중을 좁힐 수 있습니다. [눈 크래들 탄성 해석](eye-cradle.json)

## 걸렸거나 힘을 잃었을 때

- 목 모터 토크가 끊기면 마찰을 작게 둔 모형에서 약 113 ms, 앞쪽 75 g 추가 모형에서는 약 35 ms에 명령 범위 +6°를 넘었습니다. 마찰을 크게 둔 기준 모형은 계산한 650 ms 동안 범위에 머물렀습니다. 실제 정지 위치와 충격은 스토퍼와 기어의 상태에 따라 달라집니다. [토크 차단 결과](dynamics.json)
- 목 허브의 탄성 해석에서 큰 정상 구동 조건의 변형은 약 0.023 mm였습니다. D-flat은 건식 왕복 유격이 약 6.7°입니다. 같은 토크에서 접착 면적 10%는 50%보다 계산 전단응력이 5배입니다. 이 조인트는 핀 지름보다 유격과 접착이 힘 전달에 민감합니다. [목 조인트](neck-joint.json)
- 받침은 미끄럼과 전도를 따로 계산했습니다. 평평한 바닥에서 받침 컵과 가동부만 포함한 모델의 약 290 mm 높이 수평 전도력은 약 3.23 N입니다. 실제 받침의 마찰, 내부 전장 질량, 케이블을 잡아당기는 높이가 결과를 바꿉니다. [받침](base-stability.json)
- 턱 팔은 무접촉의 큰 운전 토크에서 약 0.11 mm 이동하고 0.36° 비틀렸습니다. 앞니에서 회전 토크가 가장 커지는 방향으로 1 N을 더한 하중에서는 선형 모델이 0.41 mm, 1.34°를 예측했습니다. 공급사 정지 토크를 끝까지 가한 별도 걸림 실험에서는 약 6.2° 비틀렸으며 보수적으로 둔 적층 응력 기준에도 닿았습니다. 실제 접착·체결과 적층 강도는 실물에서 확인해야 합니다. [턱 팔 탄성 해석](jaw-strength.json)
- 전선을 고정한 채 턱만 열어도 목 좌우 +45° 또는 +60°, 상하 +6°, 눈 상하 −8°에서 ID5 전원선은 턱 11.5°부터 닿았습니다. 턱 안쪽을 깎은 진단 시안은 접촉을 없앴으나 일부 외장까지 뚫렸습니다. 케이블 힘은 피복과 연선의 굽힘 강성, 고정 상태를 측정해야 계산할 수 있습니다. [고정된 배선의 턱 행정 검사](harness.json)

## 재현

[기구 해석 의존성](../../../physics/requirements.txt)과 FreeCAD 모듈을 같은 Python 환경에서 사용합니다. 아래는 저장소 루트 기준입니다.

```sh
spec=mechanical/revisions/b20/physics
assembly=mechanical/revisions/b20/R5-B20-Assembly.FCStd
out=build/b20-physics
mkdir -p "$out"
python mechanical/physics/export_cad.py --world --cad "$assembly" "$out/cad"
python mechanical/physics/b20_dynamics.py "$out/cad" "$out/dynamics" --sliced-grams "$spec/sliced-grams.json"
python mechanical/physics/b20_dynamics.py "$out/cad" "$out/jaw-touch" --sliced-grams "$spec/sliced-grams.json" --jaw-touch
python mechanical/physics/b20_neck_joint.py "$assembly" "$out/neck.json" --loads "$out/dynamics/b20-dynamics.json" --fea
python mechanical/physics/b20_blink_load.py "$out/cad" "$out/blink.json" --dynamics
python mechanical/physics/b20_eye_cradle_fea.py "$assembly" "$out/eye.json" --world-cad "$out/cad"
python mechanical/physics/b20_jaw_strength.py "$out/cad" "$out/jaw.json" --dynamics "$out/dynamics/b20-dynamics.json"
python mechanical/physics/b20_base_stability.py "$out/cad" "$out/dynamics/b20-dynamics.json" "$out/base.json" --base-mass-g 231.7155476128
node --input-type=module -e 'import {installedHardware} from "./web/assembly/steps.js"; import {readFileSync} from "node:fs"; process.stdout.write(JSON.stringify(installedHardware(JSON.parse(readFileSync("web/assets/assembly.json")).parts)));' > "$out/hardware.json"
python mechanical/physics/b20_harness.py "$out/cad" "$spec/harness-cut-lengths.json" "$out/hardware.json" "$out/harness.json"
```

질량표에는 출력 후 남는 압출량만 넣었습니다. 5·6·7·8·11·12번 판은 B20 G-code, 4·9·10·13번은 메시·배치·설정이 동일한 기존 P2S G-code에서 읽었습니다. [압출 질량 추출 코드](../../../physics/slicer_mass.py)

턱의 네 해상도를 비교하려면 `--step 1.2 .95 .7 .55`를 추가합니다. 눈 크래들의 가장 미세한 해는 `--mesh-mm .65 --fixtures stiff_bridges`로 따로 계산했습니다.
