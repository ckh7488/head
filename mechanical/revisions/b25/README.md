# R5 B25 동결 검토

**맞춤 게이지와 시험판을 사용합니다. 전체 출력과 발주 전에 판정표의 막음 항목을 해결해야 합니다.** [고정 검사 조건](../../../spec/conditions.md) · [검토와 판정 절차](../../../spec/review.md) · [리뷰 판정표](review-disposition.md)

- [FreeCAD 조립본](R5-B25-Assembly.FCStd) · [B25 전체 P2S 프로젝트](R5-B25-P2S.3mf) · [3D 조립 미리보기](../../../web/README.md#b25-조립-미리보기)
- [B25 발주 변경과 조립](assembly.md) · [B25 발주표](BOM.csv) · [목 상하축 가공 STEP과 도면](pitch-drive-shaft.md)
- [맞춤 게이지와 치수별 출력 파일](fit-gauge.md) · [서보 허브 A3 발주 검토](../../../electronics/README.md)

B25의 변경은 발주표 및 조립 변경 안내를 먼저 적용합니다. 공통 부품표와 B24 조립 절차는 나머지 기구 자리에 사용합니다. 전원과 배선은 A3 문서와 고정 14절을 적용합니다. 기존 전체 3MF의 3번 판에서는 C3 전용 캐리어와 클램프 두 개를 출력 목록에서 해제합니다. [B24 조립과 가공](../b24/) · [기존 공통 부품표](../../BOM.csv)

## 기존 검증 기록

- [형상](design.json) · [출력판 대조](print-build.json) · [정밀 슬라이스](print-precision-check.json) · [5번 판](plate5-check.json)
- [카메라와 눈꺼풀 형상](blink-fit.json) · [이전 CAD 검증과 재현 명령](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/mechanical/revisions/b25/README.md)

J2 정비선, 목 스토퍼와 턱 장착 시안은 별도 검토 기록에 있습니다. B25 검사 판정은 고정 조건을 따릅니다. [J2](j2-pigtail.md) · [목](neck-load-study.md) · [이전 턱 고정 시안](jaw-candidate.md) · [현재 턱 이탈 경로 검사](jaw-retention-witness.md)
