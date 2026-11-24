# B25 A6 서보 허브

전 부품을 직접 납땜하는 4층 시안입니다. 기판 앞쪽을 2 mm 늘려 70 × 37 mm로 만들고, 밑면의 보호 칩 세 개를 한 줄로 배치했습니다. H1–H4와 J1–J8의 위치·홀·핀 연결은 A5와 같습니다. [오프라인 뷰어](../../web/b25/R5-B25-A6.html) · [회로도](R5_Servo_Hub.kicad_sch) · [PCB](R5_Servo_Hub.kicad_pcb) · [전체 BOM](BOM.csv)

## 납땜과 주문

1. Gerber로 **FR-4 1.6 mm · 4층 · 외층 1 oz · 내층 0.5 oz · 녹색 · 무연 HASL** 생기판을 견적 냅니다. [Gerber·드릴](../fabrication/R5_Servo_Hub_A6-Gerbers.zip) · [JLCPCB 기판 규격](https://jlcpcb.com/capabilities/pcb-capabilities)
2. 밑면 SMD 12개를 먼저 납땜합니다. U1–U3은 다리가 보이는 **TPS25221DBVR, SOT-23-6, 피치 0.95 mm**입니다. 세 칩의 방향은 같으며 HTML의 밑면 그림에 1번 핀이 표시됩니다. R4–R6은 **30.9 kΩ, ±0.1%, ≤25 ppm/°C, 0805**, C3–C5는 **100 nF, 0805, 몸체 높이 1.45 mm 이하**입니다. [TI 데이터시트와 패키지 도면](https://www.ti.com/lit/ds/symlink/tps25221.pdf)
3. 윗면 관통홀 14개를 끼운 뒤 밑면에서 납땜합니다. XT30과 퓨즈 홀더에는 열 회복이 빠른 온도조절 인두와 2.4 mm 안팎의 평팁을 씁니다. F1·F2, 모터와 OpenRB를 뺀 채 5 V와 12 V 입력을 하나씩 검수합니다. [전원 실물 검수](../README.md#전원-실물-검수)

## 검사 결과

- KiCad ERC, DRC, 회로도와 PCB 일치 검사에서 위반 0건입니다.
- 기존 B25 FreeCAD 조립에서 확장한 기판과 새 밑면 SMD 9개의 외형을 넣고, 밑면 덮개 30 mm 하강 경로를 확인했습니다. 기판 외곽과 배치 공차를 포함한 검사에서 기판과 베이스의 겹침은 없었고, 새 부품과 덮개의 최소 간격은 **0.565 mm**였습니다. [B25 조립 CAD](../../mechanical/revisions/b25/R5-B25-Assembly.FCStd)
- 공칭 5 V와 카탈로그 정지전류를 동시에 적용한 보수적 모델에서 최저 모터 단자 전압은 **4.025 V**입니다. 같은 계산에서 A5는 **4.105 V**입니다. TPS25221 자체의 전형 저항은 70 mΩ로 TPS2557의 22 mΩ보다 높습니다. 1.47 A에서 칩 하나의 전압강하는 약 71 mV 늘고 전형 손실은 약 0.05 W에서 0.15 W로 늘어납니다. 칩의 권장 입력 상한은 6.5 V에서 5.5 V로 낮아집니다. 30.9 kΩ 설정의 데이터시트 전류 제한 범위는 1.626–1.907 A입니다. 첫 시제품에서 동작 중 전압, 보호 칩 온도와 전류 제한에 걸리는지 확인합니다. [P07 실물 시험](../../spec/bench.md#p07-카메라-왕복과-전원)

기판 제작 파일은 첫 명령으로 만듭니다. HTML을 재생성하려면 결과 Gerber ZIP을 `electronics/fabrication/`에 두고 KiCad 9의 3D 모델과 `npm ci --prefix web`을 준비합니다. XT30 STEP은 A5 문서의 원본 모델 규격을 따릅니다. [XT30 STEP 좌표](../servo-hub-a5/#검증)

```sh
/usr/bin/python3 electronics/export.py servo-hub-a6
/usr/bin/python3 electronics/power_check.py --hub-revision A6
/usr/bin/python3 web/wiring-review/a4/build.py --hub-revision A6 --xt30-step /path/to/XT30PW-M.step build/R5-B25-A6.html
```
