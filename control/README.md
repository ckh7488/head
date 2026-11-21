# 제어와 보정

Python 3.12로 저장소 루트에서 실행합니다. 첫 실행에 MediaPipe 모델을 내려받고 해시를 확인합니다.

```sh
python3.12 -m venv build/control-venv
. build/control-venv/bin/activate
python -m pip install -r control/pc/requirements.txt
python control/pc/track.py --source 0
```

동영상은 `--source path/to/video.mp4 --headless`로 확인합니다. U20CAM-1080P-S1의 문서상 수평 화각은 106°입니다. 설치한 카메라를 보정할 때는 `calibrate_camera.py`의 결과 JSON을 `track.py --calibration`에 넣습니다. [카메라 매뉴얼](https://github.com/INNO-MAKER/U20CAM-1080P-S1)

눈·목·눈꺼풀 5축을 켠 추적이 기본입니다. 얼굴을 포착하면 눈이 먼저 두 눈 사이를 보고 약 120 ms 뒤에 목이 따라갑니다. 얼굴을 놓치면 약 2.5초간 자세를 유지하고, 계속 얼굴이 보이지 않으면 목을 초당 10° 목표로 정면에 복귀시킵니다. 얼굴이 다시 들어오면 추적을 재개합니다. 보정 중 얼굴을 놓쳤을 때 그 자리에서 정지하려면 `--immediate-hold`를 사용합니다. [S01 합격 기준](../spec/requirements.md#동작-장면)

## OpenRB와 모터

1. Arduino IDE에 ROBOTIS 보드 인덱스를 추가합니다. OpenRB-150 코어 **0.2.1**, Dynamixel2Arduino **0.8.2**로 `openrb/R5B1/R5B1.ino`를 빌드합니다. [보드 인덱스](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenRB-150/master/package_openrb_index.json) · [라이브러리](https://github.com/ROBOTIS-GIT/Dynamixel2Arduino)
2. Wizard에서 모터를 한 개씩 연결해 ID, Protocol 2.0, 57,600 bps, 위치 모드 3, 속도 기반 프로파일, Status Return Level 2를 설정합니다. Drive Mode의 Goal Update 자동 토크 활성화는 끄고, Startup Configuration은 0(시작 시 토크와 RAM 복구 끔)으로 둡니다. [Wizard 연결](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#using-dynamixel-wizard-20) · [Drive Mode](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drive-mode10) · [Startup Configuration](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#startup-configuration60)
3. 토크를 끈 상태에서 아래 `--read`로 실물 위치의 엔코더 값을 읽어 `Calibration.h`에 넣고 다시 올립니다. `--check`는 6축의 모델, 설정, 현재 위치와 토크를 읽습니다. 보정이 비어 있거나 Startup Configuration이 0이 아니면 구동이 잠깁니다.

전시 추적을 시작할 때 PC가 OpenRB의 `R5B1_EXHIBIT_HOLD 1` 응답을 확인합니다. 턱 보정이 되어 있으면 ID 6은 닫힘 위치를 PWM 상한 100으로 유지합니다. 턱 보정이 비어 있으면 안내를 표시하고 눈·목·눈꺼풀만 구동합니다. 이전 펌웨어에서는 `--immediate-hold`로 기존 5축 모드를 쓸 수 있습니다. 이 모드는 얼굴을 놓친 자리에서 멈추며 턱 토크는 켜지지 않습니다.

전원을 켤 때 턱이 열려 있으면 목을 중립 가까이 받칩니다. 목 양축이 약 ±1° 이내이고 턱 위치가 복구 입력 범위인 110틱(약 9.67°) 이내이면 PWM 상한 120과 8.2°/s 프로파일로 닫힘을 회복합니다. 복구 목표는 닫힘 영점입니다. 실물 시험은 스토퍼가 허용하는 범위에서 시작합니다.

전시 모드는 ID6의 위치 P 게인을 1000으로 써서 다시 읽고 확인합니다. 턱 시연과 일반 구동에서는 기본값 400으로 되돌립니다. 실제 턱 위치가 닫힘에서 열린 쪽으로 약 1.05° 이내에 들어오면 PWM 상한 100을 확인한 뒤 얼굴 추적을 시작합니다. 닫힘 방향 피드백 한계는 영점에서 5틱입니다. 복구 목표도 보정한 닫힘 영점입니다. 2.4초 안에 회복하지 못하거나 도중에 목이 ±2°를 벗어나면 새 움직임을 잠그고 턱 토크만 끕니다. 복구 도중 USB 상태 출력은 멈추며 `HOLD`와 `RELEASE`는 계속 처리합니다. 명령 스트림이 끊기면 응답하는 목 위치를 유지합니다. 전원이 끊길 때 턱의 열림은 기계식 스토퍼가 제한합니다.

정면 복귀의 마지막 구간은 새 위치 보고를 받아 목의 작은 정지 오차를 줄입니다. 목 두 축이 두 번 연속으로 중립에서 ±0.5° 이내에 들어오면 찾은 목표를 유지합니다. 영점 목표를 보낸 뒤 5초 안에 도달하지 못하면 오류를 표시하고 현재 위치를 잡습니다.

| ID | 축 | `low, zero, high` 위치 |
|---|---|---|
| 1 | 눈 좌우 | 영상 왼쪽, 중립, 오른쪽 (양쪽 219틱 이내) |
| 2 | 눈 상하 | 위, 중립, 아래 (양쪽 83틱 이내) |
| 3 | 눈꺼풀 | 열림, 열림, 닫힘 (최대 1,024틱) |
| 4 | 목 좌우 | 영상 왼쪽, 중립, 오른쪽 (양쪽 659틱, 약 57.92° 이내) |
| 5 | 목 상하 | 들기 최대 13.62°(155틱 이내), 중립, 숙이기 최대 2.99°(34틱 이내) |
| 6 | 턱 | 치아 여유를 둔 닫힘, 같은 닫힘, 닫힘에서 최대 62틱 열림(엔코더 환산 각도 5.449°) |

각 범위는 간섭이 없는 실물 위치로 줄일 수 있습니다. `--drive`로 한 축씩 시험할 수 있습니다. `check_calibration.py --nominal-neck`은 목을 보정표의 끝까지 사용하도록 잡았을 때만 사용합니다. 목 엔코더의 4096틱/회전을 기준으로 실제 각도 범위를 대조합니다.

62틱을 넘는 턱 보정은 `JAW_CALIBRATION_RANGE`로, 0~5.5°의 명령 범위를 벗어난 목표는 `JAW_GOAL_RANGE`로 거부합니다. `GO`의 5.5°는 보정한 열림 끝점에 대응합니다. 62틱의 엔코더 환산 각도는 5.449°이고, 피드백 5틱을 포함하면 67틱(5.889°)입니다. B25의 CAD에서 같은 조건으로 턱 앞끝은 5.27 mm 내려갑니다. [B25 스토퍼 검사](jaw-opening-check.json)

실물의 닫힘 영점과 첫 열림 접촉점을 토크를 끈 상태에서 읽습니다. Goal PWM 제한을 확인한 직결 턱의 62틱 보정은 피드백 5틱과 1° 여유를 포함해 첫 접촉까지 최소 79틱이 필요합니다. 실제 하강량과 끝점 간극을 따로 기록합니다. [고정 검사 조건](../spec/conditions.md#6-동작-범위) · [실물 시험](../spec/bench.md#b25-실물-시험)

목 상하축은 들기 쪽 보정 폭이 155틱을 넘거나 숙이는 쪽이 34틱을 넘으면 `PITCH_CALIBRATION_RANGE`로 구동을 잠급니다. 이전 6° 숙임 보정값은 실물에서 다시 보정합니다.
눈 좌우와 상하는 중립에서 양 끝을 각각 219틱과 83틱 안에 보정합니다. 이 범위에 위치 오차 8틱을 더해도 CAD에서 검사한 ±20°와 ±8° 안에 들어갑니다.
목 좌우는 중립에서 양쪽 659틱으로 제한합니다. 위치 오차 8틱을 포함한 피드백 허용 범위는 ±58.62°입니다. 이전 보정값이 659틱을 넘으면 `YAW_CALIBRATION_RANGE`로 구동을 잠급니다. PC 명령과 상태의 목 좌우 ±60은 보정 양 끝에 대응합니다.

`jaw_clack.py`는 턱 시험 전용 모드로 목 두 축과 턱에만 토크를 켭니다. 목에 보정 중립을 명령하고 240 ms 기다린 뒤 2.75°와 5.5°를 각각 명령하고 닫습니다. 62틱으로 보정했을 때 두 열림 목표는 31틱과 62틱(2.725°와 5.449°)입니다. 매 위치 보고와 새 턱 목표 직전에 목 위치가 ±2° 안에 있고 두 축의 토크가 켜졌는지 확인합니다. 확인에 실패하면 턱 토크를 끄고 응답하는 목 축의 위치를 유지합니다. 추적 중 간헐적으로 턱을 여는 동작은 목·턱을 함께 움직이는 조건을 별도로 검증한 뒤 적용합니다.

시험을 시작할 때까지 목을 중립에 받칩니다. 시험이 끝나면 목은 정지 위치를 유지하기 위해 토크를 사용합니다. 목을 다시 받친 뒤 `--release`로 토크를 끕니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --read 1
python control/pc/check_calibration.py
python control/pc/commission.py --serial /dev/ttyACM0 --check
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive --axes eye-yaw
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive
python control/pc/jaw_clack.py --serial /dev/ttyACM0 --drive
python control/pc/commission.py --serial /dev/ttyACM0 --release
```

## 구동 중 오류

OpenRB는 최신 목표를 60 ms마다 보낼 수 있고 위치는 120 ms마다 보고합니다. 다섯 축의 목표를 30 Hz로 전부 갱신하던 조건은 요청·응답과 반환 지연만 합쳐도 57,600 bps의 약 109%였습니다. 구동 중 위치 보고마다 한 축의 토크 상태를 순서대로 확인합니다. 여섯 축의 목표가 모두 바뀌는 일반 구동에서 버스 점유 추정치는 약 84%이며, 여섯 축 토크를 한 바퀴 확인하는 명목 주기는 720 ms입니다. [DYNAMIXEL Protocol 2.0](https://emanual.robotis.com/docs/en/dxl/protocol2/)

CRC나 응답 지연은 한 번 재시도합니다. 문제가 계속되거나 실제 위치가 보정 범위를 8틱(턱은 5틱) 넘게 벗어나면 새 움직임을 잠그고, 응답하는 축에는 현재 위치를 보정 범위 안에서 잡습니다. 통신이 끊긴 축에는 마지막 목표가 남을 수 있습니다. 유효한 명령이 400 ms 동안 없을 때는 읽은 위치를 보정 범위 안으로 제한하고 서보의 목표 레지스터를 다시 읽어 확인합니다. 토크가 꺼진 축을 확인하면 오류를 내고 남은 축의 움직임을 중단합니다. `--release` 전에는 목을 받칩니다. OpenRB를 재시작한 뒤에도 `--release`는 ID 1–6의 모델과 토크를 확인합니다. 모든 대상의 토크를 0으로 확인하면 `RELEASED`를 표시합니다. 모터가 빠져 있거나 모델과 토크 확인에 실패하면 `RELEASE_UNCONFIRMED`가 표시되고 새 구동을 잠급니다. 부분 조립을 정비할 때는 목을 받친 뒤 서보 전원을 차단합니다.

턱 목표가 600 ms 유지된 뒤 오차가 일반 구동과 턱 시험에서는 8틱(약 0.70°), 전시 추적에서는 18틱(약 1.58°)을 넘는 위치 보고가 두 번 연속이면 `JAW_FOLLOW_TIMEOUT`을 표시합니다. 턱 토크만 끄고 확인하며, 다른 축은 현재 위치를 유지합니다. 턱 토크가 꺼지면 턱이 움직일 수 있습니다. `JAW_RELEASE_UNCONFIRMED`가 뜨면 토크 상태를 확인해야 합니다. 이 검사는 지속적인 위치 오차를 감지합니다. 짧거나 위치 오차가 작은 접촉을 감지하려면 별도 센서와 실물 시험이 필요합니다.

모터가 과부하·전압·과열 오류를 기록하면 상태 응답에 알림 비트가 붙어 일반 위치·토크 확인이 실패할 수 있습니다. 오류 원인을 없애고 목을 받친 뒤 `--reboot`에 해당 ID를 지정합니다. OpenRB는 그 모터의 모델, Startup Configuration 0, Torque Enable 0을 직접 확인합니다. 구동 중 오류로 멈춘 축은 해당 ID의 알림이 새 응답에도 있을 때만 재부팅합니다.

토크가 켜져 있으면 목을 받친 상태에서 `--release`를 먼저 실행합니다. 알림이 남아 있으면 `ERROR RELEASE_UNCONFIRMED`가 나올 수 있습니다. 이때 `--reboot`는 토크를 다시 읽어 확인합니다. 통신이나 설정 확인이 계속 실패하면 Wizard에서 해당 모터를 점검합니다. 재부팅 응답을 받으면 모터가 다시 켜질 때까지 잠깐 기다린 뒤 `--release`와 `--check`를 실행합니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --reboot 6
python control/pc/commission.py --serial /dev/ttyACM0 --release
python control/pc/commission.py --serial /dev/ttyACM0 --check
```

Goal PWM은 XL330·XL430 위치 모드의 출력 PWM 상한입니다. 펌웨어는 설정값을 다시 읽은 뒤 토크를 켭니다. 실제 정지 토크와 하중은 조립 상태에서 측정하는 값입니다. [XL330 제어표](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#goal-pwm100) · [XL430 제어표](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#goal-pwm100)

## 하드웨어 없이 실행

저장소 루트에서 C++ 컴파일러와 Python으로 실행합니다. 가상 USB 연동은 Linux·macOS·WSL에서 실행됩니다.

```sh
python -m pip install -r tests/requirements.txt
python -m pytest
```
