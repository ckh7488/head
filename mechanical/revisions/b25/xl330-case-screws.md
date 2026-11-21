# B25 XL330 케이스 나사

XL330-M077-T `902-0162-000` 세 개와 XL330-M288-T `902-0163-000` 한 개를 준비합니다. 각 패키지에 **PHS M2×8 TAP 10개**와 **PHS M2×6 TAP 6개**가 들어 있습니다. B25 케이스에 각각 **11개**와 **5개**를 배정하며 별도 발주 수량은 0개입니다. 제조사 판매표는 8 mm를 프레임용, 6 mm를 혼용으로 표시합니다. 제조사 조립 그림의 M2 탭 나사는 판을 관통해 모터 케이스에 물립니다. B25는 같은 체결 방식을 사용하고, 6 mm 나사 다섯 개는 B25의 얕은 케이스 자리에 배정합니다. [M077 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0162-000) · [M288 동봉품](https://en.robotis.com/shop_en/item.php?it_id=902-0163-000) · [ROBOTIS 케이스 조립 그림](https://emanual.robotis.com/assets/images/dxl/x/x330/xl330_assembly_integrated.png) · [B25 발주표](BOM.csv)

| 모터와 출력 부품 | PHS M2×8 TAP | PHS M2×6 TAP |
| --- | --- | --- |
| ID1 눈 좌우 · 모터판 39 | `eyeYawHead0`, `eyeYawHead2`, `eyeYawHead3` | `eyeYawHead1` |
| ID2 눈 상하 · 모터판 42 | `eyePitchHead0`–`eyePitchHead3` | |
| ID3 눈꺼풀 · 모터판 46 | `blinkMotorHead1`, `blinkMotorHead3` | `blinkMotorHead0`, `blinkMotorHead2` |
| ID6 턱 · 받침 36 | `jawMotorHead1`, `jawMotorHead2` | `jawMotorHead0`, `jawMotorHead3` |

네 조립체는 작업대에서 모터와 판을 맞춘 뒤 위 나사를 먼저 조입니다. 각 조립체에서 **머리 Ø4.00 × 2.00 mm**의 직선 삽입과 **축 Ø3.00 mm, 길이 30 mm**의 공구 진입이 CAD에서 통과했습니다. 나사 머리가 이 치수 이내인지 확인하고, 끝에서 30 mm까지 축 지름이 Ø3.00 mm 이하이며 십자홈에 끝까지 물리는 드라이버를 고릅니다. `blinkMotorHead1`은 머리 받침이 판 가장자리에 걸쳐 있으므로 판이 들뜨거나 머리가 기울지 않는지 확인합니다. [자리 좌표와 CAD 확인 결과](xl330-case-screws.json)

## 물림과 실물 확인

Detail A의 케이스 구멍에는 **Ø2 × 3.50 mm** 입구와 이어지는 **Ø1.60 mm** 탭 파일럿이 있습니다. B25의 제조사 솔리드 네 개에서 16곳 모두 파일럿이 **15.00 mm** 이어진 뒤 반대편 Ø2 입구로 열립니다. 나사 끝이 파일럿에 들어가는 길이는 두꺼운 2.70 mm 자리에서 **1.80 mm**, 얕은 0.85–1.10 mm 자리에서 **1.40–1.65 mm**입니다. 나사 끝에서 파일럿 끝까지 **13.20–13.60 mm**가 남습니다. 이 값은 나사 끝의 명목 진입량입니다. 도면의 3.0 mm 최대 깊이는 혼의 Ø12 피치원 구멍에 적용됩니다. [ROBOTIS 도면](https://docs.robotis.com/docs/dxl/model_reference/x_series/xl_series/xl330-m077/#drawings) · [도면 사본](https://www.besttechnology.co.jp/modules/knowledge/gate.php/X330_dimension.pdf?_noumb=&openfile=X330_dimension.pdf&refer=Dynamixel+XL330-M077&way=attach)

인용한 ROBOTIS 도면과 조립 그림에서 케이스의 수치화된 최소 물림 길이는 확인되지 않았습니다. 기존 실물 조립 시험에서 머리 받침면부터 케이스 접촉면까지의 출력물 두께와 케이스 입구 깊이, 동봉 나사의 머리 아래 길이와 끝의 불완전 나사산 길이를 잽니다. 완전한 나사산의 물림 길이는 머리 아래 길이에서 출력물 두께, 케이스 입구 깊이, 불완전 나사산 길이를 뺀 값입니다. 케이스의 나사 가용 깊이와 비교하고, 구멍의 나사산 성형과 머리가 판을 밀착시키는지 확인합니다. 조립·작동 전후의 들뜸, 헛돎과 풀림을 기존 실물 시험에서 기록합니다. [실물 시험](../../../spec/bench.md)

## CAD 확인 재현

FreeCAD Python 환경에서 저장소 루트 기준으로 실행합니다.

```sh
python mechanical/physics/check_b25_xl330_case_screws.py \
  mechanical/revisions/b25/R5-B25-Assembly.FCStd \
  mechanical/revisions/b24/hardware.json build/b25-xl330-case-screws.json
```
