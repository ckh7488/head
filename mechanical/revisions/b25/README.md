# R5 B25 제작 자료

B25 기구는 A4 서보 허브와 OpenRB-150을 사용합니다. P2S 일괄 출력은 **14판·57개**, 표준 재질은 **Bambu PETG-CF 2롤**(65 °C 8시간 건조, Bambu Studio에서 `Bambu PETG-CF @BBL P2S` 프리셋 선택 후 재슬라이스; 기준 PETG HF 기록 약 `67시간 51분·1.285 kg`)입니다. **13번 턱 판부터** 출력합니다. [전 판 슬라이스 기록](print-build.json)

## 출력에서 첫 구동까지

| 할 일 | 파일과 절차 |
| --- | --- |
| 출력 | [P2S 3MF](R5-B25-P2S.3mf) · [01 서울 출력과 후가공](01-seoul-print.md) · [02 먼저 살 부품](02-order-before.md) |
| 건식 맞춤 | [맞춤 게이지와 치수별 파일](fit-gauge.md)에서 끼움, 공구 접근과 턱 받침 간극을 확인합니다. |
| 모터·전장 구매 | 건식 맞춤 후 [03 시험 뒤 살 부품](03-order-after.md) · [A4 PCBA 발주](../../../electronics/README.md#jlcpcb-밑면-실장) |
| 허브 첫 통전 | 조립 전에 작업대에서 모터와 OpenRB를 분리하고 [퓨즈를 뺀 첫 통전](../../../electronics/README.md#전원-실물-검수)부터 진행합니다. |
| 조립과 보정 | 전원을 뽑고 J2를 잠근 뒤 [조립과 배선](assembly.md) · [OpenRB와 축별 보정](../../../control/README.md)을 진행합니다. |
| 움직임과 인수 | [실물 시험 P01–P08](../../../spec/bench.md#b25-실물-시험) · [디지털 검사 결과와 범위](alignment.md) |

## 조립에 필요한 상세 자료

- [FreeCAD 조립본](R5-B25-Assembly.FCStd) · [웹 제작 안내](https://r5-b1-review.ckh.chatgpt.site/b25/guide/) · [3D 조립·구동·배선 화면](../../../web/README.md#b25-웹-화면)
- [B25 변경 부품표](BOM.csv) · [전선 재단표](../../WIRING-CUT-LIST.csv) · [XL330 케이스 나사 배정](xl330-case-screws.md)
- [오른쪽 목 상하축 도면·STEP](pitch-drive-shaft.md) · [목 스토퍼와 보정](neck-yaw-travel.md) · [카메라 USB 선재](camera-cable-options.md) · [A4 12 V 정비 배선](j2-supply-delta.md)

## 판정과 기록

완성품 조립, 유격, 5 N 강건성, 실제 전원·USB와 구동은 P01–P08에 기록합니다. 설계 배경과 이전 시안은 검증 기록에서 볼 수 있습니다. [1층 사람 요구사항](../../../spec/user-spec.md) · [2층 검사 조건](../../../spec/conditions.md) · [FDM 실수 모음집](../../../spec/fdm-pitfalls.md) · [1회 출력 감사](audit-loop.md) · [항목별 이전 판정](review-disposition.md) · [이전 리비전](../)

<details>
<summary>형상과 검사 기록</summary>

- [조립과 구동](alignment-checks.json) · [타이바 삽입](eye-yaw-clearance.json) · [턱 받침–요크](yoke-jaw-cut.json) · [목 핀 자리](pitch-pin-ligament.json) · [시선 광선](sightlines.json)
- [XT60 체결·삽입](xt60-collar-clearance.json) · [정비 덮개](cover-service.json) · [A4 전원과 정비](a4-supply-recheck.json)
- [형상 파일과 해시](design.json) · [전 판 슬라이스](print-build.json) · [베어링 시편](bearing-fit.json) · [대형 베어링 자리](fit-large-bearings.json) · [Ø8 축 맞춤](shaft-fit.json) · [핀 치수별 검사](pin-fit-options-check.json)
- [초기 장공](eye-yaw-slot.json) · [뒤 외장 왼쪽 나사](rear-left-screw-fit.json) · [초기 정밀 슬라이스](print-precision-check.json) · [눈꺼풀 형상](blink-fit.json) · [초기 판정](frozen-fixes-check.md) · [이전 Eaton 경로](camera-r18-recheck.json) · [이전 목 스토퍼](neck-load-study.md)

</details>
