# R5 로봇 헤드

R5는 코에 달린 USB 카메라로 얼굴을 검출해 사람의 두 눈 사이를 따라보는 해골 로봇 헤드입니다. PC가 카메라 영상을 처리하고, OpenRB-150이 눈 좌우·상하, 눈꺼풀, 목 좌우·상하, 턱의 여섯 축을 구동합니다. ESP32-C3 기판은 2.4 GHz 안테나 실험용입니다.

![목 배선 가림막을 끼운 R5 B18 시안의 정면](mechanical/revisions/b18/study/neck-cover-preview.jpg)

B18 목 가림막 시안입니다. [CAD 개정 이력](mechanical/revisions/) · [모델과 자료 출처](web/README.md#모델과-자료-출처)

## 디렉터리 구성

- [mechanical/](mechanical/README.md) · FreeCAD 조립본, P1S·P2S 출력판, 부품표, 기구 검증과 조립 순서
- [electronics/](electronics/README.md) · KiCad 회로와 PCB, 발주 파일, 전원과 배선
- [control/](control/README.md) · PC 얼굴 추적, OpenRB 펌웨어, 카메라와 모터 보정
- [web/](web/README.md) · 3D 조립·구동·배선 뷰어, CAD 내보내기
- [tests/](tests/) · 모터 보정, 펌웨어와 가상 USB 통신 시험. [실행법](control/README.md#하드웨어-없이-실행)

## 최근 CAD

- **B19 체결품과 조립 불가 지점** · 모든 모터·링크 체결품의 길이를 정하고, 나사를 넣을 수 없던 자리와 머리가 끄덕이지 않던 목 상하축을 고쳤습니다. 조립 순서 122단계를 하나씩 넣어 보며 막히는 곳을 모두 고쳤습니다. [B19 조립 절차](mechanical/ASSEMBLY.md) · [부품표](mechanical/BOM.csv) · [제작할 파일 목록](mechanical/revisions/#제작할-파일-b19-기준) · [B19 검사](mechanical/revisions/b19/)
- **B18 후면 연결부** · 외부에서 USB 두 개와 5 V·12 V 전원 플러그를 잡고 뺄 수 있는 배치입니다. [조립본과 뒤쪽 3D 보기](mechanical/revisions/b18/)
- **B18 개선 시안** · 고정 허브, 30 mm 내려가는 덮개, 목 12 V 경로와 가림막을 비교합니다. 제작 전에 남은 확인 사항을 함께 기록했습니다. [FreeCAD와 전후 비교](mechanical/revisions/b18/study/)

## B15 제작과 조립

![B15 조립 외형과 외장 안쪽의 배선·체결품](mechanical/assembly/b15-readme.jpg)

- [FreeCAD 조립본](mechanical/R5-B15-Assembly.FCStd) · [기구 부품표](mechanical/BOM.csv)
- [P2S 전체판 12장과 선택 1장](mechanical/R5-B15-P2S.3mf) · [P2S 시험판](mechanical/R5-B15-Fit-P2S.3mf) · [출력 설정](mechanical/README.md#p2s-출력-설정)
- [조립 절차](mechanical/ASSEMBLY.md) · [체결품과 배선을 장착한 상태의 구동 검사](mechanical/ASSEMBLY.md#배선과-체결품을-단-상태의-구동-검사)

P2S 출력판은 **0.4 mm 노즐과 Bambu PETG HF** 기준입니다.
앞 해골의 출력 경사, 눈꺼풀 축 홈, 목 볼트와 JST 통로를 수정한 형상이 들어 있습니다.
시험판 2번은 케이블, 3번은 바닥 덮개와 허브, 4번은 보드 캐리어를 확인하는 데 씁니다. [출력 경로 검사](mechanical/README.md#출력-경로-검사)
