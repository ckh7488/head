# R5 B25 제작 자료

현재 B25 조립본과 P2S 출력 프로젝트는 같은 조정본입니다. 눈 타이바·목 스토퍼·오른쪽 턱 받침·뒤 배선 덮개를 수정했고, 출력 부품 57개를 14판에 배치했습니다. 조립, 유격, 5 N 외장 강건성과 전원·배선은 실물 시험에 기록합니다. [통합 검사](alignment.md) · [고정 검사 조건](../../../spec/conditions.md) · [실물 시험](../../../spec/bench.md#b25-실물-시험)

- [FreeCAD 조립본](R5-B25-Assembly.FCStd) · [B25 전체 P2S 프로젝트](R5-B25-P2S.3mf) · [저장소에서 조립·구동 화면 열기](../../../web/README.md#b25-웹-화면)
- [B25 발주 변경과 조립](assembly.md) · [B25 발주표](BOM.csv) · [목 상하축 가공 STEP과 도면](pitch-drive-shaft.md)
- [서울 시험 출력 목록](01-seoul-print.md) · [시험 전 준비품](02-order-before.md) · [시험 뒤 전장 발주](03-order-after.md)
- [맞춤 게이지와 치수별 출력 파일](fit-gauge.md) · [서보 허브 A4 발주 검토](../../../electronics/README.md)

구매에는 위 두 목록의 시판 규격을 사용합니다. 발주표에 적힌 개별 제품은 CAD·시험 기록에서 사용한 참조품입니다. B24 조립 절차는 공통 기구를 참고하는 데 씁니다. B25 핀·턱·배선·전원은 B25 조립 절차에 맞춥니다. [B24 공통 조립](../b24/assembly.md) · [A4 전원과 배선](../../../electronics/README.md)

## 검증 기록

- [15번 타이바와 12번 크래들 최신 검사](eye-yaw-clearance.json) · [초기 장공과 간섭 기록](eye-yaw-slot.json)
- [형상](design.json) · [출력판 대조](print-build.json) · [뒤 외장 수정과 5·6번 판](rear-left-screw-fit.json) · [이전 정밀 슬라이스](print-precision-check.json)
- [카메라와 눈꺼풀 형상](blink-fit.json) · [이전 CAD 검증과 재현 명령](https://github.com/ckh7488/head/blob/9c024361d586ff5ea582cbac3e1328d40d5b0c65/mechanical/revisions/b25/README.md)

62틱 턱, 세 점 고정, Eaton 카메라선과 A4의 앞선 설계와 검사 기록도 보관합니다. [이전 판정](frozen-fixes-check.md) · [A4 전원·정비 경로](a4-supply-recheck.json) · [Eaton 경로](camera-r18-recheck.json) · [이전 목 스토퍼 시안](neck-load-study.md)
