<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Build API And Generated Assets (BAG)

Within a routed scope, inspect added/moved/deleted files, public headers, targets, component
boundaries, `BUILD.gn`, `.gni`, `DEPS`, `OWNERS`, export macros, `.grd`, `.grdp`,
`.xtb`, `.mojom`, `.proto`, WebUI bundles, or generated files.

In the thread ledger, produce `file/symbol | owner target | sources/data/public |
deps | visibility`, exported API/ABI delta, source-to-generated-output chain,
and `BAG-*` rows citing metadata and source-of-truth inputs.

- Account for files in `sources`, `public`, `data`, generated inputs, packaging,
  and tests, including platform-conditional parity.
- Check direct `deps`/`public_deps`, configs, data deps, toolchain context,
  `DEPS`, `specific_include_rules`, visibility, and `testonly`. Do not treat a
  single `gn check` configuration as universal proof.
- Check `OWNERS`, per-file rules, component ownership, and new-directory
  coverage; moves can change review/dependency policy.
- Verify component export macros, template instantiation, vtable/key function,
  symbol visibility, and static/component variants.
- Require public headers to be self-contained and expose clear ownership,
  lifetime, and threading contracts. Trace downstream signature/default/
  semantic migrations; consider virtual/layout/packing/enum ABI effects.
- Do not edit derived outputs. Identify source generator/input, regenerate
  deterministically, and reject unrelated churn.
- For GRIT, check IDs, conditions, scale factors, locale resources,
  placeholders, `.xtb` mapping, packaging, and generated consumers.
- For mojom/proto/WebUI bundles, verify inputs, versions, generated target deps,
  resource maps, bundling assumptions, and tests against regenerated outputs.
