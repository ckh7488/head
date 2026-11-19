# R5 B3

코 안의 USB 카메라로 얼굴을 보고 눈·목을 움직이는 해골 헤드입니다. OpenRB-150이 눈 좌우·상하, 눈꺼풀, 목 좌우·상하, 턱의 6축을 구동합니다. ESP32-C3 기판은 2.4 GHz 안테나 실험용입니다.

**B3는 제작 검토판입니다.** 짧은 눈꺼풀 링크, 눈 모터 위치, 턱 뒤쪽 간극을 수정했습니다. 전체 출력에 앞서 눈꺼풀 맞춤과 케이블 당김을 시험합니다. [눈꺼풀 맞춤 3MF](mechanical/R5-B3-Blink-Fit-P1S.3mf) · [케이블 시험 3MF](mechanical/R5-B2-Cable-Pull-Test-P1S.3mf)

| 작업 | 시작 파일 |
|---|---|
| 기구 확인 및 수정 | [B3 FreeCAD 조립본](mechanical/R5-B3-Assembly.FCStd) |
| 부품·조립·물리 검증 | [기구 BOM](mechanical/BOM.csv) · [검증 재현](mechanical/README.md) |
| 회로·PCB·Gerber 내보내기 | [KiCad 프로젝트](electronics/README.md) |
| 카메라 추적·펌웨어·보정 | [제어 실행법](control/README.md) |
| 브라우저에서 6축 조작 | [B3 웹 뷰어](web/) |

## 웹 뷰어

저장소 루트에서 실행하고 브라우저에서 포트 8000을 엽니다. 뷰어에서 B3 조립 형상과 축별 움직임을 볼 수 있습니다. [로컬 주소](http://localhost:8000)

```sh
npm ci --prefix web
python -m http.server 8000 --directory web
```

CAD를 수정하면 기구 문서의 `--world` 내보내기와 해석 환경을 사용해 웹 모델을 갱신합니다.

```sh
python web/export_cad.py build/physics/cad build/web
npx --yes gltfpack@0.24.0 -i build/web/assembly.glb -o web/assets/assembly.glb -cc -kn -km -noq
cp build/web/assembly.json web/assets/assembly.json
```

외장 메시를 BoneHub의 Visible Human Full-Skeleton 3D Bone Models에서 개작했습니다. [원본](https://doi.org/10.57967/hf/10464) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

모터 참조 형상은 ROBOTIS 도면을 사용합니다. 영상 예제는 scikit-image의 NASA 우주비행사 샘플이고, 한국어 서체는 Noto Sans CJK입니다. [XL330](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#drawings) · [XL430](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#drawings) · [샘플](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) · [서체 라이선스](web/assets/noto-sans-cjk-license.txt)
