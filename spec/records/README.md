# 검수 기록

B25의 기구 기록은 `spec/records/M01.json`–`M09.json`, 실물 기록은 `P01.json`–`P08.json`에 남깁니다. 공통 필드는 `revision`(`B25`), 시험에 사용한 CAD의 `cad_sha256`과 `status`입니다. B25 CAD 파일의 SHA-256을 구한 뒤 실제 근거를 연결합니다. 보관 중인 M02·M07·M09 JSON은 B22 기록입니다. [B25 조립 CAD](../../mechanical/revisions/b25/R5-B25-Assembly.FCStd)

시험자가 결과에 따라 `PASS` 또는 `FAIL`을 적습니다. M07은 근거가 남았을 때 `UNVERIFIED`도 사용할 수 있습니다. 기록이 없거나 리비전·해시·필드가 맞지 않으면 검사 결과는 `UNVERIFIED`입니다. [판정 절차](../review.md)

## M01–M09 기구 검수

`cases` 객체에는 아래 키로 기구를 기록합니다.

| 키 | 기구 |
| --- | --- |
| `neck_yaw` | 목 좌우 |
| `neck_pitch` | 목 상하 |
| `jaw` | 턱 |
| `blink` | 눈꺼풀 |
| `eye_yaw` | 눈 좌우 |
| `eye_pitch` | 눈 상하 |
| `cable_retention` | 케이블 고정부 |

- 적용하는 기구는 `status`와 `measurements` 배열을 적습니다. 각 측정에는 `name`, 유한한 수치 `value`, `unit`, 저장소 안의 기존 근거 파일 상대경로 `source`, 부품 ID나 측정 위치 `location`이 필요합니다.
- 적용하지 않는 기구는 `status`를 `N/A`로 적고 `reason`에 해당 설계에서 적용하지 않는 이유를 씁니다.
- M02는 목 상하·턱·눈꺼풀·눈 좌우·눈 상하, M05는 눈꺼풀·턱·눈 좌우·눈 상하, M07은 눈꺼풀, M09는 일곱 기구 모두가 검사기의 필수 측정 대상입니다. 적용되는 다른 기구의 결과도 적습니다. 전체 `PASS`에는 일곱 기구의 판정과 한 건 이상의 측정이 필요합니다. 실패가 확인되면 전체 `FAIL`로 적고 아직 남은 기구는 생략할 수 있습니다.
- M02는 지지점 간 거리 ÷ 축 지름을 `support_span_to_shaft_diameter`, 단위 `ratio`로 적습니다. [보관된 B22 측정 스크립트](../measure_m02.py)
- M07은 보정 범위에서 가장 작은 힘 전달각을 `minimum_transmission_angle`, 단위 `deg`로 적습니다. 40° 미만인 눈꺼풀은 `exception`에 `required_torque_Nm`, `stall_torque_Nm`와 근거 파일 `source`를 적습니다. 검사기는 토크 비율과 해당 리비전·해시의 P03을 읽습니다. [B25 M07 근거](M07.md#b25-눈꺼풀)
- M09는 하중을 받는 부위의 가장 얇은 벽을 `minimum_wall_thickness`, 단위 `mm`로 적습니다. 검사기의 최소값 비교는 [criteria.toml](../criteria.toml)을 따릅니다. 고정 조건에 명시된 예외의 위치와 근거도 현장 판정에 남깁니다. [벽과 적층 조건](../conditions.md#9-강도)

## P01–P08 실물 시험

시험자 이름 `tester`, 실제 시험일 `date`(`YYYY-MM-DD`), 시험 방법과 조건 `measurement`, 직접 확인한 결과 `result`를 적습니다. 출력·가공·배선 조건, 펌웨어·보정값과 계측 증거를 해당 항목에 연결합니다. [B25 실물 시험](../bench.md#b25-실물-시험)

| 기록 | B25 추가 필드와 확인 범위 |
| --- | --- |
| P01·P02·P05 | 시험자가 끼움·유격, 케이블과 J2 잠금쇠 당김, 시선의 실측을 각각 적습니다. 검사기는 공통 필드와 판정만 확인합니다. [P02 내부 J2 잠금쇠](../bench.md#p02-내부-j2-잠금쇠) |
| P03 | 연속 완료 `cycles`와 `binding_events`를 정수로 적습니다. 검사기는 50회 이상과 걸림 0회를 확인합니다. 시험자는 깜빡임 **0.8~1.5초**, 시작 간격 **4~10초**도 확인한 뒤 `PASS`를 기록합니다. 깜빡임 시간·간격과 ID3 부하 전압은 실측 근거에 적습니다. |
| P04 | `neck_stop_angles_deg` 객체 안에 `yaw`와 `pitch`를 둡니다. 두 축 모두 `endpoints`(설정 끝점)와 `first_contacts`(첫 접촉각)를 같은 중립에서 `[음수 쪽 각도, 양수 쪽 각도]`로 적습니다. `PASS`에는 방향마다 첫 접촉과 설정 끝점의 각도 차에서 8틱(0.703125°)을 빼고 2° 이상이 필요합니다. |
| P06 | `jaw_command_ticks`(합격 시험은 62), 실측 `jaw_tip_drop_mm`, `jaw_visible_drop`과 `jaw_goal_pwm_verified`(`true`/`false`), 피드백 5틱을 뺀 열림 여유 `jaw_stop_reserve_deg`를 적습니다. `jaw_last_clear_ticks`는 같은 턱 닫힘 영점에서 `[닫힘 쪽 음수, 열림 쪽 양수]`로 적습니다. 검증된 PWM 제한에서 필요한 최소 무접촉 값은 `[-28, 79]`틱이고, 제한 확인 근거가 없으면 `[-28, 90]`틱입니다. 시험에 사용한 ID6 보정과 PWM 제한 확인 근거를 연결합니다. |
| P07 | 정수 `camera_yaw_cycles`, `camera_usb_disconnects`, `camera_usb_reenumerations`와 불리언 `camera_recognized_after`를 적습니다. `PASS`에는 각각 100 이상, 0, 0, `true`가 필요합니다. `camera_yaw_endpoints_deg`는 실제 도달한 `[왼쪽 음수, 오른쪽 양수]` 각도이며, `camera_yaw_calibration_ticks`는 시험 펌웨어의 ID4 `[왼쪽, 중립, 오른쪽]` 틱입니다. 시험 끝점과 보정 끝점은 각각 8틱(0.703125°) 이내로 일치해야 합니다. 지연·부하 전압과 토크 해제는 실측 근거에 적습니다. |
| P08 | `PASS`에는 전체 조립 완료 `full_assembly`가 `true`, 절차에 없던 가공 횟수 `unplanned_rework_count`가 0이어야 합니다. `retained_nut_covers`에는 `rear-cable`과 `bottom-board`를 적습니다. 앞 단계 재분해 여부, 표준 공구 접근과 턱 간극·5 N 결과는 실측 근거에 적습니다. |

저장소 루트에서 `python spec/verify.py --revision B25`로 전체 판정표를 봅니다. `python spec/verify.py --b25-physical`은 P06과 P07만 표시합니다. 수치 필드 자동 검사는 기록된 값을 읽으므로 증거 파일과 현장 결과는 시험자가 대조합니다. [인수 검사 범위](../requirements.md#b25-인수-검사) · [검사 구현](../records_check.py)
