# SteamTasks 🎮

> **Lightweight game session emulator for Discord Quests & Orbs.**  
> Automatically completes Discord desktop quests and earns Orbs without downloading tens or hundreds of gigabytes of games.

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?logo=windows)](https://microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen?logo=python)](https://python.org)
[![Discord](https://img.shields.io/badge/Discord-IPC%20v10%20%7C%20Quests-5865F2?logo=discord)](https://discord.com)
[![UI](https://img.shields.io/badge/UI-Localhost%208787%20%2B%20Win32-ff7a18)](http://127.0.0.1:8787)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## ⚡ Features

* **100% Discord Quests Completion & Orb Rewards**: Emulates genuine game windows and connects to Discord IPC on the same PID to satisfy Discord's detection pipeline.
* **Automatic Bypass Engine**:
  * Exact catalogue binary names and paths from Discord's 24,500+ game database.
  * Subfolder executables bypass (e.g., Unreal Engine / Frostbite `win64/...` titles like *Marvel Rivals*, *Delta Force*).
  * EA Sports FC / FIFA series and launcher SKU bypasses.
  * Epic Games Store registry and SKU simulation.
* **Automatic Quest Synchronization**: Scans enrolled Discord quests in one click, displays live completion progress and orb rewards, and prepares lightweight worker executables.
* **Modern Web Dashboard (`http://127.0.0.1:8787`)**:
  * Graphite dark mode and high-contrast light mode with instant toggle.
  * English and Russian language support.
  * Multi-game automated queue with configurable timers (e.g. 15 min per quest).
  * Instant search across 24,000+ Discord games.
* **Modern Frameless Window**:
  * Native Win32 window with hardware DWM frame compositing.
  * No legacy Windows 7 / Aero title bar artifacts on focus change.
  * Crisp font rendering and game icon integration.

---

## 🚀 Quick Start (English)

### Option 1. Portable Version (No Installation)

1. Open the `dist\worthlesstask` folder (or extract the latest release archive).
2. Run **`RUN.cmd`** (or `worthlesstask.exe`).
3. The dashboard will automatically open in your browser: **`http://127.0.0.1:8787`**.

### Option 2. Run from Source (Python)

Requires Python 3.10+:

```powershell
# Clone the repository
git clone https://github.com/quazovsky/SteamTasks.git
cd SteamTasks

# Launch the dashboard
python -m worthlesstask web --open
```

---

## 🕹️ How to Use

1. **Launch SteamTasks** and make sure Discord is running and logged in on your PC.
2. In the dashboard, click **«Sync Quests»**:
   * SteamTasks scans your enrolled Discord quests, displays orb rewards, and sets up worker executables.
3. Click **«Start»** next to the desired game:
   * A native game window opens and Discord immediately registers you as "Playing". Time starts counting towards the quest reward.
4. **Automated Queue**:
   * Add games to the queue using **«+ Add to queue»**.
   * Set minutes per game (default is 15 minutes).
   * Click **«Start Queue»** — SteamTasks will automatically rotate through each game until all quests are complete!

---

## 💻 CLI Commands

SteamTasks can also be controlled entirely via command line:

```powershell
# Check Discord connection and system readiness
python -m worthlesstask doctor

# Sync active Discord quests
python -m worthlesstask quests sync --auto-add

# Launch a specific game
python -m worthlesstask play ea-sports-fc-27

# Run queue with 15-minute intervals
python -m worthlesstask queue marvel-rivals delta-force --minutes 15 --start

# Stop current session
python -m worthlesstask stop
```

---
---

# SteamTasks (Русская версия) 🎮

> **Легковесный эмулятор игровых сессий для Discord Quests & Orbs.**  
> Автоматически выполняет задания Discord и начисляет сферы (Orbs) без необходимости скачивать десятки и сотни гигабайт игр на диск.

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

## 🚀 Быстрый старт (На русском)

### Вариант 1. Портативная версия (Без установки)

1. Откройте папку `dist\worthlesstask` (или распакуйте архив релиза).
2. Запустите **`RUN.cmd`** (или `worthlesstask.exe`).
3. В браузере автоматически откроется дашборд: **`http://127.0.0.1:8787`**.

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
