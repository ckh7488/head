# KiCad 9

| 프로젝트 | 제작 조건 |
|---|---|
| [서보 허브](servo-hub/R5_Servo_Hub.kicad_pro) · [BOM](servo-hub/BOM.csv) | 70 × 35 mm, 2층 FR-4 1.6 mm, 외층 2 oz, 무연 HASL |
| [ESP32-C3 안테나](c3-rf/C3_Antenna.kicad_pro) · [BOM](c3-rf/BOM.csv) | 34 × 53 mm, 4층 1.6 mm, ENIG. JLC04161H-7628의 L1–L2 0.2104 mm와 50 Ω 선폭 0.36 mm 기준 |

## 허브 배선

| 단자 | 연결 |
|---|---|
| J1 | 5 V 입력. 패드 2가 +, 1이 GND |
| J2 | 목 전원 11.1~12.0 V 입력. 패드 1이 +, 2가 GND |
| J3 | OpenRB DXL의 EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 | 5 V 어댑터에서 **2 A 퓨즈**로 별도 분기. GND와 DATA는 J6과 공통 |

OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 허브는 GND와 DATA를 공유하며 5 V와 목 전원의 양극 레일을 분리합니다. 모터를 빼고 각 입력을 따로 켜 TP1·TP2를 TP3 기준으로 측정한 뒤, 모터를 한 개씩 연결합니다. 여러 축이 함께 움직일 때 ID 6을 포함한 5 V 단자 전압을 잽니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

## 제작 데이터 내보내기

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 출력은 `build/electronics/`에 생성합니다.

```sh
/usr/bin/python3 electronics/export.py servo-hub
/usr/bin/python3 electronics/export.py c3-rf
```

C3에서 C15–C18은 미실장이라 스텐실에서도 제외합니다. 좌표 CSV에는 USB-C가 포함되며 J2는 손납땜입니다. 발주 전 실제 적층과 50 Ω 조건을 확인합니다. 안테나 S11을 볼 때는 R1을 비우고 R2에 0 Ω을 두어 ANT와 인접 GND에 VNA를 연결합니다. [적층 안내](https://jlcpcb.com/impedance) · [안테나 형상](https://www.ti.com/lit/an/swru120d/swru120d.pdf)
