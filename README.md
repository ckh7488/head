# R5 B15 로봇 헤드

R5는 코에 달린 USB 카메라로 얼굴을 검출해 사람의 두 눈 사이를 따라보는 해골 로봇 헤드입니다. PC가 카메라 영상을 처리하고, OpenRB-150이 눈 좌우·상하, 눈꺼풀, 목 좌우·상하, 턱의 여섯 축을 구동합니다. ESP32-C3 기판은 2.4 GHz 안테나 실험용입니다.

## 디렉터리 구성

- [mechanical/](mechanical/README.md) · FreeCAD 조립본, P1S·P2S 출력판, 부품표, 기구 검증과 조립 순서
- [electronics/](electronics/README.md) · KiCad 회로와 PCB, 발주 파일, 전원과 배선
- [control/](control/README.md) · PC 얼굴 추적, OpenRB 펌웨어, 카메라와 모터 보정
- [web/](web/README.md) · 3D 조립·구동·배선 뷰어, CAD 내보내기
- [tests/](tests/) · 모터 보정, 펌웨어와 가상 USB 통신 시험. [실행법](control/README.md#하드웨어-없이-실행)

## B15 제작과 조립

- [FreeCAD 조립본](mechanical/R5-B15-Assembly.FCStd) · [기구 부품표](mechanical/BOM.csv)
- [P2S 전체판 12장과 선택 1장](mechanical/R5-B15-P2S.3mf) · [P2S 시험판](mechanical/R5-B15-Fit-P2S.3mf) · [출력 설정](mechanical/README.md#p2s-출력-설정)
- [조립 절차](mechanical/ASSEMBLY.md) · [체결품과 배선을 장착한 상태의 구동 검사](mechanical/ASSEMBLY.md#배선과-체결품을-단-상태의-구동-검사)

P2S 출력판은 **0.4 mm 노즐과 Bambu PETG HF** 기준입니다. 앞 해골의 출력 경사, 눈꺼풀 축 홈, 목 볼트와 JST 통로를 수정한 형상이 들어 있습니다. 시험판 2번은 케이블, 3번은 바닥 덮개와 허브, 4번은 보드 캐리어를 확인하는 데 씁니다. [출력 경로 검사](mechanical/README.md#출력-경로-검사)
