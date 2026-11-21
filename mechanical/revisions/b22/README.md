# R5 B22 제작과 조립

[FreeCAD 조립본](R5-B22-Assembly.FCStd) · [Bambu P2S 출력판](R5-B22-P2S.3mf) · [조립 순서](assembly.md) · [부품표](../../BOM.csv) · [제어 보정](../../../control/README.md)

## 출력

P2S에서 0.4 mm 노즐, 텍스처 PEI 판, Bambu PETG HF 프로필을 사용합니다. 3MF를 Bambu Studio에서 프로젝트로 엽니다. 8번 판의 회전축 USB 통과부와 M3 머리 자리는 출력 후 서포트와 브림을 제거합니다. 12번 판의 카메라 브래킷은 아래로 열린 홈에서 서포트를 제거합니다. 케이블 타이 머리는 브래킷 안쪽의 낮은 위치에 놓습니다.

출력물은 M3×8과 M3×16 원통머리 및 일반 M3 육각너트를 기본으로 씁니다. 구매 모터와 보드의 체결은 제품 나사산을 따릅니다. 목 제한판은 12×3 mm S235 강철을 쓰고, 그 두 핀에는 M3×3 평끝 무두나사를 씁니다. [제한판 STEP](pitch-strap.step) 조립에는 2.5 mm 육각렌치와 5.5 mm 오픈 스패너를 사용합니다.

앞 해골과 코 받침은 4번 판에서 한 부품으로 출력합니다. 안쪽에서 Ø2.5 mm 드릴로 표시한 깊이 약 4 mm까지만 파일럿을 정리하고 M3 탭을 냅니다. 카메라 기판은 작업대에서 렌즈를 끼운 상태로 브래킷에 넣고 M2×8 두 개로 고정합니다. 카메라 브래킷을 받침에 고정하는 나사는 M3×8 두 개입니다.

## 배선

동봉 Ø4 mm 카메라 케이블의 작은 플러그를 빈 받침부터 넣습니다. USB-A 플러그는 뒤로 남깁니다. 회전축 가이드에서는 선이 약 51 mm 움직일 수 있게 둡니다. 코의 열린 받침과 외부 고정점에서만 피복을 잡습니다. 바닥판에 들어가는 위치까지 안쪽 케이블 길이는 약 337 mm입니다.

케이스 없이 설치할 때는 받침대에 고정한 ㄱ자 지지대에 접착식 타이 마운트(J15)와 재사용 타이(J16)를 달아 USB-A 몸체 앞의 피복을 잡습니다. 받침대 윗면이 본체 CAD의 Z=−83 mm이면 타이 마운트 밑면의 기준점은 X=56.5, Y=150, Z=−69.5 mm입니다. 선은 +Y 뒤쪽으로 뻗으며, 고정점에 있는 피복 중심은 X=56.5, Y=154, Z=−57.5 mm입니다. 하부 다리를 올려 본체가 높아지면 지지대 높이도 같은 만큼 올립니다. [받침대 고정부 간섭 검사](pedestal-cable-check.json)

## 덮개 정비

뒤 배선 덮개와 아래 보드 덮개의 M3 너트를 남기는 시안을 준비했습니다. [정비 시안 CAD·출력과 검사](service-covers.md)

## 구동

목은 명령 각도 −15°~+4.5°, 턱은 5.5°(앞니에서 약 5.6 mm 개방)를 사용합니다. 목의 강철 제한판이 전원 차단 때 양쪽 이동 끝을 잡습니다. 박물관 받침대는 수평이고 동공 높이는 바닥에서 1.4 m로 잡습니다. 각 축은 실물 중립과 끝점을 읽어 보정합니다.

계산은 보정 범위의 질량·토크·간섭과 전원 차단 거동을 대상으로 합니다. 출력물의 실제 마찰과 반복 사용에 따른 케이블 수명은 모델 범위 밖입니다.

## 선택 보호 케이스

아래는 별도 케이스 설계입니다. 접촉 하중 결과는 이 케이스에 해당합니다. 케이스는 3 mm 투명 PMMA 판과 10 mm 합판 바닥을 사용합니다. 아크릴은 탄성률 2.5 GPa 이상으로 잡았습니다. 기존 2.5 mm 육각렌치와 5.5 mm 스패너에 맞는 M3×16 원통머리와 일반 육각너트 35쌍을 사용합니다. [케이스 절단·천공 치수](guard-layout.json)

[케이스 클립 P2S 출력판](R5-B22-Guard-P2S.3mf)은 9개를 한 판에서 출력합니다. PETG HF 예상 소모량은 18.3 g, 시간은 약 43분입니다.

## 다시 만들기

저장소 루트에서 FreeCAD Python 모듈과 [기구 검사 의존성](../../physics/requirements.txt)을 사용할 수 있는 환경에서 실행합니다.

```sh
out=build/b22
rev=mechanical/revisions/b22
python mechanical/build_b22.py "$out" --camera-routing "$rev/camera-routing.json"
python mechanical/build_b22_guard.py "$rev/R5-B22-Assembly.FCStd" "$out/Guard.FCStd" --print-dir "$out/guard-print"
python mechanical/physics/export_cad.py --world --cad "$rev/R5-B22-Assembly.FCStd" "$out/cad"
python mechanical/physics/check_b22_camera_routes.py "$out/cad" "$rev/camera-paths.npz" "$out/camera-check.json"
```

검사 데이터는 함께 제공한 CAD 파일에 묶여 있습니다. [검사 기록](verification.json) 새로 만든 CAD는 새 내보내기 결과를 사용해 검사합니다.
