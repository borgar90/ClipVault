# ClipVault

ClipVault is a small Windows clipboard history tool for developers and power‑users.
It silently monitors your clipboard in the background, stores text snippets in a
local SQLite database, and gives you a quick GUI for browsing and re‑copying past
snippets.

The project is designed to be:

- **Windows‑native** – tray icon, single‑instance per user, optional autostart.
- **Zero‑setup for users** – distributed as a standalone `.exe` + installer.
- **Local‑only** – no network calls; all data lives on your machine.

---

## Features

- **Clipboard logging**
  - Watches the clipboard for text changes.
  - Ignores whatever was on the clipboard before the program started.
  - Stores snippets in `history.db` (SQLite).

- **Sun Valley‑style GUI**
  - Modern Win11‑like look via `sv-ttk` (light theme).
  - Search bar with placeholder (`Search snippets...`).
  - Sort toggle: *Newest ↓* / *Oldest ↑* based on snippet time.
  - Snippets rendered as distinct “cards” with a dedicated **Copy** button.

- **Grouping & interaction**
  - Snippets grouped by **local date** (not raw UTC) with per‑day headers.
  - Each date header is clickable to expand/collapse that day’s snippets.
  - Double‑click a card to open a full‑text detail window.
  - “Copy selected” behavior via the card’s Copy button.

- **Background mode + tray icon**
  - Closing the window (X) hides the GUI but keeps monitoring in the background.
  - A system tray icon stays active under “show hidden icons”.
  - Tray menu:
    - **Show ClipVault** – restore the main window.
    - **Quit** – stop monitoring and exit the app.

- **Export & maintenance**
  - **File → Export all snippets…** – save all snippets as CSV.
  - **File → Delete all snippets…** – wipe the history (asks for confirmation).

- **About dialog**
  - Shows the logo and app name.
  - Short introduction of *Borgar Flaen Stensrud*.
  - Clickable link to <https://borgar-stensrud.no/>.

---

## Project structure

- `copyhistory_core.py`
  - Pure “data layer” module.
  - Defines the `ClipItem` dataclass.
  - Handles all DB operations: `add_clip`, `fetch_clips`, `get_clip_by_id`,
    `get_all_clips`, `delete_all_clips`.
  - Uses SQLite with a `history.db` file next to the binaries (see Security).

- `copyhistory_gui.py`
  - Main GUI entry point.
  - Clipboard monitor thread (uses `pyperclip`).
  - Tkinter + ttk GUI styled via `sv-ttk`.
  - System tray icon (`pystray`) and single‑instance lock per user.
  - Uses functions from `copyhistory_core` for all DB interactions.

- `copyhistory.py`
  - Thin CLI wrapper around `copyhistory_core`.
  - Optional: monitor, list, and copy commands via the console.
  - Not needed for normal end‑users, but useful for debugging and power‑users.

- `ClipVault.spec`
  - PyInstaller spec file used to build the standalone `.exe`.

- `requirements.txt`
  - Python dependencies for development/building.

- `icon.png` / `logo.png` / `icon.ico`
  - Application icon and branding assets; used by the GUI, tray icon, and installer.

---

## Development environment

### Prerequisites

- Windows 11 (or 10) 64‑bit.
- Python 3.11+ (the project was developed with Python 3.11/3.14).
- PowerShell or cmd.

### Setup

```powershell
cd C:\Users\borga\Desktop\Dev\copyhistory
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Running the GUI in dev mode

```powershell
cd C:\Users\borga\Desktop\Dev\copyhistory
.venv\Scripts\activate
python copyhistory_gui.py
```

Behavior in dev is the same as in the packaged app:

- A single instance per OS user (second launch prints a message and exits).
- Clipboard logging starts immediately.
- Closing the window hides it and leaves the tray icon + logging active.

To really stop the app, right‑click the tray icon and choose **Quit**, or use
**File → Quit** from the main window.

---

## Building a standalone `.exe` (PyInstaller)

The goal is a self‑contained EXE that end‑users can run without Python installed.

### Install PyInstaller (once)

From your virtual environment:

```powershell
python -m pip install pyinstaller
```

### Build the EXE

From the project root:

```powershell
python -m PyInstaller `
  --name ClipVault `
  --windowed `
  --icon icon.ico `
  --add-data "icon.png;." `
  --add-data "logo.png;." `
  copyhistory_gui.py
```

This produces:

- `dist\ClipVault\ClipVault.exe` – the main executable.
- Bundled `icon.png` / `logo.png` alongside the exe.

The code uses a `resource_path()` helper so image paths work both in dev and from
the PyInstaller bundle.

---

## Windows installer (Inno Setup)

To give users a familiar installer with shortcuts and an optional autostart
checkbox, you can wrap `ClipVault.exe` with Inno Setup.

### 1) Create a license

Add a `license.txt` with terms similar to:

- Free to use.
- Free to distribute **unmodified** copies.
- No modifications / reverse engineering without author’s permission.
- No warranty (“as is”).

Inno Setup will show this and require acceptance before installation.

### 2) Inno Setup script (example)

Create `ClipVaultInstaller.iss` and adjust paths if needed:

```ini
#define MyAppName "ClipVault"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Borgar Flaen Stensrud"
#define MyAppURL "https://borgar-stensrud.no/"
#define MyAppExeName "ClipVault.exe"

[Setup]
AppId={{A0C8F2C1-1E3F-4C18-9E0E-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\ClipVault
DefaultGroupName=ClipVault
OutputBaseFilename=ClipVaultSetup
Compression=lzma
SolidCompression=yes
LicenseFile=license.txt
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start ClipVault when Windows starts"; \
  GroupDescription: "Additional options:"; Flags: unchecked

[Files]
Source: "dist\ClipVault\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ClipVault\icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ClipVault\logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ClipVault"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\ClipVault"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#MyAppName}"; \
  ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch ClipVault"; \
  Flags: nowait postinstall skipifsilent
```

Open this script in Inno Setup, compile it, and you’ll get a
`ClipVaultSetup.exe` installer that:

- Installs ClipVault into `Program Files`.
- Adds Start Menu (and optional Desktop) shortcuts.
- Optional autostart on login (per user).
- Shows and enforces your license terms.

---

## Security notes

- Clipboard snippets are stored unencrypted in `history.db`. Any process running
  as the same user (or an administrator) can technically read that file.
- The app does **not** send data over the network; it only writes locally.
- For stronger protection, a future version could:
  - Encrypt snippet contents at rest (e.g. using a per‑user DPAPI‑protected key
    or a user password).
  - Store the database under a per‑user application data directory instead of
    next to the EXE.

---

## License & attribution

- Copyright (c) 2025
  **Borgar Flaen Stensrud**.
- Free to use and free to distribute **unmodified** copies.
- Modifications, forks, reverse engineering, or re‑branding are not permitted
  without written permission from the author.
- The software is provided “as is”, without warranty of any kind; use at your
  own risk.
