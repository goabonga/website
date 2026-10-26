# redis

Installs Redis from the distribution packages and renders `redis.conf` from
variables. It deploys a systemd drop-in, applies the kernel parameters Redis
recommends and waits until the server accepts connections.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- The `ansible.posix` collection on the controller (a dependency of
  `goabonga.website`).

## Usage

TCP only on the loopback interface (the default):

```yaml
- hosts: cache
  become: true
  roles:
    - role: goabonga.website.redis
      vars:
        redis_maxmemory: 512mb
```

Unix socket only, protected by a password stored in a vault:

```yaml
- hosts: cache
  become: true
  roles:
    - role: goabonga.website.redis
      vars:
        redis_port: 0
        redis_socket: /run/redis/redis.sock
        redis_password: "{{ vault_redis_password }}"
```

Run it alone with `--tags redis`.

## What it does

1. Installs `redis-server` and makes sure the data directory exists.
2. Renders `redis.conf` (mode `0640`). A change restarts the service.
3. Deploys a systemd drop-in raising `LimitNOFILE` and setting the restart
   policy, or removes it when `redis_systemd_override_enabled` is false.
4. Sets `vm.overcommit_memory` and `net.core.somaxconn` (editable through
   `redis_sysctl_settings`) and disables transparent huge pages until the next
   reboot.
5. Starts and enables the service, then waits for the TCP port, or for the
   socket when `redis_port` is `0`.

## Unix socket access

The socket is created with `redis_socket_perm` (default `770`) and is owned by
the `redis` group. A service that connects through it must belong to that group;
the application deployment roles are expected to add their service user to it.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `redis_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `redis_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### Installation and paths

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_packages` | list | `[redis-server]` | Packages to install. |
| `redis_service_name` | str | `"redis-server"` | systemd unit name. |
| `redis_service_state` | str | `"started"` | State of the service after configuration. |
| `redis_service_enabled` | bool | `true` | Enable the service at boot. |
| `redis_user` | str | `"redis"` | Owner of the configuration file and data directory. |
| `redis_group` | str | `"redis"` | Group of the configuration file and data directory. |
| `redis_config_file` | path | `"/etc/redis/redis.conf"` | Path of the rendered configuration file. |
| `redis_data_dir` | path | `"/var/lib/redis"` | Data directory (RDB and AOF files). |
| `redis_log_file` | str | `"/var/log/redis/redis-server.log"` | Log file. Use an empty string to log to stdout (journald). |
| `redis_pid_file` | path | `"/run/redis/redis-server.pid"` | PID file. |
| `redis_backup_config` | bool | `false` | Keep a timestamped backup of redis.conf when it changes. |

### Network

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_bind` | str | `"127.0.0.1"` | Addresses to bind (space separated). Use 0.0.0.0 to listen on every interface. |
| `redis_port` | int | `6379` | TCP port. Set to 0 to disable TCP and use only the Unix socket. |
| `redis_socket` | str | `""` | Unix socket path, for example /run/redis/redis.sock. Empty disables the socket. |
| `redis_socket_perm` | str | `"770"` | Octal permissions of the Unix socket. |
| `redis_tcp_backlog` | int | `511` | TCP listen backlog. |
| `redis_tcp_keepalive` | int | `300` | TCP keepalive in seconds. |
| `redis_timeout` | int | `0` | Close idle client connections after this many seconds (0 disables). |
| `redis_protected_mode` | bool | `true` | Refuse external connections when no password is set and the server is not bound explicitly. |

### Security

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_password` | str | `""` | Password for requirepass. Empty disables authentication. Provide it from a vault. |

### General

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_loglevel` | str | `"notice"` | Log verbosity. |
| `redis_databases` | int | `16` | Number of logical databases. |
| `redis_maxclients` | int | `10000` | Maximum number of simultaneous clients. |

### Memory

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_maxmemory` | str | `"256mb"` | Memory limit such as 256mb. An empty string removes the limit. |
| `redis_maxmemory_policy` | str | `"allkeys-lru"` | Eviction policy when the limit is reached. |

### Persistence

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_save_enabled` | bool | `true` | Enable RDB snapshots. |
| `redis_save_rules` | list | `[900 1, 300 10, 60 10000]` | RDB snapshot rules, each formatted as `<seconds> <changes>`. |
| `redis_rdbcompression` | bool | `true` | Compress RDB snapshots. |
| `redis_stop_writes_on_bgsave_error` | bool | `true` | Refuse writes when a background save fails. |
| `redis_appendonly` | bool | `false` | Enable the append-only file. |
| `redis_appendfsync` | str | `"everysec"` | AOF fsync policy. |

### Slow log

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_slowlog_threshold` | int | `10000` | Log commands slower than this many microseconds. |
| `redis_slowlog_max_len` | int | `128` | Number of entries kept in the slow log. |

### Systemd drop-in

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_systemd_override_enabled` | bool | `true` | Deploy a drop-in that raises limits and sets the restart policy. |
| `redis_limit_nofile` | int | `65535` | LimitNOFILE of the service. |
| `redis_restart_policy` | str | `"always"` | Restart= value of the service. |
| `redis_restart_sec` | int | `5` | RestartSec= of the service. |

### Kernel tuning

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_sysctl_enabled` | bool | `true` | Apply the sysctl settings below. |
| `redis_sysctl_settings` | dict | `{net.core.somaxconn: '65535', vm.overcommit_memory: '1'}` | Kernel parameters set for Redis. |
| `redis_disable_thp` | bool | `true` | Disable transparent huge pages at runtime (not persisted across reboots). |

### Extra configuration

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_extra_config` | list | `[]` | Raw lines appended to redis.conf, for example `notify-keyspace-events Ex`. |

### Readiness

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `redis_wait_for_ready` | bool | `true` | Wait until Redis accepts connections before finishing. |
| `redis_wait_timeout` | int | `30` | Seconds to wait for readiness. |


## Handlers

| Topic | Effect |
| --- | --- |
| `redis \| restart` | Restarts the service (only when `redis_service_state` is `started`). |
| `redis \| reload systemd` | Runs `systemctl daemon-reload`. |

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults and the templates are rendered
locally. It has not been run against a live host.
