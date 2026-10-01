# Archived feature specs

One file per feature-spec version that has ever been deployed, kept so that a
prediction stored months ago can be traced to the exact feature contract that
produced it. `model_v3.json` names the version it was trained against in its
`feature_spec_version` field; the matching file here is the authoritative record of
what that version meant.

**The service does not read this directory.** It loads `../feature_spec.json` and
nothing else. That is a known gap: if the active spec is edited, or a deploy ships a
file that disagrees with the archived copy of the version it claims to be, nothing
notices. `assert_compatible` compares *versions* and *feature names*, so a changed
`scale`, `default` or `clip_max` passes both of its checks.

| Version | Deployed | What changed |
|---|---|---|
| 2.0 | 2025-04-14 | First production spec. |
| 2.1 | 2025-05-08 | Added `has_sso`. Added the `enterprise` plan category. Renormalized `monthly_spend` (scale 100 → 1000) and `support_tickets` (scale 1 → 10) so both features sit on the same order of magnitude as the others. |

Do not edit an archived file. If a feature computation changes, add a new version,
retrain, and bump `feature_spec_version` in the model artifact.
