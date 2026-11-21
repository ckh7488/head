# 웹 뷰어

## B25 조립 미리보기

B25 조립 단계에는 뒤 외장 너트와 좌우 M3×16 체결이 추가됐습니다. 조립 중 확인된 문제를 볼 수 있는 오프라인 미리보기입니다. [B25 기구 후보](../mechanical/revisions/b25/)

```sh
export PYTHONPATH="$PWD/mechanical${PYTHONPATH:+:$PYTHONPATH}"
b24=mechanical/revisions/b24
b25=mechanical/revisions/b25
out=build/b25-preview
assembly="$b25/R5-B25-Assembly.FCStd"
python mechanical/physics/export_cad.py --world --cad "$assembly" "$out/cad"
python mechanical/physics/check_b19_assembly.py "$out/cad" "$b24/hardware.json" "$b24/hardware-spec.json" "$out/assembly.json" --revision b25 --source "$assembly"
python web/b19/build_b19_viewer.py "$out/cad" "$b24/hardware.json" "$b24/hardware-spec.json" "$out/assembly.json" --revision B25 --assembly-cad "$assembly" --output "$out/viewer" --preview
npm ci --prefix web
python web/b19/pack_standalone.py "$out/viewer" "$out/R5-B25-assembly-preview.html" --revision B25 --preview
```

조립 검사가 출구 코드 1을 반환하면 생성된 `assembly.json`의 문제를 확인할 수 있습니다. 같은 입력에서 생성된 보고서가 있을 때 이어서 미리보기를 만듭니다. 실제 하부 덮개 배선과 공구 진입은 검토 중입니다.

## B24 조립 순서

`R5-B24-assembly.html`은 조립 완료 상태에서 시작합니다. **검사 위치**에서 눈 상하 베어링의 정렬봉과 목 상하 축의 M3 체결 공구를 확인할 수 있습니다. **배선 자세 비교**는 체결품과 배선이 장착된 검사 자세를 보여줍니다. [B24 CAD와 조립](../mechanical/revisions/b24/)

저장소에서 다시 만들려면 FreeCAD Python 모듈과 기구 검사 의존성이 있는 환경에서 아래 명령을 실행합니다. [기구 검사 의존성](../mechanical/physics/requirements.txt)

```sh
rev=mechanical/revisions/b24
out=build/b24-review
assembly="$rev/R5-B24-Assembly.FCStd"
python mechanical/physics/export_cad.py --world --cad "$assembly" "$out/cad"
python web/b19/export_wire_states.py "$assembly" "$rev/camera-check.json" "$rev/camera-paths.npz" "$out/wire-states.json" --layout "$out/cad/cad_parts.json"
python web/b19/build_b19_viewer.py "$out/cad" "$rev/hardware.json" "$rev/hardware-spec.json" "$rev/assembly.json" --revision B24 --assembly-cad "$assembly" --stop-report "$rev/neck-stop.json" --wire-states "$out/wire-states.json" --output "$out/viewer"
npm ci --prefix web
python web/b19/pack_standalone.py "$out/viewer" "$out/R5-B24-assembly.html" --revision B24
```

생성한 `build/b24-review/R5-B24-assembly.html`을 브라우저에서 엽니다. 로컬 파일 열기가 제한된 환경에선 `python -m http.server 8000 --bind 127.0.0.1 --directory build/b24-review`로 연 다음 브라우저에서 이 주소를 사용합니다. [로컬 B24 조립 화면](http://127.0.0.1:8000/R5-B24-assembly.html)

## B23 조립 순서

전달된 `R5-B23-assembly.html`을 브라우저에서 엽니다. 3D 모델과 142단계가 이 파일에 들어 있습니다. 마지막 조립 상태에서 **외장 숨기기**를 켜면 머리와 받침 안의 배선이 보입니다. 단계 목록에서 목 좌우 정지 블록, 두 덮개 체결과 앞 해골의 삽입을 볼 수 있습니다. [B23 CAD와 검사](../mechanical/revisions/b23/)

저장소에서 다시 만들려면 FreeCAD Python 모듈과 기구 검사 의존성이 있는 환경에서 아래 명령을 실행합니다. [기구 검사 의존성](../mechanical/physics/requirements.txt)

```sh
rev=mechanical/revisions/b23
out=build/b23-review
assembly="$rev/R5-B23-Assembly.FCStd"
python mechanical/physics/export_cad.py --world --cad "$assembly" "$out/cad"
python web/b19/export_wire_states.py "$assembly" "$rev/camera-check.json" "$rev/camera-paths.npz" "$out/wire-states.json" --layout "$out/cad/cad_parts.json"
python web/b19/build_b19_viewer.py "$out/cad" "$rev/hardware.json" "$rev/hardware-spec.json" "$rev/assembly.json" --revision B23 --assembly-cad "$assembly" --stop-report "$rev/neck-stop.json" --wire-states "$out/wire-states.json" --output "$out/viewer"
npm ci --prefix web
python web/b19/pack_standalone.py "$out/viewer" "$out/R5-B23-assembly.html" --revision B23
```

생성한 파일은 `build/b23-review/R5-B23-assembly.html`입니다. 브라우저에서 로컬 파일 열기를 제한한다면 같은 폴더를 로컬 서버로 띄웁니다.

```sh
python -m http.server 8000 --bind 127.0.0.1 --directory build/b23-review
```

서버를 띄운 뒤 이 주소에서 B23을 엽니다. [로컬 B23 조립 화면](http://127.0.0.1:8000/R5-B23-assembly.html)

## 이전 뷰어의 로컬 실행

저장소 루트에서 실행합니다. 터미널에 표시된 주소를 브라우저에 입력하면 이전 구동 뷰어가 열립니다. 주소 끝에 `?view=wiring`을 붙이면 **배선·체결** 화면으로 시작합니다. 단계별 조립은 `/assembly/`, 조립 완료 모습은 `/assembly/#complete`에서 확인합니다.

```sh
npm ci --prefix web
```

macOS와 Linux에서는 다음 명령으로 서버를 시작합니다.

```sh
python -m http.server 8000 --bind 127.0.0.1 --directory web
```

Windows PowerShell에서는 JavaScript의 MIME 유형을 지정하고 서버를 시작합니다.

```powershell
py -3.12 -c "import mimetypes, runpy; mimetypes.init(); mimetypes.add_type('text/javascript', '.js'); runpy.run_module('http.server', run_name='__main__')" 8000 --bind 127.0.0.1 --directory web
```

B18 참고 화면은 내려받아 브라우저에서 바로 엽니다. [후면 연결부](../mechanical/revisions/b18/) · [개선 시안](../mechanical/revisions/b18/study/)

## B22 조립 순서

B22 조립 화면은 체결품과 배선이 들어간 완성 상태에서 시작합니다. 136단계의 삽입·공구 경로, 목 제한판이 닿는 두 위치, 체결품과 배선이 장착된 검사 자세 세 가지를 확인할 수 있습니다. [B22 CAD와 검사](../mechanical/revisions/b22/)

저장소 루트에서 FreeCAD Python 모듈을 사용할 수 있는 환경에서 실행합니다.

```sh
rev=mechanical/revisions/b22
out=build/b22-review
assembly="$rev/R5-B22-Assembly.FCStd"
python mechanical/physics/export_cad.py --world --cad "$assembly" "$out/cad"
python mechanical/build_b22_guard.py "$assembly" "$out/Guard.FCStd"
python mechanical/physics/check_b22_guard.py "$out/Guard.FCStd" "$out/cad" "$out/guard-check.json"
python web/b19/export_wire_states.py "$assembly" "$rev/camera-check.json" "$rev/camera-paths.npz" "$out/camera-shape-states.json"
python web/b19/build_b19_viewer.py "$out/cad" "$rev/hardware.json" "$rev/hardware-spec.json" "$rev/assembly-check.json" --revision B22 --assembly-cad "$assembly" --stop-report "$rev/neck-stop.json" --guard-cad "$out/Guard.FCStd" --guard-report "$out/guard-check.json" --wire-states "$out/camera-shape-states.json" --output "$out/viewer"
npm ci --prefix web
python web/b19/pack_standalone.py "$out/viewer" "$out/R5-B22-assembly.html" --revision B22
```

## B21 조립 순서

이전 뷰어의 로컬 서버에서 `http://127.0.0.1:8000/b19/`를 열면 B21 조립 122단계를 볼 수 있습니다. 파란색은 이번에 끼우는 부품이고 주황색은 체결품과 핀입니다. 공구 표시를 켜면 검사를 통과한 스패너·소켓 경로가 나타납니다. 마지막 단계에서 외장 숨기기를 누르면 내부 배선과 체결품이 보입니다. [B21 CAD와 검사](../mechanical/revisions/b21/)

[B21 검사](../mechanical/revisions/b21/#다시-만들기)에서 나온 `assembly.json`을 지정합니다. 단일 HTML을 만들면 서버 없이 브라우저에서 열 수 있습니다.

```sh
out=build/b21
assembly_report=build/b21/checks/검사실행폴더/assembly.json
python web/b19/build_b19_viewer.py "$out/cad" "$out/hardware.json" "$out/hardware-spec.json" "$assembly_report" --revision B21 --assembly-cad "$out/R5-B21-Assembly.FCStd" --output "$out/viewer"
npm ci --prefix web
python web/b19/pack_standalone.py "$out/viewer" "$out/R5-B21-assembly.html"
```

## B20 조립 순서

[B20 재현](../mechanical/revisions/b20/README.md#재현)의 명령으로 B20 모델을 내보낼 수 있습니다.

아래 `/assembly/` 단계별 조립과 배선·구동 화면은 B15 조립본 기준입니다.

## CAD 변경 반영

먼저 FreeCAD 조립본과 `build/physics/cad`의 입력을 갱신합니다. 아래 예는 Debian의 FreeCAD Python 모듈 경로를 사용합니다. 브라우저 모델과 조립·배선 데이터를 갱신한 뒤 `verify_assets.mjs`로 확인합니다. [기구 검증 재현](../mechanical/README.md#재현)

```sh
python web/export_cad.py build/physics/cad build/web
npx --yes gltfpack@0.24.0 -i build/web/assembly.glb -o web/assets/assembly.glb -cc -kn -km -noq
cp build/web/assembly.json web/assets/assembly.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python web/assembly/export_review.py --cad build/mechanical/R5-B15-Assembly.FCStd
node web/verify_assets.mjs
```

## 모델과 자료 출처

외장 메시를 BoneHub의 Visible Human Full-Skeleton 3D Bone Models에서 개작했습니다. [원본](https://doi.org/10.57967/hf/10464) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

목의 XL430 두 개와 눈·눈꺼풀·턱의 XL330 네 개는 ROBOTIS STEP을 사용합니다. 웹 모델에서도 케이스 윤곽과 장착 구멍을 유지합니다. [XL330 도면](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drawings) · [XL430 도면](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#xl430-w250-new)

구매품 형상은 `web/export_connectors.py`로 내보냅니다. 두 번째 인수에 XT60U 암수와 JST 세 종류의 STEP 파일이 든 폴더를 지정합니다. `--review-cad`로 구매품 형상을 교체한 FreeCAD 참고본을 만들 수 있습니다. [XT60U-F](https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/7e3f76bd9e1344f68e653ea7d528bc08) · [XT60U-M](https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/8e19b37684634468b185c41bc1fdfa75) · [JST STEP](https://github.com/KiCad/kicad-packages3D/tree/master/Connector_JST.3dshapes) · [KiCad 라이선스](https://www.kicad.org/libraries/license/)

추적 영상은 scikit-image의 NASA 우주비행사 샘플을 사용합니다. 한국어 서체는 Noto Sans CJK입니다. [영상 샘플](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) · [서체 라이선스](assets/noto-sans-cjk-license.txt)
