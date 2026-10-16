# Project direction / 프로젝트 방향

## Selected name: docserve / 선택한 이름: docserve

The project and Python distribution use the name **docserve**. It covers both HTML
and Markdown, including GitHub Flavored Markdown, LaTeX math, and Mermaid diagrams.
Installation provides `docserve` as the primary command plus `html-serve` and
`md-serve` as aliases. Every command supports the same formats and options.

프로젝트와 Python 배포 패키지의 이름은 **docserve**입니다.
HTML과 Markdown을 모두 포괄하며 GitHub Flavored Markdown, LaTeX 수식,
Mermaid 다이어그램을 지원합니다. 설치하면 기본 명령인 `docserve`와
`html-serve`, `md-serve` 별칭을 함께 제공합니다. 세 명령의 기능과 옵션은 같습니다.

Earlier naming ideas included `readloop`, `docport`, `viewloop`, and `docpeek`.
The user chose `docserve` to state the document-serving purpose directly.

앞서 `readloop`, `docport`, `viewloop`, `docpeek`를 검토했습니다.
사용자는 문서 서빙이라는 목적을 바로 설명하는 `docserve`를 선택했습니다.

## Next improvements / 다음 개선 제안

1. **Show the real loop in a short demo.** Record a headless terminal/browser demo:
   an agent creates a document, the user runs the command, and the browser opens
   the document and a neighboring file. Use a disposable sample project and
   example addresses. The README illustration explains the idea. A real demo
   would show the actual interface.

   **짧은 데모로 실제 흐름 보여 주기.** 에이전트가 문서를 만들고, 사용자가 명령을 실행하고,
   브라우저에서 문서와 주변 파일을 여는 과정을 보여 줍니다.
   임시 예제 프로젝트와 예시 주소를 사용하면 됩니다.
   README 그림에 더해 실제 인터페이스도 확인할 수 있게 됩니다.

2. **Make the skill easy to adopt.** Add a portable `serve-html` skill to this
   repository with installation instructions. The current skill lives in a
   separate collection. Keeping a distributable copy here would let another
   user reproduce the same document-to-command handoff.

   **스킬을 함께 설치하기 쉽게 만들기.** 이 저장소에 재사용 가능한 `serve-html` 스킬과
   설치 안내를 제공합니다. 현재 스킬은 별도 모음에서 관리합니다.
   배포 가능한 사본을 함께 제공하면 다른 사용자도 같은 흐름을 재현하기 쉽습니다.

3. **Provide an installation path for other users.** The current `just sync`
   workflow deliberately follows the primary `main` checkout. Document and test
   a separate installation from a Git URL or a released wheel, without requiring
   the developer's checkout layout. Verify package-name availability before
   publishing a release.

   **일반 사용자를 위한 설치 경로 마련하기.** 현재 `just sync`는 기본 체크아웃의
   `main`을 따르도록 설계되어 있습니다. 개발자의 디렉터리 구조에 의존하지 않는
   Git URL 또는 릴리스 wheel 설치 방법을 문서화하고 검증하면 좋겠습니다.
   패키지를 공개하기 전에는 배포 이름의 사용 가능 여부를 확인하면 됩니다.

4. **Help users return across sessions.** Explore a local session list that shows
   running servers, their roots, selected documents, and URLs. Reusing an
   existing server for the same root could reduce duplicate launches. Keep this
   optional so serving one file stays simple.

   **다른 세션에서도 다시 찾기 쉽게 만들기.** 실행 중인 서버의 루트, 선택한 문서,
   URL을 보여 주는 로컬 세션 목록을 검토해 볼 만합니다.
   같은 루트의 서버를 재사용하면 중복 실행도 줄일 수 있습니다.
   파일 하나를 여는 기본 흐름은 간단하게 유지하고 선택 기능으로 제공하면 좋겠습니다.
