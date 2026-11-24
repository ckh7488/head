# R5 B25 제작 자료

B25 기구는 A5 서보 허브와 OpenRB-150을 사용합니다. P2S에서 Bambu PETG HF로 **18판·57개**를 출력합니다. **15번 링크**, **13번 턱** 순으로 첫 출력 상태를 봅니다. [판별 출력 기록](print-hf.json)

## 출력에서 첫 구동까지

| 할 일 | 파일과 절차 |
| --- | --- |
| 출력 | [P2S PETG HF 3MF](R5-B25-P2S.3mf) · [01 출력과 후가공](01-seoul-print.md) · [02 먼저 살 부품](02-order-before.md) |
| 건식 맞춤 | [무전원·무접착 예비 맞춤](01-seoul-print.md#출력물-후가공과-건식-맞춤)에서 끼움, 공구 접근과 오른쪽 턱 받침–요크 0.30 mm 간극을 확인합니다. 선택 출력에 쓸 치수는 [맞춤 게이지](fit-gauge.md)로 고릅니다. |
| 모터·전장 구매 | 건식 맞춤 후 [03 시험 뒤 살 부품](03-order-after.md) · [A5 PCBA 발주](../../../electronics/README.md#jlcpcb-밑면-실장) |
| 허브 첫 통전 | 작업대에서 모터와 OpenRB를 분리합니다. 무전원에서 결선을 확인하고 J2를 잠근 뒤 [퓨즈를 뺀 첫 통전](../../../electronics/README.md#전원-실물-검수)부터 진행합니다. |
| 조립과 보정 | 두 어댑터와 뒤 XT60을 분리한 뒤 [조립과 배선](assembly.md) · [OpenRB와 축별 보정](../../../control/README.md)을 진행합니다. |
| 움직임과 인수 | [실물 시험 P01–P08](../../../spec/bench.md#b25-실물-시험) · [디지털 검사 결과와 범위](alignment.md) |

## 조립에 필요한 상세 자료

- [FreeCAD 조립본](R5-B25-Assembly.FCStd) · [웹 제작 안내](https://r5-b1-review.ckh.chatgpt.site/b25/guide/) · [3D 조립·구동·배선 화면](../../../web/README.md#b25-웹-화면)
- [B25 변경 부품 기록](BOM.csv) · [전선 재단표](../../WIRING-CUT-LIST.csv) · [XL330 케이스 나사 배정](xl330-case-screws.md)
- [오른쪽 목 상하축 도면·STEP](pitch-drive-shaft.md) · [목 스토퍼와 보정](neck-yaw-travel.md) · [카메라 USB 선재](camera-cable-options.md) · [J2 잠금·정비](j2-disconnect.md) · [12 V 고정선 조립](j2-supply-delta.md)

## 판정과 기록

완성품 조립, 유격, 5 N 강건성, 실제 전원·USB와 구동은 P01–P08에 기록합니다. [실물 기록 양식](../../../spec/records/README.md) · [A5 회로도·PCB·3D HTML](../../../web/b25/R5-B25-A5.html) 설계 배경과 이전 시안은 검증 기록에서 볼 수 있습니다. [1층 사람 요구사항](../../../spec/user-spec.md) · [2층 검사 조건](../../../spec/conditions.md) · [FDM 실수 모음집](../../../spec/fdm-pitfalls.md) · [초기 1회 출력 감사](audit-loop.md) · [항목별 이전 판정](review-disposition.md) · [이전 리비전](../)

<details>
<summary>형상과 검사 기록</summary>

- [조립과 구동](alignment-checks.json) · [타이바 삽입](eye-yaw-clearance.json) · [턱 받침–요크](yoke-jaw-cut.json) · [목 핀 자리](pitch-pin-ligament.json) · [시선 광선](sightlines.json)
- [XT60 체결·삽입](xt60-collar-clearance.json) · [정비 덮개](cover-service.json) · [A4에서 확보한 공통 정비 경로 근거](a4-supply-recheck.json)
- [형상 파일과 해시](design.json) · [앞 외장 형상 대조](front-shell-sync.json) · [PETG HF 전 판 기록](print-hf.json) · [이전 CF 프로젝트](R5-B25-P2S-CF.3mf) · [이전 CF 검사](print-cf.json) · [베어링 시편](bearing-fit.json) · [대형 베어링 자리](fit-large-bearings.json) · [Ø8 축 맞춤](shaft-fit.json) · [핀 치수별 검사](pin-fit-options-check.json)
- [초기 장공](eye-yaw-slot.json) · [뒤 외장 왼쪽 나사](rear-left-screw-fit.json) · [초기 정밀 슬라이스](print-precision-check.json) · [눈꺼풀 형상](blink-fit.json) · [초기 판정](frozen-fixes-check.md) · [이전 Eaton 경로](camera-r18-recheck.json) · [이전 목 스토퍼](neck-load-study.md)

</details>
