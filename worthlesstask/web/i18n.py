"""Stable error codes for the local dashboard.

The server raises its messages in one language. Rather than threading a locale
through every layer that can fail, each known failure is mapped to a stable code
and the page renders that code in whichever language it is currently showing.

Two kinds of message reach the client:

* **Fixed** — the whole string is known ahead of time ("Очередь должна быть
  списком игр"). Matched exactly.
* **Interpolated** — the string carries a value ("Игра 'ghost' не найдена в
  библиотеке"). Matched by prefix, since the tail changes per call.

A code is part of the contract: renaming one is a breaking change for the UI.
An unmatched message is not an error — the page falls back to the server's own
text, so a new message still reaches the user readably.
"""

from __future__ import annotations

#: Exact message -> code.
EXACT_CODES = {
    "Некорректный идентификатор игры": "slug.invalid",
    "Поисковый запрос должен быть не длиннее 256 символов": "search.too_long",
    "Укажите название игры до 256 символов": "game.name_length",
    "Некорректный Application ID": "game.bad_id",
    "Выбранная карточка устарела. Повторите поиск.": "game.stale",
    "Ожидается имя .exe без пути и командных символов": "exe.bad_name",
    "Очередь должна быть списком игр": "queue.not_list",
    "Очередь должна быть списком до 100 игр": "queue.too_long",
    "Укажите целое число минут от 1 до 1440": "queue.minutes",
    "Игра не найдена": "game.missing",
    "Иконка должна быть не больше 2 МиБ": "icon.too_large",
    "Формат файла не соответствует иконке: ICO, PNG, JPG, BMP или WebP": "icon.format",
    "Дождитесь завершения запуска или остановки": "busy.operation",
    "Другая операция ещё выполняется. Дождитесь её завершения.": "busy.other",
    "Сначала остановите активную сессию": "session.active",
    "Каталог не содержит executable для этой игры. Автоматический запуск недоступен.": "exe.unavailable",
    "Разрешены только запросы из локальной панели": "request.origin",
    "Некорректный размер запроса (максимум 4 МиБ)": "request.size",
    "Потоковая передача запроса не поддерживается": "request.streaming",
    "Запрос получен не полностью": "request.truncated",
    "Некорректный JSON запроса": "request.json",
    "Тело запроса должно быть JSON-объектом": "request.object",
    "Внутренняя ошибка. Подробности в журнале приложения.": "server.internal",
    "Имя файла должно быть строкой": "exe.bad_type",
    "Иконка не загружена": "icon.missing",
    "Иконка слишком большая": "icon.too_large",
    "Не найдено": "http.not_found",
    "Панель допускает только локальный адрес 127.0.0.1": "request.local_only",
    "Нет свободного локального порта": "server.no_port",
    "Не удалось открыть процесс для остановки": "process.stop_failed",
    "Процесс запущен, но RPC ещё не подтверждён. Проверьте настольный Discord.": "rpc.unconfirmed",
    "Application ID должен содержать 17–20 цифр": "game.bad_id_length",
    "Не найдена папка приложения или файл библиотеки": "app.missing",
    "Подготовленный файл не является Windows EXE": "exe.not_windows",
    "Ожидался список игр": "library.bad_shape",
    "Недопустимый идентификатор в библиотеке": "library.bad_id",
    "Иконка должна находиться в папке icons": "icon.not_in_folder",
    "Выберите непустую иконку размером до 2 МиБ": "icon.empty",
    "Нельзя использовать символическую ссылку вместо EXE": "exe.symlink_instead",
}

#: Prefix -> code, for messages that interpolate a value. Longest prefix wins.
PREFIX_CODES = {
    "Игра '": "game.missing",
    "EXE не найден:": "exe.missing",
    "Проверьте параметры игры:": "game.invalid",
    "Не удалось создать EXE:": "exe.build_failed",
    "Не удалось сохранить библиотеку:": "library.save_failed",
    "Не удалось прочитать библиотеку:": "library.load_failed",
    "Процесс завершился с кодом": "process.exited",
    "Очередь остановлена:": "queue.stopped",
    "Нельзя записать EXE через символическую ссылку:": "exe.symlink_blocked",
    "Файл уже существует и не принадлежит worthlesstask:": "exe.foreign_file",
}

#: Order matters: longest first, so a specific prefix beats a general one.
_PREFIX_ORDER = sorted(PREFIX_CODES, key=len, reverse=True)

#: Codes the page translates. Unknown codes fall back to the server's own text.
TRANSLATIONS = {
    "en": {
        "slug.invalid": "Invalid game identifier",
        "search.too_long": "The search query must be 256 characters or fewer",
        "game.name_length": "Enter a game name of up to 256 characters",
        "game.bad_id": "Invalid Application ID",
        "game.stale": "That entry is out of date. Search again.",
        "game.missing": "Game not found",
        "game.invalid": "Check the game's settings",
        "exe.bad_name": "Expected an .exe name with no path or shell characters",
        "exe.missing": "EXE not found",
        "exe.unavailable": "The catalogue has no executable for this game. Automatic start is unavailable.",
        "exe.build_failed": "Could not build the EXE",
        "queue.not_list": "The queue must be a list of games",
        "queue.too_long": "The queue must hold at most 100 games",
        "queue.minutes": "Enter a whole number of minutes between 1 and 1440",
        "icon.too_large": "The icon must be 2 MiB or smaller",
        "icon.format": "Unsupported icon format: ICO, PNG, JPG, BMP or WebP",
        "busy.operation": "Wait for the current start or stop to finish",
        "busy.other": "Another operation is still running. Wait for it to finish.",
        "session.active": "Stop the active session first",
        "library.save_failed": "Could not save the library",
        "library.load_failed": "Could not read the library",
        "request.origin": "Only requests from the local panel are allowed",
        "request.size": "Invalid request size (4 MiB maximum)",
        "request.streaming": "Streamed request bodies are not supported",
        "request.truncated": "Request body arrived incomplete",
        "request.json": "Malformed request JSON",
        "request.object": "The request body must be a JSON object",
        "server.internal": "Internal error. See the application log for details.",
        "exe.bad_type": "The file name must be a string",
        "icon.missing": "No icon uploaded",
        "http.not_found": "Not found",
        "request.local_only": "The panel accepts requests from 127.0.0.1 only",
        "server.no_port": "No free local port",
        "process.stop_failed": "Could not open the process to stop it",
        "rpc.unconfirmed": "The process is running, but Discord has not confirmed the RPC yet. Check the desktop Discord.",
        "game.bad_id_length": "The Application ID must be 17–20 digits",
        "app.missing": "The application folder or the library file was not found",
        "exe.not_windows": "The prepared file is not a Windows EXE",
        "library.bad_shape": "Expected a list of games",
        "library.bad_id": "Invalid identifier in the library",
        "icon.not_in_folder": "The icon must live in the icons folder",
        "icon.empty": "Choose a non-empty icon of up to 2 MiB",
        "exe.symlink_instead": "A symbolic link cannot be used instead of the EXE",
        "process.exited": "The process exited unexpectedly. See the application log for details.",
        "queue.stopped": "The queue stopped. See the application log for details.",
        "exe.symlink_blocked": "The EXE cannot be written through a symbolic link",
        "exe.foreign_file": "That file already exists and does not belong to worthlesstask",
    },
    "ru": {
        "slug.invalid": "Некорректный идентификатор игры",
        "search.too_long": "Поисковый запрос должен быть не длиннее 256 символов",
        "game.name_length": "Укажите название игры до 256 символов",
        "game.bad_id": "Некорректный Application ID",
        "game.stale": "Выбранная карточка устарела. Повторите поиск.",
        "game.missing": "Игра не найдена",
        "game.invalid": "Проверьте параметры игры",
        "exe.bad_name": "Ожидается имя .exe без пути и командных символов",
        "exe.missing": "EXE не найден",
        "exe.unavailable": "Каталог не содержит executable для этой игры. Автоматический запуск недоступен.",
        "exe.build_failed": "Не удалось создать EXE",
        "queue.not_list": "Очередь должна быть списком игр",
        "queue.too_long": "Очередь должна быть списком до 100 игр",
        "queue.minutes": "Укажите целое число минут от 1 до 1440",
        "icon.too_large": "Иконка должна быть не больше 2 МиБ",
        "icon.format": "Формат файла не соответствует иконке: ICO, PNG, JPG, BMP или WebP",
        "busy.operation": "Дождитесь завершения запуска или остановки",
        "busy.other": "Другая операция ещё выполняется. Дождитесь её завершения.",
        "session.active": "Сначала остановите активную сессию",
        "library.save_failed": "Не удалось сохранить библиотеку",
        "library.load_failed": "Не удалось прочитать библиотеку",
        "request.origin": "Разрешены только запросы из локальной панели",
        "request.size": "Некорректный размер запроса (максимум 4 МиБ)",
        "request.streaming": "Потоковая передача запроса не поддерживается",
        "request.truncated": "Запрос получен не полностью",
        "request.json": "Некорректный JSON запроса",
        "request.object": "Тело запроса должно быть JSON-объектом",
        "server.internal": "Внутренняя ошибка. Подробности в журнале приложения.",
        "exe.bad_type": "Имя файла должно быть строкой",
        "icon.missing": "Иконка не загружена",
        "http.not_found": "Не найдено",
        "request.local_only": "Панель допускает только локальный адрес 127.0.0.1",
        "server.no_port": "Нет свободного локального порта",
        "process.stop_failed": "Не удалось открыть процесс для остановки",
        "rpc.unconfirmed": "Процесс запущен, но RPC ещё не подтверждён. Проверьте настольный Discord.",
        "game.bad_id_length": "Application ID должен содержать 17–20 цифр",
        "app.missing": "Не найдена папка приложения или файл библиотеки",
        "exe.not_windows": "Подготовленный файл не является Windows EXE",
        "library.bad_shape": "Ожидался список игр",
        "library.bad_id": "Недопустимый идентификатор в библиотеке",
        "icon.not_in_folder": "Иконка должна находиться в папке icons",
        "icon.empty": "Выберите непустую иконку размером до 2 МиБ",
        "exe.symlink_instead": "Нельзя использовать символическую ссылку вместо EXE",
        "process.exited": "Процесс завершился с кодом — подробности в журнале приложения.",
        "queue.stopped": "Очередь остановлена — подробности в журнале приложения.",
        "exe.symlink_blocked": "Нельзя записать EXE через символическую ссылку",
        "exe.foreign_file": "Файл уже существует и не принадлежит worthlesstask",
    },
}


def code_for(message: str) -> str | None:
    """The stable code for a server message, or None when it has none."""
    text = str(message)
    if text in EXACT_CODES:
        return EXACT_CODES[text]
    for prefix in _PREFIX_ORDER:
        if text.startswith(prefix):
            return PREFIX_CODES[prefix]
    return None
