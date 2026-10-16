# Repository names and next improvements

These are proposals for review. This documentation change keeps the repository,
package, and `html-serve` command names as they are. I have not checked name
availability or trademarks.

아래 내용은 검토를 위한 제안입니다. 이번 문서 변경에서는 저장소, 패키지,
`html-serve` 명령 이름을 유지합니다. 이름 사용 가능 여부와 상표는 확인하지 않았습니다.

## Name recommendation / 이름 제안

| Name | Why it fits | 어울리는 이유 |
| --- | --- | --- |
| **readloop** | My first choice. It captures the reason for the tool: create a document, open it, read it, repeat. It covers both HTML and Markdown. | 가장 추천합니다. 문서를 만들고, 열고, 읽는 반복 흐름을 담습니다. HTML과 Markdown을 모두 포괄합니다. |
| **docport** | Connects documents with the memorable ports that make the command useful. | 문서와 포트를 함께 떠올리게 합니다. 기억하기 쉬운 포트 선택이라는 특징을 살립니다. |
| **viewloop** | Emphasizes the repeated viewing workflow and leaves room for other document formats. | 반복해서 문서를 열어 보는 흐름을 강조합니다. 다른 형식으로 확장하기에도 자연스럽습니다. |

`html-serve` explains the action, but it leaves Markdown and the reading workflow
out of the name. **readloop** gives the project a clearer identity. The README
can keep “HTML and Markdown from your SSH terminal” as its descriptive subtitle.

`html-serve`는 동작을 바로 설명하지만 Markdown과 문서를 읽는 흐름은 잘 드러내지 못합니다.
**readloop**를 쓰면 프로젝트가 생긴 이유를 이름에 담을 수 있습니다.
부제에는 “SSH 터미널에서 HTML과 Markdown 읽기”처럼 기능을 명확히 설명하면 좋겠습니다.

Before a rename, check availability and choose whether the repository, Python
package, and CLI should share the new name. A repository rename can be separate
from a command rename. Keep `html-serve` as a compatibility alias if the CLI changes.

이름을 바꾸기 전에는 사용 가능 여부를 확인하고 저장소, Python 패키지, CLI의 이름을
어디까지 맞출지 정하면 됩니다. 저장소 이름만 먼저 바꿀 수도 있습니다.
CLI까지 바꾼다면 기존 `html-serve`는 호환용 별칭으로 유지하는 것을 권합니다.

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
   the developer's checkout layout. Publish packages only after choosing the name.

   **일반 사용자를 위한 설치 경로 마련하기.** 현재 `just sync`는 기본 체크아웃의
   `main`을 따르도록 설계되어 있습니다. 개발자의 디렉터리 구조에 의존하지 않는
   Git URL 또는 릴리스 wheel 설치 방법을 문서화하고 검증하면 좋겠습니다.
   패키지 공개는 이름을 정한 뒤 진행하면 됩니다.

4. **Help users return across sessions.** Explore a local session list that shows
   running servers, their roots, selected documents, and URLs. Reusing an
   existing server for the same root could reduce duplicate launches. Keep this
   optional so serving one file stays simple.

   **다른 세션에서도 다시 찾기 쉽게 만들기.** 실행 중인 서버의 루트, 선택한 문서,
   URL을 보여 주는 로컬 세션 목록을 검토해 볼 만합니다.
   같은 루트의 서버를 재사용하면 중복 실행도 줄일 수 있습니다.
   파일 하나를 여는 기본 흐름은 간단하게 유지하고 선택 기능으로 제공하면 좋겠습니다.
