# B25 카메라 USB 선 검토

**입구만 넓히는 방법은 막음입니다.** 기존 Ø4 mm 케이블은 12절에 따라 최소 R40 mm와 가동 부품과의 최악 간극 1 mm가 필요합니다. B25의 저장 경로는 입구에서 R12.69 mm, 입구 다음 로터 가이드 안에서 R14.00 mm, 출구에서 R12.71 mm입니다. 로터 가이드 안쪽 단면은 케이블 중심의 위치를 바꿔도 공칭 표면 간극 상한이 0.997 mm입니다. [입구 뒤 단면과 경로 검사](camera-guide-check.json) · [고정 조건 12절](../../../spec/conditions.md#12-움직이는-축을-지나는-배선)

## 선정 선재

**Sanwa Supply KU-SLEN10BKK 1 m**를 B25 BOM의 카메라 가동 구간용 선재로 선정했습니다. 제조사 공칭 외경은 Ø2.5 mm이며, USB 2.0 Hi-Speed 480 Mbps와 제품 최소 굽힘 R15 mm를 명시합니다. B25 판정은 실측 외경의 10배이므로 공칭 R25 mm, 허용 상한 Ø3.0 mm에서는 R30 mm를 적용합니다. 제품 표의 R15 mm는 연속 가동으로 검증된 수치인지 공개 자료에서 확인되지 않았습니다. [제조사 규격](https://www.sanwa.co.jp/product/syohin?code=KU-SLEN10BKK&print=1) · [판매처](https://www.biccamera.com/bc/item/10116901/) · [한국 배송 지원](https://bc.help.buyee.jp/en/countries/)

U20CAM 보드 쪽은 동봉 케이블의 순정 플러그를 유지합니다. 연결은 두 축의 가동 구간 밖에서 하고, 꺾이거나 당겨지지 않도록 고정합니다. 보드 인식과 UVC 스트리밍은 실제 연결 뒤 확인합니다. 기존 경로를 유지하면 외경 약 1.27 mm 이하가 필요하므로, 이 선재에는 새 경로를 검증해야 합니다. [카메라 제조사 설명서](https://github.com/INNO-MAKER/U20CAM-1080P-S1/blob/main/U20CAM-1080P-S1%20UserManual-v1.1.pdf) · [발주표](BOM.csv)
