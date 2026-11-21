# 서보 허브와 ESP32-C3

서보 허브 A2와 C3 A1 시제품의 검토용 제작 자료입니다. 허브 전원 여유와 분기 보호, 실물 전원·구동 확인 결과가 발주 판정에 남아 있습니다.

| 보드 | 제작 파일 | 제작 옵션 |
|---|---|---|
| [서보 허브 A2](servo-hub/R5_Servo_Hub.kicad_pro) | [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A2-Gerbers.zip) | 70 × 35 mm, **2층 FR-4 1.6 mm, 양면 2 oz**, 무연 HASL |
| [ESP32-C3 RF A1](c3-rf/C3_Antenna.kicad_pro) | [Gerber·드릴 ZIP](fabrication/C3_Antenna_A1-Gerbers.zip) | 34 × 53 mm, **4층 FR-4 1.6 mm, 외층 1 oz, 내층 0.5 oz**, ENIG |

허브 A2에서 J1과 J3–J6의 도금홀 주변 동박 최소 폭을 0.30 mm로 늘렸습니다. 부품 위치와 홀 지름은 동일합니다. 세 풋프린트는 KiCad 공식 라이브러리를 수정했습니다. [제작 한계](https://jlcpcb.com/capabilities/pcb-capabilities/) · [KiCad 라이브러리 라이선스](https://www.kicad.org/libraries/license/)

RF 보드는 JLC04161H-7628 적층을 선택합니다. L1–L2 사이 0.2104 mm 조건에서 RF 선폭 0.36 mm, 양옆 GND 간격 0.20 mm, 아래 L2 GND로 50 Ω을 목표로 합니다. [JLC 적층표](https://jlcpcb.com/impedance)

허브는 전부 관통홀입니다. C3의 SMT 부품은 윗면에 실장합니다. C3 스텐실은 윗면 0.10 mm를 사용합니다. 칩 아래의 솔더마스크가 방열 비아를 덮고, 그 사이 네 곳에 납을 올립니다. C15–C18은 비웁니다. USB-C J1과 UART J2는 실장 좌표에서 제외합니다. 리플로우 뒤 J1의 전기 단자 16개와 고정 탭 4개, J2의 단자 3개를 관통홀로 납땜합니다. R1·R2의 기본 실장은 둘 다 0 Ω입니다. [허브 BOM](servo-hub/BOM.csv) · [C3 BOM](c3-rf/BOM.csv) · [C3 스텐실](fabrication/C3_Antenna_A1-Stencil.zip) · [C3 실장 좌표](fabrication/C3-front-positions-mm.csv)

## 전원과 배선

- 눈·눈꺼풀·턱은 **정전압 5 V 8 A** 어댑터를 사용합니다. 각 XL330의 5 V 정지 전류는 1.47 A이고 네 개 합은 5.88 A입니다. 목은 정전압 12 V급 5 A 어댑터를 쓰고, 허브 TP2 기준 실제 출력은 11.1~12.0 V로 맞춥니다. [XL330 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications) · [5 V 8 A 어댑터 예](https://spec.globtek.info/spec/?id=01ta0000007dRGUAA2&rohs_cert=1)
- 공통 전원선은 18 AWG, 고정부에서 전원 입력까지 편도 0.30 m 이내입니다. XT60U의 12 AWG 꼬리는 양쪽 각 50 mm를 기준으로 삼습니다. 분기에서 각 모터 단자까지 24 AWG 기준 편도 0.50 m 이내입니다. 외부 5 V 배선으로 들어가는 어댑터 출력이 최대 부하에서 4.95 V일 때, 전선 70 °C와 PCB·퓨즈·접점 손실을 넣어 계산한 5 V 모터의 최저 전압은 **4.27 V**입니다. 목 전원 입력을 11.10 V로 놓은 계산은 **10.62 V**입니다. 예시 어댑터의 허용 하한 4.75 V에서는 J5·J6가 **4.07 V**로 내려가며 깜빡임 시험 모델의 전압 범위를 벗어납니다. [전선 품번과 조립 순서](../mechanical/ASSEMBLY.md#배선)

| 단자 | 연결 |
|---|---|
| J1 5 V 입력 | 패드 2는 +, 1은 GND. 기판 XT30PW-M에는 W3/W4의 XT30U-F가 연결 |
| J2 목 전원 입력 | 패드 1은 +, 2는 GND. B5 외부 고정에는 XT60U를 사용 |
| J3 OpenRB | OpenRB EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 턱 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

5 V 배선에는 XT30U-F 두 개와 XT30U-M 한 개가 필요합니다. F 한 개는 어댑터에, 다른 한 개는 허브 J1 쪽 W3/W4에 씁니다. OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 5 V와 목 전원은 GND·DATA를 공유하고 양극은 별도입니다. 모터를 빼고 두 입력을 각각 켜 TP1과 TP2를 TP3 기준으로 확인합니다. 전원을 끄고 번호를 붙인 모터선을 하나씩 꽂습니다. 첫 동작에서 저전압이나 통신 끊김이 보이면 해당 모터 단자와 입력 단자를 함께 잽니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

5 V의 J4–J6에 있는 각 JST PH 단자는 24 AWG에서 2 A 정격입니다. 공용 5 A 퓨즈는 합계 전류가 5 A 미만인 단일 분기 과부하를 차단한다고 볼 수 없습니다. 전원을 실제 사용할 어댑터와 배선으로 묶은 뒤 모터 단자 전압과 분기 보호를 검수합니다. [JST PH 정격](https://www.jst-mfg.com/product/pdf/eng/ePH.pdf)

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

`/usr/bin/python3 electronics/power_check.py --input-5v 4.75`는 해당 전압 모델을 실행합니다. 현재 배선의 분석 한계 4.25 V를 밑도는 출력을 보고하고 종료 코드 1을 반환합니다.
