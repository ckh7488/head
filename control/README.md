# 제어와 보정

Python 3.12로 저장소 루트에서 실행합니다. 첫 실행에 MediaPipe 모델을 내려받고 해시를 확인합니다.

```sh
python3.12 -m venv build/control-venv
. build/control-venv/bin/activate
python -m pip install -r control/pc/requirements.txt
python control/pc/track.py --source 0
```

동영상은 `--source path/to/video.mp4 --headless`로 확인합니다. 카메라 왜곡 보정은 `calibrate_camera.py --help`를 참고하고 결과 JSON을 `track.py --calibration`에 넣습니다.

## OpenRB와 모터

1. Arduino IDE에 ROBOTIS 보드 인덱스를 추가합니다. OpenRB-150 코어 **0.2.1**, Dynamixel2Arduino **0.8.2**로 `openrb/R5B1/R5B1.ino`를 빌드합니다. [보드 인덱스](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenRB-150/master/package_openrb_index.json) · [라이브러리](https://github.com/ROBOTIS-GIT/Dynamixel2Arduino)
2. Wizard에서 모터를 한 개씩 연결해 ID, Protocol 2.0, 57,600 bps, 위치 모드 3, 속도 기반 프로파일을 설정합니다. [Wizard 연결](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#using-dynamixel-wizard-20)
3. 토크를 끈 상태에서 아래 `--read`로 실물 위치의 엔코더 값을 읽어 `Calibration.h`에 넣고 다시 올립니다. 미보정 축은 구동이 잠깁니다.

| ID | 축 | `low, zero, high` 위치 |
|---|---|---|
| 1 | 눈 좌우 | 영상 왼쪽 20°, 중립, 오른쪽 20° |
| 2 | 눈 상하 | 위 8°, 중립, 아래 8° |
| 3 | 눈꺼풀 | 열림, 열림, 닫힘 |
| 4 | 목 좌우 | 영상 왼쪽 60°, 중립, 오른쪽 60° |
| 5 | 목 상하 | 들기 15°, 중립, 숙이기 6° |
| 6 | 턱 | 치아 여유를 둔 닫힘, 같은 닫힘, 열림 14° |

각 범위는 간섭이 없는 실물 위치로 줄일 수 있습니다. `--drive`는 한 축씩 시험합니다. 추적은 ID 1–5를 쓰고, 얼굴을 놓치거나 400 ms 동안 명령을 받지 않으면 현재 위치를 유지합니다. `--release` 전에는 목을 받칩니다. 아래 USB 포트는 환경에 맞게 바꿉니다.

```sh
python control/pc/commission.py --serial /dev/ttyACM0 --read 1
python control/pc/track.py --source 0 --serial /dev/ttyACM0 --drive --axes eye-yaw
python control/pc/jaw_clack.py --serial /dev/ttyACM0 --drive
python control/pc/commission.py --serial /dev/ttyACM0 --release
```
