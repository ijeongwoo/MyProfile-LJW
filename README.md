# 이정우의 개인 소개 사이트

- 공개 주소: https://ijeongwoo0109.github.io/MyProfile-LJW/

## 준비 도구

| 도구 | 버전 | 설치 (Windows / macOS) |
| --- | --- | --- |
| Hugo extended | 0.169.0 | `winget install Hugo.Hugo.Extended` / `brew install hugo` |
| Go | 1.27 | `winget install GoLang.Go` / `brew install go` |
| Node.js | 24 | `winget install OpenJS.NodeJS.LTS` / `brew install node` |
| Git | 2.x | `winget install Git.Git` / `brew install git` |

## 로컬 실행

```bash
git clone https://github.com/ijeongwoo0109/MyProfile-LJW.git
cd MyProfile-LJW
python .github/pages_build.py --dependencies
hugo server --source site
```

Hugo 사이트는 `site/` 폴더에 있습니다. `hugo server --source site` 후 터미널에 표시되는 주소(http://localhost:1313/)에서 미리볼 수 있고, 배포는 `.github/workflows/hugo-pages.yml`이 `.github/pages_build.py`로 빌드합니다.

## 수정 위치

| 바꿀 것 | 파일 |
| --- | --- |
| 주소·제목 | `site/hugo.toml` |
| 로고 글자·저작권·상단 버튼 | `site/config/_default/params.toml` |
| 메뉴 | `site/config/_default/menus.ko.toml` |
| 소셜 링크 | `site/data/social.json` |
| 홈 배너 | `site/content/english/_index.md` |
| 소개 | `site/content/english/about/_index.md` |
| 활동 | `site/content/english/blog/` |
| 이미지 | `site/assets/images/` |
| 화면 문구 번역 | `site/i18n/ko.yaml` |
| 배포 설정 | `.github/workflows/` |

## 재배포

1. 파일 수정 후 `git add` → `git commit` → `git push origin main`
2. 저장소 Actions 탭에서 해당 커밋의 실행이 성공(초록색 체크)인지 확인
3. 공개 주소를 시크릿 창에서 열어 변경 반영 확인 (안 보이면 Ctrl+Shift+R)

## 링크 점검

```bash
cd site
hugo --gc --minify --baseURL "https://ijeongwoo0109.github.io/MyProfile-LJW/"
python ../scripts/check_site.py https://ijeongwoo0109.github.io/MyProfile-LJW/
```

## 출처

| 자료 | 구분 | 출처 | 이용 조건 |
| --- | --- | --- | --- |
| Hugoplate 테마 | 외부 자료 | https://github.com/zeon-studio/hugoplate | MIT License, 테마 LICENSE 파일 유지 |
| 데모 이미지 | 사용 안 함 | - | 제작사가 배포 권한 없음을 밝혀 모두 교체·삭제 |
| 프로필·로고 이미지 | 직접 제작 | - | - |
| 소개·활동 글, 설정 변경 | 직접 작성 (AI 도움: Claude) | - | - |
