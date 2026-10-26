# Visitor enrichment

Two small services turn the raw HTTP request of a visitor into data that is
worth storing: the device (from the `User-Agent` header) and the approximate
location (from the IP address). The collection endpoints described later call
them when they create a session.

## User agent parsing

`analytics.services.useragent.useragent_service.parse(user_agent)` returns a
`DeviceInfo` dataclass:

| Field | Values |
| --- | --- |
| `device_type` | `mobile`, `tablet`, `desktop`, `bot`, `other`, or `None` when no user agent is given |
| `browser`, `browser_version` | Browser family and version, `None` when unknown |
| `os`, `os_version` | Operating system family and version, `None` when unknown |
| `is_bot` | `True` for crawlers |

Parsing uses the `user-agents` package. If the package cannot be imported, or
if it raises, a keyword based fallback detects bots (`bot`, `crawler`,
`curl`, ...), mobile and tablet devices, the main browsers and operating
systems. An empty or missing user agent yields an empty `DeviceInfo`.

## GeoIP lookup

`analytics.services.geoip.geoip_service.lookup(ip)` returns a `GeoLocation`
with an ISO country code and a city name, both `None` when nothing is found.
It uses a MaxMind GeoLite2 City database (`geoip2` package):

- The reader is opened lazily on the first lookup.
- Lookups are skipped for private, loopback, link-local and invalid
  addresses.
- When `GEOIP_ENABLED=false`, when the database file does not exist, when
  `geoip2` is missing or when the database cannot be opened, the service
  switches itself off, logs a warning and answers empty locations. The
  application keeps running without geolocation.

The GeoLite2 database is not shipped with the application: download
`GeoLite2-City.mmdb` from MaxMind (a free account is required) and point
`GEOIP_DATABASE_PATH` at it.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `GEOIP_ENABLED` | `true` | Enable GeoIP lookups |
| `GEOIP_DATABASE_PATH` | `/usr/share/GeoIP/GeoLite2-City.mmdb` | MaxMind GeoLite2 City database |

The settings are read once, when `GeoIPService` is instantiated.

## Tests

pytest:

- `test_services_useragent.py`: `DeviceInfo` defaults, desktop, mobile, tablet
  and bot detection, browser and OS extraction, the error path and the
  fallback parser.
- `test_services_geoip.py`: disabled service, private and invalid addresses,
  missing database, lazy reader loading (success, import error, other
  exception, cached reader), successful lookup, lookup error and `close`.
- `test_config.py`: GeoIP defaults and overrides.

behave (`features/enrichment.feature`, no database file or network needed):

- User agents are classified (outline: desktop Chrome, mobile Safari, a bot)
- A missing user agent gives no device information
- Bots are flagged
- GeoIP can be disabled
- A missing GeoIP database disables lookups

A real GeoLite2 database is not used by the tests: successful lookups are
covered in pytest with a mocked reader.
