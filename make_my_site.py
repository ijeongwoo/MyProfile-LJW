import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from datetime import date
from pathlib import Path

ROOT = Path.cwd()
SITE = ROOT / "site" if (ROOT / "site" / "hugo.toml").exists() else ROOT
CLASS_SETUP = SITE != ROOT
CONTENT = SITE / "content" / "english"
CONFIG = SITE / "config" / "_default"
IMAGES = SITE / "assets" / "images"

CHECK_SITE = r'''import sys
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
'''

KO_UI = {
    "read more": "더 보기",
    "related posts": "관련 글",
    "related post": "관련 글",
    "recent posts": "최근 글",
    "recent post": "최근 글",
    "categories": "카테고리",
    "category": "카테고리",
    "tags": "태그",
    "tag": "태그",
    "back to home": "홈으로",
    "back home": "홈으로",
    "page not found": "페이지를 찾을 수 없습니다",
    "search": "검색",
    "share": "공유",
    "previous": "이전",
    "next": "다음",
    "home": "홈",
    "posts": "글",
    "posts by": "작성한 글",
    "author": "작성자",
    "authors": "작성자",
    "all": "전체",
    "contact": "연락처",
    "submit": "보내기",
    "no results found": "검색 결과가 없습니다",
    "table of contents": "목차",
}


def ask(label, default=""):
    shown = f" [{default}]" if default else ""
    value = input(f"{label}{shown}: ").strip()
    return value or default


def run(cmd, check=True, quiet=False, cwd=None):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not quiet and r.stdout.strip():
        print(r.stdout.strip())
    if check and r.returncode != 0:
        print(r.stderr.strip())
        sys.exit(f"명령 실패: {cmd}")
    return r


def read(p):
    return Path(p).read_text(encoding="utf-8")


def write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def toml_str(s):
    return json.dumps(s, ensure_ascii=False)


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#")) + "\n"


def set_toml(text, section, key, literal):
    lines = text.splitlines()
    header = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*$")
    start, end = 0, len(lines)
    if section:
        start = None
        for i, l in enumerate(lines):
            m = header.match(l)
            if m and m.group(1).strip() == section and not l.strip().startswith("[["):
                start = i + 1
                break
        if start is None:
            lines += ["", f"[{section}]", f"{key} = {literal}"]
            return "\n".join(lines) + "\n"
    for j in range(start, len(lines)):
        if header.match(lines[j]):
            end = j
            break
    keyre = re.compile(rf"^(\s*){re.escape(key)}\s*=")
    for j in range(start, end):
        m = keyre.match(lines[j])
        if m:
            lines[j] = f"{m.group(1)}{key} = {literal}"
            return "\n".join(lines) + "\n"
    lines.insert(start if section else 0, f"{key} = {literal}")
    return "\n".join(lines) + "\n"


def png(path, w, h, c1, c2):
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            t = (x + y) / (w + h - 2)
            rows += bytes(int(a + (b - a) * t) for a, b in zip(c1, c2))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


def tool_version(cmd, pattern, default):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        m = re.search(pattern, r.stdout + r.stderr)
        return m.group(1) if m else default
    except OSError:
        return default


class Git:
    def __init__(self, enabled):
        self.enabled = enabled
        self.count = 0

    def commit(self, message):
        if not self.enabled:
            return
        run("git add -A", quiet=True)
        if run("git diff --cached --quiet", check=False, quiet=True).returncode == 0:
            return
        run(["git", "commit", "-q", "-m", message], quiet=True)
        self.count += 1
        print(f"  커밋: {message}")


def step_setup():
    if CLASS_SETUP:
        print(f"수업 스크립트 구성 감지: Hugo 사이트 폴더 = {SITE.name}\\ (project-setup·워크플로는 건드리지 않음)")
        return
    if (ROOT / "exampleSite").is_dir() and not (ROOT / "themes" / "hugoplate").is_dir():
        print("npm run project-setup 실행 중...")
        run("npm run project-setup", quiet=True)
    if not (ROOT / "hugo.toml").exists() or not CONFIG.is_dir():
        sys.exit("Hugoplate 프로젝트 폴더(hugo.toml, config/_default 가 있는 곳)에서 실행하세요.")
    if not (ROOT / "node_modules").is_dir():
        print("npm install 실행 중... (1~2분)")
        run("npm install", quiet=True)


def step_gitignore():
    p = ROOT / ".gitignore"
    lines = read(p).splitlines() if p.exists() else []
    if CLASS_SETUP:
        have = {l.strip().rstrip("/") for l in lines}
        lines += [n for n in ("node_modules/", "public/", "resources/", ".hugo_build.lock", "__pycache__/") if n.rstrip("/") not in have]
        write(p, "\n".join(lines) + "\n")
        return
    drop = {"package-lock.json", "go.sum", "/package-lock.json", "/go.sum"}
    lines = [l for l in lines if l.strip() not in drop and not l.lstrip().startswith("#")]
    need = ["node_modules/", "public/", "resources/", ".hugo_build.lock", "hugo_stats.json", ".DS_Store", "Thumbs.db", "__pycache__/"]
    have = {l.strip().rstrip("/") for l in lines}
    lines += [n for n in need if n.rstrip("/") not in have]
    write(p, "\n".join(l for l in lines if l.strip()) + "\n")


def step_git_init(info):
    if run("git --version", check=False, quiet=True).returncode != 0:
        print("Git이 없어 커밋은 건너뜁니다.")
        return Git(False)
    if not (ROOT / ".git").is_dir():
        run("git init -q -b main", quiet=True)
        run(f"git remote add origin https://github.com/{info['gh']}/{info['repo']}.git", check=False, quiet=True)
    if not run("git config user.name", check=False, quiet=True).stdout.strip():
        run(f'git config user.name "{info["gh"]}"', quiet=True)
    if not run("git config user.email", check=False, quiet=True).stdout.strip():
        email = ask("Git 커밋에 쓸 이메일(GitHub 계정 이메일)")
        run(f'git config user.email "{email}"', quiet=True)
    return Git(True)


def step_hugo_toml(info):
    p = SITE / "hugo.toml"
    t = strip_comments(read(p))
    t = set_toml(t, "", "baseURL", toml_str(info["base"]))
    t = set_toml(t, "", "title", toml_str(f"{info['name']}의 포트폴리오"))
    t = set_toml(t, "", "defaultContentLanguage", toml_str("ko"))
    write(p, t)


def step_language():
    p = CONFIG / "languages.toml"
    content_dir = "content/english"
    if p.exists():
        m = re.search(r'contentDir\s*=\s*"([^"]+)"', read(p))
        if m:
            content_dir = m.group(1)
    write(p, f'[ko]\nlanguageName = "한국어"\nlanguageCode = "ko-kr"\ncontentDir = "{content_dir}"\nweight = 1\n')
    src = None
    for cand in (SITE / "i18n" / "en.yaml", ROOT / "i18n" / "en.yaml", SITE / "themes" / "hugoplate" / "i18n" / "en.yaml",
                 ROOT / "exampleSite" / "i18n" / "en.yaml"):
        if cand.exists():
            src = cand
            break
    if src:
        out = []
        for line in read(src).splitlines():
            m = re.match(r'^(\s*translation\s*:\s*)(["\']?)(.*?)\2\s*$', line)
            if m and m.group(3).strip().lower() in KO_UI:
                line = f"{m.group(1)}{yaml_str(KO_UI[m.group(3).strip().lower()])}"
            out.append(line)
        write(SITE / "i18n" / "ko.yaml", "\n".join(out) + "\n")
        stray = ROOT / "i18n"
        if CLASS_SETUP and stray.is_dir() and not any(stray.iterdir()):
            stray.rmdir()
    else:
        print("  i18n/en.yaml 을 찾지 못해 ko.yaml 은 만들지 않았습니다.")


def step_menus():
    for old in CONFIG.glob("menus.*.toml"):
        old.unlink()
    write(CONFIG / "menus.ko.toml", "\n".join([
        "[[main]]", 'name = "홈"', 'pageRef = "/"', "weight = 1", "",
        "[[main]]", 'name = "소개"', 'pageRef = "/about"', "weight = 2", "",
        "[[main]]", 'name = "활동"', 'pageRef = "/blog"', "weight = 3", "",
        "[[footer]]", 'name = "소개"', 'pageRef = "/about"', "weight = 1", "",
        "[[footer]]", 'name = "활동"', 'pageRef = "/blog"', "weight = 2", "",
    ]))


def step_params(info, avatar_rel):
    p = CONFIG / "params.toml"
    t = strip_comments(read(p))
    year = date.today().year
    t = set_toml(t, "", "logo", '""')
    t = set_toml(t, "", "logo_darkmode", '""')
    t = set_toml(t, "", "logo_text", toml_str(info["name"]))
    t = set_toml(t, "", "favicon", '"images/favicon.png"')
    t = set_toml(t, "", "copyright", toml_str(
        f"© {year} {info['name']} · Theme: [Hugoplate](https://github.com/zeon-studio/hugoplate) by Zeon Studio"))
    t = set_toml(t, "navigation_button", "enable", "true")
    t = set_toml(t, "navigation_button", "label", '"GitHub"')
    t = set_toml(t, "navigation_button", "link", toml_str(f"https://github.com/{info['gh']}"))
    for section in ("search", "announcement", "cookies", "subscription", "preloader"):
        if re.search(rf"^\s*\[{section}\]", t, re.M):
            t = set_toml(t, section, "enable", "false")
    t = set_toml(t, "metadata", "keywords", toml_str(["포트폴리오", "개인소개", info["field"] or "학습"]))
    t = set_toml(t, "metadata", "description", toml_str(f"{info['name']}의 개인 소개 사이트"))
    t = set_toml(t, "metadata", "author", toml_str(info["name"]))
    t = set_toml(t, "metadata", "image", toml_str(avatar_rel.lstrip("/")))
    write(p, t)


def step_social(info):
    write(SITE / "data" / "social.json", json.dumps(
        {"main": [{"name": "GitHub", "icon": "fab fa-github", "link": f"https://github.com/{info['gh']}"}]},
        ensure_ascii=False, indent=2) + "\n")


def step_images(info):
    keep_ext = ".png"
    if info["avatar"]:
        src = Path(info["avatar"].strip('"'))
        if src.is_file():
            keep_ext = src.suffix.lower() if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png"
    demo = re.compile(r"^(service|call-to-action|cta|post|testimonial|banner|avatar|author|feature|blog|about|image-\d|gallery|slider)", re.I)
    if IMAGES.is_dir():
        for f in IMAGES.rglob("*"):
            if f.is_file() and demo.match(f.name):
                f.unlink()
    avatar = IMAGES / f"avatar{keep_ext}"
    if info["avatar"] and Path(info["avatar"].strip('"')).is_file():
        shutil.copyfile(info["avatar"].strip('"'), avatar)
    else:
        png(IMAGES / "avatar.png", 400, 400, (59, 130, 246), (147, 51, 234))
        avatar = IMAGES / "avatar.png"
    for name, size in (("favicon.png", (64, 64)), ("og-image.png", (1200, 630)),
                       ("logo.png", (320, 64)), ("logo-darkmode.png", (320, 64)),
                       ("image-placeholder.png", (800, 450))):
        png(IMAGES / name, *size, (59, 130, 246), (147, 51, 234))
    left = sorted(f.relative_to(ROOT).as_posix() for f in IMAGES.rglob("*") if f.is_file())
    return "/images/" + avatar.name, left


def front(d):
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{k}:")
            for k2, v2 in v.items():
                if isinstance(v2, dict):
                    out.append(f"  {k2}:")
                    for k3, v3 in v2.items():
                        out.append(f"    {k3}: {yaml_str(v3) if isinstance(v3, str) else str(v3).lower()}")
                else:
                    out.append(f"  {k2}: {yaml_str(v2) if isinstance(v2, str) else str(v2).lower()}")
        elif isinstance(v, list):
            out.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, bool):
            out.append(f"{k}: {str(v).lower()}")
        else:
            out.append(f"{k}: {yaml_str(v) if isinstance(v, str) else v}")
    out.append("---")
    return "\n".join(out) + "\n"


def step_clean_content():
    for d in ("elements", "contact", "pages"):
        shutil.rmtree(CONTENT / d, ignore_errors=True)
    for f in ("search.md", "contact.md", "elements.md", "privacy-policy.md"):
        (CONTENT / f).unlink(missing_ok=True)
    blog = CONTENT / "blog"
    if blog.is_dir():
        for f in blog.iterdir():
            if f.name != "_index.md":
                shutil.rmtree(f) if f.is_dir() else f.unlink()
    authors = CONTENT / "authors"
    if authors.is_dir():
        for f in authors.iterdir():
            if f.name != "_index.md":
                shutil.rmtree(f) if f.is_dir() else f.unlink()
    sections = CONTENT / "sections"
    if sections.is_dir():
        for f in sections.glob("*.md"):
            write(f, re.sub(r"^(\s*enable\s*:\s*)true", r"\1false", read(f), flags=re.M))


def ph(value, what):
    return value if value else f"[{what}]"


def step_write_content(info, avatar_rel):
    n = info["name"]
    write(CONTENT / "_index.md", front({
        "banner": {
            "title": f"안녕하세요, {n}입니다",
            "content": ph(info["oneline"], "한 줄 소개"),
            "image": avatar_rel,
            "button": {"enable": True, "label": "대표 활동 보기", "link": "blog/portfolio-site/"},
        }
    }))

    about = front({
        "title": f"안녕하세요, {n}입니다",
        "meta_title": "소개",
        "description": f"{n}의 관심 분야, 학습 목표, 역량",
        "image": avatar_rel,
        "draft": False,
    })
    about += f"""
{ph(info['major'], '학과·학년')} {n}입니다. {ph(info['oneline'], '한 줄 소개')}

## 관심 분야

**{ph(info['field'], '관심 분야')}**

{ph(info['why'], '이 분야에 관심을 갖게 된 이유')}

## 학습 목표와 계획

- **목표**: {ph(info['goal'], '앞으로의 학습 목표')}
- **다음 행동**
    1. {ph(info['next1'], '목표를 위해 할 구체적인 행동 1')}
    2. {ph(info['next2'], '목표를 위해 할 구체적인 행동 2')}

## 역량과 적용 사례

| 기술·도구 | 실제로 사용한 곳 |
| --- | --- |
| Git / GitHub | 이 사이트의 변경을 커밋으로 나눠 기록하고 push로 배포 |
| Hugo / Markdown | Hugoplate 설정을 바꾸고 소개·활동 페이지를 Markdown으로 작성 |
| GitHub Actions | push하면 자동으로 빌드·배포되는 워크플로 구성 |

## 대표 활동

- [개인 소개 웹사이트 구축](../blog/portfolio-site/)
"""
    write(CONTENT / "about" / "_index.md", about)

    write(CONTENT / "blog" / "_index.md", front({
        "title": "활동",
        "meta_title": "활동",
        "description": "수업과 개인 학습에서 직접 수행한 활동",
    }))

    author_slug = re.sub(r"\s+", "-", n.strip()).lower()
    write(CONTENT / "authors" / f"{author_slug}.md", "\n".join([
        "---",
        f"title: {yaml_str(n)}",
        f"image: {yaml_str(avatar_rel)}",
        f"description: {yaml_str(ph(info['oneline'], '한 줄 소개'))}",
        "social:",
        "  - name: GitHub",
        '    icon: "fab fa-github"',
        f'    link: "https://github.com/{info["gh"]}"',
        "---",
        "",
        ph(info["oneline"], "한 줄 소개"),
        "",
    ]))
    if not (CONTENT / "authors" / "_index.md").exists():
        write(CONTENT / "authors" / "_index.md", front({"title": "작성자"}))

    post = front({
        "title": "개인 소개 웹사이트 구축",
        "meta_title": "",
        "description": "Hugoplate와 GitHub Pages로 만든 개인 소개 사이트",
        "date": f"{info['start']}T00:00:00+09:00",
        "categories": ["수업 실습"],
        "author": n,
        "tags": ["Hugo", "GitHub Pages"],
        "draft": False,
    })
    post += f"""
## 개요

- **기간**: {info['start']} ~ {info['end']}
- **상태**: 완료 (이후 내용 추가 중)
- **구분**: 2026학년도 초급프로젝트 과제, **개인 수행**

## 목적

테마 데모에 남아 있던 가상 인물과 데모 문구를 내 정보로 바꾸고, 코드를 push하면 자동으로 배포되는
사이트를 만들어 누구나 로그인 없이 볼 수 있게 하는 것이 목표였습니다.

## 내 역할

혼자 수행한 개인 활동입니다. 테마 설정, 페이지 작성, 배포 설정, 동작 점검을 직접 했습니다.
설정 변경 자동화와 오류 분석에는 AI(Claude)의 도움을 받았고, 결과는 직접 실행해 확인했습니다.

## 수행 과정

1. Hugoplate ZIP을 받아 project-setup으로 폴더 구조 정리
2. 주소·이름·메뉴·한국어 설정을 적용하고 데모 기능(후기·쿠키 팝업 등) 끄기
3. 소개·활동 페이지 작성, 데모 이미지를 내 이미지로 교체
4. Go·Node·Hugo를 설치하는 GitHub Actions 워크플로로 자동 배포
5. 1440px·390px 화면, 키보드 조작, 링크를 점검하고 수정

**Hugoplate를 고른 이유**: 반응형과 다크모드가 기본으로 들어 있고, Tailwind CSS와 Hugo 모듈을 쓰는
구조를 직접 다뤄 보며 요즘 웹 개발 도구가 어떻게 이어지는지 익히고 싶었기 때문입니다.

## 결과물

- 공개 사이트: <{info['base']}>
- 소스 코드: <https://github.com/{info['gh']}/{info['repo']}>

main 브랜치에 push하면 GitHub Actions가 빌드와 배포를 자동으로 수행하고, 메뉴·이미지·링크가 공개 주소에서
정상 동작하는 것을 확인했습니다.

## 배운 점과 다음 개선

- **배운 점**: 테마의 데모 설정이 여러 파일(설정, 데이터, 콘텐츠, 이미지)에 흩어져 있어, 화면의 문구를
  검색해 원본 파일을 찾는 방법이 가장 빠르다는 것을 알게 됐습니다.
- **한계**: Chrome에서만 점검했고, 활동이 아직 하나입니다.
- **다음 개선**: 다음 학기 프로젝트를 활동에 추가하고, 다른 브라우저에서도 검사합니다.
"""
    write(CONTENT / "blog" / "portfolio-site.md", post)


def step_workflow(versions):
    wf = ROOT / ".github" / "workflows"
    if CLASS_SETUP or (wf.is_dir() and any("prepare_github_pages" in read(f) for f in wf.glob("*.y*ml"))):
        print("  수업 제공 배포 워크플로를 그대로 사용합니다.")
        return
    if wf.is_dir():
        for f in list(wf.glob("*.yml")) + list(wf.glob("*.yaml")):
            f.unlink()
    write(wf / "hugo.yaml", f"""name: Deploy Hugo site to Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

defaults:
  run:
    shell: bash

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      HUGO_VERSION: {versions['hugo']}
      GO_VERSION: "{versions['go']}"
      NODE_VERSION: "{versions['node']}"
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: ${{{{ env.GO_VERSION }}}}

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{{{ env.NODE_VERSION }}}}

      - name: Install Hugo (extended)
        run: |
          wget -O ${{{{ runner.temp }}}}/hugo.deb https://github.com/gohugoio/hugo/releases/download/v${{HUGO_VERSION}}/hugo_extended_${{HUGO_VERSION}}_linux-amd64.deb
          sudo dpkg -i ${{{{ runner.temp }}}}/hugo.deb
          hugo version

      - name: Install Node dependencies
        run: |
          if [ -f package-lock.json ]; then npm ci; else npm install; fi

      - name: Download Hugo modules
        run: hugo mod graph

      - name: Setup Pages
        id: pages
        uses: actions/configure-pages@v5

      - name: Build
        env:
          HUGO_ENVIRONMENT: production
          TZ: Asia/Seoul
        run: |
          hugo --gc --minify --baseURL "${{{{ steps.pages.outputs.base_url }}}}/"
          test -f public/index.html

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./public

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
""")


def step_readme(info, versions):
    sp = "site/" if CLASS_SETUP else ""
    check_cd = "cd site\n" if CLASS_SETUP else ""
    check_py = "../" if CLASS_SETUP else ""
    if CLASS_SETUP:
        local_cmds = "python .github/pages_build.py --dependencies\nhugo server --source site"
        local_note = "Hugo 사이트는 `site/` 폴더에 있습니다. `hugo server --source site` 후 터미널에 표시되는 주소(http://localhost:1313/)에서 미리볼 수 있고, 배포는 `.github/workflows/hugo-pages.yml`이 `.github/pages_build.py`로 빌드합니다."
    else:
        local_cmds = "npm ci\nnpm run dev\nnpm run build"
        local_note = "`npm run dev` 후 터미널에 표시되는 주소(http://localhost:1313/)를 열면 미리볼 수 있고, `npm run build`는 `public/`에 배포용 결과를 만듭니다."
    for f in ROOT.iterdir():
        if f.name.lower() == "readme.md":
            f.unlink()
    write(ROOT / "README.md", f"""# {info['name']}의 개인 소개 사이트

- 공개 주소: {info['base']}

## 준비 도구

| 도구 | 버전 | 설치 (Windows / macOS) |
| --- | --- | --- |
| Hugo extended | {versions['hugo']} | `winget install Hugo.Hugo.Extended` / `brew install hugo` |
| Go | {versions['go']} | `winget install GoLang.Go` / `brew install go` |
| Node.js | {versions['node']} | `winget install OpenJS.NodeJS.LTS` / `brew install node` |
| Git | 2.x | `winget install Git.Git` / `brew install git` |

## 로컬 실행

```bash
git clone https://github.com/{info['gh']}/{info['repo']}.git
cd {info['repo']}
{local_cmds}
```

{local_note}

## 수정 위치

| 바꿀 것 | 파일 |
| --- | --- |
| 주소·제목 | `{sp}hugo.toml` |
| 로고 글자·저작권·상단 버튼 | `{sp}config/_default/params.toml` |
| 메뉴 | `{sp}config/_default/menus.ko.toml` |
| 소셜 링크 | `{sp}data/social.json` |
| 홈 배너 | `{sp}content/english/_index.md` |
| 소개 | `{sp}content/english/about/_index.md` |
| 활동 | `{sp}content/english/blog/` |
| 이미지 | `{sp}assets/images/` |
| 화면 문구 번역 | `{sp}i18n/ko.yaml` |
| 배포 설정 | `.github/workflows/` |

## 재배포

1. 파일 수정 후 `git add` → `git commit` → `git push origin main`
2. 저장소 Actions 탭에서 해당 커밋의 실행이 성공(초록색 체크)인지 확인
3. 공개 주소를 시크릿 창에서 열어 변경 반영 확인 (안 보이면 Ctrl+Shift+R)

## 링크 점검

```bash
{check_cd}hugo --gc --minify --baseURL "{info['base']}"
python {check_py}scripts/check_site.py {info['base']}
```

## 출처

| 자료 | 구분 | 출처 | 이용 조건 |
| --- | --- | --- | --- |
| Hugoplate 테마 | 외부 자료 | https://github.com/zeon-studio/hugoplate | MIT License, 테마 LICENSE 파일 유지 |
| 데모 이미지 | 사용 안 함 | - | 제작사가 배포 권한 없음을 밝혀 모두 교체·삭제 |
| 프로필·로고 이미지 | 직접 제작 | - | - |
| 소개·활동 글, 설정 변경 | 직접 작성 (AI 도움: Claude) | - | - |
""")


def main():
    print("Hugoplate 사이트를 내 정보로 바꿉니다. 모르는 항목은 Enter로 건너뛰면 [ ] 자리표시가 남습니다.\n")
    step_setup()
    global CONTENT
    lang = CONFIG / "languages.toml"
    if lang.exists():
        m = re.search(r'contentDir\s*=\s*"([^"]+)"', read(lang))
        if m:
            CONTENT = ROOT / m.group(1)

    info = {}
    info["name"] = ask("이름(사이트에 표시)")
    while not info["name"]:
        info["name"] = ask("이름은 꼭 필요합니다")
    gh0, repo0 = "", ""
    cfg = ROOT / ".github-pages.json"
    if cfg.exists():
        m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?[\"/]", read(cfg))
        if m:
            gh0, repo0 = m.group(1), m.group(2)
    info["gh"] = ask("GitHub 아이디", gh0)
    while not info["gh"]:
        info["gh"] = ask("GitHub 아이디는 꼭 필요합니다")
    info["repo"] = ask("저장소 이름", repo0 or f"{info['gh']}.github.io")
    info["base"] = (f"https://{info['gh'].lower()}.github.io/" if info["repo"].lower() == f"{info['gh'].lower()}.github.io"
                    else f"https://{info['gh'].lower()}.github.io/{info['repo']}/")
    info["major"] = ask("학과와 학년 (예: 컴퓨터공학과 1학년)")
    info["oneline"] = ask("한 줄 소개")
    info["field"] = ask("관심 분야 (예: 웹 개발)")
    info["why"] = ask("그 분야에 관심을 갖게 된 이유 (한두 문장)")
    info["goal"] = ask("앞으로의 학습 목표")
    info["next1"] = ask("목표를 위한 구체적 행동 1")
    info["next2"] = ask("목표를 위한 구체적 행동 2")
    info["start"] = ask("이 사이트 작업 시작일 (YYYY-MM-DD)", "2026-10-01")
    info["end"] = ask("작업 종료일 (YYYY-MM-DD)", date.today().isoformat())
    info["avatar"] = ask("프로필 사진 파일 경로 (없으면 Enter, 그라데이션 이미지 생성)")

    versions = {
        "hugo": tool_version("hugo version", r"v(\d+\.\d+\.\d+)", "0.152.2"),
        "go": tool_version("go version", r"go(\d+\.\d+)", "1.24"),
        "node": tool_version("node -v", r"v(\d+)", "22"),
    }
    print(f"\n감지한 버전: Hugo {versions['hugo']}, Go {versions['go']}, Node {versions['node']}\n")

    step_gitignore()
    git = step_git_init(info)
    if git.enabled and run("git rev-parse --verify HEAD", check=False, quiet=True).returncode != 0:
        git.commit("chore: Hugoplate 테마 원본과 수업 스크립트 준비 결과 등록" if CLASS_SETUP else "chore: Hugoplate 테마 원본과 project-setup 결과 등록")

    step_hugo_toml(info)
    git.commit("config: baseURL과 사이트 제목을 내 주소와 이름으로 변경")
    step_language()
    git.commit("config: 사이트 언어를 한국어(ko)로 바꾸고 화면 문구 번역 추가")
    step_menus()
    git.commit("config: 메뉴를 홈·소개·활동으로 정리하고 pageRef 방식으로 연결")
    avatar_rel, left_images = step_images(info)
    git.commit("assets: 데모 이미지를 삭제하고 내 프로필·파비콘·로고 이미지로 교체")
    step_params(info, avatar_rel)
    git.commit("config: 로고 글자·저작권·상단 버튼을 내 정보로, 검색·쿠키·공지 기능 끄기")
    step_social(info)
    git.commit("data: 소셜 링크를 내 GitHub 하나로 변경")
    step_clean_content()
    git.commit("cleanup: 데모 글·작성자·요소 모음·문의 페이지 삭제, 후기·CTA 섹션 끄기")
    step_write_content(info, avatar_rel)
    git.commit("content: 홈 배너·소개·대표 활동·작성자 페이지 작성")
    write(ROOT / "scripts" / "check_site.py", CHECK_SITE)
    git.commit("test: 배포 결과물의 깨진 링크·이미지를 찾는 검사 스크립트 추가")
    step_workflow(versions)
    if not CLASS_SETUP:
        git.commit("ci: Go·Node·Hugo를 설치해 빌드하는 GitHub Pages 배포 워크플로 추가")
    step_readme(info, versions)
    git.commit("docs: README에 설치·실행·수정 위치·재배포·출처 정리")

    print("\n빌드 확인 중...")
    build = run(f'hugo --gc --minify --baseURL "{info["base"]}"', check=False, quiet=True, cwd=SITE)
    if build.returncode != 0:
        print("로컬 빌드 실패(로컬에 Tailwind 의존성이 없으면 날 수 있음). 아래 오류를 Claude에게 보여 주세요. push 후 Actions 결과로도 확인할 수 있습니다.\n")
        print((build.stderr or build.stdout)[-3000:])
    else:
        check = run(f'"{sys.executable}" "{ROOT / "scripts" / "check_site.py"}" {info["base"]}', check=False, cwd=SITE)
        if check.returncode != 0:
            print("위 문제를 고치거나 Claude에게 보여 주세요.")

    todo = [k for k in ("major", "oneline", "field", "why", "goal", "next1", "next2") if not info[k]]
    print("\n완료.")
    if git.enabled:
        print(f"커밋 {git.count}개를 만들었습니다. 올리려면:  git push -u origin main")
    print("GitHub 저장소 Settings → Pages → Source 를 GitHub Actions 로 바꾸세요.")
    if todo:
        print("비워 둔 항목이 있어 content/english/about/_index.md 등에 [ ] 자리표시가 남아 있습니다.")
    print("assets/images 에 남은 파일:", ", ".join(left_images))
    print("확인: hugo server --source site 후 http://localhost:1313/" if CLASS_SETUP else "확인: npm run dev 후 http://localhost:1313/")


if __name__ == "__main__":
    main()