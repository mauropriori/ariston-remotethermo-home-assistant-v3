[![CodeQL](https://github.com/mauropriori/ariston-remotethermo-home-assistant-v3/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mauropriori/ariston-remotethermo-home-assistant-v3/actions/workflows/codeql.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![HACS Action](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hacs.yml/badge.svg)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hacs.yml)
[![Validate with hassfest](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hassfest.yml/badge.svg)](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/actions/workflows/hassfest.yml)
# Ariston NET remotethermo integration for Home Assistant
This integration inspired by chomupashchuk fantastic work https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2
But it does not use Ariston website. It uses Ariston API what I reversed engineered.

## Cloud resilience defaults

This fork is tuned for accounts with multiple devices and conservative Ariston
cloud usage. Entries with the same credentials share one authenticated client,
discovery result and per-account request queue. Requests are spaced by at least
one second, have a 30-second timeout and honor HTTP 429 backoff. HTTP 5xx
responses are not retried immediately.

The default options are:

| Poll | Default | Minimum | Enabled by default |
| --- | ---: | ---: | :---: |
| Device state | 600 seconds | 60 seconds | Yes |
| Energy | 360 minutes | 60 minutes | No |
| Bus errors | 3600 seconds | 600 seconds | No |

Temperature, target temperature, power and operating-mode entities use the
device-state poll. Energy and bus-error polling can therefore remain disabled
when those are the only required controls. Disabling individual Home Assistant
entities does not reduce requests made by an enabled coordinator; use the
integration options instead.

Energy and bus-error endpoints are optional. If enabled and their first request
fails, core climate/water-heater controls still load and the optional
coordinator retries on its configured schedule. This prevents a Lydos energy
HTTP 500 from blocking the whole device.

Home Assistant 2026.8 introduced a built-in virtual integration with the same
`ariston` domain for Midea-protocol air conditioners. It does not support
Ariston NET products such as Nimbus or Lydos. The hassfest domain-collision
warning is therefore expected for this custom integration.


| [This integration](https://github.com/fustom/ariston-remotethermo-home-assistant-v3)  | [Chomupashchuk's v2 integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2) |
| ------------- | ------------- |
| Uses real API  | Uses Ariston website  |
| Faster set/get data  | Sometimes needs minutes to set/get data |
| Easy to setup with UI | Not so easy to setup (only with configuration.yaml) |
| Integration & devices & entites | Only entites |
| Proper asynchronous integration, clean code | Hard to understand and maintain (ariston.py has more than 4000 lines) |
| Less sensors, switches, etc |  More sensors, switches, etc |
| New code, may contains lot of bugs | Old, tested code |

## TODO
- Localization. Avaliable in english, catalan, italian, russian and ukranian.
- More sensors, switches, binary sersors, selectors, services.
- Exception handling.
- More logs.
- Unit tests.
- Fun.

## Integration was tested on and works with:
- Ariston Alteas One 24
- Ariston Velis Evo
- Ariston Velis Lux
- Ariston Lydos Hybrid

Feel free to test something else and create new issue / pull request if something goes wrong.

## Installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mauropriori&repository=ariston-remotethermo-home-assistant-v3&category=integration) or copy ariston folder to your configuration/custom_components path.
Use the add integration UI to set up your device.

| ![Kazam_screenshot_00003](https://user-images.githubusercontent.com/6751243/146653448-ff7b6f9d-cbf1-4555-9a75-61bf68bc9d3e.png) | ![Kazam_screenshot_00004](https://user-images.githubusercontent.com/6751243/146653484-52e39d78-7c6f-44ae-888d-acf246147290.png) | ![Kazam_screenshot_00010](https://user-images.githubusercontent.com/6751243/147890590-6c4ebf38-16d9-421f-9b81-8f43298ec62f.png) |
:-------------------------:|:-------------------------:|:-------------------------:

![Kazam_screenshot_00011](https://user-images.githubusercontent.com/6751243/147890611-54ae2d28-bf5a-45f8-ba92-e7a00a22615c.png)

![Kazam_screenshot_00012](https://user-images.githubusercontent.com/6751243/147989103-cdac510f-e6f6-461f-a88e-b8ff0204c34f.png)

| ![Kazam_screenshot_00013](https://user-images.githubusercontent.com/6751243/148247717-5211c01c-561f-4a4e-b4b5-47a680e04a68.png) | ![Kazam_screenshot_00009](https://user-images.githubusercontent.com/6751243/146657797-ed14b741-595a-48a6-9126-1acca3beb69f.png) |
:-------------------------:|:-------------------------:

<h1 align="center">Peace Love Freedom</h1>
