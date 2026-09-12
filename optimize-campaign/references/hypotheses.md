# Redundancy hypothesis classes

A counter tests one hypothesis about one function. A row closed by that
count is closed for that hypothesis only. This catalogue names the classes
of hypothesis the campaign considers for each phase of work, so that a
decomposition is judged not only on whether every row above the floor has
a count, but on whether the counts asked the questions that phase can
answer. `campaign.py depth-audit` lists, per story and phase, the rows
above the floor whose count belongs to an ancestor and the classes no
packet in that story has probed for that phase; exhaustion cannot be
claimed while it has open entries.

Every packet records its class (`redundancy_evidence.py --hypothesis-class
<id>`); packets reduced before the field existed take their class from the
site table at the end of this file.

## The classes

| id | the hypothesis | key | `applicable` | reading |
|---|---|---|---|---|
| `unchanged-input` | the same inputs are processed again and the result could have been kept | the inputs the result depends on (text hash, style, constraint space, tree version) | `counter->HasSeen(key)` or "the input's version is unchanged since the last result" | repeat time fraction = work that a result cache could skip |
| `no-op-mutation` | a write leaves the state it writes unchanged | (target, name, value hash) | the new value equals the current one; the child is already in place; the container is already empty | applicable time fraction = writes that could return early |
| `redundant-trigger` | the whole call has nothing to do | (target, version) | nothing is dirty at entry; no layout object to detach; the path is empty | applicable time fraction = calls that could be skipped at entry |
| `cache-hit-path` | an existing cache holds the answer but the machinery before the lookup is paid in full | the cache key (URL, string identity, selector, text and font) | the cache holds a complete answer at entry (`MemoryCache::Get` complete, `StringCache` hit, shape cache hit) | applicable time fraction = the cost of reaching an answer that already existed; the candidate is a fast path, not a cache |
| `unconsumed-result` | work whose result nothing reads | (target, version) | the consumer does not run before the result is invalidated (ink bounds never painted, layout of a subtree never displayed, a clean subtree walked) | applicable time fraction = results computed for nobody |
| `notification-fanout` | listeners, observers or reactions are notified and nobody is listening | (event or reaction type, target) | no listener, observer or reaction is registered for this notification | applicable time fraction = dispatch machinery with no recipient |
| `copy-churn` | unchanged data is copied or re-serialized | (source identity, size hash) | the same source was copied before in this update | repeat time fraction = copies of what was already there |

A predicate that tests an existing cache's *hit* (round 28: the AtomicString
counter, the proposed FrameShapeCache test) measures the cheap path and
belongs to `cache-hit-path` only if the scope times the whole call so the
cost of reaching the hit is what is measured. For `unchanged-input` the
predicate is the repeat itself (`HasSeen`), so that a cache the engine
already has shows up as cheap repeats and a missing one as expensive
repeats.

## Which classes each phase must answer

| phase | classes |
|---|---|
| style-recalc, active-style-update | unchanged-input, redundant-trigger, notification-fanout |
| layout, line-breaking, min-max-sizing | unchanged-input, redundant-trigger, unconsumed-result |
| text-shaping, ink-overflow | unchanged-input, cache-hit-path, unconsumed-result |
| prepaint, paint, layerization | unchanged-input, redundant-trigger, unconsumed-result |
| hit-test | redundant-trigger, unchanged-input |
| html-parsing | unchanged-input, copy-churn |
| dom-mutation | no-op-mutation, notification-fanout, redundant-trigger |
| attribute-change | no-op-mutation, notification-fanout |
| selector-query | unchanged-input, cache-hit-path |
| event-dispatch | notification-fanout, redundant-trigger |
| custom-element-reactions | notification-fanout |
| text-input-state | redundant-trigger |
| resource-loading | cache-hit-path, unchanged-input |
| bindings | copy-churn, cache-hit-path, unchanged-input |
| canvas-2d | unchanged-input, copy-churn, redundant-trigger |
| lifecycle | redundant-trigger |

A class is probed for a story and phase when a packet in that story
carries the class and its probed function is in that phase; a
`redundant-trigger` packet on a lifecycle root (the frame update, the
lifecycle phases) counts for every phase beneath it, since a skipped
update skips them all. A class the host judges inapplicable to a story's
phase is recorded with `campaign.py exclude-hypothesis --story S --phase P
--class C --note <why>` and stays visible in the audit as excluded; the
operator proposes exclusions in the report, never records them.

## Phases the audit assigns beyond the lens

The lens phases (`campaign_lens.own_phase`) cover style, layout, paint,
parsing, DOM mutation, attributes, queries, events and custom elements.
The audit adds: `resource-loading` (ResourceFetcher, ImageLoader,
ImageResource, PrepareResourceRequestForCacheAccess, MemoryCache),
`text-shaping` (HarfBuzzShaper, InlineNode::ShapeText, ShapeResult,
PlainTextNode), `bindings` (ToBlinkString, V8Union*::Create,
V8PerContextData::CreateWrapper, V8*::IndexedPropertyGetterCallback),
`canvas-2d` (Canvas2DRecorderContext, BaseRenderingContext2D,
Canvas2DResourceProvider), `lifecycle` (LocalFrameView::UpdateLifecyclePhases,
UpdateStyleAndLayout*, RequestMainFrameUpdate, WidgetBase::UpdateVisualState).

## Classes of the sites reduced before the field existed

| site | class |
|---|---|
| style/element-recalc-style, css/element-rule-collector-calls, css/element-rule-collector-calls-within-resolve, style/style-engine-rebuild-layout-tree, style/update-active-style-shadow-root | unchanged-input |
| layout/box-cached-layout-result, layout/inline-layout-algorithm, layout/oof-layout-part, layout/simplified-layout-algorithm, layout/layout-svg-text | unchanged-input |
| flex/min-max-sizes-func | cache-hit-path |
| lifecycle/update-lifecycle-phases, root/request-main-frame-update, root/document-update-style-and-layout, root/update-style-and-layout-for-node, hittest/layout-view-hit-test, hittest/tree-scope-element-from-point, input/widget-base-update-text-input-state | redundant-trigger |
| paint/pre-paint-tree-walk, paint/run-paint-lifecycle-phase, paint/box-fragment-paint, compositing/layerizer-layerize-group, fonts/shape-result-view-ink-bounds | unchanged-input |
| parser/parse-html-fragment, parser/domparser-parse-from-string, dom/document-import-node, dom/container-node-query-selector, dom/container-node-query-selector-all, dom/htmlcollection-item, dom/v8-nodelist-indexed-property, canvas/flush-canvas-internal | unchanged-input |
| dom/element-set-attribute-hinted, dom/element-set-attribute-without-validation, dom/input-set-value-binding, dom/container-node-append-child, dom/container-node-append-children, dom/container-node-insert-before, dom/container-node-remove-children | no-op-mutation |
| dom/detach-layout-tree, canvas/canvas-2d-recorder-context-fill, canvas/canvas-2d-recorder-context-stroke | redundant-trigger |
| events/event-dispatcher-dispatch, custom-elements/pop-invoking-reactions | notification-fanout |
| bindings/to-blink-string, bindings/to-blink-atomic-string | cache-hit-path |
