const ids = value => value.split(" ");
const move = (names, ...offset) => ({ ids: ids(names), offset });
const gear = (prefix, type, size, length, axis, seats) =>
  seats.map((seat, i) => ({ id: prefix + i, type, size, length, axis, seat }));
const names = items => items.map(item => item.id).join(" ");
const across = (xs, ys, point) => xs.flatMap(x => ys.map(y => point(x, y)));

const hatchSeats = [[-41.85, 55], [41.85, 55], [-26.9, 82.25], [26.9, 82.25]];
const hubSeats = across([-30.8, 30.8], [46.2, 72.8], (x, y) => [x, y, -72.5]);
const hatchNuts = gear("hatchNut", "nut", 3, 0, [0, 0, 1], hatchSeats.map(([x, y]) => [x, y, -76.61]));
const hatchBolts = gear("hatchBolt", "flat", 3, 10, [0, 0, 1], hatchSeats.map(([x, y]) => [x, y, -82.97]));
const hubBolts = gear("hubBolt", "bolt", 3, 10, [0, 0, -1], hubSeats);
const hubNuts = gear("hubNut", "nut", 3, 0, [0, 0, 1], hubSeats.map(([x, y]) => [x, y, -80.72]));
const cableX = [-47, -28.3, -3, 22, 47];
const cableNuts = gear("cableNut", "nut", 3, 0, [0, 0, 1], cableX.map(x => [x, 121.6, -64.43]));
const cableBolts = gear("cableBolt", "bolt", 3, 16, [0, 0, -1], cableX.map(x => [x, 121.6, -49.1]));
const clipBolts = gear("clipBolt", "bolt", 3, 16, [0, -1, 0], [-28.5, 28.5].map(x => [x, 93.6, -71]));
const rotorBolts = gear("rotorBolt", "bolt", 3, 10, [0, 0, 1], across([-12, 12], [11, 31], (x, y) => [x, y, -37.9]));
const mastBolt = gear("mastBolt", "bolt", 2, 6, [0, 0, -1], [[0, 8, -32.9]]);
const mastTool = gear("mastTool", "tool", 2, 36, [0, 0, 1], [[0, 8, -30.9]]);
const yokeSeats = [[-12, 17], [-12, 27.3], [12, 24.3]];
const yokeNuts = gear("yokeNut", "nut", 3, 0, [0, 0, 1], yokeSeats.map(([x, y]) => [x, y, 59.64]));
const yokeBolts = gear("yokeBolt", "bolt", 3, 16, [0, 0, -1], yokeSeats.map(([x, y]) => [x, y, 75]));
const railSeats = across([-20, 20], [143, 150], (x, z) => [x, 27.7, z]);
const railBolts = gear("railBolt", "bolt", 3, 20, [0, -1, 0], railSeats);
const railNuts = gear("railNut", "nut", 3, 0, [0, 1, 0], railSeats.map(([x, , z]) => [x, 8.74, z]));
const crankBolts = gear("crankBolt", "bolt", 2, 8, [0, 0, -1], [-53.9, 10.2, 54.15].map(x => [x, -24, 163.55]));
const crankNuts = gear("crankNut", "nut", 2, 0, [0, 0, 1], [-53.9, 10.2, 54.15].map(x => [x, -24, 156.6]));
const clampX = [-1, 1, 1];
const arm = (y, z, r) => [y + r * Math.cos(-56 * Math.PI / 180), z + r * Math.sin(-56 * Math.PI / 180)];
const [servoY, servoZ] = arm(-14, 170, 8.25);
const [crankY, crankZ] = arm(-24, 154, 8.25);
const [sideY, sideZ] = arm(-24, 154, 11.5);
const [lidY, lidZ] = arm(-39, 119, 11.5);
const linkBolts = [
  ...gear("middleServo", "bolt", 2, 6, [-1, 0, 0], [[7.45, servoY, servoZ]]),
  ...gear("centerLink", "bolt", 2, 8, [1, 0, 0], [[4.55, crankY, crankZ], [-53.75, sideY, sideZ], [-53.5, lidY, lidZ]]),
  ...gear("rightLink", "bolt", 2, 8, [-1, 0, 0], [[53.75, sideY, sideZ], [53.5, lidY, lidZ]]),
];
const linkNuts = [
  ...gear("middleNut", "nut", 2, 0, [1, 0, 0], [[1.25, servoY, servoZ]]),
  ...gear("linkNutPos", "nut", 2, 0, [1, 0, 0], [[10.55, crankY, crankZ], [-47.65, sideY, sideZ], [-47.65, lidY, lidZ]]),
  ...gear("linkNutNeg", "nut", 2, 0, [-1, 0, 0], [[47.65, sideY, sideZ], [47.65, lidY, lidZ]]),
];

export const hardware = [
  ...hatchNuts, ...hatchBolts, ...hubBolts, ...hubNuts, ...cableNuts, ...cableBolts, ...clipBolts,
  ...rotorBolts, ...mastBolt, ...mastTool, ...yokeNuts, ...yokeBolts, ...railNuts, ...railBolts,
  ...crankNuts, ...crankBolts, ...linkBolts, ...linkNuts,
];

const PCB = "HubPCB HubBodyJ1 HubBodyJ2 HubBodyJ3 HubBodyJ4 HubBodyJ5 HubBodyJ6 HubBodyJ7 HubBodyJ8 HubBodyF1 HubBodyF2 HubBodyC1 HubBodyC2 HubBodyR1 HubBodyR2 HubBodyR3 HubBodyD1 HubBodyD2";
const frame = "Part019 Part020 Part021";
const lids = "Part076 Part077 Part078 Part079 Part058 Part059 Part061 Part062";
const rail = "Part063 Part048 Part050 Part052 BlinkCollarLeft BlinkCollarRight Part053 Part054 Part055";
const eyes = "Part024 Part025 Part026 Part027 Part028 Part029 Part030 Part031 Part032 Part033 Part034 Part035 Part036";
const yoke = "Part010 Part011 Part012 Part014 Part018 Part016";
const jaw = "Jaw_30_moving_jaw Jaw_36_left_jaw_servo_stay Jaw_37_right_jaw_bearing_stay Jaw_38_left_jaw_drive_arm Jaw_39_right_jaw_pivot_arm Jaw_XL330_M288_Jaw Jaw_MR104ZZ_jaw_right Jaw_Pin_jaw_4x10";
const camera = "Part065 Part066 Part067 Part068 Part080";

export const steps = [
  {
    id: "hatch-nuts", group: "받침", title: "바닥 덮개 너트", base: "Part000",
    moves: [move(names(hatchNuts), 0, 0, 22)], focus: [0, 68, -66], view: [1, -1.4, 1.6], span: 104,
    task: "받침 안쪽에서 M3 너트 4개를 먼저 넣습니다.", check: "너트가 홈 바닥까지 앉아야 밑면에서 나사가 잡힙니다.",
    stock: "M3 일반 육각너트 ×4", note: "B7 전체 출력판 11번에 35번 허브 덮개가 있습니다.",
  },
  {
    id: "hub-board", group: "받침", title: "허브 PCB를 덮개에", base: `HubHolder ${names(hubNuts)}`,
    moves: [move(`${PCB} ${names(hubBolts)}`, 0, 0, 30)], focus: [0, 62, -69], view: [1, -1.15, 1], span: 93,
    task: "덮개 위로 허브를 올리고 위에서 M3×10 나사 4개를 넣습니다.", check: "일반 너트는 덮개 아래 홈에 넣습니다. 커넥터가 받침 안을 향합니다.",
    stock: "M3×10 일반 육각렌치 나사 ×4",
  },
  {
    id: "hatch-fit", group: "받침", title: "아래에서 덮개 닫기", base: `Part000 CableSaddle ${names(hatchNuts)}`,
    moves: [move(`HubHolder ${PCB} ${names(hatchBolts)}`, 0, 0, -30)], focus: [0, 58, -92], view: [1, 1.2, -1.15], span: 135,
    task: "허브와 덮개를 통째로 아래에서 들어 올립니다.", check: "배선을 당기지 않고 덮개를 30 mm 내릴 수 있게 여유를 둡니다. 바닥의 나사 머리는 평평하게 들어갑니다.",
    stock: "M3×10 육각렌치 접시머리 ×4", checked: true,
  },
  {
    id: "cable-nuts", group: "받침", title: "케이블 너트 먼저", base: "CableSaddle",
    moves: [move(names(cableNuts), 0, 0, -18)], focus: [0, 112, -65], view: [1, 1.65, -.8], span: 88,
    task: "케이블 트레이 아래에서 M3 너트 5개를 넣습니다.", check: "40번 트레이를 받침에 붙이기 전에 작업합니다.",
    stock: "M3 일반 육각너트 ×5",
  },
  {
    id: "cable-tray", group: "받침", title: "트레이를 뒤에서 체결", base: "Part000",
    moves: [move(`CableSaddle ${names(clipBolts)}`, 0, 26, 0)], focus: [0, 92, -64], view: [1, 1.4, .83], span: 130,
    task: "받침 뒤에서 트레이를 대고 M3 나사 2개로 고정합니다.", check: "안쪽 평와셔와 육각너트를 놓을 자리가 있어야 합니다.",
    stock: "M3×16 일반 육각렌치 나사 ×2",
  },
  {
    id: "cable-cover", group: "받침", title: "커넥터를 덮개로 잡기", base: `Part000 CableSaddle ${names(cableNuts)}`,
    moves: [move(`CableGate ${names(cableBolts)}`, 0, 0, 25)], focus: [0, 113, -53], view: [1, 1.6, 1.05], span: 97,
    task: "플러그 뒤턱을 홈에 밀착시킨 다음 42번 덮개를 위에서 내립니다.", check: "선만 누르지 않고 플러그 뒤턱이 걸려야 합니다. 실물에서는 10 N으로 당겨 봅니다.",
    stock: "M3×16 일반 육각렌치 나사 ×5",
  },
  {
    id: "base-boards", group: "받침", title: "보드 캐리어 넣기", base: "Part000",
    moves: [move("Part069 Part070 Part071 Part072", 0, 0, 36)], focus: [0, -8, -64], view: [1, -1.1, 1.4], span: 170,
    task: "C3와 OpenRB 캐리어를 각각 안착시킵니다.", check: "C3의 USB-C는 정면을 향합니다. 보드 체결 너트를 캐리어 하단에 먼저 넣습니다.",
    stock: "캐리어 M3×8 ×8 · C3 M2×8 ×2",
  },
  {
    id: "yaw-motor", group: "목", title: "받침 안 목 모터", base: "Part000 Part008 Part009",
    moves: [move("Part017", 0, 0, 34)], focus: [0, 12, -57], view: [1.15, -1.55, 1.5], span: 108,
    task: "ID 4 XL430을 05번 좌우 브래킷 사이에 둡니다.", check: "뒷 단계에서 가려지기 전에 본체 나사와 케이블을 연결합니다.",
    stock: "ROBOTIS 본체 지정 체결품",
  },
  {
    id: "yaw-bearing", group: "목", title: "6816 베어링 안착", base: "Part001 Part017",
    moves: [move("Part006", 0, 0, 28)], focus: [0, 2, -37], view: [1, -1.3, 1.4], span: 121,
    task: "받침 02에 6816을 위에서 넣습니다.", check: "외륜이 균일하게 앉는지 확인한 뒤 41번 눌림판 세 개를 M3×8로 고정합니다.",
    stock: "눌림판 M3×8 ×3", checked: true,
  },
  {
    id: "rotor", group: "목", title: "회전판과 모터가 걸림", base: "Part017 Part006",
    moves: [move(`Part007 ${names(rotorBolts)}`, 0, 0, 26)], focus: [-4, 13, -37], view: [1, -1.35, .48], span: 75,
    task: "기둥 나사 머리가 달린 상태에서 회전판을 모터 위로 내리는 경로입니다.", check: "아래에서 들어오는 일반 M3 머리 3개가 XL430 케이스와 겹칩니다. 볼트 길이를 줄여도 머리 높이는 같습니다.",
    stock: "일반 M3 머리 기준 · 길이 결정 보류", cut: ["x", -11.98], blocker: true,
  },
  {
    id: "mast", group: "목", title: "기둥이 M2 나사 가림", base: `Part007 Part017 ${names(mastBolt)} ${names(mastTool)}`,
    moves: [move("Part010", 0, 0, 28)], focus: [0, 10, -20], view: [1.5, -1.15, .38], span: 82,
    task: "모터 혼에 M2 나사를 먼저 두고 기둥을 내려 봅니다.", check: "기둥 앞벽이 M2 머리와 수직 렌치 경로를 가립니다. 노란 막대는 렌치가 들어오는 공간입니다.",
    stock: "모터 혼 M2×6 · 1.5 mm 렌치", cut: ["x", .05], blocker: true,
  },
  {
    id: "yoke-nuts", group: "목", title: "요크 너트를 옆으로", base: "Part010",
    moves: [
      move("yokeNut0 yokeNut1", -18, 0, 0),
      move("yokeNut2", 18, 0, 0),
    ], focus: [0, 23, 64], view: [1.2, -1.5, 1], span: 58,
    task: "목 기둥 옆 홈에 일반 너트 3개를 밀어 넣습니다.", check: "위에서 나사를 넣기 전에 너트 중심을 맞춥니다.",
    stock: "M3 일반 육각너트 ×3", checked: true,
  },
  {
    id: "yoke-fit", group: "목", title: "상하 요크 얹기", base: `Part010 ${names(yokeNuts)}`,
    moves: [move(`Part011 ${names(yokeBolts)}`, 0, 0, 28)], focus: [0, 9, 86], view: [1.1, -1.25, .87], span: 124,
    task: "07번 요크를 위에서 얹고 M3×16 세 개로 조입니다.", check: "M3×20을 넣으면 나사 끝이 기둥 내부 플라스틱에 들어갑니다. 별도 작업대에서 맞춰 봅니다.",
    stock: "M3×16 일반 육각렌치 나사 ×3",
  },
  {
    id: "pitch-bearing", group: "목", title: "688을 바깥쪽에서", base: "Part011 Part018 Part016",
    moves: [move("Part012", -19, 0, 0), move("Part014", 19, 0, 0)],
    focus: [0, 2, 112], view: [1.05, -1.5, .75], span: 129,
    task: "688 베어링을 요크 양끝의 바깥쪽에서 안으로 넣습니다.",
    check: "좌우 베어링이 같은 높이에서 수평으로 앉는지 확인합니다.",
    stock: "688 ×2", checked: true,
  },
  {
    id: "head-frame", group: "목", title: "머리 프레임을 위에서", base: yoke,
    moves: [move("Part019", 0, 0, 31)], focus: [0, 11, 132], view: [1.15, -1.4, .8], span: 140,
    task: "두 688 베어링 사이에 09번 머리 프레임을 위에서 내립니다.",
    check: "외장을 붙이기 전에 이 상태에서 좌우 축 구멍을 맞춥니다.", checked: true,
  },
  {
    id: "neck-pins", group: "목", title: "목 축을 양쪽에서", base: `${yoke} Part019`,
    moves: [move("Part013", -24, 0, 0), move("Part015", 24, 0, 0)],
    focus: [2, 2, 111], view: [1.05, -1.5, .75], span: 132,
    task: "머리 프레임을 받친 채 Ø8 축을 양쪽에서 끼웁니다.",
    check: "오른쪽 긴 축의 평평한 끝이 08번 구동 혼을 향합니다. 모터 혼을 풀고 핀이 들어가는지 확인합니다.",
    stock: "Ø8 강철축 ×2", checked: true,
  },
  {
    id: "eye-pins", group: "눈·눈꺼풀", title: "안구의 위아래 핀", base: "Part024 Part029 Part030 Part031 Part033 Part034 Part035",
    moves: [move("Part032 Part036", 0, 0, 23)], focus: [0, -38, 123], view: [1, -1.35, 1.15], span: 91,
    task: "안구 두 개를 12번 크래들에 놓고 Ø2 핀을 위에서 넣습니다.", check: "핀을 끼운 뒤 안구를 각각 손으로 돌려 봅니다.",
    stock: "Ø2 × 24 mm 핀 ×2", checked: true,
  },
  {
    id: "eye-pin", group: "눈·눈꺼풀", title: "오른쪽 눈축 반쪽 막힘", base: "Part024 Part027",
    moves: [move("Part028", 20, 0, 0)],
    focus: [65, -38, 120], view: [1.4, -1.5, .66], span: 28,
    task: "오른쪽 Ø3 핀을 바깥에서 밀어 넣는 단계입니다.", check: "12번의 보강재가 구멍 반쪽을 막습니다. Ø3.2 가공 미리보기로 같은 축의 이동을 비교할 수 있습니다.",
    stock: "Ø3 × 17 mm 핀 ×1", cut: ["y", -39.02], blocker: true,
  },
  {
    id: "lids", group: "눈·눈꺼풀", title: "눈꺼풀 힌지 핀 네 개", base: "Part076 Part077 Part078 Part079",
    moves: [move("Part058 Part059", -13, 0, 0), move("Part061 Part062", 13, 0, 0)],
    focus: [0, -42, 123], view: [1, -1.9, .9], span: 110,
    task: "눈틀 두 개에 각각 눈꺼풀 하나를 대고 안쪽과 바깥쪽 핀을 넣습니다.",
    check: "핀은 눈틀에 잡히고 눈꺼풀만 가볍게 돌아야 합니다. 링크는 나중에 겁니다.",
    stock: "Ø2 × 9.5 mm 핀 ×4", checked: true,
  },
  {
    id: "blink-bearings", group: "눈·눈꺼풀", title: "레일의 작은 베어링", base: "Part063",
    moves: [move("Part050", 18, 0, 0), move("Part052", -18, 0, 0)],
    focus: [0, -22, 156], view: [1.25, -1.65, .75], span: 82,
    task: "MR104ZZ 두 개를 레일 중앙에서 양 바깥쪽으로 눌러 넣습니다.",
    check: "간격통의 얇은 턱은 베어링 안쪽 링에 닿습니다.",
    stock: "MR104ZZ ×2", checked: true,
  },
  {
    id: "blink-shaft", group: "눈·눈꺼풀", title: "공용축을 옆에서 통과", base: "Part063 Part050 Part052 Part054 BlinkCollarLeft BlinkCollarRight",
    moves: [move("Part048", -87, 0, 0)], focus: [-28, -21, 154], view: [1.05, -1.55, .42], span: 168,
    task: "두 간격통과 가운데 크랭크를 대고 Ø4 축을 왼쪽에서 넣습니다.",
    check: "37.4 mm 간격통은 왼쪽, 짧은 간격통은 오른쪽입니다. 끼울 때 축이 휘도록 누르지 않습니다.",
    stock: "Ø4 × 112 mm 연마축", checked: true,
  },
  {
    id: "blink-clamps", group: "눈·눈꺼풀", title: "크랭크의 너트와 고정 나사", base: rail,
    moves: crankNuts.map((item, i) => move(item.id, clampX[i] * 5, 0, 0)),
    focus: [2, -22, 156], view: [1, -1.35, 1.3], span: 102,
    task: "양끝 크랭크를 끼우고 세 크랭크의 옆 홈에 M2 너트를 밀어 넣습니다.",
    check: "너트 다음에 나사를 넣어 축의 평평한 면을 누릅니다. 볼트 규격에서 변경한 머리 높이와 길이를 볼 수 있습니다.",
    stock: "M2 일반 육각너트 ×3", checked: true,
  },
  {
    id: "blink-clamp-bolts", group: "눈·눈꺼풀", title: "축의 평면 세 곳 고정", base: `${rail} ${names(crankNuts)}`,
    moves: [move(names(crankBolts), 0, 0, 13)], focus: [0, -24, 160], view: [1, -1.3, .88], span: 108,
    task: "축 위쪽의 깊이 0.45 mm 평면에 나사 세 개를 맞춥니다.",
    check: "M2×8 그대로 쓰면 기존 M2×4보다 머리가 4 mm 위로 올라옵니다. 실제 조립 후 전체 깜빡임에서 긁힘이 없는지 봅니다.",
    stock: "M2×8 일반 육각렌치 나사 ×3",
  },
  {
    id: "blink-rail", group: "눈·눈꺼풀", title: "레일을 프레임에", base: `${frame} ${names(railNuts)}`,
    moves: [move(rail, 0, -27, 0), move(names(railBolts), 0, 19, 0)],
    focus: [0, 8, 157], view: [1, 1.6, 1.1], span: 136,
    task: "레일 너트 네 개를 앞쪽 홈에 놓고 프레임 뒤에서 M3×20을 넣습니다.",
    check: "M3×16은 이 자리에서 너트까지 닿지 않습니다. 모터판 두 자리도 M3×20으로 통일합니다.",
    stock: "M3×20 ×4 · 모터판 M3×20 ×2",
  },
  {
    id: "blink-links", group: "눈·눈꺼풀", title: "양쪽 링크와 모터 혼", base: `${rail} ${lids} Part045 Part046 Part047 Part056 Part057 Part060 ${names(linkNuts)}`,
    moves: linkBolts.map(item => move(item.id, -item.axis[0] * 12, 0, 0)),
    focus: [0, -23, 155], view: [1.4, -1.75, 1], span: 129,
    task: "모터 혼 뒤 너트를 먼저 넣고 가운데 링크 및 양쪽 링크를 체결합니다.",
    check: "혼 쪽 한 개는 M2×6입니다. M2×8을 넣으면 모터 케이스에 닿습니다. 관절에 축방향 유격 0.10~0.20 mm를 둡니다.",
    stock: "M2×6 ×1 · M2×8 ×5 · M2 평와셔 ×6",
  },
  {
    id: "jaw-fit", group: "턱·외장", title: "턱 오른쪽 축 맞추기", base: jaw.replace(" Jaw_Pin_jaw_4x10", ""),
    moves: [move("Jaw_Pin_jaw_4x10", 14, 0, 0)], focus: [26, -26, 82], view: [1.6, -1.1, .5], span: 100,
    task: "해골 밖에서 왼쪽 모터 혼과 오른쪽 Ø4 핀의 축을 맞춥니다.",
    check: "턱을 손으로 열고 닫아 한쪽만 들리는지 확인합니다. 접착 위치는 가조립이 끝난 뒤 잡습니다.",
    stock: "MR104ZZ ×1 · Ø4 × 10 mm 핀 ×1",
  },
  {
    id: "camera-fit", group: "턱·외장", title: "코 카메라 놓기", base: "Part073 Part065 Part080",
    moves: [move("Part066 Part067 Part068", 0, 26, 0)], focus: [0, -53, 88], view: [1.1, 1.45, .55], span: 73,
    task: "브래킷에 카메라를 끼운 상태로 코 쪽에 맞춥니다.",
    check: "영상 가장자리에 코 테두리가 보이는지 접착 전에 확인합니다.",
    stock: "일반 M2 나사와 넓은 평와셔",
  },
  {
    id: "front-orbit", group: "턱·외장", title: "눈틀의 삽입 경로 막힘", base: "Part073",
    moves: [move("Part077", 0, -28, 0)], focus: [32, -52, 120], view: [1, -1.8, .7], span: 62,
    task: "오른쪽 눈틀을 해골 앞에서 곧게 넣어 봅니다.",
    check: "눈틀의 옆발이 해골 눈구멍 벽에 걸립니다. 눈틀을 고정하기 전에 통과 경로를 확보해야 합니다.",
    cut: ["x", 50.6], blocker: true,
  },
  {
    id: "front-shell", group: "턱·외장", title: "앞 해골이 지지대에 걸림", base: `${frame} ${yoke} ${eyes} Part063`,
    moves: [move("Part073", 0, -54, 0)], focus: [0, -14, 125], view: [1.25, 1.75, .37], span: 155,
    task: "눈 지지대와 목 요크를 단 뒤 앞 해골을 정면에서 넣는 경로입니다.",
    check: "13번 눈 지지대와 07번 요크에 걸립니다. 반대로 해골부터 끼우면 Ø8 목 축의 옆쪽 통로가 막힙니다.",
    cut: ["x", 66.9], blocker: true,
  },
  {
    id: "rear-shell", group: "턱·외장", title: "뒤 해골과 오른쪽 탭", base: `${frame} Part073`,
    moves: [move("Part074", 0, 40, 0)], focus: [67, 22, 156], view: [1.1, 1.4, .59], span: 53,
    task: "뒤 해골을 이음면에 평행하게 밀어 넣습니다.",
    check: "닫히기 직전에 10번 오른쪽 탭과 겹칩니다. 뒤 해골을 고정하기 전 눈 지지대 옆 나사도 확인합니다.",
    cut: ["y", 22.98], blocker: true,
  },
];
