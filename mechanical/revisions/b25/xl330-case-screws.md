# B25 XL330 케이스 나사

1. XL330-M077-T `902-0162-000` 세 개와 XL330-M288-T `902-0163-000` 한 개를 준비합니다. 각 상자에 **PHS M2×8 TAP 10개**와 **PHS M2×6 TAP 6개**가 들어 있습니다. B25의 케이스 조립에는 각각 **11개**와 **5개**를 배정합니다. 별도 발주 수량은 0개입니다. [M077 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0162-000) · [M288 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0163-000) · [B25 발주표](BOM.csv)
2. 아래 표대로 나사를 나눕니다. 네 조립체 모두 작업대에서 출력 부품과 모터를 맞추고, 판을 관통시켜 모터 케이스에 물립니다. B25의 얕은 다섯 자리에 6 mm 나사를 씁니다. [ROBOTIS 케이스 조립 그림](https://emanual.robotis.com/assets/images/dxl/x/x330/xl330_assembly_integrated.png)

   | 모터와 출력 부품 | PHS M2×8 TAP | PHS M2×6 TAP |
   | --- | --- | --- |
   | ID1 눈 좌우 · 모터판 39 | `eyeYawHead0`, `eyeYawHead2`, `eyeYawHead3` | `eyeYawHead1` |
   | ID2 눈 상하 · 모터판 42 | `eyePitchHead0`–`eyePitchHead3` | |
   | ID3 눈꺼풀 · 모터판 46 | `blinkMotorHead1`, `blinkMotorHead3` | `blinkMotorHead0`, `blinkMotorHead2` |
   | ID6 턱 · 받침 36 | `jawMotorHead1`, `jawMotorHead2` | `jawMotorHead0`, `jawMotorHead3` |

3. 나사 머리 **Ø4.00 × 2.00 mm**와 공구 축 **Ø3.00 × 30 mm**가 직선으로 들어가는 CAD 경로를 참고합니다. 나사 머리를 재고, 끝에서 30 mm까지 축 지름이 Ø3.00 mm 이하이며 십자홈에 끝까지 물리는 드라이버를 고릅니다. `blinkMotorHead1`의 머리 받침은 판 가장자리에 걸치므로 머리의 수평 안착과 판의 밀착을 확인합니다. [자리 좌표와 공구 검사](xl330-case-screws.json)

## 물림과 실물 확인

1. 각 자리의 머리 받침면부터 케이스 접촉면까지 출력물 두께, 케이스 입구 깊이, 나사 머리 아래 길이와 끝의 불완전 나사산 길이를 잽니다. 머리 아래 길이에서 출력물 두께, 입구 깊이, 불완전 나사산 길이를 빼서 완전한 나사산의 물림 길이를 구합니다.
2. 물림을 케이스의 실제 가용 깊이와 대조합니다. Detail A의 케이스 입구는 **Ø2 × 3.50 mm**, 뒤의 탭 파일럿은 **Ø1.60 mm**입니다. 제조사 솔리드에서 16곳의 파일럿은 **15.00 mm** 이어지고 반대편 Ø2 입구로 열립니다. CAD에서 나사 끝의 명목 진입량은 2.70 mm 자리에서 **1.80 mm**, 0.85–1.10 mm 자리에서 **1.40–1.65 mm**입니다. 파일럿 끝까지 **13.20–13.60 mm**가 남습니다. 제조사 도면의 최대 **3.0 mm** 깊이는 혼의 Ø12 피치원 구멍에 적용합니다. 케이스의 최소 물림 수치는 인용한 제조사 자료에 별도 표기가 없습니다. [ROBOTIS 도면](https://docs.robotis.com/docs/dxl/model_reference/x_series/xl_series/xl330-m077/#drawings) · [도면 사본](https://www.besttechnology.co.jp/modules/knowledge/gate.php/X330_dimension.pdf?_noumb=&openfile=X330_dimension.pdf&refer=Dynamixel+XL330-M077&way=attach)
3. 체결하면서 구멍의 나사산 성형과 머리의 밀착을 확인합니다. 조립·작동 전후의 들뜸, 헛돎, 풀림 여부를 P08에 기록합니다. [실물 시험](../../../spec/bench.md#b25-실물-시험)

## CAD 확인 재현

저장소 루트의 FreeCAD Python 환경에서 실행합니다.

```sh
python mechanical/physics/check_b25_xl330_case_screws.py \
  mechanical/revisions/b25/R5-B25-Assembly.FCStd \
  mechanical/revisions/b24/hardware.json build/b25-xl330-case-screws.json
```
