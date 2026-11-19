# R5 B13

코 안의 USB 카메라로 얼굴을 보고 눈·목을 움직이는 해골 헤드입니다. OpenRB-150이 눈 좌우·상하, 눈꺼풀, 목 좌우·상하, 턱의 6축을 구동합니다. ESP32-C3 기판은 2.4 GHz 안테나 실험용입니다.

구조물은 **M3×8·M3×16 육각렌치 원통머리 ISO 4762 (DIN 912)**와 일반 M3 육각너트를 씁니다. 작은 링크와 기판, 제조사 체결 구멍은 부품표에 적었습니다. [기구 부품표](mechanical/BOM.csv)

시험판 2번은 케이블 덮개 공구 통로, 3번은 바닥 덮개와 허브, 4번은 보드 캐리어용입니다. 모터 케이스 나사산과 OpenRB 구멍 간격은 가조립에서 확인합니다. [조립절차서](mechanical/ASSEMBLY.md) · [P1S 시험판](mechanical/R5-B13-Fit-P1S.3mf)

| 작업 | 시작 파일 |
|---|---|
| 기구 확인 및 수정 | [B13 FreeCAD 조립본](mechanical/R5-B13-Assembly.FCStd) |
| P1S 전체 출력 | [B13 출력판 12장과 선택 1장](mechanical/R5-B13-P1S.3mf) |
| 부품·물리 검증 | [기구 BOM](mechanical/BOM.csv) · [검증 재현](mechanical/README.md) |
| 두 PCB 발주·납땜 | [발주 파일·제작 옵션·배선](electronics/README.md) |
| 카메라 추적·펌웨어·보정 | [제어 실행법](control/README.md) |
| 브라우저에서 조립 순서와 6축 조작 | [단계별 조립](https://r5-b1-review.ckh.chatgpt.site/b13/assembly/) · [B13 웹 뷰어](web/) |

## 웹 뷰어

저장소 루트에서 실행하면 브라우저에서 조립 형상과 6축 움직임을 볼 수 있습니다. [구동 검토](http://localhost:8000) · [단계별 조립](http://localhost:8000/assembly/)

```sh
npm ci --prefix web
python -m http.server 8000 --directory web
```

CAD를 수정하면 기구 문서의 `--world` 내보내기와 해석 환경을 사용해 웹 모델을 갱신합니다.

```sh
python web/export_cad.py build/physics/cad build/web
npx --yes gltfpack@0.24.0 -i build/web/assembly.glb -o web/assets/assembly.glb -cc -kn -km -noq
cp build/web/assembly.json web/assets/assembly.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=/usr/lib/freecad-python3/lib build/freecad-venv/bin/python web/assembly/export_review.py --cad build/mechanical/R5-B13-Assembly.FCStd
```

외장 메시를 BoneHub의 Visible Human Full-Skeleton 3D Bone Models에서 개작했습니다. [원본](https://doi.org/10.57967/hf/10464) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

모터 참조 형상은 ROBOTIS 도면을 사용합니다. 영상 예제는 scikit-image의 NASA 우주비행사 샘플이고, 한국어 서체는 Noto Sans CJK입니다. [XL330](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drawings) · [XL430](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#drawings) · [샘플](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) · [서체 라이선스](web/assets/noto-sans-cjk-license.txt)
