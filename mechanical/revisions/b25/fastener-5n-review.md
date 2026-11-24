# B25 직접 나사산 5 N 예외 재판정

현행 B25의 원통머리 18곳과 무두나사 9곳을 대조했습니다. 고정 조건에서 나사 한 개의 최대 작용력이 5 N 이하임을 확인한 곳이 없어 27곳 모두 열압입 인서트를 유지합니다. 판정은 자중·지정 가속 동작과 별도 5 N 누름, 지정 마찰 및 최악 제조 공차를 적용합니다. 최초 조립 토크나 조임 예압을 별도 시험 하중으로 추가하지 않았습니다. [고정 조건](../../../spec/conditions.md) · [현행 위치와 형상 검사](heat-set-checks.json)

| 자리 | 개수 | 하중 경로와 판정 근거 |
| --- | ---: | --- |
| `YawBracketFoot0`–`3` | 4 | ID4 케이스 반력이 브래킷 발과 받침을 지납니다. 발의 면접촉·마찰과 각 나사 반력 분담은 미확인입니다. [기존 모터·베어링 하중 모델](../b24/force-path.json) |
| `ServiceHatchNutKeeperLeftScrew`, `ServiceHatchNutKeeperRightScrew` | 2 | 고정판은 최초 조립 후 일상 정비에서 그대로 둡니다. 아래 덮개의 별도 나사 네 개는 금속 너트에 물립니다. 너트 아래턱과 육각 홈 벽이 정상 체결 하중을 받지만, 너트의 위쪽 이동 한계와 고정판 중앙 나사 반력은 5 N 누름에서 입증되지 않았습니다. [공통 조립](../b23/assembly.md) · [고정판 형상](../../build_service_hatch_nuts.py) |
| `ID5KeeperScrew1`, `ID5KeeperScrew2` | 2 | ID5 플러그와 배선에서 가드에 전달되는 힘을 그 접촉면, 두 M3 나사, 별도 모터 케이스 나사 사이에서 나눕니다. 그 최대 분담은 미확인입니다. 플러그나 모터 수리 시 분리하는 자리입니다. [가드와 모터 나사 구조](../../build_b19_review_fixes.py) |
| `EyePitchStayFrame0`, `EyePitchStayFrame1`, `eyePitchHead4`, `eyePitchHead5` | 4 | ID2 링크·모터 반력은 모터판, 지지대, 프레임의 연속 두 결합을 지납니다. 기존 축 토크로 두 결합의 나사별 반력을 정할 수 없습니다. [조립 순서](../../physics/check_b19_assembly.py) · [기존 눈 구동 하중](../b23/eye-drive.json) |
| `CradleMountFrameL`, `CradleMountFrameR` | 2 | 양쪽 크래들 베어링에서 받침과 프레임으로 하중이 전달됩니다. 한쪽 외부 접촉과 최악 공차에서 각 받침–프레임 나사 반력은 미확인입니다. [베어링 받침 구조](../../build_b24_eye_bearings.py) |
| `EyeYawFoot0`, `EyeYawFoot1` | 2 | ID1 모터판과 크래들 결합이 모터 케이스 토크 및 링크 반력을 전달합니다. 5 N 외부 누름에서 두 나사의 힘을 따로 확인하지 않았습니다. [모터판 결합](../../build_b19_review_fixes.py) · [기존 눈 구동 하중](../b23/eye-drive.json) |
| `CameraTrayScrewLeft`, `CameraTrayScrewRight` | 2 | 렌즈·기판·외피 고정점에서 브래킷 발과 두 나사로 힘이 전달됩니다. 외부 케이블 10 N 시험은 먼저 받침대 장력 완화부에 걸리고, 코받침에 전달되는 잔류 장력과 렌즈 쪽 접촉 시 나사 반력은 미확인입니다. [브래킷 구조](../../build_b22_camera_mount.py) · [외부 케이블 시험](../../../spec/bench.md#p02-케이블-당김) |
| `BlinkPivotServoRetainer`, `BlinkPivotDriveRetainer`, `BlinkPivotUpperLRetainer`, `BlinkPivotUpperRRetainer`, `BlinkPivotLowerLRetainer`, `BlinkPivotLowerRRetainer` | 6 | Ø2 핀 저널이 링크 횡력을 받습니다. 핀이 끝으로 밀리면 무두나사가 축력을 받습니다. 공칭 축방향 유격 0.20 mm는 형상값이며, 최악 맞춤·마찰·접촉에서 끝 나사가 받는 힘은 미확인입니다. [핀과 저널 구조](../../build_b21_links.py) · [깜빡임 하중 범위](../../../spec/records/M07.md) |
| `EyeYawDrivePivotRetainer` | 1 | 혼과 타이바의 횡력은 저널에서 받습니다. 핀 자중은 약 0.0012 N이고, 외부 접촉과 마찰에서 아래쪽 나사에 전달될 축력의 상한은 미확인입니다. [핀과 저널 구조](../../build_b21_links.py) · [인서트 후 통로 검사](heat-set-checks.json) |
| `PitchLimitLowerRetainer`, `PitchLimitUpperRetainer` | 2 | Ø4 핀과 귀가 슬롯 끝의 횡력을 받습니다. 핀이 출구 쪽으로 이동하면 무두나사 옆면이 잡습니다. 핀 끝과 나사 옆면의 공칭 축방향 간격은 0.40 mm이고, 최악 공차와 외장 접촉에서의 핀 이동력은 미확인입니다. [핀 위치와 스토퍼 구조](../../build_b22_neck_stop.py) · [이전 스토퍼 하중 모델](neck-load-study.md) |
