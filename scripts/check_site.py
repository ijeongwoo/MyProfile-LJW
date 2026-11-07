import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

PUBLIC = Path("public")


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids, self.imgs_no_alt = [], set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key) is not None and not (tag == "link" and a.get("rel") in ("canonical", "alternate")):
                self.refs.append((tag, key, a[key]))
        if tag == "img" and "alt" not in a:
            self.imgs_no_alt.append(a.get("src", "?"))


def page_url(base, html_file):
    rel = html_file.relative_to(PUBLIC.resolve()).as_posix()
    rel = rel[: -len("index.html")] if rel.endswith("index.html") else rel
    return urljoin(base, rel)


def target_file(base_path, path):
    path = unquote(path)
    if not path.startswith(base_path):
        return None
    local = PUBLIC / path[len(base_path):]
    if path.endswith("/") or local.is_dir():
        local = local / "index.html"
    return local


def exists_exact(path):
    path = path.resolve()
    root = PUBLIC.resolve()
    if not path.exists():
        return False
    for part in path.relative_to(root).parts:
        if part not in [p.name for p in root.iterdir()]:
            return False
        root = root / part
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit("사용법: python scripts/check_site.py https://내아이디.github.io/")
    base = sys.argv[1].rstrip("/") + "/"
    base_host, base_path = urlparse(base).netloc, urlparse(base).path
    if not PUBLIC.is_dir():
        sys.exit("public/ 폴더가 없습니다. 먼저 hugo 로 빌드하세요.")
    pages = {}
    for f in PUBLIC.rglob("*.html"):
        c = Collector()
        c.feed(f.read_text(encoding="utf-8", errors="replace"))
        pages[f.resolve()] = c
    problems = []
    for f, c in pages.items():
        here = page_url(base, f)
        name = f.relative_to(PUBLIC.resolve()).as_posix()
        for src in c.imgs_no_alt:
            problems.append((name, "alt 없음", src))
        for tag, key, ref in c.refs:
            low = ref.strip().lower()
            if low in ("", "#") and tag == "a":
                problems.append((name, "빈 링크", repr(ref)))
                continue
            if low.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            if any(s in low for s in ("localhost", "127.0.0.1", "file:", "c:/", "c:\\")):
                problems.append((name, "개인 PC 주소", ref))
                continue
            u = urlparse(urljoin(here, ref))
            if u.scheme == "http":
                problems.append((name, "HTTP(혼합 콘텐츠 위험)", ref))
            if u.netloc != base_host:
                continue
            t = target_file(base_path, u.path)
            if t is None:
                problems.append((name, "사이트 경로 밖(앞의 / 확인)", ref))
            elif not exists_exact(t):
                problems.append((name, "없는 파일(404)", ref))
            elif u.fragment and t.suffix == ".html":
                c2 = pages.get(t.resolve())
                if c2 and unquote(u.fragment) not in c2.ids:
                    problems.append((name, "없는 앵커", ref))
    for p in sorted(set(problems)):
        print(" | ".join(p))
    print(f"\n검사한 페이지 {len(pages)}개, 문제 {len(set(problems))}건")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
