# B16 배선 검토

B16의 받침 배선 교차, 눈·턱 동작 중 접촉, 턱 DATA선의 굽힘 반경을 검토했습니다. 배선 그룹에는 중립 자세의 중심선, 외경, 모델 절단 길이와 굽힘 반경이 있습니다. [B16 FreeCAD 조립본](R5-B16-Wiring.FCStd)

목 전원 가드, 30 cm 시선과 넓힌 덮개 루프는 [B17 검토](../b17/)에 기록했습니다.

## B16 출력판

| 프린터 | 전체판 | 시험판 |
| --- | --- | --- |
| P2S | [13장](R5-B16-P2S.3mf) | [4장](R5-B16-Fit-P2S.3mf) |
| P1S | [13장](R5-B16-P1S.3mf) | [4장](R5-B16-Fit-P1S.3mf) |

전체판의 받침(1번), 목 회전판(8번), 케이블 트레이(11번)와 시험판 2번의 트레이·받침 단면 시편에 B16 형상을 적용했습니다. 최신 B15 P2S의 부품 배치와 프린터별 기존 0.4 mm 노즐·PETG HF 설정을 사용합니다. Bambu Studio 2.9.1.70에서 각 프린터의 전체판 13장과 시험판 4장이 모두 슬라이스됐으며 각 판의 결과 경고는 0건입니다. 회전판 3MF에서 카메라 통로와 턱 DATA 통로에 각각 Ø2.5 mm 검사봉이 지났습니다.

## 변경한 형상

- **J1 5 V 입력선.** 5 V 선을 **패드 2(X −10 mm)**, GND를 **패드 1(X −5 mm)**에 맞췄습니다. 같은 길이에서 서로 지나갈 수 있도록 뒤쪽 U자 구간을 다시 배치하고, 트레이 통과 홈 상단을 0.5 mm 높였습니다. 분기에서 단자까지의 목표 중심선 길이는 양극 **186.508 mm**, GND **172.483 mm**입니다. 실물 단자에 끼우는 피복 제거 길이는 단자에 맞춰 덧붙입니다.
- **J6 DATA.** J6 핀 3에서 **52 mm 점퍼 한 가닥**이 고정 WAGO에 연결됩니다. WAGO의 다른 두 포트에서 눈꺼풀 ID3와 턱 ID6의 DATA선을 각각 보냅니다. FreeCAD 배선 그룹에서 WAGO 자리와 세 선의 끝점을 확인할 수 있습니다.
- **받침 배선.** 턱 퓨즈 입력선은 기존 중심선 길이 **141.838 mm**로 왼쪽 리브의 Ø3.2 mm 통로를 지납니다. ID5 세 가닥은 허브 앞쪽에서 J7 위로 지나갑니다. 카메라선은 **365 mm**를 유지하고 허브 뒤쪽으로 돌아 회전판의 기존 **Ø6.4 mm** 통로로 들어갑니다. 카메라 플러그 통과 여유는 **8.4 × 5.8 mm**입니다.
- **눈 좌우 ID1.** 실제 뒤쪽 JST 단자의 삽입 방향으로 세 가닥을 아래로 빼고, 눈이 내려갈 때 카메라선과 벌어지도록 위쪽 경로를 조정했습니다. 절단 길이는 GND **351 mm**, 전원 **352 mm**, DATA **355 mm**입니다. [ROBOTIS XL330 단자](https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#connector-information) · [JST EH 치수도](https://www.jst-mfg.com/product/pdf/eng/eEH.pdf)
- **턱 ID6.** DATA선 **416 mm**는 받침 아래에서 큰 반원으로 돌고, 회전판 옆 Ø3.3 mm 통로를 지나 턱 뒤 JST 단자로 이어집니다. 전원 **315 mm**, GND **399 mm**도 실제 단자 방향에 맞췄습니다. DATA선의 기준 반경 **5.715 mm**는 외경 **1.143 mm**의 5배입니다. [Alpha Wire 6712 사양](https://www.alphawire.com/products/wire/ecogen/ecowire/6712)

## 검사하는 방법

검사한 20가닥은 5 V 입력 2가닥, 모터 15가닥, 카메라, J6 점퍼, 퓨즈 입력선입니다. 기존 참조 경로 12가닥과의 교차도 비교합니다. 끝점은 부품과 함께 움직이고 각 선의 목표 중심선 길이는 고정합니다. 목 하네스의 여유 구간은 각 자세에서 고정 길이에 맞춰 휘게 합니다. 분홍색 표시는 간섭 위치, 주황색 표시는 굽힘 위치입니다.

덮개 0~30 mm는 1 mm 간격으로 검사합니다. 목 좌우 ±60°는 5° 간격, 상하 −15°~+6°는 3° 간격의 모든 조합을 검사합니다. 네 끝 자세는 눈과 턱을 중립으로 두고 덮개를 30 mm 내린 상태에서도 검사합니다. 눈 상하 ±8°, 턱 13°를 포함한 추가 자세도 확인합니다. 부품 근접 판정에는 전선 외피 반지름에 0.25 mm를 더합니다. 전선끼리는 피복이 0.06 mm를 넘게 겹친 구간을 표시합니다. 자기 겹침은 선을 따라 3 mm와 외경의 두 배 중 큰 값보다 떨어진 구간을 비교합니다.

각 자세의 기하 형상을 계산합니다. 케이블의 실제 강성, 고정부 반력, 마찰, 연속 이동에 따른 형상 이력과 반복 수명은 실물과 대조하는 범위입니다. 카메라선의 굽힘 기준은 모델 비교용으로 12 mm를 가정했습니다.

## 출력 전 확인할 위치

- **뒤 트레이 밑의 5 V 처짐.** 덮개가 닫혔을 때 GND선 외피와 받침 최저 평면의 모델 간격은 **0.97 mm**입니다. 루프 높이와 자중 처짐은 조립 후 실물에서 확인합니다. [Alpha Wire 3055 사양](https://www.alphawire.com/en/products/wire/hook-up-wire/premium/3055.aspx)
- **동봉 카메라선.** 모델에서 움직임과 함께 검사한 구간은 365 mm입니다. 동봉 1 m 케이블을 쓰는 경우에는 남는 길이를 정지부에서 잡아둘 위치를 별도로 맞춥니다.
- **덮개 정비용 하네스.** J2·J3·J7의 참조선 7가닥은 덮개가 0~30 mm 움직이면 표시 길이가 **23.23~27.87 mm** 늘어납니다. 참조 경로끼리 **10쌍**이 겹칩니다. 실제 절단 길이와 고정 위치를 정한 뒤 같은 30 mm 이동에서 여유와 간섭을 확인합니다. HTML의 `기존 배선 비교`를 켜면 참조선 사이의 겹침이 표시됩니다.

## 같은 266개 자세에서 비교

| 검사 항목 | 수정 전 | 수정 후 |
| --- | ---: | ---: |
| 덮개 30 mm와 목 복합 끝자세 네 조합의 배선 교차 | 12쌍 | 0쌍 |
| 266개 자세 전체의 서로 다른 배선 교차 | 15쌍 | 0쌍 |
| ID1 또는 카메라선이 부품에 닿은 자세 | 12개 | 0개 |
| 턱 DATA의 최소 굽힘 반경 | 0.949 mm | 5.768 mm |

턱 DATA의 최저 반경은 목 좌우 +60°·상하 −15°, 눈 −8°, 턱 13°, 덮개 닫힘에서 기록됐습니다. 기준보다 **0.053 mm** 큽니다. 기존 19가닥의 모델 절단 길이와 두 5 V 루프의 중심선은 그대로 유지했습니다. 모든 표시용 중심선과 목표 길이의 차이는 **0.016 mm 이내**입니다. J7을 포함한 12가닥은 기존 참조 경로를 사용했습니다.

수정 후 266개 자세에서 피복 자기 겹침과 부품 접촉이 없었습니다. ID5 전원선은 목 요크와 32개 자세, 턱과 2개 자세에서 **0.25 mm 이내**입니다. 턱과 가까워지는 두 자세는 덮개 닫힘, 목 +60°/+6°, 눈 ±8°, 턱 13°입니다. ID1과 카메라선의 최소 굽힘 반경은 각각 **0.778 mm**, **2.074 mm**로, 접촉 검사와 별도로 굽힘 여유를 확인합니다.

턱 DATA 여유 루프는 자세별로 배치했습니다. 목 좌우 +60°에서 상하 −12°와 −9°를 비교하면 루프 방향이 바뀌고, 케이블을 따라 같은 길이 비율에 있는 점의 위치가 최대 **102.87 mm** 차이 납니다. 두 자세 사이를 실제 케이블이 지나갈 때의 굽힘과 간섭은 별도 검증 항목입니다.

## 목 모터 정비 시안

ID4·ID5 모터 끝의 EH 플러그를 케이스 체결 위치에 맞춘 가드로 잡습니다. 정비 때는 전원을 뺀 뒤 받침 허브에서 분리합니다. 허브의 5 V J4–J6은 PH, 목 전원 J7–J8은 EH입니다. 모터를 교환할 때는 허브 쪽을 분리한 상태에서 가드를 풀고, 다시 체결한 뒤 허브에 연결합니다. [전압 확인 절차](../../../electronics/README.md#전원과-배선)

가드를 추가한 CAD에서 플러그 외형과 가드 사이의 축 방향 간격은 0.40 mm입니다. 0.10 mm 간격으로 빼 봤을 때 두 가드 모두 0.50 mm 이동에서 플러그 외형에 걸립니다. 기존 266개 자세에서 가드와 배선 사이에 0.25 mm 이내 접촉 후보가 없었습니다. ID4 가드와 장착 브래킷의 솔리드 겹침은 0 mm³입니다. 같은 자세에서 허브 J7과 가장 가까운 5 V 모터 단자 간 직선 거리는 150.60 mm입니다. J7에 연결된 ID4 하네스 길이를 이 거리보다 짧게 잡으면 5 V 모터까지 닿지 않습니다. 가드를 덧댄 체결 길이와 출력물의 고정 강도는 시험 조립에서 확인합니다.

J2에 3055 18 AWG를 쓸 때 외경 2.057 mm와 제조사 굽힘 기준 10배를 적용하면 최소 반경은 20.57 mm입니다. 두 선 모두 J2에서 받침 뒤를 향해 나왔다가 더 앞에 있는 WAGO로 돌아갑니다. 이 방향 조건에서 선 길이는 양극 최소 85.93 mm, GND 최소 64.53 mm입니다. 장애물과 단자 안쪽 길이를 계산에 넣으면 더 길어질 수 있습니다. 닫힌 상태의 기존 참조선은 각각 64.99 mm와 49.62 mm입니다. [3055 굽힘 사양](https://www.alphawire.com/en/products/wire/hook-up-wire/premium/3055.aspx)

## 재현

FreeCAD 모듈을 쓸 수 있는 Python과 [기구 검사 의존성](../../physics/requirements.txt)을 사용합니다. 저장소 루트에서 실행합니다. `python`은 해당 환경의 실행 파일입니다.

```sh
python mechanical/build_wiring_revision.py --cad build/R5-B16-Wiring.FCStd --world build/b16-cad
python mechanical/export_b16_print_projects.py --output build/b16-print-projects
python mechanical/build_neck_plug_keepers.py --output build/R5-B16-service-trial.FCStd
node --input-type=module -e 'import {installedHardware} from "./web/assembly/steps.js"; import {readFileSync,writeFileSync} from "node:fs"; writeFileSync("build/b16-cad/hardware.json",JSON.stringify(installedHardware(JSON.parse(readFileSync("web/assets/assembly.json")).parts)));'
python mechanical/physics/wiring_check.py build/b16-cad build/b16-results --packed --preview --workers 8
python mechanical/physics/check_neighboring_wires.py build/b16-cad build/b16-results
npm ci --prefix web
npx --yes esbuild@0.25.12 web/wiring-review/review.js --bundle --format=iife --minify --outfile=build/b16-review.js
node web/wiring-review/package_review.mjs build/b16-cad build/b16-results build/b16-review.js build/R5-B16-wiring-review.html
```

생성한 HTML 파일은 검사 자세와 3D 모델을 포함합니다. 브라우저에서 파일을 직접 열어 궤적과 간섭 위치를 확인할 수 있습니다. 같은 자세의 수정 전 데이터가 있으면 패키징 명령 끝에 수정 전 검사 결과 디렉터리와 CAD 내보내기 디렉터리를 순서대로 붙입니다.
