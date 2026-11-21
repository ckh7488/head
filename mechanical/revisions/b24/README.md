# R5 B24 제작과 조립

[FreeCAD 조립본](R5-B24-Assembly.FCStd) · [Bambu Studio P2S 프로젝트](R5-B24-P2S.3mf) · [조립 순서](assembly.md) · [3D 조립 화면 재현](../../../web/README.md#b24-조립-순서) · [원본 B24의 저장 검증 기록](verification.json)

검토 중인 B24 자료입니다. 전체 출력과 일괄 발주는 아래 실물 제작 항목이 해결될 때까지 보류합니다.

Bambu Studio **02.09.01.70**에서 3MF를 프로젝트로 열고 슬라이스했습니다. **P2S 0.4 mm 노즐, Textured PEI, PETG HF, 0.20 mm 레이어** 설정입니다. 전체 12개 판의 슬라이서 추정치는 서포트 포함 **약 1.20 kg, 62시간 32분**입니다. B24의 변경 부품은 4번 판의 앞 외장, 6번 판의 목 클램프, 7번 판의 좌우 눈 베어링 지지대, 8번 판의 왼쪽 눈꺼풀 링크입니다. [출력 경로 검사](slicing-check.json)

## 구입과 가공

- **모터 수량**은 XL330-M077-T **3개**(ID1·2·3), XL330-M288-T **1개**(ID6), XL430-W250-T **2개**(ID4·5)입니다. 공통 부품표 A1·A2의 수량과 ID3 표기는 이 B24 구성으로 대체합니다. [공통 부품표](../../BOM.csv)
- **XL330 케이스 나사** 16곳 중 11곳(눈 좌우 3, 눈 상하 4, 눈꺼풀 2, 턱 2)은 머리 아래에서 나사산 시작점까지 모델 기준 6.20 mm(출력물 2.70 mm + 케이스 입구 3.50 mm)여서 M2×6이 나사산에 닿지 않습니다. 케이스 16곳마다 출력물 두께, 나사산 시작점과 가용 깊이를 실물에서 잽니다. 나사산에 충분히 물리면서 바닥에 닿기 전에 머리가 앉는 길이를 확인한 뒤 구매할 길이별 수량을 확정합니다. [제조사 도면 Detail A](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#drawings) · [조립 모델](hardware.json)
- **B24 추가품**은 NSK MR63ZZMC3P6 베어링 2개, 목 체결용 M3×8 원통머리 육각렌치 나사 1개, 길이 150 mm의 눈 베어링 정렬봉 1개입니다. 공통 부품표 D2는 내륜에 손으로 미끄러지는 Ø3×13 mm 연마핀 2개로 실측 선별하고 크래들 쪽에만 고정합니다. 오른쪽 목 축 C2는 B24 가공표를 따릅니다. [핀 끼움 기준](assembly.md#눈-상하-베어링) · [축 치수와 체결 시험](pitch-coupler.md)

- **5 V 커넥터와 공구**는 XT30U-F 두 개, XT30U-M 한 개를 준비합니다. 공통 부품표 J6의 F 수량에 허브 J1용 한 개를 더합니다. M3 덮개에 쓰는 5.5 mm 스패너의 머리 폭은 13 mm 이하입니다. [전원 배선](../../../electronics/README.md#전원과-배선) · [공통 조립 공구](../b23/assembly.md)

## 목 상하축

D면 접촉과 금속 축의 M3 체결로 토크를 전달합니다. 나사가 들어오는 위쪽과 모터 혼의 순정 M2 네 곳은 실제 머리 크기와 공구 경로를 검사했습니다. 펌웨어의 상하축 PWM 상한은 185이며, 출력축 구동 끝점은 뒤로 13.62°, 앞으로 2.99°입니다. 조립 오차와 최대 구동 하중에서의 탄성 변형 1.35°를 반영한 뒤 물리 스토퍼까지 최소 0.27°가 남았습니다. [체결부 해석](pitch-drive-strength.json) · [스토퍼와 간섭 검사](neck-stop.json) · [전원 차단 계산](coupled-release.json)

조립은 150단계입니다. 모터 전체 메시로 교차 부피를 계산하지 못했던 접촉 쌍 29개는 제조사 모터 형상의 구성 솔리드로 재검사했습니다. 출력물과 모터가 만나는 열 쌍은 교차 부피 0 mm³였습니다. 나사산과 JST 끼움의 단순화된 형상은 구매품의 결합 위치 및 기존 배치와 비교했습니다. [조립 단계별 결과](assembly.json) · [모터 접촉 검사](seated-mates.json)

## 눈꺼풀과 제어

눈꺼풀 ID3은 **XL330-M077-T**, 턱 ID6은 **XL330-M288-T**입니다. 두 제품은 동일한 제조사 외형 STEP을 사용합니다. 눈꺼풀 링크와 혼은 기존 형상이고 개폐 곡선도 같습니다. B24 펌웨어는 ID3 모델을 읽어 M077에 PWM 230을 적용합니다. B23의 M288에는 200을 적용하며, B24 깜빡임 시간 검증은 M077에 해당합니다. [제조사 도면](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#drawings) · [제어와 보정](../../../control/README.md)

눈꺼풀은 단자 전압 4.27–5.25 V, 영상 24–30 fps, 마찰과 명령 시점을 바꾼 4,320개 모델에서 **1.29–1.42초**에 닫혔다 열렸습니다. 입력을 막은 별도 하중 계산에서는 기존 모터를 그대로 두고 구동력을 높이는 방식의 레일 휨이 커서 M077을 사용했습니다. [눈꺼풀 모델](blink-loaded.json) · [레일 탄성 해석](blink-rail.json) · [M07 토크와 실물 판정](../../../spec/records/M07.md)

레일이 휘면 양쪽 눈꺼풀이 다른 각도까지 움직입니다. 왼쪽 외장 안쪽에서 **0.98 mm³**를 덜어냈고, 왼쪽 링크는 핀 둘레를 남겨 닿는 외곽만 깎았습니다. 90° 명령에서 양쪽 관절 마찰과 한쪽 1 N 접촉을 함께 적용했을 때 링크는 0.335 mm, 눈꺼풀은 0.285 mm 이상 외장과 떨어졌습니다. 총 저항 토크 0.036 N·m를 왼쪽 하나에 몰아주는 별도 계산에서는 링크 접촉이 남았습니다. 7번 판의 공통축 베어링 자리는 서포트를 제거한 뒤 Ø10.24 mm로 마감합니다. 두 외륜을 접착제 없이 넣어 레일이 휠 때 미세하게 정렬될 여유를 둡니다. [외장 여유](blink-shell.json) · [양쪽 핀과 접촉 하중](blink-loaded-link.json) · [베어링 자리 출력·가공 경로](blink-seat-print-check.json)

얼굴을 놓친 뒤 복귀할 때는 축의 실제 위치를 읽어 중립 근처의 편차를 보정합니다. 추적 중 턱에는 낮은 출력으로 닫힘을 유지할 힘만 줍니다. 전원을 켤 때 턱이 조금 열려 있으면 목이 중립에 있는지 확인한 뒤 천천히 닫습니다. [구동 재현](motion-replay.json) · [턱 하중 계산](jaw-hold.json)

## 눈 상하 베어링

양쪽 13번 지지대에 Ø3 × Ø6 × 2.5 mm 베어링을 한 개씩 넣습니다. P2S 7번 판에서 확인한 포켓 최소 지름은 6.216 mm였고, 포켓 안에 서포트 경로는 없었습니다. 베어링이 바깥 면에서 돌출하지 않고 중심이 앞뒤와 위아래로 각각 0.1 mm 이내에 있으면, 앞 외장을 직선으로 넣는 동안 0.25 mm 이상 간격이 남습니다. [제조사 규격](https://www.nsk.com/eu-en/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/extra-small-ball-bearings-and-miniature-ball-bearings-metric-series/mr63zzmc3p6-apn.html) · [P2S 포켓 검사](slicing-check.json) · [앞 외장 삽입 검사](eye-bearing-shell.json)

프레임에 지지대를 먼저 조이고 길이 150 mm의 연마봉으로 베어링을 정렬합니다. 외륜의 고정제가 굳으면 봉을 뺍니다. 내륜과 조립 핀의 지름 차가 양수이고 0.010 mm 이하일 때 베어링과 링크에서 생기는 반전 유격은 계산상 1.54–1.88°입니다. [조립과 실측 기준](assembly.md#눈-상하-베어링) · [눈 상하 계산](eye-pitch.json)

## 실물 검수

턱 모듈과 머리 뒤 외장 29의 이탈 방지 방법이 제작 전에 확정되어야 합니다. 뒤 외장을 설치한 CAD에서 턱 모듈이 아래로 6 mm 내려갈 수 있었고, 뒤 외장 자체의 이탈 방지 단계도 빠져 있습니다. 하부 보드 덮개 정비는 기존 모델에서 빠진 연결선 7가닥과 주전원 커넥터까지 장착해 확인합니다. 하중과 공차를 함께 고려한 눈꺼풀 접촉, 목 토크와 턱 복귀 때의 치아 간격도 검토 항목으로 남아 있습니다. 후보 펌웨어는 보정 영점까지만 명령합니다. 새 MuJoCo 재생에서 초기 턱이 열려 있던 12가지 조건은 모두 2.4초에 복구를 중단했습니다. [설계 검토](https://github.com/ckh7488/head/blob/765d379f9c37a0123b0e38612cc2745b216bceca/REVIEW.md#기구조립-검토-결과) · [조립 순서](assembly.md)

CAD와 슬라이서에서 확인한 공구 접근과 가공 경로는 실제 출력물에서 확인해야 합니다. 서포트 제거, 베어링 포켓·구멍 마감, 제한판 가공과 오른쪽 목 축 체결 시험이 남아 있습니다. 실물 P01–P08과 M05 눈 상하 반전 유격, P03 깜빡임 50회는 미실시입니다. [조립 순서](assembly.md) · [실물 시험](../../../spec/bench.md) · [M05](../../../spec/mechanisms.md)

## 파일과 검사 재현

저장소 루트에서 실행합니다. 저장 보고서는 생성에 사용한 B24 소스 `2157cbf`의 펌웨어·트래커 해시와 대조합니다. 아래 예에서 `../r5-b24-review`는 그 커밋의 별도 체크아웃 경로입니다. CAD 생성에는 FreeCAD Python과 기구 해석 의존성이 필요합니다. 출력 방향과 설정은 B23 P2S의 저장된 설정을 사용합니다. [보고서 작성 시점의 소스](https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a) · [실행 환경](../../README.md#재현) · [변경 형상과 출력 메시 해시](design.json)

```sh
python mechanical/physics/verify_b23_release.py mechanical/revisions/b24 --revision B24 --source ../r5-b24-review
python mechanical/build_b24.py build/b24
python mechanical/build_b24_print.py build/b24/R5-B24-P2S.3mf --print-dir build/b24/print
```

후보 펌웨어로 목과 턱의 모델을 다시 실행하려면 기구 검사 환경에서 아래 명령을 사용합니다. 새 결과는 `build/b24-motion/report.json`에 들어갑니다.

```sh
rev=mechanical/revisions/b24
python mechanical/physics/export_cad.py --world --cad "$rev/R5-B24-Assembly.FCStd" build/b24-motion-cad
python mechanical/physics/b23_motion_replay.py build/b24-motion-cad "$rev/sliced-grams.json" "$rev/jaw-stop.json" build/b24-motion
```
