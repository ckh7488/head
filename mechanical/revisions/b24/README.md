# R5 B24 제작과 조립

[FreeCAD 조립본](R5-B24-Assembly.FCStd) · [Bambu Studio P2S 프로젝트](R5-B24-P2S.3mf) · [조립 순서](assembly.md) · [3D 조립 화면 재현](../../../web/README.md#b24-조립-순서) · [검증 결과](verification.json)

Bambu Studio에서 3MF를 프로젝트로 엽니다. **P2S 0.4 mm 노즐, Textured PEI, PETG HF, 0.20 mm 레이어** 설정입니다. 전체 12개 판의 슬라이서 추정치는 서포트 포함 **약 1.20 kg, 62시간 32분**입니다. B24의 변경 부품은 4번 판의 앞 외장, 6번 판의 목 클램프, 7번 판의 좌우 눈 베어링 지지대, 8번 판의 왼쪽 눈꺼풀 링크입니다. [출력 경로 검사](slicing-check.json)

## 구입과 가공

목은 XL430-W250-T 두 개, 눈 좌우·상하와 눈꺼풀은 XL330-M077-T 세 개, 턱은 XL330-M288-T 한 개를 씁니다. B23 부품표에 NSK MR63ZZMC3P6 베어링 두 개, M3×8 원통머리 육각렌치 나사 한 개, 정렬용 Ø3 계열 연마봉 150 mm 한 개를 더합니다. 오른쪽 Ø8 mm 금속 축에는 M3 탭을 추가합니다. [축 가공 STEP](pitch-drive-shaft-B24.step) · [축 치수와 체결 시험](pitch-coupler.md) · [공통 부품표](../../../mechanical/BOM.csv)

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

프레임에 지지대를 먼저 조이고 Ø3 × 150 mm 연마봉으로 베어링을 정렬합니다. 외륜의 고정제가 굳으면 봉을 뺍니다. 12번 크래들 구멍에 남은 서포트를 제거한 뒤, Ø3 × 13 mm 핀이 크래들과 베어링 내륜에 손으로 들어가는지 먼저 봅니다. 짧은 핀은 크래들 안쪽에만 붙입니다. 내륜과 핀의 지름 차가 0.010 mm 이하일 때 베어링과 링크에서 생기는 반전 유격은 계산상 1.54–1.88°입니다. [눈 상하 계산](eye-pitch.json)

## 실물 검수

같은 부품과 리비전으로 모든 체결·배선을 조립하는 P08과 깜빡임 50회의 P03을 시행합니다. 눈 상하 반전 유격은 핀 조립과 모터를 포함해 M05에서 측정합니다. 프린터와 모터가 연결되지 않은 환경에서 CAD, 슬라이서 및 모터 모형까지 검증했습니다. [실물 시험](../../../spec/bench.md) · [M05](../../../spec/mechanisms.md)

## 파일과 검사 재현

저장소 루트에서 실행합니다. CAD 생성에는 FreeCAD Python과 기구 해석 의존성이 필요합니다. 출력 방향과 설정은 B23 P2S의 저장된 설정을 사용합니다. [실행 환경](../../README.md#재현) · [변경 형상과 출력 메시 해시](design.json)

```sh
python mechanical/physics/verify_b23_release.py mechanical/revisions/b24 --revision B24
python mechanical/build_b24.py build/b24
python mechanical/build_b24_print.py build/b24/R5-B24-P2S.3mf --print-dir build/b24/print
```
