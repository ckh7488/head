import review from "./interference.json" with { type: "json" };

const ids = value => value.split(" ");
const move = (names, ...offset) => ({ ids: ids(names), offset });
const gear = (prefix, type, size, length, axis, seats, phase = 0) =>
  seats.map((seat, i) => ({ id: prefix + i, type, size, length, axis, seat, phase }));
const names = items => items.map(item => item.id).join(" ");

const service = review.service_hatch;
const at = (centers, z) => centers.map(([x, y]) => [x, y, z]);
const baseStack = review.base_stack;
const radialNuts = (prefix, layout) => layout.centers.flatMap(([x, y, angle], index) =>
  gear(`${prefix}${index}-`, "nut", 3, 0, [0, 0, 1], [[x, y, layout.nut_z]], angle * Math.PI / 180));
const radialMoves = (items, layout) => items.map((item, index) => {
  const angle = layout.centers[index][2] * Math.PI / 180;
  return move(item.id, Math.cos(angle) * layout.nut_stroke, Math.sin(angle) * layout.nut_stroke, 0);
});
const stackBolts = (prefix, layout) => gear(prefix, "bolt", 3, layout.length, [0, 0, -1], at(layout.centers, layout.bolt_z));
const seatNuts = radialNuts("seatNut", baseStack.seat);
const seatBolts = stackBolts("seatBolt", baseStack.seat);
const lidNuts = radialNuts("lidNut", baseStack.lid);
const lidBolts = stackBolts("lidBolt", baseStack.lid);
const keeperNuts = radialNuts("keeperNut", baseStack.keepers);
const keeperBolts = stackBolts("keeperBolt", baseStack.keepers);
const carrierNuts = gear("carrierNut", "nut", 3, 0, [0, 0, 1], at(baseStack.carriers.centers, baseStack.carriers.nut_z), Math.PI / 6);
const carrierBolts = gear("carrierBolt", "bolt", 3, 8, [0, 0, -1], at(baseStack.carriers.centers, baseStack.carriers.bolt_z));
const hatchNuts = gear("hatchNut", "nut", 3, 0, [0, 0, 1], at(service.base_centers, service.base_nut_seat), Math.PI / 6);
const hatchBolts = gear("hatchBolt", "bolt", 3, 8, [0, 0, 1], at(service.base_centers, service.base_screw_seat));
const hubBolts = gear("hubBolt", "bolt", 3, 8, [0, 0, -1], at(service.board_centers, service.board_screw_seat));
const hubNuts = gear("hubNut", "nut", 3, 0, [0, 0, 1], at(service.board_centers, service.board_nut_seat), Math.PI / 6);
const cable = review.cable_assembly;
const cableSeats = z => cable.x.map(x => [x, cable.y, z]);
const cableNuts = gear("cableNut", "nut", 3, 0, [0, 0, 1], cableSeats(cable.nut_floor), Math.PI / 6);
const cableTightNuts = gear("cableTightNut", "nut", 3, 0, [0, 0, 1], cableSeats(cable.nut_roof - 2.4), Math.PI / 6);
const cableBolts = gear("cableBolt", "bolt", 3, cable.bolt_length, [0, 0, -1], cableSeats(cable.bolt_seat));
const clipBolts = gear("clipBolt", "bolt", 3, 16, [0, -1, 0], cable.tray_mounts);
const clipSeats = y => cable.tray_mounts.map(([x, , z]) => [x, y, z]);
const clipWashers = gear("clipWasher", "washer", 3, 0, [0, -1, 0], clipSeats(cable.tray_washer_y));
const clipNuts = gear("clipNut", "nut", 3, 0, [0, -1, 0], clipSeats(cable.tray_nut_y));
const neck = review.neck;
const rotorNuts = gear("rotorNut", "nut", 3, 0, [0, 0, 1],
  neck.mast_mounts.map(([x, y]) => [x, y, neck.nut_roof - 2.4]), Math.PI / 6);
const mastBolts = gear("mastBolt", "bolt", 3, neck.mast_length, [0, 0, -1],
  neck.mast_mounts.map(([x, y]) => [x, y, neck.mast_seat]));
const hornBolts = gear("hornBolt", "bolt", 2, neck.horn_length, [0, 0, -1],
  neck.horn_mounts.map(([x, y]) => [x, y, neck.horn_seat]));
const pitchHornBolts = gear("pitchHornBolt", "bolt", 2, neck.horn_length, [-1, 0, 0],
  neck.pitch_horn_mounts.map(([y, z]) => [neck.pitch_horn_seat, y, z]));
const yokeSeats = [[-12, 17], [-12, 27.3], [12, 24.3]];
const yokeNuts = gear("yokeNut", "nut", 3, 0, [0, 0, 1], yokeSeats.map(([x, y]) => [x, y, 59.64]));
const yokeBolts = gear("yokeBolt", "bolt", 3, 16, [0, 0, -1], yokeSeats.map(([x, y]) => [x, y, 75]));
const blink = review.blink_mounts;
const railSeats = blink.rail_xz.map(([x, z]) => [x, blink.rail_screw_y, z]);
const railBolts = gear("railBolt", "bolt", 3, blink.rail_length, [0, -1, 0], railSeats);
const railNuts = gear("railNut", "nut", 3, 0, [0, 1, 0], railSeats.map(([x, , z]) => [x, blink.rail_nut_y, z]));
const crankBolts = gear("crankBolt", "bolt", 3, 8, [0, 0, -1], blink.crank_x.map(x => [x, -24, 163.55]));
const crankNuts = gear("crankNut", "nut", 3, 0, [0, 0, 1], blink.crank_x.map(x => [x, -24, blink.crank_nut_z]));
const blinkMotorHeads = review.motor_caps.Part046.map(([size, seat, axis], index) =>
  ({id: `blinkMotorHead${index}`, type: "head", size, seat, axis, phase: 0}));
const blinkPlateBolts = gear("blinkPlateBolt", "bolt", 3, 16, [-1, 0, 0], [[.9, 0, 183], [.9, 0, 189]]);
const blinkPlateNuts = gear("blinkPlateNut", "nut", 3, 0, [-1, 0, 0], [[-12.4, 0, 183], [-12.4, 0, 189]]);
const clampX = [-1, 1, 1];
const arm = (y, z, r) => [y + r * Math.cos(-56 * Math.PI / 180), z + r * Math.sin(-56 * Math.PI / 180)];
const [servoY, servoZ] = arm(-14, 170, 8.25);
const [crankY, crankZ] = arm(-24, 154, 8.25);
const [sideY, sideZ] = arm(-24, 154, 11.5);
const [lidY, lidZ] = arm(-39, 119, 11.5);
const linkBolts = [
  ...gear("middleServo", "bolt", 2, 8, [-1, 0, 0], [[9.45, servoY, servoZ]]),
  ...gear("centerLink", "bolt", 2, 8, [1, 0, 0], [[4.55, crankY, crankZ], [-53.75, sideY, sideZ], [-53.5, lidY, lidZ]]),
  ...gear("rightLink", "bolt", 2, 8, [-1, 0, 0], [[53.75, sideY, sideZ], [53.5, lidY, lidZ]]),
];
const linkNuts = [
  ...gear("middleNut", "nut", 2, 0, [1, 0, 0], [[1.25, servoY, servoZ]], Math.PI / 6),
  ...gear("linkNutPos", "nut", 2, 0, [1, 0, 0], [[10.55, crankY, crankZ], [-47.65, sideY, sideZ], [-47.65, lidY, lidZ]]),
  ...gear("linkNutNeg", "nut", 2, 0, [-1, 0, 0], [[47.65, sideY, sideZ], [47.65, lidY, lidZ]]),
];
const lidJointIds = new Set(["centerLink2", "rightLink1"]);
const upperLinkBolts = linkBolts.filter(item => !lidJointIds.has(item.id));
const lowerLinkBolts = linkBolts.filter(item => lidJointIds.has(item.id));
const upperLinkNuts = "middleNut0 linkNutPos0 linkNutPos1 linkNutNeg0";
const blinkRods = "Part056 Part057 Part060";

export const hardware = [
  ...hatchNuts, ...hatchBolts, ...hubBolts, ...hubNuts, ...cableNuts, ...cableTightNuts, ...cableBolts,
  ...clipBolts, ...clipWashers, ...clipNuts,
  ...seatNuts, ...seatBolts, ...lidNuts, ...lidBolts, ...keeperNuts, ...keeperBolts, ...carrierNuts, ...carrierBolts,
  ...rotorNuts, ...mastBolts, ...hornBolts, ...pitchHornBolts, ...yokeNuts, ...yokeBolts, ...railNuts, ...railBolts,
  ...crankNuts, ...crankBolts, ...linkBolts, ...linkNuts, ...blinkMotorHeads, ...blinkPlateBolts, ...blinkPlateNuts,
];

const PCB = "HubPCB HubBodyJ1 HubBodyJ2 HubBodyJ3 HubBodyJ4 HubBodyJ5 HubBodyJ6 HubBodyJ7 HubBodyJ8 HubBodyF1 HubBodyF2 HubBodyC1 HubBodyC2 HubBodyR1 HubBodyR2 HubBodyR3 HubBodyD1 HubBodyD2";
const frame = "Part019";
const lids = "Part076 Part077 Part078 Part079 Part058 Part059 Part061 Part062";
const rail = "Part063 Part048 Part050 Part052 BlinkCollarLeft BlinkCollarRight Part053 Part054 Part055";
const eyes = "Part024 Part025 Part026 Part027 Part028 Part029 Part030 Part031 Part032 Part033 Part034 Part035 Part036";
const yoke = "Part010 Part011 Part012 Part014 Part018 Part016";
const jaw = "Jaw_30_moving_jaw Jaw_36_left_jaw_servo_stay Jaw_37_right_jaw_bearing_stay Jaw_38_left_jaw_drive_arm Jaw_39_right_jaw_pivot_arm Jaw_XL330_M288_Jaw Jaw_MR104ZZ_jaw_right Jaw_Pin_jaw_4x10";
const camera = "Part065 Part066 Part067 Part068 Part080";
const front = `Part073 ${lids} ${camera}`;
const outer = review.outer_loading;
const yawStack = `Part001 Part006 Part007 Part017 ${names(rotorNuts)} ${names(hornBolts)}`;
const keepers = "YawBearingRetainer1 YawBearingRetainer2 YawBearingRetainer3";
const cableTray = "Part000 CableSaddle";
const mountedCableTray = `${cableTray} ${names(clipBolts)} ${names(clipWashers)} ${names(clipNuts)}`;

export const steps = [
  {
    id: "hatch-nuts", group: "받침", title: "바닥 덮개 너트", base: "Part000",
    moves: [move(names(hatchNuts), 0, 0, 22)], focus: [0, 60, -64], view: [1, -.78, 2.5], span: 116,
    task: "받침 안쪽에서 M3 너트 4개를 위에서 떨어뜨려 넣습니다.",
    check: "평평한 면을 맞춰 내려놓습니다. 손이 좁으면 M3×8 한 개를 너트에 두어 바퀴 걸어 손잡이처럼 쓴 뒤 빼면 됩니다.",
    stock: "M3 일반 육각너트 ×4", note: "홈 폭 5.95 mm · 입구 6.65 mm · 너트 맞은편 면 5.50 mm",
    cut: ["x", 41.2], checked: true,
  },
  {
    id: "hub-nuts", group: "받침", title: "덮개 기둥에 너트 넣기", base: "HubHolder",
    moves: [move(names(hubNuts), 0, 0, 20)], focus: [0, 58, -72], view: [1.35, -1.25, .94], span: 100,
    task: "덮개 안쪽 네 기둥에도 M3 너트를 위에서 넣습니다.",
    check: "홈에 너트를 넣고 나면 허브 PCB가 위에서 눌러 잡습니다.",
    stock: "M3 일반 육각너트 ×4", note: "덮개 가장자리 4.0 mm · 중앙 5.0 mm",
    cut: ["x", 30.8], checked: true,
  },
  {
    id: "hub-board", group: "받침", title: "허브 PCB를 덮개에", base: `HubHolder ${names(hubNuts)}`,
    moves: [move(PCB, 0, 0, 30)], focus: [0, 62, -69], view: [1, -1.15, 1], span: 93,
    task: "너트가 들어간 덮개 위에 기판을 얹습니다.", check: "기판의 네 구멍이 홈 중심과 맞고, 납땜부가 기둥에 닿지 않는지 확인합니다.",
  },
  {
    id: "hub-bolts", group: "받침", title: "허브 기판 나사 체결", base: `HubHolder ${PCB} ${names(hubNuts)}`,
    moves: [move(names(hubBolts), 0, 0, 19)], focus: [0, 59, -69], view: [1, -1.15, 1.45], span: 94,
    task: "기판 위에서 M3×8 네 개를 넣어 너트에 잡습니다.",
    check: "끝이 덮개 바닥까지 나오지 않습니다. 네 나사를 조금씩 번갈아 조입니다.",
    stock: "M3×8 일반 육각렌치 나사 ×4", checked: true,
  },
  {
    id: "hatch-fit", group: "받침", title: "아래에서 덮개 닫기", base: `Part000 CableSaddle ${names(hatchNuts)}`,
    moves: [move(`HubHolder ${PCB} ${names(hubNuts)} ${names(hubBolts)}`, 0, 0, -30)], focus: [0, 63, -90], view: [1.25, .98, -.6], span: 133,
    task: "허브와 덮개를 통째로 아래에서 들어 올립니다.",
    check: "서포트를 떼어낸 받침 홈에 덮개가 힘 없이 들어가야 합니다. 배선에는 덮개를 30 mm 내릴 여유를 둡니다.",
    note: "좌우·앞뒤에 편측 0.55 mm 여유를 뒀습니다.", cut: ["y", 51], checked: true,
  },
  {
    id: "hatch-bolts", group: "받침", title: "덮개 바깥 나사 체결", base: `Part000 HubHolder ${PCB} ${names(hatchNuts)}`,
    moves: [move(names(hatchBolts), 0, 0, -21)], focus: [0, 61, -82], view: [1.2, .88, -1], span: 118,
    task: "아래에서 M3×8 두 쌍을 넣고 일반 육각렌치로 조입니다.",
    check: "본체를 받쳐 세운 채 아래에서 조입니다. 뒤집어 작업한다면 열린 너트 홈을 종이테이프로 덮어 둡니다.",
    stock: "M3×8 일반 육각렌치 나사 ×4", note: "나사 머리는 받침 밑면보다 0.35 mm 안쪽입니다.",
    cut: ["y", 71], checked: true,
  },
  {
    id: "cable-tray", group: "받침", title: "트레이를 뒤에서 대기", base: "Part000",
    moves: [move("CableSaddle", 0, cable.tray_travel, 0)], focus: [0, 95, -64], view: [1, 1.4, .83], span: 130,
    task: "40번 트레이를 받침 뒤쪽에서 수평으로 밀어 붙입니다.",
    check: "두 나사 구멍을 받침 구멍과 맞춥니다. 받침 위는 열어 둡니다.", checked: true,
  },
  {
    id: "cable-tray-fasteners", group: "받침", title: "트레이 나사와 안쪽 너트", base: cableTray,
    moves: [move(names(clipBolts), 0, cable.tray_bolt_travel, 0),
      move(`${names(clipWashers)} ${names(clipNuts)}`, 0, -cable.tray_inner_travel, 0)],
    focus: [0, 105, -69], view: [1.1, 1.6, .9], span: 132, cut: ["x", -28.5],
    task: "뒤쪽 큰 구멍으로 M3×16을 넣고, 받침 안쪽에서 평와셔와 너트를 끼웁니다.",
    check: "2.5 mm 육각렌치의 긴 쪽으로 조입니다. 절개 보기에서 나사 머리와 안쪽 너트 자리를 확인할 수 있습니다.",
    stock: "M3×16 원통머리 · 일반 너트 · 평와셔 각 2개", checked: true,
  },
  {
    id: "cable-nuts", group: "받침", title: "케이블 너트를 뒤에서 넣기", base: mountedCableTray,
    moves: [move(names(cableNuts), 0, cable.nut_travel, 0)], focus: [0, 127, -62],
    view: [.5, 2, .3], span: 119, cut: ["z", -63.55],
    task: "트레이 뒤에 열린 가로 홈 다섯 곳에 M3 너트를 한 개씩 밀어 넣습니다.",
    check: "너트의 평평한 면을 홈 벽과 나란히 맞추고, 위에서 봤을 때 너트 구멍이 보이게 놓습니다.",
    stock: "M3 일반 육각너트 ×5", note: `홈 폭 ${cable.nut_width.toFixed(2)} mm · P1S 시험판 2번`, checked: true,
  },
  {
    id: "cable-cover", group: "받침", title: "커넥터 위에 덮개 내리기", base: `${mountedCableTray} ${names(cableNuts)}`,
    moves: [move("CableGate", 0, 0, cable.cover_travel)], focus: [0, 113, -53], view: [1, 1.6, 1.05], span: 115,
    task: "플러그 뒤턱을 홈에 밀착시킨 다음 42번 덮개를 위에서 내립니다.", check: "선만 누르지 않고 플러그 뒤턱이 걸려야 합니다. 실물에서는 10 N으로 당겨 봅니다.",
    checked: true,
  },
  {
    id: "cable-cover-bolts", group: "받침", title: "덮개 나사 다섯 개 조이기", base: `${mountedCableTray} CableGate ${names(cableTightNuts)}`,
    moves: [move(names(cableBolts), 0, 0, cable.cover_travel)], focus: [0, 119, -53], view: [.65, 1.65, 1.05], span: 118,
    task: "덮개가 내려앉은 뒤 M3×16을 위에서 걸고 육각렌치로 조입니다.",
    check: "너트가 홈 벽에 잡힌 상태에서 나사가 돌고 덮개가 고르게 닫히는지 확인합니다.",
    stock: "M3×16 일반 육각렌치 나사 ×5", checked: true,
  },
  {
    id: "carrier-nuts", group: "받침", title: "캐리어용 너트를 받침 밑에서", base: "Part000",
    moves: [move(names(carrierNuts), 0, 0, -15)], focus: [0, -13, -82], view: [1, 1, -1.6], span: 181,
    task: "받침 밑면의 여덟 홈에 일반 M3 너트를 넣습니다.",
    check: "받침을 돌리기 전에 얇은 종이테이프로 너트를 고정합니다.", stock: "일반 M3 육각너트 ×8", checked: true,
  },
  {
    id: "base-boards", group: "받침", title: "빈 보드 캐리어 내려놓기", base: `Part000 ${names(carrierNuts)}`,
    moves: [move("Part071 Part072", 0, 0, 36)], focus: [0, -8, -64], view: [1, -1.1, 1.4], span: 170,
    task: "C3와 OpenRB 캐리어를 각각 내려놓습니다.",
    check: "PCB를 얹기 전에 아래 받침 구멍과 캐리어 구멍을 맞춥니다.", checked: true,
  },
  {
    id: "carrier-bolts", group: "받침", title: "캐리어부터 M3로 체결", base: `Part000 Part071 Part072 ${names(carrierNuts)}`,
    moves: [move(names(carrierBolts), 0, 0, 18)], focus: [0, -8, -67], view: [1, -1.15, 1.5], span: 169,
    task: "캐리어 두 개를 위에서 각각 M3×8 네 개로 고정합니다.",
    check: "받침 밑면에 볼트 끝이 나오지 않는지 확인합니다.", stock: "M3×8 원통머리 ×8", checked: true,
  },
  {
    id: "boards-fit", group: "받침", title: "PCB를 캐리어에", base: `Part000 Part071 Part072 ${names(carrierBolts)}`,
    moves: [move("Part069 Part070", 0, 0, 26)], focus: [0, -8, -64], view: [1, -1.1, 1.4], span: 171,
    task: "케이블 공간을 확인하면서 보드를 올립니다.",
    check: "C3의 USB-C가 정면을 향하고 보드 밑 납땜부가 나사 머리에 닿지 않는지 확인합니다.",
    stock: "C3 기존 보드 홀 · M2×8 ×2",
  },
  {
    id: "base-stack-nuts", group: "받침", title: "베어링 받침과 상판 너트", base: "Part000",
    moves: [...radialMoves(seatNuts, baseStack.seat), ...radialMoves(lidNuts, baseStack.lid)],
    focus: [0, -2, -42], view: [1.1, -1.45, 1.4], span: 189,
    task: "받침 안쪽에서 중간 높이의 너트 세 개와 벽 위쪽 너트 세 개를 옆 홈에 밀어 넣습니다.",
    check: "높이가 다른 두 줄은 각각 베어링 받침과 맨 위 상판을 잡습니다.", stock: "일반 M3 육각너트 ×6", checked: true,
  },
  {
    id: "yaw-motor", group: "목", title: "받침 안 목 모터", base: "Part000 Part008 Part009",
    moves: [move("Part017", 0, 0, 34)], focus: [0, 12, -57], view: [1.15, -1.55, 1.5], span: 108,
    task: "ID 4 XL430을 05번 좌우 브래킷 사이에 대 봅니다.", check: "본체에는 M2.6 성형 나사용 구멍이 있습니다. 맞는 나사산과 길이의 원통머리 볼트를 확인한 뒤 고정합니다.",
    stock: "육각렌치 원통머리 · 본체 체결품 확인 대기", hold: true,
  },
  {
    id: "keeper-nuts", group: "목", title: "베어링 눌림판 너트", base: "Part001",
    moves: radialMoves(keeperNuts, baseStack.keepers), focus: [0, 0, -42], view: [1, -1.3, .56], span: 144,
    task: "작업대에서 베어링 받침 바깥쪽 세 홈에 M3 너트를 넣습니다.",
    check: "각 너트의 평평한 면을 홈에 맞춥니다.", stock: "일반 M3 육각너트 ×3", checked: true,
  },
  {
    id: "bearing-seat", group: "목", title: "베어링 받침 02 올리기", base: `Part000 Part017 ${names(seatNuts)}`,
    moves: [move(`Part001 ${names(keeperNuts)}`, 0, 0, 33)], focus: [0, 0, -48], view: [1.15, -1.4, 1.15], span: 180,
    task: "베어링 받침을 세 개의 안쪽 기둥 위에 놓습니다.", check: "세 체결 구멍이 맞으면 위에서 M3×16으로 조입니다.", checked: true,
  },
  {
    id: "bearing-seat-bolts", group: "목", title: "받침 02를 M3×16으로", base: `Part000 Part001 Part017 ${names(seatNuts)} ${names(keeperNuts)}`,
    moves: [move(names(seatBolts), 0, 0, 34)], focus: [0, 0, -37], view: [1.1, -1.3, 1.1], span: 165,
    task: "베어링을 넣기 전에 받침을 M3×16 세 개로 조입니다.",
    check: "맨 위 상판의 짧은 나사는 바깥쪽의 별도 구멍으로 들어갑니다.", stock: "M3×16 원통머리 ×3", checked: true,
  },
  {
    id: "yaw-bearing", group: "목", title: "6816 베어링 안착", base: "Part001 Part017",
    moves: [move("Part006", 0, 0, 28)], focus: [0, 2, -37], view: [1, -1.3, 1.4], span: 121,
    task: "받침 02에 6816을 위에서 넣습니다.", check: "외륜이 균일하게 앉는지 확인한 뒤 41번 눌림판 세 개를 M3×8로 고정합니다.",
    stock: "눌림판 M3×8 ×3", checked: true,
  },
  {
    id: "yaw-keepers", group: "목", title: "외륜 눌림판 세 개", base: `Part001 Part006 ${names(keeperNuts)}`,
    moves: [move(keepers, 0, 0, 15), move(names(keeperBolts), 0, 0, 25)],
    focus: [0, 0, -34], view: [1.15, -1.4, 1.2], span: 145,
    task: "외륜 위에 눌림판을 올리고 M3×8로 고정합니다.",
    check: "세 눌림판 모두 바깥 링에만 닿아야 합니다.", stock: "M3×8 원통머리 ×3", checked: true,
  },
  {
    id: "rotor-nuts", group: "목", title: "회전판 아래에 너트 넣기", base: "Part007",
    moves: [move(names(rotorNuts), 0, 0, -15)], focus: [0, 15, -36], view: [1, .85, -1.55], span: 98,
    task: "회전판을 작업대에서 뒤집어 일반 M3 너트 네 개를 밑면 홈에 넣습니다.",
    check: "회전판을 돌려도 빠지지 않게 홈 위에 얇은 종이테이프를 붙입니다.",
    stock: "일반 M3 육각너트 ×4", checked: true,
  },
  {
    id: "rotor", group: "목", title: "회전판을 위에서 안착", base: "Part017 Part006 Part001",
    moves: [move(`Part007 ${names(rotorNuts)}`, 0, 0, 26)], focus: [-4, 13, -37], view: [1, -1.35, .6], span: 94,
    task: "너트를 넣은 회전판을 베어링 내륜에 내려 놓습니다.",
    check: "너트와 기둥 나사 끝이 회전판 밑면보다 위에 있습니다.", checked: true,
  },
  {
    id: "rotor-horn", group: "목", title: "혼에 회전판부터 체결", base: `Part001 Part006 Part007 Part017 ${names(rotorNuts)}`,
    moves: [move(names(hornBolts), 0, 0, 21)], focus: [0, 3, -33], view: [1, -1.2, 1.35], span: 78,
    task: "기둥을 올리기 전에 모터 혼의 네 구멍을 맞추고 위에서 체결합니다.",
    check: "혼에 들어가는 나사 길이는 3 mm입니다.",
    stock: "XL430 혼 · M2×8 원통머리 ×4", checked: true,
  },
  {
    id: "base-deck", group: "목", title: "상판 03 닫기", base: `Part000 ${yawStack} ${keepers} ${names(lidNuts)}`,
    moves: [move("Part002", 0, 0, 29)], focus: [0, 0, -27], view: [1, -1.4, 1.1], span: 191,
    task: "기둥을 얹기 전에 상판 03을 위에서 내립니다.",
    check: "상판 바깥쪽 세 구멍을 받침 벽의 너트와 맞춥니다.", checked: true,
  },
  {
    id: "base-deck-bolts", group: "목", title: "상판 바깥쪽을 M3×8로", base: `Part000 Part002 ${yawStack} ${names(lidNuts)}`,
    moves: [move(names(lidBolts), 0, 0, 20)], focus: [0, 0, -24], view: [1, -1.4, 1.06], span: 191,
    task: "바깥쪽 세 자리에서 짧은 볼트로 상판을 조입니다.",
    check: "회전판을 손으로 움직여 상판에 닿지 않는지 봅니다.", stock: "M3×8 원통머리 ×3", checked: true,
  },
  {
    id: "mast", group: "목", title: "기둥을 회전판 위로", base: `${yawStack} Part002`,
    moves: [move("Part010", 0, 0, 36)], focus: [0, 20, -2], view: [1.5, -1.15, .45], span: 106,
    task: "상판 03을 닫은 다음 06번 기둥을 회전판 위에 놓습니다.",
    check: "기둥 앞면 밑의 홈이 이미 조인 모터 혼 나사 위를 덮습니다.", cut: ["x", 0], checked: true,
  },
  {
    id: "mast-bolts", group: "목", title: "기둥 양옆을 위에서 조이기", base: `${yawStack} Part002 Part010`,
    moves: [move(names(mastBolts), 0, 0, 19)], focus: [0, 19, -26], view: [1.3, -1.05, 1.2], span: 100,
    task: "기둥 양옆 날개 위에서 M3×8 네 개를 넣고 조입니다.",
    check: "네 곳 모두 일반 2.5 mm 육각렌치가 위에서 닿습니다.", stock: "M3×8 원통머리 ×4", checked: true,
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
    task: "07번 요크를 위에서 얹고 M3×16 세 개로 조입니다.", check: "세 볼트를 손으로 한 바퀴씩 걸고 차례로 조입니다.",
    stock: "M3×16 일반 육각렌치 나사 ×3",
  },
  {
    id: "pitch-horn", group: "목", title: "끄덕임 모터의 혼을 먼저", base: "Part016 Part018",
    moves: [move(names(pitchHornBolts), 21, 0, 0)], focus: [30, 0, 112], view: [1.7, -1., .65], span: 86,
    task: "모터가 요크 밖에 있을 때 08번 혼을 모터에 M2×8로 먼저 조입니다.",
    check: "네 자리에 평평한 원통머리 받침이 있습니다.", stock: "XL430 혼 · M2×8 원통머리 ×4", checked: true,
  },
  {
    id: "pitch-drive", group: "목", title: "끄덕임 모터를 요크 위에서", base: "Part011",
    moves: [move(`Part018 Part016 ${names(pitchHornBolts)}`, 0, 0, 52)], focus: [20, 0, 108], view: [1.2, -1.5, .88], span: 131,
    task: "혼을 조인 모터를 요크 위에서 내려 넣습니다.",
    check: "본체의 기존 나사산과 장착 나사 길이를 대조한 뒤 고정합니다.", hold: true,
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
    id: "eye-pin", group: "눈·눈꺼풀", title: "눈 상하축 핀을 양옆에서", base: "Part024 Part025 Part027 Part029 Part033 Part032 Part036",
    moves: [move("Part026", -18, 0, 0), move("Part028", 18, 0, 0)],
    focus: [0, -38, 120], view: [1.2, -1.8, .66], span: 135,
    task: "외장을 씌우기 전에 양쪽 지지대와 크래들의 구멍을 맞춰 Ø3 핀을 넣습니다.",
    check: "핀 끝과 나중에 들어오는 눈꺼풀 핀 사이에는 0.75 mm 틈이 있습니다.",
    stock: "Ø3 × 13 mm 핀 ×2", cut: ["y", -39.02], checked: true,
  },
  {
    id: "eye-module", group: "눈·눈꺼풀", title: "눈 모듈을 프레임에", base: `${frame} ${yoke} Part013 Part015`,
    moves: [move(`${eyes} Part037 Part038 Part039 Part040`, 0, -64, 0)],
    focus: [0, -13, 130], view: [1.3, -1.45, .77], span: 158,
    task: "축을 맞춘 눈 모듈을 머리 프레임 앞쪽에서 뒤로 밀어 넣습니다.",
    check: "해골을 씌우기 전에 좌우 지지대의 체결과 안구 움직임을 확인합니다.", checked: true,
  },
  {
    id: "lids", group: "눈·눈꺼풀", title: "왼쪽 눈꺼풀 핀", base: "Part076 Part078",
    moves: [move("Part058", -13, 0, 0), move("Part061", 13, 0, 0)],
    focus: [-34, -42, 123], view: [1, -1.9, .9], span: 71,
    task: "작업대에서 왼쪽 눈틀과 눈꺼풀을 맞추고 양쪽 핀을 넣습니다.",
    check: "핀은 눈틀에 잡히고 눈꺼풀만 가볍게 돕니다.", stock: "Ø2 × 8 mm 핀 ×2", checked: true,
  },
  {
    id: "right-lid", group: "눈·눈꺼풀", title: "오른쪽 눈꺼풀 핀", base: "Part077 Part079",
    moves: [move("Part059", -13, 0, 0), move("Part062", 13, 0, 0)],
    focus: [34, -42, 123], view: [1, -1.9, .9], span: 71,
    task: "오른쪽도 작업대에서 따로 조립합니다.",
    check: "양쪽 모두 막대 링크 없이 눈꺼풀이 손으로 가볍게 돌아가야 합니다.",
    stock: "Ø2 × 8 mm 핀 ×2", checked: true,
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
    id: "blink-clamps", group: "눈·눈꺼풀", title: "빈 크랭크에 너트 먼저", base: "Part053 Part054 Part055",
    moves: crankNuts.map((item, i) => move(item.id, clampX[i] * 8, 0, 0)),
    focus: [2, -22, 156], view: [1, -1.35, 1.3], span: 125,
    task: "크랭크를 축에 넣기 전에 일반 M3 너트를 각각 옆 홈에 밀어 넣습니다.",
    check: "가운데 크랭크도 빈 상태에서 너트를 넣습니다.", stock: "M3 일반 육각너트 ×3", checked: true,
  },
  {
    id: "blink-shaft", group: "눈·눈꺼풀", title: "공용축을 옆에서 통과", base: "Part063 Part050 Part052 Part054 BlinkCollarLeft BlinkCollarRight",
    moves: [move("Part048", -87, 0, 0)], focus: [-28, -21, 154], view: [1.05, -1.55, .42], span: 168,
    task: "두 간격통과 가운데 크랭크를 대고 Ø4 축을 왼쪽에서 넣습니다.",
    check: "37.4 mm 간격통은 왼쪽, 짧은 간격통은 오른쪽입니다. 끼울 때 축이 휘도록 누르지 않습니다.",
    stock: "Ø4 × 112 mm 연마축", checked: true,
  },
  {
    id: "blink-outer-cranks", group: "눈·눈꺼풀", title: "양끝 크랭크를 축에", base: "Part063 Part048 Part050 Part052 Part054 BlinkCollarLeft BlinkCollarRight crankNut1",
    moves: [move("Part053 crankNut0", -16, 0, 0), move("Part055 crankNut2", 16, 0, 0)],
    focus: [0, -23, 158], view: [1.2, -1.35, .72], span: 134,
    task: "너트를 미리 넣은 양끝 크랭크를 축에 끼웁니다.",
    check: "볼트는 다음 단계에 넣어 축의 세 평면과 방향을 맞춥니다.", checked: true,
  },
  {
    id: "blink-clamp-bolts", group: "눈·눈꺼풀", title: "축의 평면 세 곳 고정", base: `${rail} ${names(crankNuts)}`,
    moves: [move(names(crankBolts), 0, 0, 13)], focus: [0, -24, 160], view: [1, -1.3, .88], span: 108,
    task: "축 위쪽의 깊이 0.45 mm 평면에 나사 세 개를 맞춥니다.",
    check: "손으로 축을 돌려 세 나사가 각각 평면에 닿는지 확인합니다.",
    stock: "M3×8 일반 육각렌치 나사 ×3", checked: true,
  },
  {
    id: "blink-motor-heads", group: "눈·눈꺼풀", title: "눈꺼풀 모터 원통머리 자리", base: "Part045 Part046",
    moves: [move(names(blinkMotorHeads), 14, 0, 0)], focus: [1, -14, 177], view: [1.45, -.8, .53], span: 53,
    task: "모터 브래킷 앞면에 일반 M2 원통머리 외형을 대 봅니다.",
    check: "혼과 가까운 한 곳은 1.85 mm 깊이의 평평한 홈으로 머리를 내립니다. 혼을 끼우기 전에 조이는 자리입니다.",
    stock: "1.5 mm 육각렌치 · XL330 나사산 실물 대조 대기", cut: ["y", -6], hold: true,
  },
  {
    id: "blink-rail-nuts", group: "눈·눈꺼풀", title: "레일 앞에서 너트 넣기", base: "Part063",
    moves: [move(names(railNuts), 0, -16, 0)], focus: [0, 11, 150], view: [1, -1.5, 1], span: 89,
    task: "레일을 프레임에 붙이기 전에 앞쪽 홈에 M3 너트 네 개를 넣습니다.",
    check: "너트를 홈에 넣고 앞을 위로 향하게 잡습니다.", stock: "M3 일반 육각너트 ×4", checked: true,
  },
  {
    id: "blink-rail", group: "눈·눈꺼풀", title: "레일을 프레임에", base: frame,
    moves: [move(`${rail} ${names(railNuts)} ${names(crankNuts)} ${names(crankBolts)}`, 0, -27, 0)],
    focus: [0, 8, 157], view: [1, 1.6, 1.1], span: 136,
    task: "조립한 레일을 앞쪽에서 밀어 프레임에 댑니다.",
    check: "뒤쪽 나사 구멍과 레일 너트가 맞으면 다음 단계에서 조입니다.", checked: true,
  },
  {
    id: "blink-rail-bolts", group: "눈·눈꺼풀", title: "레일 뒤쪽 나사 네 개", base: `${frame} ${rail} ${names(railNuts)}`,
    moves: [move(names(railBolts), 0, 21, 0)], focus: [0, 25, 147], view: [1, 1.6, 1.1], span: 106,
    task: "프레임 뒤에서 M3×16으로 레일을 고정합니다.",
    check: "레일 네 곳과 모터판 두 곳에 같은 길이를 씁니다.", stock: "M3×16 원통머리", checked: true,
  },
  {
    id: "blink-horn-nut", group: "눈·눈꺼풀", title: "혼에 작은 너트 먼저", base: "Part047",
    moves: [move("middleNut0", -9, 0, 0)], focus: [1, -14, 167], view: [-1.25, -1.5, .8], span: 42,
    task: "혼을 모터에 붙이기 전에 안쪽 홈에 M2 너트를 넣습니다.",
    check: "너트가 들어간 뒤 혼을 모터에 체결할 준비를 합니다.", stock: "M2 일반 육각너트 ×1", checked: true,
  },
  {
    id: "blink-motor-fit", group: "눈·눈꺼풀", title: "눈꺼풀 모터판을 레일에", base: rail,
    moves: [move("Part045 Part046 Part047 middleNut0", 0, -31, 0)], focus: [0, -6, 177], view: [1.25, -1.5, .48], span: 103,
    task: "케이스와 혼을 단 모터판을 레일 앞쪽에서 받침에 댑니다.",
    check: "모터판이 붙으면 다음 단계에서 두 곳을 체결합니다.", checked: true,
  },
  {
    id: "blink-motor-fasteners", group: "눈·눈꺼풀", title: "모터판 체결", base: `${rail} Part045 Part046 Part047`,
    moves: [move(names(blinkPlateBolts), 24, 0, 0), move(names(blinkPlateNuts), -12, 0, 0)],
    focus: [-3, -2, 182], view: [1.2, -.9, .72], span: 91,
    task: "몸체 양옆에서 M3×16과 일반 육각너트를 넣어 모터판을 고정합니다.",
    check: "레일을 붙인 볼트와 같은 규격입니다.", stock: "M3×16 원통머리 · M3 일반 너트 각 2개", checked: true,
  },
  {
    id: "blink-upper-links", group: "눈·눈꺼풀", title: "외장 전 링크 윗부분 체결", base: `${rail} Part045 Part046 Part047 ${blinkRods} ${upperLinkNuts}`,
    moves: upperLinkBolts.map(item => move(item.id, -item.axis[0] * (item.id === "middleServo0" ? 8.5 : 12), 0, 0)),
    focus: [0, -20, 151], view: [1.3, -1.7, .85], span: 128,
    task: "가운데 구동 링크와 양옆 링크의 위쪽 끝을 외장 밖에서 조입니다.",
    check: "앞 외장을 넣는 동안 양쪽 링크를 그림의 위치에 가볍게 잡아 둡니다.",
    stock: "M2×8 원통머리 ×4", checked: true,
  },
  {
    id: "jaw-fit", group: "턱·외장", title: "턱 오른쪽 축 맞추기", base: jaw.replace(" Jaw_Pin_jaw_4x10", ""),
    moves: [move("Jaw_Pin_jaw_4x10", -15, 0, 0)], focus: [26, -20, 88], view: [1.6, -1.1, .5], span: 100,
    task: "작업대에서 오른쪽 Ø4 핀을 턱 안쪽에서 베어링과 힌지팔로 밀어 넣습니다.",
    check: "턱을 손으로 열고 닫아 한쪽만 들리는지 확인합니다. 접착 위치는 가조립이 끝난 뒤 잡습니다.",
    stock: "MR104ZZ ×1 · Ø4 × 10 mm 핀 ×1", checked: true,
  },
  {
    id: "camera-fit", group: "턱·외장", title: "코 카메라 놓기", base: "Part073 Part065 Part080",
    moves: [move("Part066 Part067 Part068", ...outer.camera)], focus: [0, -34, 97], view: [1.1, 1.45, .55], span: 98,
    task: "열린 뒤쪽 위에서 카메라와 브래킷을 함께 코 쪽으로 비스듬히 내립니다.",
    check: "영상 가장자리에 코 테두리가 보이는지 접착 전에 확인합니다.",
    stock: "카메라 고정홀 · M2 원통머리와 평와셔", checked: true,
  },
  {
    id: "front-orbit", group: "턱·외장", title: "눈틀을 열린 뒤쪽에서", base: "Part073",
    moves: [move(lids, 0, outer.orbit, 0)], focus: [0, -32, 123], view: [1.1, 1.5, .63], span: 136,
    task: "핀을 끼운 두 눈틀을 해골 뒤쪽에서 눈구멍으로 밀어 넣습니다.",
    check: "눈꺼풀은 닫아 두고 링크는 나중에 연결합니다.", closedLids: true, checked: true,
  },
  {
    id: "front-shell", group: "턱·외장", title: "앞 해골을 정면에서", base: `${frame} ${yoke} ${eyes} Part013 Part015 Part063 ${blinkRods} ${names(upperLinkBolts)} ${upperLinkNuts}`,
    moves: [move(front, 0, -outer.front, 0)], focus: [0, -24, 123], view: [1.25, 1.75, .37], span: 178,
    task: "목 핀을 먼저 끼웁니다. 눈꺼풀을 닫아 둔 앞 외장을 정면에서 뒤로 밀어 맞춥니다.",
    check: "안쪽에 만든 통로로 눈 지지대와 목 축이 지나갑니다.",
    cut: ["x", 66.9], closedLids: true, checked: true,
  },
  {
    id: "blink-links", group: "턱·외장", title: "링크 아래를 눈꺼풀에", base: `${rail} ${front} Part045 Part046 Part047 ${blinkRods} ${names(upperLinkBolts)} ${names(linkNuts)}`,
    moves: lowerLinkBolts.map(item => move(item.id, -item.axis[0] * 12, 0, 0)),
    focus: [0, -23, 155], view: [1.4, -1.75, 1], span: 129,
    task: "앞 외장을 맞춘 뒤 눈꺼풀을 열어 링크의 아래쪽 끝 두 곳을 조입니다.",
    check: "관절에 축방향 유격 0.10~0.20 mm를 둡니다.",
    stock: "M2×8 원통머리 ×2 · M2 평와셔", checked: true,
  },
  {
    id: "jaw-to-shell", group: "턱·외장", title: "턱 조립체를 아래에서", base: `${frame} ${yoke} ${eyes} ${front} Part013 Part015 ${blinkRods}`,
    moves: [move(jaw, 0, 0, -outer.jaw)], focus: [0, -25, 77], view: [1.3, -1.45, .65], span: 175,
    task: "지지대와 핀을 맞춘 턱 조립체를 해골 아래에서 올립니다.",
    check: "양쪽 지지대가 제 위치에 닿을 때까지 접착제 없이 먼저 맞춰 봅니다.", checked: true,
  },
  {
    id: "rear-shell", group: "턱·외장", title: "뒤 해골을 씌우기", base: `${frame} ${front} ${eyes} ${rail} Part041 Part042 Part064 BallastTray BallastCover`,
    moves: [move("Part074", 0, 68, 0)], focus: [0, 43, 151], view: [1.1, 1.4, .59], span: 172,
    task: "뒤 해골을 이음면에 수직으로 밀어 넣습니다.",
    check: "앞뒤 이음면이 힘 없이 닫히는지 봅니다. 눈 지지대와 링크의 옆 나사를 먼저 확인합니다.",
    cut: ["y", 22.98], checked: true,
  },
];
