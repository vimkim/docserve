# docserve

[English](README.md) · **한국어** · [명령어 가이드 (English)](docs/guide.md)

> AI가 문서를 만들면, 이제 편하게 읽으세요.

SSH 서버에 있는 HTML과 Markdown을 명령 하나로 열어 보세요.
기억하기 쉬운 빈 포트를 고르고, 접속 주소를 찾아 주고,
주변 파일까지 함께 둘러볼 수 있게 해 줍니다.

![SSH 터미널에서 docserve docs/review.md를 실행한 뒤, 브라우저에서 문서와 주변 파일 목록을 여는 흐름.](docs/assets/readme-workflow.svg)

> [!WARNING]
> **개발 용도로만 사용하세요. 프로덕션 서비스에는 사용하지 마세요.**
> 파일이나 디렉터리를 지정하면 숨김 파일과 민감한 파일을 포함한 Git 저장소 전체가 노출될 수 있습니다.
> 절대 파일시스템 URL은 추가 옵션 없이 서빙 루트 밖의 파일과 디렉터리에도 접근할 수 있습니다.
> 서버 프로세스가 읽을 수 있는 파일은 숨김 파일과 민감한 파일을 포함해 노출될 수 있습니다.
> 심볼릭 링크를 통해 서빙 디렉터리 밖의 파일도 노출될 수 있습니다.
> 기본적으로 모든 IPv4 인터페이스에서 접속을 받으며, 인증이나 TLS를 제공하지 않습니다.
> 서버에 접근할 수 있는 사람은 서빙 중인 파일을 읽을 수 있으므로 신뢰할 수 있는 개발 네트워크에서만 사용하세요.
> 로컬 접근에는 `--bind 127.0.0.1`로 실행한 뒤 SSH 터널로 접속하세요. `-d`는 주 디렉터리를 지정하며 절대 경로 접근을 제한하지 않습니다.

## 왜 만들었나요?

AI 에이전트는 읽어 볼 만한 문서를 많이 만들어 줍니다.
코드 설명, 설계 노트, 작업 계획, 다이어그램까지 Markdown이나 HTML로 남깁니다.

그런데 저는 대부분 원격 SSH 서버에서 작업합니다.
새 문서가 생길 때마다 파일을 찾고, 서버를 띄우고, 포트를 고르고,
어느 주소로 접속할지 확인해야 했습니다.
여러 세션과 프로젝트를 오가다 보니 이 작은 수고가 계속 반복됐습니다.

돌아보면 제 작업 흐름은 **문서 생성 → 서빙 → 읽기 → 반복**이었습니다.
이 흐름을 편하게 이어 줄 작은 명령 하나와 간단한 에이전트 스킬이면
충분하겠다고 생각했습니다.

그래서 `docserve`를 만들었습니다.
제 환경에서는 에이전트가 문서를 만든 뒤 스킬을 통해 실행할 명령을 알려 줍니다.
저는 SSH 터미널에서 그 명령을 실행하고, 제 컴퓨터에서 출력된 링크를 열어 읽습니다.

## 파일 하나를 지정하면, 주변 맥락도 함께

```sh
docserve docs/review.md
```

Tailscale을 사용할 때의 링크 예시입니다. 실제 주소와 빈 포트는 환경에 따라 달라집니다.

```text
Root directory:
- http://100.64.0.12:7777/ — Tailscale

Selected path:
- http://100.64.0.12:7777/docs/review.md — Tailscale
```

문서 링크로 바로 읽거나, 루트 목록에서 주변 파일을 둘러보세요.
읽는 동안 명령을 실행 상태로 두고, 다 읽으면 **Ctrl+C**로 종료합니다.
접속할 컴퓨터에서 출력된 주소에 접근할 수 있어야 합니다.
같은 LAN이나 VPN으로 연결된 환경에서 사용할 수 있습니다.

자주 신경 쓰던 일은 명령에 맡길 수 있습니다.

- **기억하기 쉬운 포트.** `7777`, `8888`, `9999` 같은 포트부터 시도합니다.
  사용 중인 포트는 건너뛰고, 선택한 포트는 서버가 계속 점유합니다.
  여러 세션에서 실행해도 서로 다른 빈 포트를 사용합니다.
- **문서가 속한 프로젝트.** 파일이나 디렉터리를 지정하면 Git 저장소 루트를 찾습니다.
  관련 문서를 둘러보고 상대 경로로 연결된 문서와 리소스에도 접근할 수 있습니다.
  Git 저장소 밖에서는 지정한 디렉터리나 파일의 상위 디렉터리를 사용합니다.
- **접속할 수 있는 주소.** 활성 Tailscale, VPN, LAN의 IPv4 주소를 찾아
  루트 목록과 선택한 문서의 링크를 출력합니다.
- **바로 읽을 수 있는 문서.** HTML은 HTML로 열립니다.
  Markdown은 표, Mermaid 다이어그램, 수식, SVG 이미지와 라이트/다크 테마를 지원합니다.
  렌더러와 폰트를 함께 제공하므로 미리보기에 CDN이 필요하지 않습니다.

파일 목록에서는 **Title**, **Created**, **Modified** 헤더를 눌러 정렬할 수 있습니다.
터미널로 돌아가지 않고 다른 문서도 이어서 열어 보세요.

HTML과 Markdown을 열면 상단에 작은 배너가 표시됩니다. **Directory listing**으로
파일 탐색 창을 열고, **Compact view**로 플로팅 컨트롤로 전환할 수 있습니다.
플로팅 컨트롤에서도 별도의 디렉터리 팝업을 열 수 있으며, **Open standalone**은
문서를 새 탭에서 엽니다. 자세한 내용은 [문서 탐색 안내](docs/guide.md#document-navigation)를 참고하세요.

**Find files**, **Find contents**, **Find directories**에서 경로나 본문을 검색하고 Markdown과 HTML을 렌더링한 미리보기를 볼 수 있습니다.
**Go to root**는 서빙 루트로 이동합니다. **Recently visited**는 최근 연 파일과 디렉터리를 서버 재시작 후에도 보여 줍니다.
**Recently updated**는 하위 디렉터리의 파일까지 수정 시각이 최신인 순서로 보여 주며, 기본값이 `.html`과 `.md`인 파일명 필터를 편집하거나 지울 수 있습니다.
자세한 동작은 [검색과 최근 방문 안내](docs/guide.md#finding-and-revisiting-paths)를 참고하세요.

## SSH 서버에서 시작하기

[uv](https://docs.astral.sh/uv/)와
[just](https://github.com/casey/just)를 설치한 뒤 실행하세요.

```sh
git clone https://github.com/vimkim/docserve.git ~/gh/docserve
cd ~/gh/docserve
just sync
```

`just sync`는 **`docserve`**, **`html-serve`**, **`md-serve`**를 자동으로 설치합니다.
세 명령은 같은 인자를 받고 HTML과 Markdown을 모두 지원합니다.
문서의 절대 파일시스템 링크는 다른 저장소를 가리켜도 추가 옵션 없이 열립니다.
대상 문서가 속한 Git 저장소를 함께 서빙하므로 상대 링크와 이미지도 사용할 수 있습니다.
기존 `html-serve` 명령도 그대로 사용할 수 있습니다.

실행에는 **Python 3.10+**와 Linux **iproute2**(`ip`)가 필요합니다.
별도 Python 런타임 의존성은 없으며, Node/npm은 개발할 때만 사용합니다.

```sh
docserve                     # 현재 디렉터리 둘러보기
docserve docs/review.md      # Git 프로젝트를 루트로 Markdown 읽기
docserve output/report.html  # 주변 리소스와 함께 HTML 열기
```

SSH 터미널에서 실행한 뒤, 출력된 URL을 제 컴퓨터의 브라우저에서 엽니다.
명령은 포그라운드에서 실행됩니다.
제 작업 흐름에서는 에이전트 스킬이 명령을 제안하지만, 직접 실행해도 됩니다.

## 자세한 사용법

상세 문서는 [`docs/`](docs/guide.md)에 있습니다. 아래 가이드는 영어로 제공합니다.

- [경로 지정, Git 루트 탐색, 디렉터리 둘러보기](docs/guide.md#paths-and-file-selection)
- [Markdown, Mermaid, 수식, 테마](docs/guide.md#markdown-preview)
- [포트, 네트워크 주소, 서버 옵션](docs/guide.md#server-options)
- [개발, 테스트, 번들 리소스](docs/guide.md#source-and-installation)
