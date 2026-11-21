# B25 카메라 USB 선 검토

기존 Ø4 mm 배선의 저장 경로는 입구 R12.69 mm, 로터 가이드 안 R14.00 mm, 출구 R12.71 mm입니다. 안쪽 가이드 시험 형상은 실제 선재의 반경, 가동 간극 1 mm, 길이 여유 10%를 함께 검사합니다. [입구 뒤 단면과 경로 검사](camera-guide-check.json) · [고정 조건 12절](../../../spec/conditions.md#12-움직이는-축을-지나는-배선)

## 선정 선재

**Sanwa Supply KU-SLEN10BKK 1 m**를 B25 BOM에 지정했습니다. 제조사는 공칭 Ø2.5 mm, USB 2.0 Hi-Speed 480 Mbps, PVC 피복 및 최소 굽힘 R15 mm를 명시합니다. 공개 규격의 제품 분류는 극세 케이블이고 고굴곡 또는 반복 굽힘 등급은 명시돼 있지 않습니다. R15 이상 경로를 설계 시안으로 검토하되, 확인된 규격만 적용한 12절 판정에는 일반 케이블의 10배, 공칭 R25 mm를 사용합니다. [제조사 규격](https://www.sanwa.co.jp/product/syohin?code=KU-SLEN10BKK&print=1) · [판매처](https://www.biccamera.com/bc/item/10116901/) · [한국 배송 지원](https://bc.help.buyee.jp/en/countries/)

U20CAM 보드 쪽은 동봉 케이블의 순정 플러그를 유지합니다. 연결은 두 축의 가동 구간 밖에서 고정합니다. USB 인식과 UVC 영상은 연결 뒤 확인하고, 목 좌우 끝–끝–시작점 1,000회 동안과 종료 뒤에 USB 인식이 유지돼야 합니다. [카메라 제조사 설명서](https://github.com/INNO-MAKER/U20CAM-1080P-S1/blob/main/U20CAM-1080P-S1%20UserManual-v1.1.pdf) · [발주표](BOM.csv) · [실물 시험](../../../spec/bench.md#b25-실물-시험)


## 가이드와 전체 경로

로터의 R40 통과 구간은 중심선 간극이 2.85 mm에서 3.05 mm로 늘었습니다. 전체 가동 경로에서는 Sanwa R25의 뒤쪽 고정선 진입과 10% 길이 여유가 남았습니다. 제품 최소 반경에 맞춰 R16으로 낮춘 시안도 뒤쪽 OpenRB USB 선과 0.96 mm 겹쳤습니다. 대체 실리콘 선재 Eaton U040-B03-C-2는 공칭 Ø2.8 mm에서 R16.8 이상이 필요합니다. 시험한 R18 경로의 경성 부품·선 자체 겹침은 289개 자세에서 없었고, 실제 고정점·인접 배선 공차와 약 87 mm의 여유를 넣을 공간은 미검증입니다. [국부 형상과 출력 검사](local-geometry-checks.json) · [Eaton 제조사 사양](https://assets.tripplite.com/product-pdfs/en/u040b03c2.pdf)
