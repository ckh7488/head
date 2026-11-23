import review from "./interference.json" with { type: "json" };
import { withAssemblyState } from "./assembly-state.js";

const ids = value => value.split(" ");
const move = (names, ...offset) => ({ ids: ids(names), offset });
const gear = (prefix, type, size, length, axis, seats, phase = 0) =>
  seats.map((seat, i) => ({ id: prefix + i, type, size, length, axis, seat, phase }));
const names = items => items.map(item => item.id).join(" ");

const service = review.service_hatch;
const at = (centers, z) => centers.map(([x, y]) => [x, y, z]);
const baseStack = review.base_stack;
const stackNuts = (prefix, layout) => gear(prefix, "nut", 3, 0, [0, 0, 1], at(layout.centers, layout.nut_z), Math.PI / 6);
const stackBolts = (prefix, layout) => gear(prefix, "bolt", 3, layout.length, [0, 0, 1], at(layout.centers, layout.bolt_z));
const seatNuts = stackNuts("seatNut", baseStack.seat);
const seatBolts = stackBolts("seatBolt", baseStack.seat);
const lidNuts = stackNuts("lidNut", baseStack.lid);
const lidBolts = stackBolts("lidBolt", baseStack.lid);
const keeperNuts = stackNuts("keeperNut", baseStack.keepers);
const keeperBolts = stackBolts("keeperBolt", baseStack.keepers);
const carrierNuts = stackNuts("carrierNut", baseStack.carriers);
const carrierBolts = stackBolts("carrierBolt", { ...baseStack.carriers, length: 8 });
const c3CarrierNuts = carrierNuts.slice(0, 4);
const openrbCarrierNuts = carrierNuts.slice(4);
const c3CarrierBolts = carrierBolts.slice(0, 4);
const openrbCarrierBolts = carrierBolts.slice(4);
const boardMounts = (key, suffix, type, length, axis, phase) => {
  const layout = review.board_mounts[key];
  return gear(key + suffix, type, 2, length, axis, at(layout.centers, layout[type + "_z"]), phase);
};
const c3Nuts = boardMounts("c3", "Nut", "nut", 0, [0, 0, 1], Math.PI / 6);
const c3Bolts = boardMounts("c3", "Bolt", "bolt", 8, [0, 0, -1], 0);
const openrbNuts = boardMounts("openrb", "Nut", "nut", 0, [0, 0, 1], Math.PI / 6);
const openrbBolts = boardMounts("openrb", "Bolt", "bolt", 8, [0, 0, -1], 0);
const hatchNuts = gear("hatchNut", "nut", 3, 0, [0, 0, 1], at(service.base_centers, service.base_nut_seat));
const hatchBolts = gear("hatchBolt", "bolt", 3, 8, [0, 0, 1], at(service.base_centers, service.base_screw_seat));
const hubBolts = gear("hubBolt", "bolt", 3, 8, [0, 0, -1], at(service.board_centers, service.board_screw_seat));
const hubNuts = gear("hubNut", "nut", 3, 0, [0, 0, 1], at(service.board_centers, service.board_nut_seat), Math.PI / 6);
const cable = review.cable_assembly;
const cableSeats = z => cable.x.map(x => [x, cable.y, z]);
const cableNuts = gear("cableNut", "nut", 3, 0, [0, 0, 1], cableSeats(cable.nut_face - 2.4), Math.PI / 6);
const handStarted = (nuts, rise) => Object.fromEntries(nuts.map(nut => [nut.id, [0, 0, rise]]));
const cableBolts = gear("cableBolt", "bolt", 3, cable.bolt_length, [0, 0, -1], cableSeats(cable.bolt_seat));
const clipBolts = gear("clipBolt", "bolt", 3, 16, [0, -1, 0], cable.tray_mounts);
const clipSeats = y => cable.tray_mounts.map(([x, , z]) => [x, y, z]);
const clipWashers = gear("clipWasher", "washer", 3, 0, [0, -1, 0], clipSeats(cable.tray_washer_y));
const clipNuts = gear("clipNut", "nut", 3, 0, [0, -1, 0], clipSeats(cable.tray_nut_y));
const neck = review.neck;
const rotorNuts = gear("rotorNut", "nut", 3, 0, [0, 0, 1],
  at(neck.mast_mounts, neck.rotor_nut_seat));
const mastStuds = gear("mastStud", "bolt", 3, neck.mast_length, [0, 0, 1],
  at(neck.mast_mounts, neck.stud_seat));
const mastNuts = gear("mastNut", "nut", 3, 0, [0, 0, 1],
  neck.mast_mounts.map(([x, y]) => [x, y, neck.mast_seat]));
const hornBolts = gear("hornBolt", "bolt", 2, neck.horn_length, [0, 0, -1],
  neck.horn_mounts.map(([x, y]) => [x, y, neck.horn_seat]));
const pitchHornBolts = gear("pitchHornBolt", "bolt", 2, neck.horn_length, [-1, 0, 0],
  neck.pitch_horn_mounts.map(([y, z]) => [neck.pitch_horn_seat, y, z]));
const yokeSeats = neck.yoke_mounts;
const yokeNuts = gear("yokeNut", "nut", 3, 0, [0, 0, 1], yokeSeats.map(([x, y]) => [x, y, 59.64]));
const yokeBolts = gear("yokeBolt", "bolt", 3, 16, [0, 0, -1], yokeSeats.map(([x, y]) => [x, y, 75]));
const blink = review.blink_mounts;
const railSeats = blink.rail_xz.map(([x, z]) => [x, blink.rail_screw_y, z]);
const railBolts = gear("railBolt", "bolt", 3, blink.rail_length, [0, -1, 0], railSeats);
const railNuts = gear("railNut", "nut", 3, 0, [0, 1, 0], railSeats.map(([x, , z]) => [x, blink.rail_nut_y, z]));
const crankBolts = gear("crankBolt", "bolt", 3, 8, [0, 0, -1], blink.crank_x.map(x => [x, -24, 163.55]));
const crankNuts = gear("crankNut", "nut", 3, 0, [0, 0, 1], blink.crank_x.map(x => [x, -24, blink.crank_nut_z]), Math.PI / 6);
const motorHeads = (prefix, part) => review.motor_caps[part].map(([size, seat, axis], index) =>
  ({id: `${prefix}Head${index}`, type: "head", size, seat, axis, phase: 0}));
const blinkMotorHeads = motorHeads("blinkMotor", "Part046");
const eyeYawHeads = motorHeads("eyeYaw", "Part039");
const eyePitchHeads = motorHeads("eyePitch", "Part042");
const jawHeads = motorHeads("jawMotor", "Jaw_36_left_jaw_servo_stay");
const blinkPlateBolts = gear("blinkPlateBolt", "bolt", 3, 16, [-1, 0, 0], blink.plate_z.map(z => [.9, blink.plate_y, z]));
const blinkPlateNuts = gear("blinkPlateNut", "nut", 3, 0, [-1, 0, 0], blink.plate_z.map(z => [-12.4, blink.plate_y, z]), Math.PI / 6);
const arm = (y, z, r) => [y + r * Math.cos(-56 * Math.PI / 180), z + r * Math.sin(-56 * Math.PI / 180)];
const [servoY, servoZ] = arm(-14, 170, 8.25);
const [crankY, crankZ] = arm(-24, 154, 8.25);
const [sideY, sideZ] = arm(-24, 154, 11.5);
const [lidY, lidZ] = arm(-39, 119, 11.5);
const linkBolts = [
  ...gear("middleServo", "bolt", 2, 8, [1, 0, 0], [[blink.horn_screw_x, servoY, servoZ]]),
  ...gear("centerLink", "bolt", 2, 8, [1, 0, 0], [[4.55, crankY, crankZ], [-53.75, sideY, sideZ], ]),
  ...gear("centerLower", "bolt", 2, 8, [1, 0, 0], [[-53.5, lidY, lidZ]]),
  ...gear("rightLink", "bolt", 2, 8, [-1, 0, 0], [[53.75, sideY, sideZ]]),
  ...gear("rightLower", "bolt", 2, 8, [-1, 0, 0], [[53.5, lidY, lidZ]]),
];
const linkNuts = [
  ...gear("middleNut", "nut", 2, 0, [1, 0, 0], [[blink.horn_nut_x, servoY, servoZ]], Math.PI / 6),
  ...gear("linkNutPos", "nut", 2, 0, [1, 0, 0], [[10.55, crankY, crankZ], [-47.65, sideY, sideZ], ]),
  ...gear("linkNutNeg", "nut", 2, 0, [-1, 0, 0], [[47.65, sideY, sideZ]]),
  ...gear("linkLeftLowerNut", "nut", 2, 0, [1, 0, 0], [[-47.65, lidY, lidZ]]),
  ...gear("linkRightLowerNut", "nut", 2, 0, [-1, 0, 0], [[47.65, lidY, lidZ]]),
];
const lidJointIds = new Set(["centerLower0", "rightLower0"]);
const upperLinkBolts = linkBolts.filter(item => !lidJointIds.has(item.id) && !["middleServo0", "centerLink0"].includes(item.id));
const lowerLinkBolts = linkBolts.filter(item => lidJointIds.has(item.id));
const upperLinkNuts = "linkNutPos1 linkNutNeg0";
const linkWashers = [
  ...gear("middleWasher", "washer", 2, 0, [1, 0, 0], [[blink.horn_nut_x - .3, servoY, servoZ]]),
  ...gear("linkWasherPos", "washer", 2, 0, [-1, 0, 0], [[10.55, crankY, crankZ], [-47.65, sideY, sideZ], [-47.65, lidY, lidZ]]),
  ...gear("linkWasherNeg", "washer", 2, 0, [1, 0, 0], [[47.65, sideY, sideZ], [47.65, lidY, lidZ]]),
];
const lowerLinkWasherIds = "linkWasherPos2 linkWasherNeg1";
const upperLinkWasherIds = "linkWasherPos1 linkWasherNeg0";
const blinkRods = "Part056 Part057 Part060";

function spanner(id, nut, outward, offset, thickness = review.tools[nut.size].thickness) {
  const { profile } = review.tools[nut.size];
  return { id, type: "spanner", tool: true, size: nut.size, axis: nut.axis, outward, profile, thickness,
    seat: nut.seat.map((coordinate, i) => coordinate + offset * nut.axis[i]) };
}
const cableSpanner = spanner("cableSpanner", cableNuts[2], [0, 1, 0], 2.4 - review.tools[3].thickness - .26);
const hatchSpanner = spanner("hatchSpanner", hatchNuts[3], [1, 0, 0], .24);
const mastSpanner = spanner("mastSpanner", rotorNuts[3], [1, 0, 0], .24);
const lowerSpanner = spanner("lowerSpanner", linkNuts.find(item => item.id === "linkLeftLowerNut0"), [0, 0, -1], .12);
const crankSpanner = spanner("crankSpanner", crankNuts[1], [0, -1, 0], 2.4 - blink.crank_wrench - .15, blink.crank_wrench);
const hubTool = review.tools[3];
const hubSocket = {
  id: "hubSocket", type: "socket", tool: true, size: 3, axis: [0, 0, -1],
  seat: [hubNuts[0].seat[0], hubNuts[0].seat[1], service.board_nut_seat + 2.33],
  radius: hubTool.socket_radius, opening: 3.25, depth: 5.6, length: 22,
};
const hubKey = {
  id: "hubKey", type: "tool", tool: true, size: 3, axis: [0, 0, 1],
  seat: [hubBolts[0].seat[0], hubBolts[0].seat[1], service.board_screw_seat + 3.02],
  radius: hubTool.key_radius, length: 29,
};

export const hardware = [
  ...hatchNuts, ...hatchBolts, ...hubBolts, ...hubNuts, ...cableNuts, ...cableBolts,
  ...clipBolts, ...clipWashers, ...clipNuts,
  ...seatNuts, ...seatBolts, ...lidNuts, ...lidBolts, ...keeperNuts, ...keeperBolts, ...carrierNuts, ...carrierBolts,
  ...c3Nuts, ...c3Bolts, ...openrbNuts, ...openrbBolts,
  ...rotorNuts, ...mastStuds, ...mastNuts, ...hornBolts, ...pitchHornBolts, ...yokeNuts, ...yokeBolts, ...railNuts, ...railBolts,
  ...crankNuts, ...crankBolts, ...linkBolts, ...linkNuts, ...linkWashers, ...blinkMotorHeads, ...blinkPlateBolts, ...blinkPlateNuts,
  ...eyeYawHeads, ...eyePitchHeads, ...jawHeads,
  cableSpanner, hatchSpanner, mastSpanner, crankSpanner, lowerSpanner, hubSocket, hubKey,
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

const cablePlugs = "InputXT30 InputXT60 CameraUSB ControlUSB";
const hubPlugs = "HubPlugJ3 HubPlugJ4 HubPlugJ5 HubPlugJ6 HubPlugJ7 HubPlugJ8";

const definitions = [
  {
    id: "xt60-mate", group: "받침", title: "작업대에서 전원 암수 연결", base: "InputXT30 InputXT60",
    moves: [move("InputXT60Mate", 0, -16, 0)], focus: [-24, 104, -57], view: [1.05, -.8, 1.5], span: 94,
    task: "작업대에서 XT30U와 XT60U 암수를 끝까지 꽂습니다.",
    check: "XT30U 열수축부는 한 가닥당 Ø4.0 mm, XT60U는 Ø5.6 mm까지입니다.",
    ports: ["InputXT30", "InputXT60", "InputXT60Mate"], checked: true,
  },
  {
    id: "cable-plugs", group: "받침", title: "트레이 위에 커넥터 얹기", base: "CableSaddle",
    moves: [move(cablePlugs, 0, 0, 25)], focus: [0, 106, -53], view: [.95, -.90, 1.5], span: 132,
    task: "연결한 전원 두 쌍과 USB 연장선 두 개를 열린 트레이 위에서 내려놓습니다.",
    check: "커넥터 뒤턱을 받침 턱에 붙이고, 받침으로 들어갈 선 끝을 같은 방향으로 펴 둡니다.",
    stock: "Alpha Wire 3055 · 18 AWG, 6718 · XT60U용 12 AWG",
    ports: [...ids(cablePlugs), "InputXT60Mate"], checked: true,
  },
  {
    id: "cable-cover", group: "받침", title: "작업대에서 덮개 닫기", base: "CableSaddle",
    moves: [move("CableGate", 0, 0, cable.cover_travel)], focus: [0, 113, -53], view: [.7, 1.6, .95], span: 115,
    task: "트레이를 작업대에 둔 채 42번 덮개를 위에서 내립니다.",
    check: "전선 피복이 덮개 사이에 끼지 않고 각 커넥터 뒤턱이 홈에 걸립니다.",
    ports: ids(cablePlugs), checked: true,
  },
  {
    id: "cable-nuts", group: "받침", title: "트레이 밖에서 덮개 너트 걸기", base: "CableSaddle",
    moves: [move(names(cableBolts), 0, 0, 18), move(names(cableNuts), 0, 0, -11)],
    seatOffsets: handStarted(cableNuts, -.85),
    focus: [0, 122, -61], view: [.4, 2, -.38], span: 116,
    task: "덮개 위에서 M3×16을 한 개씩 꽂고, 뒤쪽 열린 턱에서 너트를 손으로 두 바퀴 걸어 둡니다.",
    check: "너트 밑이 열려 있어 손으로 받칠 수 있습니다.", stock: "M3×16 원통머리 · 일반 M3 육각너트 각 5개",
    checked: true, inspectFasteners: true,
  },
  {
    id: "cable-cover-bolts", group: "받침", title: "작업대에서 덮개 조이기", base: "CableSaddle",
    moves: [move(cableSpanner.id, 0, cable.wrench_travel, 0), move(names(cableNuts), 0, 0, -.85)],
    focus: [0, 123, -61], view: [.9, 1.8, -.52], span: 136,
    task: "뒤에서 5.5 mm 오픈 스패너로 너트를 잡고, 위에서 2.5 mm 육각렌치로 조입니다.",
    check: "트레이를 작업대 끝에 두고 아래가 보이는 상태에서 다섯 곳을 조입니다.",
    note: `뒤쪽 공구 통로 폭 ${cable.wrench_width} mm · P2S 시험판 2번`, checked: true, inspectFasteners: true,
  },
  {
    id: "cable-tray", group: "받침", title: "연결한 트레이를 통째로 넣기", base: "Part000",
    moves: [move("CableSaddle", 0, cable.tray_travel, 0)], focus: [0, 98, -58], view: [1, 1.4, 1.03], span: 142,
    task: "선 끝을 받침 뒤쪽 창에 맞추고, 덮개까지 조립한 트레이를 수평으로 밀어 붙입니다.",
    check: "전원 암수는 이미 연결돼 있습니다. 받침 안쪽에서 네 선이 각 창을 지나 꺾이지 않는지 봅니다.",
    ports: [...ids(cablePlugs), "InputXT60Mate"], checked: true,
  },
  {
    id: "cable-tray-fasteners", group: "받침", title: "완성 트레이를 M3 두 개로 고정", base: cableTray,
    moves: [move(names(clipBolts), 0, cable.tray_bolt_travel, 0),
      move(`${names(clipWashers)} ${names(clipNuts)}`, 0, -cable.tray_inner_travel, 0)],
    focus: [0, 105, -69], view: [1.1, 1.6, .9], span: 132, cut: ["x", -28.5],
    task: "뒤에서 M3×16 두 개를 넣고, 덮개가 열린 받침 안쪽에서 평와셔와 너트를 끼웁니다.",
    check: "2.5 mm 긴 육각렌치와 5.5 mm 공구로 조입니다. 허브를 장착하기 전에 작업합니다.",
    stock: "M3×16 원통머리 · 일반 너트 · 평와셔 각 2개", checked: true,
  },
  {
    id: "hub-board", group: "받침", title: "작업대에서 허브 PCB 얹기", base: "HubHolder",
    moves: [move(PCB, 0, 0, 26)], focus: [0, 59, -69], view: [1, -1.15, 1], span: 93,
    task: "분리한 바닥 덮개를 작업대에 두고 허브를 네 기둥에 얹습니다.",
    check: "보드 아래 납땜부가 기둥에 닿는지와 네 구멍을 확인합니다.",
  },
  {
    id: "hub-nuts", group: "받침", title: "소켓에 너트를 담아 허브에 걸기", base: "HubHolder",
    moves: [move(names(hubBolts), 0, 0, 17), move(`${hubSocket.id} ${hubNuts[0].id}`, 0, 0, -17),
      move(names(hubNuts.slice(1)), 0, 0, -17)],
    seatOffsets: handStarted([...hubNuts, hubSocket], -.80),
    focus: [-15, 53, -78], view: [-1, -1.15, -.78], span: 107,
    task: "5.5 mm 소켓에 일반 M3 너트를 담아 덮개 아래에서 넣습니다. 기판 쪽에서 M3×8을 두 바퀴 걸어 둡니다.",
    check: "덮개 양끝만 받쳐 밑을 비웁니다. 그림은 네 곳 중 왼쪽 한 곳의 소켓을 보여 줍니다.",
    note: `덮개 구멍 Ø${2 * hubTool.socket_bore} mm · 확인한 소켓 앞쪽 외경 Ø${2 * hubTool.socket_radius} mm`,
    stock: "M3×8 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "hub-bolts", group: "받침", title: "허브를 양쪽에서 조이기", base: "HubHolder",
    moves: [move(hubSocket.id, 0, 0, -15), move(hubKey.id, 0, 0, 13), move(names(hubNuts), 0, 0, -.80)],
    focus: [-15, 53, -73], view: [-1, -1.35, -.48], span: 111,
    task: "아래에서 5.5 mm 소켓으로 너트를 잡고 위에서 2.5 mm 육각렌치로 조입니다.",
    check: "초록색 소켓을 그대로 잡고 위쪽 육각렌치를 돌립니다. 기판이 휘지 않게 네 곳을 조금씩 조입니다.",
    checked: true, inspectFasteners: true,
  },
  {
    id: "hub-wiring", group: "받침", title: "작업대에서 JST 하네스 꽂기", base: "HubHolder",
    moves: [move(hubPlugs, 0, 0, 16)], focus: [0, 61, -66], view: [1, -1.15, 1.15], span: 103,
    task: "J4–J6은 PH 3핀, J7–J8은 EH 3핀을 꽂습니다. J3 PH 2핀에는 OpenRB의 GND와 DATA를 연결합니다.",
    check: "빨강은 2번 전원, 검정은 1번 GND, 흰색은 3번 DATA입니다. J3은 1번 GND·2번 DATA입니다. 모터별 전압과 ID를 대조합니다.",
    stock: "Alpha Wire 6712 · 24 AWG · 피복 Ø1.04–1.14 mm · JST PHR-2/3, EHR-3",
    ports: ids(hubPlugs),
    note: "전원 J1은 XT30U-F를 꽂습니다. B15의 Phoenix J2에는 18 AWG 연선을 7 mm 벗겨 연결합니다. 허브를 30 mm 내려도 선이 당겨지지 않게 둡니다.", checked: true,
  },
  {
    id: "hatch-fit", group: "받침", title: "아래에서 허브와 덮개 올리기", base: "Part000",
    moves: [move("HubHolder", 0, 0, -30)], focus: [0, 63, -90], view: [1.25, .98, -.6], span: 133,
    task: "허브를 체결한 덮개를 받침 아래에서 함께 들어 올립니다.",
    check: "덮개가 힘 없이 들어가는지 확인합니다. 배선에는 덮개를 30 mm 내릴 여유를 둡니다.",
    note: "덮개 둘레 편측 0.55 mm 여유", cut: ["y", 51], checked: true,
  },
  {
    id: "hatch-nuts", group: "받침", title: "바닥 덮개에 일반 너트 걸기", base: "Part000",
    moves: [move(names(hatchBolts), 0, 0, -18), move(names(hatchNuts), 0, 0, 17)],
    seatOffsets: handStarted(hatchNuts, .80),
    focus: [25, 61, -73], view: [1.5, .95, .34], span: 133,
    task: "받침을 받쳐 둔 채 아래에서 M3×8을 넣고 위에서 보이는 자리에 너트를 손으로 겁니다.",
    check: "옆 창에서 너트와 볼트 끝을 볼 수 있습니다.",
    stock: "M3×8 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "hatch-bolts", group: "받침", title: "측면 스패너로 바닥 덮개 조이기", base: "Part000",
    moves: [move(hatchSpanner.id, 48, 0, 0), move(names(hatchNuts), 0, 0, .80)],
    focus: [42, 66, -74], view: [1.7, .94, .30], span: 145,
    task: "바깥쪽 창으로 5.5 mm 스패너를 넣고 밑에서 2.5 mm 육각렌치로 조입니다.",
    check: "허브를 다시 내릴 때도 같은 창으로 너트를 잡습니다. 받침을 받쳐 바닥과 측면을 모두 엽니다.",
    note: `측면 공구 통로 폭 ${service.wrench_width} mm · P2S 시험판 3번`, checked: true, inspectFasteners: true,
  },
  {
    id: "boards-fit", group: "받침", title: "작업대에서 C3를 지지점에", base: "Part071",
    moves: [move("Part070", 0, 0, 26)], focus: [-52, -7, -65], view: [1, -1.1, 1.5], span: 106,
    task: "받침 밖에서 USB-C가 정면을 향하도록 보드를 두 기둥에 올립니다.",
    check: "보드가 기둥에 바로 앉는지 봅니다.", checked: true,
  },
  {
    id: "c3-bolts", group: "받침", title: "C3 캐리어를 작업대에서 체결", base: "Part071",
    moves: [move(names(c3Bolts), 0, 0, 17), move(names(c3Nuts), 0, 0, -13)],
    focus: [-52, -7, -70], view: [1, -1.15, .65], span: 100,
    task: "위에서 M2×8을 넣고 넓은 원형 구멍 아래에서 4 mm 소켓으로 일반 M2 너트를 잡습니다.",
    check: "1.5 mm 육각렌치로 보드가 휘지 않을 만큼 조입니다.",
    stock: "M2×8 원통머리 · 일반 M2 육각너트 각 2개", checked: true, inspectFasteners: true,
  },
  {
    id: "base-boards", group: "받침", title: "C3를 고정한 캐리어 넣기", base: "Part000",
    moves: [move("Part071", 0, 0, 36)], focus: [-44, -8, -68], view: [1, -1.1, 1.5], span: 120,
    task: "C3를 조립한 왼쪽 캐리어를 받침에 놓습니다.",
    check: "기판 양옆의 바깥 네 구멍에 위쪽 공구가 들어갈 공간이 보입니다.", checked: true, inspectFasteners: true,
  },
  {
    id: "carrier-bolts", group: "받침", title: "왼쪽 캐리어 M3 체결", base: "Part000",
    moves: [move(names(c3CarrierBolts), 0, 0, -18), move(names(c3CarrierNuts), 0, 0, 18)],
    focus: [-47, -8, -69], view: [1, -1.15, 1.0], span: 118,
    task: "받침 아래에서 M3×8을 넣고 위에서 5.5 mm 소켓으로 너트를 잡아 조입니다.",
    check: "보드 바깥에 체결 위치가 있어 보드를 조립한 채 공구가 들어갑니다.",
    stock: "M3×8 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "openrb-usb", group: "받침", title: "USB-C를 보드에 먼저 꽂기", base: "Part069",
    moves: [move("OpenRBUSB", 0, -16, 0)], focus: [54, -42, -62], view: [-.8, -1.3, 1.5], span: 92,
    task: "작업대에서 OpenRB에 USB-C 데이터 케이블을 먼저 꽂습니다.",
    check: "플러그와 보드가 같이 들어갈 방향을 확인합니다.",
    note: "플러그 몸체 12.4 × 18 × 6.2 mm 이내", checked: true,
  },
  {
    id: "openrb-board", group: "받침", title: "작업대에서 OpenRB를 지지점에", base: "Part072",
    moves: [move("Part069", 0, 0, 26)], focus: [53, -9, -64], view: [-1, -1.1, 1.5], span: 110,
    task: "USB-C를 꽂은 OpenRB를 받침 밖에서 네 기둥에 올립니다.",
    check: "시험판 4번에서 실물 보드의 구멍 네 곳을 먼저 맞춰 봅니다.",
    note: "OpenRB 홀 간격은 제조사 정면 그림에서 환산했습니다.", checked: true, inspectFasteners: true,
  },
  {
    id: "openrb-bolts", group: "받침", title: "OpenRB 캐리어를 작업대에서 체결", base: "Part072",
    moves: [move(names(openrbBolts), 0, 0, 17), move(names(openrbNuts), 0, 0, -13)],
    focus: [53, -9, -68], view: [-1, -1.1, .65], span: 111,
    task: "위에서 M2×8을 넣고 아래에서 4 mm 소켓으로 일반 M2 너트를 잡습니다.",
    check: "1.5 mm 육각렌치로 보드를 당겨 휘게 하기 전에 멈춥니다.",
    stock: "M2×8 원통머리 · 일반 M2 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "openrb-carrier", group: "받침", title: "OpenRB를 고정한 캐리어 넣기", base: "Part000",
    moves: [move("Part072", 0, 0, 36)], focus: [43, -8, -68], view: [-1, -1.1, 1.5], span: 120,
    task: "OpenRB와 USB-C가 달린 오른쪽 캐리어를 받침에 내립니다.",
    check: "케이블은 받침 가운데 쪽으로 보냅니다.", checked: true, inspectFasteners: true,
  },
  {
    id: "openrb-carrier-bolts", group: "받침", title: "오른쪽 캐리어 M3 체결", base: "Part000",
    moves: [move(names(openrbCarrierBolts), 0, 0, -18), move(names(openrbCarrierNuts), 0, 0, 18)],
    focus: [48, -8, -68], view: [-1, -1.15, 1.0], span: 112,
    task: "받침 아래에서 M3×8을 넣고 위에서 5.5 mm 소켓으로 잡아 조입니다.",
    check: "작업대에서 받침을 옆으로 지지하면 위아래 공구를 동시에 댈 수 있습니다.",
    stock: "M3×8 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "yaw-motor", group: "목", title: "받침 안 목 모터", base: "Part000 Part008 Part009",
    moves: [move("Part017", 0, 0, 34)], focus: [0, 12, -57], view: [1.15, -1.55, 1.5], span: 108,
    task: "ID 4 XL430을 05번 좌우 브래킷 사이에 놓고 왼쪽 창에서 JST를 꽂습니다.",
    check: "왼쪽 창에서 플러그가 12 mm 드나듭니다. 본체에는 M2.6 탭핑 나사 자리가 있습니다.",
    stock: "JST EHR-3 · 본체용 육각 나사의 나사산 호환은 실물 검증 범위", hold: true,
  },
  {
    id: "yaw-bearing", group: "목", title: "작업대에서 6816 베어링부터", base: "Part001",
    moves: [move("Part006", 0, 0, 28)], focus: [0, 2, -37], view: [1, -1.3, 1.4], span: 121,
    task: "분리된 베어링 받침 02에 6816을 위에서 올려 외륜을 앉힙니다.",
    check: "이 상태에서 받침 위와 밑에 공구가 들어갑니다.", stock: "6816 ×1", checked: true,
  },
  {
    id: "yaw-keepers", group: "목", title: "외륜 눌림판 세 개", base: "Part001",
    moves: [move(keepers, 0, 0, 12)], focus: [0, 0, -34], view: [1.15, -1.4, 1.2], span: 145,
    task: "외륜 위에 눌림판 세 개를 올립니다.",
    check: "세 눌림판 모두 바깥 링에 닿습니다.", checked: true,
  },
  {
    id: "keeper-nuts", group: "목", title: "작업대에서 눌림판 체결", base: "Part001",
    moves: [move(names(keeperBolts), 0, 0, -17), move(names(keeperNuts), 0, 0, 14)],
    focus: [0, 0, -34], view: [1.15, -1.4, .72], span: 145,
    task: "아래에서 M3×8을 넣고 위의 일반 너트를 5.5 mm 소켓으로 잡아 조입니다.",
    check: "조인 뒤에도 베어링 내륜이 돌아갑니다.", stock: "M3×8 원통머리 · 일반 M3 육각너트 각 3개",
    checked: true, inspectFasteners: true,
  },
  {
    id: "bearing-seat", group: "목", title: "조립한 베어링 받침 올리기", base: "Part000",
    moves: [move("Part001", 0, 0, 33)], focus: [0, 0, -47], view: [1.15, -1.4, 1.15], span: 180,
    task: "베어링과 눌림판을 조인 02번 받침을 세 안쪽 기둥에 내려놓습니다.",
    check: "베어링 받침을 올릴 때 눌림판 볼트와 너트도 함께 움직입니다.", checked: true,
  },
  {
    id: "bearing-seat-bolts", group: "목", title: "베어링 받침을 아래에서 체결", base: "Part000",
    moves: [move(names(seatBolts), 0, 0, -45), move(names(seatNuts), 0, 0, 19)],
    focus: [0, 0, -45], view: [1.1, -1.3, .76], span: 185,
    task: "바닥의 원형 통로로 M3×16을 넣고 위에서 너트를 소켓으로 잡습니다.",
    check: "긴 2.5 mm 육각렌치로 아래쪽에서 조입니다.", stock: "M3×16 원통머리 · 일반 M3 육각너트 각 3개",
    checked: true, inspectFasteners: true,
  },
  {
    id: "rotor-nuts", group: "목", title: "회전판에 M3 볼트 네 개 세우기", base: "Part007",
    moves: [move(names(mastStuds), 0, 0, -18), move(names(rotorNuts), 0, 0, 17)],
    focus: [0, 15, -35], view: [1, .85, .53], span: 99,
    task: "회전판 밑 볼트 자리 네 곳에서 서포트를 빼고 M3×16을 넣습니다. 육각렌치로 잡고 위쪽 너트를 조입니다.",
    check: "머리는 아래, 나사산은 위로 나옵니다. 이 볼트에 나중에 목 기둥을 얹습니다.",
    stock: "M3×16 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
  },
  {
    id: "rotor", group: "목", title: "회전판을 위에서 안착", base: "Part017 Part006 Part001",
    moves: [move("Part007", 0, 0, 26)], focus: [-4, 13, -37], view: [1, -1.35, .6], span: 94,
    task: "볼트 네 개를 세운 회전판을 베어링 내륜에 내려 놓습니다.",
    check: "밑면 나사 머리가 모터와 베어링에 닿지 않고 돌아갑니다.", checked: true,
  },
  {
    id: "rotor-horn", group: "목", title: "혼에 회전판부터 체결", base: `Part001 Part006 Part007 Part017 ${names(rotorNuts)}`,
    moves: [move(names(hornBolts), 0, 0, 21)], focus: [0, 3, -33], view: [1, -1.2, 1.35], span: 78,
    task: "기둥을 올리기 전에 모터 혼의 네 구멍을 맞추고 위에서 체결합니다.",
    check: "혼에 들어가는 나사 길이는 3 mm입니다.",
    stock: "XL430 혼 · M2×8 원통머리 ×4", checked: true,
  },
  {
    id: "base-deck", group: "목", title: "상판 03 닫기", base: `Part000 ${yawStack} ${keepers}`,
    moves: [move("Part002", 0, 0, 29)], focus: [0, 0, -27], view: [1, -1.4, 1.1], span: 191,
    task: "기둥을 얹기 전에 상판 03을 위에서 내립니다.",
    check: "상판 바깥쪽 세 구멍을 받침 벽의 너트와 맞춥니다.", checked: true,
  },
  {
    id: "base-deck-bolts", group: "목", title: "상판을 아래에서 M3×8로", base: "Part000",
    moves: [move(names(lidBolts), 0, 0, -65), move(names(lidNuts), 0, 0, 19)], focus: [0, 0, -24], view: [1, -1.4, 1.06], span: 191,
    task: "바닥의 바깥 세 통로로 M3×8을 넣고 위에서 5.5 mm 소켓으로 너트를 잡습니다.",
    check: "긴 2.5 mm 육각렌치로 조인 뒤 회전판을 손으로 돌려 봅니다.", stock: "M3×8 원통머리 ×3", checked: true,
  },
  {
    id: "yoke-fit", group: "목", title: "상하 요크 얹기", base: "Part010",
    moves: [move("Part011", 0, 0, 28)], focus: [0, 16, 76], view: [1, -1.25, .87], span: 118,
    task: "작업대에 놓은 목 기둥 위에 07번 요크를 얹습니다.",
    check: "목 기둥 아래 쪽으로 두 손과 공구를 댈 수 있는 공간을 비웁니다.", checked: true,
  },
  {
    id: "yoke-nuts", group: "목", title: "기둥 옆에서 스패너로 요크 체결", base: "Part010",
    moves: [move("yokeNut0 yokeNut1", -18, 0, 0), move("yokeNut2", 18, 0, 0),
      move(names(yokeBolts), 0, 0, 25)],
    seatOffsets: handStarted(yokeBolts, 6), focus: [0, 23, 67], view: [1.3, -1.35, .53], span: 100,
    task: "요크 위에서 볼트를 들고 있는 동안 옆 통로에 스패너로 너트를 댑니다.",
    check: "왼쪽 두 개는 한 개씩 맞춥니다.",
    stock: "M3×16 원통머리 · 일반 M3 육각너트 각 3개", checked: true, inspectFasteners: true,
  },
  {
    id: "yoke-bolts", group: "목", title: "너트를 잡고 요크 조이기", base: "Part010",
    moves: [move(names(yokeBolts), 0, 0, 6)], focus: [0, 23, 68], view: [1.3, -1.35, .68], span: 99,
    task: "스패너로 너트를 잡은 상태에서 볼트를 내려 2.5 mm 육각렌치로 조입니다.",
    check: "기둥 옆이 열린 상태에서 세 곳에 차례로 공구를 댑니다.", checked: true, inspectFasteners: true,
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
    check: "JST를 요크의 뒤쪽 창에서 꽂습니다. 플러그 삽입 경로는 12 mm입니다.", hold: true,
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
    id: "eye-pitch-stay", group: "눈·눈꺼풀", title: "눈 상하 모터 지지대", base: frame,
    moves: [move("Part064", 0, 35, 0)], focus: [50, 21, 150], view: [1.3, .7, 1], span: 86,
    task: "머리 뒤가 열린 상태에서 34번 지지대를 대고 프레임 쪽 체결 자리 두 곳을 맞춥니다.",
    check: "프레임 쪽 체결 방식과 나사 길이는 가조립에서 대조합니다.", hold: true,
  },
  {
    id: "blink-motor-heads", group: "눈·눈꺼풀", title: "눈꺼풀 모터 원통머리 자리", base: "Part045 Part046",
    moves: [move(names(blinkMotorHeads), 14, 0, 0)], focus: [1, -14, 177], view: [1.45, -.8, .53], span: 53,
    task: "모터 브래킷 앞면에 일반 M2 원통머리 외형을 대 봅니다.",
    check: "혼과 가까운 한 곳은 1.85 mm 깊이의 평평한 홈으로 머리를 내립니다. 혼을 끼우기 전에 조이는 자리입니다.",
    stock: "1.5 mm 육각렌치 · XL330 나사산 실물 대조 대기", cut: ["y", -6], hold: true,
  },
  {
    id: "blink-rail", group: "눈·눈꺼풀", title: "레일을 프레임에", base: frame,
    moves: [move("Part063", 0, -27, 0)],
    focus: [0, 8, 157], view: [1, 1.6, 1.1], span: 136,
    task: "빈 레일을 앞쪽에서 밀어 프레임에 댑니다. 먼저 레일을 체결한 다음 작은 베어링을 넣습니다.",
    check: "레일과 프레임 구멍을 맞춥니다. 레일 앞쪽에는 소켓이 들어가는 원형 통로가 보입니다.", checked: true,
  },
  {
    id: "blink-rail-bolts", group: "눈·눈꺼풀", title: "앞뒤에서 레일 나사 네 개", base: "Part063",
    moves: [move(names(railBolts), 0, 21, 0), move(names(railNuts), 0, -24, 0)], focus: [0, 25, 147], view: [1, 1.6, 1.1], span: 106,
    task: "뒤에서 M3×16을 넣고 앞쪽 원형 통로에서 5.5 mm 소켓으로 일반 너트를 잡습니다.",
    check: "공용축과 모터를 놓기 전에 앞뒤에서 네 개를 조입니다.",
    stock: "M3×16 원통머리 · 일반 M3 육각너트 각 4개", checked: true, inspectFasteners: true,
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
    id: "eye-pitch-motor-heads", group: "눈·눈꺼풀", title: "눈 상하 모터와 모터판", base: "Part041 Part042",
    moves: [move(names(eyePitchHeads.filter(head => head.size === 2)), 18, 0, 0)], focus: [56, 10, 148], view: [1.6, -1, .6], span: 74,
    task: "작업대에서 상하 모터를 모터판에 맞추고 옆에서 체결합니다.",
    check: "모터 케이스에 맞는 나사산과 나사 길이를 실물에서 대조합니다.", hold: true,
  },
  {
    id: "eye-pitch-horn", group: "눈·눈꺼풀", title: "작업대에서 눈 상하 혼 끼우기", base: "Part042",
    moves: [move("Part043", 18, 0, 0)], focus: [57, 10, 150], view: [1.55, -1, .64], span: 78,
    task: "모터와 모터판을 프레임에 넣기 전에 작업대에서 혼을 오른쪽에서 끼웁니다.",
    check: "혼을 넣을 때 이미 붙인 모터 나사 머리를 확인합니다.", checked: true,
  },
  {
    id: "eye-pitch-motor-fit", group: "눈·눈꺼풀", title: "눈 상하 모터를 지지대에", base: "Part064",
    moves: [move("Part042", 8, -32, 0)], focus: [56, 10, 148], view: [1.65, -1.2, .67], span: 107,
    task: "모터·혼·나사를 붙인 모터판을 비어 있는 머리 정면에서 약간 비스듬히 밀어 넣습니다.",
    check: "안구 모듈을 넣기 전에 모터판 위 두 자리를 조일 수 있게 둡니다.", checked: true,
  },
  {
    id: "eye-pitch-plate-heads", group: "눈·눈꺼풀", title: "눈 상하 모터판 두 자리", base: "Part064",
    moves: [move(names(eyePitchHeads.filter(head => head.size === 3)), 18, 0, 0)], focus: [56, 10, 160], view: [1.65, -1.2, .67], span: 100,
    task: "모터판 위 두 곳에 M3 머리와 2.5 mm 육각렌치 공간을 확인합니다.",
    check: "지지대 쪽 파일럿 구멍은 체결 방식을 실물에서 대조합니다.", hold: true,
  },
  {
    id: "blink-horn-nut", group: "눈·눈꺼풀", title: "작업대에서 혼과 가운데 링크 체결", base: "Part047 Part056",
    moves: [move("middleServo0", -11, 0, 0), move("middleNut0 middleWasher0", 13, 0, 0)],
    focus: [3, -12, 167], view: [1.2, -1.4, .75], span: 56,
    task: "모터에 혼을 붙이기 전에 가운데 링크를 M2×8로 연결합니다. 바깥에서 4 mm 소켓으로 너트를 잡습니다.",
    check: "안쪽에서 1.5 mm 육각렌치로 조이고 링크 유격을 확인합니다.",
    stock: "M2×8 원통머리 · 일반 M2 육각너트 · 평와셔 각 1개", checked: true, inspectFasteners: true,
  },
  {
    id: "blink-center-link", group: "눈·눈꺼풀", title: "작업대에서 가운데 크랭크까지 체결", base: "Part047 Part054",
    moves: [move("centerLink0", -12, 0, 0), move("linkNutPos0 linkWasherPos0", 12, 0, 0)],
    focus: [6, -18, 155], view: [1.2, -1.4, .75], span: 68,
    task: "베어링 사이에 들어가기 전에 가운데 크랭크와 링크를 작업대에서 조입니다.",
    check: "1.5 mm 육각렌치와 4 mm 소켓이 양옆에서 닿습니다.",
    stock: "M2×8 원통머리 · 일반 M2 육각너트 · 평와셔 각 1개", checked: true, inspectFasteners: true,
  },
  {
    id: "blink-motor-fit", group: "눈·눈꺼풀", title: "눈꺼풀 모터판을 레일에", base: "Part063",
    moves: [move("Part045 Part046 Part047", 0, -31, 0)], focus: [0, -6, 177], view: [1.25, -1.5, .48], span: 103,
    task: "혼과 가운데 링크, 크랭크를 단 모터판을 앞쪽에서 레일에 댑니다.",
    check: "모터판이 붙으면 다음 단계에서 두 곳을 체결합니다.", checked: true,
  },
  {
    id: "blink-motor-fasteners", group: "눈·눈꺼풀", title: "모터판 체결", base: "Part063",
    moves: [move(names(blinkPlateBolts), 24, 0, 0), move(names(blinkPlateNuts), -12, 0, 0)],
    focus: [-3, -2, 182], view: [1.2, -.9, .72], span: 91,
    task: "몸체 양옆에서 M3×16과 일반 육각너트를 넣어 모터판을 고정합니다.",
    check: "레일을 붙인 볼트와 같은 규격입니다.", stock: "M3×16 원통머리 · M3 일반 너트 각 2개", checked: true,
  },
  {
    id: "blink-shaft", group: "눈·눈꺼풀", title: "공용축을 옆에서 통과", base: "Part063 Part050 Part052 Part054 BlinkCollarLeft BlinkCollarRight",
    moves: [move("Part048", -87, 0, 0)], focus: [-28, -21, 154], view: [1.05, -1.55, .42], span: 168,
    task: "눈 상하 모터가 자리 잡은 뒤 간격통과 이미 연결한 가운데 크랭크를 통과하도록 Ø4 축을 왼쪽에서 넣습니다.",
    check: "37.4 mm 간격통은 왼쪽, 짧은 간격통은 오른쪽입니다. 끼울 때 축이 휘도록 누르지 않습니다.",
    stock: "Ø4 × 112 mm 연마축", checked: true,
  },
  {
    id: "blink-outer-cranks", group: "눈·눈꺼풀", title: "양끝 크랭크를 축에", base: "Part063 Part048 Part050 Part052 Part054 BlinkCollarLeft BlinkCollarRight",
    moves: [move("Part053", -16, 0, 0), move("Part055", 16, 0, 0)],
    focus: [0, -23, 158], view: [1.2, -1.35, .72], span: 134,
    task: "양끝 크랭크를 열린 면이 정면을 향하게 끼웁니다.",
    check: "볼트는 다음 단계에 넣어 축의 세 평면과 방향을 맞춥니다.", checked: true,
  },
  {
    id: "blink-clamps", group: "눈·눈꺼풀", title: "크랭크 너트를 정면에서 대기", base: rail,
    moves: [move(names(crankNuts), 0, -15, 0), move(names(crankBolts), 0, 0, 13)],
    seatOffsets: { ...handStarted(crankNuts, -.55), ...handStarted(crankBolts, 5) },
    focus: [3, -24, 159], view: [1, -1.35, .7], span: 132,
    task: "볼트를 조금 들어 두고 앞에서 5.5 mm 스패너로 너트를 댑니다.",
    check: "나사 끝을 Ø4 축의 평평한 부분에 맞춥니다. 한 곳씩 작업합니다.",
    stock: "M3×8 원통머리 · 일반 M3 육각너트 각 3개", checked: true, inspectFasteners: true,
  },
  {
    id: "blink-clamp-bolts", group: "눈·눈꺼풀", title: "크랭크 축을 공구로 조이기", base: rail,
    moves: [move(crankSpanner.id, 0, -17, 0), move(names(crankNuts), 0, 0, -.55), move(names(crankBolts), 0, 0, 5)],
    focus: [0, -25, 159], view: [1, -1.3, .68], span: 129,
    task: "앞에서 너트를 스패너로 잡고 위에서 육각렌치로 나사를 조입니다.",
    check: `머리 바깥 폭 16 mm·두께 ${blink.crank_wrench} mm의 스패너로 정면과 좌우 15° 경로를 확인했습니다.`,
    checked: true, inspectFasteners: true,
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
    id: "eye-yaw-motor-heads", group: "눈·눈꺼풀", title: "눈 좌우 모터와 모터판", base: "Part038 Part039",
    moves: [move(names(eyeYawHeads), 0, 0, 17)], focus: [0, -36, 111], view: [1, -1, 1.2], span: 74,
    task: "작업대에서 좌우 모터와 모터판을 맞추고 1.5 mm 육각렌치가 들어가는 네 자리를 확인합니다.",
    check: "나사 머리는 아래 단계에서도 같이 움직입니다. 모터 케이스 나사산과 깊이는 실물에서 대조합니다.", hold: true,
  },
  {
    id: "eye-module", group: "눈·눈꺼풀", title: "눈 모듈을 프레임에", base: `${frame} ${yoke} Part013 Part015`,
    moves: [move(`${eyes} Part037 Part038 Part039 Part040`, 0, -64, 0)],
    focus: [0, -13, 130], view: [1.3, -1.45, .77], span: 158,
    task: "축을 맞춘 눈 모듈을 머리 프레임 앞쪽에서 뒤로 밀어 넣습니다.",
    check: "해골을 씌우기 전에 좌우 지지대의 체결과 안구 움직임을 확인합니다.", checked: true,
  },
  {
    id: "eye-pitch-link", group: "눈·눈꺼풀", title: "눈 상하 링크 연결", base: "Part064",
    moves: [move("Part044", 0, -26, 26)], focus: [58, -5, 139], view: [1.65, -1.2, .67], span: 116,
    task: "안구 모듈을 넣은 뒤 상하 링크를 정면 위에서 비스듬히 내려 혼과 안구에 연결합니다.",
    check: "앞 외장을 끼우기 전에 손으로 안구 상하축을 움직여 봅니다.", checked: true,
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
    id: "blink-upper-links", group: "눈·눈꺼풀", title: "외장 전 링크 윗부분 체결", base: `${rail} Part045 Part046 Part047 ${blinkRods} ${upperLinkNuts} ${upperLinkWasherIds}`,
    moves: upperLinkBolts.map(item => move(item.id, -item.axis[0] * 12, 0, 0)),
    focus: [0, -20, 151], view: [1.3, -1.7, .85], span: 128,
    task: "양옆 링크의 위쪽 끝을 외장을 씌우기 전에 체결합니다.",
    check: "앞 외장을 넣는 동안 양쪽 링크를 그림의 위치에 가볍게 잡아 둡니다.",
    stock: "M2×8 원통머리 · M2 평와셔 각 2개", checked: true,
  },
  {
    id: "jaw-motor-heads", group: "턱·외장", title: "턱 모터와 왼쪽 지지대", base: "Jaw_36_left_jaw_servo_stay Jaw_XL330_M288_Jaw",
    moves: [move(names(jawHeads), -16, 0, 0)], focus: [-42, -8, 99], view: [-1.6, -1, .57], span: 81,
    task: "작업대에서 턱 모터를 왼쪽 지지대에 맞추고 바깥에서 체결합니다.",
    check: "원통머리가 들어가는 네 자리와 모터 케이스에 맞는 나사산을 대조합니다.", hold: true,
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
    check: "영상 가장자리와 실물 카메라의 고정 홀을 브래킷에 대조합니다.",
    stock: "카메라 고정 방식 실물 대조", hold: true,
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
    id: "blink-lower-nuts", group: "턱·외장", title: "눈꺼풀 아래에서 작은 너트 잡기", base: frame,
    moves: [move("linkLeftLowerNut0 linkRightLowerNut0 " + lowerLinkWasherIds, 0, 0, -13),
      move(lowerSpanner.id, 0, 0, -13)],
    focus: [-29, -31, 112], view: [.7, -1.6, -.50], span: 113,
    task: "앞 외장을 끼운 뒤 턱이 비어 있을 때 아래에서 4 mm 스패너를 올려 너트를 댑니다.",
    check: "그림은 왼쪽 예입니다. 한쪽씩 와셔와 너트를 대고 바로 볼트를 겁니다.", checked: true, inspectFasteners: true,
  },
  {
    id: "blink-links", group: "턱·외장", title: "양옆에서 눈꺼풀 링크 조이기", base: frame,
    moves: lowerLinkBolts.map(item => move(item.id, -item.axis[0] * 12, 0, 0)),
    focus: [0, -29, 115], view: [1.4, -1.75, .63], span: 129,
    task: "아래의 스패너로 너트를 잡은 채 옆에서 1.5 mm 육각렌치로 조입니다.",
    check: "각 관절에 축방향 유격 0.10~0.20 mm를 둡니다.",
    stock: "M2×8 원통머리 · M2 평와셔 각 2개", checked: true, inspectFasteners: true,
  },
  {
    id: "jaw-to-shell", group: "턱·외장", title: "턱 조립체를 아래에서", base: `${frame} ${yoke} ${eyes} ${front} Part013 Part015 ${blinkRods}`,
    moves: [move(jaw, 0, 0, -outer.jaw)], focus: [0, -25, 77], view: [1.3, -1.45, .65], span: 175,
    task: "받침에 붙이기 전에 작업대에서 머리를 높게 받치고 턱을 아래에서 올립니다.",
    check: "왼쪽 턱 지지대의 작은 홈이 앞에서 조인 눈꺼풀 링크 나사를 지나갑니다. 양쪽 지지대가 앉는지 봅니다.", checked: true,
  },
  {
    id: "mast", group: "턱·외장", title: "기둥과 머리를 받침 위로", base: `${yawStack} Part002`,
    moves: [move("Part010", 0, 0, 36)], focus: [0, 4, 65], view: [1.1, -1.15, .52], span: 288,
    task: "작업대에서 조립한 머리를 06번 기둥과 함께 들어 회전판 위에 낮춥니다.",
    check: "회전판에 세운 볼트 네 개에 기둥 발을 맞춥니다. 머리를 받친 채 너트를 손으로 겁니다.", cut: ["x", 0], checked: true,
  },
  {
    id: "mast-bolts", group: "턱·외장", title: "기둥 바깥 위아래 너트로 고정", base: "Part000",
    moves: [move(names(mastNuts), 0, 0, 17), move(mastSpanner.id, 21, 0, 0)],
    focus: [17, 19, -26], view: [1.3, -1.05, .68], span: 108,
    task: "이미 세워 둔 M3 볼트에 기둥을 얹은 뒤 위쪽 일반 너트 네 개를 조입니다.",
    check: "아래쪽 너트는 열린 홈에서 5.5 mm 스패너로 잡고 위쪽 너트는 소켓으로 조입니다.",
    stock: "일반 M3 육각너트 ×4", checked: true, inspectFasteners: true,
  },
  {
    id: "neck-wiring", group: "턱·외장", title: "목과 머리 배선 연결", base: "Part000",
    moves: [], focus: [0, 0, 55], view: [1.6, -1, .8], span: 310,
    task: "뒤 해골을 닫기 전에 받침에서 올라오는 선을 회전판 앞 통로로 보내고 모터 네 개와 카메라를 연결합니다.",
    check: "ID 4는 왼쪽 창, ID 5는 뒤쪽 창에 꽂습니다. ID 1의 뒤쪽 플러그는 눈 모듈을 만들 때 미리 꽂습니다.",
    inspectFasteners: true, wiring: true, checked: true, status: "CAD 삽입 경로 확인",
  },
  {
    id: "rear-shell", group: "턱·외장", title: "뒤 해골을 씌우기", base: frame,
    moves: [move("Part074", 0, 68, 0)], focus: [0, 43, 151], view: [1.1, 1.4, .59], span: 172,
    task: "뒤 해골을 이음면에 수직으로 밀어 넣습니다.",
    check: "앞뒤 이음면이 힘 없이 닫히는지 봅니다. 눈 지지대와 링크의 옆 나사를 먼저 확인합니다.",
    cut: ["y", 22.98], checked: true, wiring: true,
  },
  {
    id: "complete", group: "턱·외장", title: "조립 완료 · 체결과 배선", base: "Part000",
    moves: [], focus: [0, 1, 58], view: [1.15, -1.45, .8], span: 325,
    task: "기본 체결품 140개와 체결 길이를 확인 중인 원통머리 18곳, 내부 전선 32가닥을 표시합니다.",
    check: "목 좌우 ±60°에서 회전판 아래 볼트와 모터 사이 최소 간격은 0.70 mm입니다.",
    note: "구동 검토에서 배선과 체결품을 표시한 채 눈·목·턱을 움직일 수 있습니다.",
    inspectFasteners: true, wiring: true, checked: true, status: "CAD 조립 상태",
  },
];

const joints = {
  "cable-plugs": [["CableSaddle", cablePlugs]],
  "xt60-mate": [["InputXT60", "InputXT60Mate"]],
  "hub-wiring": [["HubPCB", hubPlugs]],
  "hatch-nuts": [["HubHolder", `${names(hatchNuts)} ${names(hatchBolts)}`]],
  "hub-nuts": [["HubHolder", `${names(hubNuts)} ${names(hubBolts)}`]],
  "hub-board": [["HubHolder", PCB]],
  "hatch-fit": [["Part000", "HubHolder"]],
  "cable-tray": [["Part000", "CableSaddle"]],
  "cable-tray-fasteners": [["CableSaddle", `${names(clipBolts)} ${names(clipNuts)} ${names(clipWashers)}`]],
  "cable-nuts": [["CableGate", `${names(cableNuts)} ${names(cableBolts)}`]],
  "cable-cover": [["CableSaddle", "CableGate"]],
  "base-boards": [["Part000", "Part071"]],
  "carrier-bolts": [["Part071", `${names(c3CarrierBolts)} ${names(c3CarrierNuts)}`]],
  "boards-fit": [["Part071", "Part070"]],
  "c3-bolts": [["Part071", `${names(c3Bolts)} ${names(c3Nuts)}`]],
  "openrb-carrier": [["Part000", "Part072"]],
  "openrb-carrier-bolts": [["Part072", `${names(openrbCarrierBolts)} ${names(openrbCarrierNuts)}`]],
  "openrb-usb": [["Part069", "OpenRBUSB"]],
  "openrb-board": [["Part072", "Part069"]],
  "openrb-bolts": [["Part072", `${names(openrbBolts)} ${names(openrbNuts)}`]],
  "yaw-motor": [["Part000", "Part008 Part009 Part017"]],
  "keeper-nuts": [["Part001", `${names(keeperNuts)} ${names(keeperBolts)}`]],
  "bearing-seat": [["Part000", "Part001"]],
  "bearing-seat-bolts": [["Part001", `${names(seatBolts)} ${names(seatNuts)}`]],
  "yaw-bearing": [["Part001", "Part006"]],
  "yaw-keepers": [["Part001", keepers]],
  "rotor-nuts": [["Part007", `${names(rotorNuts)} ${names(mastStuds)}`]],
  "rotor": [["Part006", "Part007"]],
  "rotor-horn": [["Part007", names(hornBolts)]],
  "base-deck": [["Part000", "Part002"]],
  "base-deck-bolts": [["Part002", `${names(lidBolts)} ${names(lidNuts)}`]],
  "mast": [["Part007", "Part010"]],
  "mast-bolts": [["Part010", names(mastNuts)]],
  "yoke-nuts": [["Part011", `${names(yokeNuts)} ${names(yokeBolts)}`]],
  "yoke-fit": [["Part010", "Part011"]],
  "pitch-horn": [["Part018", "Part016"], ["Part016", names(pitchHornBolts)]],
  "pitch-drive": [["Part011", "Part018"]],
  "pitch-bearing": [["Part011", "Part012 Part014"]],
  "head-frame": [["Part011", "Part019"]],
  "neck-pins": [["Part019", "Part013 Part015"]],
  "eye-pins": [["Part024", "Part029 Part030 Part031 Part032 Part033 Part034 Part035 Part036"]],
  "eye-pin": [["Part024", "Part025 Part026 Part027 Part028"]],
  "eye-yaw-motor-heads": [["Part039", `Part038 ${names(eyeYawHeads)}`]],
  "eye-module": [["Part019", "Part024"], ["Part024", "Part037 Part039 Part040"]],
  "eye-pitch-stay": [["Part019", "Part064"]],
  "eye-pitch-motor-heads": [["Part042", `Part041 ${names(eyePitchHeads.filter(head => head.size === 2))}`]],
  "eye-pitch-horn": [["Part041", "Part043"]],
  "eye-pitch-motor-fit": [["Part064", "Part042"]],
  "eye-pitch-plate-heads": [["Part042", names(eyePitchHeads.filter(head => head.size === 3))]],
  "eye-pitch-link": [["Part041", "Part044"]],
  "lids": [["Part076", "Part078 Part058 Part061"]],
  "right-lid": [["Part077", "Part079 Part059 Part062"]],
  "blink-bearings": [["Part063", "Part050 Part052"]],
  "blink-clamps": [["Part053", "crankNut0 crankBolt0"], ["Part054", "crankNut1 crankBolt1"], ["Part055", "crankNut2 crankBolt2"]],
  "blink-shaft": [["Part063", "Part048"], ["Part048", "BlinkCollarLeft BlinkCollarRight"]],
  "blink-outer-cranks": [["Part048", "Part053 Part055"]],
  "blink-motor-heads": [["Part046", `Part045 ${names(blinkMotorHeads)}`]],
  "blink-rail": [["Part019", "Part063"]],
  "blink-rail-bolts": [["Part063", `${names(railBolts)} ${names(railNuts)}`]],
  "blink-horn-nut": [["Part047", "Part056 middleNut0 middleServo0 middleWasher0"]],
  "blink-center-link": [["Part056", "Part054 centerLink0 linkNutPos0 linkWasherPos0"]],
  "blink-motor-fit": [["Part063", "Part046"], ["Part045", "Part047"]],
  "blink-motor-fasteners": [["Part046", `${names(blinkPlateBolts)} ${names(blinkPlateNuts)}`]],
  "blink-upper-links": [["Part063", `Part057 Part060 ${names(upperLinkBolts)} ${upperLinkWasherIds} linkNutPos1 linkNutNeg0`]],
  "jaw-motor-heads": [["Jaw_36_left_jaw_servo_stay", `Jaw_XL330_M288_Jaw ${names(jawHeads)}`]],
  "jaw-fit": [["Jaw_36_left_jaw_servo_stay", jaw.replace("Jaw_36_left_jaw_servo_stay ", "").replace(" Jaw_XL330_M288_Jaw", "")]],
  "camera-fit": [["Part073", camera]],
  "front-orbit": [["Part073", "Part076 Part077"]],
  "front-shell": [["Part019", "Part073"]],
  "blink-lower-nuts": [["Part073", `${lowerLinkWasherIds} linkLeftLowerNut0 linkRightLowerNut0`]],
  "blink-links": [["Part073", names(lowerLinkBolts)]],
  "jaw-to-shell": [["Part073", "Jaw_36_left_jaw_servo_stay"]],
  "rear-shell": [["Part019", "Part074"]],
};

const assembly = withAssemblyState(definitions, joints, hardware);
export const steps = assembly.stages;

const jointMotion = new Map([
  [names(mastNuts), "pan"],
  ["middleServo0 middleNut0 middleWasher0", "blink_motor_horn"],
  ["centerLink0 linkNutPos0 linkWasherPos0", "blink_shaft_crank"],
  ["centerLink1 rightLink0 linkNutPos1 linkNutNeg0 " + upperLinkWasherIds, "blink_shaft_crank"],
  ["centerLower0 linkLeftLowerNut0 linkWasherPos2", "lid1"],
  ["rightLower0 linkRightLowerNut0 linkWasherNeg1", "lid2"],
  [names(hatchNuts) + " " + names(hatchBolts), "fixed"],
].flatMap(([list, motion]) => ids(list).map(id => [id, motion])));

export function installedHardware(cadParts) {
  const parts = new Map(cadParts.map(part => [part.cad_id, part]));
  return hardware.filter(part => !part.tool).map(part => {
    const parent = parts.get(assembly.parents.get(part.id));
    if (!parent) throw Error(`Missing motion parent for ${part.id}`);
    return {
      ...part, parent: parent.cad_id, motion: jointMotion.get(part.id) || parent.motion,
      cover: parent.cover && /^(Part00[12])$/.test(parent.cad_id),
    };
  });
}
