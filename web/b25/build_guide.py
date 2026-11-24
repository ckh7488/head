"""Build the B25 overview and human-facing guide for the static site."""

from argparse import ArgumentParser
from html import escape, unescape
from pathlib import Path
from shutil import copyfile
from subprocess import check_output
from urllib.parse import quote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
B25 = ROOT / "mechanical/revisions/b25"
A5_VIEWER = HERE / "R5-B25-A5.html"
DOCS = {
    "start": ("제작 순서", B25 / "README.md"),
    "print": ("출력과 후가공", B25 / "01-seoul-print.md"),
    "before": ("먼저 살 부품", B25 / "02-order-before.md"),
    "gauge": ("맞춤 게이지", B25 / "fit-gauge.md"),
    "after": ("시험 뒤 살 부품", B25 / "03-order-after.md"),
    "assembly": ("조립 절차", B25 / "assembly.md"),
    "electronics": ("A5 발주·첫 통전", ROOT / "electronics/README.md"),
    "service": ("J2 잠금·정비", B25 / "j2-disconnect.md"),
    "control": ("구동과 보정", ROOT / "control/README.md"),
    "bench": ("실물 시험", ROOT / "spec/bench.md"),
    "records": ("검수 기록", ROOT / "spec/records/README.md"),
    "status": ("검사 결과와 범위", B25 / "alignment.md"),
    "intent": ("사람 요구사항", ROOT / "spec/user-spec.md"),
    "conditions": ("검사 조건", ROOT / "spec/conditions.md"),
    "requirements": ("동작 인수 기준", ROOT / "spec/requirements.md"),
}
NAV_GROUPS = (
    ("제작", ("start", "print", "before", "gauge", "after", "assembly")),
    ("통전·구동", ("electronics", "service", "control", "bench", "records")),
    ("판정과 기준", ("status", "intent", "conditions", "requirements")),
)
ROUTE = {path: name for name, (_, path) in DOCS.items()}
ROUTE[B25] = "start"
LINK = re.compile(r'\b(href|src)="([^"]+)"')
MEDIA = {".svg", ".png", ".jpg", ".jpeg", ".webp"}


def local_links(body, document, hosted_path, ref, output):
    def rewrite(match):
        attribute, url = match.groups()
        parts = urlsplit(unescape(url))
        if parts.scheme or parts.netloc or not parts.path:
            return match[0]
        path = (document.parent / parts.path).resolve()
        relative = path.relative_to(ROOT).as_posix()
        slug = ROUTE.get(path)
        if attribute == "src" and path.suffix.lower() in MEDIA and path.is_file():
            media = output / "guide" / "media" / relative
            media.parent.mkdir(parents=True, exist_ok=True)
            copyfile(path, media)
            location = f"{hosted_path}guide/media/{quote(relative)}"
        elif path == A5_VIEWER:
            location = f"{hosted_path}a5/"
        elif slug:
            location = f"{hosted_path}guide/{slug}/"
        else:
            if path.suffix in (".3mf", ".FCStd", ".zip", ".step", ".svg", ".png", ".jpg", ".webp"):
                location = f"https://raw.githubusercontent.com/ckh7488/head/{ref}/{quote(relative)}"
            else:
                route = "tree" if path.is_dir() else "blob"
                location = f"https://github.com/ckh7488/head/{route}/{ref}/{quote(relative)}"
        if parts.fragment:
            location += "#" + parts.fragment
        return f'{attribute}="{escape(location, quote=True)}"'

    return LINK.sub(rewrite, body)


def sheet(title, body, prefix, ref, current=""):
    groups = []
    for label, slugs in NAV_GROUPS:
        links = "".join(
            f'<a href="{prefix}guide/{slug}/"'
            + (' aria-current="page"' if slug == current else "")
            + f">{escape(DOCS[slug][0])}</a>"
            for slug in slugs
        )
        groups.append(f'<nav class="guide-nav" aria-label="{label}">{links}</nav>')
    nav = "".join(groups)
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · R5 B25</title>
<link rel="stylesheet" href="{prefix}review.css">
</head>
<body>
<header class="bar">
  <a class="brand" href="{prefix}">R5 <span>B25</span></a>
  <nav aria-label="보기 선택">
    <a href="{prefix}demo/">구동</a><a href="{prefix}assembly/">조립</a>
    <a href="{prefix}wiring/diagram/">배선도</a><a href="{prefix}guide/" aria-current="page">문서</a>
  </nav>
</header>
<main class="container guide">
  <div class="guide-header">{nav}</div>
  <article>{body}</article>
  <footer class="guide-footer"><a href="https://github.com/ckh7488/head/tree/{quote(ref)}">이 안내의 저장소 버전</a></footer>
</main>
</body>
</html>
'''


def build(output, poster, ref, offline=None):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "review.css"):
        copyfile(HERE / name, output / name)
    copyfile(poster, output / "r5-b25.webp")
    (output / "a5").mkdir(exist_ok=True)
    copyfile(A5_VIEWER, output / "a5" / "index.html")
    if offline:
        with ZipFile(output / "assembly-offline.zip", "w", ZIP_DEFLATED) as archive:
            archive.write(offline, "R5-B25-assembly.html")
    guide = output / "guide"
    guide.mkdir(exist_ok=True)
    for slug, (title, path) in DOCS.items():
        page = guide / slug
        page.mkdir(exist_ok=True)
        fragment = check_output(
            ["pandoc", "--from=gfm", "--to=html5", "--wrap=none", str(path)],
            cwd=ROOT, text=True,
        )
        fragment = fragment.replace("<table>", '<div class="guide-table" tabindex="0"><table>')
        fragment = fragment.replace("</table>", "</table></div>")
        if slug == "start":
            intro = local_links(fragment, path, "../", ref, output)
            if offline:
                intro += '<p><a href="../assembly-offline.zip" download>오프라인 조립 HTML 내려받기</a></p>'
            (guide / "index.html").write_text(sheet(title, intro, "../", ref, slug), encoding="utf-8")
        body = local_links(fragment, path, "../../", ref, output)
        (page / "index.html").write_text(
            sheet(title, body, "../../", ref, slug), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--poster", type=Path, default=ROOT / "web/assets/b25-motion/assembly-poster.webp")
    parser.add_argument("--offline", type=Path)
    parser.add_argument("--ref", default="fix/r5-b24-final-validation")
    args = parser.parse_args()
    build(args.output, args.poster, args.ref, args.offline)
