# 제어와 보정

Python 3.12로 저장소 루트에서 실행합니다. 첫 실행에 MediaPipe 모델을 내려받고 해시를 확인합니다.

```sh
python3.12 -m venv build/control-venv
. build/control-venv/bin/activate
python -m pip install -r control/pc/requirements.txt
python control/pc/track.py --source 0
```

동영상은 `--source path/to/video.mp4 --headless`로 확인합니다. U20CAM-1080P-S1의 문서상 수평 화각은 106°입니다. 설치한 카메라를 보정할 때는 `calibrate_camera.py`의 결과 JSON을 `track.py --calibration`에 넣습니다. [카메라 매뉴얼](https://github.com/INNO-MAKER/U20CAM-1080P-S1)

## OpenRB와 모터

1. Arduino IDE에 ROBOTIS 보드 인덱스를 추가합니다. OpenRB-150 코어 **0.2.1**, Dynamixel2Arduino **0.8.2**로 `openrb/R5B1/R5B1.ino`를 빌드합니다. [보드 인덱스](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenRB-150/master/package_openrb_index.json) · [라이브러리](https://github.com/ROBOTIS-GIT/Dynamixel2Arduino)
2. Wizard에서 모터를 한 개씩 연결해 ID, Protocol 2.0, 57,600 bps, 위치 모드 3, 속도 기반 프로파일, Status Return Level 2를 설정합니다. Drive Mode의 Goal Update 자동 토크 활성화는 끄고, Startup Configuration은 0(시작 시 토크와 RAM 복구 끔)으로 둡니다. [Wizard 연결](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#using-dynamixel-wizard-20) · [Drive Mode](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drive-mode10) · [Startup Configuration](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#startup-configuration60)
3. 토크를 끈 상태에서 아래 `--read`로 실물 위치의 엔코더 값을 읽어 `Calibration.h`에 넣고 다시 올립니다. `--check`는 6축의 모델, 설정, 현재 위치와 토크를 읽습니다. 미보정 축은 구동이 잠깁니다.

| ID | 축 | `low, zero, high` 위치 |
|---|---|---|
| 1 | 눈 좌우 | 영상 왼쪽 20°, 중립, 오른쪽 20° |
| 2 | 눈 상하 | 위 8°, 중립, 아래 8° |
| 3 | 눈꺼풀 | 열림, 열림, 닫힘 |
| 4 | 목 좌우 | 영상 왼쪽 60°, 중립, 오른쪽 60° |
| 5 | 목 상하 | 들기 15°, 중립, 숙이기 6° |
| 6 | 턱 | 치아 여유를 둔 닫힘, 같은 닫힘, 닫힘 기준에서 열림 13° |

각 범위는 간섭이 없는 실물 위치로 줄일 수 있습니다. `--drive`로 한 축씩 시험할 수 있습니다. `check_calibration.py --nominal-neck`은 목의 위 표 각도를 그대로 목표로 잡았을 때만 사용합니다. 목 엔코더의 4096틱/회전을 기준으로 실제 각도 범위를 대조합니다.

`jaw_clack.py`는 턱을 켜기 직전에 보드에 올린 보정값으로 목 두 축의 위치가 중립에서 ±2° 이내인지 확인합니다. 턱 시험 동안 목을 중립에 받쳐 둡니다. 이 확인은 시작할 때의 자세에 한합니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --read 1
python control/pc/check_calibration.py
python control/pc/commission.py --serial /dev/ttyACM0 --check
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive --axes eye-yaw
python control/pc/jaw_clack.py --serial /dev/ttyACM0 --drive
python control/pc/commission.py --serial /dev/ttyACM0 --release
```

## 구동 중 오류

OpenRB는 최신 목표를 60 ms마다 보낼 수 있고 위치는 120 ms마다 보고합니다. 다섯 축의 목표를 30 Hz로 전부 갱신하던 조건은 요청·응답과 반환 지연만 합쳐도 57,600 bps의 약 109%였습니다. 새 주기는 여섯 축이 동시에 바뀌어도 같은 계산으로 약 80%입니다. [DYNAMIXEL Protocol 2.0](https://emanual.robotis.com/docs/en/dxl/protocol2/)

CRC나 응답 지연은 한 번 재시도합니다. 문제가 계속되거나 실제 위치가 보정 범위를 8틱 넘게 벗어나면 새 움직임을 잠그고, 응답하는 축에는 현재 위치를 보정 범위 안에서 잡습니다. 통신이 끊긴 축에는 마지막 목표가 남을 수 있습니다. 추적이 얼굴을 놓치거나 유효한 명령이 400 ms 동안 없을 때도 현재 위치를 잡습니다. `--release` 전에는 목을 받칩니다. OpenRB가 제어 중이던 축의 Torque Enable이 0으로 읽히면 `RELEASED`가 표시됩니다.

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
