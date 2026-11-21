# R5 B25 기구 검토 후보

**전체 출력과 발주는 보류합니다.** B25는 B24 조립에서 뒤 외장 고정, 눈꺼풀 간섭, J2 형상을 다시 만든 후보입니다. [FreeCAD 조립본](R5-B25-Assembly.FCStd) · [P2S 프로젝트](R5-B25-P2S.3mf) · [형상 기록](design.json) · [출력판 대조](print-build.json)

## 조립에서 바뀐 곳

- **뒤 외장**은 B24 방향 그대로 밀어 넣습니다. 먼저 프레임 양쪽 뒤가 열린 슬롯에 일반 M3 육각너트를 넣습니다. 외장을 앉힌 뒤 좌우에서 M3×16 원통머리 나사 두 개를 넣고 2.5 mm 육각렌치로 조입니다. 분해할 때는 전원을 끄고 목과 외장을 받친 뒤 두 나사를 빼고 뒤로 곧게 빼냅니다.
- **눈꺼풀**은 앞 외장 안쪽의 B24 국부 절삭을 되돌리고 왼쪽 눈꺼풀의 바깥 핀 멈춤턱 주변을 다듬었습니다. 핀 받침과 파일럿은 유지했습니다. 7번 판의 Ø10.24 mm 베어링 포켓은 턱을 보존하고, 각 포켓 가운데에 폭 1.0–1.2 mm 금속 시임 띠를 맞춥니다. 띠의 지름 간극 목표는 약 0.030 mm이고 양쪽 포켓 끝은 넓게 둡니다. 안쪽 간격통에는 약 0.10 mm 축방향 여유를 둡니다. 모터 링크를 풀고 한 바퀴 돌렸을 때 걸림이 없어야 합니다. 조립 상태에서 축 중심의 총 방사 편차가 베어링마다 0.025 mm 이내인지 측정합니다. 이 수치에는 띠 위치, 베어링 간극, 축 끼움이 모두 들어갑니다.
- **하부 기판**의 J2는 실제 Phoenix 1715721의 기판 위 높이 13.8 mm를 표시합니다. J2 양극·접지 위치도 실제 패드와 일치시켰습니다. 기존 덮개를 내려서는 표준 드라이버로 J2에 접근할 수 없고, 빠져 있던 일곱 가닥의 동시 배선 경로도 아직 없습니다. [J2 제조사 사양](https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-mkds-15-2-508-1715721)

- **XL330 케이스**의 출력 두께에 따라 모터 동봉 M2×8 탭 나사 11개와 M2×6 탭 나사 5개를 나누어 씁니다. 16곳 모두 CAD에서 머리와 공구가 들어가는 경로를 확인했습니다. [나사 배정과 검사](xl330-case-screws.md)

목 상하축의 기존 구동과 스토퍼는 외장에 직접 1 N이 걸리는 조건에서 여유가 부족합니다. 보강 후보에 필요한 구동 토크와 스토퍼 하중을 계산했습니다. [목 하중과 보강 후보](neck-load-study.md)

조립 경로 152개 중 151개를 CAD에서 확인했습니다. 나머지 하부 덮개 경로에는 배선의 굽힘과 J2 공구 접근 문제가 남아 있습니다. [B25 조립 미리보기 생성](../../../web/README.md#b25-조립-미리보기) · [A3 전원과 남은 시험](../../../electronics/README.md) · [B24 원본 기록과 가공 절차](../b24/)

## 재현

FreeCAD Python과 [기구 검사 의존성](../../physics/requirements.txt)을 설치한 환경에서 저장소 루트에서 실행합니다.

```sh
export PYTHONPATH="$PWD/mechanical${PYTHONPATH:+:$PYTHONPATH}"
out=build/b25
python mechanical/build_b25.py "$out"
python mechanical/physics/export_cad.py --world --cad "$out/R5-B25-Assembly.FCStd" "$out/cad"
python mechanical/physics/check_b25_rear_retention.py "$out/R5-B25-Assembly.FCStd" "$out/rear-retention.json"
python mechanical/physics/check_b24_jaw_close.py "$out/cad" control/openrb/R5B1/R5B1.ino "$out/jaw-clearance.json"
```

P2S 프로젝트는 B24와 같은 0.4 mm 노즐, PETG HF, Textured PEI와 0.20 mm 레이어 설정입니다. 변경 판은 앞 외장 4번, 뒤 외장 5번, 머리 프레임 6번, 왼쪽 눈꺼풀 9번입니다. [출력판 변경 기록](print-build.json)
