# aviasales-mcp: описания тулов, установка в один шаг, .mcpb (веха promo-mcp)

- **Репозиторий:** `/home/deploy/github/aviasales-mcp` (GitHub `stufently/aviasales-mcp`, публичный), 10.10.2026.
- **Базовый коммит:** `b37d002` «Add security policy» (main).
  BASE_SHA: b37d0022259f7411dd65c2c1a49df78e9680428f
  Следом за ним постановщик закоммитил ЭТУ спеку `docs/specs/promo-mcp.md` и входные
  данные критериев (`docs/specs/promo_check.py`, `docs/specs/promo-bundle-check.sh`,
  `docs/specs/promo-tools-before*.json`); клон сделан от этого коммита, они в нём уже
  tracked — коммитить их заново не нужно.
- **Исполнитель:** Grok (`gk`) — решение владельца 10.10.2026 («вехами Grok»).
  Мутации по новым тестам потом гоняет противоположный исполнитель (Codex/Spark).

## Где работать

Клон `/home/deploy/exec-clones/aviasales-mcp-promo-20261010`, новая ветка `promo-mcp` от `main`. Живое дерево
`/home/deploy/github/aviasales-mcp` не трогать. **push в origin запрещён** (push-URL клона —
`no-push`), работу заберёт постановщик через `git fetch` из клона.

Что кладёт постановщик ДО запуска: ничего: образы собираются из Dockerfile клона (`--target dev`/`runtime`), зависимости ставит сам `docker build`. Образы `python:3.14-slim`, `ghcr.io/astral-sh/uv:0.12.23-python3.14-trixie-slim`, `node:24.21.0-slim`, `rhysd/actionlint:1.7.12` есть на хосте.

## Задача и почему

Решение владельца 10.10.2026: техническая часть продвижения публичных MCP-серверов.
(1) Описание тула — это системный промпт для модели: узкое описание с «когда звать»
и аннотации `readOnlyHint`/`destructiveHint` решают, выберет ли агент тул и спросит
ли подтверждение. (2) Трение установки убивает проект вернее отсутствия рекламы: один
copy-paste путь и готовые JSON-блоки под Claude Code, Cursor, Windsurf, Claude Desktop,
Zed. (3) `.mcpb` (Desktop Extension) — установка в Claude Desktop одним кликом из
Release assets, собирается CI. Наружу в этой вехе НИЧЕГО не публикуется.

Что при этом сломается и чинится в этой же вехе: тесты, сверяющие текст описаний
или аннотации; проверка версий/README, если она есть в CI; `.gitignore` (новый
`dist-mcpb/`).

## Что проверено вживую, а что предположение

Код репо (BASE, постановщиком 10.10.2026, чтением кода и запуском сервера):
1. 13 тулов (FastMCP 3.x), регистрируются циклом `mcp.tool(annotations=_READ_ONLY)` в
   `src/aviasales_mcp/server.py:96`; описания — докстринги функций в
   `src/aviasales_mcp/tools/{flights,reference}.py`. Аннотации уже полные и верные (все
   тулы читающие: readOnly/idempotent/openWorld true, destructive false) — их не
   трогать. `Use when` нет ни у одного; `lookup_airlines`, `lookup_countries` — 8 слов.
2. Сервер стартует по stdio с фиктивным `AVIASALES_API_TOKEN` и отдаёт `tools/list` без
   сети (образ `docker build --target runtime`). `config.py` читает `.env` из cwd — в
   проверках его нет.
3. PyPI-пакета `aviasales-mcp` НЕТ (404 на 10.10); путь установки README — Docker
   `ghcr.io/stufently/aviasales-mcp` (один copy-paste, уже есть); блоки клиентов —
   `docker`.
4. README (BASE): Claude Desktop/Cursor/Windsurf — под ОДНИМ заголовком; Claude Code —
   без JSON; «Common prompts» — таблица из 6 строк.
5. `.github/workflows/registry.yml` (тег `v*`): образ GHCR + MCP-реестр, `contents: read`;
   GitHub Release не создаёт. `.mcpb` нигде нет.
6. Тесты CI: `ruff check src/ tests/`, `pytest -q --cov=aviasales_mcp --cov-fail-under=90`.
7. Проверено постановщиком: копия `pyproject.toml`, `README.md`, `LICENSE`, `src/` плюс
   лаунчер `from aviasales_mcp.server import main; main()` поднимается командой
   `uv run --directory <каталог> <лаунчер>` в uv-образе и отдаёт 13 тулов.

Клиенты и формат (общие для всех вех promo-mcp):
- Конфиги клиентов сверены 10.10.2026 по живой документации (curl):
  Claude Code — `.mcp.json` в корне проекта, ключ `mcpServers`, и команда
  `claude mcp add <имя> -- <команда>` (code.claude.com/docs/en/mcp);
  Cursor — `~/.cursor/mcp.json` или `.cursor/mcp.json`, ключ `mcpServers`
  (cursor.com/docs/context/mcp); Windsurf — docs.windsurf.com/windsurf/cascade/mcp
  отвечает страницей docs.devin.ai: файл `mcp_config.json`, macOS/Linux
  `~/.config/devin/mcp_config.json` (или `$XDG_CONFIG_HOME/devin/…`), Windows
  `%APPDATA%\devin\mcp_config.json`, ключ `mcpServers`; прежний путь
  `~/.codeium/windsurf/mcp_config.json` в текущей доке не встречается —
  писать новый, старый можно упомянуть как путь старых сборок;
  Claude Desktop — `claude_desktop_config.json`, ключ `mcpServers`;
  Zed — `settings.json`, ключ `context_servers`, поля `command`/`args`/`env`
  (zed.dev/docs/ai/mcp).
- Формат `.mcpb` сверен 10.10.2026 по `modelcontextprotocol/mcpb` (MANIFEST.md,
  ветка main): `manifest_version` `0.3` для `node`/`python`/`binary`, `0.4` нужен
  для `server.type: "uv"` (Python без вшитых зависимостей: хост ставит их из
  `pyproject.toml` через uv). Обязательные поля: `manifest_version`, `name`,
  `version`, `description`, `author.name`, `server`. `mcp_config` поддерживает
  `${__dirname}`, `${HOME}`, `${user_config.<ключ>}`; `user_config` с
  `sensitive: true` для секретов; `privacy_policies` обязателен, если расширение
  ходит во внешний сервис с данными пользователя. CLI — npm
  `@anthropic-ai/mcpb`, последняя версия 2.1.2 (04.12.2025), команды `validate
  <manifest>`, `pack <dir> <out>`, `info`. Проверено в Docker
  (`node:24.21.0-slim`): `validate` даёт rc=0 на корректном манифесте 0.3 и 0.4 и
  rc=1 на неизвестной версии/битом манифесте; `pack` упаковывает каталог.
- Пример `hello-world-uv` из того же репо: `"mcp_config": {"command": "uv",
  "args": ["run", "--directory", "${__dirname}", "src/server.py"]}`. Проверено
  10.10.2026 постановщиком на копиях этих репо: `uv run --directory <каталог>
  <скрипт|entry-point>` в `ghcr.io/astral-sh/uv:0.12.23-python3.14-trixie-slim`
  ставит зависимости и поднимает сервер, `tools/list` отвечает.
- `rhysd/actionlint:1.7.12` (последний релиз) локально есть, на текущих
  workflow этого репо даёт rc=0.

Состояние критериев на BASE (прогон постановщиком): AC-002, AC-003, AC-005, AC-006,
AC-007 красные по причинам выше; AC-004 красный — сборки `.mcpb` нет. Полный цикл
`promo-bundle-check.sh` (сборка → `mcpb validate` → проверка структуры → запуск из
`mcp_config`) постановщик прогнал на собранном вручную бандле `yandex-metrica-mcp`
— зелёный по всем шагам, кроме описаний/аннотаций самого сервера.

Предположения (не проверены; не подтвердились — «Контракт на невыполнимое»):
- П1. Claude Desktop поддерживает `server.type: "uv"` (manifest 0.4) так, как
  описано в MANIFEST.md. Проверить нечем — клиента на хосте нет; наш критерий
  гоняет ровно ту команду из `mcp_config`, которую хост должен выполнить.
- П2. Хост подставляет булев `user_config` в `env` строкой `true`/`false`.

## Что сделать

**Описания и аннотации тулов** (то, что видит модель при выборе тула):
- Каждое описание: первой фразой — что тул делает, узко и предметно; затем
  отдельное предложение, начинающееся с `Use when` — в какой ситуации пользователя
  его звать (пример: «Use when the user asks why an alert never arrived»); где есть
  близкий соседний тул — фраза, когда звать НЕ его, а соседа. Минимум 25 слов.
  Язык описаний — английский, как сейчас.
- Аннотации у КАЖДОГО тула: читающий — `readOnlyHint: true`,
  `destructiveHint: false`; пишущий — `readOnlyHint: false` и явный
  `destructiveHint` (`true` — удаляет, перезаписывает, необратимо меняет;
  `false` — только добавляет); `openWorldHint: true`, если тул ходит во внешний
  API; `idempotentHint` — где известно. Существующие верные аннотации не ломать.
- Имена тулов и `inputSchema` НЕ менять (критерий сверяет с
  `docs/specs/promo-tools-before*.json`, снятыми постановщиком с BASE).
  Описания параметров внутри схемы тоже не трогать — схема сравнивается целиком.
- Тесты, которые сверяют текст описаний, обновить; ослаблять их нельзя.
Аннотации у этого репо уже верные — меняются только описания.

**README.md** (английский, как сейчас):
- Раздел установки начинается с ОДНОГО copy-paste пути (команда, которую можно
  вставить в терминал и получить работающий сервер), его команда — та же, что в
  блоках клиентов ниже.
- Отдельный заголовок (любого уровня) на КАЖДОГО из пяти клиентов, в заголовке
  имя ровно одного клиента: `Claude Code`, `Claude Desktop`, `Cursor`,
  `Windsurf`, `Zed`. Под каждым — блок ```json, который парсится строгим JSON (без
  комментариев и хвостовых запятых): для первых четырёх — объект `mcpServers`, для
  Zed — `context_servers`; у сервера `command` (строка) и `args` (массив), секреты —
  в `env` плейсхолдерами. Рядом — путь к файлу конфига этого клиента (факты выше).
  У Claude Code JSON — это `.mcp.json`; команду `claude mcp add` оставить рядом.
  Прочие клиенты (Codex, VS Code и т.п.) — сохранить как есть.
- Под Claude Desktop — абзац про установку одним кликом: скачать `.mcpb` со
  страницы `https://github.com/stufently/aviasales-mcp/releases/latest` и открыть его.
- Заголовок `Example prompts`, под ним от 3 до 5 пунктов списка — запросы
  пользователя на естественном языке, сформулированные как задача («Why did my
  site lose clicks last week?»), а не как имя тула. Остальные примеры, если
  их больше, — под другим заголовком.
- Ничего не обещать из того, чего нет (npm/PyPI-пакет, которого нет в реестре,
  — только с пометкой статуса, как сейчас).

**Desktop Extension (`.mcpb`)**:
- Исходник манифеста — в репо (`mcpb/manifest.json`); `version` в нём не
  хранится руками, его подставляет сборка из `pyproject.toml`. `name`,
  `display_name`, `description`, `long_description` (что умеет и что нужно для
  запуска), `author.name` = `stufently`, `repository`, `homepage`, `support`
  (issues), `license`, `keywords`, `compatibility.platforms`, `tools` — список ВСЕХ
  тулов сервера `{name, description}` (имена должны совпасть с живым
  `tools/list`, критерий это сверяет), `user_config` — ниже.
- `scripts/build-mcpb.sh` — единственная точка сборки и локально, и в CI: чистит и
  создаёт `dist-mcpb/`, собирает стейджинг-каталог, пакует `npx -y
  @anthropic-ai/mcpb@2.1.2 pack` через Docker (`node:24.21.0-slim`, под
  `$(id -u):$(id -g)`), на хост ничего не ставит. `dist-mcpb/` — в `.gitignore`.
  В архив не попадают тесты, `.git`, кэши, `__pycache__`, `.env*`, исходники
  TypeScript (`.mcpbignore` или стейджинг только из нужного).
- Имена файлов: `dist-mcpb/aviasales-mcp-<версия pyproject>.mcpb`.
- `server.type: "uv"`, `manifest_version: "0.4"`, в бандле `pyproject.toml`,
  `README.md`, `LICENSE` (их требует сборка пакета), `src/aviasales_mcp/` и лаунчер;
  `mcp_config: {"command": "uv", "args": ["run", "--directory", "${__dirname}",
  "<лаунчер>"], "env": {"AVIASALES_API_TOKEN": "${user_config.api_token}",
  "AVIASALES_MARKET": "${user_config.market}"}}`. `compatibility.runtimes.python:
  ">=3.12"`. Лимит размера — 5 МБ.
- `user_config`: `api_token` (string, `sensitive: true`, required), `market` (string,
  `default: ""`, описание — см. README «Configuration»). Ключи — ровно эти.
- `privacy_policies`: страница политики конфиденциальности Travelpayouts — найди и
  проверь, что она открывается (`https://www.travelpayouts.com/en/privacy-policy`
  отвечает 404 — не она).

**Сборка в Release через CI**: новый `.github/workflows/mcpb.yml` на `push: tags: ["v*"]`; если релиза тега нет — создать (`gh release create "$GITHUB_REF_NAME" --verify-tag`), затем загрузить бандл.
Сборка вызывает тот же `scripts/build-mcpb.sh`; загрузка — `gh release upload
"$GITHUB_REF_NAME" dist-mcpb/*.mcpb --clobber` (или эквивалент) с
`permissions: contents: write` только у этой джобы. Сторонние actions — с
пином версии (как в соседних workflow). Workflow проходит
`rhysd/actionlint:1.7.12` без замечаний. Существующие шаги публикации (GHCR,
MCP-реестр, PyPI, npm) не трогать и новых публикаций в реестры не добавлять.

**CHANGELOG.md** — запись в начале файла (секция Unreleased или в формате файла):
описания и аннотации тулов, блоки клиентов, `.mcpb` и его сборка в CI.

## Не трогать

- Изменения — только в: `src/`, `tests/`, `scripts/`, `mcpb/`, `README.md`, `CHANGELOG.md`, `TASKS.md`, `.gitignore`, `.dockerignore`, `.github/workflows/mcpb.yml`.
- Имена тулов, `inputSchema`, поведение и ответы тулов, транспорт, авторизацию,
  версию пакета (`version` в манифестах пакета), зависимости и lock-файлы
  (`pyproject.toml`) — не менять.
- Никаких тегов, релизов, `git push`, `npm publish`, загрузок в PyPI/GHCR/MCP-
  реестр/каталоги, PR в чужие репозитории. **push в origin запрещён**, работу
  заберёт постановщик через `git fetch` из клона.
- `docs/specs/` не трогать (спека, `promo_check.py`, `promo-bundle-check.sh`,
  `promo-tools-before*.json` — входные данные критериев; они уже закоммичены
  постановщиком, коммитить их заново не нужно). Править чекер, чтобы он
  «прошёл», запрещено.
- `.env*`, секреты, учётные данные — не открывать и не создавать. Для запуска
  сервера в проверках — только фиктивные значения, как в критериях.
- На хост ничего не ставить; Docker — под своим uid (`-u $(id -u):$(id -g)`).

## Разрешения

Docker под своим uid; сеть — для `docker pull`, `npm`/`pip`/`uv`-зависимостей
и npx `@anthropic-ai/mcpb@2.1.2`; временные каталоги (`mktemp -d`); коммиты в
ветку `promo-mcp`. Запрещено: `git push`, sudo, установка на хост, обращения к
боевым API с настоящими ключами.

## Авторевью

Не делается (решение владельца 10.10.2026, как в соседних вехах этого дня):
ревью Codex и agy, мутационный прогон и живая проверка — у постановщика.
Исполнитель сдаёт работу после зелёных критериев и `report.json`.

## Контракт на невыполнимое

Факт из раздела «Что проверено» не подтверждается, предположение П1–П2 оказалось
ложным так, что критерий недостижим, `mcpb validate` отвергает обязательное по
спеке поле, или требование противоречит другому — критерий `blocked` с дословной
причиной, доведи остальное и остановись. Обходить (менять критерий или чекер,
ослаблять тест, менять имена/схемы тулов, публиковать что-либо) запрещено.

## Стыки с соседними вехами

После приёмки: ревью и мутационный прогон у постановщика, затем — тег и релиз
владельцем (первый реальный прогон workflow с `.mcpb`). Профили/сокращение числа
тулов, GitHub Topics, демо-GIF и подача в каталоги — отдельными задачами, не здесь.

## Контракт отчёта

`report.json` в КОРНЕ клона, untracked, ровно 8 записей AC-001…AC-008; `command` —
команда критерия посимвольно. `blocked` — `"rc": null` и дословная ошибка в `note`.
Глушители кода возврата запрещены.

```json
{"criteria": [{"id": "AC-001", "status": "pass|fail|blocked",
               "command": "<команда критерия>", "rc": 0, "note": "…"}]}
```

## Критерии приёмки

Команды запускаются из корня клона. Критериев: 8.

- **AC-001. Тесты и линтеры репозитория зелёные.**
  `bash -c 'docker build -q --target dev -t aviasales-mcp-dev:promo . >/dev/null && docker run --rm aviasales-mcp-dev:promo sh -c "ruff check src/ tests/ && pytest -q -p no:cacheprovider --cov=aviasales_mcp --cov-fail-under=90"'`
- **AC-002. У каждого тула сервера из исходников клона есть аннотации, описание не короче 25 слов с фразой Use when; имена и схемы тулов не изменились.**
  `bash -c 'docker build -q --target runtime -t aviasales-mcp:promo . >/dev/null && f=$(mktemp) && python3 docs/specs/promo_check.py tools --timeout 120 --dump "$f" --cmd "docker run --rm -i --network none -e AVIASALES_API_TOKEN=dummy aviasales-mcp:promo" && python3 docs/specs/promo_check.py surface --before docs/specs/promo-tools-before.json --after "$f"'`
- **AC-003. README даёт JSON-блоки пяти клиентов на одной команде запуска, 3–5 примеров запросов и ссылку на mcpb в Releases.**
  `bash -c 'python3 docs/specs/promo_check.py readme README.md --commands docker && grep -q "\.mcpb" README.md && grep -q "github.com/stufently/aviasales-mcp/releases/latest" README.md'`
- **AC-004. Бандлы mcpb собираются скриптом репо, проходят официальный валидатор и проверку структуры, запускаются из собственного mcp_config и отдают объявленные тулы.**
  `bash -c 'bash docs/specs/promo-bundle-check.sh'`
- **AC-005. Release-workflow собирает и прикладывает mcpb к релизу; actionlint чистый.**
  `bash -c 'python3 docs/specs/promo_check.py ci .github/workflows/mcpb.yml --build-marker scripts/build-mcpb.sh && docker run --rm -u $(id -u):$(id -g) -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.12 -no-color'`
- **AC-006. Скрипт сборки и манифест закоммичены, выход сборки игнорируется git.**
  `bash -c 'git ls-files --error-unmatch scripts/build-mcpb.sh >/dev/null && test -n "$(git ls-files mcpb | grep -E "manifest\.json$")" && git check-ignore -q dist-mcpb/probe.mcpb'`
- **AC-007. CHANGELOG получил запись о вехе.**
  `bash -c 'git diff b37d0022259f7411dd65c2c1a49df78e9680428f..HEAD -- CHANGELOG.md | grep -E "^\+" | grep -qi "mcpb"'`
- **AC-008. Изменены только разрешённые файлы, docs/specs тронут одним коммитом постановщика, работа есть, дерево чистое.**
  `bash -c 'b=b37d0022259f7411dd65c2c1a49df78e9680428f; git cat-file -e "$b^{commit}" && test -n "$(git diff --name-only $b..HEAD -- mcpb scripts/build-mcpb.sh)" && test -z "$(git diff --name-only $b..HEAD | grep -v "^docs/specs/" | grep -vE "^(src/|tests/|scripts/|mcpb/|README\.md$|CHANGELOG\.md$|TASKS\.md$|\.gitignore$|\.dockerignore$|\.github/workflows/mcpb\.yml$)")" && test "$(git log --format=%H $b..HEAD -- docs/specs | wc -l)" = 1 && test -z "$(git status --porcelain -- . ":(exclude)report.json" ":(exclude)report-blocked.md")"'`
