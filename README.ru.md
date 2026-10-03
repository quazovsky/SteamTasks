<div align="center">

# SteamTasks 🎮

<p align="center">
  <b>Легковесный эмулятор игровых сессий для Discord Quests & Orbs.</b><br>
  Автоматически выполняет задания Discord и начисляет сферы (Orbs) без необходимости скачивать десятки и сотни гигабайт игр на диск.<br><br>
  <a href="README.ru.md">🇷🇺 Русский</a> • <a href="README.md">🇬🇧 English</a>
</p>

[![Release](https://img.shields.io/github/v/release/quazovsky/SteamTasks?logo=github&color=ff7a18)](https://github.com/quazovsky/SteamTasks/releases)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?logo=windows)](https://microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen?logo=python)](https://python.org)
[![Discord](https://img.shields.io/badge/Discord-IPC%20v10%20%7C%20Quests-5865F2?logo=discord)](https://discord.com)
[![UI](https://img.shields.io/badge/UI-Localhost%208787%20%2B%20Win32-ff7a18)](http://127.0.0.1:8787)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

</div>

---

## ⚡ Возможности

* **100% зачёт Discord Quests и начисление сфер**: Эмуляция нативных окон верхнего уровня и подключение к Discord IPC на одном PID для полного прохождения проверок Discord.
* **Автоматический обход защит (Bypass Engine)**:
  * Каталожные пути и оригинальные имена процессов из базы Discord (24 500+ игр).
  * Поддержка подкаталогов (Unreal Engine / Frostbite `win64/...`, например *Marvel Rivals*, *Delta Force*).
  * Обход лаунчеров для серии EA Sports FC / FIFA.
  * Эмуляция реестра и манифестов Epic Games Store SKU.
* **Авто-синхронизация квестов**: В один клик подтягивает активные задания из Discord, отображает прогресс в реальном времени и готовит нужные исполняемые файлы.
* **Современный веб-дашборд (`http://127.0.0.1:8787`)**:
  * Графитовая тёмная и контрастная светлая темы с быстрым переключением.
  * Поддержка русского и английского языков.
  * Умная очередь игр с таймером авто-переключения (например, по 15 минут на игру).
  * Поиск по каталогу 24 000+ игр Discord.
* **Современное окно эмуляции**:
  * Нативное Win32-окно с аппаратным сглаживанием DWM.
  * Никаких устаревших рамок Windows 7 / Aero при смене фокуса.
  * Чёткий рендеринг текста и оригинальная иконка игры.

---

## 🚀 Быстрый старт

### Вариант 1. Портативная версия (Без установки)

1. Скачайте архив **`SteamTasks-v3.1.0-portable.zip`** из раздела [GitHub Releases](https://github.com/quazovsky/SteamTasks/releases/latest).
2. Распакуйте архив в любую папку.
3. Запустите **`RUN.cmd`** (или `worthlesstask.exe`).
4. В браузере автоматически откроется дашборд: **`http://127.0.0.1:8787`**.

### Вариант 2. Запуск из исходников (Python)

Требуется установленный Python 3.10+:

```powershell
# Клонируйте репозиторий
git clone https://github.com/quazovsky/SteamTasks.git
cd SteamTasks

# Запустите веб-панель
python -m worthlesstask web --open
```

---

## 🕹️ Как пользоваться

1. **Запустите SteamTasks** и убедитесь, что приложение Discord запущено на компьютере.
2. В веб-панели нажмите кнопку **«Синхронизировать задания»** (`Sync Quests`):
   * SteamTasks автоматически определит ваши активные квесты Discord, покажет награды и создаст нужные мини-воркеры.
3. Нажмите **«Запустить»** (`Start`) напротив нужной игры:
   * Откроется аккуратное окно эмулятора игры.
   * Discord моментально определит статус «Играет в...» и начнет начислять время.
4. **Очередь заданий (Queue)**:
   * Добавьте несколько игр в очередь кнопкой **«+ В очередь»**.
   * Укажите время на игру (по умолчанию 15 минут).
   * Нажмите **«Запустить очередь»** — программа сама поочередно выполнит все квесты и остановится, когда всё будет готово!

---

## 💻 Управление через консоль (CLI)

```powershell
# Проверить подключение к Discord и готовность системы
python -m worthlesstask doctor

# Синхронизировать активные задания Discord
python -m worthlesstask quests sync --auto-add

# Запустить конкретную игру
python -m worthlesstask play ea-sports-fc-27

# Запустить очередь с интервалом 15 минут
python -m worthlesstask queue marvel-rivals delta-force --minutes 15 --start

# Остановить текущую сессию
python -m worthlesstask stop
```

---

## 📄 License / Лицензия

Distributed under the MIT License. Распространяется под лицензией MIT.
