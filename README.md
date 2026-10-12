# Agent Commander (AC) 🎖️

> **The Orthodox Dual-Pane AI Agent Conversation Manager**  
> *Patterned after Norton Commander of old.*

`agent_commander` is a terminal user interface (TUI) for managing, inspecting, cross-copying, and resuming chat histories across multiple autonomous AI agent platforms:

- 🧠 **OpenAI Codex** (`~/.codex/sessions`)
- 🛸 **Google Antigravity (`agy`)** (`~/.gemini/antigravity/brain`)
- 🤖 **Anthropic Claude Code** (`~/.claude/projects`)
- ⚡ **xAI Grok Build** (`~/.grok/sessions`)

```
╔═══════════════════════════════════╦═══════════════════════════════════╗
║ [Left: Claude Code]       3 items ║ [Right: Codex]           12 items ║
╠═╤══════════════╤════════════╤═════╬═╤══════════════╤════════════╤═════╣
║*│2026-09-14 11 │Android QA  │  14 ║ │2026-09-15 08 │Kaggle Run  │  28 ║
║ │2026-09-12 04 │Doc Review  │   6 ║ │2026-09-15 14 │Model Screen│  12 ║
║ │2026-09-10 18 │API Refactor│  32 ║*│2026-09-16 06 │Docs Sync   │  18 ║
╚═╧══════════════╧════════════╧═════╩═╧══════════════╧════════════╧═════╝
 1Help  2Plat  3View  4Filter  5Copy  6Ref  7Export  8Del  Enter:Resume  10Quit
```

---

## ✨ Features

- **Classic Norton Commander Layout**: Side-by-side orthodox dual panes with the unmistakable DOS blue and cyan retro aesthetic.
- **Multi-Platform Agent Aggregator**: Auto-discovers and reads sessions from Codex, Google Antigravity, Claude Code, and Grok Build.
- **Multi-Select Tagging**: Use `Space` or `Insert` to tag one or multiple conversations with `[*]`.
- **Cross-Pane Conversation Copying (`F5`)**: Copy selected sessions to the other pane as a **native session** you can resume there (`claude --resume`, `codex resume`), or as a **Markdown transcript** (saved to `~/AgentCommander/exports` and put on the clipboard).
- **Direct Agent Resumption (`Enter`)**: Press Enter on any session to resume directly in the agent's native CLI (`codex resume <id>`, `grok --resume <id>`, etc.) via terminal suspend, or inspect turns and tool calls in the built-in Conversation Viewer.
- **Fast Search & Filter (`F4`)**: Real-time filtering across conversation titles, prompts, and IDs.
- **Offline & Safe**: Operates directly on local JSONL storage; never touches remote APIs without user command.

---

## ⌨️ Keybindings

| Key | Action |
|---|---|
| `Tab` | Switch active pane (Left ⇄ Right) |
| `Up` / `Down` | Navigate conversation list |
| `Space` / `Insert` | Toggle multi-select tag `[*]` on current conversation |
| `Enter` | **Enter Agent**: Resume in native CLI or open Conversation Viewer |
| `F1` / `?` | Show Help modal |
| `F2` / `p` | Select Platform for the active pane (Codex, AGY, Claude, Grok) |
| `1` / `2` / `3` / `4` | Quick-switch platform (`1`: Codex, `2`: AGY, `3`: Claude, `4`: Grok) |
| `F3` / `v` | View conversation transcript details & tool calls |
| `F4` / `/` | **Find**: filter by title as you type; press Enter to search inside every conversation |
| `F5` / `c` | **Copy** selected conversations to the other pane (native session or Markdown) |
| `F6` / `n` | **Rename** a session; Claude Code and Codex show the new name too |
| `F7` / `e` | Export the current conversation to Markdown |
| `F8` / `d` | **Archive** selected sessions (in the archive view: restore them) |
| `Shift+F8` / `Del` | Delete selected sessions permanently, after confirming |
| `F9` / `a` | Toggle the archive view for the active pane |
| `Ctrl+R` / `r` | Re-read the pane from disk |
| `F10` / `q` | Quit Agent Commander |

---

## 🚀 Installation & Running

Works on macOS, Windows and Linux.

### Download (no Python needed)

Grab the file for your system from the [latest release](https://github.com/jcole75/agent_commander/releases/latest):

| System | File |
|---|---|
| macOS (Apple silicon) | `ac-macos-arm64` |
| Windows | `ac-windows-x86_64.exe` |
| Linux | `ac-linux-x86_64` |

On macOS and Linux, make it executable and put it on your PATH, e.g.
`chmod +x ac-macos-arm64 && mv ac-macos-arm64 /usr/local/bin/ac`.
The builds are not code-signed yet: on macOS, clear the download flag once with
`xattr -d com.apple.quarantine /usr/local/bin/ac`; on Windows, choose "More info → Run anyway"
the first time SmartScreen asks.

### Install with pipx (Python 3.10+)

```bash
pipx install git+https://github.com/jcole75/agent_commander
ac
```

### From a checkout

```bash
pip install -e ".[dev]"
ac                 # or: agent-commander, python -m agent_commander
python -m pytest   # tests run against sample sessions in tests/fixtures
```

Set `AC_CODEX_BIN` to a Codex CLI to also run the tests that check copies and archives
against the real Codex.

### Releasing

Push a tag such as `v0.2.0`. The Release workflow builds the three executables, tests
each one, and attaches them (plus a wheel) to a GitHub release.

### Command line

Everything the commander does with copies is also available as commands:

```bash
ac list codex                      # newest Codex sessions: id, date, turns, title
ac copy 0199a3f2 --to claude       # copy a session (id or unique prefix) into Claude Code
ac copy 6f1c --to codex            # ...or into Codex
ac copy 6f1c --markdown -o chat.md # write a Markdown transcript instead
ac export 6f1c                     # same as copy --markdown, to ~/AgentCommander/exports
```

`ac copy` prints the command to resume the copy. Run it from the session's project folder,
because both Claude Code and Codex look sessions up by folder.

### Archiving

F8 moves a session out of the agent's list without deleting it, and F8 in the archive view
(F9) puts it back. Codex sessions go to Codex's own `archived_sessions` folder (using
`codex archive` when the Codex CLI is installed, so `codex resume` and Codex's own
"archived" list agree). Claude Code has no archive, so Agent Commander keeps Claude sessions
in `~/AgentCommander/archive/claude/`. That also keeps them safe from Claude Code's
automatic clean-up of old transcripts (`cleanupPeriodDays`, 30 days by default).

The same is available on the command line: `ac archive <id>`, `ac restore <id>`,
`ac rename <id> "New title"`, `ac search claude "flaky test"`.

### How copies work

A copied session keeps every prompt and reply. Each assistant turn also carries a short
record of the tools it ran and what they returned, written as text: tool calls and
reasoning are tied to the agent that produced them (Claude Code rejects foreign thinking
blocks; Codex encrypts its reasoning), so they are not replayed as native tool calls.
The first prompt ends with a note saying where the conversation came from, and the copy
is titled "<original title> (from <agent>)". The original session is never changed.

`CODEX_HOME` and `CLAUDE_CONFIG_DIR` are honoured if you have moved either tool's data folder.

---

## 🛠️ Architecture

```
agent_commander/
├── adapters/          # Platform-specific storage adapters (Codex, AGY, Claude, Grok)
├── converters/        # Bidirectional cross-platform translation engine
├── models/            # UnifiedSession & UnifiedMessage data models
└── ui/                # Textual-based orthodox dual-pane Norton Commander interface
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
