# Ariston NET 0.1.0

This is the first release of the `ariston_net` maintenance fork. It is based on
fustom's v3 asynchronous integration and retains the project lineage and credit
described in the README.

## Highlights

- Uses the unique `ariston_net` domain, avoiding the Home Assistant 2026.8 core
  `ariston`/Midea collision.
- Shares one authenticated client and serialized request queue across Nimbus and
  Lydos entries using the same account.
- Adds conservative polling defaults, request timeouts and HTTP 429 backoff.
- Disables optional energy and bus-error polling by default.
- Prevents Lydos energy HTTP 500 responses from blocking core controls.
- Restores HVAC OFF for plant-controlled older Nimbus systems.
- Adds the Lydos Hybrid current-temperature and operating-mode entities.
- Verifies Lydos writes on later scheduled polls with bounded, race-safe retries.
- Pins the companion `python-ariston-api` fork to an exact reviewed commit.

## Reviewed upstream work

Targeted parts of upstream PRs
[#452](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/452),
[#476](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/476),
[#488](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/488),
[#489](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/489),
[#321](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/321)
and
[#445](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/pull/445)
were adapted. Broad changes for untestable BSB/R32, Elco, Nuos and other device
families were intentionally excluded. See the README for the exact provenance
and rationale.

## Validation scope

The hardware available for real-world validation is an Ariston Nimbus 70 M from
2018 (non-R32 generation) and an Ariston Lydos Hybrid 100 L. Other devices retain
their upstream support but have not been regression-tested by this fork.

## Installation note

Keep any legacy Remote Thermo integration disabled while testing this release;
running both against the same account would duplicate cloud traffic. Existing
`ariston` config entries do not migrate automatically to the new `ariston_net`
domain.
