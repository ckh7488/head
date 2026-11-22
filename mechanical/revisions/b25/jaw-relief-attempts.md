# B25 턱 받침 국부 수정 검사

[고정 검사 조건](../../../spec/conditions.md)의 2절은 동작 간극 0.3 mm 이상, 13절은 조립 중 겹침 0을 요구합니다. B25 제작 조립본에 세 점 고정 검토본을 합친 별도 CAD에서 고정 안내면 수정과 턱 받침 모서리 수정을 차례로 평가했습니다. [수정 좌표](b25-jaw-relief-trials.json) · [공차 결과](jaw-relief-witnesses.json)

| 수정 | 공차 검증 결과 |
| --- | --- |
| 고정 안내면 | 프레임, 요크, 앞 외장을 국부적으로 덜어냈습니다. 제자리에 장착한 상태에서 앞 외장과 왼쪽 받침이 0.009866 mm³, 오른쪽 받침이 0.004295 mm³ 겹쳤습니다. 우측 요크 수정은 Ø16.26 피치 베어링 자리의 약 47°를 깎으며 모델상 베어링 자리까지 축 방향으로 0.09 mm 침범했습니다. |
| 턱 받침 모서리 | 외측 고정점 주변을 반지름 3.2 mm로 보존한 후보에서 앞 외장과 좌우 받침이 각각 0.023044 mm³, 0.004933 mm³ 겹쳤습니다. 목의 기계 범위까지 넓힌 참고 검사에서는 +6.116°의 요크 간극이 0.110674 mm였습니다. 절삭을 더 한 후보도 제자리에 장착한 상태에서 앞 외장과 좌우 받침이 각각 0.009667 mm³, 0.004683 mm³ 겹쳤습니다. 별도로 목의 기계 한계 +7.13°에서 0.263764 mm의 요크 간극을 기록했습니다. |

겹침은 각 부품 출력 방향의 치수 허용치 중 95%를 적용해 증명했습니다. 접촉 주변의 표면 크기만 바꿔 계산한 표의 겹침 값에서 원래 부품의 전체 바깥 치수는 그대로였습니다. 이 판정에는 평판 휨을 더하지 않았습니다. [공차 입력과 겹침 체적](jaw-relief-witnesses.json)

턱 개방 명령 62틱에서 턱 끝 하강량은 5.267 mm였습니다. 피드백 끝점까지 받침·피벗 팔 간극 하한은 0.307 mm이고, 그 끝점부터 열림 스토퍼까지의 여유 하한은 1.001°였습니다. 세 점 고정 후보에는 여전히 2절·13절 조립 간섭과 완성 출력물 5 N 시험이 남습니다. [개방 연속 검사](jaw-relief-witnesses.json) · [B25 실물 시험](../../../spec/bench.md#b25-실물-시험)

고정점 세 곳에는 일반 M3 원통머리 완전나사 볼트와 열압입 인서트를 사용했습니다. 독립 단면 계산의 최대 층간 응력은 왼쪽 **3.404 MPa**, 오른쪽 **2.598 MPa**였습니다. 이 계산의 범위는 5 N 압력에 따른 공칭 축력·굽힘 응력입니다. 위치 결정용 홀에는 실물 볼트에 맞춘 동축 마감이 필요하고, 완성품 시험에서 비틀림과 인서트 빠짐을 확인합니다. [검사 근거](jaw-relief-witnesses.json) · [5 N 조건](../../../spec/conditions.md#9-강도)

후보를 다시 생성할 때는 저장소 루트에서 FreeCAD 파이썬으로 다음을 실행합니다. 마지막 인수는 [수정 좌표 파일](b25-jaw-relief-trials.json)의 후보 이름입니다.

```sh
export PYTHONPATH="mechanical:mechanical/physics:/usr/lib/freecad-python3/lib"
python mechanical/build_b25_jaw_relief_trials.py \
  mechanical/revisions/b25/R5-B25-Assembly.FCStd \
  mechanical/revisions/b25/R5-B25-Jaw-Keeper-Review.FCStd \
  build/B25-jaw-trial.FCStd mechanical/revisions/b25/b25-jaw-relief-trials.json stay_corners_trial_5
```
