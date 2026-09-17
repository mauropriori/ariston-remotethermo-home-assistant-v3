[![CodeQL](https://github.com/mauropriori/ariston_net/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mauropriori/ariston_net/actions/workflows/codeql.yml)
[![HACS Action](https://github.com/mauropriori/ariston_net/actions/workflows/hacs.yml/badge.svg?branch=main)](https://github.com/mauropriori/ariston_net/actions/workflows/hacs.yml)
[![Validate with hassfest](https://github.com/mauropriori/ariston_net/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/mauropriori/ariston_net/actions/workflows/hassfest.yml)
[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom_repository-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

# Ariston NET for Home Assistant

This is a focused maintenance fork of
[fustom/ariston-remotethermo-home-assistant-v3](https://github.com/fustom/ariston-remotethermo-home-assistant-v3).
It keeps fustom's asynchronous Home Assistant integration and targets reliable,
low-volume use of the Ariston Remote Thermo cloud with multiple devices.

The Home Assistant domain of this fork is **`ariston_net`**. It can therefore
coexist with Home Assistant's built-in `ariston` virtual integration for
Midea-protocol air conditioners and with an installed legacy custom integration.
Do not, however, keep two Remote Thermo integrations active with the same
Ariston account: duplicate polling would increase the risk of cloud rate limits.

## Credits and project lineage

This project would not exist without the work of:

- **[Chomupashchuk](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2)**,
  who created the original v2 integration and established broad Ariston Remote
  Thermo support.
- **[fustom](https://github.com/fustom/ariston-remotethermo-home-assistant-v3)**,
  who designed and maintained the v3 asynchronous integration and the
  [`python-ariston-api`](https://github.com/fustom/python-ariston-api) library on
  which this fork is based.
- All contributors who reported devices, investigated the undocumented cloud
  behavior, and submitted fixes and pull requests to the upstream projects.

This fork is not an official Ariston product. Copyright and authorship of the
upstream code remain with their respective contributors; see the repository
history and [LICENSE](LICENSE).

## What this fork changes

Compared with the fustom `main` baseline used by this fork, it adds:

- one authenticated client, discovery cache and serialized request queue shared
  by all config entries using the same account;
- a minimum one-second spacing between cloud requests, a 30-second request
  timeout, and server-directed HTTP 429 backoff;
- no immediate retry storm for HTTP 5xx responses;
- conservative polling defaults designed for two devices on one account;
- energy and bus-error coordinators disabled by default and configurable
  independently;
- isolation of optional metric failures, so an energy HTTP 500 cannot prevent
  climate or water-heater controls from loading;
- safe cleanup and reuse of the shared client across reloads, failed setup and
  Home Assistant shutdown;
- restoration of Home Assistant's HVAC `OFF` mode for older Nimbus systems that
  expose plant-level OFF but omit it from their zone-mode list;
- Lydos Hybrid current-temperature and operating-mode entities;
- confirmation of Lydos temperature and mode writes on later scheduled polls,
  without extra reads and without allowing a stale retry to overwrite a newer
  command;
- a corrected heat-pump feature gate (`HP_SYS`) for the relevant sensor;
- the unique `ariston_net` domain and HACS package name.

The integration uses the matching maintenance fork of `python-ariston-api`,
pinned to an exact commit for reproducible installs.

## Problems addressed

### Lydos energy endpoint returns HTTP 500

Energy data is optional. It is disabled by default; when explicitly enabled, a
failed first refresh is logged but no longer aborts the entire config entry.
Temperature, target temperature, power and operating-mode controls remain
available.

### Rate limits and multiplied calls with two devices

Nimbus and Lydos entries using the same credentials now share one cloud client
and one per-account request queue. Requests are serialized and spaced rather
than being emitted concurrently by two independent sessions. HTTP 429 responses
honor the server's retry delay.

Disabling individual Home Assistant entities does not stop their coordinator.
Use the integration options to disable energy and bus-error polling or to
increase the polling intervals.

### Nimbus can no longer be switched off from Home Assistant

Recent Home Assistant versions require `HVACMode.OFF` to be advertised before
the standard turn-off path can use it. Older Nimbus/Galevo devices may support
plant-level OFF without listing zone-level OFF. This fork advertises OFF when
plant-mode control is available and sends the normal plant OFF command.

### Lydos commands sometimes revert or appear ignored

The cloud can acknowledge a write before the following state snapshot reflects
it. Lydos temperature and non-BOOST mode writes are confirmed on subsequent
scheduled polls and retried a bounded number of times. A coordinator lock makes
the poll/verification sequence atomic with respect to new user commands, so an
old retry cannot replace a newer choice.

## Upstream pull requests used selectively

The following open upstream PRs were reviewed. They were not merged wholesale;
only the parts relevant to the available hardware and current problems were
adapted on top of that upstream `main` baseline.

| Upstream PR | What was retained or adapted | Why it was not merged wholesale |
| --- | --- | --- |
| [#452](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/452) | Conservative intervals and explicit rate-limit handling. This fork extends the idea with one shared account client, a serialized library-level queue, timeout handling and `Retry-After` support. | Coordinator-only backoff would still allow the two device entries and optional coordinators to multiply concurrent requests. |
| [#476](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/476) | An energy failure must not abort setup. The same isolation was generalized to both energy and bus-error coordinators, which are now opt-in. | The original change covered only the initial energy refresh and still created the optional coordinator unconditionally. |
| [#488](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/488) | Confirm water-heater writes during later normal polls, with no additional read calls. The implementation is limited to Lydos Hybrid and hardened with serialization, bounded retries and stale-command protection. | Applying it to every water-heater model could change established behavior on hardware that is unavailable for testing. |
| [#489](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/489) | The `HP_SYS` feature-gating correction for heat-pump status. | New BSB, resistor, weather, DHW boost and buffer entities were omitted because they cannot be validated on the two available devices and would add surface area and cloud writes. |
| [#321](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/321) | The useful Lydos Hybrid current-temperature and operating-mode exposure, with the device-provided temperature unit. | The PR contains broad, older structural and typing changes unrelated to these entities; only the small compatible subset was retained. |
| [#445](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/445) | The identified need to expose climate OFF when Nimbus omits it from zone capabilities. | The large PR mixes unrelated zone, metric and configuration changes. This fork uses plant-level OFF directly instead of the proposed summer-mode workaround. |

## Deliberately excluded changes

Support aimed specifically at BSB/R32 heat pumps, Elco/Remocon devices, Nuos
Split, additional Velis variants, gas-calorific configuration and broad new
energy/diagnostic entities has not been included. Those changes may be valuable,
but they cannot be responsibly verified with the hardware available to this
fork. They can be reconsidered individually when a reproducible issue, device
trace and tester are available.

## Hardware validation scope

Real-world validation for this fork is intentionally limited to:

- **Ariston Nimbus 70 M, 2018 generation, non-R32**;
- **Ariston Lydos Hybrid 100 L**.

The upstream project supports more models, and that code remains present unless
explicitly documented otherwise. The list above defines what can be regression
tested by this fork's maintainer; it is not a claim that other upstream-supported
devices have been removed.

## Cloud-resilience defaults

| Poll | Default | Minimum | Enabled by default |
| --- | ---: | ---: | :---: |
| Device state | 600 seconds | 60 seconds | Yes |
| Energy | 360 minutes | 60 minutes | No |
| Bus errors | 3600 seconds | 600 seconds | No |

Temperature, target temperature, power and operating mode all use the main
device-state poll. For the two-device setup described above, start with these
defaults and leave optional polling disabled unless those data are truly needed.

## Why the integration is named `ariston_net`

Home Assistant 2026.8 introduced a built-in virtual integration using the
`ariston` domain for Ariston-branded air conditioners that communicate through
the Midea protocol. It does **not** support Remote Thermo products such as
Nimbus heat pumps or Lydos water heaters, but Home Assistant integration domains
must still be unique.

Using `ariston_net` avoids shadowing the core integration, removes the domain
collision, makes the Remote Thermo purpose explicit and permits side-by-side
installation during validation. Because this is a new domain, legacy `ariston`
config entries are not migrated automatically.

## Installation with HACS

1. In HACS, add
   `https://github.com/mauropriori/ariston_net` as a
   custom **Integration** repository.
2. Install **Ariston NET** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Ariston NET**.
4. Sign in and select the Nimbus. Repeat the add-integration flow to select the
   Lydos Hybrid. Entries with the same credentials automatically share one
   cloud client.
5. Keep the legacy Remote Thermo custom integration disabled while testing, so
   both integrations do not poll the same account.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mauropriori&repository=ariston_net&category=integration)

For a manual installation, copy `custom_components/ariston_net` into the
`custom_components` directory under the Home Assistant configuration directory,
then restart Home Assistant.

## Reporting problems

When opening an issue, include the exact model, production generation, Home
Assistant version, integration version, whether energy/bus-error polling is
enabled, and a redacted traceback. Never publish Ariston credentials, gateway
identifiers or serial numbers.

<h1 align="center">Peace Love Freedom</h1>
