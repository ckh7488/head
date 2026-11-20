# 웹 뷰어

브라우저에서 B21의 조립 순서와 공구 경로를 볼 수 있습니다. 아래의 B15 뷰어에서는 배선을 살펴보고 여섯 축을 움직일 수 있습니다.

최근 개정의 [B18 후면 연결부](../mechanical/revisions/b18/)와 [B18 개선 시안](../mechanical/revisions/b18/study/)은 HTML을 내려받아 브라우저에서 직접 엽니다.

## 로컬 실행

저장소 루트에서 실행합니다. 터미널에 표시된 주소를 브라우저에 입력하면 구동 뷰어가 열립니다. 주소 끝에 `?view=wiring`을 붙이면 **배선·체결** 화면으로 시작합니다. 단계별 조립은 `/assembly/`, 조립 완료 모습은 `/assembly/#complete`에서 확인합니다.

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

## B21 조립 순서

위 서버를 띄우고 `http://127.0.0.1:8000/b19/`를 열면 B21 조립 122단계를 볼 수 있습니다. 파란색은 이번에 끼우는 부품이고 주황색은 체결품과 핀입니다. 공구 표시를 켜면 검사를 통과한 스패너·소켓 경로가 나타납니다. 마지막 단계에서 외장 숨기기를 누르면 내부 배선과 체결품이 보입니다. [B21 CAD와 검사](../mechanical/revisions/b21/)

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
