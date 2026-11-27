# R5 B27 작업 지시서 · 해골 외피 복원과 기계 가림

이 문서 하나로 B27 작업을 처음부터 끝까지 할 수 있게 썼습니다. 위에서 아래 순서대로 진행합니다. 각 단계의 산출물과 통과 조건을 만족해야 다음 단계로 넘어갑니다.

## 1. 목표

R5 해골은 안쪽 기계에 자리를 내주느라 관자(눈 뒤 옆머리)와 턱 경첩 부근이 깎여 있습니다. 그래서 옆에서 보면 눈 받침, 프레임, 턱 팔, 턱 받침, 요크가 보입니다. B27의 목표는 다음 두 가지입니다.

1. 해골 겉모양을 사람 해골 기준 모양으로 되살린다.
2. 그 겉면 안쪽으로 기계를 옮겨서 밖에서 기계가 거의 보이지 않게 한다.

혹처럼 부풀려서 덮는 방법은 쓰지 않습니다. 겉면은 기준 모양을 따라야 합니다.

완료 조건은 다섯 가지입니다.

- `mechanical/physics/check_b27_skull_cover.py`의 다섯 검사(노출, 해부 모양, 움직임 간극, 출력, 빼내는 길)가 모두 PASS
- 조립 절차 점검 막힘 0
- `check_head.py` 충돌 0
- 출력 프로젝트 슬라이스 경고 0

## 2. 이미 정해진 판단

소유자가 정한 것입니다. 바꾸지 않습니다.

| 항목 | 정한 내용 |
| --- | --- |
| 관자 | 기계(13 눈 받침, 09 프레임 옆 탭, 눈 상하 축 핀·베어링, 18 링크 등)를 **안쪽으로 옮긴다**. 해골은 기준 모양으로 되살린다 |
| 턱 경첩 | 턱 아래뼈의 위쪽 가지(하악지·관절돌기·근육돌기)를 되살린 **덮개를 턱과 같이 움직이게** 붙인다. 이를 위해 39·38 턱 팔의 아래 블록을 안쪽으로 줄인다 |
| 머리 바닥 뒤 | 이번에는 손대지 않는다. 노출 검사 영역에서도 빠져 있다 |
| 체결 | 열압입 인서트를 새로 쓰지 않는다. 볼트와 일반 너트를 쓰고, 공구가 닿게 한다. 프린터 오차 ±0.2 mm에 민감한 끼워맞춤(눌러 끼우는 너트 자리, 스냅)을 쓰지 않는다. 구멍은 나사보다 0.4 mm 이상 크게 한다 |
| 벽 | 2 mm 이상. 부딪히는 것이 없고 겉모양에 영향이 없으면 더 두꺼워도 된다. 더 두껍게 할 수 없는 얇은 조각은 깎아 없앤다 |
| 움직이는 틈 | 0.30 mm 이상 (`spec/conditions.md` 2절) |
| A5 전원 커넥터 | J1·J2가 같은 XT30인 것은 소유자가 받아들였다. 다루지 않는다 |

## 3. 저장소와 좌표

- 시작점: `ckh7488/head` 브랜치 `b27-skull-cover`. B26 검수본(`codex/r5-b26-assembly-review`, f5c32a1) 위에 이 지시서, 검사기, 기준 메쉬를 더한 커밋이다. 새 작업 브랜치는 여기서 만든다.
- 단위는 mm다. x는 해골의 오른쪽(+x에 37 턱 받침), y는 앞이 음수(얼굴이 −y), z는 위다.
- 턱은 x축 방향 축을 따라 돈다. 축은 (y −9, z 92)를 지나고 각도 범위는 0–6.6°다(소프트웨어 열림 5.5°, 검증 여유 6.6°). 열면 앞쪽이 내려간다.
- 목 상하는 x축 방향 축을 따라 돈다. 축은 (y 0, z 112)를 지난다. 이때 요크 07과 목 부품(`pan` 묶음)이 머리에 대해 돈다.
- 부품마다 FreeCAD 속성 `Motion`이 있다. 값은 `head`, `jaw`, `pan`, `tilt`, `look1` 등이다. `export_cad.py --world`가 이 값을 `cad_parts.json`의 `world_motion`에 적는다. 자세는 `mechanical/physics/check_head.py`의 `pose()`가 정의한다.
- 턱과 같이 움직이는 부품은 FreeCAD의 `JawMotion` 묶음 안에 둔다(턱 30과 같은 곳). 머리에 붙는 부품은 `Head_frame` 묶음에 둔다.

자주 나오는 부품

| CAD 이름 | 부품 |
| --- | --- |
| Part073 / Part074 | 28 앞 외장(해골 앞) / 29 뒤 외장 |
| Jaw_30_moving_jaw | 30 턱 |
| Jaw_36_left_jaw_servo_stay / Jaw_37_right_jaw_bearing_stay | 36 왼쪽 턱 모터 받침 / 37 오른쪽 턱 베어링 받침 |
| Jaw_38_left_jaw_drive_arm / Jaw_39_right_jaw_pivot_arm | 38 왼쪽 턱 구동 팔 / 39 오른쪽 턱 핀 팔 (턱과 일체 출력) |
| Part019 | 09 머리 프레임 |
| Part025 / Part027 | 13 왼쪽 / 오른쪽 눈 받침 |
| Part024 | 12 눈 상하 받침대 |
| Part044 | 18 눈 상하 링크 |
| Part011 | 07 목 요크 |

## 4. 입력 자료

| 자료 | 위치 |
| --- | --- |
| 기준 해골 모양 | `mechanical/inputs/anatomy/` — 두개골 좌우, 관자 채움(측두와를 겉면과 매끄럽게 메운 덩어리), 아래턱. 설명은 그 폴더의 README |
| 고정 검사 조건 | `mechanical/revisions/b27/cover-spec.json` |
| 검사기 | `mechanical/physics/check_b27_skull_cover.py` |
| 검사기 확인 기록 | `mechanical/revisions/b27/checker-validation.md` — 일부러 틀린 입력을 넣어 검사기가 잡는 것을 확인한 표 |
| B26 기준 결과 | `mechanical/revisions/b27/baseline/` — 기준 검사 결과, 정측면 노출 그림 2장, 부품별 안쪽 이동량 안내 `inward-shift-guide.json`, 옆 실루엣 밖 부품 `side-silhouette-guide.json` |

**목표 겉면**은 둘 중 하나입니다. 하나는 두개골 기준 그 자체(뼈 겉면)이고, 다른 하나는 두개골에 관자 채움을 합친 면입니다. 관자의 깊은 오목면까지 기계를 넣으려면 눈 상하 축을 20 mm 넘게 옮겨야 해서 사실상 불가능합니다. 그래서 관자는 채운 면을 겉면으로 씁니다. 턱 덮개는 아래턱 기준을 따릅니다.

**기계 위치의 기준**은 목표 겉면에서 3.0 mm 안쪽입니다(외피 2.4 mm + 틈 0.6 mm). B26 기준에서 각 부품이 몇 mm 안쪽으로 가야 하는지는 `inward-shift-guide.json`에 있습니다. 숫자는 옆 방향 광선으로 잰 98% 값입니다.

| 부품 (B26) | 9방향 합계 노출 mm² | 안쪽 이동 필요 (98%) |
| --- | ---: | ---: |
| 13 오른쪽 눈 받침 | 3,385 | 7.8 mm |
| 13 왼쪽 눈 받침 | 2,740 | 6.2 mm |
| 09 머리 프레임 | 오른쪽 2,332 / 왼쪽 6,318 | 6.9 / 8.1 mm |
| 눈 상하 베어링 MR63 · Ø3×13 눈 상하 핀 | 각 153 · 77 | 5.7–9.2 mm |
| 18 눈 상하 링크 · 12 눈 상하 받침대 · 23 눈꺼풀 링크 | 150–390 | 2.6–2.7 mm |
| 39 오른쪽 턱 핀 팔 · 37 오른쪽 받침 | 2,911 · 1,858 | 하악지 덮개 안쪽으로 (옆 실루엣 밖은 0.3%) |
| 38 왼쪽 턱 구동 팔 · 36 왼쪽 받침 · 턱 모터 | 2,492 · 1,183 · 26 | 8.5 mm 이상. 옆 실루엣 밖 3–7% (관절돌기와 근육돌기 사이 홈 y −19…−12, z 82…91) |
| 07 요크 | 오른쪽 2,175 / 왼쪽 1,594 | 하악지 뒤 y −2…5, z 67…82가 실루엣 밖 |

턱 쪽 부품은 광선이 하악지 뒤로 빠져서 이동량이 크게 나옵니다. 이 값은 그대로 쓰지 말고 검사기의 노출 그림으로 판단합니다.

## 5. 작업 단계

### 단계 0 · 준비와 기준 재현

1. FreeCAD 1.0 파이썬과 `numpy scipy trimesh embreex manifold3d python-fcl pillow shapely`를 준비한다. 검사기는 메모리 8 GB에서 돈다.
2. 기준 CAD를 내보낸다.
   ```sh
   export PYTHONPATH="$PWD/mechanical:$PWD/mechanical/physics:/usr/lib/freecad-python3/lib"
   python mechanical/physics/export_cad.py --world --cad mechanical/revisions/b26/R5-B26-Assembly.FCStd build/b26/cad
   echo '{"covers": []}' > build/empty-covers.json
   python mechanical/physics/check_b27_skull_cover.py build/b26/cad build/b26/cad build/empty-covers.json build/b26/cover-check.json --images build/b26/cover-check
   ```
3. **통과 조건**: 노출 합계가 `baseline/baseline-check.json`과 ±1% 안에서 같다(오른쪽 14,123 mm², 왼쪽 15,168 mm²). 그리고 anatomy·clearance·print가 PASS다. 다르면 환경 문제이므로 진행하지 않는다.

### 단계 1 · 관자 기계를 안쪽으로

**대상**: 13 눈 받침 좌우, 09 프레임 옆 탭, 눈 상하 축의 핀·베어링, 12 눈 상하 받침대의 바깥 팔, 18 링크, 23 눈꺼풀 링크, 그리고 이들에 딸린 체결품(나사·너트·핀·기존 인서트)

**지킬 것**

- 눈알 중심, 동공 위치, 눈 상하 축선(y −39, z 119 부근의 공통 축)은 그대로 둔다. 축은 그대로 두고 축을 받치는 부품만 안쪽으로 당긴다(핀을 짧게, 받침대 팔을 좁게, 받침을 안쪽으로).
- 눈 상하·좌우·깜빡임 구동 범위를 줄이지 않는다.
- 부품을 옮길 때는 그 부품에 딸린 체결품도 같이 옮긴다. 검사기는 따로 남은 나사·인서트와의 겹침을 실패로 잡는다.
- 09 프레임 탭은 외장 28·29를 붙이는 자리다. 옮기거나 깎은 뒤에도 외장을 고정할 수 있어야 한다.

**산출물**: 수정 생성 스크립트 `mechanical/build_b27_temple_inward.py`(B26 FCStd → 중간 FCStd. `build_b26_base_fasteners.py`처럼 다시 돌리면 같은 결과가 나와야 함), 바뀐 부품 목록과 이동량 표

**통과 조건**

- 검사기 clearance·print PASS
- `python mechanical/physics/check_head.py build/b27/cad build/b27/check-head.json` 충돌 0
- 모든 바뀐 부품이 목표 겉면에서 3.0 mm 안쪽에 있음. 단계 2의 노출 검사로 확인한다

### 단계 2 · 관자 외피

방법은 둘 중 하나입니다. 첫째, 해골 28·29를 직접 고쳐 메운다. 둘째, **따로 출력해 볼트로 붙이는 관자 덮개**를 새 부품으로 만든다. 28 앞 외장에는 조립 중 09 프레임 탭이 지나가는 긴 절삭 구간이 있으니 막으면 안 됩니다. 그래서 둘째 방법을 권합니다. 이 경우 조립 마지막에 바깥에서 붙입니다.

- **모양**: 바깥면은 목표 겉면(뼈 또는 뼈+관자 채움)을 따른다. 안쪽으로 2.4 mm 두께로 만들고, 해골의 기존 가장자리와는 0.5 mm 이하 틈으로 맞댄다.
- **체결**: 덮개 하나에 M3 볼트 2개 이상, 한쪽 노출 볼트는 4개 이하. 나사 머리는 보여도 된다. 너트는 공구나 손이 닿는 곳에 두고, 숨은 너트 홈과 인서트는 쓰지 않는다. 그런 자리가 없으면 멈추고 보고한다(7절).
- 출력 방향은 바깥 보이는 면에 서포트가 닿지 않게 정한다.
- 새 부품은 FreeCAD `Part::Feature`로 추가한다. `Motion`은 `head`, `Printed`는 True, `Label`은 `"4x 관자 덮개 오른쪽"`처럼 번호와 이름을 붙인다. 추가 방법은 `mechanical/build_b19_review_fixes.py`의 `add_part()`를 본다.

**산출물**: `mechanical/build_b27_skull_cover.py`(단계 1의 결과 → `mechanical/revisions/b27/R5-B27-Assembly.FCStd`), 덮개 선언 `mechanical/revisions/b27/cover-parts.json`

### 단계 3 · 턱 경첩

1. 39 오른쪽 핀 팔과 38 왼쪽 구동 팔의 아래 블록을 아래턱 기준 하악지 겉면에서 3.0 mm 안쪽으로 줄이거나 옮긴다. 이 부품들은 턱 30과 한 몸으로 출력한다(`30_38_39_jaw_one_piece`). 턱 구동 강도는 B25 계산(`mechanical/physics/b20_jaw_strength.py`)과 같은 조건으로 다시 확인한다.
2. 좌우 **하악지 덮개**를 새 부품으로 만든다. `Motion`은 `jaw`이고 `JawMotion` 묶음 안에 둔다. 바깥면은 아래턱 기준의 하악지·관절돌기·근육돌기를 따르고, 두께는 2.4 mm다. 턱 30에 M3 볼트 2개 이상으로 고정한다.
3. 덮개는 턱 0–6.6°, 목 상하 전 범위에서 36·37 받침, 09 프레임, 07 요크, 해골 28·29, 관자 덮개와 0.30 mm 이상 떨어져야 한다. 관절돌기는 해골의 턱관절 오목 아래에서, 근육돌기는 광대활 아래에서 이 틈을 지켜야 한다.
4. 관절돌기와 근육돌기 사이 홈(y −19…−12, z 82…91)으로 보이는 36 받침, 38 팔, 턱 모터는 홈 뒤로 숨게 줄이거나 옮긴다.

**산출물**: 단계 2와 같은 스크립트와 FCStd. `cover-parts.json`에 하악지 덮개를 추가한다.

### 단계 4 · 출력·조립 자료 통합

- **출력 프로젝트** `mechanical/revisions/b27/R5-B27-P2S.3mf`: `mechanical/build_b26_print.py`의 방식(3MF 안의 객체 메쉬 교체, `model_settings.config` 갱신)을 따르는 `mechanical/build_b27_print.py`로 만든다. 바뀐 부품은 메쉬를 교체하고, 새 부품은 객체와 판을 추가한다.
- **조립 절차**: 새 부품과 볼트는 `mechanical/physics/check_b19_assembly.py`의 `assembly_plan()`과 `web/b19/b25_preview.py`의 `plan()`에 단계로 넣는다. 관자 덮개와 하악지 덮개는 마지막 무렵, 바깥에서 붙이는 단계다. 기존 단계 순서는 바꾸지 않는다.
- **조립 점검 입력**: `check_b26_assembly.py`는 리비전 폴더의 `design.json`(`cad_sha256`이 FCStd의 SHA-256과 같아야 함), `heat-set-checks.json`, `xl330-case-screws.json`을 읽는다. B26 폴더에서 복사해 `mechanical/revisions/b27/`에 두고 `cad_sha256`을 B27 FCStd 값으로 고친다. 인서트 자리가 바뀌었으면 `heat-set-checks.json`도 맞춘다.
- **볼트·너트**: 기존 체결품 표 규칙(`mechanical/revisions/b24/hardware.json`, `hardware-spec.json`)에 맞춰 행을 추가한다. BOM은 `mechanical/revisions/b27/BOM.csv`에 B26 대비 증감으로 쓴다.

### 단계 5 · 검증

모두 B27 FCStd를 `build/b27/cad`로 내보낸 뒤 실행합니다.

```sh
python mechanical/physics/export_cad.py --world --cad mechanical/revisions/b27/R5-B27-Assembly.FCStd build/b27/cad
python mechanical/physics/check_b27_skull_cover.py build/b27/cad build/b26/cad mechanical/revisions/b27/cover-parts.json \
    mechanical/revisions/b27/cover-check.json --images mechanical/revisions/b27/cover-check
python mechanical/physics/check_head.py build/b27/cad mechanical/revisions/b27/check-head.json
python mechanical/physics/check_b26_assembly.py build/b27/cad mechanical/revisions/b24/hardware.json mechanical/revisions/b24/hardware-spec.json \
    mechanical/revisions/b27 mechanical/revisions/b27/assembly-check.json --source mechanical/revisions/b27/R5-B27-Assembly.FCStd
```

**통과 조건**

- `cover-check.json`의 `"pass": true`
- `check-head.json`의 collisions가 빈 목록
- 조립 점검 막힘 0. 설계상 접촉은 기존 11건에 새 볼트–너트 쌍만 더해진다
- 3MF를 Bambu Studio 02.09.01.70 CLI로 전 판 슬라이스해 경고 0. 소유자 PC의 실행 예는 `E:\head\build\b26-patch-review\slice-local.sh`다

### 단계 6 · 결과 정리

- `mechanical/revisions/b27/README.md`에 다음을 넣는다.
  - 바뀐 부품 표(전 → 후)
  - 체결 방법
  - 노출 전후 수치: 검사기 `exposure.sides`
  - 전후 그림: 기준 `baseline/exposure-*.png`와 `cover-check/exposure-*-yaw+0-tilt+0.png`
  - 다시 만들기 명령
  - 검증 결과 표
- 커밋은 기구(스크립트·FCStd·3MF·검사 결과)와 웹(조립 화면 자료)으로 나눈다.

## 6. 덮개 선언 (`cover-parts.json`)

검사기는 이 파일로 어떤 부품이 덮개이고 어떤 볼트로 붙는지 압니다.

```json
{
  "covers": [
    {"part": "SkullTempleCoverRight", "side": "right", "follows": "cranium",
     "removal_direction": [1, 0, 0.2],
     "fasteners": [{"part": "TempleCoverScrewR1", "host": "Part019"},
                   {"part": "TempleCoverScrewR2", "host": "Part074"}]},
    {"part": "RamusCoverRight", "side": "right", "follows": "mandible",
     "removal_direction": [1, 0, 0],
     "fasteners": [{"part": "RamusCoverScrewR1", "host": "Jaw_30_moving_jaw"},
                   {"part": "RamusCoverScrewR2", "host": "Jaw_30_moving_jaw"}]}
  ]
}
```

- 덮개는 B26에 없던 **새 부품**만 선언할 수 있습니다. 기존 기계 부품을 덮개로 선언하면 실패합니다.
- `follows`가 `mandible`인 덮개는 `Motion`이 `jaw`여야 합니다.
- `fasteners`의 볼트는 덮개와 `host`하고만 닿아도 됩니다. 볼트가 다른 부품과 닿으면 실패합니다.
- `removal_direction`은 볼트를 뺀 덮개를 빼내는 방향입니다. 그 방향으로 40 mm를 빼는 동안 어떤 부품에도 0.05 mm 넘게 파고들면 안 됩니다.

## 7. 규칙

1. `cover-spec.json`, `check_b27_skull_cover.py`, `mechanical/inputs/anatomy/`는 고치지 않는다. 검사 결과에는 조건 파일의 해시가 기록된다.
2. 조건을 만족할 수 없으면 기준을 낮추거나 우회하지 말고 멈춘다. 다음을 `mechanical/revisions/b27/BLOCKED.md`에 적고 소유자에게 넘긴다.
   - 어느 검사가 몇 대 몇으로 안 되는지
   - 시도한 방법
   - 남은 선택지와 각각의 대가
3. 눈 위치, 구동 범위, 겉모양 방향(되살린 해골 모양)을 바꾸는 판단은 소유자에게 묻는다. 좌표, 파일 형식, 스크립트 구조 같은 구현 세부는 스스로 정한다.
4. 검사 숫자를 손으로 고치거나, 검사기 대신 다른 조건으로 만든 자체 검사 결과로 통과를 주장하지 않는다.
5. 새 부품과 바뀐 출력물은 하나의 닫힌 몸체다. 0.8 mm보다 얇은 면은 2 mm² 이하, 2.0 mm보다 얇은 면은 표면의 3% 이하. 바뀐 기존 부품은 B26보다 나빠지지 않는다.

## 8. 검사기가 보는 것

| 검사 | 내용 | 통과 기준 |
| --- | --- | --- |
| exposure | 좌우 각 9방향(옆에서 좌우 ±30°, 위아래 ±20°) 정투영, 0.4 mm 간격. 첫 번째로 맞은 면이 옆 영역(\|x\| ≥ 38, y ≥ −46, 60 ≤ z ≤ 175, 머리 바닥 뒤 z < 80 · y > 5 제외)에 있고, 해골·덮개·눈·눈꺼풀·목 기둥·받침대·기존 해골 고정 나사·덮개 볼트가 아니면 기계로 센다 | 방향당 60 mm² 이하, 한쪽 9방향 합 300 mm² 이하 (B26: 1,200–2,000 / 14,100–15,200) |
| anatomy | 보이는 덮개 면, 그리고 B26보다 0.3 mm 넘게 바뀐 해골 28·29·턱 30의 보이는 면이 기준 겉면과 얼마나 떨어졌나. 두개골 쪽은 뼈 또는 뼈+관자 채움 중 가까운 쪽 | 95%가 1.5 mm 이내, 바깥으로 2.5 mm 넘게 나온 점 없음 |
| clearance | 새 부품과 바뀐 부품 × 머리·목·턱의 모든 부품. 목 −15…4.5°(14점), 눈 상하 ±8°, 눈 좌우 ±20°, 깜빡임 −1…91°, 턱 0…6.6°(12점)를 두 부품의 움직임 축에 맞춰 조합(fcl 거리) | 움직이는 쌍 0.30 mm 이상, 또는 B26의 같은 쌍보다 나빠지지 않음. 고정된 쌍은 겹침 0.01 mm³ 이하, 또는 B26의 같은 쌍보다 늘지 않음 |
| print | 새 출력물과 바뀐 출력물의 닫힘, 몸체 수, 두께 | 7절 5항 |
| removal | 각 덮개를 볼트 없이 40 mm 빼냄 | 0.05 mm 넘게 파고드는 곳 없음 |

결과 JSON의 `failures`, `closest`, `by_part`를 보면 어디를 고쳐야 하는지 나옵니다. `--images` 폴더의 노출 그림에서 빨강은 보이는 기계, 파랑은 덮개 볼트, 흐린 색은 검사 영역 밖입니다.
