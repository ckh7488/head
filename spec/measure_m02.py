"""Read support spans in the released B22 CAD with FreeCAD's Python module."""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from math import atan2, dist, pi
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
CAD_SOURCE = Path("mechanical/revisions/b22/R5-B22-Assembly.FCStd")
TOLERANCE_MM = 0.0001


def cylindrical_bands(doc, name, axis, cross_section, radius):
    """Find cylindrical faces at the stated centerline and project along it."""
    from export_cad import world_shape

    bands = []
    for face in world_shape(doc.getObject(name)).Faces:
        surface = face.Surface
        if surface.__class__.__name__ != "Cylinder" or abs(surface.Axis[axis]) < 0.999:
            continue
        cross = [value for i, value in enumerate(surface.Center) if i != axis]
        if abs(radius - surface.Radius) >= TOLERANCE_MM or dist(cross, cross_section) >= TOLERANCE_MM:
            continue
        face_range = face.BoundBox
        spans = ((face_range.XMin, face_range.XMax), (face_range.YMin, face_range.YMax),
                 (face_range.ZMin, face_range.ZMax))
        bands.append(spans[axis])
    merged = []
    for low, high in sorted(bands):
        if merged and low <= merged[-1][1] + TOLERANCE_MM:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    if not merged:
        raise ValueError(f"{name}: support geometry not found")
    return merged


def overlapping_centers(faces, journal):
    centers = []
    for start, end in faces:
        for low, high in journal:
            left, right = max(start, low), min(end, high)
            if right - left > TOLERANCE_MM:
                centers.append((left + right) / 2)
    return centers


def centers(faces):
    return [(low + high) / 2 for low, high in faces]


def span_row(description, seats, diameter):
    if len(seats) != 2:
        raise ValueError(f"{description}: two distinct supported locations are required")
    low, high = sorted(seats)
    if high - low <= TOLERANCE_MM:
        raise ValueError(f"{description}: supported locations coincide")
    location = f"{description}, 축 좌표 {low:.3f} mm와 {high:.3f} mm"
    return [
        dict(name=name, value=round(value, 5), unit=unit, source=str(CAD_SOURCE), location=location)
        for name, value, unit in (
            ("shaft_diameter", diameter, "mm"),
            ("support_span", high - low, "mm"),
            ("support_span_to_shaft_diameter", (high - low) / diameter, "ratio"),
        )
    ]


def eyelid_land(doc, lid, intervals):
    """Read each complete rim of the polygonal bore on the Ø2 mm pin line."""
    from export_cad import world_mesh

    points = [tuple(point.Vector) for point in world_mesh(doc.getObject(lid)).Points]
    seats = []
    for low, high in intervals:
        rings = {}
        for x, y, z in points:
            radial = dist((y, z), (-39., 119.))
            if low <= x <= high and abs(radial - 1.12) < TOLERANCE_MM:
                rings.setdefault(round(x, 3), set()).add(atan2(z - 119., y + 39.))
        qualified = []
        for station, angles in rings.items():
            ordered = sorted(angles)
            gaps = [b - a for a, b in zip(ordered, ordered[1:])]
            gaps.append(2 * pi + ordered[0] - ordered[-1])
            if max(gaps) < pi / 4:
                qualified.append(station)
        if len(qualified) != 1:
            raise ValueError(f"{lid}: cannot identify one bore rim on the supported pin")
        seats.extend(qualified)
    return seats


def measured_case(rows, limit):
    minimum = min(row["value"] for row in rows if row["name"] == "support_span_to_shaft_diameter")
    status = "PASS" if minimum >= limit else "FAIL"
    return dict(status=status, measurements=rows)


def check_native(doc, cad_hash, limit):
    from export_cad import world_shape

    pitch = [v for name in ("Part012", "Part014")
             for v in centers(cylindrical_bands(doc, name, 0, (0., 112.), 4.))]
    shaft = [v for name in ("Part050", "Part052")
             for v in centers(cylindrical_bands(doc, name, 0, (-24., 154.), 2.))]
    blink = span_row("공통 눈꺼풀 축, MR104 Part050·Part052 내륜 중심", shaft, 4.)
    for lid, pins in (("Part078", ("Part058", "Part061")), ("Part079", ("Part059", "Part062"))):
        bands = [band for pin in pins for band in cylindrical_bands(doc, pin, 0, (-39., 119.), 1.)]
        blink += span_row(f"{lid} 눈꺼풀 보어 테두리, 핀 {'·'.join(pins)} 범위 안", eyelid_land(doc, lid, bands), 2.)

    eye_yaw = []
    for x, eye, pin in ((-34., "Part029", "Part032"), (34., "Part033", "Part036")):
        line = (x, -39.)
        journal = cylindrical_bands(doc, pin, 2, line, 1.)
        for name in ("Part024", eye):
            contact = overlapping_centers(cylindrical_bands(doc, name, 2, line, 1.13), journal)
            eye_yaw += span_row(f"{name} Ø2.26 CAD 보어와 {pin} Ø2 핀의 지지 구간 중심", contact, 2.)
    eye_pitch = []
    for pin in ("Part026", "Part028"):
        journal = cylindrical_bands(doc, pin, 0, (-39., 119.), 1.5)
        cradle_band = cylindrical_bands(doc, "Part024", 0, (-39., 119.), 1.62)
        eye_pitch.extend(overlapping_centers(cradle_band, journal))

    vendor = cylindrical_bands(doc, "Jaw_XL330_M288_Jaw", 0, (-9., 92.), 8.)
    right = cylindrical_bands(doc, "Jaw_MR104ZZ_jaw_right", 0, (-9., 92.), 2.)
    jaw_pin = cylindrical_bands(doc, "Jaw_Pin_jaw_4x10", 0, (-9., 92.), 2.)
    left_face = min(low for low, _ in vendor)
    jaw = [left_face, *overlapping_centers(right, jaw_pin)]
    yaw = world_shape(doc.getObject("Part006")).BoundBox
    if abs(yaw.XLength - 100.) >= TOLERANCE_MM or abs(yaw.ZLength - 10.) >= TOLERANCE_MM:
        raise ValueError("Part006: check the integral yaw bearing specification")

    cases = {
        "neck_yaw": {
            "status": "N/A",
            "reason": "Part006 6816-2RS (80×100×10 mm)의 원주 베어링과 동축 혼 구조. 두 축 방향 지지점 간격 대신 구매 베어링의 모멘트 하중·기울기·수명으로 확인.",
        },
        "neck_pitch": measured_case(span_row("Part012·Part014 688 내륜 중심", pitch, 8.), limit),
        "jaw": measured_case(span_row("왼쪽 XL330 출력 플랜지 외측 면과 오른쪽 MR104·핀 지지 중심. 구매품 내부 지지 구조 및 수명은 별도", jaw, 4.), limit),
        "blink": measured_case(blink, limit),
        "eye_yaw": measured_case(eye_yaw, limit),
        "eye_pitch": measured_case(span_row("Part024 양쪽 보어와 Part026·Part028 Ø3 핀의 실제 겹침 중심", eye_pitch, 3.), limit),
        "cable_retention": {
            "status": "N/A",
            "reason": "고정 타이 받침에는 회전축이 없습니다. 회전판 열린 가이드에서는 케이블 피복이 미끄러집니다.",
        },
    }
    status = "FAIL" if any(case["status"] == "FAIL" for case in cases.values()) else "PASS"
    return dict(revision="B22", cad_sha256=cad_hash, status=status, cases=cases)


def main():
    import FreeCAD as App

    sys.path.insert(0, str(ROOT / "mechanical/physics"))
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cad = ROOT / CAD_SOURCE
    with cad.open("rb") as source:
        cad_hash = file_digest(source, "sha256").hexdigest()
    with (ROOT / "spec/criteria.toml").open("rb") as source:
        limit = tomllib.load(source)["M02_support"]["minimum_span_to_diameter"]
    doc = App.openDocument(str(cad))
    try:
        result = check_native(doc, cad_hash, limit)
    finally:
        App.closeDocument(doc.Name)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
