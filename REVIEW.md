# B24·A1 설계 검토

**상태는 검토 중이며 전체 출력과 부품·PCB 발주는 보류합니다.** B24는 기구와 펌웨어의 리비전입니다. A1은 서보 허브와 ESP32-C3 PCB의 리비전입니다. 카메라 USB와 OpenRB USB가 PC에 연결되고 OpenRB는 서보 허브의 DATA와 GND에 연결됩니다. ESP32-C3의 전원과 데이터는 별도입니다. [검토 대상 커밋][rev] · [전원과 배선][ee]

## 깨끗한 체크아웃에서 실행

```sh
git init r5-b24-review
cd r5-b24-review
git fetch --depth 1 https://github.com/ckh7488/head.git 2157cbfafac76ff17a58f86f65da18d7d153c68a
git switch --detach FETCH_HEAD
```

Linux에서 Python 3.12와 C++ 컴파일러로 가상 제어 테스트를 실행합니다. PCB는 KiCad 9.0.2, KiCad 표준 라이브러리와 `pcbnew`가 설치된 시스템 Python이 필요합니다. [제어 실행법][control] · [KiCad 프로젝트와 발주 산출물][ee]

```sh
python3.12 -m venv build/review-env
. build/review-env/bin/activate
python -m pip install -r tests/requirements.txt
python -m pytest -q
python mechanical/physics/verify_b23_release.py mechanical/revisions/b24 --revision B24

/usr/bin/python3 electronics/power_check.py
/usr/bin/python3 electronics/export.py servo-hub
/usr/bin/python3 electronics/export.py c3-rf
```

- **가상 제어**는 206개 통과했습니다. 두 PCB는 ERC·DRC·미연결·회로도 대조 모두 0건이었습니다. 재생성한 Gerber·드릴·스텐실 ZIP의 구성과 파일 내용은 생성 시각을 제외하면 저장본과 일치했고 C3 실장 좌표도 일치했습니다. [가상 테스트][tests] · [PCB 검사와 내보내기][export]
- **B24 저장 보고서**는 CAD·3MF·펌웨어 해시와 검사 결과의 일치를 확인합니다. 위 명령이 150단계 조립이나 26,196자세를 다시 계산하지는 않습니다. B24 모델 생성과 3D 조립 HTML은 별도 명령을 사용합니다. `spec/verify.py`의 기본 인수 검사는 B22 기록을 읽습니다. [저장 보고서][verification] · [CAD와 출력판][cad] · [3D 조립 HTML][viewer] · [인수 검사 리비전][spec]
- **실물 인수**는 P01–P08, 눈 상하축 유격 M05, 눈꺼풀 실물 50회가 남아 있습니다. P2S 3MF는 0.4 mm 노즐과 PETG HF 설정이 포함된 프로젝트이며, 사용한 슬라이서 버전은 Bambu Studio 02.09.01.70입니다. [슬라이싱 기록][slice] · [B24 실물 검수][b24-bench] · [공통 검수 절차와 B22 출력 예시][bench]

B24 CAD와 출력판을 소스에서 재생성하려면 FreeCAD 1.0을 호환되는 Python 3.12 환경에 설치합니다. 아래 FreeCAD 모듈 경로는 Debian 예시입니다. 3D HTML 생성에는 Node.js와 npm도 필요합니다. [기구 의존성][deps] · [HTML 생성 명령][viewer]

```sh
python -m pip install -r mechanical/physics/requirements.txt
export QT_QPA_PLATFORM=offscreen
export PYTHONPATH=/usr/lib/freecad-python3/lib
python -c 'import FreeCAD, Part, MeshPart'
python mechanical/build_b24.py build/b24
python mechanical/build_b24_print.py build/b24/R5-B24-P2S.3mf --print-dir build/b24/print
python mechanical/physics/verify_b23_release.py mechanical/revisions/b24 --revision B24 --print-inputs build/b24/print
```

FreeCAD 1.0과 Python 3.12 환경에서 다시 만든 3MF는 저장본과 바이트까지 일치했습니다. Python 3.13에서 재생성했을 때는 4번 판 메시의 점·면 순서가 달랐고 좌표와 삼각형은 일치했습니다. FreeCAD 파일은 저장 시각 등의 메타데이터가 달라질 수 있으므로, 기존 검사 기록의 해시는 저장본으로 대조하고 새 출력 메시의 해시는 위 명령으로 대조합니다. 150단계 조립부터 Bambu 슬라이스 검사까지 전부 다시 돌리는 통합 명령은 아직 없습니다.

## 전자·제어 검토 결과

| 발견 | 다시 확인할 곳 |
| --- | --- |
| **5 V 전원 하한**. 공급품 예시의 허용 하한은 4.75 V입니다. 같은 배선 손실 모델로 계산하면 눈·눈꺼풀의 최저 전압은 4.27 V에서 약 4.07 V로 내려갑니다. 이는 눈꺼풀 검증에 사용한 4.27–5.25 V 범위 아래입니다. | [전원 모델][power] · [어댑터 사양][adapter] |
| **정지와 전원 리셋**. 가상 테스트에서 목 상하축이 끝점보다 5틱 바깥에 있을 때 PC 명령을 끊으면 이전 목표가 남았습니다. 서보만 재부팅한 경우엔 토크가 꺼졌는데도 `STATE 31`이 나왔습니다. OpenRB 쪽만 재부팅한 가상 시험에서는 `RELEASED` 응답 뒤에도 모터 토크가 켜져 있었습니다. | [정지 처리][hold] · [상태 보고][report] · [가상 서보 인터페이스][harness] |
| **허브 2 oz 제조 한계**. JST PH 패드 11개의 최소 동박 링은 0.225 mm이고 XT30 고정홀 두 개는 0.200 mm입니다. JLCPCB의 2 oz 도금홀 기준 0.254 mm보다 작습니다. KiCad 검사에는 해당 제조 한계가 반영되어 있지 않습니다. | [허브 PCB][hub-pcb] · [JLCPCB 2 oz 도금홀 기준][jlc] |
| **허브 분기 보호**. 각 PH 출력 정격은 24 AWG에서 2 A입니다. 공용 5 A 퓨즈만으로는 한 분기가 2 A를 넘고 총전류가 5 A 미만인 경우의 차단을 보장하지 못합니다. | [허브 퓨즈와 단자][hub-bom] · [JST PH 정격][jst] |
| **허브 전원 커넥터 수량**. 외부 5 V 입력과 내부 허브 J1에 XT30U-F가 각각 하나 필요합니다. 공통 BOM은 하나만 적고 있습니다. | [공통 BOM][bom] · [허브 J1][hub-bom] · [배선표][wiring] |
| **목 상하 보정 안내**. 제어 문서의 171/51틱을 적용하면 현재 펌웨어의 155/34틱 상한을 넘겨 구동을 거부합니다. | [보정 안내][calibration] · [펌웨어 상한][limits] |
| **C3 RF 발주 ZIP의 층 번호**. Gerber X2는 내부층을 L2/L3으로 기록하지만 같은 ZIP의 `.gbrjob`은 L5/L7로 기록합니다. 4층 발주 전 두 층의 입력 순서와 적층을 일치시켜야 합니다. 안테나 S11과 USB 첫 동작은 시제품 시험 항목입니다. | [Gerber ZIP][rfzip] · [PCB 적층과 첫 동작][ee] |
| **C3 USB-C 조립**. J1의 16개 전기 단자와 고정 탭은 모두 관통홀인데 실장 좌표에 포함되어 있습니다. 스텐실에는 J1 납 개구가 없고 조립 문서는 리플로우 후 고정 탭만 납땜하라고 되어 있습니다. SMT 주문에선 빼고 전기 단자까지 포함한 관통홀 조립 절차가 필요합니다. | [J1 풋프린트][usb] · [실장 좌표][positions] · [기존 조립 안내][ee] |

OpenRB 재부팅 뒤 모터 전원이 남는 경우는 가상 장치에서 다음 명령으로 재현합니다. 결과는 `RELEASED`, 레지스터 접근 없음 `[]`, ID4 토크 `1`입니다.

```sh
python -m pytest -q tests/test_firmware.py::test_unconfirmed_enable_latches_without_switching_off --basetemp=build/r5-reset-repro
PYTHONPATH=tests python - <<'PYTHON'
from pathlib import Path
from conftest import Firmware

binary = Path("build/r5-reset-repro/openrb0")
firmware = Firmware(binary / "openrb")
try:
    firmware.set(4, 64, 1)
    firmware.set(4, 116, 2400)
    print(firmware.command("RELEASE"), firmware.trace())
    print("ID4 torque:", firmware.command("CHECK 4")[0].split()[6])
finally:
    firmware.close()
PYTHON
```

가상 시험 206개에는 위 리셋 문제를 판정하는 회귀 테스트가 없습니다. 전원 복구와 정지 처리는 실제 모터를 연결하는 첫 시험 전에 다룹니다. 카메라 샘플 영상은 PC에서 처리했으며, 실물 카메라 지연과 두 방향 USB-C 인식은 미검증입니다. [카메라 처리 코드][tracking] · [B24 실물 검수][b24-bench]

## 기구·조립 검토 결과

| 발견 | 다시 확인할 곳 |
| --- | --- |
| **모터와 체결품**. B24의 ID3은 M077이어서 M077 세 개와 M288 한 개가 필요합니다. 공통 BOM은 두 개씩입니다. XL330 케이스용 M2×6 중 11개는 2.70 mm 출력물과 제조사 3.50 mm 입구를 합한 깊이까지 닿지 않습니다. | [B24 모터 구성][cad] · [공통 BOM][bom] · [제조사 도면 Detail A][xl330] |
| **축 발주와 가공**. Ø3 ISO 8734 m6 핀과 지정 베어링은 공차상 0.002–0.015 mm 간섭입니다. 조립서는 미끄럼 끼움과 크래들 쪽 접착을 요구합니다. 목 상하축의 STEP에는 Ø3.10 mm 구멍이 있고, 가공표는 Ø2.50 mm 후 M3 관통 탭을 요구합니다. | [B24 조립][assembly] · [목 축 가공 치수][pitch] · [STEP][shaft] · [베어링 공차][nsk] · [핀 공차][pin] |
| **고정과 정비**. 뒤 외장까지 설치한 CAD에서 턱 모듈이 6 mm 아래로 내려가는 경로가 열려 있습니다. 뒤 외장도 끼운 뒤 이탈을 막는 단계가 빠져 있습니다. 아래 덮개 점검 입력에는 연결선 일곱 가닥과 주전원 커넥터의 이동 형상이 빠져 있습니다. | [턱 모듈 삽입과 뒤 외장][jaw-assembly] · [아래 덮개 점검][service] |
| **목 상하 스토퍼**. 해석은 첫 접촉이 뒤로 15.953–16.444°, 앞으로 5.436–5.962°인 조건을 사용합니다. 조립서는 구동 끝점에서 최소 거리만 요구하므로, 해석 범위를 벗어난 스토퍼도 합격할 수 있습니다. | [해석 가정][neck-stop] · [조립서의 판정][pitch] |
| **하중과 턱 여유**. 1 N 접촉과 베어링 유격을 함께 적용하면 눈꺼풀 링크와 외장이 닿는 조합이 나옵니다. 목은 불리한 1 N 방향에서 요구 0.160 N·m, 모델상 가용 0.107 N·m입니다. 턱의 복구 닫힘은 공차를 적용하면 치아 간격이 약 0.04 mm로 줄어듭니다. | [눈꺼풀 계산][blink] · [목 모델][force] · [턱 복구 보정][jaw-recovery] |

[rev]: https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a
[ee]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/README.md
[control]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/README.md#하드웨어-없이-실행
[tests]: https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/tests
[export]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/export.py
[verification]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/verification.json
[cad]: https://github.com/ckh7488/head/tree/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24
[viewer]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/web/README.md#b24-조립-순서
[spec]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/spec/requirements.md#L1-L9
[slice]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/slicing-check.json
[bench]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/spec/bench.md
[power]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/power_check.py#L62-L85
[adapter]: https://spec.globtek.info/spec/?id=01ta0000007dRGUAA2&rohs_cert=1
[hold]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/openrb/R5B1/R5B1.ino#L348-L389
[report]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/openrb/R5B1/R5B1.ino#L509-L580
[harness]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/tests/conftest.py#L53-L113
[calibration]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/README.md#L32-L45
[limits]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/openrb/R5B1/R5B1.ino#L9-L22
[rfzip]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/fabrication/C3_Antenna_A1-Gerbers.zip
[bom]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/BOM.csv
[xl330]: https://emanual.robotis.com/docs/en/dxl/x/xl330-m077/#drawings
[assembly]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/assembly.md#L15-L24
[pitch]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/pitch-coupler.md#L5-L14
[shaft]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/pitch-drive-shaft-B24.step#L891
[nsk]: https://www.nsk.com/content/dam/nsk/common/catalogs/ctrgPdf/bearings/e126h.pdf
[pin]: https://sdp-si.com/D815/D815-Metric-Section10-Hardware.pdf
[jaw-assembly]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/physics/check_b19_assembly.py#L230-L257
[service]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/physics/check_b23_service.py#L102
[blink]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/physics/blink_fea.py#L145
[force]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/physics/b23_force_path.py#L208
[jaw-recovery]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/openrb/R5B1/R5B1.ino#L556
[deps]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/physics/requirements.txt
[hub-bom]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/servo-hub/BOM.csv#L12-L14
[wiring]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/web/assets/wiring.json#L37-L51
[usb]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/c3-rf/C3_RF.pretty/USB4085_SilkAtEdge.kicad_mod#L199-L273
[positions]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/fabrication/C3-front-positions-mm.csv#L16
[hub-pcb]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/electronics/servo-hub/R5_Servo_Hub.kicad_pcb
[jlc]: https://jlcpcb.com/capabilities/pcb-capabilities/
[jst]: https://www.jst-mfg.com/product/pdf/eng/ePH.pdf
[tracking]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/control/pc/track.py#L413-L453
[neck-stop]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/neck-stop.json#L239-L244
[b24-bench]: https://github.com/ckh7488/head/blob/2157cbfafac76ff17a58f86f65da18d7d153c68a/mechanical/revisions/b24/README.md#실물-검수
