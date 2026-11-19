# B5 보드 발주와 조립

| 보드 | 발주에 올릴 파일 | 제작 옵션 |
|---|---|---|
| [서보 허브 A1](servo-hub/R5_Servo_Hub.kicad_pro) | [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A1-Gerbers.zip) | 70 × 35 mm, **2층 FR-4 1.6 mm, 양면 2 oz**, 무연 HASL |
| [ESP32-C3 RF A1](c3-rf/C3_Antenna.kicad_pro) | [Gerber·드릴 ZIP](fabrication/C3_Antenna_A1-Gerbers.zip) | 34 × 53 mm, **4층 FR-4 1.6 mm, 외층 1 oz, 내층 0.5 oz**, ENIG |

각 ZIP을 별도 PCB 주문으로 넣습니다. RF 보드는 JLC04161H-7628 적층을 선택합니다. L1–L2 사이 0.2104 mm 조건에서 RF 선폭 0.36 mm, 양옆 GND 간격 0.20 mm, 아래 L2 GND로 50 Ω을 목표로 합니다. [JLC 적층표](https://jlcpcb.com/impedance)

허브는 전부 관통홀이고, C3는 윗면 실장입니다. C3 스텐실은 윗면 0.10 mm를 사용합니다. 칩 아래의 솔더마스크가 방열 비아를 덮고, 그 사이 네 곳에 납을 올립니다. C15–C18은 비우고 USB-C 고정 탭은 리플로우 뒤 납땜합니다. R1·R2의 기본 실장은 둘 다 0 Ω입니다. [허브 BOM](servo-hub/BOM.csv) · [C3 BOM](c3-rf/BOM.csv) · [C3 스텐실](fabrication/C3_Antenna_A1-Stencil.zip) · [C3 실장 좌표](fabrication/C3-front-positions-mm.csv)

## 전원과 배선

- 눈·눈꺼풀·턱은 **정전압 5 V 8 A** 어댑터를 사용합니다. 각 XL330의 5 V 정지 전류는 1.47 A이고 네 개 합은 5.88 A입니다. 목은 정전압 12 V급 5 A 어댑터를 쓰고, 허브 TP2 기준 실제 출력은 11.1~12.0 V로 맞춥니다. [XL330 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications) · [5 V 8 A 어댑터 예](https://spec.globtek.info/spec/?id=01ta0000007dRGUAA2&rohs_cert=1)
- 공통 전원선은 18 AWG, 케이블 고정부에서 전원 입력까지 편도 0.30 m 이내입니다. 개별 모터는 24 AWG로 배선하고, 커넥터에서 모터까지 편도 0.50 m 이내로 잡습니다. 5 V 어댑터 출력이 최대 부하에서 XT30 입구 기준 4.90 V일 때, PCB 선폭과 퓨즈·접점·케이블 손실을 넣은 계산은 5 V 모터 단자에서 최소 **4.26 V**입니다.

| 단자 | 연결 |
|---|---|
| J1 5 V 입력 | 패드 2는 +, 1은 GND. B5 외부 고정에는 XT30U를 사용 |
| J2 목 전원 입력 | 패드 1은 +, 2는 GND. B5 외부 고정에는 XT60U를 사용 |
| J3 OpenRB | OpenRB EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 턱 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 5 V와 목 전원은 GND·DATA를 공유하고 양극은 별도입니다. 모터를 빼고 두 입력을 각각 켜 TP1과 TP2를 TP3 기준으로 확인합니다. 전원을 끄고 번호를 붙인 모터선을 하나씩 꽂습니다. 첫 동작에서 저전압이나 통신 끊김이 보이면 해당 모터 단자와 입력 단자를 함께 잽니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

## C3 첫 동작

1. 5 V USB를 연결해 TP1–TP2에서 3.3 V를 확인합니다.
2. BOOT을 누른 채 RESET을 눌렀다 떼고 BOOT을 놓습니다. PC에서 ESP32-C3의 USB Serial/JTAG 포트와 플래시 ID를 확인합니다. [ESP32-C3 다운로드 모드](https://docs.espressif.com/projects/esptool/en/latest/esp32c3/advanced-topics/boot-mode-selection.html)
3. VNA로 안테나를 볼 때는 전원을 빼고 R1을 제거합니다. R1의 안테나 쪽 패드와 바로 옆 GND를 사용합니다. 인쇄 IFA라 ANT와 GND는 직류에서 연결됩니다. 케이스 안에서 쓰려면 장착 전후 S11을 각각 봅니다. [TI 인쇄 안테나 원본](https://www.ti.com/lit/an/swru120d/swru120d.pdf)

U2는 AP7361C 1 A SOT-223이며 GND 방열 탭에 비아를 배치했습니다. 데이터시트의 Wi-Fi 최대 송신 조건 335 mA, USB 5.25 V에서 손실은 약 0.67 W입니다. [레귤레이터 데이터시트](https://www.diodes.com/datasheet/download/AP7361C.pdf) · [ESP32-C3 데이터시트](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf)

## 재현

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 회로·PCB 검사와 BOM 대조 후 `build/electronics/`에 발주 파일을 생성합니다.

```sh
/usr/bin/python3 electronics/power_check.py
/usr/bin/python3 electronics/export.py servo-hub
/usr/bin/python3 electronics/export.py c3-rf
```
