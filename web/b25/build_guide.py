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
DOCS = {
    "assembly": ("조립 절차", B25 / "assembly.md"),
    "print": ("서울 시험 출력", B25 / "01-seoul-print.md"),
    "before": ("먼저 살 부품", B25 / "02-order-before.md"),
    "after": ("시험 뒤 살 부품", B25 / "03-order-after.md"),
    "gauge": ("맞춤 게이지", B25 / "fit-gauge.md"),
    "electronics": ("전원과 배선", ROOT / "electronics/README.md"),
    "control": ("구동과 보정", ROOT / "control/README.md"),
    "bench": ("실물 시험", ROOT / "spec/bench.md"),
    "status": ("B25 판정", B25 / "frozen-fixes-check.md"),
}
ROUTE = {path: name for name, (_, path) in DOCS.items()}
LINK = re.compile(r'\b(href|src)="([^"]+)"')


def local_links(body, document, hosted_path, ref):
    def rewrite(match):
        attribute, url = match.groups()
        parts = urlsplit(unescape(url))
        if parts.scheme or parts.netloc or not parts.path:
            return match[0]
        path = (document.parent / parts.path).resolve()
        relative = path.relative_to(ROOT).as_posix()
        slug = ROUTE.get(path)
        if slug:
            location = f"{hosted_path}guide/{slug}/"
        else:
            route = "tree" if path.is_dir() else "blob"
            if path.suffix in (".3mf", ".FCStd", ".zip", ".step", ".svg", ".png", ".jpg", ".webp"):
                route = "raw"
            location = f"https://github.com/ckh7488/head/{route}/{ref}/{quote(relative)}"
        if parts.fragment:
            location += "#" + parts.fragment
        return f'{attribute}="{escape(location, quote=True)}"'

    return LINK.sub(rewrite, body)


def sheet(title, body, prefix, current=""):
    nav = "".join(
        f'<a href="{prefix}guide/{slug}/"'
        + (' aria-current="page"' if slug == current else "")
        + f">{escape(name)}</a>"
        for slug, (name, _) in DOCS.items()
    )
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
    <a href="{prefix}wiring/">배선</a><a href="{prefix}guide/" aria-current="page">문서</a>
  </nav>
</header>
<main class="container guide">
  <div class="guide-header"><nav class="guide-nav" aria-label="문서 선택">{nav}</nav></div>
  <article>{body}</article>
</main>
</body>
</html>
'''


def build(output, poster, ref, offline=None):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "review.css"):
        copyfile(HERE / name, output / name)
    copyfile(poster, output / "r5-b25.webp")
    if offline:
        with ZipFile(output / "assembly-offline.zip", "w", ZIP_DEFLATED) as archive:
            archive.write(offline, "R5-B25-assembly.html")
    guide = output / "guide"
    guide.mkdir(exist_ok=True)
    intro = """<h1>B25 제작 문서</h1>
<p>서울 시험 출력과 맞춤 게이지부터 시작합니다. 건식 조립에서 위치와 간극을 확인한 다음 모터와 전장을 준비하세요.</p>
<div class="document-links">
<a href="print/">서울 시험 출력</a><a href="before/">먼저 살 부품</a>
<a href="after/">시험 뒤 살 부품</a><a href="assembly/">조립 절차</a>
</div>"""
    if offline:
        intro += '<p><a href="../assembly-offline.zip" download>오프라인 조립 HTML 내려받기</a></p>'
    (guide / "index.html").write_text(sheet("제작 문서", intro, "../"), encoding="utf-8")
    for slug, (title, path) in DOCS.items():
        page = guide / slug
        page.mkdir(exist_ok=True)
        fragment = check_output(
            ["pandoc", "--from=gfm", "--to=html5", "--wrap=none", str(path)],
            cwd=ROOT, text=True,
        )
        fragment = fragment.replace("<table>", '<div class="guide-table" tabindex="0"><table>')
        fragment = fragment.replace("</table>", "</table></div>")
        fragment = local_links(fragment, path, "../../", ref)
        (page / "index.html").write_text(
            sheet(title, fragment, "../../", slug), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--poster", type=Path, default=ROOT / "web/assets/b25-motion/assembly-poster.webp")
    parser.add_argument("--offline", type=Path)
    parser.add_argument("--ref", default="fix/r5-b24-final-validation")
    args = parser.parse_args()
    build(args.output, args.poster, args.ref, args.offline)
