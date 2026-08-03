<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Accessibility And Internationalization (AXI)

Trigger on UI controls, focus/input, DOM/AX trees, roles/names/states/actions,
announcements, color/animation, user-visible strings, GRIT, locale/time zone,
plurals, formatting, text direction, or layout mirroring.

In the thread ledger, produce `control/state | role/name/state/action |
focus/keyboard | AX event`, `message | resource | placeholders/plural | locale |
direction`, representative mode/locale evidence, and `AXI-*` rows.

- Verify roles, accessible names/descriptions, state/value, actions, and AX tree
  relationships across dynamic insert/remove/reparent/visibility/errors.
- Preserve logical focus through open/close/navigation/rerender/deletion; provide
  keyboard completeness, visible focus, sensible tab order, and no trap.
- Emit correct tree/state/live-region events without stale or duplicate
  announcements. Test screen-reader-visible semantics and dynamic updates.
- Preserve contrast/meaning in high contrast and forced colors; do not use color
  alone. Respect zoom/text scaling and reduced motion.
- Localize user-visible strings without concatenated fragments. Preserve
  translator-reorderable typed placeholders and locale plural/select rules.
- New or changed translatable strings need translator context: a meaningful
  `desc`, and the screenshot metadata Chromium's translation pipeline expects
  for new UI strings. A missing screenshot/desc is a polish candidate, not a
  silent pass.
- Format date/time/duration/number/percent/currency/list/collation with intended
  locale/time zone; never use localized text as protocol/storage format.
- Check RTL mirroring, start/end semantics, bidi isolation for mixed or user
  text, directional icons, and cursor/navigation behavior.
- Test long/plural/RTL/non-Latin text, graphemes/surrogates/normalization, locale
  changes, multiline/truncation, keyboard-only use, and focus restoration.
