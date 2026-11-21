# 검수 기록

`M01.json`부터 `M09.json`, `P01.json`부터 `P08.json`까지 항목별로 기록합니다. 모든 파일에 `revision`, `cad_sha256`, `status`를 적습니다. 판정에는 선택한 CAD 조립본과 리비전 및 SHA-256이 일치하는 기록을 사용합니다. 시험을 끝낸 사람이 `PASS` 또는 `FAIL`을 적습니다.

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

- 적용하는 기구에는 `status`와 `measurements` 배열을 적습니다. 각 측정값은 `name`, 수치 `value`, `unit`, 근거 파일의 저장소 상대경로 `source`, 그 안의 부품 ID나 측정 위치 `location`을 담습니다.
- 적용하지 않는 기구에는 `status`를 `N/A`로 적고 그 설계에서 규칙이 적용되지 않는 이유를 `reason`에 씁니다.
- M02는 목 상하·턱·눈꺼풀·눈 좌우·눈 상하, M05는 눈꺼풀·턱·눈 좌우·눈 상하, M07은 눈꺼풀, M09는 출력 부품이 있는 일곱 기구 모두를 측정합니다.
- M02의 지지점 간 거리 ÷ 축 지름은 `support_span_to_shaft_diameter`를 측정 이름으로 사용하고 단위는 `ratio`로 적습니다. [B22 측정 스크립트](../measure_m02.py)는 거리, 지름과 비율을 함께 기록합니다.
- M07은 작동 범위에서 가장 작은 힘 전달각을 `minimum_transmission_angle`이라는 측정 이름으로 사용하고 단위는 `deg`로 적습니다. 40° 미만인 눈꺼풀은 `exception`에 요구·정지 토크(`required_torque_Nm`, `stall_torque_Nm`)와 근거 경로(`source`)를 적습니다. P03이 미확인일 때는 `UNVERIFIED`로 기록합니다. [B22 눈꺼풀 판단](M07.md)
- M09의 가장 얇은 벽은 `minimum_wall_thickness`라는 측정 이름으로 사용하고 단위는 `mm`로 적습니다. 기준 두께는 `criteria.toml`을 따릅니다.
- 측정한 기구 중 하나라도 `FAIL`이면 전체 판정은 `FAIL`입니다. 이때 아직 측정하지 않은 기구는 생략할 수 있습니다. 전체 `PASS`에는 일곱 기구의 판정과 최소 한 건의 실제 측정이 필요합니다.

## P01–P08 실물 시험

시험한 사람이 `tester`에 이름, `date`에 시험일(`YYYY-MM-DD`), `measurement`에 시험 방법과 조건, `result`에 직접 확인한 결과를 적습니다. P03은 구동·걸림 횟수를, P08은 전체 조립 완료 여부와 두 덮개의 너트 유지 결과를 함께 적습니다. [실물 시험과 필드](../bench.md)

B25의 P06은 `jaw_open_deg`, `jaw_stop_reserve_deg`를 실측합니다. P07은 `camera_yaw_cycles`, `camera_usb_disconnects`, `camera_usb_reenumerations`, `camera_recognized_after`와 좌우 끝 실제 각도를 기록합니다. [B25 실물 시험](../bench.md#b25-실물-시험)

두 기록은 저장소에서 `python spec/verify.py --b25-physical`로 검사합니다.
