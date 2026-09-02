# Discarded Candidates: DOM Core & Tree Mutation

Subsystem: `third_party/blink/renderer/core/dom/`, `core/editing/serializers/`

---

## DOM-01: `Element::setInnerHTML` Buffer Pre-allocation
- **Concept:** Pre-allocate string builders or parser buffers based on input HTML length during `setInnerHTML`.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Negligible impact (`+0.02%`).
- **Causal Failure Mechanism:** String materialization and HTML tokenizer state machine instantiation dwarf initial buffer allocation costs. The allocation is already handled efficiently by WTF `StringBuilder` exponential growth.
- **Durable Invariant:** Do not attempt pre-sizing or capacity reservation optimizations for HTML parser input buffers.

---

## DOM-02: `HTMLCollection` Sequential Index Caching
- **Concept:** Cache the last accessed integer index and corresponding node pointer in `HTMLCollection` to optimize `collection[i]` sequential iteration loops.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Flat delta (`+0.07%`).
- **Causal Failure Mechanism:** Blink already implements `CollectionItemsCache` and `CollectionIndexCache` inside `ContainerNode`. Adding an extra layer of index caching at the IDL wrapper level added redundant branch checks without avoiding tree walks.
- **Durable Invariant:** Do not add outer index/iterator caches to DOM collections; internal collection caches already optimize forward/backward traversal.

---

## DOM-03: `Element::SetAttributeInternal` Redundancy Check
- **Concept:** In `Element::SetAttributeInternal`, check if `getAttribute(name) == new_value` and return early to avoid attribute synchronization and mutation records.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Net negative (`-0.20%`).
- **Causal Failure Mechanism:** Modern JavaScript UI frameworks (React, Vue, Preact, Lit) already maintain virtual DOM or template state and omit setting unchanged attributes in user-space script. The C++ check was evaluated on every legitimate attribute update where strings differed, adding string equality comparison overhead to every mutation.
- **Durable Invariant:** Avoid adding duplicate-check branches to general DOM attribute setters. Frameworks already deduplicate in JS; C++ checks only penalize genuine mutations.

---

## DOM-04: `ContainerNode::NotifyNodeRemoved` Leaf Short-Circuit
- **Concept:** When removing a leaf node, bypass subtree walks in `NotifyNodeRemoved` by checking `!node->hasChildren()`.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Regressed `TodoMVC-JavaScript-ES5-Complex-DOM` (`-1.56%`).
- **Causal Failure Mechanism:** Blink's `ContainerNode::RemoveBetween` already batches removal notifications. Adding pre-removal checks on every individual child detachment added redundant branch evaluations without reducing work in batched removal routines.
- **Durable Invariant:** Do not add outer leaf-node guards to removal notification pipelines; batch removal routines (`RemoveChildren`, `RemoveBetween`) already optimize unparented and childless subtrees.

---

## DOM-05: `ContainerNode::RemoveChildren` Batch Detachment
- **Concept:** Manually unlink child node linked-list pointers in a flat loop inside `RemoveChildren()` before triggering tree detachments to optimize bulk deletions.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `e7fe5448749d0`).
- **Empirical Result:** Stat-sig regression on `NewsSite-Nuxt` (`-0.88%`).
- **Causal Failure Mechanism:** Pre-unlinking child pointers disrupted Blink's unified layout tree detachment (`DetachLayoutTree`) and invalidated DOM tree structural invariants expected by subsequent MutationObserver notification scopes.
- **Durable Invariant:** Never modify DOM tree sibling/parent pointers ahead of Blink's standard `Node::DetachLayoutTree` and `ContainerNodeWillBeRemoved` sequence.

---

## DOM-06: `SelectorQuery` Childless Container Bypass & `SpaceSplitString` Single-Class
- **Concept:** In `SelectorQuery::QueryAll()`, return early if `!root_node.hasChildren()`. In `SpaceSplitString`, optimize single-class elements by checking `vector_.front()`.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `94aa1c3d49674`).
- **Empirical Result:** Sub-threshold suite delta `+0.18% [-0.21%, +0.58%]` ($t = 0.94$); zero stat-sig story wins.
- **Causal Failure Mechanism:** While directionally positive in `TodoMVC-Backbone` (`+1.18%`), querying selectors against childless nodes is rare in modern frameworks. The per-call cycle savings were too small (<5 cycles) to cross statistical significance.
- **Durable Invariant:** Selector query optimizations must address selector matching complexity (e.g. bloom filters or rule sharing) rather than trivial container empty checks.
