# geoip

Installs `geoipupdate` and the MaxMind DB reader tools, renders
`/etc/GeoIP.conf` from variables, downloads the GeoLite2 databases once and
keeps them current with a cron job.

## Requirements

- A Debian-family target (the role asserts `os_family == Debian`).
- A free MaxMind account: an account ID and a license key
  (<https://www.maxmind.com/en/geolite2/signup>). Neither has a default; the
  role stops with an explicit message when one is missing.
- Outbound HTTPS access to the MaxMind update servers (and to GitHub with the
  `deb` install method).

## Usage

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.geoip
      vars:
        geoip_account_id: "{{ vault_geoip_account_id }}"
        geoip_license_key: "{{ vault_geoip_license_key }}"
        geoip_editions:
          - GeoLite2-City
          - GeoLite2-ASN
```

Install an upstream release instead of the distribution package, behind a
proxy:

```yaml
- hosts: web
  become: true
  roles:
    - role: goabonga.website.geoip
      vars:
        geoip_account_id: "{{ vault_geoip_account_id }}"
        geoip_license_key: "{{ vault_geoip_license_key }}"
        geoip_install_method: deb
        geoip_deb_version: "7.1.0"
        geoip_proxy: proxy.example.net:3128
```

Run it alone with `--tags geoip`.

## What it does

1. Validates the target and the credentials.
2. Installs `geoipupdate` from the distribution (`apt`) or from the upstream
   `.deb` (`deb`). With `deb` the installed version is read with `dpkg-query`
   and the package is only downloaded when it is older than
   `geoip_deb_version`.
3. Installs `libmaxminddb0` and `mmdb-bin` (disable with
   `geoip_install_reader_tools`) and `cron` when scheduling is enabled.
4. Creates the database directory and renders the configuration file
   (mode `0600`, credentials hidden from the Ansible output).
5. Runs the update command once when the first edition is not on disk yet.
6. Installs a file in `/etc/cron.d` that refreshes the databases twice a
   week, or removes it when `geoip_schedule_enabled` is false.

The databases land in `geoip_database_dir` (`/usr/share/GeoIP` by default), for
example `GeoLite2-City.mmdb`. Applications read them from there; the role does
not write any web server configuration.

## Variables

### Role control

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `geoip_enabled` | bool | `true` | Master toggle. When false the role does nothing. |
| `geoip_apt_update_cache` | bool | `true` | Refresh the apt cache before installing packages. |
| `geoip_apt_cache_valid_time` | int | `3600` | Seconds the apt cache is considered fresh. |

### MaxMind account

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `geoip_account_id` | str | `""` | MaxMind account ID. Required when the role is enabled. Provide it from a vault. |
| `geoip_license_key` | str | `""` | MaxMind license key. Required when the role is enabled. Provide it from a vault. |
| `geoip_editions` | list | `[GeoLite2-City, GeoLite2-Country]` | Edition IDs to download (GeoLite2-City, GeoLite2-Country, GeoLite2-ASN, ...). The first one is the marker of the initial download. |

### Installation

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `geoip_install_method` | str | `"apt"` | How geoipupdate is installed: from the distribution packages (`apt`) or from an upstream .deb release (`deb`). |
| `geoip_package` | str | `"geoipupdate"` | Package installed with the `apt` method. |
| `geoip_install_reader_tools` | bool | `true` | Install the libmaxminddb reader packages below. |
| `geoip_reader_packages` | list | `[libmaxminddb0, mmdb-bin]` | Packages providing mmdblookup and the MaxMind DB library. |
| `geoip_deb_version` | str | `"7.1.0"` | geoipupdate release installed with the `deb` method. |
| `geoip_deb_arch` | str | `"{{ 'arm64' if ansible_facts['architecture'] in ['aarch64', 'arm64'] else 'amd64' }}"` | Architecture suffix of the .deb file. |
| `geoip_deb_url` | str | `"https://github.com/maxmind/geoipupdate/releases/download/v{{ geoip_deb_version }}/geoipupdate_{{ geoip_deb_version }}_linux_{{ geoip_deb_arch }}.deb"` | Download URL of the .deb for the `deb` method. |
| `geoip_deb_checksum` | str | `""` | Optional checksum of the .deb in the `algorithm:value` form accepted by get_url. |
| `geoip_deb_download_dir` | path | `"/var/cache/geoipupdate"` | Directory where the .deb is stored. |

### Configuration

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `geoip_config_file` | path | `"/etc/GeoIP.conf"` | Path of the geoipupdate configuration file. |
| `geoip_database_dir` | path | `"/usr/share/GeoIP"` | Directory receiving the .mmdb files. |
| `geoip_lock_file` | path | `"/var/lock/geoipupdate.lock"` | Lock file preventing concurrent updates. |
| `geoip_host` | str | `""` | Update server host name. Empty uses the geoipupdate default. |
| `geoip_proxy` | str | `""` | HTTP proxy used by geoipupdate (host:port). Empty for none. |
| `geoip_proxy_user_password` | str | `""` | Proxy credentials as `user:password`. Empty for none. |
| `geoip_preserve_file_times` | bool | `false` | Keep the modification time of downloaded files. |
| `geoip_parallelism` | int | `0` | Number of parallel downloads. 0 leaves the geoipupdate default (needs geoipupdate 6 or newer when set). |

### Updates

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `geoip_update_command` | str | `"/usr/bin/geoipupdate -f {{ geoip_config_file }}"` | Command run by the initial download, the cron job and the change handler. |
| `geoip_initial_download` | bool | `true` | Run the update command once when the first edition is not on disk yet. |
| `geoip_update_on_config_change` | bool | `true` | Run the update command when the configuration file changes. |
| `geoip_schedule_enabled` | bool | `true` | Install a cron job refreshing the databases. When false the job is removed. |
| `geoip_cron_package` | str | `"cron"` | Package providing cron, installed when scheduling is enabled. Empty skips the installation. |
| `geoip_cron_name` | str | `"geoip-update"` | Name of the cron entry and of its file in /etc/cron.d. |
| `geoip_cron_minute` | str | `"0"` | Cron minute field. |
| `geoip_cron_hour` | str | `"3"` | Cron hour field. |
| `geoip_cron_weekday` | str | `"0,3"` | Cron weekday field (MaxMind publishes on Tuesdays). |


## Handlers

| Topic | Effect |
| --- | --- |
| `geoip \| update databases` | Runs `geoip_update_command` after a configuration change, unless the initial download already ran in the same play or `geoip_update_on_config_change` is false. |

## Notes

- MaxMind publishes new GeoLite2 data on Tuesdays; the default schedule runs on
  Sundays and Wednesdays at 03:00.
- Check the freshness of a database with
  `mmdblookup --file /usr/share/GeoIP/GeoLite2-City.mmdb --ip 8.8.8.8 country`
  or force an update with `geoipupdate -v`.
- `geoip_parallelism` is only written to the configuration when it is greater
  than zero, because older `geoipupdate` releases reject the directive.

## Verification status

The role is checked with `ansible-playbook --syntax-check`, the argument
specification is validated against the defaults and the configuration template
is rendered locally. It has not been run against a live host: package
installation, the download of the databases and the cron entry are untested.
