# 제어와 보정

B25 기구와 A5 허브는 카메라 미리보기, 모터를 뺀 첫 통전, 보정과 한 축 구동, 실물 인수 시험 순서로 확인합니다. 웹 데모에서는 B25의 눈·목·눈꺼풀·턱을 조작할 수 있습니다. [구동 데모](https://r5-b1-review.ckh.chatgpt.site/b25/demo/) · [B25 실물 시험](../spec/bench.md#b25-실물-시험)

## 하드웨어 없이 실행

저장소 루트에서 Python과 C++ 컴파일러로 모형과 가상 USB 연동을 검사합니다. 가상 USB 연동은 Linux·macOS·WSL에서 실행됩니다. B25 인수 검사에서 실물 기록이 없으면 해당 항목은 `UNVERIFIED`입니다. [판정 범위](../spec/requirements.md)

```sh
python -m pip install -r tests/requirements.txt
python -m pytest
python spec/verify.py --revision B25
```

## 카메라 미리보기

Python 3.12에서 PC 제어 환경을 준비합니다. `--drive` 플래그 없이 실행하면 미리보기 모드로 동작합니다. 첫 실행에 MediaPipe 모델을 내려받고 해시를 확인합니다.

```sh
python3.12 -m venv build/control-venv
. build/control-venv/bin/activate
python -m pip install -r control/pc/requirements.txt
python control/pc/track.py --source path/to/video.mp4 --headless
```

실제 카메라 미리보기에는 `--source 0`을 사용합니다. 미리보기는 U20CAM-1080P-S1 사양표의 수평 화각 106°를 기본값으로 씁니다. 설치한 카메라는 체커보드 사진을 `calibrate_camera.py`에 넘겨 보정하고, 결과 JSON을 `track.py --calibration`에 넣습니다. [카메라 매뉴얼](https://github.com/INNO-MAKER/U20CAM-1080P-S1)

## OpenRB와 모터

### 모터를 뺀 첫 통전

1. 작업대에서 모터·OpenRB·USB와 두 어댑터를 분리하고, 두 퓨즈를 뺍니다. J1 5 V와 J2 12 V 배선의 극성과 도통을 잰 뒤 **첫 통전 전에 J2 잠금쇠를 고정**합니다. 잠금쇠를 확인한 뒤 퓨즈를 뺀 첫 통전과 퓨즈를 넣은 무부하 출력을 순서대로 잽니다. [A5 전원 실물 검수](../electronics/README.md#전원-실물-검수) · [B25 조립과 배선](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선)
2. 어댑터를 뺀 채 OpenRB 점퍼를 **USB(VIN)** 쪽에 두고 나사식 VIN 단자를 비워 둡니다. 허브 J3와 연결할 W10·W11은 GND·DATA만 이어지며 OpenRB EH 2(VDD)는 비워 둡니다. 도통과 단락 여부를 확인한 뒤 J3를 연결합니다. [허브 단자와 배선](../electronics/README.md#허브-단자와-배선)
3. Arduino IDE에 ROBOTIS 보드 인덱스를 추가합니다. OpenRB-150 코어 **0.2.1**, Dynamixel2Arduino **0.8.2**로 [R5B1.ino](openrb/R5B1/R5B1.ino)를 빌드하고 USB로 올립니다. 모터를 연결하기 전에 시리얼 모니터를 **115200 bps**, 줄바꿈 사용으로 열어 `PING`에 `R5B1 1`이 오는지 확인합니다. 여기까지는 A5 출력 전압과 OpenRB USB 응답을 확인합니다. [보드 인덱스](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenRB-150/master/package_openrb_index.json) · [라이브러리](https://github.com/ROBOTIS-GIT/Dynamixel2Arduino)

### 보정과 한 축 구동

1. OpenRB로 Wizard를 사용할 때는 보드 매니저 예제 `usb_to_dynamixel`을 먼저 올립니다. 어댑터와 USB를 뺀 상태에서 해당 전압의 A5 출력에 모터를 한 개씩 연결합니다. OpenRB는 위와 같이 USB(VIN)으로 공급하고, A5와는 GND·DATA만 잇습니다. 전원을 넣고 Wizard에서 ID, Protocol 2.0, **57,600 bps**, 위치 모드 3, 속도 기반 프로파일, Status Return Level 2를 설정합니다. Drive Mode의 Goal Update 자동 토크 활성화는 끄고 Startup Configuration은 0으로 둡니다. 모터를 바꿀 때마다 어댑터와 USB를 뺍니다. 설정이 끝나면 Wizard를 닫고 모터 전원을 분리한 뒤 `R5B1.ino`를 다시 올립니다. 시리얼 모니터에서 `PING` → `R5B1 1`을 확인한 뒤 포트를 닫습니다. [Wizard 연결](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#dynamixel-wizard-20) · [Drive Mode](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drive-mode10) · [Startup Configuration](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#startup-configuration60)
2. 무전원에서 모터를 연결한 뒤 목과 턱을 받치고 전원을 넣습니다. `--release`로 `RELEASED`를 받고 `--check`의 전 축 `torque=0`을 확인한 뒤 손으로 움직입니다. 초기 보정표가 비어 있으면 `--check`가 `CHECK`와 함께 종료값 1을 낼 수 있으므로 각 행의 `torque=`를 직접 확인합니다. 토크 해제를 확인할 수 없으면 서보 전원을 분리합니다. 중립과 접촉 없이 쓸 수 있는 위치를 잽니다. 목·턱의 첫 접촉과 보정 끝점은 같은 중립을 기준으로 기록하고, 모터 전원은 켜고 토크는 끈 상태에서 `commission.py --read ID`로 각 위치의 엔코더를 읽습니다. [P04·P06 측정](../spec/bench.md#b25-실물-시험)
3. 실측한 `low, zero, high`를 [Calibration.h](openrb/R5B1/Calibration.h)에 넣고 파일 검사 후 펌웨어를 다시 올립니다. 저장소에 포함된 기본 보정표의 여섯 행은 모두 `-1`입니다. 파일 검사가 통과해도 비어 있는 행은 잠겨 있습니다. 여섯 모터를 연결한 상태에서 `--check`를 실행해 각 ID의 `OK`, `torque=0`, `calibrated=1`을 확인합니다. `--check`는 연결된 상태만 읽으며, 보정·시작 설정·현재 위치를 포함한 구동 준비 상태를 확인합니다.
4. 목을 받치고 `--axes eye-yaw`부터 한 축씩 보정 방향과 간섭을 확인합니다. 나머지 추적 축은 `eye-pitch`, `blink`, `neck-yaw`, `neck-pitch`입니다. 추적 프로그램을 닫으면 `HOLD`가 전송됩니다. 축을 바꾸기 전에는 목을 다시 받치고 `--release`의 `RELEASED`를 확인합니다. ID6은 목 양축을 중립에 두는 턱 시험 모드에서 확인합니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --release
python control/pc/commission.py --serial /dev/ttyACM0 --check
python control/pc/commission.py --serial /dev/ttyACM0 --read 1
```

실측 보정표를 작성한 뒤 파일을 검사합니다.

```sh
python control/pc/check_calibration.py
```

보정표를 포함한 펌웨어를 다시 올리고 전 축 준비를 확인한 뒤 한 축 구동을 시작합니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --check
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive --axes eye-yaw --immediate-hold
python control/pc/commission.py --serial /dev/ttyACM0 --release
```

`/dev/ttyACM0`과 카메라 번호는 실제 장치에 맞춥니다. `--check`와 `--release`는 ID 1–6을 모두 확인합니다. 일부만 조립한 경우에는 필요한 ID를 `--read`로 읽고, 정비 전에 목을 받친 뒤 서보 전원을 차단합니다.

### 보정 범위

| ID | 축 | `low, zero, high` 위치 |
|---|---|---|
| 1 | 눈 좌우 | 영상 왼쪽, 중립, 오른쪽 (양쪽 162틱 이내) |
| 2 | 눈 상하 | 위, 중립, 아래 (양쪽 83틱 이내) |
| 3 | 눈꺼풀 | 열림, 열림, 닫힘 (최대 1,024틱) |
| 4 | 목 좌우 | 영상 왼쪽, 중립, 오른쪽 (양쪽 640틱, 56.25° 이내) |
| 5 | 목 상하 | 들기 최대 13.10°(149틱 이내), 중립, 숙이기 최대 2.64°(30틱 이내) |
| 6 | 턱 | 치아 여유를 둔 닫힘, 같은 닫힘, 닫힘에서 최대 62틱 열림(엔코더 환산 각도 5.449°) |

#### 축별 한계와 잠금 조건
- **공통**: 실물 간섭이 없는 범위로 줄여 보정할 수 있습니다. 목 엔코더는 4,096틱/회전 기준이며, `check_calibration.py --nominal-neck`은 목을 보정표 끝까지 쓰도록 잡았을 때만 사용합니다.
- **눈 좌우·상하 (ID1·ID2)**: 중립에서 양 끝을 각각 **162틱(약 14.24°)**, **83틱(약 7.29°)** 안에 보정합니다(위치 허용 8틱 포함 피드백 범위 약 ±14.94° / ±8.00°). PC 명령 ±15°·±8°가 보정 양 끝에 대응합니다. [B25 눈 좌우 검사](../mechanical/revisions/b25/eye-yaw-clearance.json)
- **목 좌우 (ID4)**: 중립 양쪽 **640틱(56.25°)** 초과 시 `YAW_CALIBRATION_RANGE`로 잠깁니다(위치 오차 8틱 포함 ±56.95°, PC 명령 ±60° 대응). [스토퍼와 추적 검사](../mechanical/revisions/b25/neck-yaw-travel.md)
- **목 상하 (ID5)**: 들기 **149틱**·숙이기 **30틱** 초과 시 `PITCH_CALIBRATION_RANGE`로 잠깁니다(위치 오차 8틱 포함 −13.799°~+3.340°, PC 명령 −15°/+4.5° 대응).
- **턱 (ID6)**: **62틱(5.449°)** 초과 보정은 `JAW_CALIBRATION_RANGE`, 0~5.5° 외 명령은 `JAW_GOAL_RANGE`로 거부합니다(피드백 5틱 포함 67틱 = 5.889°, B25 CAD 하강량 **5.18 mm**). 토크를 끈 실물에서 닫힘 영점 기준 **닫힘 쪽 최소 28틱**, **열림 쪽 최소 79틱**(Goal PWM 미확인 시 **90틱**) 무접촉 범위를 확보합니다. [B25 스토퍼 검사](jaw-opening-check.json) · [고정 검사 조건](../spec/conditions.md#6-동작-범위)

## 전시 추적과 턱 시험

한 축씩 방향과 간극을 확인한 뒤 전시 추적과 턱 시험을 실행합니다. 턱을 구동하기 전에 P08 건식 간극과 P06 토크 OFF 스토퍼 확인을 먼저 마칩니다. 구동을 시작하거나 모드를 바꿀 때 목과 턱을 받칩니다. 프로그램을 닫으면 `HOLD`를 보내며 위치 유지에 토크를 계속 사용합니다. 다음 프로그램은 `--release`에서 `RELEASED`를 확인하고 실행합니다. [P03–P08 실물 시험](../spec/bench.md#b25-실물-시험)

```sh
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive
python control/pc/commission.py --serial /dev/ttyACM0 --release
python control/pc/jaw_clack.py --serial /dev/ttyACM0 --drive
python control/pc/commission.py --serial /dev/ttyACM0 --release
```

#### 동작 요약
- **추적과 복귀**: 얼굴 포착 시 눈이 먼저 두 눈 사이를 보고 약 **120 ms** 뒤 목이 따라갑니다. 얼굴을 놓치면 약 **2.5초** 유지 후 목이 초당 **10°** 목표로 정면 복귀합니다. 목 양축이 연속 2회 중립 ±0.5° 이내이면 위치를 유지합니다. 영점 목표에 도달한 뒤 5초 동안 실측 위치가 허용 범위에 들어오지 않으면 오류가 표시됩니다. `--immediate-hold`를 사용하면 얼굴을 놓칠 때 `HOLD`를 보내고 턱 토크는 켜지지 않습니다. [S01 합격 기준](../spec/requirements.md#동작-장면)
- **전시 모드 턱 유지·복구**: 시작 시 `R5B1_EXHIBIT_HOLD 1`을 확인합니다. 턱 보정이 있으면 ID6의 위치 P 게인 **1000**(일반/턱 시험은 400), Goal PWM 상한 **100**으로 닫힘을 유지합니다. 턱이 8틱을 넘게 열려 있으면 미리 확인한 무접촉 구간에서 목을 중립 ±11틱(약 1°)에 받친 채 시작합니다. 복구 입력은 최대 110틱(9.67°)이며 실제 시작 위치는 실측한 무접촉 구간 안에서 정합니다. 복구 중에는 PWM 상한 **120**과 **8.2°/s** 프로파일로 닫고 열림 12틱(1.05°) 이내에서 추적을 시작합니다. 2.4초에 도달하거나 목이 허용 범위 약 ±2°를 벗어나면 턱 토크를 끄고 구동을 잠급니다. 복구 결과가 나오기까지 USB 상태 출력은 멈추며 `HOLD`와 `RELEASE`는 계속 처리합니다.
- **턱 시험 모드 (`jaw_clack.py`)**: 목 두 축과 턱에 토크를 켜고 목 중립을 명령합니다. 240 ms 대기 후 턱 열림 2.75°와 5.5°를 각각 명령하고 닫습니다. 이 값은 제어 명령의 각도이며 5.5°는 ID6의 보정 끝점 `high`에 대응합니다. P06 인수 시험에는 `abs(high - zero) = 62`인 실측 보정이 필요합니다. 이때 두 목표는 31틱과 62틱(2.725°와 5.449°)입니다. 각 위치 보고와 새 턱 목표 직전에 목 양축의 중립 약 ±2°와 토크 ON을 확인합니다. 실패 시 턱 토크를 끄고 응답하는 목 축의 위치를 유지합니다. [P06 실물 시험](../spec/bench.md#p06-턱-구동과-복구)

## 구동 중 오류

OpenRB는 목표를 **60 ms**마다 보낼 수 있고 위치를 **120 ms**마다 보고합니다(57,600 bps, 여섯 축 동시 갱신 시 버스 점유 약 84%, 한 바퀴 토크 점검 주기 720 ms). CRC·응답 지연은 1회 재시도합니다. 구동 중 유효한 명령이 **400 ms** 동안 끊기면 현재 위치를 읽어 보정 범위 안에서 유지하고 토크를 계속 사용합니다. 읽은 위치가 보정 범위를 일반 8틱, 턱 5틱보다 더 벗어나거나 통신 오류가 이어지면 새 움직임을 잠급니다. 응답하는 축은 위치를 유지하고, 응답하지 않는 축에는 직전 목표가 남을 수 있습니다. [DYNAMIXEL Protocol 2.0](https://emanual.robotis.com/docs/en/dxl/protocol2/)

#### 주요 오류와 대처

| 오류 · 증상 | 원인 | 대처 순서 |
| --- | --- | --- |
| `*_CALIBRATION_RANGE` | 보정표가 축별 허용 틱(ID4 640 / ID5 149·30 / ID6 62)을 초과 | [Calibration.h](openrb/R5B1/Calibration.h) 범위를 줄이고 `check_calibration.py` 후 재업로드 |
| `JAW_FOLLOW_TIMEOUT` | 턱 목표 유지 600 ms 후 연속 2회 오차 초과(일반 8틱 / 전시 18틱) | 턱 간섭 확인. 턱 토크만 꺼지므로 `JAW_RELEASE_UNCONFIRMED` 시 토크 상태 재확인 |
| `RELEASE_UNCONFIRMED` | `--release` 중 모터 미응답·모델 불일치·알림 비트 잔존 | **목과 턱을 받친 채** 서보 전원을 분리합니다. 모터 알림의 원인을 제거한 뒤 아래 절차로 확인합니다. |
| OpenRB 재시작 후 뻣뻣함 | 모터 전원이 켜져 있으면 직전 목표를 계속 유지함 | 목을 받치고 `--check`의 `torque=` 확인 후 `--release` 실행 ([P07](../spec/bench.md#b25-실물-시험)) |
| 과부하·전압·과열 알림 비트 | 모터 하드웨어 오류 비트로 일반 읽기·해제 실패 | 원인 제거 → 목 받침 → `--release` → `--reboot ID` → 잠시 대기 → `--release`·`--check` |

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --reboot 6
python control/pc/commission.py --serial /dev/ttyACM0 --release
python control/pc/commission.py --serial /dev/ttyACM0 --check
```

> [!NOTE]
> Goal PWM은 XL330·XL430 위치 모드의 출력 상한이며, 펌웨어는 설정값을 다시 읽은 뒤 토크를 켭니다. 통신·설정이 계속 실패하면 Wizard에서 해당 모터를 단독 점검하세요. [XL330 제어표](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#goal-pwm100) · [XL430 제어표](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#goal-pwm100)
