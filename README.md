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
| `F4` / `/` | Filter conversations by query |
| `F5` / `c` | **Copy** selected conversations to the other pane's platform |
| `F6` / `r` | Refresh session lists from disk |
| `F7` / `e` | Export selected conversations to Markdown |
| `F8` / `d` | Delete / archive session |
| `F10` / `q` | Quit Agent Commander |

---

## 🚀 Installation & Running

### Run directly with Python:
```bash
python -m agent_commander
```

### Install in editable development mode:
```bash
pip install -e .
agent-commander
```

Or use the handy shorthand:
```bash
ac
```

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
