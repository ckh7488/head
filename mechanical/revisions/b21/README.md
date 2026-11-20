# R5 B21 제작과 조립

[FreeCAD 조립본](R5-B21-Assembly.FCStd) · [Bambu P2S 전체판](R5-B21-P2S.3mf) · [조립 절차](../../ASSEMBLY.md) · [부품표](../../BOM.csv) · [3D 조립 화면](../../../web/README.md#b21-조립-순서)

엣지 클램프 두 개로 선택 C3 보드를 잡습니다. 일반 출력물 체결은 M3×8·M3×16 원통머리와 일반 M3 너트를 씁니다. M2와 M2.5는 구매품의 장착 구멍에 씁니다. 눈과 눈꺼풀 관절 일곱 곳은 Ø2 연마핀으로 회전하고 M3×3 평끝 무두나사가 핀을 잡습니다.

## 출력과 조립

P2S에서 0.4 mm 노즐, Textured PEI Plate, Bambu PETG HF로 출력합니다. 3MF를 Bambu Studio에서 프로젝트로 엽니다. 1~12번은 기본 부품, 13번은 선택 균형추입니다. 8번 판의 눈꺼풀 혼과 링크에만 서포트가 추가됩니다. 3번 판의 C3 클램프는 선택 RF 기판을 달 때 사용합니다.

눈 링크는 본체에 올리기 전에 핀 구멍과 M3 탭을 정리합니다. 목 받침은 5.5 mm 스패너 두 개로 위아래 너트를 잡을 수 있습니다. 너트 방향과 오른쪽 턱 받침을 넣는 방향은 3D 조립 화면에서 확인합니다.

## 검사 기록

[검사 결과](checks.json) · [조립 순서와 공구](assembly-check.json) · [턱 개방 스토퍼](jaw-stop.json) · [출력 경로](slicing-check.json) · [눈꺼풀 하중](blink-load.json) · [턱 주변 배선](jaw-wiring.json)

조립 122단계에서 너트 공구 경로 62개와 육각렌치 경로 116개를 확인했습니다. 구동 자세 26,408개와 체결품 49개의 움직임 검사에서 충돌이 없었습니다. 안착 검사에서는 B20에 기록된 접촉만 남았으며, 구매품 등의 열린 메시가 있는 30쌍은 접촉 부피가 미산정입니다. [안착 기록](static-pairs.json) · [구동 자세](head-clearance.json) · [구동 중 체결품](hardware-sweep.json)

변경된 3·6·7·8·9번 판을 다시 슬라이스했습니다. 44개 부품에서 슬라이서 경고와 지지 없이 시작하는 압출 경로가 모두 0건이었습니다. 5개 판의 예상 소모량은 387 g, 예상 시간은 20시간 15분입니다. 나머지 8개 판은 B20의 형상·배치·설정을 사용합니다.

슬라이서의 부품별 압출량과 CAD의 구매품 질량을 합산하면 목 상하축을 따라 움직이는 부분은 약 615 g입니다. 턱 자체는 약 48 g입니다. [출력 질량 입력](sliced-grams.json)

눈꺼풀은 한쪽에 0.25·0.5·1 N을 잠깐 가하는 조건을 양쪽에 따로 적용했습니다. 1 N에서 계산상 88.4°까지 닫혔고 힘이 사라지면 원위치로 돌아왔습니다. 1 N은 가벼운 접촉을 비교하기 위해 정한 모델 입력입니다. 무두나사와 핀의 성능은 출력 후 손으로 움직여 끼움을 확인하고 실물 왕복에서 검증합니다.

턱 시험은 목 정면에서 0–8°를 사용합니다. 스토퍼는 CAD의 기준 치수에서 9.40°, 각 축의 ±0.20 mm 조합 27가지에서 8.72–10.10°에 걸립니다. 무마찰 중력 낙하와 0.5 GPa 탄성 모델을 겹친 계산에서 약 11.15°까지 열렸습니다. 배선 검사는 목·눈·덮개를 고정한 자세 39개에서 실제 외경에 여유를 더해 턱 행정을 확인합니다. [턱 개방각과 배선 범위](jaw-envelope.json) · [중립에서 턱 접촉](jaw-touch.json)

목 상하축은 전원을 빼기 전에 머리를 받칩니다. 정전 시 기어 마찰과 목의 정지 위치는 실물 구동 확인 항목입니다. [초기 보정과 구동](../../../control/README.md#openrb와-모터)

## 다시 만들기

저장소 루트에서 FreeCAD Python 모듈, [기구 검사 의존성](../../physics/requirements.txt), Node.js를 사용할 수 있는 환경에서 실행합니다. 설치 경로에 맞게 FreeCAD 모듈 경로를 지정합니다.

```sh
out=build/b21
python mechanical/build_b21.py "$out"
python mechanical/physics/export_cad.py --world --cad "$out/R5-B21-Assembly.FCStd" "$out/cad"
python mechanical/physics/run_b21_checks.py "$out/R5-B21-Assembly.FCStd" "$out/cad" "$out/hardware.json" "$out/hardware-spec.json" "$out/checks"
python mechanical/build_b21_print.py "$out/R5-B21-P2S.3mf" --print-dir "$out/print" --report "$out/project-check.json"
```

검사 결과는 실행마다 생기는 하위 폴더에 저장됩니다. 동일한 CAD 해시와 계획을 가진 `assembly.json`으로 [3D 조립 화면을 다시 만듭니다](../../../web/README.md#b21-조립-순서).
