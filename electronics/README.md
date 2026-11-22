# B25 서보 허브 A4

받침 뒤의 **XT30은 5 V**, **XT60은 12 V**입니다. 내부 J2의 12 V 리드는 작업대에서 연결하고 고정합니다. 조립 후 정비할 때는 뒤쪽 XT60을 분리합니다. [3D 배선·정비](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/) · [B25 조립](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선)

기판 발주는 A4 제작 파일과 아래 옵션을 사용합니다. 부품은 시험판을 맞춘 뒤 준비합니다. [A4 구매 규격](../mechanical/revisions/b25/03-order-after.md) · [검사 조건 14절](../spec/conditions.md#14-전원과-환경)

| 보드 | 제작 파일 | JLCPCB 발주 옵션 |
|---|---|---|
| [서보 허브 A4](servo-hub/R5_Servo_Hub.kicad_pro) | [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A4-Gerbers.zip) | 70 × 35 mm, **2층 FR-4 1.6 mm, 양면 완성 동박 2 oz**, ENIG, 녹색 솔더마스크 |

A4의 JST PH 11개 패드(J3–J6)는 **1.35 × 1.75 mm / Ø0.75 mm**입니다. J1과 J2의 XT30은 각각 **5.00 mm 피치, Ø1.90 mm 단자홀 2개, Ø1.00 mm 고정홀 2개**이며, 도금 고정홀의 동박 패드는 Ø1.60 mm입니다. 전체 도금 부품홀 51개의 최소 설계 링은 0.300 mm로 JLCPCB의 2층 2 oz 기준 **0.254 mm**를 충족합니다. 비아 25개는 Ø0.70 또는 Ø0.90 mm 패드에 Ø0.35 mm 드릴을 사용합니다. KiCad 9.0.2에서 ERC, DRC, 미연결과 회로도 대조 각 0건입니다. [AMASS XT30PW-M 제조사 도면](https://www.tme.eu/Document/6eb2005a51a52592b3f19e8a450c54c8/XT30PW-M.pdf) · [JLCPCB 제작 한계](https://jlcpcb.com/capabilities/pcb-capabilities/)

허브 U1–U3, R4–R6, C3–C5를 밑면에 먼저 리플로우합니다. VSON 접지 패드의 접합을 검사한 뒤 윗면 관통홀 부품을 납땜합니다. [허브 BOM](servo-hub/BOM.csv) · [허브 밑면 스텐실](fabrication/R5_Servo_Hub_A4-Stencil.zip) · [허브 밑면 실장 좌표](fabrication/R5-hub-back-positions-mm.csv) · [KiCad 라이브러리 라이선스](https://www.kicad.org/libraries/license/)

## 전원과 배선

전원 계산에는 어댑터 공칭값 **5.0 V와 12 V**를 적용합니다. 동박 검토에 사용한 카탈로그 정지 전류는 XL330 5.0 V에서 1.47 A, XL430 12 V에서 1.40 A입니다. 전류 합은 5 V 분기 전 5.89 A, J1·F1 4.42 A(허브 10 mA 포함), J2·F2 2.80 A입니다. [XL330-M077 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [XL330-M288 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications)

| 양극 경로 | 공통부 선폭과 전류 | 모터별 분기 선폭과 전류 |
|---|---|---|
| 5 V | 2.30–2.35 mm, 4.42 A | 제한기 앞 최소 0.32 mm, 뒤 최소 0.38 mm, 1.47 A |
| 12 V | 2.20–2.40 mm, 2.80 A | 1.25 mm, 1.40 A |

동박 두께 60 µm를 적용한 IPC-2221 외층 단일 트랙의 온도 상승 추정은 공통부에서 5 V 약 4 °C, 12 V 약 2 °C, 가장 좁은 5 V 분기에서 약 9 °C입니다. 5 V 분기의 Ø0.35 mm 비아는 JLCPCB의 평균 도금 두께 18 µm에서 약 1.6 mΩ 및 3.4 mW입니다. 위 전류에서 PCB 양극 동박의 전압 강하 추정은 J4–J6 **32.3–45.3 mV**, J7 **18.2 mV**, J8 **12.4 mV**입니다. GND는 양면 동박 면으로 연결됩니다. 정상 구동 중의 어댑터 출력과 모터 단자 최저 전압은 조립품에서 측정합니다. [동박 전압 강하 계산](power_check.py) · [KiCad 트랙 폭 계산 기준](https://docs.kicad.org/9.0/en/pcb_calculator/pcb_calculator.html#track-width) · [JLCPCB 비아 도금](https://jlcpcb.com/capabilities/pcb-capabilities/)

### 허브 단자와 배선

| 단자 | 연결 |
|---|---|
| J1 5 V 입력 | 패드 2는 +, 1은 GND. 기판 XT30PW-M에는 W3/W4의 XT30U-F가 연결 |
| J2 12 V 목 전원 입력 | 패드 2는 +, 1은 GND. 기판 XT30PW-M에는 W8/W9의 12 V XT30U-F가 연결. 작업대에서 결합해 잠금쇠로 고정하며 조립 상태의 정비 분리는 받침 뒤 XT60 |
| J3 OpenRB | OpenRB EH 1(GND) → PH 1, EH 3(DATA) → PH 2. EH 2는 비움 |
| J4–J6 | ID 1–3. PH 1 GND / 2 **개별 전류 제한 5 V** / 3 DATA |
| J7–J8 | ID 4·5. EH 1 GND / 2 **목 전원** / 3 DATA |
| ID 6 턱 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

5 V 배선에는 XT30U-F 두 개와 XT30U-M 한 개가 필요합니다. F 한 개는 5 V 전원 꼬리에, 다른 한 개는 허브 J1 쪽 W3/W4에 씁니다. OpenRB 점퍼는 USB/VIN에 두고 USB로 공급합니다. 5 V와 목 전원은 GND·DATA를 공유하고 양극은 별도입니다. [OpenRB 전원과 포트](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/)

외부 5 V XT30과 12 V XT60은 간격이 각각 5.0 mm와 7.2 mm이며 반대편 외형에도 맞지 않습니다. 내부에서는 J1과 J2 모두 XT30을 쓰므로, 12 V J2 리드를 작업대에서 먼저 연결하고 H3·H4 잠금쇠로 고정합니다. 받침 뒤의 12 V 공급선과 같은 전압의 정비 접속부에는 각각 용도를 표시합니다. 전원은 +를 패드 2, GND를 패드 1에 연결합니다. [AMASS XT30U](https://www.china-amass.com/biao/268.html) · [AMASS XT60U](https://www.china-amass.com/biao/288.html) · [B25 조립과 배선](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선)

### 전원 실물 검수

1. 실내 15–30 °C에서 받침을 수평으로 놓습니다. 모터를 뺀 채 5 V와 12 V 어댑터를 각각 켜 허브 TP1과 TP2의 전압과 극성을 TP3 기준으로 확인합니다.
2. 전원을 끄고 모터를 연결합니다. 보정 후 추적·깜빡임·턱 동작에서 어댑터 출력과 모터 단자의 최저 전압을 각각 측정하고, 전원 강하·통신 끊김과 구동 결과를 기록합니다. [B25 검사 조건](../spec/conditions.md#14-전원과-환경) · [실물 동작 검사](../spec/bench.md)

## 재현

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 회로·PCB 검사와 BOM 대조 후 `build/electronics/servo-hub/`에 제작 파일을 생성합니다.

```sh
/usr/bin/python3 electronics/power_check.py --nominal
/usr/bin/python3 electronics/export.py servo-hub
```

## 이전 전장 검토 기록

이전 서보 허브 A3의 제작 파일입니다. [Gerber·드릴](fabrication/R5_Servo_Hub_A3-Gerbers.zip) · [스텐실](fabrication/R5_Servo_Hub_A3-Stencil.zip)

ESP32-C3 A1은 별도 RF 실험으로 보관합니다. B25의 부품·PCB 발주 범위에서 제외합니다. [C3 KiCad 원본](c3-rf/) · [이전 C3 제작·실장 기록](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/electronics/README.md#c3-첫-동작)

### 외부 전원 보호 계산

이전 전원 설정과 외부 보호 시안은 개정 이력에서 확인할 수 있습니다. [이전 전원과 보호 계산](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/electronics/README.md#외부-전원-보호-계산)
