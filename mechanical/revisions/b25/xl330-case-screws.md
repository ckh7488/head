# B25 XL330 케이스 나사

ROBOTIS XL330 패키지에 동봉된 **PHS M2×8 TAP 11개**와 **PHS M2×6 TAP 5개**를 아래 위치에 배정합니다. XL330-M077-T `902-0162-000` 세 개와 XL330-M288-T `902-0163-000` 한 개의 동봉품에 길이별로 40개와 24개가 들어 있으므로 케이스 나사를 따로 발주할 필요가 없습니다. 공통 BOM E2에서 케이스용 16개를 뺍니다. 케이스는 제조사 체결품 예외를 적용해 동봉 십자 둥근머리 탭 나사를 사용합니다. [M077 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0162-000) · [M288 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0163-000) · [ROBOTIS 케이스 조립 그림](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#how-to-assemble) · [공통 BOM](../../BOM.csv)

| 모터와 출력 부품 | PHS M2×8 TAP | PHS M2×6 TAP |
| --- | --- | --- |
| ID1 눈 좌우 · 모터판 39 | `eyeYawHead0`, `eyeYawHead2`, `eyeYawHead3` | `eyeYawHead1` |
| ID2 눈 상하 · 모터판 42 | `eyePitchHead0`–`eyePitchHead3` | |
| ID3 눈꺼풀 · 모터판 46 | `blinkMotorHead1`, `blinkMotorHead3` | `blinkMotorHead0`, `blinkMotorHead2` |
| ID6 턱 · 받침 36 | `jawMotorHead1`, `jawMotorHead2` | `jawMotorHead0`, `jawMotorHead3` |

네 조립체는 작업대에서 모터와 판을 맞춘 뒤 위 나사를 먼저 조입니다. 각 조립체에서 **머리 Ø4.00 × 2.00 mm**의 직선 삽입과 **축 Ø3.00 mm, 길이 30 mm**의 공구 진입이 CAD에서 통과했습니다. 나사 머리가 이 치수 이내인지 확인하고, 끝에서 30 mm까지 축 지름이 Ø3.00 mm 이하이며 십자홈에 끝까지 물리는 드라이버를 고릅니다. `blinkMotorHead1`은 머리 받침이 판 가장자리에 걸쳐 있으므로 판이 들뜨거나 머리가 기울지 않는지 확인합니다. [자리 좌표와 CAD 확인 결과](xl330-case-screws.json)

## 물림과 실물 확인

Detail A의 케이스 구멍에는 **Ø2 × 3.50 mm** 입구와 이어지는 **Ø1.60 mm** 탭 파일럿이 있습니다. B25의 제조사 솔리드 네 개에서 16곳 모두 파일럿이 **15.00 mm** 이어진 뒤 반대편 Ø2 입구로 열립니다. 나사 끝이 파일럿에 들어가는 길이는 두꺼운 2.70 mm 자리에서 **1.80 mm**, 얕은 0.85–1.10 mm 자리에서 **1.40–1.65 mm**입니다. 나사 끝에서 파일럿 끝까지 **13.20–13.60 mm**가 남습니다. 도면의 3.0 mm 최대 깊이는 혼의 Ø12 피치원 구멍에 적용됩니다. [ROBOTIS 도면](https://docs.robotis.com/docs/dxl/model_reference/x_series/xl_series/xl330-m077/#drawings) · [도면 사본](https://www.besttechnology.co.jp/modules/knowledge/gate.php/X330_dimension.pdf?_noumb=&openfile=X330_dimension.pdf&refer=Dynamixel+XL330-M077&way=attach)

실물에서 각 출력물의 머리 받침면부터 케이스 접촉면까지 두께를 잽니다. 전원을 끈 모터의 케이스 구멍에 지름 1.6 mm보다 작은 매끈한 핀을 대어 나사 끝이 닿는 깊이까지 열린 것을 확인합니다. 동봉 나사의 머리 아래 길이와 끝의 불완전 나사산 길이도 기록합니다. 완전한 나사산의 물림 길이는 머리 아래 길이에서 출력물 두께, 케이스 입구 깊이, 불완전 나사산 길이를 뺀 값입니다. 작업대에서 손으로 나사를 조여 머리가 판에 앉아 판을 눌러 잡는지, 미리 걸리는 곳이나 헛도는 구멍이 있는지 확인합니다. 케이스와 판에 기준선을 표시해 작동 전후에 들뜸이나 회전 여부를 확인합니다. 실제 케이스의 나사산 성형과 조임 유지 판정은 P01과 모터 작동 시험에서 기록합니다. [실물 시험](../../../spec/bench.md)

## CAD 확인 재현

FreeCAD Python 환경에서 저장소 루트 기준으로 실행합니다.

```sh
python mechanical/physics/check_b25_xl330_case_screws.py \
  mechanical/revisions/b25/R5-B25-Assembly.FCStd \
  mechanical/revisions/b24/hardware.json build/b25-xl330-case-screws.json
```
