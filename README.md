# R5 로봇 헤드

코의 USB 카메라로 사람을 보고 눈·목·눈꺼풀·턱을 움직이는 전시용 해골입니다. 얼굴 추적은 PC에서, 여섯 축 구동은 OpenRB-150에서 실행합니다. A1 서보 허브가 전원을 공급하고 모터 통신을 분기합니다. A1 ESP32-C3 보드는 별도의 2.4 GHz 안테나 실험용입니다.

## 현재 검토 대상

**B24 기구·펌웨어와 A1 PCB 두 종이 검토 대상입니다. 전체 출력과 부품·PCB 발주는 보류 상태입니다.**

| 확인할 내용 | 시작 파일 |
| --- | --- |
| 검토 대상 커밋, 다시 실행할 명령, 발견한 문제 | [B24·A1 검토 안내](REVIEW.md) |
| FreeCAD 조립본, P2S 출력판, 조립 순서 | [B24 기구 파일](https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24) |
| 대화 없이 3D 조립·구동 열기 | [브라우저용 모델 만들기](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/web/README.md#b24-조립-순서) |
| 두 KiCad 프로젝트, PCB 출력 파일과 배선 | [A1 전자 설계](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/README.md) |
| 펌웨어, 얼굴 추적, 실물 판정 | [제어](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/README.md) · [B24 실물 검수](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/README.md#실물-검수) |

기본 브랜치의 CAD와 조립 문서는 B18 이하 이력입니다. [이전 첫 화면](https://github.com/ckh7488/head/blob/aea5a97dc126997b99470e445302394d638795f6/README.md)
