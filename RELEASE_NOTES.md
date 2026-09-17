# Ariston NET 0.1.2

This patch release fixes Lydos Hybrid temporary BOOST recovery and removes
automatic command replay that could compete with the official Ariston app.

After BOOST, malformed cloud modes (`null`, `0`, unknown numbers or strings,
booleans, arrays and objects) no longer make the entity unusable. The companion
API library preserves the stable mode that preceded BOOST without writing it
back to the appliance. Delayed snapshots, BOOST initiated by the official app,
Home Assistant restarts during BOOST and repeated BOOST commands are covered by
the regression suite.

Temperature and non-BOOST mode writes are now checked passively on the next
scheduled poll. A mismatch is logged once and is never replayed, preventing a
stale Home Assistant value from overwriting a later app-side change and avoiding
additional API calls.

It includes all functionality introduced in the initial 0.1.0 release and
retains the project lineage and credit described in the README.

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
- Passively verifies Lydos writes without retrying or adding API calls.
- Preserves the last stable Lydos mode across temporary BOOST cloud anomalies.
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
