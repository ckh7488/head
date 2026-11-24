# B25 A5 서보 허브

손납땜을 쉽게 만든 4층 보드입니다. 70 × 35 mm 외곽, H1–H4 고정홀, J1–J8의 위치와 핀 배치는 기존 B25 받침에 맞췄습니다. [오프라인 뷰어](../../web/b25/R5-B25-A5.html) · [회로도](R5_Servo_Hub.kicad_sch) · [PCB](R5_Servo_Hub.kicad_pcb) · [전체 BOM](BOM.csv)

## 손납땜

| 작업 | 부품 |
| --- | --- |
| JLCPCB 밑면 실장 12개 | U1–U3 전류제한기, C3–C5 바이패스, R1–R6 저항 |
| 윗면에 끼워 밑면에서 납땜 14개 | J1–J8, F1·F2 퓨즈 홀더, C1·C2 전해콘덴서, D1·D2 LED |

R1·R2는 1206, R3는 0805 규격입니다. 이 저항 세 개를 공장 실장으로 옮겨 손납땜할 도금홀을 47개에서 41개로 줄였습니다. F1 패드와 밑면 SMT 사이 동박 간격은 0.26 mm에서 **2.24 mm**로 늘었습니다. XT30 고정핀을 포함한 손납땜 패드에서 밑면 SMT 몸체까지 공칭 최소 거리는 **2.05 mm**입니다.

| 부품 | 작업할 때 볼 곳 |
| --- | --- |
| J3–J6 JST PH | 2.00 mm 피치에 패드 사이 0.65 mm입니다. 1.2–1.6 mm 평팁으로 한 핀씩 붙인 뒤 브리지를 확인합니다. |
| J1·J2 전원, F1·F2 퓨즈 홀더, C1 음극 | XT30 양극과 퓨즈 홀더에는 여러 층의 전원 배선이 이어집니다. C1 음극은 L2의 넓은 GND 배선에 연결됩니다. 열 회복이 빠른 온도조절 인두와 2.4 mm 안팎의 평팁으로 핀과 패드를 함께 가열합니다. |

처음 한 장은 XT30과 퓨즈 홀더를 끝까지 끼워 모든 핀이 함께 들어가는지 확인합니다. 퓨즈 홀더의 홀은 Ø1.78 mm이고 제조사 도면의 최소는 Ø1.60 mm입니다. 홀더 한 곳에서 납이 핀과 패드 양쪽에 잘 젖는지 본 뒤 나머지를 붙입니다. 실물 접합은 시제품에서 확인합니다. [AMASS 도면](https://www.tme.eu/Document/6eb2005a51a52592b3f19e8a450c54c8/XT30PW-M.pdf) · [Keystone 3568 도면](https://www.keyelco.com/product-pdf.cfm?p=306) · [HAKKO 팁 선택](https://www.hakko.com/english/support/maintenance/detail.php?seq=171)

## 견적

**70 × 35 mm · FR-4 1.6 mm · 4층 · 외층 1 oz · 내층 0.5 oz · 녹색 · 무연 HASL**로 2장 견적을 받습니다. Economic PCBA의 Bottom을 선택합니다. 공개 조건에 맞춘 구성으로, 실제 견적의 표면처리 조합과 재고·실장 단가를 확인합니다. [JLCPCB 실장 조건](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) · [표준 적층](https://jlcpcb.com/impedance)

**U2를 따로 확인합니다.** CPL은 U1·U3 **0°**, U2 **90°**입니다. HTML의 밑면 그림과 같은 방향으로 기판을 보면 U1·U3의 1번 핀은 오른쪽 아래, U2는 왼쪽 아래입니다. JLCPCB 미리보기에서 각 칩의 몸체 점을 그림의 1번 핀과 대조합니다. 업체가 노출 방열패드의 평탄도를 지적하면 같은 실장 조건으로 ENIG도 비교합니다. [JLCPCB 회전 확인](https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2) · [표면처리 비교](https://jlcpcb.com/help/article/jlcpcb-surface-finish) · [TI 패키지 도면](https://www.ti.com/lit/ds/symlink/tps2557.pdf)

- [Gerber·드릴](../fabrication/R5_Servo_Hub_A5-Gerbers.zip) · [JLCPCB BOM](../fabrication/R5_Servo_Hub_A5-JLCPCB-BOM.csv) · [JLCPCB CPL](../fabrication/R5_Servo_Hub_A5-JLCPCB-CPL.csv)
- [스텐실](../fabrication/R5_Servo_Hub_A5-Stencil.zip) · [리플로우 후 납땜·첫 통전](../README.md#전원-실물-검수)

첫 통전은 F1·F2 퓨즈, 모터, OpenRB를 뺀 상태에서 진행합니다. 어댑터를 하나씩 켜 F1 입력에 +5 V, F2 입력에 +12 V가 들어오는지 확인합니다. 출력 검수 뒤에는 전원을 분리하고 J2 잠금쇠를 고정합니다. [전원 실물 검수](../README.md#전원-실물-검수)

## 검증

L2는 GND 면입니다. DATA 주 배선은 그 위에 두었습니다. L3에 전원 동박을 배치하고 5 V와 12 V의 입력 고전류 구간을 바깥 면과 병렬로 이었습니다. 5 V 퓨즈 앞뒤와 12 V 퓨즈 앞뒤는 서로 다른 넷입니다.

KiCad 9 ERC·DRC·회로도 대조를 통과했습니다. B25 조립 CAD에서 밑면 부품의 높이 1.2 mm 외형을 대입했습니다. 하부 덮개와 최소 1.88 mm 떨어지고 덮개를 30 mm 내리는 구간에서 새 간섭이 없었습니다. [B25 조립 CAD](../../mechanical/revisions/b25/R5-B25-Assembly.FCStd)

공칭 5 V에서 허브 4.42 A와 각 눈·눈꺼풀 분기 1.47 A의 하중을 적용했습니다. 동박 면과 병렬 경로를 0.10 및 0.15 mm 격자로 근사한 5 V 양극 경로의 전압강하는 약 36–43 mV입니다. 배선과 접촉저항을 포함한 최저 모터 단자 전압은 약 4.25 V로 추정합니다. 동박 면을 빼고 한 경로씩 계산하는 아래 전원 스크립트의 보수적 추정은 J5에서 4.105 V입니다. 첫 구동 때 P07에서 실제 전압과 온도를 잽니다. [P07 실물 시험](../../spec/bench.md#p07-카메라-왕복과-전원)

TPS2557 입력의 폭 0.35 mm, 길이 0.93 mm 구간에 1.47 A 전부를 적용하면 고온 동박 두께 30 µm 가정에서 약 **2.7 mV, 4 mW**입니다. 채널 제한 상한 1.96 A에서는 약 **3.6 mV, 7 mW**입니다. 같은 위치의 배선 폭은 이 추정으로 유지하고, P07에서 실제 부하 전압과 온도를 확인합니다.

```sh
/usr/bin/python3 electronics/export.py servo-hub-a5
/usr/bin/python3 electronics/power_check.py --hub-revision A5
/usr/bin/python3 web/wiring-review/a4/build.py --hub-revision A5 --xt30-step /path/to/XT30PW-M.step build/R5-B25-A5.html
```

제작 파일은 `build/electronics/servo-hub-a5`에 생성됩니다. HTML은 저장소에 포함된 `electronics/fabrication`의 A5 파일을 읽으며, KiCad 9의 3D 모델과 `npm ci --prefix web`이 필요합니다.

`--xt30-step`은 전원핀 중심이 (±2.5, 8.5) mm, 고정핀이 (±5.5, −1.5) mm인 원본 모델을 받습니다. 뷰어를 내보낼 때만 모델을 보정하고 GLB의 핀 8개가 PCB 홀 중심에 맞는지 검사합니다. 이미 같은 위치로 내보낸 GLB가 있으면 `--glb`로 넘길 수 있습니다. U1–U3 STEP이 없으면 TI 패키지 치수에 맞춘 외형과 1번 핀이 표시됩니다. [TI 패키지 도면](https://www.ti.com/lit/ds/symlink/tps2557.pdf)
