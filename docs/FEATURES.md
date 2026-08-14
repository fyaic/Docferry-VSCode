# Feature contract

DocFerry for VS Code consumes the same product session, membership policy, and
share/import APIs as the current DocFerry mainline. It does not maintain a
separate entitlement model.

| Product workflow | VS Code 0.2.3 | Boundary |
| --- | --- | --- |
| Bondie login | Complete | System-browser Device Code flow |
| Product Dashboard | Complete | Short-lived DocFerry-only handoff |
| Import DocFerry share | Complete | Saves into the selected workspace |
| Save ordinary public link | Complete | No remote source fetch |
| Advanced Import | Complete | Pro capability, provider contract, confirmation |
| Share Markdown | Complete | Free/Pro server limits |
| Share visible Markdown folder | Complete | Pro capability and atomic revision |
| Open/copy/update/stop share | Complete | Note and folder variants |
| Delete stopped history | Complete | Separate permanent confirmation |
| Plan and usage | Complete | Notes, folders, and detailed-note monthly usage |
| Full Obsidian theme capture | Not applicable | Requires Obsidian rendering context |
| Agent conversation slash commands | Separate Agent Kit | CLI/MCP/Skill distribution, not VS Code Chat transcript access |

The extension uses returned limits and feature gates and cannot grant or mutate
server-managed access roles.
