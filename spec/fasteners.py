"""Check the stock fastener policy against the typed bill of materials."""

import csv
from hashlib import file_digest
import json
import re
from pathlib import Path


COLUMNS = ("번호", "구분", "품목", "규격·품번", "사용 위치")
ROLES = {
    "나사": "screw",
    "볼트": "screw",
    "너트": "nut",
    "와셔": "washer",
}
STANDARDS = {
    "ISO 4762": ("screw", r"원통\s*머리|socket[ -]head[ -]cap|\bSHCS\b"),
    "DIN 934": ("nut", r"육각\s*너트|hex(?:agon)?[ -]nut"),
    "DIN 125": ("washer", r"평\s*와셔|flat[ -]washer|plain[ -]washer"),
    "ISO 4026": ("screw", r"(?:평끝.*무두나사|무두나사.*평끝)|flat[ -]point.*set[ -]screw"),
}
THREAD = re.compile(r"(?<![A-Za-z0-9])M\d+(?:\.\d+)?(?![\d.])", re.IGNORECASE)
INTERFACE = re.compile(r"\s+·\s+")
HARDWARE_WORD = re.compile(
    r"원통\s*머리|접시\s*머리|무두\s*나사|볼트|육각\s*너트|평\s*와셔|"
    r"(?:나사|너트|와셔)(?:\s|$)|"
    r"\b(?:screw|bolt|nut|washer)\b",
    re.IGNORECASE,
)
NONSTANDARD_FORM = re.compile(
    r"접시|둥근\s*머리|버튼\s*머리|카운터싱크|countersunk|flat[ -]head|"
    r"button[ -]head|ISO\s*(?:10642|7380)\b|DIN\s*7991\b|"
    r"나일론|플랜지|스프링\s*와셔|spring[ -]washer|nyloc|lock[ -]?nut",
    re.IGNORECASE,
)


def normalized(value: str) -> str:
    return " ".join(value.split())


def read_policy(criteria: dict) -> tuple[set[str], str, dict]:
    policy = criteria["S06_fasteners"]
    standards = policy["allowed_standards"]
    size = policy["default_size"]
    exceptions = policy.get("exceptions", {})
    if (
        not isinstance(standards, list)
        or not standards
        or any(s not in STANDARDS or s == "ISO 4026" for s in standards)
        or not isinstance(size, str)
        or not THREAD.fullmatch(size)
        or not isinstance(exceptions, dict)
    ):
        raise ValueError("표준·기본 호칭·예외 설정 형식이 올바르지 않음")
    for item_id, rule in exceptions.items():
        if not isinstance(rule, dict) or set(rule) - {"size", "standard", "interfaces"}:
            raise ValueError(f"{item_id}: 예외 설정 형식이 올바르지 않음")
        interfaces = rule.get("interfaces")
        if (
            not isinstance(interfaces, list)
            or not interfaces
            or any(not isinstance(site, str) or not normalized(site) for site in interfaces)
            or len({normalized(site) for site in interfaces}) != len(interfaces)
            or not ({"size", "standard"} & rule.keys())
            or "size" in rule and (
                not isinstance(rule["size"], str) or not THREAD.fullmatch(rule["size"])
            )
            or "standard" in rule and rule["standard"] not in STANDARDS
        ):
            raise ValueError(f"{item_id}: 적용 위치와 허용 호칭 또는 표준을 명시해야 함")
    return set(standards), size.upper(), exceptions


def check_guard(root, policy):
    release = root / "mechanical/revisions/b22"
    try:
        layout = json.loads((release / "guard-layout.json").read_bytes())
        verification = json.loads((release / "verification.json").read_bytes())
        with (release / "R5-B22-Assembly.FCStd").open("rb") as file:
            cad_hash = file_digest(file, "sha256").hexdigest()
        rows = layout["fasteners"]
        count = verification["guard"]["fastener_tool_pairs"]
        expected = policy["guard"]
        if (cad_hash != layout["source_sha256"] or cad_hash != verification["cad_sha256"]
                or not count or len(rows) != count or len({row["id"] for row in rows}) != count):
            return "UNVERIFIED", "보호 케이스 체결 자료와 CAD 또는 체결 위치 수가 다름"
        wrong = [row["id"] for row in rows if any(row[key] != expected[key] for key in ("screw", "nut"))]
    except (OSError, ValueError, TypeError, KeyError) as error:
        return "UNVERIFIED", f"보호 케이스 체결 자료를 읽을 수 없음 ({error})"
    if wrong:
        return "FAIL", f"보호 케이스 체결 규격 불일치 ({', '.join(wrong)})"
    return "PASS", f"케이스 체결 {count}쌍 확인"


def check_fasteners(root: Path, criteria: dict) -> tuple[str, str]:
    """Return the outcome and detail for S06."""
    try:
        standards, default_size, exceptions = read_policy(criteria)
        with (root / "mechanical" / "BOM.csv").open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if not set(COLUMNS) <= set(reader.fieldnames or ()):
                return "UNVERIFIED", "BOM의 번호·구분·품목·규격·사용 위치 열을 확인할 수 없음"
            rows = list(reader)
    except (csv.Error, OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        return "UNVERIFIED", f"S06 입력을 읽을 수 없음 ({error})"

    checked = set()
    violations = []
    for row in rows:
        if None in row or any(row[column] is None for column in COLUMNS):
            return "UNVERIFIED", "BOM에 필드 수가 맞지 않는 행이 있음"
        item_id, category, item, standard, location = (
            normalized(row[column]) for column in COLUMNS
        )
        role = ROLES.get(category)
        if not role:
            if (
                category in {"체결", "체결품", "스크류", "피스"}
                or HARDWARE_WORD.search(item)
                or standard in STANDARDS
            ):
                violations.append(f"{item_id}: 체결품 구분 {category} 확인 필요")
            continue
        if not item_id or item_id in checked:
            violations.append(f"{item_id or '번호 없음'}: BOM 체결품 번호 중복 또는 누락")
            continue
        checked.add(item_id)

        rule = exceptions.get(item_id, {})
        sites = INTERFACE.split(location)
        if not location:
            violations.append(f"{item_id}: 사용 위치 누락")
        if rule and set(sites) != {normalized(site) for site in rule["interfaces"]}:
            violations.append(f"{item_id}: 예외 사용 위치와 BOM 불일치 ({location})")
        allowed_size = rule.get("size", default_size).upper()
        sizes = {match.upper() for match in THREAD.findall(item)}
        if sizes != {allowed_size}:
            violations.append(f"{item_id}: {item} / 허용 호칭 {allowed_size}")
        expected_role, item_pattern = STANDARDS.get(standard, ("", ""))
        allowed = (
            standard == rule["standard"] if "standard" in rule else standard in standards
        )
        if (
            not allowed
            or role != expected_role
            or not re.search(item_pattern, item, re.IGNORECASE)
            or NONSTANDARD_FORM.search(item)
        ):
            violations.append(f"{item_id}: 허용되지 않은 형식 또는 표준 ({item}, {standard})")

    unused = sorted(exceptions.keys() - checked)
    if unused:
        violations.append(f"BOM에 없는 예외 품목 {', '.join(unused)}")
    if violations:
        return "FAIL", " / ".join(violations)
    if not checked:
        return "UNVERIFIED", "BOM에서 확인할 체결품을 찾지 못함"
    status, guard = check_guard(root, criteria["S06_fasteners"])
    return status, f"본체 BOM 체결품 {len(checked)}개 품목 확인 · {guard}"
