# B25 서보 허브 A5

B25 제작에는 **A5**를 사용합니다. 70 × 35 mm 4층 보드의 밑면 SMD 12개는 공장에 맡기고 윗면 관통홀 부품 14개는 직접 납땜합니다. [A5 회로도·PCB·3D](../web/b25/R5-B25-A5.html) · [시험 뒤 구매 목록](../mechanical/revisions/b25/03-order-after.md)

받침 뒤의 **XT30은 5 V**, **XT60은 12 V**입니다. 작업대에서 무전원 검사를 마치고, 첫 통전 전에 내부 J2 잠금쇠를 고정합니다. [B25 조립](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선) · [핀별 배선도](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/diagram/)

| 작업 | 확인할 항목 |
| --- | --- |
| [A5 발주](#jlcpcb-밑면-실장) | 4층 무연 HASL, 밑면 12개, U1–U3의 1번 핀 |
| [첫 통전](#전원-실물-검수) | 양쪽 퓨즈를 빼고 5 V와 12 V 입력을 하나씩 확인 |
| [모터와 OpenRB 결선](#허브-단자와-배선) | 모터별 전원 핀과 J3의 GND·DATA |
| [하부 덮개 정비](#하부-덮개-정비) | 두 어댑터와 USB를 분리한 뒤 뒤쪽 XT60 서비스 플러그 사용 |
| [구동 중 전원 확인](#구동-중-전원-확인) | 어댑터 출력과 각 모터 단자의 최저·최고 전압 |

## A5 발주

### JLCPCB 밑면 실장

건식 맞춤 뒤 **70 × 35 mm · FR-4 1.6 mm · 4층 · 외층 1 oz · 내층 0.5 oz · 녹색 · 무연 HASL**로 견적을 받습니다. **Economic PCBA, Bottom, 실장 2장**을 선택합니다. U1–U3의 바닥 GND 패드는 X-ray 검사 범위와 견적을 확인합니다. [Gerber·드릴 ZIP](fabrication/R5_Servo_Hub_A5-Gerbers.zip) · [실장 BOM](fabrication/R5_Servo_Hub_A5-JLCPCB-BOM.csv) · [실장 CPL](fabrication/R5_Servo_Hub_A5-JLCPCB-CPL.csv) · [JLCPCB 실장 규격](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)

CPL에서 U1–U3은 모두 0°입니다. 밑면 미리보기에서 각 칩의 몸체 점을 기판의 1번 패드 옆 표시와 대조합니다. 받은 기판에 J1–J8, F1·F2 홀더, C1·C2 및 D1·D2를 윗면에서 끼우고 밑면에서 납땜합니다. C1·C2의 극성과 J1·J2의 방향을 먼저 확인하세요. [A5 구매와 손납땜](servo-hub-a5/README.md#손납땜) · [A5 전체 BOM](servo-hub-a5/BOM.csv)

## 전원과 배선

### 전원 실물 검수

**허브를 받침에 넣기 전에 작업대에서 확인합니다.** 내부 J1·J2는 같은 XT30이므로 12 V 플러그가 J1에도 들어갑니다. F1이 장착된 상태에서 J1에 12 V를 넣으면 모터를 빼 두어도 TPS2557의 절대최대 **7 V**와 C1의 정격 **10 V**를 넘어 부품이 손상될 수 있습니다. F1은 과전류 퓨즈입니다. 두 퓨즈를 뺀 채 아래 순서로 입력을 확인합니다. [TPS2557 데이터시트 7.1·7.3절](https://www.ti.com/lit/ds/symlink/tps2557.pdf)

1. **두 어댑터를 AC와 하네스에서 분리하고 USB·모터·OpenRB를 뺍니다. F1·F2 퓨즈도 뺍니다.** 뒤 `12 V SERVICE` XT60을 분리합니다. W3/W4 양끝은 `J1 · 5 V`, W8/W9 양끝은 `J2 · 12 V`로 표시합니다. 뒤쪽 XT60 두 곳은 `12 V IN`과 `12 V SERVICE`로 표시합니다. 각 어댑터는 하네스에 연결하기 전에 DC 출력과 극성을 재고 AC에서 분리합니다.
2. 무전원에서 J1·J2를 꽂고 허브를 하부 덮개에 고정합니다. 분리된 **가동 XT60의 +는 F2 입력 접점에만**, −는 **TP3(GND)**에 도통되는지 확인합니다. 외부 5 V XT30의 +는 **F1 입력 접점에만**, −는 **TP3**에 도통되어야 합니다. 두 입력 양극끼리와 GND 사이의 단락도 확인합니다. **J2 잠금쇠를 H2·H4에 조인 뒤** 플러그 뒤턱이 걸려 있는지 확인합니다. [P02의 무전원 잠금 확인](../spec/bench.md#p02-내부-j2-잠금쇠)을 마치면 서비스 XT60을 연결합니다.
3. **퓨즈를 뺀 채** 검정 리드를 `GND` 실크가 있는 TP3에 댑니다. 어댑터를 하나씩 켜서 F1 입력에 +5 V, F2 입력에 +12 V가 각각 나타나는지 확인합니다. 전압이 다른 입력에 나타나거나 극성이 다르면 전원을 분리하고 처음부터 확인합니다. 5 V를 켜면 F1 앞에 분기된 턱 배선에도 전압이 걸립니다.
4. 두 어댑터를 AC에서 분리하고 입력이 0 V로 내려가면 **F1 7.5 A, F2 4 A**를 넣습니다. 모터·OpenRB·USB를 분리한 채 한 계통씩 확인합니다.

   | 연결할 어댑터 | TP3(GND) 기준 | 모터를 꽂기 전 출력 핀 2 |
   | --- | --- | --- |
   | 5 V만 | TP1 약 +5 V | J4–J6 약 +5 V, 2 A 인라인 퓨즈 뒤 턱 ID6 EH 약 +5 V |
   | 12 V만 | TP2 약 +12 V | J7·J8 약 +12 V |

5. 전원을 분리하고 전압이 0 V가 되면 아래 핀을 대조해 OpenRB와 모터를 연결합니다. **일상 정비는 뒤쪽 XT60에서 분리합니다.** 내부 J2 잠금쇠를 푸는 작업에서는 1번부터 다시 확인합니다. [B25 조립 순서](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선)

### 허브 단자와 배선

새로 재단하는 선의 색은 **+5 V·+12 V 빨강, GND 검정, 모터 DATA 흰색**으로 고정합니다. 두 전압의 양극 색이 같으므로 선 양끝의 J1·J2 및 전압 라벨로 구분합니다. 카메라 USB의 접합부 표식은 **VBUS 빨강, D− 흰색, D+ 초록, GND 검정**입니다. 순정 플러그와 선재의 도체는 절단 전 도통으로 식별합니다. [핀과 선의 색·길이](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/diagram/) · [하네스 재단표](../mechanical/WIRING-CUT-LIST.csv)

| 단자 | 연결 |
| --- | --- |
| J1 5 V 입력 | 패드 2는 +, 1은 GND. W3/W4의 XT30U-F 연결 |
| J2 12 V 목 전원 입력 | 패드 2에 W8 적색(+), 패드 1에 W9 흑색(GND). XT30U-F를 J2 쪽 잠금쇠로 고정 |
| J3 OpenRB | W10은 **OpenRB EH 1(GND) → J3 PH 1**, W11은 **OpenRB EH 3(DATA) → J3 PH 2**. **OpenRB EH 2(VDD)는 금속 단자 없이 비움** |
| J4–J6 | ID 1–3. PH 1 GND / 2 **개별 전류 제한 5 V** / 3 DATA |
| J7·J8 | ID 4·5. EH 1 GND / 2 **12 V 목 전원** / 3 DATA |
| 턱 ID 6 | 어댑터 5 V에서 **2 A 인라인 퓨즈**를 거쳐 EH 2. 입력 GND는 EH 1, J6 DATA는 EH 3에 분기 |

OpenRB는 USB를 뽑은 상태에서 점퍼를 **USB(VIN)** 쪽에 놓습니다. 나사식 VIN 단자를 비워 두고 제어기만 USB로 공급합니다. 무전원에서 W10·W11의 도통, 두 선 사이의 단락 여부, EH 2에 금속 단자가 없는지 확인한 뒤 J3를 연결합니다. 5 V와 12 V 목 전원은 GND·DATA를 공유하고 양극 배선은 각각 독립입니다. [OpenRB 전원 점퍼](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#power-source-jumper) · [포트 핀 배치](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#dynamixel-ports)

5 V 배선에는 XT30U-F 두 개와 XT30U-M 한 개를 씁니다. F 한 개는 5 V 전원 꼬리, 다른 한 개는 J1 쪽 W3/W4에 씁니다. 외부 5 V XT30과 12 V XT60은 서로 다른 외형과 단자 간격(각각 5.0 mm와 7.2 mm)으로 구분합니다. [AMASS XT30U](https://www.china-amass.com/biao/268.html) · [AMASS XT60U](https://www.china-amass.com/biao/288.html)

12 V 어댑터의 DC 출력 리드에는 **XT60U-F 한 개**를 납땜합니다. 어댑터의 출력 극성을 멀티미터로 확인하고, AC에서 분리한 뒤 XT60U-F 몸체의 +·− 표기에 맞춥니다. 두 컵을 각각 절연하고 **12 V IN** 라벨을 붙입니다. 받침의 XT60U-M에서 W6·W7이 시작됩니다. [12 V 고정선 조립](../mechanical/revisions/b25/j2-supply-delta.md) · [하네스 재단표](../mechanical/WIRING-CUT-LIST.csv)

### 하부 덮개 정비

두 어댑터와 USB를 뽑고 받침을 지지합니다. 뒤쪽 **`12 V SERVICE` XT60** 플러그를 똑바로 빼서 아래 대기 위치로 내린 뒤, 허브와 하부 덮개를 함께 내립니다. 내부 J2는 작업대에서 J2 쪽 M3×12 두 개를 풀어 분리합니다. 다시 닫을 때 선의 눌림, 커넥터 체결과 극성을 무전원에서 확인합니다. 내부 J1 또는 J2를 분리했다면 위의 [전원 실물 검수](#전원-실물-검수)를 다시 수행합니다. [B25 덮개·배선 절차](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선) · [3D 배선·정비](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/)

`12 V SERVICE` 가동 플러그 XT60U-M의 제조사 권장 선은 12 AWG입니다. B25의 W8·W9는 18 AWG이므로 실제 컵 깊이로 탈피 길이를 정하고, 컵과 도체 모두에 납이 잘 젖었는지 확인합니다. 식힌 뒤 각 선을 가볍게 당겨 접합을 확인하고, 두 컵을 각각 열수축 튜브로 절연합니다. 플러그를 뺄 때 몸체를 잡고 가동선 루프를 받쳐 접합부의 당김을 줄입니다. 통전 전 극성과 단락, P08에서 절연부의 눌림과 당김을 확인합니다. [AMASS XT60U-M 사양](https://images.100y.com.tw/pdf_file/AMASS-XT60U.pdf) · [B25 정비 리드 조립](../mechanical/revisions/b25/j2-disconnect.md#결선과-남은-검증)

### 구동 중 전원 확인

검사 조건 14절의 실내 환경에서 받침을 수평으로 놓습니다. 목을 받치고 보정한 뒤 한 축씩 처음 구동합니다. 추적·깜빡임·별도 턱 시험에서 어댑터의 DC 출력과 각 모터 단자 전압을 기록합니다. 기동·급감속의 순간 전압을 보려면 오실로스코프로 최저·최고를 기록합니다. XL430의 제조사 작동 범위 상한은 12.0 V입니다. P07에서 OpenRB를 재시작한 뒤 토크 해제도 확인합니다. [OpenRB와 모터 보정](../control/README.md#openrb와-모터) · [검사 조건 14절](../spec/conditions.md#14-전원과-환경) · [P07 실물 시험](../spec/bench.md#b25-실물-시험)

모터 GND는 TTL DATA의 기준이자 전원 전류의 귀환 경로입니다. 전류가 급변하면 같은 GND 선의 전압 강하가 순간적으로 변해, 모터가 보는 DATA 전압이 흔들릴 수 있습니다. DATA와 해당 GND를 가까이 묶고 긴 공급선과 나란히 가는 구간을 줄입니다. 구동 중 통신 오류나 리셋이 보이면 해당 모터에서 **3번 DATA와 2번 전원**을 각각 **1번 GND** 기준으로 봅니다. 허브와 모터 간 GND 전위차를 직접 비교할 때는 차동 프로브를 사용합니다. [ROBOTIS 핀 배치](https://emanual.robotis.com/docs/en/parts/controller/openrb-150/#dynamixel-ports) · [배선도](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/diagram/#ground)

U1–U3의 61.9 kΩ 설정에서 TI 특성표의 출력 제한은 **1.590 / 1.785 / 1.960 A**(최소 / 대표 / 최대)입니다. 저항값에 따른 근사식의 하한은 약 **1.54 A**이고 XL330의 5.0 V 공칭 정지 전류는 **1.47 A**입니다. 과전류 시 출력 전압이 내려가고, 과부하가 계속되면 온도에 따라 차단과 재시동을 반복할 수 있습니다. **FAULT 8번은 미연결**이라 LED와 OpenRB에 채널별 경보가 없습니다. 눈·눈꺼풀 기동에서 출력이 떨어지거나 모터가 리셋되면 TP1과 해당 J4–J6의 2번 핀을 비교하고 해당 채널의 전류와 온도를 확인합니다. TI는 출력의 과도 전류가 클 때 개별 출력 커패시터를 권장하며, A5의 개별 커패시터 C3–C5는 입력에 있습니다. J7·J8의 12 V는 공통 F2 4 A로 보호되므로 P08에서 두 분기 배선의 피복과 눌림을 확인합니다. [TPS2557 특성표·과전류 동작·설정식](https://www.ti.com/lit/ds/symlink/tps2557.pdf) · [XL330 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [A5 회로도](servo-hub-a5/R5_Servo_Hub.kicad_sch)

## 제작 치수와 전원 계산

J1·J2는 **5.00 mm 피치 XT30PW-M**입니다. 각 자리의 단자홀은 Ø1.90 mm 두 개, 고정홀은 Ø1.00 mm 두 개입니다. [AMASS XT30PW-M 도면](https://www.tme.eu/Document/6eb2005a51a52592b3f19e8a450c54c8/XT30PW-M.pdf)

공칭 5.0 V·12 V와 모터 카탈로그 정지전류를 적용한 A5 계산에서 최저 모터 단자 전압은 **J4 4.132 V, J8 11.460 V**입니다. 조립된 배선의 접촉저항, 어댑터의 부하 조정률과 순간 전압은 P07에서 측정합니다. [A5 계산과 검사 범위](servo-hub-a5/README.md#검증) · [P07 실물 시험](../spec/bench.md#b25-실물-시험)

## 재현

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 발주 파일은 `build/electronics/servo-hub-a5/`에 생성됩니다. [A5 HTML 재현](servo-hub-a5/README.md#검증)

```sh
/usr/bin/python3 electronics/power_check.py --hub-revision A5
/usr/bin/python3 electronics/export.py servo-hub-a5
```

## 이전 전장 기록

- [A4 2층 원본](servo-hub/) · [A4 발주·검증 이력](https://github.com/ckh7488/head/blob/b19aada/electronics/README.md#a4-발주) · [A3 제작 기록](fabrication/R5_Servo_Hub_A3-Gerbers.zip)
- [A6 전량 손납땜 시안](servo-hub-a6/) · [C3 별도 RF 실험](c3-rf/) · [외부 전원 보호 시안 계산](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/electronics/README.md#외부-전원-보호-계산)
