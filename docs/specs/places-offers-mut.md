# Мутационный прогон: веха places-offers (aviasales-mcp)

- Клон: `/home/deploy/exec-clones/aviasales-mcp-places-offers-mut`, ветка
  `feat/places-offers-duration` (HEAD `9bd058a`). Код писал Codex, мутации гоняешь ты (Qwen).
- **Push в origin запрещён**, merge/deploy/релизы запрещены. `git pull` не делать.
  Реальных вызовов API нет и не нужно. Ничего не коммитить.
- Тесты (образ уже собран; pip не ставить):
  `docker run --rm --network none -u 1002:1002 -v "$PWD":/app -w /app -e PYTHONPATH=/app/src -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 aviasales-mcp-dev:offers python -m pytest -q -p no:cacheprovider <тесты>`

## Задача

Проверить, что НОВЫЕ тесты вехи ловят поломку нового кода. Для каждой мутации
ниже: (1) убедиться, что целевые тесты зелёные на чистом дереве; (2) проверить,
что заменяемый фрагмент встречается в файле ровно один раз; (3) наложить
мутацию; (4) прогнать целевые тесты (файлы целиком из списка); (5) записать,
упал ли тест и НА КАКОМ ассерте (причина падения должна относиться к мутации,
а не к ошибке импорта/синтаксиса); (6) откатить `git checkout -- <файл>` и
убедиться, что `git status --porcelain` показывает только эту спеку.

Целевые тесты: `tests/test_places.py tests/test_offers.py tests/test_client.py tests/test_flights.py tests/test_validation.py tests/test_server.py`

Мутации (по одной за раз; пути от `src/aviasales_mcp/`; фрагменты — как они стоят в файле):

- M1 `api/client.py`: строка `    if send_token:` → `    if True:`
- M2 `tools/places.py`: `requested_types = ["city", "airport"] if types is None else types` → `requested_types = ["city"] if types is None else types`
- M3 `tools/places.py`: `types = list(dict.fromkeys(requested_types))` → `types = list(requested_types)`
- M4 `tools/places.py`: `if len(term) < 2:` → `if len(term) < 1:`
- M5 `tools/places.py`: `{key: row[key] for key in _PLACE_FIELDS if key in row}` → `dict(row)`
- M6 `tools/places.py`: `"truncated": len(data) < len(rows),` → `"truncated": False,`
- M7 `tools/places.py`: `raise ApiError("Place autocomplete returned a non-list response")` → `rows = []`
- M8 `tools/places.py`: `][:max(1, min(limit, 20))]` → `][:20]`
- M9 `tools/places.py`: `"locale": locale, "types[]": types}` → `"locale": locale, "types": types}`
- M10 `tools/offers.py`: `and not fragment.startswith("/search/")` → `and True`
- M11 `tools/offers.py`: `fragment = f"/search{fragment}"` → `fragment = fragment`
- M12 `tools/offers.py`: `and fragment[1:2] not in ("/", "\\")` → `and True`
- M13 `tools/offers.py`: `return _with_route_link(ticket, block)` → `return ticket`
- M14 `tools/offers.py`: `ticket = {key: row[key] for key in _OFFER_FIELDS if key in row}` → `ticket = dict(row)`
- M15 `tools/offers.py`: `rows[:max(1, min(limit, 100))]` → `rows`
- M16 `tools/offers.py`: `"price_note": _price_note(trip_class),` → пустая строка (удалить фрагмент)
- M17 `tools/offers.py`: `origin = validation.iata_code(origin, "origin")` → `origin = validation.iata_code(origin, "origin", required=False)`
- M18 `validation.py`: `type(value) is not int or not 1 <= value <= 365` → `not 1 <= value <= 365`
- M19 `validation.py`: `min_days > max_days` → `False and min_days > max_days`
- M20 `validation.py`: `r"[A-Za-z0-9]{2}"` → `r"[A-Za-z0-9]{2,3}"`
- M21 `validation.py`: `return value.strip().upper()` → `return value.strip()`
- M22 `tools/flights.py`: строку `        max_trip_duration=max_trip_duration,` (аргумент вызова `get`) удалить
- M23 `tools/flights.py`: `if min_trip_duration is not None or max_trip_duration is not None:` → `if min_trip_duration is not None:`

Если фрагмент не найден ровно один раз — мутацию пометь `not_applied` с
причиной, не придумывай свою.

## Результат

Файл `mutation-report.md` в корне клона (НЕ коммитить): таблица
`id | применилась | убит/выжил | тест и строка ассерта, на которой упал`.
Для выжившего — короткое объяснение, какого ассерта не хватает. Код и тесты не
правь. В конце `git status --porcelain` должен показывать только
`mutation-report.md` и эту спеку.
