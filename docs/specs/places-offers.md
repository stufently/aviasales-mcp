# Веха places-offers: find_places, get_special_offers, длительность поездки в календаре

- Репозиторий: `/home/deploy/github/aviasales-mcp` (GitHub `stufently/aviasales-mcp`, публичный).
- Дата: 2026-11-08.
- База: коммит постановщика «Add places-offers spec» (эта спека + smoke) поверх
  `2d39aca` «Bump actions/setup-python from 7.0.0 to 7.1.0 (#14)» (main).
  Критерии находят коммит спеки сами (`git log --grep`).
- Исполнитель: cx (Codex) — регламент координатора на 08.11.2026. Мутации по новым
  тестам после приёмки гоняет противоположный исполнитель (Qwen).
- Отчёт — простой формат (раздел «Контракт отчёта»). Авторевью внутри вехи НЕ
  требуется: ревью Codex и мутации делает постановщик после приёмки.

## Где работать

- Клон: `/home/deploy/exec-clones/aviasales-mcp-places-offers`, ветка
  `feat/places-offers-duration` (уже выбрана). Новые коммиты — поверх неё.
- Живое дерево `/home/deploy/github/aviasales-mcp` не трогать.
- **Push в origin запрещён** (push-url клона = `no-push`); работу постановщик
  заберёт `git fetch` из клона. Merge, теги, релизы, публикация в PyPI/GHCR — запрещены.
- **`git pull` в клоне не делать** (глобальное правило «git pull перед работой» здесь
  не действует: клон уже на нужной базе).
- **Никаких реальных вызовов API и ключей.** Все HTTP-вызовы в тестах — `respx`-моки,
  как в существующих `tests/`. Тесты гоняются в Docker с `--network none`. `.env`
  не создавать и не читать.
- Тулчейна на хосте нет — всё через Docker-образ ниже.

### Что кладёт постановщик ДО запуска

| Что | Где | Зачем |
|---|---|---|
| Docker-образ `aviasales-mcp-dev:offers` | локальный docker хоста (собран `docker build --target dev` от `2d39aca`; зависимости вехой не меняются) | pytest/ruff/respx. Пакет внутри установлен не editable, поэтому критерии ставят `PYTHONPATH=/app/src` — импортируется код клона (проверено: `aviasales_mcp.__file__` = `/app/src/...`) |
| `docs/specs/places-offers-smoke.py` | закоммичен постановщиком вместе со спекой | независимая проверка контракта; **исполнитель его НЕ правит** |

## Задача и почему

Три открытых пункта `TASKS.md` (строки 16, 19, 20): серверный поиск мест вместо
выгрузки 2.5 МБ `airports.json` для частого пути «название города → IATA»,
промо-тарифы авиакомпаний, и «поездка на 10–14 дней в сентябре» в календаре цен.

Что при этом СЛОМАЕТСЯ и чинится в этой же вехе:
- `tests/test_server.py::test_every_tool_is_registered` — фиксированный набор из 13
  имён; добавить два новых.
- `.github/workflows/ci.yml`, джоба `docker`: `[ "$count" = 13 ]` → 15.
- `mcpb/manifest.json` — список `tools` (13) → 15.
- `.github/site/site.toml` — «Thirteen …» / «All thirteen tools …» → fifteen.
- `tests/test_server.py::test_tool_descriptions_say_when_to_call_them` и
  `test_tool_descriptions_point_only_at_real_tools` действуют и на новые тулы:
  докстринг с отдельным предложением `Use when …`, ≥25 слов, упоминания в обратных
  кавычках только реальных тулов.

## Что проверено вживую, а что предположение

Проверено постановщиком 08.11.2026:
1. **Autocomplete живёт НЕ там, где написано в TASKS.md.**
   `GET https://api.travelpayouts.com/aviasales/v3/autocomplete?term=bangk&types=city`
   → `404 page not found` (а соседние пути v3 без токена дают `401` — то есть маршрута
   нет вообще). Рабочий эндпоинт — публичный
   `GET https://autocomplete.travelpayouts.com/places2?term=&locale=&types[]=…`
   (документация Travelpayouts, статья 360002322572), **токен не нужен** → `200`.
2. `types` передаётся ТОЛЬКО как повторяемый `types[]` (`types[]=city&types[]=airport`,
   скобки можно процент-кодировать `types%5B%5D` — проверено, работает). Голый
   `types=city` молча игнорируется (вернулись и аэропорты). Допустимые значения:
   `city`, `airport`, `country`.
3. Ответ — JSON-массив, не больше **20** элементов (`term=san` → 20), упорядочен по
   релевантности (`weight`). Пустой/не найден → `[]` с кодом 200. Поля строки:
   `id, type, code, name, country_code, country_name, state_code, coordinates{lon,lat},
   index_strings, weight, cases, country_cases`; у аэропорта ещё `city_code, city_name,
   city_cases`; у города — `main_airport_name`; у страны — только
   `id, type, code, name, index_strings, weight, cases`. `locale=ru` даёт русские имена.
4. `grouped_prices`: в официальной документации (статья 203956163) есть
   `min_trip_duration` / `max_trip_duration` — «длина поездки в днях (разница дат вылета
   и возврата)». TASKS.md отмечает их как «verified working live» прошлой сессией;
   сегодня вживую НЕ перепроверено (нужен токен, а `.env` не читаем) — **предположение
   на основе документации и прошлой проверки**.
5. `get_special_offers`: документация (та же статья) — `GET /aviasales/v3/get_special_offers`,
   параметры `origin` (если не указан — определяется **по IP вызывающего**, то есть по
   IP нашего сервера, а не пользователя), `destination`, `locale`, `currency`, `market`,
   `airline` (IATA авиакомпании); ответ `{"currency", "data": [...], "success": true}`,
   строка: `airline, airline_title, color, departure_at, return_at?, destination,
   destination_airport, destination_name, duration, flight_number, link, mini_title,
   origin, origin_airport, origin_name, price, search_id, signature, title`.
   Без токена → `401` (эндпоинт существует). **Формат `link` — предположение по
   документации:** пример там `/LON1409BCN1?t=…` — БЕЗ префикса `/search/`, и текст
   документации велит дописывать его к `https://www.aviasales.ru/search/`. Живьём не
   видели; поэтому код обязан принимать оба вида (с `/search/` и без).

Проверено чтением кода на `2d39aca`:
- `api/client.py`: `BASE_URL = "https://api.travelpayouts.com"`; `_request(method, path, *, params)`
  собирает `url = f"{BASE_URL}{path}"`, ВСЕГДА ставит заголовок `X-Access-Token`, ретраит
  429/5xx/таймауты/сетевые ошибки, `ApiError`/`RateLimitError` (оба — `TravelpayoutsError`),
  не-JSON → `ApiError`, `{"success": false}` → `ApiError`. Публичная обёртка
  `get(path, **params)` выкидывает `None`-параметры. AGENTS.md: весь HTTP — только через
  этот модуль, `httpx` из модулей тулов не звать.
- `tools/responses.py::guard(build_error, *, hint=None)` — превращает
  `InvalidArgumentError` (с его `hint`), `TravelpayoutsError` и прочие исключения в
  payload ошибки.
- `tools/flights.py` (топ-уровневые, импортируемые): `_error_response(message, hint)`
  (`{"status": "error", "error", "data": [], "hint"?}`), `_API_ERROR_HINT`,
  `_FIELD_NOTE`, `_validate_trip_class`, `_price_note(trip_class)`,
  `_clamp_party(adults, children, infants)`, `_passenger_block(...)`,
  `_build_booking_link(link_fragment, passenger_block)` (отказывает в `""` фрагменту,
  который не начинается с одного `/` или начинается с `//`/`/\`; для
  `/search/<ROUTE><блок>…` подменяет блок пассажиров; ставит `marker` из
  `AVIASALES_PARTNER_ID` ровно один раз), `_with_route_link(ticket, block)` (дописывает
  ссылку из `origin/destination/departure_at/return_at`, если `booking_link` пуст),
  `_price_summary(tickets)` (`None` на пустом).
- `get_prices_calendar(origin, destination, departure_at, return_at, currency, market,
  group_by, adults, children, infants, trip_class)` → `get("/aviasales/v3/grouped_prices", …)`;
  payload `status, currency, passengers, trip_class, price_note, field_note,
  price_summary, data` (+`hint` на пустом).
- `tools/reference.py`: `_error(message, hint)` →
  `{"status": "error", "error", "total": 0, "returned": 0, "truncated": False, "data": [], "hint"?}`.
- `validation.py`: `InvalidArgumentError(message, hint)`, `iata_code(value, field, *, required=True)`,
  `currency_code(value, default)`, `two_letter_code(value, field, default="")`
  (2 латинские буквы, иначе ошибка), `one_of(...)`.
- `config.settings`: `aviasales_locale` (умолч. `"en"`), `aviasales_market` (`""`),
  `aviasales_default_currency` (`"rub"`), `aviasales_partner_id`.
- `server.py`: тулы регистрируются циклом по кортежу `_TOOLS` с `_READ_ONLY`
  аннотациями; `instructions` сервера советуют `lookup_cities`/`find_nearest_airports`.
- Тестовый env (`tests/conftest.py`): `AVIASALES_API_TOKEN=test-token-for-testing`,
  `AVIASALES_PARTNER_ID=12345`.
- Базовый прогон на `2d39aca` в образе, `-u 1002:1002`, `--network none`:
  `ruff` чисто, `225 passed`, coverage 97.22% (порог CI 90%).
- Smoke постановщика на базе: падает (14 провалов) — ожидаемо.

## Контракт (его проверяет smoke постановщика — имена дословно)

### `api/client.py`
- Новая константа `PLACES_URL = "https://autocomplete.travelpayouts.com/places2"`.
- Новая функция **`async def get_places(params: dict[str, Any]) -> Any`** — GET на
  `PLACES_URL` с теми же ретраями и переводом ошибок, что у `get`, **но без заголовка
  `X-Access-Token`** (токен не нужен этому хосту и не должен туда уходить). Реализация —
  обобщить `_request` (например, параметры `url`/`send_token`), не копировать цикл
  ретраев. Поведение `get()` не меняется.

### `tools/places.py` (новый модуль) — тул **`find_places`**
```
find_places(
    term: str,
    types: list[Literal["city", "airport", "country"]] | None = None,
    locale: str | None = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict
```
- `term` обрезается по краям; меньше 2 символов → `InvalidArgumentError` с `hint`
  (текст ошибки называет `term`), API не зовётся.
- `types`: `None` → `["city", "airport"]`; дубликаты убираются с сохранением порядка;
  значение вне трёх допустимых (прямой вызов мимо схемы) → `InvalidArgumentError`.
- `locale`: `validation.two_letter_code(locale, "locale", settings.aviasales_locale)`.
- Запрос: `get_places({"term": term, "locale": locale, "types[]": types})` — httpx
  кодирует список повторяемым параметром.
- Не список в ответе → `ApiError` (через `guard` → payload ошибки с `hint`).
  Элементы, не являющиеся dict, отбрасываются.
- Каждая строка — только поля из белого списка, если они есть в строке:
  `type, code, name, city_code, city_name, country_code, country_name, state_code,
  main_airport_name, coordinates`. Порядок строк — как у апстрима.
- Ответ: `{"status": "ok", "term", "locale", "types", "total", "returned",
  "truncated", "data"}`; `total` — сколько строк пришло, `returned` — сколько отдано
  (≤ `limit`), `truncated = returned < total`. Пусто → тот же `status: "ok"`,
  `data: []` и `hint` (короче `term`, другой `locale`, `lookup_cities`).
- Ошибки — через `@guard(reference._error, hint=…)` (форма с `total/returned/truncated`).
- Докстринг: однострочное резюме, затем отдельное предложение `Use when …`
  (название города/аэропорта/страны → IATA-код, быстрее и легче `lookup_cities`),
  отсылки к `lookup_cities` / `find_nearest_airports`, секции `Args:`/`Returns:`.

### `tools/offers.py` (новый модуль) — тул **`get_special_offers`**
```
get_special_offers(
    origin: str,
    destination: str | None = None,
    airline: str | None = None,
    currency: str | None = None,
    market: str | None = None,
    locale: str | None = None,
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
    limit: Annotated[int, Field(ge=1, le=100)] = 30,
) -> dict
```
- `origin` **обязателен** (`validation.iata_code(origin, "origin")`): без него API
  подставит город по IP сервера — молча неверный ответ. `destination` —
  `iata_code(..., required=False)`.
- `airline` — новый валидатор **`validation.airline_code(value, field="airline")`**:
  `None`/пусто → `None`; ровно 2 символа `[A-Za-z0-9]` → верхний регистр; иначе
  `InvalidArgumentError` с `hint`, называющим `lookup_airlines`.
- `currency`/`market`/`locale` — как у соседних тулов (`currency_code`,
  `two_letter_code(..., settings.aviasales_market)`,
  `two_letter_code(..., settings.aviasales_locale)`).
- Запрос: `get("/aviasales/v3/get_special_offers", origin=…, destination=…, airline=…,
  currency=…, market=…, locale=…)`.
- Строка ответа: поля `origin, origin_name, origin_airport, destination,
  destination_name, destination_airport, airline, airline_title, flight_number,
  departure_at, return_at, duration, price, title, mini_title` (какие есть) +
  `booking_link`. `link`, `color`, `signature`, `search_id` в ответ НЕ попадают.
- `booking_link`: фрагмент `link` из строки; если это строка, начинается с одного `/`,
  второй символ не `/` и не `\`, и НЕ начинается с `/search/` — дописать спереди
  `/search` (вид из документации `/LON1409BCN1?…` → `/search/LON1409BCN1?…`). Затем
  `_build_booking_link(fragment, block)`; при пустом результате —
  `_with_route_link`. Ссылка никогда не уводит с `www.aviasales.ru`.
- Ответ (контракт ценовых тулов из AGENTS.md): `{"status": "ok", "currency",
  "passengers", "trip_class", "price_note", "field_note", "price_summary", "total",
  "returned", "data"}`; `limit` обрезает `data`. Пусто → `price_note` остаётся,
  `price_summary: None`, есть `hint` (без `destination`/`airline`, либо
  `get_latest_prices` / `get_city_directions`).
- Ошибки — `@guard(_error_response, hint=_API_ERROR_HINT)` из `flights.py`.
- Докстринг с `Use when …` (промо-тарифы/«горящие» предложения из города), пометкой,
  что цены за взрослого в экономе, `Args:`/`Returns:`.

### `get_prices_calendar` — длительность поездки
- Новые параметры в конце сигнатуры:
  `min_trip_duration: Annotated[int | None, Field(ge=1, le=365)] = None`,
  `max_trip_duration: Annotated[int | None, Field(ge=1, le=365)] = None` (дни).
- Новый валидатор **`validation.trip_duration_range(min_days, max_days)`** →
  `(min, max)`: каждое — `None` или целое 1..365 (bool не целое), иначе
  `InvalidArgumentError` с именем параметра в тексте; оба заданы и `min > max` →
  `InvalidArgumentError`, текст называет `min_trip_duration`, `hint` — поменять местами.
  Вызывается ДО запроса.
- Передаются в `grouped_prices` как `min_trip_duration` / `max_trip_duration` (только
  заданные; `get()` уже выкидывает `None`).
- В payload ключ `"trip_duration": {"min": …, "max": …}` — ТОЛЬКО если задан хотя бы
  один (незаданный — `None`); иначе ключа нет.
- Докстринг: `Args:` для обоих (поездка «на 10–14 дней»: оставить `return_at`
  пустым, `departure_at` — месяц).

### Регистрация и метаданные
- `server.py`: оба тула в `_TOOLS` (`find_places` — в блок reference,
  `get_special_offers` — в блок flight); `instructions` сервера: имя места → сначала
  `find_places`, затем `lookup_cities`/`find_nearest_airports`.
- `lookup_cities` и `lookup_airports`: в докстринг одна фраза-отсылка к `find_places`.
- Версия `0.5.3` → **`0.6.0`**: `pyproject.toml`, `server.json` (`version`, OCI
  `identifier` `ghcr.io/stufently/aviasales-mcp:0.6.0`, pypi `version`).
- `mcpb/manifest.json`: +2 записи `tools` (однострочное описание, как у соседей).
- `.github/workflows/ci.yml`: ожидание 15 тулов (`[ "$count" = 15 ]` и текст ошибки).
- `.github/site/site.toml`: «Thirteen»/«thirteen» → «Fifteen»/«fifteen»; пункт про
  разрешение имён упоминает `find_places`.
- `README.md`: строки в таблицы тулов (flight — `get_special_offers`, reference —
  `find_places`), абзац про `min_trip_duration`/`max_trip_duration`, абзац про
  `find_places` (публичный хост без токена, до 20 результатов). Историческую строку
  проверки «Verified 2026-10-14: 13 tools» и пример пина `:0.5.3` НЕ трогать.
- `AGENTS.md`: в Layout — два новых модуля; в Gotchas — autocomplete живёт на
  `autocomplete.travelpayouts.com/places2`, без токена, `types[]` повторяемый, голый
  `types` игнорируется, `/aviasales/v3/autocomplete` — 404; у special offers `origin`
  без значения берётся по IP сервера.
- `CHANGELOG.md`: секцию `## Unreleased` переименовать в `## 0.6.0 — 2026-11-08`
  (её текущее содержимое не трогать) и добавить в неё `### Added` с тремя пунктами
  (два тула и длительность поездки).

## Что сделать (тесты)

Тесты с `respx`, без сети. Имена ДОСЛОВНО — их собирает критерий AC-003:
- `tests/test_places.py::test_find_places_sends_types_without_token` — `types[]`
  по умолчанию `city,airport`, `term`/`locale` в запросе, заголовка `X-Access-Token`
  нет, `api.travelpayouts.com` не вызывается.
- `tests/test_places.py::test_find_places_limit_and_whitelist` — `limit` режет,
  `total/returned/truncated` верные, служебные поля (`id, index_strings, weight,
  cases, city_cases, country_cases`) выброшены, нужные — на месте.
- `tests/test_places.py::test_find_places_dedups_types` — `["country","country"]` →
  один `types[]=country`.
- `tests/test_places.py::test_find_places_rejects_short_term` — `" l "` → ошибка,
  ноль запросов.
- `tests/test_places.py::test_find_places_non_list_is_error` — `{"oops": 1}` →
  `status: "error"` с `hint`.
- `tests/test_places.py::test_find_places_empty_has_hint`.
- `tests/test_client.py::test_get_places_retries_5xx_without_token` — 500 затем 200:
  результат второго ответа, оба запроса без `X-Access-Token` (заглушить
  `asyncio.sleep`/бэкофф, как соседние тесты ретраев).
- `tests/test_offers.py::test_special_offers_formats_rows_and_link` — пример из
  документации, `adults=2` → ссылка `https://www.aviasales.ru/search/LON1409BCN2?…`,
  `marker=12345` один раз, служебные поля выброшены, `price_note`/`price_summary`.
- `tests/test_offers.py::test_special_offers_keeps_search_prefixed_link` — `link`
  уже вида `/search/…` не получает второй `/search`.
- `tests/test_offers.py::test_special_offers_hostile_link` — `@evil.example/x` и
  `//evil.example/x` → ссылка не уходит с `www.aviasales.ru`.
- `tests/test_offers.py::test_special_offers_empty_keeps_price_note`.
- `tests/test_offers.py::test_special_offers_requires_origin` — ноль запросов.
- `tests/test_offers.py::test_special_offers_rejects_bad_airline` — `S77`, `S`, `S-`.
- `tests/test_offers.py::test_special_offers_limit` — 3 строки, `limit=2`.
- `tests/test_flights.py::test_prices_calendar_trip_duration_params` — оба, один,
  ни одного (ключа `trip_duration` нет).
- `tests/test_flights.py::test_prices_calendar_trip_duration_rejects_bad_range` —
  `min>max`, `0`, `366`; ноль запросов.
- `tests/test_validation.py::test_airline_code`.
- `tests/test_validation.py::test_trip_duration_range`.
- `tests/test_server.py::test_every_tool_is_registered` — дополнить двумя именами.

## Не трогать

- `docs/specs/places-offers.md` и `docs/specs/places-offers-smoke.py` — не править
  (уже закоммичены постановщиком). Остальные файлы `docs/specs/` тоже.
- `TASKS.md` (закроет постановщик), `Dockerfile`, `.github/workflows/{release,registry,pages}.yml`,
  `.github/dependabot.yml`, `scripts/`, `glama.json`, `SECURITY.md`, `LICENSE`, `.env.example`.
- `api/client.py`: поведение `get()` и существующих ретраев/ошибок не меняется.
- Существующие тулы, кроме `get_prices_calendar` (параметры), `lookup_cities` /
  `lookup_airports` (одна фраза в докстринге), — без изменений.
- Зависимости в `pyproject.toml` не трогать (только `version`).
- Разрешённые пути изменений: `src/aviasales_mcp/api/client.py`,
  `src/aviasales_mcp/validation.py`, `src/aviasales_mcp/server.py`,
  `src/aviasales_mcp/tools/{flights,reference,places,offers}.py`, `tests/**`,
  `README.md`, `AGENTS.md`, `CHANGELOG.md`, `pyproject.toml`, `server.json`,
  `mcpb/manifest.json`, `.github/workflows/ci.yml`, `.github/site/site.toml`.

## Критерии приёмки

Все команды — из корня клона.

- **AC-001 — ruff и полный сьют зелёные в Docker без сети, coverage не ниже 90.**
  `bash -c 'docker run --rm --network none -u 1002:1002 -v "$PWD":/app -w /app -e PYTHONPATH=/app/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e COVERAGE_FILE=/tmp/.coverage aviasales-mcp-dev:offers sh -c "ruff check --no-cache src/ tests/ && python -m pytest -q -p no:cacheprovider --cov=aviasales_mcp --cov-report=term-missing --cov-fail-under=90"'`
- **AC-002 — независимый smoke постановщика проходит.**
  `bash -c 'docker run --rm --network none -u 1002:1002 -v "$PWD":/app -w /app -e PYTHONPATH=/app/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 aviasales-mcp-dev:offers python docs/specs/places-offers-smoke.py'`
- **AC-003 — обязательные тесты существуют и зелёные.**
  `bash -c 'docker run --rm --network none -u 1002:1002 -v "$PWD":/app -w /app -e PYTHONPATH=/app/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 aviasales-mcp-dev:offers python -m pytest -q -p no:cacheprovider tests/test_places.py::test_find_places_sends_types_without_token tests/test_places.py::test_find_places_limit_and_whitelist tests/test_places.py::test_find_places_dedups_types tests/test_places.py::test_find_places_rejects_short_term tests/test_places.py::test_find_places_non_list_is_error tests/test_places.py::test_find_places_empty_has_hint tests/test_client.py::test_get_places_retries_5xx_without_token tests/test_offers.py::test_special_offers_formats_rows_and_link tests/test_offers.py::test_special_offers_keeps_search_prefixed_link tests/test_offers.py::test_special_offers_hostile_link tests/test_offers.py::test_special_offers_empty_keeps_price_note tests/test_offers.py::test_special_offers_requires_origin tests/test_offers.py::test_special_offers_rejects_bad_airline tests/test_offers.py::test_special_offers_limit tests/test_flights.py::test_prices_calendar_trip_duration_params tests/test_flights.py::test_prices_calendar_trip_duration_rejects_bad_range tests/test_validation.py::test_airline_code tests/test_validation.py::test_trip_duration_range tests/test_server.py::test_every_tool_is_registered'`
- **AC-004 — модули тулов не ходят в httpx напрямую.**
  `bash -c '! grep -nE "^(import httpx|from httpx)" src/aviasales_mcp/tools/*.py'`
- **AC-005 — изменены только разрешённые пути (от коммита спеки).**
  `bash -c 'B=$(git log --format=%H --grep="Add places-offers spec" -n 1) && test -n "$B" && test -z "$(git diff --name-only "$B" HEAD | grep -Ev "^(src/aviasales_mcp/(api/client|validation|server|tools/(flights|reference|places|offers))\.py|tests/.*|README\.md|AGENTS\.md|CHANGELOG\.md|pyproject\.toml|server\.json|mcpb/manifest\.json|\.github/workflows/ci\.yml|\.github/site/site\.toml)$")"'`
- **AC-006 — спека и smoke постановщика не изменены.**
  `bash -c 'B=$(git log --format=%H --grep="Add places-offers spec" -n 1) && test -n "$B" && git diff --quiet "$B" HEAD -- docs/specs/'`
- **AC-007 — дерево чистое, работа закоммичена.**
  `bash -c 'test -z "$(git status --porcelain -- . ":(exclude)report.json" ":(exclude)report-blocked.md")"'`

## Контракт отчёта

`report.json` в КОРНЕ клона, untracked (не коммитить). Записей в `criteria` ровно
семь: AC-001…AC-007, `command` — строка критерия из этой спеки посимвольно.

```json
{"criteria": [{"id": "AC-001", "status": "pass|fail|blocked",
               "command": "<команда критерия>", "rc": 0, "note": "…"}]}
```

`blocked` — штатный исход, когда среда не даёт выполнить критерий (нет Docker, нет
образа): `"rc": null`, в `note` — дословная ошибка. Обходить несовместимость
ЗАПРЕЩЕНО: подмена окружения (`pip install` в контейнере вместо образа,
`--no-deps`, `--break-system-packages`), глушители кода (`|| true`, `; true`,
`set +e`), `sudo`, `git push` — приёмщик снимает веху целиком.

## Контракт на невыполнимое

Если контракт выше противоречит существующему коду или тестам так, что выполнить
его без нарушения «Не трогать» нельзя (например, FastMCP не принимает
`list[Literal[...]] | None` в схеме), — остановись, ничего не обходи, опиши
противоречие в `report-blocked.md` в корне клона и отметь затронутые критерии
`blocked`. Править smoke постановщика, чтобы он прошёл, запрещено. Реальные вызовы
API ради проверки формата — запрещены.

## Стыки с соседними вехами

- Релиз `v0.6.0` (тег, PyPI, GHCR, MCP registry) — за владельцем, вне вехи.
- Пункт TASKS.md про real-time search (`/v1/flight_search`) этой вехой не затрагивается.
