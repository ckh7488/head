# R5 로봇 헤드

R5는 코에 숨긴 카메라로 지나가는 사람을 보고, 눈이 먼저 움직인 뒤 목이 천천히 따라가는 **6축 해골 로봇**입니다. PC가 얼굴을 찾고 OpenRB-150이 모터 여섯 축을 제어합니다. 전시 모드에서는 눈을 깜빡이며, 턱은 별도 시연 모드에서 움직입니다.

![B25 조립 CAD에서 본 해골 로봇](web/assets/b25-motion/assembly-poster.webp)

현재 제작 자료는 **B25 기구와 A5 서보 허브**를 기준으로 합니다. P2S 출력은 PETG HF **18판·57개**입니다. 완성품 조립과 구동에 필요한 P01–P08 실물 시험이 남아 있습니다. [B25 제작 자료](mechanical/revisions/b25/) · [검증 결과와 범위](mechanical/revisions/b25/alignment.md)

## 제작 순서

| 순서 | 할 일 |
| --- | --- |
| 1. 출력 준비 | 핀·베어링·나사를 준비합니다. 한 번에 맡길 때는 **15번 링크 판**으로 바닥 접지를 확인한 뒤 **13번 턱 판**으로 큰 부품의 출력 상태를 확인합니다. [서울 출력](mechanical/revisions/b25/01-seoul-print.md) · [먼저 살 부품](mechanical/revisions/b25/02-order-before.md) |
| 2. 건식 맞춤 | 끼움, 공구 접근, 오른쪽 턱 받침과 요크 사이 틈을 전원과 접착제 없이 확인합니다. [맞춤 게이지](mechanical/revisions/b25/fit-gauge.md) |
| 3. 모터·전장 구매 | 건식 맞춤을 마친 뒤 모터·카메라·A5 허브를 준비합니다. [시험 뒤 구매](mechanical/revisions/b25/03-order-after.md) · [A5 PCBA 발주](electronics/README.md#jlcpcb-밑면-실장) |
| 4. 허브 첫 통전 | 허브를 받침에 넣기 전에 작업대에서 확인합니다. 모터와 OpenRB는 분리하고, J2를 잠그고 퓨즈를 뺀 상태에서 입력부터 확인합니다. [전원 실물 검수](electronics/README.md#전원-실물-검수) |
| 5. 조립과 보정 | 허브의 전원을 뽑고 조립·배선합니다. 무전원에서 배선을 확인하고, 전원을 켜서 한 축씩 보정합니다. [조립 절차](mechanical/revisions/b25/assembly.md) · [구동과 보정](control/README.md) |
| 6. 실물 인수 | 완성품의 조립 상태, 움직임, 전압과 전원 복구를 확인합니다. [실물 시험 P01–P08](spec/bench.md#b25-실물-시험) |

## 주요 사양

| 항목 | B25 적용값 |
| --- | --- |
| 머리 외형과 환경 | 약 `160 × 166 × 167 mm`, 한국 실내 `−5–35 °C` |
| 3D 프린팅 | **Bambu Lab P2S** (0.4 mm 경화 노즐), **Bambu PETG HF** (65 °C 4–6시간 건조 · 2롤), 18판·57개 |
| 눈과 턱 (5 V) | ID1–ID3 `XL330-M077-T` × 3, ID6 `XL330-M288-T` × 1 |
| 목 (12 V) | ID4·ID5 `XL430-W250-T` × 2 |
| 카메라와 제어 | `U20CAM-1080P-S1`, `OpenRB-150` (USB 전원), `A5 서보 허브` |

## 파일과 기준

- [A5 회로도·PCB·3D 단일 HTML](web/b25/R5-B25-A5.html)
- [FreeCAD 조립본](mechanical/revisions/b25/R5-B25-Assembly.FCStd) · [P2S PETG HF 출력 프로젝트](mechanical/revisions/b25/R5-B25-P2S.3mf) · [웹 제작 안내](https://r5-b1-review.ckh.chatgpt.site/b25/guide/) · [핀별 배선도](https://r5-b1-review.ckh.chatgpt.site/b25/wiring/diagram/) · [3D 조립·구동·배선 화면 만들기](web/README.md#b25-웹-화면)
- [1층 사람 요구사항](spec/user-spec.md) · [2층 수치 기준](spec/conditions.md) · [FDM 실수 모음집](spec/fdm-pitfalls.md) · [동작 인수 기준](spec/requirements.md)
- [기구 자료](mechanical/README.md) · [전장 자료](electronics/README.md) · [하드웨어 없이 테스트](control/README.md#하드웨어-없이-실행) · [이전 리비전](mechanical/revisions/)
