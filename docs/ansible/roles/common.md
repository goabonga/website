# common

Baseline host configuration: packages, time zone, locale, bash prompt and tmux.

Brings a fresh Debian or Ubuntu host to a consistent baseline: package index and upgrades, base packages, host name, time zone, locale, a shared bash prompt and a system-wide tmux configuration.

## Requirements

- Debian 12 or 13, Ubuntu 22.04 or 24.04.
- Privilege escalation (`become: true`).
- Collection `community.general` for locale generation.

## Variables

Every variable is optional and defined in `defaults/main.yml`. The role validates them against `meta/argument_specs.yml` before running.

### Packages

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `common_apt_update_cache` | bool | `true` | Refresh the apt package index. |
| `common_apt_cache_valid_time` | int | `3600` | Seconds during which the apt cache is considered fresh. |
| `common_upgrade` | str | `"safe"` | How installed packages are upgraded (none skips the upgrade). Choices: `none`, `safe`, `full`, `dist`. |
| `common_packages` | list of str | `["ca-certificates", "curl", "git", "htop", "unzip", "vim", "wget"]` | Packages installed on every host. |
| `common_packages_absent` | list of str | `[]` | Packages removed from every host. |

### System

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `common_hostname` | str | `""` | Host name to set. Left untouched when empty. |
| `common_timezone` | str | `"UTC"` | System time zone. |
| `common_locale` | str | `"en_US.UTF-8"` | Default system locale (LANG). |
| `common_locales_extra` | list of str | `[]` | Additional locales to generate. |

### Bash prompt

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `common_bash_prompt_enabled` | bool | `true` | Install a shared bash prompt for interactive shells. |
| `common_bash_prompt_show_host` | bool | `true` | Show the host name in the prompt. |
| `common_bash_prompt_show_git` | bool | `true` | Show the current git branch in the prompt. |
| `common_bash_prompt_user_color` | int | `32` | ANSI foreground color code of the user name. |
| `common_bash_prompt_root_color` | int | `31` | ANSI foreground color code of the user name for root. |
| `common_bash_prompt_host_color` | int | `36` | ANSI foreground color code of the host name. |
| `common_bash_prompt_path_color` | int | `34` | ANSI foreground color code of the working directory. |
| `common_bash_prompt_git_color` | int | `33` | ANSI foreground color code of the git branch. |

### tmux

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `common_tmux_enabled` | bool | `true` | Install tmux and a system-wide configuration. |
| `common_tmux_config_path` | path | `"/etc/tmux.conf"` | Path of the system-wide tmux configuration. |
| `common_tmux_prefix` | str | `"C-a"` | tmux prefix key. |
| `common_tmux_mouse` | bool | `true` | Enable mouse support. |
| `common_tmux_history_limit` | int | `50000` | Scrollback lines kept per pane. |
| `common_tmux_base_index` | int | `1` | Index of the first window and pane. |
| `common_tmux_default_terminal` | str | `"tmux-256color"` | Value of default-terminal. |
| `common_tmux_status_bg` | str | `"colour235"` | Status bar background color. |
| `common_tmux_status_fg` | str | `"colour250"` | Status bar foreground color. |
| `common_tmux_accent` | str | `"colour33"` | Accent color of the active window and pane border. |
| `common_tmux_extra_config` | list of str | `[]` | Extra raw tmux configuration lines appended to the file. |
| `common_tmux_autoattach` | bool | `false` | Attach interactive SSH logins to a tmux session (skipped when already inside tmux). |
| `common_tmux_session_name` | str | `"main"` | Name of the session created by auto-attach. |

## Behavior

- The package index is refreshed at most once per `common_apt_cache_valid_time` seconds. A check run (`--check`) does not refresh it, so it never reports a stale index as a change.
- `/etc/default/locale` is followed when it is a symbolic link: the mode is checked on the file it points to.
- Setting `common_upgrade` to `none` skips the system upgrade; `safe` is the aptitude-style safe upgrade.
- The host name is only changed when `common_hostname` is not empty.
- The prompt is installed in `/etc/profile.d` and sourced from `/etc/bash.bashrc` through a managed block, so it also applies to non-login interactive shells.
- tmux auto-attach is a managed block in `/etc/bash.bashrc`; setting `common_tmux_autoattach` back to `false` removes the block.
- Auto-attach never nests: it is skipped when the client already runs inside tmux or screen.

## Tags

| Tag | Scope |
| --- | --- |
| `common` | Every task of the role. |
| `common_packages` | Package index, upgrade and packages. |
| `common_system` | Host name, time zone and locale. |
| `common_bash_prompt` | Shared bash prompt. |
| `common_tmux` | tmux installation, configuration and auto-attach. |

## Example

```yaml
- hosts: all
  become: true
  roles:
    - role: goabonga.website.common
      vars:
        common_timezone: Europe/Paris
        common_locale: en_US.UTF-8
        common_packages: [curl, git, htop, jq]
        common_tmux_autoattach: true
```
