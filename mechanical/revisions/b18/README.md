# B18 후면 연결부 조립

[FreeCAD 조립본](R5-B18-external-connections.FCStd) · [후면 연결부 3D HTML](R5-B18-rear-connections.html) · [고정 허브와 목 가림막 시안](study/)

HTML은 GitHub에서 **Download raw file**로 내려받아 브라우저에서 엽니다.

5 V XT30U와 목 전원 XT60U는 받침 밖에서 양쪽 몸체를 잡고 분리합니다. 카메라와 OpenRB는 내부 USB-A 중간 연결 없이 각각 PC로 연결합니다. CAD에는 전원 플러그와 USB-A의 외형을 검사용 형상으로 넣었습니다.

| 출구 | 받침 뒤끝에서 플러그 몸체까지 | 안내 홈 |
|---|---:|---:|
| 5 V XT30U | 34 mm | Ø2.80 mm × 2 |
| 목 전원 XT60U | 46 mm | Ø3.80 mm × 2 |
| 카메라 USB | 33 mm | Ø5.50 mm |
| OpenRB USB | 44 mm | Ø5.50 mm |

위 길이는 조립 형상의 바깥 꼬리선입니다. 내부 배선과 납땜 여유를 합산해 재단합니다. USB는 실드가 연결된 완제품 케이블을 사용합니다. 카메라 케이블은 기존 검증 기준점부터 머리까지 365 mm이고, B18의 직선 추가 구간은 기준점부터 바깥 플러그 몸체까지 82.88 mm입니다.

## 순서

1. 전원이 분리된 상태에서 USB-A 두 끝을 받침 안에서 뒤 벽으로 보냅니다. 트레이를 넣기 전 **17.0 × 9.8 mm** 검사 외형을 좌우·상하 ±0.30 mm로 움직여 확인했습니다. 실제 USB-A 몸체와 부츠 치수를 맞춥니다.
2. 열린 트레이 40을 받침 뒤에서 넣고 기존 M3×16 두 개를 조입니다. 전원 꼬리선은 5 V XT30U와 목 전원 XT60U를 구분하고 양끝에 이름과 극성을 붙입니다.
3. 케이블을 안내 홈에 놓고 네 곳의 고정부에 케이블 타이를 겁니다. CAD 검사 외형은 띠 폭 2.5 mm, 두께 약 1 mm, 머리 4.64 × 4.90 × 4.10 mm입니다. 머리는 피복 위의 덮개 홈 쪽으로 돌립니다.
4. 상부 덮개 42를 닫고 기존 M3 다섯 개를 체결합니다. 조립한 뒤에는 외부에서 플러그 몸체를 잡고 분리합니다. 외부 전원용 어댑터 쪽에는 해당 XT 암커넥터를 사용합니다.

## 검사

외부 탈착 **0–16 mm**와 상부 덮개 들어 올림 **0–25 mm**를 각각 0.5 mm 간격으로 확인했습니다. 위아래로 잡을 공간은 폭 18 mm, 축 방향 10 mm, 몸체 위와 아래 12 mm씩으로 검사했습니다. 바닥 덮개와 목의 기존 266개 자세에서 재단값을 갖는 20가닥과 후면 변경부의 새 접촉은 없었습니다.

타이가 지나는 하부 통로는 지붕을 약 47°로 기울였습니다. Bambu Studio 2.9.1.70에서 기존 0.4 mm 노즐, PETG HF, 0.20 mm 조건으로 40번과 42번이 놓인 11번 판을 P1S·P2S 각각 슬라이스했고, 두 결과에서 오버행 경고가 사라졌습니다.

후면 부품의 [40번 케이블 가이드 STL](40-rear-cable-guide-B18.stl)과 [42번 트레이 덮개 STL](42-rear-cable-cover-B18.stl)을 제공합니다. ID5 가드를 달 때는 너트 자리 두 곳이 추가된 [07 요크와 ID5 가드 STL](study/R5-B18-yoke-and-ID5-keeper.zip)을 함께 사용합니다.

실물에서는 피복 상태와 케이블 고정을 확인합니다. 전원을 끄고 직선 및 45° 방향으로 각각 10 N을 30초씩 가해, 움직임 0.5 mm 이하와 피복 손상 여부를 확인하는 기존 기준을 사용합니다. 목 전원 내부 입력선의 경로와 J2의 덮개 여유선은 별도로 확정합니다.

## 재현

FreeCAD가 제공하는 Python 환경에서 저장소 루트를 기준으로 실행합니다.

```sh
python mechanical/build_b18_external_connections.py --source mechanical/revisions/b17/R5-B17-service-and-eyes.FCStd --output build/R5-B18-external-connections.FCStd --assets build/b18-external-io
python mechanical/physics/check_b18_external_connections.py build/R5-B18-external-connections.FCStd build/b18-external-io/external-clearance.json
python mechanical/physics/cable_assembly.py build/R5-B18-external-connections.FCStd
```
