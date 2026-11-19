# R5 B15 조립순서

3D 조립에서 재생을 누르면 앞 단계에서 체결한 부품도 자리를 지킵니다. **체결품 보기**를 누르면 안쪽 볼트와 너트까지 볼 수 있습니다. 시험판 1번은 눈과 레일, 2번은 케이블, 3번은 바닥 덮개, 4번은 보드 캐리어입니다. [3D 단계별 조립](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/) · [P1S 시험판](R5-B15-Fit-P1S.3mf)

## 체결품

구조물은 **M3×8과 M3×16 육각렌치 원통머리(ISO 4762 / DIN 912)**와 일반 M3 육각너트를 사용합니다. 작은 눈 링크와 기판, 제조사 구멍에 들어가는 체결품은 [부품표](BOM.csv)를 확인합니다. XL330과 XL430 케이스에 들어가는 성형 나사는 나사산과 깊이를 실물에 대조합니다. [XL330 사양](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/) · [XL430 사양](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/)

M3에는 2.5 mm 육각렌치와 5.5 mm 스패너 또는 소켓, M2에는 1.5 mm 육각렌치와 4 mm 공구를 씁니다. 케이블·바닥 덮개의 18 mm 입구와 눈꺼풀 크랭크는 스패너 머리 바깥 폭 16 mm, 두께 4.2 mm로 확인했습니다. 받침의 깊은 통로에는 직선으로 60 mm 이상 닿는 2.5 mm 육각렌치를 씁니다. [폭 16 mm·두께 3.5 mm 스패너 예](https://shop.gedore.com/en-de/6063750/)

## 배선

| 구간 | 전선과 단자 |
|---|---|
| 5 V 입력·목 전원 J2 | **Alpha Wire 3055, 18 AWG, 피복 Ø1.96–2.06 mm**. XT30U 납땜 컵에 연결해 허브 J1의 XT30PW-M에 꽂음. 목 전원 J2는 Phoenix 1715721에 7 mm 벗긴 연선을 끼워 0.5–0.6 N·m로 조임. [3055](https://www.alphawire.com/en/products/wire/hook-up-wire/premium/3055.aspx) · [J2 단자](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-15-2-508-1715721) |
| 목 전원 XT60U 양쪽 | **Alpha Wire 6718, 12 AWG, 피복 Ø2.92–3.03 mm**로 XT60U 양쪽에 짧은 꼬리를 만듦. J2 쪽 +와 GND를 각각 WAGO 221-412에서 18 AWG로 바꿈. [6718](https://www.alphawire.com/products/wire/ecogen/ecowire/6718) · [XT60U 도면](https://www.china-amass.com/public/upload/20240620/94b600a6a4c042646bc89646abc8ea85.pdf) · [221-412](https://www.wago.com/global/p/221-412) |
| 모터·OpenRB 신호 | **Alpha Wire 6712, 24 AWG, 피복 Ø1.04–1.14 mm**. 허브 PH는 PHR-2/PHR-3과 SPH-002T-P0.5S. 모터와 OpenRB EH는 EHR-3과 SEH-001T-P0.6. [6712](https://www.alphawire.com/products/wire/ecogen/ecowire/6712) · [JST PH](https://www.jst-mfg.com/product/index.php?lang=en&series=199) · [JST EH](https://www.jst-mfg.com/product/pdf/eng/eEH.pdf) |
| 카메라·OpenRB USB | **StarTech USBEXTAA6IN** 두 개. 암 커넥터 도면은 몸체 16.0 × 9.1 mm, 금속부 돌출 9.5 mm, 케이블 Ø4.8 mm입니다. 시험판에서 뒤턱과 뒷목을 대조합니다. 카메라 모듈에는 동봉 케이블을 사용합니다. [StarTech 치수도](https://media.startech.com/downloads/image/USBEXTAA6IN_Diagram.pdf) |

1. **작업대에서 단자를 만듭니다.** 접점 한 개에 한 가닥을 압착합니다. 앞쪽 날개는 구리, 뒤쪽 날개는 피복을 잡습니다. 단자를 하우징 뒤에서 끝까지 넣고 한 가닥씩 가볍게 당겨 잠겼는지 확인합니다. 하우징의 1번 표시를 기준으로 연속성을 잽니다. 빨강은 전원, 검정은 GND, 흰색은 DATA로 두고 양끝에 5 V·목 전원·모터 ID를 붙입니다. [핀 순서](../electronics/README.md#전원과-배선)
2. **트레이에 전원 커넥터를 먼저 얹습니다.** XT30U는 암수를 결합해 앉힙니다. XT60U는 바깥쪽 암 커넥터를 앉히고 허브를 넣기 전에 받침 안에서 수 커넥터를 꽂습니다. 납땜부를 한 가닥씩 열수축하고 완성 외경이 XT30U **Ø4.0 mm**, XT60U **Ø5.6 mm** 이하인지 확인합니다. 몸체 뒤턱을 고정부에 붙이고 두 전선을 각자 홈으로 뺀 뒤 덮개를 닫습니다. [트레이에 배선 올리기](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#cable-plugs) · [XT60U 안쪽 꽂기](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#xt60-mate) · [AMASS XT30U 도면](https://www.china-amass.com/public/upload/20240608/810c62b3f7ace2287989748538eb2a6b.pdf) · [열수축 튜브](https://www.te.com/en/product-CAT-HST-RNF100-2.html)
3. **허브를 눕힌 상태에서 먼저 연결합니다.** J4–J6은 PH–EH, J7–J8은 EH–EH입니다. OpenRB에서 J3으로는 GND와 DATA 두 가닥을 연결합니다. 5 V와 GND는 WAGO 221-413 두 개에서 허브와 턱으로 나누고, 턱의 5 V에 Littelfuse 0FHM0003ZXJV-F2를 넣습니다. J6 DATA는 별도 221-413에 분기합니다. 레버 단자는 11 mm 벗겨 넣습니다. 덮개를 30 mm 내려도 단자를 당기지 않도록 여유를 둡니다. [허브 배선](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#hub-wiring) · [221-413](https://www.wago.com/gb/installation-terminal-blocks-and-connectors/splicing-connector-with-levers/p/221-413) · [2 A 인라인 퓨즈](https://www.littelfuse.com/assetdocs/0fhm0003zxjv-f2-2d-prints?assetguid=0cf40f2e-7338-4c1d-bce2-d9255753058c)
4. **회전판 앞쪽 통로로 선부터 보냅니다.** 목 좌우 ±60°에서 Ø9 mm 검사봉이 지났습니다. 선 다발은 Ø8 mm 이내로 묶고, 통과시킨 뒤 JST 하우징을 끼웁니다. 받침과 목 사이에서 움직일 수 있는 구간을 60 mm 이상 확보하고 상하축에도 따로 여유를 둡니다. 고정 전원선은 18 AWG에서 굽힘 반경 21 mm, 12 AWG에서 16 mm 이상으로 둡니다. WAGO와 턱 퓨즈는 받침 안의 고정 배선에 결속합니다. 퓨즈는 앞쪽, 5 V 분기는 왼쪽, 12 V 연결은 오른쪽에 자리가 있습니다.
5. **뒤 해골을 닫기 전에 확인합니다.** 시험판 2번에서 XT 몸체의 뒤턱이 움직이지 않는지 봅니다. 전원을 뺀 채 직선과 45° 방향으로 각각 10 N을 30초 가했을 때 이동량 0.5 mm 이하와 피복 상태를 확인합니다. 회전판과 머리를 손으로 끝까지 움직여 선을 물거나 당기는지 봅니다. 첫 전압과 부하 전압은 보드와 모터에서 각각 잽니다. [P1S 시험판](R5-B15-Fit-P1S.3mf) · [전원 측정](../electronics/README.md#전원과-배선)

구매품 목록에서 커넥터를 누르면 해당 부품이 강조됩니다. XT60U 암수는 공급사 STEP, 허브의 JST 핀 헤더는 KiCad STEP을 썼습니다. XT30U·StarTech·JST 케이블 하우징은 각 제조사 도면을 기준으로 그렸습니다. XT60U 수 커넥터 삽입 경로는 다섯 위치에서 간섭이 없었습니다. [뒤쪽 커넥터](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#cable-plugs) · [JST 하네스](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#hub-wiring)

## 배선과 체결품을 단 상태의 구동 검사

마지막 조립 화면과 구동 화면에 기본 체결품 140개, 모터 나사 원통머리 18곳, 내부 배선 32가닥을 표시했습니다. 머리의 모터 네 개, 목 모터 두 개, 코 카메라와 OpenRB까지 연결했습니다. ESP32-C3는 독립 RF 시험용으로 둡니다. [마지막 조립](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#complete) · [배선 포함 구동](https://r5-b1-review.ckh.chatgpt.site/b15/?view=wiring)

- **회전판 아래 볼트.** 목 좌우 +36°에서 M3 볼트 머리와 고정 XL430 몸체가 44.9 mm³ 겹칩니다. 볼트 받침을 2.25 mm 올린 후보는 ±60°를 3° 간격으로 검사해 최소 0.40 mm를 확보했습니다. 남는 회전판 두께와 공구 경로를 확인한 뒤 반영합니다.
- **목 모터의 JST.** ID 4 좌우 포트와 ID 5 앞뒤 포트 모두에서 EHR-3 외형이 지지대에 걸립니다. 작업대에서 꽂고 빼는 공간을 포함해 지지대를 수정해야 합니다. 모터 포트는 제조사 도면의 위치를 사용했습니다. [ROBOTIS XL430](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/)
- **턱과 배선.** 턱에 닿던 배선을 목 기둥 쪽으로 옮겼습니다. 수정 경로는 6축 공칭 자세 148개에서 턱을 피했습니다. 눈 좌우 모터의 플러그는 목 상하 +6°와 눈 상하 +8°에서 목 지지대에 닿습니다. 받침의 허브 주변 배선도 여유가 더 필요합니다.

카메라 플러그 치수와 고정 나사, 선의 굽힘과 왕복 여유는 실물에서 대조합니다. 카메라선은 움직임에 따라 필요한 경로 길이가 최대 약 47 mm 달라집니다. [카메라 매뉴얼](https://github.com/INNO-MAKER/U20CAM-1080P-S1)

B15 전체 출력은 구동 간섭과 출력 경로 문제를 수정한 뒤 진행합니다. [출력 검사](README.md#출력-경로-검사)

## 받침

받침의 뒤쪽 M3 통로 두 곳과 바닥 덮개 체결부 네 곳에서 서포트를 제거합니다. 시험판 2번 시편의 뒤쪽 통로 두 곳도 정리합니다. 볼트가 힘을 주지 않고 통과하는지 확인한 뒤 조립합니다.

1. 허브를 넣기 전에 트레이 40을 M3×16 두 개로 붙입니다. 뒤에서 긴 육각렌치를 넣고 받침 안에서 소켓으로 와셔 뒤의 너트를 잡습니다. 커넥터 뒤턱을 맞추고 덮개 42를 얹습니다. 위에서 덮개 볼트를 조이는 동안 뒤쪽 열린 턱에서 너트를 스패너로 잡습니다. [케이블 덮개 체결](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#cable-cover-bolts)
2. 작업대에서 바닥 덮개를 양끝만 받쳐 밑을 비웁니다. 5.5 mm 소켓에 너트를 담아 덮개 아래 Ø10.6 mm 구멍에 올리고 기판 쪽에서 볼트를 겁니다. 소켓 앞쪽 외경 Ø9.3 mm까지 확인했습니다. 허브가 달린 덮개를 받침에 올린 다음에는 옆 창에서 스패너로 너트를 잡고 아래에서 M3×8을 조입니다. 배선에는 덮개를 30 mm 내릴 여유를 둡니다. [허브 소켓 경로](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#hub-nuts) · [외경 Ø8 mm 복스 드라이버 예](https://digicat.wiha.com/au/en/tools/screwdrivers/mechanic-s-screwdrivers/softfinish/hex/screwdriver-softfinish/01076)
3. 각 PCB를 분리된 캐리어에 M2×8로 조입니다. 4 mm 소켓은 아래에서 들어갑니다. 보드가 달린 캐리어를 놓고 양옆 M3×8을 아래에서 넣어 위의 너트를 잡습니다. OpenRB는 USB-C를 꽂은 채 내려놓습니다. 플러그 몸체는 12.4 × 18 × 6.2 mm 이내입니다. OpenRB의 홀 간격은 제조사 그림에서 환산한 20.5 × 61.5 mm로, 시험판 4번에서 실물과 맞춥니다. [보드 캐리어 조립](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#base-boards) · [ROBOTIS 보드 그림](https://docs.robotis.com/docs/parts/controller/openrb-150/#pinout)

## 목

1. 02번 받침에 6816과 눌림판 세 개를 끼웁니다. 작업대에서 눌림판을 M3×8로 조인 다음 조립체를 받침에 놓습니다. 바닥 안쪽 세 통로에서 M3×16을 넣고 위에서 너트를 잡습니다.
2. 작업대에서 회전판에 M3×16 볼트 네 개를 아래에서 넣고 위의 너트로 먼저 고정합니다. 회전판을 내륜에 놓아 위에서 모터 혼을 조입니다. 상판 03은 볼트가 통과하는 바깥 세 자리에 M3×8을 아래에서 넣습니다.
3. 작업대에서 기둥 06에 요크 07을 얹습니다. 옆 통로에서 너트를 스패너로 잡고 위에서 M3×16으로 조입니다. 688 두 개는 요크 바깥에서 넣습니다.
4. 머리 프레임 09를 내려 양쪽 Ø8 축을 끼웁니다. 오른쪽 D-flat 끝을 구동 혼에 맞춥니다. 외장을 달기 전에 손으로 축을 움직여 걸리는 곳을 확인합니다. [회전판부터 보기](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#rotor-nuts)

## 눈·눈꺼풀

1. 안구를 크래들에 넣고 위에서 Ø2×24 핀을 끼웁니다. 좌우 눈 지지대와 크래들에는 바깥에서 Ø3×13 핀을 넣습니다.
2. 왼쪽과 오른쪽 눈틀을 작업대에서 따로 조립합니다. 각 눈꺼풀에 Ø2×8 핀을 두 개씩 씁니다. 핀은 눈틀에 고정하고 눈꺼풀은 돌 수 있게 둡니다.
3. 빈 레일을 프레임에 댑니다. 앞에서 소켓으로 너트를 잡고 뒤에서 M3×16으로 조인 다음 베어링 두 개를 넣습니다. 선택 균형추를 다는 경우 레일과 눈 모터를 달기 전에 프레임 앞쪽에서 소켓으로 너트를 잡습니다.
4. 작업대에서 혼과 가운데 링크를 먼저 조입니다. 모터판을 레일에 달고 Ø4×112 축을 간격통과 가운데 크랭크에 통과시킨 뒤 양끝 크랭크를 끼웁니다. 앞에서 스패너로 크랭크 너트를 잡고 M3×8을 위에서 조입니다.
5. 나머지 링크를 M2×8로 체결하고 평와셔를 댑니다. 축방향 유격은 0.10~0.20 mm입니다.

## 턱·외장

1. 턱 조립체의 오른쪽 Ø4 핀은 작업대에서 안쪽으로 접근해 베어링과 힌지팔에 끼웁니다. 링크를 분리한 채 손으로 13° 범위를 확인합니다.
2. 앞 외장을 작업대에 놓고, 카메라 브래킷은 열린 뒤쪽 위에서 비스듬히 내려 넣습니다. 눈틀은 눈꺼풀을 닫은 상태에서 열린 뒤로 넣습니다.
3. 목 축을 끼운 뒤 앞 외장을 정면에서 밀어 넣습니다. 눈꺼풀을 열고 링크 아래쪽 두 곳을 체결합니다. 작업대에서 머리를 받쳐 턱을 아래에서 올립니다. [앞 외장 장착](https://r5-b1-review.ckh.chatgpt.site/b15/assembly/#front-shell)
4. 머리와 기둥을 통째로 회전판에 세운 볼트 위에 내려놓습니다. 열린 통로로 아래 너트를 잡고 위쪽 너트 네 개를 조입니다. 손으로 움직여 본 뒤 뒤 해골을 씌웁니다.

가조립에서 출력 공차, 실물 케이블, 접착 위치를 확인합니다. 전원을 연결하기 전에 5 V와 목용 11.1~12.0 V를 각각 확인하고, 외장을 열어 둔 상태에서 축마다 저속으로 첫 구동을 시험합니다. [전원 측정](../electronics/README.md#전원과-배선) · [구동 보정](../control/README.md#openrb와-모터)
