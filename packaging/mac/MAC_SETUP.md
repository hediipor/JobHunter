# Running JobHunter AI (Mac)

1. Unzip this folder anywhere (Desktop is fine).
2. Start it — zipping strips the "this file is runnable" flag Mac uses, so double-clicking `run.command` may just open it in a text editor the very first time. The sure-fire way:
   - Open **Terminal** (Spotlight → type "Terminal" → Enter).
   - Type `cd ` (with a trailing space), then drag the unzipped `JobHunterAI` folder from Finder into the Terminal window, and press Enter. This fills in the right path for you.
   - Run:
     ```
     chmod +x run.command && ./run.command
     ```
   - First run takes a minute or two (installing dependencies) — that's normal, just let it finish.
   - After this once, double-clicking `run.command` in Finder will work directly.
   - If macOS still blocks it ("cannot be opened because it is from an unidentified developer") when double-clicking: right-click `run.command` → **Open** → **Open** again in the dialog. Only needed once.
   - If you see `python3: command not found`: install Python first — run `xcode-select --install` in Terminal, or install from [python.org](https://www.python.org/downloads/macos/) — then try again.
3. Your browser opens automatically to the app. Follow the setup wizard: paste in your API keys (free, links provided in the wizard) and fill in your profile.
4. That's it — click "Scan Jobs Now" on the dashboard whenever you want fresh listings.

Next time, just double-click `run.command` (or rerun `./run.command` in Terminal) — no reinstall, it starts in a couple seconds.

Your data (jobs, applications, your profile, your API keys) is stored in files next to this folder — nothing is sent anywhere except the job-search APIs and AI providers (Gemini, Groq, OpenRouter) you configure yourself.
