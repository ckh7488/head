# 서보 허브와 ESP32-C3

서보 허브 A3와 C3 A1 시제품의 검토용 제작 자료입니다. A3 전원은 회로·PCB 검사와 부하 계산을 통과했습니다. 실물 전압·고장 보호·구동 검수 뒤 발주를 판정합니다.

| 보드 | 제작 파일 | 제작 옵션 |
|---|---|---|
| [서보 허브 A3](servo-hub/R5_Servo_Hub.kicad_pro) | [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A3-Gerbers.zip) | 70 × 35 mm, **2층 FR-4 1.6 mm, 양면 2 oz**, ENIG |
| [ESP32-C3 RF A1](c3-rf/C3_Antenna.kicad_pro) | [Gerber·드릴 ZIP](fabrication/C3_Antenna_A1-Gerbers.zip) | 34 × 53 mm, **4층 FR-4 1.6 mm, 외층 1 oz, 내층 0.5 oz**, ENIG |

허브 A3는 J4–J6 앞에 전류 제한기 세 개를 넣고, 공용 퓨즈 F1을 7.5 A로 바꿨습니다. 기존 커넥터, 장착홀과 0.30 mm 도금홀 동박 링은 유지했습니다. B24 CAD에 새 밑면 부품의 1.40 mm 높이와 평면 공차를 포함한 상자를 놓은 결과, 덮개와 최소 **1.46 mm** 떨어졌습니다. 커넥터와 VSON 풋프린트는 KiCad 공식 라이브러리를 수정했습니다. [제작 한계](https://jlcpcb.com/capabilities/pcb-capabilities/) · [KiCad 라이브러리 라이선스](https://www.kicad.org/libraries/license/)

RF 보드는 JLC04161H-7628 적층을 선택합니다. L1–L2 사이 0.2104 mm 조건에서 RF 선폭 0.36 mm, 양옆 GND 간격 0.20 mm, 아래 L2 GND로 50 Ω을 목표로 합니다. [JLC 적층표](https://jlcpcb.com/impedance)

허브 U1–U3, R4–R6, C3–C5는 밑면에 먼저 리플로우합니다. VSON 접지 패드의 접합을 검사한 뒤 윗면 관통홀 부품을 납땜합니다. [허브 밑면 스텐실](fabrication/R5_Servo_Hub_A3-Stencil.zip) · [허브 밑면 실장 좌표](fabrication/R5-hub-back-positions-mm.csv)

C3 RF 보드의 SMT 부품은 윗면에 실장합니다. C3 스텐실은 윗면 0.10 mm를 사용합니다. 칩 아래의 솔더마스크가 방열 비아를 덮고, 그 사이 네 곳에 납을 올립니다. C15–C18은 비웁니다. USB-C J1과 UART J2는 실장 좌표에서 제외합니다. 리플로우 뒤 J1의 전기 단자 16개와 고정 탭 4개, J2의 단자 3개를 관통홀로 납땜합니다. R1·R2의 기본 실장은 둘 다 0 Ω입니다. [허브 BOM](servo-hub/BOM.csv) · [C3 BOM](c3-rf/BOM.csv) · [C3 스텐실](fabrication/C3_Antenna_A1-Stencil.zip) · [C3 실장 좌표](fabrication/C3-front-positions-mm.csv)

## 전원과 배선

- 기준 전원은 **SIGLENT SPD1168X**, 20–30 °C, 로컬 센스, 정전압 **5.21 V**, 전류 상한 **7.50 A**입니다. 설정 오차, 입력·부하 변동과 3 mV 리플을 합쳐 출력 단자에서 **5.17–5.25 V**를 사용했습니다. 16 AWG 전원 꼬리 W33·W34는 각 250 mm 이내입니다. 전원 본체는 받침 바깥에 둡니다. 국내 표시가는 약 **₩454,300**으로, 사용 가능한 계측기를 우선 연결할 수 있습니다. [SIGLENT 사양과 시험 방법](https://siglentna.com/wp-content/uploads/dlm_uploads/2023/04/SPD1000X-Series-Service-Manual_E01B.pdf) · [국내 판매 페이지](https://siglentkorea.com/product/siglent-%EC%8B%9C%EA%B8%80%EB%9F%B0%ED%8A%B8-spd1168x-programmable-dc-power-supply-%ED%8C%8C%EC%9B%8C%EC%84%9C%ED%94%8C%EB%9D%BC%EC%9D%B4-%EC%A0%84%EC%9B%90%EA%B3%B5%EA%B8%89%EA%B8%B0-128w-1/88/) · [전선 재단표](../mechanical/WIRING-CUT-LIST.csv)
- 5 V 부하 계산에는 네 XL330에 각각 **1.55 A**, 허브 보조 부하 10 mA, 두 목 XL430에 각각 **1.40 A**를 적용했습니다. XL330 제조사 값은 5.00 V에서 1.47 A, 6.00 V에서 1.74 A이며, 5.25 V에서 선형 보간한 약 1.54 A보다 큰 값을 사용했습니다. WAGO 분기 전 공통선은 6.21 A, W3·W4와 F1은 4.66 A를 반영했습니다. 70 °C 전선, 수명 후 접점, 퓨즈와 스위치, PCB 트랙과 비아를 포함했습니다. [XL330-M077 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [XL330-M288 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications) · [전압 계산](power_check.py)
- 5.17 V 전원과 목 전원 입력 11.10 V에서 모터 단자 하한은 J4 **4.334 V**, J5 **4.325 V**, J6 **4.341 V**, 턱 **4.621 V**, 목 J7 **10.730 V**, J8 **10.647 V**입니다. XL330 단자 계산은 기존 하중 모델의 4.27–5.25 V 안에 듭니다. 종전 전원 허용 하한 4.75 V를 넣으면 네 XL330 모두 4.27 V 미만입니다. 목은 별도 정전압 12 V급 5 A 전원을 씁니다. [눈꺼풀 부하 모델](../mechanical/revisions/b24/blink-loaded.json)
- 받침 외부의 소형 전원을 검토할 때는 정전압 영역, 8 A급 연속 정격과 아래 실물 검수 조건을 사용합니다. 예를 들어 12 V 입력 DIN형 **Phoenix Contact 2905007**은 5–18 V 조정과 8 A 정격을 제공하지만, 공개된 부하 변동 1% 미만은 10–100% 조건이며 리플은 20 mVpp 미만입니다. 5.17–5.25 V의 전체 운전 범위는 별도 검증이 필요합니다. [Phoenix Contact 데이터시트](https://www.phoenixcontact.com/en-us/products/dcdc-converters-quint-ps12dc12dc8-2905007?type=pdf)

| 단자 | 연결 |
|---|---|
| J1 5 V 입력 | 패드 2는 +, 1은 GND. 기판 XT30PW-M에는 W3/W4의 XT30U-F가 연결 |
| J2 목 전원 입력 | 패드 1은 +, 2는 GND. B5 외부 고정에는 XT60U를 사용 |
| J3 OpenRB | OpenRB EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **개별 전류 제한 5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 턱 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

5 V 배선에는 XT30U-F 두 개와 XT30U-M 한 개가 필요합니다. F 한 개는 5 V 전원 꼬리에, 다른 한 개는 허브 J1 쪽 W3/W4에 씁니다. OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 5 V와 목 전원은 GND·DATA를 공유하고 양극은 별도입니다. 모터를 빼고 두 입력을 각각 켜 TP1과 TP2를 TP3 기준으로 확인합니다. 전원을 끄고 번호를 붙인 모터선을 하나씩 꽂습니다. 첫 동작에서 저전압이나 통신 끊김이 보이면 해당 모터 단자와 입력 단자를 함께 잽니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

J4–J6는 각각 TPS2557과 지정 61.9 kΩ, 0.1%, 25 ppm/°C 저항을 사용합니다. 정상 정지 전류 계산값 1.55 A보다 높고, 24 AWG PH의 2 A 연속 정격보다 낮은 **1.585–1.997 A** 제한 범위입니다. 제한기는 과부하 중 전류를 줄이며 과열 시 차단 후 자동 복귀합니다. 데이터시트의 단락 응답 3.5 µs는 일반값입니다. 공용 F1은 허브 입력에 있으며 턱의 별도 2 A 인라인 퓨즈도 사용합니다. [TPS2557 특성·허용 오차](https://www.ti.com/lit/ds/symlink/tps2557.pdf) · [JST PH](https://www.jst.com/wp-content/uploads/2025/06/ePH.pdf) · [JST EH](https://jst.es/wp-content/uploads/2025/06/eh-connector.pdf) · [MINI 퓨즈](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_297_mini32v.pdf?assetguid=42c9dd21-a88e-4328-8e67-2f832444faf1)

### 전원 실물 검수

1. 모터를 빼고 네 5 V 모터 단자에 전자부하를 연결합니다. 전원 본체 출력에서 무부하부터 6.21 A까지 **5.17–5.25 V**인지 확인합니다. 전자부하를 각 1.55 A로 맞추고, 목의 두 단자에도 각 1.40 A를 걸어 동시에 측정합니다. 전원 단자와 각 모터 커넥터의 GND를 기준으로 잽니다.
2. 정상 부하에서 5 V 모터 단자 **4.27–5.25 V**, 목 모터 단자 **10.50 V 이상**을 확인합니다. 냉간과 충분히 따뜻해진 상태에서 전원 투입·부하 변화·동시 구동 파형을 기록합니다. 전원 단자·외부 XT30·WAGO 접점에 배정한 12 mΩ, J1 4 mΩ, 설치된 F1 홀더와 퓨즈 35 mΩ, 턱 퓨즈 및 홀더 110 mΩ은 접점과 배선 온도를 반영해 전압 강하로 대조합니다.
3. J4–J6를 한 개씩 전자부하로 과부하시키고, 해당 PH의 정상 1.55 A 통과 및 제한 동작 중 연속 2.00 A 미만을 확인합니다. 다른 5 V 분기에 정상 부하를 둔 상태에서 차단·복구, 전류 피크와 셸 온도를 기록합니다. 이후 실제 모터를 연결해 동작을 확인합니다.

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

`/usr/bin/python3 electronics/power_check.py --input-5v 4.75`는 해당 전압 모델을 실행합니다. 현재 배선의 분석 한계 4.27 V를 밑도는 출력을 보고하고 종료 코드 1을 반환합니다.
