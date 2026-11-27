# 해부 기준 메쉬 (B27 해골 외피 복원용)

R5 해골 28·29와 턱 30에 맞춰 놓은 사람 해골 스캔입니다. B27에서 외피를 되살릴 때 목표 모양으로 쓰고, `mechanical/physics/check_b27_skull_cover.py`가 같은 파일로 모양을 검사합니다. 좌표는 R5 조립 좌표(mm)이고, 아래턱은 턱 0°(닫힘) 자세입니다.

| 파일 | 내용 |
| --- | --- |
| `bonehub-male-cranium-right-r5.stl` · `-left-r5.stl` | 두개골. 좌우 \|x\| ≥ 22 mm, z ≤ 186 mm로 잘라 막고 줄인 것(원본과 최대 0.05 mm) |
| `bonehub-male-temple-fill-right-r5.stl` · `-left-r5.stl` | 관자 오목한 곳(측두와)을 겉면과 매끄럽게 메운 덩어리. 옆에서 본 높이 지도를 반지름 15 mm 원판으로 닫아 만든 것. 두개골과 합쳐 "관자를 채운 해골" 모양이 됨 |
| `bonehub-male-mandible-r5.stl` | 아래턱 전체. 하악지·관절돌기·근육돌기 포함 |
| `registration.json` | 원본 → R5 좌표 변환 행렬과 맞춘 방법 |

출처: BoneHub, *Visible Human Full-Skeleton 3D Bone Models* (Hugging Face `BoneHub/visible-human-3d-models`), `01_Male SKULL_CRANIAL_MAXILLA.stl`, `01_Male SKULL_MANDIBLE.stl`. 라이선스 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 위 파일은 원본을 이동·축척·자르기·단순화한 파생물입니다.

맞춘 방법
- 두개골: 해골 28·29의 손대지 않은 부분에 축별 축척을 허용해 맞춘 변환(`mechanical/revisions/b26/assembly-review.json`의 `skull_study.scan_registration`). 표면 거리 중앙값 0.32 mm.
- 아래턱: 두개골 변환을 먼저 적용한 뒤 턱 30의 몸통에 닮음 변환(축척 1.040)으로 다시 맞춤. 상위 60% 점 기준 반복 정합, 표면 거리 중앙값 1.44 mm. 스캔은 실제 사람이라 좌우가 대칭이 아닙니다(관절돌기 높이 차 약 5 mm).
