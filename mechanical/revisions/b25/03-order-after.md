# 3. 시험 맞춤 뒤 발주할 전장과 배선

서울 시험에서 끼움 지름을 고르고 P08의 건식 조립과 목 상하 범위의 0.30 mm 간극을 확인한 뒤 아래 부품을 발주합니다. 수량은 **R5 한 대** 기준입니다. 모터·카메라·전원이 필요한 구동과 USB 1,000회 검사는 입고 후 조립품으로 진행합니다. [서울 출력 목록](01-seoul-print.md) · [실물 검사](../../../spec/bench.md#b25-실물-시험)

## 모터·제어기·카메라·전원

| 품목 | 품번 또는 사양 | 수량 | 사용 위치 |
| --- | --- | ---: | --- |
| ROBOTIS XL330-M077-T | `902-0162-000` | 3 | ID1 눈 좌우, ID2 눈 상하, ID3 눈꺼풀 |
| ROBOTIS XL330-M288-T | `902-0163-000` | 1 | ID6 턱 |
| ROBOTIS XL430-W250-T | `902-0135-000` | 2 | ID4 목 좌우, ID5 목 상하 |
| ROBOTIS OpenRB-150 | `902-0183-000` | 1 | 단품 제어기. USB 전원. |
| Innomaker U20CAM-1080P-S1 | 32 × 32 mm UVC 카메라 | 1 | 코. 동봉 1 m 케이블의 키 플러그와 USB-A 꼬리 재사용. |
| 정전압 DC 5.0 V / 8 A 어댑터 | 예시 GlobTek `GTM96600-4005-T3` | 1 | 눈·눈꺼풀·턱, 외부 XT30 |
| 정전압 DC 12 V / 5 A 어댑터 | 출력 조정 가능품 | 1 | 두 XL430, 외부 XT60 |
| R5 서보 허브 A4 | 70 × 35 mm, 2층 FR-4 1.6 mm, 양면 완성 동박 2 oz, ENIG, 녹색 솔더마스크 | 실장 1대분 | PCB 제작 최소 수량은 업체에서 확인. |

XL330 네 상자의 케이스용 동봉 나사를 사용합니다. B25 범위에서는 ESP32-C3 A1과 전용 왼쪽 캐리어·클램프를 제외합니다. [B25 BOM](BOM.csv) · [M077](https://www.robotis.com/shop/item.php?it_id=902-0162-000) · [M288](https://www.robotis.com/shop/item.php?it_id=902-0163-000) · [XL430](https://www.robotis.com/shop/item.php?it_id=902-0135-000) · [OpenRB-150](https://www.robotis.com/shop/item.php?it_id=902-0183-000) · [U20CAM](https://github.com/INNO-MAKER/U20CAM-1080P-S1)

## A4 허브 1대분 실장 부품

| 위치 | 발주 품번 또는 사양 | 수량 |
| --- | --- | ---: |
| C1 · C2 | Panasonic `EEU-FR1A471` 470 µF/10 V, `EEU-FR1E221` 220 µF/25 V | 각 1 |
| C3–C5 | Murata `GRM188R71C104KA01D` 100 nF 0603 | 3 |
| D1 · D2 | 3 mm 확산형 LED 녹색·황색, 피치 2.54 mm | 각 1 |
| F1 · F2 홀더 | Keystone `3568` MINI 블레이드 퓨즈홀더 | 2 |
| F1 · F2 퓨즈 | Littelfuse `029707.5L` 7.5 A, `0297004.WXNV` 4 A | 각 1 |
| J1 · J2 | AMASS `XT30PW-M` | 2 |
| J3 | JST `B2B-PH-K-S` | 1 |
| J4–J6 | JST `B3B-PH-K-S` | 3 |
| J7 · J8 | JST `B3B-EH-A` | 2 |
| R1–R3 | 0 Ω, 1 kΩ, 3.3 kΩ 축형 ¼ W, 피치 7.62 mm | 각 1 |
| R4–R6 | Yageo `RT0603BRD0761K9L` 61.9 kΩ, 0.1%, 25 ppm/°C | 3 |
| U1–U3 | Texas Instruments `TPS2557DRBR` | 3 |

Gerber·드릴 ZIP으로 제작합니다. 스텐실과 실장 좌표는 밑면 SMD용입니다. 표의 XT30PW-M 2개는 B25 BOM의 J6-P와 동일합니다. [A4 Gerber·드릴](../../../electronics/fabrication/R5_Servo_Hub_A4-Gerbers.zip) · [A4 스텐실](../../../electronics/fabrication/R5_Servo_Hub_A4-Stencil.zip) · [밑면 좌표](../../../electronics/fabrication/R5-hub-back-positions-mm.csv) · [A4 BOM](../../../electronics/servo-hub/BOM.csv) · [전원과 실장 안내](../../../electronics/README.md)

## 하네스와 전선

| 품목 | 품번 또는 규격 | 발주량 |
| --- | --- | ---: |
| 전선용 5 V 및 내부 입력 커넥터 | AMASS `XT30U-F` / `XT30U-M` | 3 / 1 |
| 전선용 외부 12 V 커넥터 | AMASS `XT60U-F` / `XT60U-M` | 1 / 2 |
| 뒤 고정 12 V 정비 소켓 | AMASS `XT60E-F` | 1 |
| 12 V · 5 V 분기 | WAGO `221-412` / `221-413` | 2 / 3 |
| JST PH 하우징과 단자 | `PHR-2` / `PHR-3` / `SPH-002T-P0.5S` | 2 / 5 / 30 |
| JST EH 하우징과 단자 | `EHR-3` / `SEH-001T-P0.6` | 12 / 50 |
| 턱 인라인 퓨즈 | Littelfuse `0FHM0003ZXJV-F2` 계열 홀더, MINI 2 A 구성 | 1세트 |
| OpenRB·PC 데이터선 | USB-C 수–USB-A 수 약 30 cm / USB-A 수–USB-A 암 PC까지 길이 | 1 / 2 |
| A4 고정 12 V 선 | Alpha Wire EcoWire `6718`, 12 AWG 적·흑 | 색상별 0.30 m |
| A4 가동 12 V 정비 선 W8·W9 | Alpha Wire EcoWire `6715`, 18 AWG 적·흑, 외경 1.65–1.75 mm | 색상별 준비분 0.25 m, 1가닥씩 가조립 재단 |
| 5 V 배선 | Alpha Wire `3055` 또는 동급 18 AWG 적·흑, 피복 약 Ø2.0 mm | 색상별 1 m |
| 5 V 외부 꼬리 | Alpha Wire EcoWire `6716`, 16 AWG 적·흑 | 색상별 0.30 m |
| 모터·데이터 배선 | Alpha Wire EcoWire `6712` 또는 동급 24 AWG 적·흑·백, 외경 1.04–1.14 mm | 색상별 3 m |
| 공급선 고정 소모품 | 0.05·0.10·0.20 mm 절연 시임 / 폭 2.5 mm 나일론 타이 / 열수축 튜브 | 시임 1세트 / 1개 / 1세트 |

JST 수량은 예비분을 포함한 기존 BOM 발주 수량입니다. 가동 W8·W9의 노출 경로는 각 **170.578 mm**이며 양쪽 단자 삽입분을 더합니다. 고정 W6·W7·W35·W36은 A4 노출 경로, WAGO 탈피 11 mm, XT60 컵 매입 실측을 합산합니다. [A4 공급선 실측·재단](j2-supply-delta.md) · [하네스 재단표](../../WIRING-CUT-LIST.csv) · [공통 기구 BOM](../../BOM.csv) · [B25 변경 BOM](BOM.csv)
