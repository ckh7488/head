# R5 B25 발주와 조립 변경

[B25 발주표](BOM.csv) · [B25 기구 검토](README.md) · [B24 기본 조립 절차](../b24/assembly.md)

## 모터와 케이스

작업대에서 ID1·ID2·ID3에는 XL330-M077-T를, ID6에는 XL330-M288-T를 맞춥니다. 출력 모터판과 턱 받침의 관통 구멍을 지나 **ROBOTIS 케이스**에 물리는 자리에만 모터 동봉 **PHS M2×8 TAP 11개**와 **PHS M2×6 TAP 5개**를 씁니다. 모터별 조립 표시와 구멍 ID는 자리별 표를 따릅니다. [케이스 나사 배정과 실물 확인](xl330-case-screws.md)

공통 부품표 E2의 ISO 4762 M2×6 원통머리는 B25에서 **깜빡임 혼 19에 2개, 턱 구동팔 38에 2개**를 사용합니다. [이전 개정 공통 부품표](../../BOM.csv)

## 5 V 커넥터와 RF 부품

**XT30U-F 두 개** 중 하나는 외부 5 V 전원 출력 꼬리에, 다른 하나는 허브 J1에 꽂을 W3·W4에 납땜합니다. 허브 J1에는 기판용 XT30PW-M, 외부 전원과 만나는 로봇 꼬리에는 XT30U-M이 들어갑니다. [AMASS XT30U](https://www.china-amass.com/biao/268.html) · [배선과 극성](../../../electronics/README.md#전원과-배선) · [전선 재단표](../../WIRING-CUT-LIST.csv)

ESP32-C3 안테나 보드, 전용 왼쪽 캐리어와 클램프, 해당 체결품은 이번 발주와 조립에서 제외합니다. [RF 실험 원본](../../../electronics/c3-rf/)


## 뒤 외장 나사

프레임의 열린 슬롯에 일반 M3 육각너트 두 개를 먼저 넣습니다. 뒤 외장 29를 끼운 뒤 **왼쪽 M3×18, 오른쪽 M3×16** 원통머리 나사를 바깥에서 넣고 2.5 mm L자 육각렌치로 조입니다. 왼쪽 프레임은 같은 축의 Ø3.52 mm 홀을 2.50 mm 연장했습니다. 왼쪽 외장의 Ø3.90 × 0.75 mm 단차는 나사 머리 밑 목 부분의 여유입니다. 머리는 바깥쪽 평면에 닿습니다. [나사와 공차 검사](rear-left-screw-fit.json)

최단 M3×18과 불완전 끝 나사산 1.0 mm, 출력 치수 공차를 적용하면 왼쪽 너트 밖에 완전한 나사산 **0.81 mm**가 남습니다. 최장 나사 끝의 홀 바닥 여유는 **0.10 mm**입니다. 실제 출력 후 머리가 평면에 밀착하고 나사가 홀 바닥에 먼저 닿지 않는지 확인합니다. [ISO 4762](https://standards.theiteh.com/catalog/standards/iso/491e2f65-2018-40a8-b442-a6b8d113334d/iso-4762-2004) · [Bossard 나사](https://www.bossard.com/kr-ko/eshop/screws-and-bolts-with-internal-drive/hex-socket-head-cap-screws-fully-threaded/p/3/)
