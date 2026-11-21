# B25 카메라 USB 선 검토

**입구만 넓히는 방법은 막음입니다.** 기존 Ø4 mm 케이블은 12절에 따라 최소 R40 mm와 가동 부품과의 최악 간극 1 mm가 필요합니다. B25의 저장 경로는 입구에서 R12.69 mm, 입구 다음 로터 가이드 안에서 R14.00 mm, 출구에서 R12.71 mm입니다. 로터 가이드 안쪽 단면은 케이블 중심의 위치를 바꿔도 공칭 표면 간극 상한이 0.997 mm입니다. [입구 뒤 단면과 경로 검사](camera-guide-check.json) · [고정 조건 12절](../../../spec/conditions.md#12-움직이는-축을-지나는-배선)

| 얇은 USB 2.0 후보 | 검토할 치수 |
| --- | --- |
| Sanwa Supply KU-SLEN10BKK | Ø2.5 mm, 제품 최소 굽힘 R15 mm. B25는 공칭 외경 기준 R25 mm. [제조사 규격](https://www.sanwa.co.jp/product/syohin?code=KU-SLEN10BKK&print=1) |
| Buffalo BU2ACY10BK | Ø3.2 mm, 제조사 굽힘 시험 10,000회. 시험 굽힘 반경은 공개 자료에서 미확인. B25는 공칭 외경 기준 R32 mm. [제조사 규격](https://www.buffalo.jp/product/detail/bu2acy10bk.html) |

두 후보는 선재 후보입니다. 카메라 쪽에는 U20CAM 동봉 케이블의 보드 플러그를 유지하고, 접속부는 움직이는 구간 밖에 둬야 합니다. 현 경로의 R12.69 mm를 유지하면 외경이 약 1.27 mm 이하여야 하므로, 두 후보 모두 경로를 다시 잡아야 합니다. 후보 선정 후에는 실제 외경과 단자, 최대 자세의 여유 길이·굽힘 반경·간극을 함께 확인합니다. [카메라 제조사 설명서](https://github.com/INNO-MAKER/U20CAM-1080P-S1/blob/main/U20CAM-1080P-S1%20UserManual-v1.1.pdf)

현재 CAD와 발주표에는 대체 케이블을 적용하지 않았습니다.
