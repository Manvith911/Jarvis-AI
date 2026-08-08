<p align="center">
  <img src="https://mir-s3-cdn-cf.behance.net/project_modules/disp/0f3ed952323519.5608d8fce47b2.png" width="200" height="200" />
</p>

<h1 align="center">🤖 <b>J.A.R.V.I.S.</b> Virtual Assistant</h1>
<p align="center">
  <b>Your own offline Iron-Man assistant.</b> A privacy-first, AI-driven voice assistant
  that runs entirely on your PC with <b>Ollama</b> — it controls your computer, answers
  from local models, and remembers who you are. No cloud, no subscriptions.
</p>

---

## 🚀 About the Project
**J.A.R.V.I.S.** is an AI-powered voice assistant inspired by Tony Stark's J.A.R.V.I.S. It runs **100% locally**: local Ollama models (Qwen 3) answer your questions, offline wake-word detection listens for "Hey Jarvis", and a PyQt6 Desktop HUD brings the Iron-Man Mark-L style to your screen.

> ✨ **In one line:** *Talk to your PC — open apps, search the web, check the weather — and it talks back, remembers your name and interests, all offline and free.*

Unlike cloud assistants, nothing you say leaves your machine — speech recognition, AI answers, and voice replies are all generated locally. On top of PC control, it now has a **personal memory**: tell it "my name is Sam" or "I like chess" once, and it remembers across sessions.
<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Ollama-000000?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Speech%20Recognition-FF9900?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Text--to--Speech-007ACC?style=for-the-badge&logo=azure-speech-services&logoColor=white" />
</p>

### 🔥 Features
- 🗣️ **Voice-controlled assistant** – Uses speech recognition to process commands.
- 🤖 **AI-powered responses** – Uses local Ollama models (Qwen 3) for intelligent interaction.
- 💻 **PC control capabilities** – Opens apps & websites in your browser of choice ("open github in brave"), takes screenshots, and runs system commands.
- 🎙️ **Text-to-Speech (TTS) and Speech Recognition (SR)** – Seamless, fully offline conversation.
- 🧠 **Personal memory** – Remembers your name, interests, favourites, job, location and birthday across sessions ("my name is Sam", "I like chess"). Ask *"what do you know about me?"* anytime, or *"forget everything"* to wipe it.
- 🪪 **Knows who you are** – Ask *"who am I?"* and it answers with your name (no more confused AI talking about itself).
- 🌍 **Key-free fallbacks** – Weather, news and web search work even with zero API keys configured.
- ⚡ **Always up** – Auto-starts Ollama when needed and can launch itself at Windows startup.

---


## **Table of Contents**

- [🚀 About the Project](#-about-the-project)  
- [🏗️ Installation & Setup](#%EF%B8%8F-installation--setup)  
- [🚀 Usage](#-usage)  
- [📜Project Structure](#-project-structure)  
- [License](#license)  

## 🏗️ Installation & Setup
Follow these steps **in order** — each one tells you the exact command to run.

### 1. Install Python 3.13 (for PyAudio support)
Download it from [python.org/downloads](https://www.python.org/downloads/).
On Windows, tick **“Add Python to PATH”** during installation.

### 2. Install Ollama + the AI models
Download Ollama from [ollama.com/download](https://ollama.com/download) and install it.
Then open a **new terminal** (so `ollama` is on PATH) and download the two models the assistant uses:
```bash
ollama pull qwen3:0.6b
ollama pull qwen3:1.7b
```
> ℹ️ On Windows, Ollama runs in the background (tray icon). Don't worry if it isn't running — the HUD now **starts it automatically** whenever it's needed.

### 3. Clone this Repo
```bash
git clone https://github.com/adrxLV/J.A.R.V.I.S.AI.git
cd J.A.R.V.I.S.AI
```

### 4. Create a Virtual Environment
- **Windows:**
  ```bash
  py -3.13 -m venv ollama_assistant_env
  ```
- **Mac/Linux:**
  ```bash
  python3 -m venv ollama_assistant_env
  ```
> 💡 If `py -3.13` isn't found (or PyAudio fails to install on 3.13), use **3.12** instead: `py -3.12 -m venv ollama_assistant_env`.

### 5. Activate the Virtual Environment
- **Windows (Command Prompt):**
  ```bash
  ollama_assistant_env\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  ollama_assistant_env\Scripts\Activate.ps1
  ```
- **Mac/Linux:**
  ```bash
  source ollama_assistant_env/bin/activate
  ```
You'll know it worked when your prompt is prefixed with `(ollama_assistant_env)`.

### 6. Install the Dependencies
```bash
pip install -r requirements.txt
```

### 7. Create Your .env File
There's a template ready for you — just copy it and fill it in:
- **Windows (Command Prompt):**
  ```bash
  copy .env.example .env
  ```
- **Mac/Linux:**
  ```bash
  cp .env.example .env
  ```
Then open `.env` in any editor and replace the placeholder values.

Minimal setup — only these two lines are truly required (the rest have key-free fallbacks):
```
USER=YourName
BOTNAME=JARVIS
```
All variables and where to get the free API keys are explained inside `.env.example` (weather, news, email, search, movies).

### 8. Launch It
- **Windows:** double-click `run.bat`
- **Any OS:** `python main.py`

The HUD opens, greets you out loud, and **starts listening for your voice right away**. By default it runs in **wake-word mode**: stand by, say **"Hey Jarvis"**, and it wakes to take your command.

> 🧠 **Wake word first run:** the first time the HUD starts with wake-word ON, it downloads the small offline "hey jarvis" model automatically (one-time, needs internet). After that it works offline. If `openwakeword` isn't installed, it falls back to the online recognizer.

> 🧪 **First-run check:** say *“What's the weather?”* or click **WEATHER** in the side panel. It works even with no API keys (key-free fallbacks).

---

## 🚀 Usage

### 🖥️ Desktop HUD (recommended)
Start the **J.A.R.V.I.S. Desktop HUD** — a native Iron-Man / Mark-L style interface — with one double-click:
```bash
run.bat
```
or manually (either entry point opens the HUD):
```bash
ollama_assistant_env\Scripts\python.exe main.py
```
You get:

- 🌀 Animated **HUD core** (spinning rings, pulsing glow, status states: LISTENING / THINKING / PROCESSING / SPEAKING + live waveform)
- 💬 Streaming chat log with a **typewriter effect** (colored `You:` / `JARVIS:` entries)
- 🎙️ **Voice input** — the HUD **starts listening automatically as soon as it opens** (right after its greeting), and you can re-trigger it with the MIC button. The **AUTO-MIC** toggle in the side panel turns this off/on (remembered between sessions)
- 🗣️ **"Hey Jarvis" wake word** — the HUD stands by, listening continuously, and only wakes when you address it. Runs **fully offline** (openWakeWord), instant and free. Toggle with the **WAKE** button (remembered between sessions). When ON, it replaces the one-shot auto-listen
- 🗣️ **Voice replies** via TTS (toggle with the SPEAKER button)
- ⚙️ **STARTUP toggle** — the **STARTUP: ON/OFF** button switches **launching J.A.R.V.I.S. at Windows startup** on and off, right from inside the HUD (no .bat files needed). When **OFF**, it won't start on boot
- 🚀 **Ollama auto-start** — if the local Ollama server is offline when the HUD opens (typical right after a reboot), J.A.R.V.I.S. starts it automatically in the background and waits until it's online, so your first question always gets answered
- ⚡ **Quick actions** — weather, jokes, news, your IP, screenshots, opening apps, Wikipedia & YouTube search
- 📊 Live **system metrics** (CPU / RAM / network) and status LEDs for Ollama / TTS / mic
- 🎛️ **Model picker** in the side panel — switch between `qwen3:0.6b` (fast, light on CPU) and `qwen3:1.7b` (smarter) anytime; your choice is remembered between sessions
- 🧠 **ULTRA THINK** — start a question with `ULTRATHINK:` (e.g. `ULTRATHINK: explain black holes`) to answer it with the bigger `qwen3:1.7b` model; everything else uses the fast `qwen3:0.6b`
- ⟲ One-click conversation reset

### 🗣️ Things you can say
| You say… | J.A.R.V.I.S. does… |
|---|---|
| `open github in brave` / `search for best laptops in chrome` | Opens the app or searches in the browser you asked for |
| `play despacito on youtube` | Plays it on YouTube |
| `what's the weather` / `joke` / `news` / `my ip` | Weather (key-free), a joke, headlines, your IP |
| `who am I` / `what is my name` | Tells you your name (from memory or .env) |
| `my name is Sam` / `I like chess` / `my favourite colour is blue` | **Remembers it** and confirms |
| `what do you know about me` | Recaps everything it remembers |
| `forget everything` | Wipes its memory of you |
| `ULTRATHINK: explain black holes` | Answers with the bigger, smarter model |

### ⚡ Start J.A.R.V.I.S. Automatically at Boot (Windows)
Want the assistant up and listening the moment you sit down — with **no console window** popping up?

**Easiest way — inside the HUD:**
1. Click the **STARTUP** button in the side panel until it reads **`STARTUP: ON`**.
2. That's it — it creates the autostart entry for you. No .bat files and no admin rights needed (it falls back to the Startup-folder method automatically). Toggle it back to **`STARTUP: OFF`** anytime to stop launching at startup.

**Manual way — one double-click:**
1. Double-click **`enable_autostart.bat`**.
2. That's it. J.A.R.V.I.S. now launches **silently** at every startup via `autostart.vbs` (`pythonw.exe`, no black console window) and **starts listening immediately**.

The script tries the two methods in order:
1. **Task Scheduler** (preferred) — a *"JARVIS Assistant"* task fires at boot and starts the HUD ~20 seconds in, once audio/network drivers are ready, right as your desktop appears. It's set to **auto-restart if the HUD ever crashes** (retries every 1 minute, up to 3 times) and never stops it for running too long, so J.A.R.V.I.S. stays up.
2. **Startup folder** (automatic fallback) — if Task Scheduler needs admin rights you don't have, it creates a Startup-folder shortcut instead. Same visible behavior; it just launches at logon rather than at boot.

To stop it from auto-starting, double-click **`disable_autostart.bat`** — it removes whichever method is active. The HUD's **STARTUP** button does the same thing in one click.

> 🧠 No admin rights or stored password needed. Old entries are cleared first, so J.A.R.V.I.S. never launches twice.
> 🔧 Want Task Scheduler specifically? Right-click `enable_autostart.bat` → **Run as administrator**. Inspect/edit the task anytime with `Win+R` → `taskschd.msc` → "JARVIS Assistant". Want the console visible for debugging? Run `run.bat` manually — that's still the normal (windowed) launcher.
> 🚀 **Ollama comes along too:** the autostart entry launches the HUD, and the HUD then makes sure the Ollama server is running — so the AI answers the moment you ask, even right after a restart.

### 🎛️ One interface: the Desktop HUD
`main.py` is the main entry point — running it (or `run.bat`) pops up the Desktop HUD. The old terminal voice loop has been retired.

---

## 📜 Project Structure
```
├── J.A.R.V.I.S.AI/
│   ├──functions/                 # some functions to make the V.A. work;
│   │   ├── online_ops.py         # Online services and operations;
│   │   ├── os_ops.py             # Local operations;
│   ├── main.py                   # Main entry point — launches the Desktop HUD;
│   ├── gui.py                    # Desktop HUD interface (PyQt6, Mark-L style);
│   ├── ai_memory.py              # Personal memory: learns name/interests/favourites, saves to ai_memory.json;
│   ├── speech_engine.py          # Reliable SAPI5 text-to-speech (strips emoji before speaking);
│   ├── ollama_streaming.py       # Streaming Ollama client (fast + big model constants);
│   ├── ollama_manager.py         # Auto-starts the local Ollama server when it's offline;
│   ├── autostart.py              # In-app STARTUP toggle (scheduled task / Startup-folder entry);
│   ├── .env.example              # Template — copy to .env and fill in your values;
│   ├── .gitignore                # Keeps .env, venv, caches & ai_memory.json out of git;
│   ├── requirements.txt          # All Python dependencies — pip install -r requirements.txt;
│   ├── run.bat                   # One double-click launcher (Windows, shows a console);
│   ├── autostart.vbs             # Silent launcher fallback (pythonw, no console; used when the venv is missing);
│   ├── enable_autostart.bat      # Registers a Task Scheduler task that starts the HUD at boot;
│   ├── enable_startup_task.ps1   # PowerShell helper for the task (crash-restart settings);
│   ├── disable_autostart.bat     # Deletes the scheduled task again;
│   ├── .env                      # Your real secrets & settings (gitignored, never committed)
├──
```
---

<table align="center">
  <tr>
    <td align="center">
      <a href="https://ollama.com/">
        <img src="https://dev-to-uploads.s3.amazonaws.com/uploads/articles/qbosw7lyg8enfdqqi8ox.png" alt="Ollama" style="width: 200px; height: 200px;">
      </a>
    </td>
    <td align="center">
      <a href="https://ollama.com/library/qwen3">
        <img src="https://ollama.com/public/ollama.png" alt="Qwen 3" style="width: 200px; height: 200px;">
      </a>
    </td>
  </tr>
</table>



---
## License
*This project is licensed under the **MIT License** - see the LICENSE file for details.*

