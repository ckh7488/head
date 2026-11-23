# B25 서보 허브 A4

받침 뒤의 **XT30은 5 V**, **XT60은 12 V**입니다. 내부 J1과 J2는 모두 XT30PW-M이므로 작업대에서 두 입력을 확인한 뒤 J2를 잠급니다. [B25 조립](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선) · [핀별 배선도](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/diagram/) · [3D 배선·정비](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/)

| 작업 | 확인할 항목 |
| --- | --- |
| [A4 발주](#a4-발주) | 2층 양면 완성 동박 2 oz, 밑면 SMD 9개, U1–U3의 1번 핀 |
| [첫 통전](#전원-실물-검수) | 양쪽 퓨즈를 빼고 5 V와 12 V 입력을 하나씩 확인 |
| [모터와 OpenRB 결선](#허브-단자와-배선) | 모터별 전원 핀과 J3의 GND·DATA |
| [하부 덮개 정비](#하부-덮개-정비) | 두 어댑터와 USB를 분리한 뒤 뒤쪽 XT60 서비스 플러그 사용 |
| [구동 중 전원 확인](#구동-중-전원-확인) | 조립 상태에서 어댑터 출력과 모터 단자 최저 전압 실측 |

## A4 발주

부품은 시험판을 맞춘 뒤 준비합니다. [A4 구매 규격](../mechanical/revisions/b25/03-order-after.md) · [전체 허브 부품표](servo-hub/BOM.csv)

| 기판 원본 | 제작 파일 | JLCPCB 발주 옵션 |
| --- | --- | --- |
| [KiCad 프로젝트](servo-hub/R5_Servo_Hub.kicad_pro) · [회로도](servo-hub/R5_Servo_Hub.kicad_sch) · [PCB](servo-hub/R5_Servo_Hub.kicad_pcb) | [Gerber·드릴·밑면 페이스트 ZIP](fabrication/R5_Servo_Hub_A4-Gerbers.zip) | **70 × 35 mm, 2층 FR-4 1.6 mm, 양면 완성 동박 2 oz**, 무연 HASL, 녹색 솔더마스크 |

### JLCPCB 밑면 실장

1. B.Paste가 포함된 A4 Gerber ZIP을 올립니다. Economic PCBA에서 **밑면(Bottom)만 실장**을 선택하고, **양면 완성 동박 2 oz와 무연 HASL**을 함께 살 수 있는지 견적에서 확인합니다. U1–U3의 VSON(0.65 mm 피치, 노출 방열 패드)에 대해 업체가 ENIG를 요구하면 표면처리만 ENIG로 견적을 다시 냅니다. 주문 수량은 공개 최소인 2장부터 비교합니다. Standard PCBA는 최소 70 × 70 mm와 레일·피듀셜 조건을 업체와 확인합니다. [JLCPCB 실장 조건](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) · [TI VSON 도면](https://www.ti.com/lit/ds/symlink/tps2557.pdf)
2. 전용 CSV를 BOM과 CPL 칸에 각각 올립니다. 아래 **9개 모두 밑면**에 매칭되는지 확인합니다. 재고와 견적은 바뀔 수 있습니다. R4–R6을 대체할 때는 **61.9 kΩ, 0.1%, 25 ppm/°C 이하, 0603**을 유지합니다. [업로드용 BOM](fabrication/R5_Servo_Hub_A4-JLCPCB-BOM.csv) · [업로드용 CPL](fabrication/R5_Servo_Hub_A4-JLCPCB-CPL.csv) · [JLCPCB 파일 형식](https://jlcpcb.com/help/article/How-to-generate-the-BOM-and-Centroid-file-from-KiCAD)
3. 배치 미리보기에서 U1–U3의 몸체 점을 **기판의 1번 패드 옆 실크 점**에 맞춥니다. 같은 위쪽 모서리를 유지해 밑면에서 보면 몸체의 **오른쪽 위**입니다. Gerber X/Y 축에서 1번 패드는 몸체 중심보다 **X −0.975 mm, Y +1.400 mm**에 있습니다. 업로드 좌표는 KiCad의 mm 좌표와 각도를 그대로 변환한 값입니다. 공급사 미리보기에서 방향이 다르면 해당 부품을 회전시킨 뒤 다시 확인합니다. [KiCad 원본 좌표](fabrication/R5-hub-back-positions-mm.csv) · [TI 1번 핀 도면](https://www.ti.com/lit/ds/symlink/tps2557.pdf)

| 위치 | 부품 | JLCPCB 품번 |
| --- | --- | --- |
| U1–U3 | TPS2557DRBR | [C130056](https://jlcpcb.com/partdetail/TexasInstruments-TPS2557DRBR/C130056) |
| C3–C5 | CC0603KRX7R9BB104, 100 nF, 50 V, X7R, ±10%, 0603 | [C14663 (Basic)](https://jlcpcb.com/partdetail/C14663) |
| R4–R6 | RT0603BRD0761K9L | [C861498](https://jlcpcb.com/partdetail/YAGEO-RT0603BRD0761K9L/C861498) |

Economic 실장에서 C3–C5는 같은 Basic 품번으로 넣습니다. 이전 Extended 커패시터 대비 피더 교체비가 품번 한 종류분 줄어듭니다. 공개 단가는 주문당 **US$3.07**이며, 실제 금액과 부품 재고는 견적에서 확인합니다. [JLCPCB 실장 가격표](https://jlcpcb.com/help/article/pcb-assembly-price)

![A4 밑면에서 U1–U3의 1번 핀은 각 몸체의 오른쪽 위에 있습니다.](fabrication/R5_Servo_Hub_A4-bottom-placement.png)

### 관통홀 부품 수납땜

받은 기판에서 U1–U3의 1번 핀 방향을 위 그림과 대조합니다. 직접 실장할 경우에는 별도 밑면 스텐실로 SMD를 먼저 리플로우합니다. C1·C2, D1·D2, F1·F2, J1–J8, R1–R3을 윗면에서 끼우고 기판을 고정한 뒤 밑면에서 납땜합니다. [전체 허브 부품표](servo-hub/BOM.csv) · [밑면 스텐실](fabrication/R5_Servo_Hub_A4-Stencil.zip)

밑면 동박 가장자리 간격은 **F1과 U1·U2 사이 약 0.26–0.27 mm**, C1의 2번 패드와 C5 사이 약 0.81 mm, J4–J6의 3번 패드와 R4–R6 사이 약 1.13 mm입니다. 주변이 열린 쪽에서 폭이 작은 평팁을 대고 관통홀 패드와 다리를 함께 가열합니다. 납땜 후 확대경으로 납 브리지, 납땜이 덜 된 관통홀, 밀린 밑면 부품이 있는지 확인합니다. 첫 통전 전에 퓨즈와 외부 배선을 분리한 채 입력·출력 양극의 GND 단락 여부도 확인합니다. [A4 PCB](servo-hub/R5_Servo_Hub.kicad_pcb)

## 전원과 배선

### 전원 실물 검수

**허브를 받침에 넣기 전에 작업대에서 확인합니다.** 내부 J1·J2는 같은 XT30이므로 12 V 플러그가 J1에도 들어갑니다. F1이 장착된 상태에서 J1에 12 V를 넣으면 모터를 빼 두어도 TPS2557의 절대최대 **7 V**와 C1의 정격 **10 V**를 넘어 부품이 손상될 수 있습니다. F1은 과전류 퓨즈입니다. 두 퓨즈를 뺀 채 아래 순서로 입력을 확인합니다. [TPS2557 데이터시트 7.1·7.3절](https://www.ti.com/lit/ds/symlink/tps2557.pdf)

1. **두 어댑터를 AC와 하네스에서 분리하고 USB를 뽑습니다. 모터와 OpenRB를 허브에서 분리하고 F1·F2를 뺍니다.** W3/W4 양쪽 끝에 `J1 · 5 V`, W8/W9 양쪽 끝에 `J2 · 12 V`를 표시합니다. 뒤쪽 XT60 두 곳에는 각각 `12 V IN`과 `12 V SERVICE`를 표시합니다. 하네스의 양극과 GND를 도통으로 추적하고, 5 V 양극·12 V 양극·GND 사이에 단락이 없는지 확인합니다. 각 어댑터는 하네스에 꽂기 전에 DC 출력 전압과 극성을 재고 AC에서 다시 분리합니다.
2. 무전원에서 J1·J2 패드 2와 도통되는 각각의 F1·F2 입력 접점(패드 1)을 찾습니다. **퓨즈를 뺀 채** 검증한 플러그를 꽂습니다. 12 V를 확인할 때는 무전원에서 `12 V SERVICE`도 결합합니다. TP3에 멀티미터 검정 리드를 댑니다. 어댑터를 한 개씩만 켜서 5 V는 **F1 입력 접점**, 12 V는 **F2 입력 접점**에 나타나는지 확인합니다. 공급 전압이 반대쪽 입력에 나타나거나 극성이 다르면 전원을 분리하고 배선을 고친 뒤 처음부터 확인합니다. 턱 5 V 분기는 F1 앞에 있어 이 단계에서도 5 V를 켜면 전압이 걸립니다.
3. 두 어댑터를 AC에서 다시 분리하고 F1·F2 입력 전압이 0 V로 내려간 뒤 **F1 7.5 A, F2 4 A**를 장착합니다. 모터·OpenRB·USB를 분리한 채 아래 표대로 한 계통씩 확인합니다.

   | 연결할 어댑터 | TP3(GND) 기준 | 모터를 꽂기 전 출력 핀 2 |
   | --- | --- | --- |
   | 5 V만 | TP1 약 +5 V | J4–J6 약 +5 V, 2 A 인라인 퓨즈 뒤 턱 ID6 EH 약 +5 V |
   | 12 V만 | TP2 약 +12 V | J7·J8 약 +12 V |

4. 두 어댑터를 AC에서 분리하고 출력 전압이 0 V로 내려간 뒤 **J2 쪽 두 홀(KiCad H2·H4)에 잠금쇠를 고정**합니다. 잠금쇠가 플러그 뒤턱을 잡는지 확인한 다음 허브를 받침에 넣습니다. OpenRB와 모터는 아래 핀을 확인한 뒤 무전원에서 연결합니다. [B25 조립 순서](../mechanical/revisions/b25/assembly.md#전원-커넥터와-배선)

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

U1–U3의 61.9 kΩ 설정에서 TI 특성표의 출력 제한은 **1.590 / 1.785 / 1.960 A**(최소 / 대표 / 최대)입니다. 저항값에 따른 근사식의 하한은 약 **1.54 A**이고 XL330의 5.0 V 공칭 정지 전류는 **1.47 A**입니다. 과전류 시 출력 전압이 내려가고, 과부하가 계속되면 온도에 따라 차단과 재시동을 반복할 수 있습니다. **FAULT 8번은 미연결**이라 LED와 OpenRB에 채널별 경보가 없습니다. 눈·눈꺼풀 기동에서 출력이 떨어지거나 모터가 리셋되면 TP1과 해당 J4–J6의 2번 핀을 비교하고 해당 채널의 전류와 온도를 확인합니다. TI는 출력의 과도 전류가 클 때 개별 출력 커패시터를 권장하며, A4의 개별 커패시터 C3–C5는 입력에 있습니다. J7·J8의 12 V는 공통 F2 4 A로 보호되므로 P08에서 두 분기 배선의 피복과 눌림을 확인합니다. [TPS2557 특성표·과전류 동작·설정식](https://www.ti.com/lit/ds/symlink/tps2557.pdf) · [XL330 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [A4 회로도](servo-hub/R5_Servo_Hub.kicad_sch)

## 제작 치수와 전원 계산

A4의 JST PH 11개 패드(J3–J6)는 **1.35 × 1.75 mm / Ø0.75 mm**입니다. J1·J2 각각 **5.00 mm 피치**, **Ø1.90 mm 단자홀 2개**, **Ø1.00 mm 고정홀 2개**를 쓰며, 도금 고정홀의 동박 패드는 Ø1.60 mm입니다. J1 풋프린트의 `P2.50mm` 표기는 이전 이름이며 두 자리의 구매품은 **5.00 mm 피치 XT30PW-M**입니다. [AMASS XT30PW-M 제조사 도면](https://www.tme.eu/Document/6eb2005a51a52592b3f19e8a450c54c8/XT30PW-M.pdf)

도금 부품홀 51개의 최소 설계 링 0.300 mm는 JLCPCB의 2층 2 oz 기준 **0.254 mm**를 충족합니다. 비아 25개는 Ø0.70 또는 Ø0.90 mm 패드에 Ø0.35 mm 드릴을 사용합니다. KiCad 9.0.2에서 ERC, DRC, 미연결, 회로도 대조 각 0건입니다. [JLCPCB 제작 한계](https://jlcpcb.com/capabilities/pcb-capabilities/)

동박 검토는 어댑터 공칭값 **5.0 V와 12 V** 및 모터의 카탈로그 정지 전류를 적용했습니다. XL330은 5.0 V에서 1.47 A, XL430은 12 V에서 1.40 A입니다. 합계는 5 V 분기 전 5.89 A, J1·F1 4.42 A(허브 10 mA 포함), J2·F2 2.80 A입니다. [XL330-M077 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications) · [XL330-M288 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#specifications) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#specifications)

공칭 공급과 카탈로그 정지 전류를 동시에 넣은 배선 모델의 최저 계산값은 **5 V 계통 J5에서 4.197 V**, **12 V 계통 J8에서 11.472 V**입니다. 12 V는 W6–W9·W35·W36의 재단용 전선 전체와 추가 정비 접점 **12 mΩ 가정값**을 포함했습니다. 5 V는 W33·W34가 각각 250 mm인 조건입니다. 두 값 모두 모델 추정이며 실제 어댑터 부하 조정률과 순간 강하는 P07에서 잽니다. [재단표](../mechanical/WIRING-CUT-LIST.csv) · [실물 구동 측정](#구동-중-전원-확인)

SPD1168X의 부하 시 5.17 V와 1.55 A/축을 적용하던 별도 스트레스 계산은 `--bench`로 재현합니다. 같은 스트레스 모델에 `--input-5v 5.0`을 넣으면 J5는 **4.155 V**로 과거 검토 기준 **4.27 V**에 못 미칩니다. 4.27 V는 이전 설계 검토값이며, XL330의 제조사 동작 하한은 3.7 V입니다. 실제 구동 전압을 기록한 뒤 전압 강하가 어댑터 쪽인지 배선·퓨즈·채널 쪽인지 분리해서 확인합니다. [계산 코드](power_check.py) · [XL330 제조사 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#specifications)

| 양극 경로 | 공통부 선폭과 전류 | 모터별 분기 선폭과 전류 |
| --- | --- | --- |
| 5 V | 2.30–2.35 mm, 4.42 A | 제한기 앞 최소 0.32 mm, 뒤 최소 0.38 mm, 1.47 A |
| 12 V | 2.20–2.40 mm, 2.80 A | 1.25 mm, 1.40 A |

IPC-2221 외층 단일 트랙에 동박 두께 60 µm를 적용하면 온도 상승은 5 V 공통부 약 4 °C, 12 V 공통부 약 2 °C, 가장 좁은 5 V 분기 약 9 °C로 추정됩니다. 5 V 분기의 Ø0.35 mm 비아는 JLCPCB의 평균 도금 두께 18 µm에서 약 1.6 mΩ 및 3.4 mW입니다. PCB 양극 동박의 전압 강하 추정은 J4–J6 **32.3–45.3 mV**, J7 **18.2 mV**, J8 **12.4 mV**입니다. GND는 양면 동박 면으로 연결됩니다. [동박 전압 강하 계산](power_check.py) · [KiCad 트랙 폭 계산 기준](https://docs.kicad.org/9.0/en/pcb_calculator/pcb_calculator.html#track-width) · [JLCPCB 비아 도금](https://jlcpcb.com/capabilities/pcb-capabilities/)

## 재현

저장소 루트에서 KiCad 9의 `kicad-cli`와 `pcbnew`가 설치된 Python으로 실행합니다. 회로·PCB 검사와 BOM 대조 후 `build/electronics/servo-hub/`에 Gerber, 업로드용 BOM·CPL, KiCad 원본 좌표와 스텐실을 생성합니다.

```sh
/usr/bin/python3 electronics/power_check.py
/usr/bin/python3 electronics/export.py servo-hub
```

회로도, PCB, 3D와 발주 자료는 단일 HTML로 생성할 수 있습니다. KiCad 9의 3D 라이브러리와 `npm ci --prefix web`이 필요합니다. 기판 원점 `100x80mm`로 이미 내보낸 A4 GLB가 있으면 `--glb`로 넘길 수 있습니다.

```sh
/usr/bin/python3 web/wiring-review/a4/build.py build/R5-B25-A4-KiCad.html
```

## 이전 전장 검토 기록

**서보 허브 A3** 제작 파일은 개정 이력으로 보관합니다. B25 발주에는 위 A4 파일을 사용합니다. [A3 Gerber·드릴](fabrication/R5_Servo_Hub_A3-Gerbers.zip) · [A3 스텐실](fabrication/R5_Servo_Hub_A3-Stencil.zip)

**ESP32-C3 A1**은 B25 발주 범위 밖의 별도 RF 실험입니다. [C3 KiCad 원본](c3-rf/) · [이전 C3 제작·실장 기록](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/electronics/README.md#c3-첫-동작)

### 외부 전원 보호 계산

외부 보호 시안의 계산은 A3 길이를 기준으로 하고, 정비 루프 저항은 별도 입력으로 받습니다. [이전 전원과 보호 계산](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/electronics/README.md#외부-전원-보호-계산)
