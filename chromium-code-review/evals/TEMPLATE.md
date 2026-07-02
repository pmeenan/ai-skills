# CL <number> PS<n> — <short name>

- CL: https://chromium-review.googlesource.com/c/chromium/src/+/<number>
- Pinned patchset: <n> (revision `<sha>`)
- Domain: <net/http cache, socket throttling, blink loader, …>
- Why in corpus: <one line — what runs got wrong here>
- Mode: <full review | follow-up review against PS<m> feedback>

## Must-find findings

| id | severity | finding (one line) | location | owning roster thread |
| --- | --- | --- | --- | --- |
| F1 | P1 | <e.g. discarded `Push` return drops bytes on partial acceptance> | path:line | Data Lineage |
| F2 | P2 | … | path:line | State/Persistence/Cache |

## Known traps (must-not-report / must-calibrate)

| id | trap | correct disposition |
| --- | --- | --- |
| T1 | <looks like a UAF but the guard at path:line prevents it> | refute with the guard citation |
| T2 | <untested flag-OFF branch that only gates memoization> | P3 test polish, not a blocker |

## Process expectations

- Roster entries that must trigger: <…>
- Roster entries legitimately not-triggered: <…>
- <e.g. "the Mode × Host matrix must contain cells X, Y, Z">

## Results

### <date> — <model>

- found: <F-ids> | found-miscalibrated: <F-ids> | missed: <F-ids> |
  false positives: <count, incl. tripped traps>
- process: <roster/spawn/ledger/reconciliation/gate compliance>
- notes: <anything that should change the skill or the expectations>
