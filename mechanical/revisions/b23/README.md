# R5 B23 제작과 조립

[FreeCAD 조립본](R5-B23-Assembly.FCStd) · [Bambu P2S 프로젝트](R5-B23-P2S.3mf) · [조립 순서](assembly.md) · [검사 결과](verification.json)

앞 해골을 끼우는 길에서 오른쪽 눈 상하 링크가 걸리던 곳에 내부 여유를 냈습니다. 눈 모듈의 링크와 핀을 다 넣고 해골을 정면에서 곧게 끼웁니다. 눈 상하 링크의 최소 힘 전달각은 42.15°입니다. 목 좌우축의 무게는 PET 시임을 거쳐 6816 베어링에 실립니다. 목의 좌우 스토퍼는 베어링을 먼저 끼우고 기존 M3×16 두 곳으로 고정합니다. 뒤 배선과 하부 보드 덮개에는 일반 M3 너트가 남는 구조를 적용했습니다. [구조와 치수](design.json) · [앞 해골 삽입](front-841.json)

## 출력과 구매품

P2S에서 **0.4 mm 노즐, 0.20 mm 층, 텍스처 PEI, Bambu PETG HF** 설정으로 3MF를 프로젝트로 엽니다. 변경된 8개 판의 예상 소모량은 920 g, 시간은 47시간 5분입니다. 4번 판의 앞 해골은 코받침과 함께 나옵니다. 6번 판에서 스토퍼 두 개는 베어링 받침과 별도로 출력됩니다. 키 어깨와 받침 홈, 8번 판의 회전판 통로, 12번 판의 카메라 브래킷에 남은 서포트를 제거합니다. [플레이트별 슬라이싱 결과](slicing-check.json)

목 좌우축에 **0.10 mm PET 평판 링** 한 장을 사용합니다. 안지름은 80.10 mm, 바깥지름은 84.50 mm입니다. 내륜에 평평하게 올리고 회전판을 앉힌 상태에서 ID4 위치를 잡습니다. 볼트는 M3×8·M3×16 원통머리 육각렌치형과 일반 육각너트가 기본입니다. 구매 모터·보드와 목 제한판 핀은 조립 단계에 표시한 체결품을 사용합니다. [PET 링 STEP](yaw-shim.step) · [공구와 결합 순서](assembly.md)

## 확인 범위

조립은 실제 부품 형상과 지정 공구로 삽입 경로를 검사했습니다. 움직임은 정상 자세의 강체 간섭, 정전 시 목과 턱의 도달 범위, 선의 꺾임과 간격을 따로 검사했습니다. 힘 경로 계산은 출력 질량, 중력, 구동 관성과 마찰 예산을 사용합니다. 가볍게 닿는 경우는 정지부의 하중과 자유로 움직이는 축에 대한 모터 여유를 각각 계산했습니다. [검사 결과](verification.json) · [힘 경로](force-path.json) · [목 좌우 스토퍼 탄성 해석](yaw-stop-strength.json)

실물의 핀 정렬·마찰·유격과 깜빡임 50회, 완성품 한 번 조립(P08)은 아직 측정하지 않았습니다. 눈 상하 링크 구멍만의 반전 유격 계산은 1.37–1.71°입니다. 크래들 지지부가 양쪽 극단으로 움직이면 3.42–3.76°까지 가능하므로, 합산 2°는 실물에서 확인합니다. 눈 좌우 핀은 Ø2.20 mm로 마감한 상태에서 가벼운 0.25 N 접촉 시 약 0.046 mm의 반지름 방향 여유가 남는 것으로 계산했습니다. [눈 상하 검사](eye-pitch.json) · [눈 좌우 핀 탄성 해석](eye-yaw-pin-fit.json) · [깜빡임 토크 판정](../../../spec/records/M07.md) · [실물 시험](../../../spec/bench.md)

추적 모델은 영상 지연 120 ms에서 시선 10° 이내를 약 96% 유지했습니다. 정면 복귀 끝에는 일부 조건에서 약 1.3°가 남았습니다. 추적 중 토크가 해제된 턱은 힌지 저항이 작을 때 자중으로 약 8.5° 열릴 수 있었습니다. 턱 소리 시연과 정면 복귀는 완성품에서 다시 확인합니다. [추적·턱 모델](motion-replay.json)

## 다시 만들기

저장소 루트에서 FreeCAD Python 모듈과 [기구 검사 의존성](../../physics/requirements.txt)을 사용할 수 있는 환경에서 실행합니다.

```sh
rev=mechanical/revisions/b23
out=build/b23
assembly="$rev/R5-B23-Assembly.FCStd"
python mechanical/build_b23.py "$out"
python mechanical/physics/export_cad.py --world --cad "$out/R5-B23-Assembly.FCStd" "$out/cad"
python mechanical/build_b23_print.py "$out/R5-B23-P2S.3mf" --service-prints "$out/print" --nose "$out/print/26_u20cam_slotted_bracket-B23.stl" --front-shell "$out/cad/world/Part073.stl" "$out/cad/world/Part065.stl" "$rev/printing/nasal-tray-with-pilots.stl"
historical="$out/b23-source"
mkdir -p "$historical"
git archive 0e94ed2 control/openrb/R5B1/R5B1.ino control/pc/track.py mechanical/physics/b23_motion_replay.py | tar -x -C "$historical"
python mechanical/physics/verify_b23_release.py "$rev" --source "$historical"
```

조립 HTML을 만들거나 기존 리비전의 조립 경로를 다시 검사할 때는, 위 명령의 `--cad`에 `"$assembly"`를 넣어 검사 데이터와 동일한 배포본을 내보냅니다. [3D 뷰어 생성법](../../../web/README.md#b23-조립-순서)
