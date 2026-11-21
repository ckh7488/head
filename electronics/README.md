# 서보 허브와 ESP32-C3

서보 허브 A3와 C3 A1 시제품의 검토용 제작 자료입니다. A3는 회로·PCB 검사와 기준 전원에서의 정적 전압 계산을 통과했습니다. 실물 전압·고장 보호·구동 검수 뒤 발주를 판정합니다.

| 보드 | 제작 파일 | 제작 옵션 |
|---|---|---|
| [서보 허브 A3](servo-hub/R5_Servo_Hub.kicad_pro) | [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A3-Gerbers.zip) | 70 × 35 mm, **2층 FR-4 1.6 mm, 양면 2 oz**, ENIG |
| [ESP32-C3 RF A1](c3-rf/C3_Antenna.kicad_pro) | [Gerber·드릴 ZIP](fabrication/C3_Antenna_A1-Gerbers.zip) | 34 × 53 mm, **4층 FR-4 1.6 mm, 외층 1 oz, 내층 0.5 oz**, ENIG |

허브 A3는 J4–J6 앞에 전류 제한기 세 개를 넣고, 공용 퓨즈 F1을 7.5 A로 바꿨습니다. 기존 커넥터, 장착홀과 0.30 mm 도금홀 동박 링은 유지했습니다. B24 CAD에 새 밑면 부품의 1.40 mm 높이와 평면 공차를 포함한 상자를 놓은 결과, 덮개와 최소 **1.46 mm** 떨어졌습니다. 커넥터와 VSON 풋프린트는 KiCad 공식 라이브러리를 수정했습니다. [제작 한계](https://jlcpcb.com/capabilities/pcb-capabilities/) · [KiCad 라이브러리 라이선스](https://www.kicad.org/libraries/license/)

RF 보드는 JLC04161H-7628 적층을 선택합니다. L1–L2 사이 0.2104 mm 조건에서 RF 선폭 0.36 mm, 양옆 GND 간격 0.20 mm, 아래 L2 GND로 50 Ω을 목표로 합니다. [JLC 적층표](https://jlcpcb.com/impedance)

허브 U1–U3, R4–R6, C3–C5는 밑면에 먼저 리플로우합니다. VSON 접지 패드의 접합을 검사한 뒤 윗면 관통홀 부품을 납땜합니다. [허브 밑면 스텐실](fabrication/R5_Servo_Hub_A3-Stencil.zip) · [허브 밑면 실장 좌표](fabrication/R5-hub-back-positions-mm.csv)

C3 RF 보드의 SMT 부품은 윗면에 실장합니다. C3 스텐실은 윗면 0.10 mm를 사용합니다. 칩 아래의 솔더마스크가 방열 비아를 덮고, 그 사이 네 곳에 납을 올립니다. C15–C18은 비웁니다. USB-C J1과 UART J2는 실장 좌표에서 제외합니다. 리플로우 뒤 J1의 전기 단자 16개와 고정 탭 4개, J2의 단자 3개를 관통홀로 납땜합니다. R1·R2의 기본 실장은 둘 다 0 Ω입니다. [허브 BOM](servo-hub/BOM.csv) · [C3 BOM](c3-rf/BOM.csv) · [C3 스텐실](fabrication/C3_Antenna_A1-Stencil.zip) · [C3 실장 좌표](fabrication/C3-front-positions-mm.csv)

## 전원과 배선

- 기준 시험 전원은 **SIGLENT SPD1168X**, 20–30 °C, 로컬 센스, 정전압 **5.21 V**, 전류 상한 **7.50 A**입니다. 설정 오차, 입력·부하 변동과 3 mV 리플을 합쳐 출력 단자에서 **5.17–5.25 V**를 사용했습니다. 16 AWG 전원 꼬리 W33·W34는 각 250 mm 이내입니다. 전원 본체는 받침 바깥에 둡니다. 국내 표시가는 약 **₩454,300**으로, 시제품 시험에는 사용 가능한 계측기를 우선 연결합니다. [SIGLENT 사양과 시험 방법](https://siglentna.com/wp-content/uploads/dlm_uploads/2023/04/SPD1000X-Series-Service-Manual_E01B.pdf) · [국내 판매 페이지](https://siglentkorea.com/product/siglent-%EC%8B%9C%EA%B8%80%EB%9F%B0%ED%8A%B8-spd1168x-programmable-dc-power-supply-%ED%8C%8C%EC%9B%8C%EC%84%9C%ED%94%8C%EB%9D%BC%EC%9D%B4-%EC%A0%84%EC%9B%90%EA%B3%B5%EA%B8%89%EA%B8%B0-128w-1/88/) · [전선 재단표](../mechanical/WIRING-CUT-LIST.csv)
- 5 V 부하 계산에는 네 XL330에 각각 **1.55 A**, 허브 보조 부하 10 mA, 두 목 XL430에 각각 **1.40 A**를 적용했습니다. XL330 제조사 값은 5.00 V에서 1.47 A, 6.00 V에서 1.74 A이며, 5.25 V에서 선형 보간한 약 1.54 A보다 큰 값을 사용했습니다. WAGO 분기 전 공통선은 6.21 A, W3·W4와 F1은 4.66 A를 반영했습니다. 70 °C 전선, 수명 후 접점, 퓨즈와 스위치, PCB 트랙과 비아를 포함했습니다. [XL330-M077 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [XL330-M288 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications) · [전압 계산](power_check.py)
- 5.17 V 전원과 목 전원 입력 11.10 V에서 모터 단자 하한은 J4 **4.334 V**, J5 **4.325 V**, J6 **4.341 V**, 턱 **4.621 V**, 목 J7 **10.730 V**, J8 **10.647 V**입니다. XL330 단자 계산은 기존 하중 모델의 4.27–5.25 V 안에 듭니다. 종전 전원 허용 하한 4.75 V를 넣으면 네 XL330 모두 4.27 V 미만입니다. 목은 별도 정전압 12 V급 5 A 전원을 씁니다. [눈꺼풀 부하 모델](../mechanical/revisions/b24/blink-loaded.json)
- J4–J6 중 하나가 1.997 A로 제한되고 나머지 XL330 세 개가 1.55 A씩 쓰면 전원은 **6.657 A**, F1은 **5.107 A**를 공급합니다. 정상인 모터 단자를 4.27 V 이상 유지하려면 전원 출력이 정상 부하에서는 **5.115 V**, 단일 PH 고장에서는 **5.158 V** 이상이어야 합니다. 전원 출력이 5.17 V일 때 단일 고장 중 정상인 J5의 계산값은 **4.283 V**입니다. 16 AWG W33·W34를 각 100 mm로 줄이면 단일 고장 계산 하한은 **5.120 V**입니다. [전압 계산](power_check.py)

### 소형 전원 후보

받침 옆에 전원을 놓고 100 mm 이하의 W33·W34를 연결할 수 있으면, 전원 출력 단자 **5.14–5.25 V**로 검수합니다. 5.14 V에서 단일 고장 중 정상인 J5의 계산값은 **4.290 V**입니다.

소형 전원 시안은 **MEAN WELL GST120A24-R7B** 어댑터에서 외장 함의 **DDR-60G-5**와 **DDR-60G-12**에 각각 24 V를 공급합니다. 조정한 5 V 출력은 XT30으로, 목 출력은 XT60으로 연결하고 두 출력의 GND를 허브에서 만납니다. 24 V 입구는 전용 R7B 커넥터를 씁니다. XL430의 동작 상한은 12.00 V입니다. 12 V 고정 어댑터만 직결하면 허용 오차에서 이 값을 넘으므로 목에도 조정 가능한 출력이 필요합니다. [GST120A 사양](https://www.meanwell.com/Upload/PDF/GST120A/GST120A-SPEC.PDF) · [DDR-60 사양](https://www.meanwell.com/Upload/PDF/DDR-60/DDR-60-SPEC.PDF) · [XL430 동작 전압](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications)

5.25 V에서 단일 PH 고장 부하는 **35.0 W**, 12.00 V에서 두 목 모터 부하는 **33.6 W**입니다. 수직 장착, 외장 함 내부 20–30 °C를 기준으로 두 변환기 입력이 22.8 V 이상이고 효율이 각각 80% 이상이면 어댑터에서 약 **3.76 A**를 공급합니다. 검수 시 24 V 어댑터의 정격 **5 A**와 변환기의 실제 입력·온도를 확인합니다. Kycon KPJX-CM-4S 접점은 양극 1·4번과 음극 2·3번을 각각 병렬로 씁니다. 제조사의 접점 상한 30 mΩ으로 계산한 3.76 A의 접점 쌍 강하는 약 **0.113 V**입니다. 두 DDR의 입력은 5번 양극·6번 음극이며, 출력은 1·2번 음극·3·4번 양극입니다. [GST120A 핀 배열](https://www.meanwell.com/Upload/PDF/GST120A/GST120A-SPEC.PDF) · [DDR-60 디레이팅 곡선](https://www.meanwell.com/Upload/PDF/DDR-60/DDR-60-SPEC.PDF) · [Kycon 커넥터 사양](https://www.mouser.com/datasheet/2/222/KPJX-CM-365189.pdf)

시작 조정값은 5 V 레일 **5.19 V**, 목 레일 **11.55 V**입니다. 변환기 사양만으로 아래의 실제 전압 범위를 보증할 수 없으므로 무부하와 최대 부하, 리플과 과도까지 시험합니다. 각 변환기의 과부하 정격은 보호 기준과 별개이므로 출력 보호도 검수합니다. [DDR-60 사양](https://www.meanwell.com/Upload/PDF/DDR-60/DDR-60-SPEC.PDF)

### 외부 전원 보호 계산

5 V 보호는 변환기에서 첫 XT30과 턱 분기 앞에 둡니다. 목 보호는 두 종류의 결선에서 첫 XT60보다 앞에 둡니다. A3의 4 A F2는 J2 뒤에 있습니다. 전원이 5.00 A를 제한하면 F2에는 정격의 125%가 흐를 수 있습니다. Littelfuse 표에서 최대 개방 시간은 135%인 **5.40 A**부터 제시됩니다. JST EH의 3.00 A는 22 AWG를 사용한 제조사 기준입니다. 실제 24 AWG인 J7·J8 하네스는 접점·전선 온도가 85 °C 이하인지 별도로 확인합니다. 공용 5.00 A 제한과 F2만으로는 분기 전류를 이 기준 안에 둘 수 없습니다. 각 EH의 전류를 개별 제한하려면 J7·J8의 첫 EH 접점보다 기판 쪽에 보호를 둡니다. 아래의 채널별 시안은 A3 기판에서 별도로 작업해야 합니다. [MINI 퓨즈 개방 시간](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_297_mini32v.pdf?assetguid=42c9dd21-a88e-4328-8e67-2f832444faf1) · [JST EH 정격](https://jst.es/wp-content/uploads/2025/06/eh-connector.pdf)

| 위치 | 검토 부품 및 설정 | 정적 임계값 추정 | 필요한 연속 전류 범위 |
|---|---|---:|---:|
| 5 V 공통선 | INA301A2, WSLP2512 5 mΩ 1%, LIMIT 22.1 kΩ 0.1%/10 ppm/°C, TPS22990N 차단 스위치 | 6.782–7.373 A | 6.657 A 통과, 7.50 A 이하에서 차단 |
| 목 전원 공통선 | TPS259470L, ILM 750 Ω 0.1%/25 ppm/°C, ITIMER 개방 | 3.946–4.857 A | 2.80 A 통과, 5.00 A 이하에서 제한 |
| J7·J8 양극 분기 | TPS259470L 각각 한 개, ILM 1.65 kΩ 0.1%/25 ppm/°C, ITIMER 개방 | 1.794–2.208 A | 채널별 1.40 A 통과, 22 AWG 카탈로그 기준 3.00 A 미만에서 비교 |

INA301A2의 표 조건에 저항·증폭 이득·오프셋·명시된 온도 변화량을 반영했습니다. 비교기 오프셋의 전 온도 범위는 실측합니다. ALERT의 래치 설정으로 스위치를 제어하는 시안입니다. 비교기가 준비되기 전, 고장으로 바이어스 전압이 꺼질 때, 차단 이후 재설정 전의 세 경우에 스위치가 열려 있도록 제어 회로를 검증합니다. TPS259470L은 12 V에서 저항별로 제시된 표의 상·하한을 식 (7)의 감도로 보정했습니다. 두 목 채널 중 하나가 추정 상한으로 제한되면 총 약 **3.61 A**로 공통 제한기의 추정 하한 3.946 A 미만입니다. 이때 F2의 온도와 정상 채널의 동작 전압도 확인해야 합니다. 실물에서는 온도·입력 전압 전역의 임계값, 단락 전류 피크, 내부 방열, 차단·재가동 및 분기 커패시터의 방전 전류를 잽니다. [INA301 사양](https://www.ti.com/lit/ds/symlink/ina301.pdf) · [WSLP2512 사양](https://www.vishay.com/docs/30122/wslp.pdf) · [TPS22990N 사양](https://www.ti.com/lit/ds/symlink/tps22990.pdf) · [TPS25947 사양](https://www.ti.com/lit/ds/symlink/tps25947.pdf)

TPS22990N의 VBIAS는 VIN 이상이 되도록 차단기 앞 5 V에 연결하고 ON 제어를 함께 검증합니다. 6 mΩ는 실제 전압·전류·온도에서 검수할 저항 예산입니다. 제조사의 6 mΩ 표는 VBIAS 5 V와 0.2 A 조건입니다. 5 V는 6.657 A에서 션트와 스위치에 약 74 mV, 목은 2.80 A에서 공용 스위치에 약 126 mV를 배정했습니다. 소형 후보의 보호장치 **이후** 출력 하한 5.14 V와 11.10 V를 맞추려면 이 부품의 **앞**에서 각각 **5.214 V**, **11.226 V** 이상의 부하 전압이 필요합니다. 보호를 추가한 소형 후보는 이 하한과 무부하 상한 5.25 V 및 12.00 V를 함께 검수합니다. 위의 5.19 V는 보호를 달기 전의 시작값입니다. 공용 보호 이후 11.10 V에서 두 목 모터가 각 1.40 A를 쓰고 채널별 45 mΩ를 더하면 J8 기준 추가 왕복 저항은 약 30.02 mΩ까지입니다. 배선 검수 기준에는 뜨거운 상태의 **30.0 mΩ 이하**를 적용합니다. 접점·배선·접합을 모두 포함해서 기존 계산 경로와의 차이를 적용합니다. 추가 저항 20 mΩ의 예에서는 J8 **10.5281 V**, 31 mΩ에서는 **10.4973 V**로 10.50 V에 못 미칩니다. 반대 분기가 2.208 A로 제한되는 동안의 정상 J8은 20 mΩ에서 **10.450 V**, 30 mΩ에서 **10.414 V**입니다. 각각 공용 보호 이후 **11.150 V**, **11.186 V**가 필요합니다. [보호 계산](protection_check.py) · [B25 J2 결선 시안](../mechanical/revisions/b25/j2-disconnect.md#결선과-남은-검증)

TPS259470L은 출력에서 입력으로 역전류를 막습니다. 개별 제한기를 추가하면 기존 220 µF C2는 두 제한기 앞 공통 레일에 남으므로 개별 분기의 회생 에너지 흡수 용량에서 제외합니다. F2 앞 J2에서 단락하면 C2는 F2를 통해 역방향으로 방전할 수 있으므로 공용 단락 시험에도 포함합니다. 양쪽 목 모터 단자와 C2 양단에서 감속 과도 전압을 측정합니다. 5 V는 공통 레일과 J4–J6의 제한기 뒤, 턱 단자를 각각 계측합니다. 측정한 역전류·지속 시간과 실제 흡수 회로의 동작을 대조해 5.25 V 및 12.00 V 상한을 검증합니다. [TPS25947 역전류 차단](https://www.ti.com/lit/ds/symlink/tps25947.pdf)

### 허브 단자와 배선

| 단자 | 연결 |
|---|---|
| J1 5 V 입력 | 패드 2는 +, 1은 GND. 기판 XT30PW-M에는 W3/W4의 XT30U-F가 연결 |
| J2 목 전원 입력 | 패드 1은 +, 2는 GND. B5 외부 고정에는 XT60U를 사용 |
| J3 OpenRB | OpenRB EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **개별 전류 제한 5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 턱 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

5 V 배선에는 XT30U-F 두 개와 XT30U-M 한 개가 필요합니다. F 한 개는 5 V 전원 꼬리에, 다른 한 개는 허브 J1 쪽 W3/W4에 씁니다. OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 5 V와 목 전원은 GND·DATA를 공유하고 양극은 별도입니다. 모터를 빼고 두 입력을 각각 켜 TP1과 TP2를 TP3 기준으로 확인합니다. 전원을 끄고 번호를 붙인 모터선을 하나씩 꽂습니다. 첫 동작에서 저전압이나 통신 끊김이 보이면 해당 모터 단자와 입력 단자를 함께 잽니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

J4–J6는 각각 TPS2557과 지정 61.9 kΩ, 0.1%, 25 ppm/°C 저항을 사용합니다. 61.9 kΩ의 데이터시트 표와 근사식을 적용한 추정치는 **1.585–1.997 A**입니다. 같은 근사식만 사용한 하한은 **1.539 A**입니다. 식 (1)에 저항 변동 ±0.3%를 넣으면 1.55 A를 공급하려면 공칭 저항이 61.486 kΩ 이하여야 하고, 2.00 A를 넘지 않으려면 61.791 kΩ 이상이어야 합니다. 두 범위가 겹치지 않으므로 조립한 채널마다 검사합니다. 제한기는 과부하 중 전류를 줄이며 과열 시 차단 후 자동 복귀합니다. 데이터시트의 단락 응답 3.5 µs는 일반값입니다. 공용 F1은 허브 입력에 있으며 턱의 별도 2 A 인라인 퓨즈도 사용합니다. [TPS2557 특성·허용 오차](https://www.ti.com/lit/ds/symlink/tps2557.pdf) · [JST PH](https://www.jst.com/wp-content/uploads/2025/06/ePH.pdf) · [JST EH](https://jst.es/wp-content/uploads/2025/06/eh-connector.pdf) · [MINI 퓨즈](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_297_mini32v.pdf?assetguid=42c9dd21-a88e-4328-8e67-2f832444faf1)

### 전원 실물 검수

1. 모터를 빼고 네 5 V 모터 단자에 전자부하를 연결합니다. 전원 단자에서 무부하부터 정상 6.21 A와 단일 PH 고장 6.66 A까지 기준 전원은 **5.17–5.25 V**, 100 mm 꼬리를 쓰는 소형 후보는 **5.14–5.25 V**인지 확인합니다. 전자부하를 각 1.55 A로 맞추고, 목의 두 단자에도 각 1.40 A를 걸어 동시에 측정합니다. 전원 단자와 각 모터 커넥터의 GND를 기준으로 잽니다. 계측 오차가 ±5 mV이면 소형 후보의 예시 합격 판독 범위는 **5.145–5.245 V**입니다.
2. 무부하부터 정상 동시 부하까지 보호장치 이후 목 전원 출력 **11.10–12.00 V**, 5 V 모터 단자 **4.27–5.25 V**, 목 모터 단자 **10.50–12.00 V**를 확인합니다. 냉간과 충분히 따뜻해진 상태에서 전원 투입·부하 변화·동시 구동 파형을 기록합니다. 전원 단자·외부 XT30·WAGO 접점에 배정한 12 mΩ, J1 4 mΩ, 설치된 F1 홀더와 퓨즈 35 mΩ, 턱 퓨즈 및 홀더 110 mΩ은 접점과 배선 온도를 반영해 전압 강하로 대조합니다.
3. J4–J6를 한 개씩 전자부하로 과부하시키고, 해당 PH의 정상 1.55 A 통과 및 제한 동작 중 연속 2.00 A 미만을 확인합니다. 전류 계측 오차가 ±10 mA이면 제한값 판독치 **1.56 A 이상, 1.99 A 미만**을 합격으로 봅니다. 나머지 5 V와 목 분기에 위 부하를 공급하면서 정상 5 V 채널 **4.27–5.25 V**와 목 **10.50–12.00 V**를 확인합니다. 차단·복구, 전류 피크와 퓨즈·커넥터·케이스 온도를 기록합니다. 전원은 30분 예열하고 운전 온도에서 확인합니다. 조립한 채널마다 냉간과 열간에서 반복합니다. Littelfuse의 대표 열 디레이팅 표에서 60 °C 주변의 7.5 A 퓨즈는 5.5 A, 2 A 퓨즈는 1.6 A, 4 A 퓨즈는 2.9 A입니다. 특히 턱 1.55 A와 목 2.80 A에서 퓨즈 주변 온도와 불필요한 차단 여부를 확인합니다. [MINI 퓨즈 열 디레이팅](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_297_mini32v.pdf?assetguid=42c9dd21-a88e-4328-8e67-2f832444faf1)
4. 5 V 출력의 연속 전류를 **7.50 A 이하**, 목 출력은 **5.00 A 이하**에서 제한하거나 차단하도록 보호를 선정합니다. 목의 보호장치는 XT60이 분리되는 모든 경로와 허브 F2보다 전원 쪽에 둡니다. 모터를 빼고 5 V 공통선, 턱 퓨즈 뒤, 각 PH 출력과 12 V XT60 뒤·F2 앞의 단락을 따로 확인합니다. 각 결선 방식에서 점검하고, J7·J8도 각각 과부하와 단락으로 검사합니다. 첫 피크와 차단·재시작 시간을 기록해 실제 전선과 단자의 허용 곡선·온도 한계 안인지 판정합니다. 모터를 연결한 뒤에는 전원 순서와 감속 중 역전류, 모터 단자 과도 파형을 확인합니다. [외부 전원 보호 계산](#외부-전원-보호-계산) · [J2 분리 시안의 보호 위치](../mechanical/revisions/b25/j2-disconnect.md#결선과-남은-검증)

## C3 첫 동작

1. 5 V USB를 연결해 TP1–TP2에서 3.3 V를 확인합니다.
2. BOOT을 누른 채 RESET을 눌렀다 떼고 BOOT을 놓습니다. PC에서 ESP32-C3의 USB Serial/JTAG 포트와 플래시 ID를 확인합니다. [ESP32-C3 다운로드 모드](https://docs.espressif.com/projects/esptool/en/latest/esp32c3/advanced-topics/boot-mode-selection.html)
3. VNA로 안테나를 볼 때는 전원을 빼고 R1을 제거합니다. R1의 안테나 쪽 패드와 바로 옆 GND를 사용합니다. 인쇄 IFA라 ANT와 GND는 직류에서 연결됩니다. 케이스 안에서 쓰려면 장착 전후 S11을 각각 봅니다. [TI 인쇄 안테나 원본](https://www.ti.com/lit/an/swru120d/swru120d.pdf)

U2는 AP7361C 1 A SOT-223이며 GND 방열 탭에 비아를 배치했습니다. 데이터시트의 Wi-Fi 최대 송신 조건 335 mA, USB 5.25 V에서 손실은 약 0.67 W입니다. [레귤레이터 데이터시트](https://www.diodes.com/datasheet/download/AP7361C.pdf) · [ESP32-C3 데이터시트](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf)

## 재현

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 회로·PCB 검사와 BOM 대조 후 `build/electronics/`에 발주 파일을 생성합니다.

```sh
/usr/bin/python3 electronics/power_check.py
/usr/bin/python3 electronics/power_check.py --ph-fault
/usr/bin/python3 electronics/power_check.py --ph-fault --tail-mm 100 --input-5v 5.14
/usr/bin/python3 electronics/protection_check.py --neck-service-loop-mohm 20
/usr/bin/python3 electronics/export.py servo-hub
/usr/bin/python3 electronics/export.py c3-rf
```

`/usr/bin/python3 electronics/power_check.py --input-5v 4.75`는 해당 전압 모델을 실행합니다. 현재 배선의 분석 한계 4.27 V를 밑도는 출력을 보고하고 종료 코드 1을 반환합니다.

`protection_check.py`에는 기존 경로보다 추가되는 목 전원 왕복 저항을 mΩ로 입력합니다. 예시 20 mΩ는 정적 계산을 통과합니다. 31 mΩ는 J8 하한을 밑돌아 종료 코드 1을 반환합니다. 차단과 구동 합격은 실물에서 확인합니다.
