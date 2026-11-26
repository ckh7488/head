# R5 로봇 헤드

코의 USB 카메라로 사람을 보고 눈·목·눈꺼풀·턱을 움직이는 6축 전시용 로봇입니다. PC가 얼굴을 찾고 OpenRB-150이 모터를 제어합니다.

**[ATLAS에서 R5 조립·구동·배선·회로 열기](https://ckh7488.github.io/showcase/reports/r5-head/)**

## 초도 제작 기준

**B25 기구 · A5 서보 허브 · P2S PETG HF 18판·57개.** CAD, 출력·발주 파일, 조립·검수 문서는 `r5-b25-a5-prototype` 태그에 모았습니다. 시험 출력은 15번 링크와 13번 턱부터 진행하고, 완성품은 P01–P08 실물 시험으로 확인합니다. [초도 제작 태그](https://github.com/ckh7488/head/tree/r5-b25-a5-prototype) · [제작 안내](https://github.com/ckh7488/head/tree/r5-b25-a5-prototype/mechanical/revisions/b25)

## 이전 B24 검토 기록

아래는 독립 검토에 사용한 B24 기구·펌웨어와 A1 PCB 원본입니다.

| 확인할 내용 | 시작 파일 |
| --- | --- |
| 검토 대상 커밋, 다시 실행할 명령, 발견한 문제 | [B24·A1 검토 안내](REVIEW.md) |
| FreeCAD 조립본, P2S 출력판, 조립 순서 | [B24 기구 파일](https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24) |
| 당시 3D 조립·구동 화면 만들기 | [브라우저용 모델 만들기](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/web/README.md#b24-조립-순서) |
| A1 회로도·PCB 원본 | [서보 허브](https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/servo-hub) · [ESP32-C3](https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/c3-rf) |
| 펌웨어, 얼굴 추적, 실물 판정 | [제어](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/README.md) · [B24 실물 검수](https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/README.md#실물-검수) |

[더 이전 제작 자료](https://github.com/ckh7488/head/blob/aea5a97dc126997b99470e445302394d638795f6/README.md)
