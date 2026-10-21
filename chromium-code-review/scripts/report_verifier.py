#!/usr/bin/env python3
"""Verify files, line numbers, verbatim quotes, functions, and variables in review outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import subprocess


SOURCE_EXTS = (
    "cc|h|mm|c|cpp|mojom|idl|js|ts|py|gn|gni|html|htm|css|json|json5|xml|"
    "grd|grdp|xtb|proto|sql|sh|filelist|tmpl"
)

PATH_RE = re.compile(
    rf"(?<![A-Za-z0-9_.+@{{}}\-/])([A-Za-z0-9_.+@{{}}\-]+(?:/[A-Za-z0-9_.+@{{}}\-]+)+\.(?:{SOURCE_EXTS}))(?![A-Za-z0-9_])"
)
FULL_CITE_RE = re.compile(
    rf"(?<![A-Za-z0-9_.+@{{}}\-/])([A-Za-z0-9_.+@{{}}\-]+(?:/[A-Za-z0-9_.+@{{}}\-]+)+\.(?:{SOURCE_EXTS})):([1-9]\d*)(?:-([1-9]\d*))?"
)
BASENAME_CITE_RE = re.compile(
    rf"(?<![A-Za-z0-9_.+@{{}}\-/])([A-Za-z0-9_.+@{{}}\-]+\.(?:{SOURCE_EXTS})):([1-9]\d*)(?:-([1-9]\d*))?"
)
SHORT_CITE_RE = re.compile(r"(?:`|:|\()\s*:([1-9]\d*)(?:-([1-9]\d*))?(?:`|\))")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"\n]+)"', re.MULTILINE)

REVIEW_ARTIFACT_PREFIXES = (
    "ledger/",
    "verification/",
    "root-cause/",
    "reconciliation/",
    "synthesis/",
    "draft-parts/",
    "gerrit-parts/",
    "draft-sections/",
    "gerrit-sections/",
    "draft-assembly/",
    "challenge/",
    "briefs/",
    "indexes/",
    "packets/",
    "inventory/",
    "gerrit/",
    "skill-snapshot/",
)

SKIP_LINE_PREFIXES = (
    "- **Fix status:**",
    "- **Regression test:**",
    "- **Suggested edit:**",
    "- **Rows:**",
    "- **Severity:**",
    "- **Synthesis item:**",
    "- **Origin:**",
)

KNOWN_IDENTIFIERS = {
    # C/C++/JS/IDL keywords & primitives
    "true", "false", "null", "nullptr", "void", "bool", "int", "char", "float",
    "double", "long", "short", "unsigned", "signed", "size_t", "ssize_t",
    "ptrdiff_t", "intptr_t", "uintptr_t", "uint8_t", "uint16_t", "uint32_t",
    "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t", "const", "auto",
    "return", "if", "else", "for", "while", "switch", "case", "default",
    "break", "continue", "class", "struct", "enum", "union", "namespace",
    "public", "private", "protected", "virtual", "override", "final", "static",
    "constexpr", "consteval", "constinit", "inline", "explicit", "friend",
    "typename", "template", "operator", "sizeof", "alignof", "decltype",
    "noexcept", "mutable", "volatile", "thread_local", "try", "catch", "throw",
    "new", "delete", "this", "super", "async", "await", "function", "var",
    "let", "typeof", "instanceof", "undefined", "NaN", "Infinity",
    # Common namespaces & STL types/helpers
    "std", "mojo", "blink", "content", "base", "net", "url", "storage", "sql",
    "gfx", "ui", "cc", "viz", "gpu", "media", " IPC", "v8", "wtf", "absl",
    "testing", "unique_ptr", "shared_ptr", "weak_ptr", "scoped_refptr",
    "raw_ptr", "raw_ref", "optional", "nullopt", "vector", "string",
    "string_view", "u16string", "u16string_view", "map", "unordered_map",
    "set", "unordered_set", "flat_map", "flat_set", "span", "pair", "tuple",
    "variant", "function", "make_unique", "make_optional", "make_shared",
    "move", "forward", "swap", "min", "max", "clamp",
    # Common Chromium / GTest macros
    "DCHECK", "DCHECK_EQ", "DCHECK_NE", "DCHECK_LT", "DCHECK_LE", "DCHECK_GT",
    "DCHECK_GE", "DCHECK_CALLED_ON_VALID_SEQUENCE", "DCHECK_CURRENTLY_ON",
    "CHECK", "CHECK_EQ", "CHECK_NE", "CHECK_LT", "CHECK_LE", "CHECK_GT",
    "CHECK_GE", "NOTREACHED", "NOTIMPLEMENTED", "FROM_HERE", "SEQUENCE_CHECKER",
    "GUARDED_BY_CONTEXT", " VALID_CONTEXT_REQUIRED", "EXPECT_EQ", "EXPECT_NE",
    "EXPECT_LT", "EXPECT_LE", "EXPECT_GT", "EXPECT_GE", "EXPECT_TRUE",
    "EXPECT_FALSE", "EXPECT_THAT", "EXPECT_CALL", "ASSERT_EQ", "ASSERT_NE",
    "ASSERT_LT", "ASSERT_LE", "ASSERT_GT", "ASSERT_GE", "ASSERT_TRUE",
    "ASSERT_FALSE", "ASSERT_THAT", "IN_PROC_BROWSER_TEST_F",
    "IN_PROC_BROWSER_TEST_P", "TEST", "TEST_F", "TEST_P", "TYPED_TEST",
    # WebIDL / DOMExceptions / standard Web APIs & test targets
    "DOMException", "AbortError", "NotAllowedError", "NotFoundError",
    "NotReadableError", "InvalidStateError", "InvalidModificationError",
    "NoModificationAllowedError", "QuotaExceededError", "SecurityError",
    "SyntaxError", "TypeError", "TypeMismatchError", "DataError",
    "EncodingError", "NetworkError", "OperationError", "RangeError",
    "ReferenceError", "EvalError", "URIError", "DedicatedWorker",
    "SharedWorker", "ServiceWorker", "Window", "Worker", "SharedStorage",
    "structuredClone", "postMessage", "Promise", "ReadableStream",
    "WritableStream", "TransformStream", "ArrayBuffer", "Uint8Array", "Blob",
    "File", "Response", "Request", "Headers", "fetch", "caches", "navigator",
    "window", "document", "self", "location", "origin",
    # Common Chromium build targets & GN flags
    "dcheck_always_on", "is_debug", "is_asan", "is_msan", "is_tsan",
    "is_ubsan", "is_official_build", "content_browsertests",
    "content_unittests", "blink_unittests", "blink_web_tests",
    "unit_tests", "browser_tests", "net_unittests", "services_unittests",
}


def _sibling_paths(rel: str) -> list[str]:
    out = [rel]
    if rel.endswith(".cc"):
        out.append(rel[:-3] + ".h")
    elif rel.endswith(".mm"):
        out.append(rel[:-3] + ".h")
    elif rel.endswith(".h"):
        out.append(rel[:-2] + ".cc")
        out.append(rel[:-2] + ".mm")
    return out


def _is_review_artifact(rel: str) -> bool:
    return rel.startswith(REVIEW_ARTIFACT_PREFIXES)


@dataclass
class WorktreeCorpus:
    root: Path
    worktree: Path | None = None
    revision: str | None = None
    parent: str | None = None
    changed_files: set[str] = field(default_factory=set)
    file_cache: dict[str, str | None] = field(default_factory=dict)
    basename_map: dict[str, str] = field(default_factory=dict)
    corpus_tokens: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, root: Path) -> "WorktreeCorpus":
        pin_path = root / "pin.md"
        if not pin_path.is_file():
            return cls(root=root)
        try:
            pin = pin_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return cls(root=root)
        wt_match = re.search(r"^- Worktree:\s*(\S+)", pin, re.MULTILINE)
        rev_match = re.search(r"^- Revision SHA:\s*(\S+)", pin, re.MULTILINE)
        par_match = re.search(r"^- Parent SHA:\s*(\S+)", pin, re.MULTILINE)
        wt = Path(wt_match.group(1)) if wt_match else None
        if wt is not None and not wt.is_dir():
            wt = None
        changed: set[str] = set()
        in_files = False
        for line in pin.splitlines():
            if line.startswith("- Files changed"):
                in_files = True
                continue
            if in_files:
                m = re.match(
                    r"^  - (.*?)(?: \[[A-Z?]+; \+[0-9?]+/-[0-9?]+\])?$", line
                )
                if m:
                    changed.add(m.group(1))
                elif line.strip():
                    in_files = False
        instance = cls(
            root=root,
            worktree=wt,
            revision=rev_match.group(1) if rev_match else None,
            parent=par_match.group(1) if par_match else None,
            changed_files=changed,
        )
        if wt is not None:
            instance._build_corpus()
        return instance

    def get_file(self, rel: str, allow_git_fallback: bool = True) -> str | None:
        if rel in self.file_cache:
            return self.file_cache[rel]
        if self.worktree is None:
            self.file_cache[rel] = None
            return None
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            self.file_cache[rel] = None
            return None
        candidate = self.worktree / rel
        if candidate.is_file():
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                self.file_cache[rel] = content
                return content
            except OSError:
                pass
        if not allow_git_fallback:
            return None
        # Fallback to git show on revision or parent (e.g. for deleted files)
        for commit in (self.revision, self.parent):
            if not commit:
                continue
            try:
                out = subprocess.run(
                    ["git", "-C", str(self.worktree), "show", f"{commit}:{rel}"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ).stdout.decode("utf-8", errors="replace")
                self.file_cache[rel] = out
                return out
            except (subprocess.CalledProcessError, OSError):
                continue
        self.file_cache[rel] = None
        return None

    def _build_corpus(self) -> None:
        seed_paths: set[str] = set()
        for rel in self.changed_files:
            for sp in _sibling_paths(rel):
                seed_paths.add(sp)
        for md in self.root.glob("**/*.md"):
            rel_md = md.relative_to(self.root).as_posix()
            if rel_md.startswith("skill-snapshot/"):
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in PATH_RE.finditer(text):
                rel = m.group(1)
                pure = PurePosixPath(rel)
                if pure.is_absolute() or ".." in pure.parts or _is_review_artifact(rel):
                    continue
                for sp in _sibling_paths(rel):
                    seed_paths.add(sp)

        for rel in sorted(seed_paths):
            content = self.get_file(rel, allow_git_fallback=False)
            if content is None:
                continue
            self.basename_map.setdefault(PurePosixPath(rel).name, rel)
            self.corpus_tokens.update(
                re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", content)
            )

    def symbol_in_corpus(self, ident: str) -> bool:
        if ident in KNOWN_IDENTIFIERS or ident in self.corpus_tokens:
            return True
        # Generated Blink RuntimeEnabledFeatures constants: k<FeatureName> or <FeatureName>Enabled
        if (
            ident.startswith("k")
            and len(ident) > 2
            and ident[1].isupper()
            and ident[1:] in self.corpus_tokens
        ):
            return True
        if (
            ident.endswith("Enabled")
            and len(ident) > 8
            and ident[:-7] in self.corpus_tokens
        ):
            return True
        # Generated Mojom C++ classes: <Interface>StubDispatch, <Interface>_<Method>_ProxyToResponder
        if ident.endswith("StubDispatch"):
            iface = ident[: -len("StubDispatch")]
            if iface and iface in self.corpus_tokens:
                return True
        if ident.endswith("_ProxyToResponder"):
            prefix = ident[: -len("_ProxyToResponder")]
            parts = [p for p in prefix.split("_") if p]
            if len(parts) >= 2 and all(p in self.corpus_tokens for p in parts):
                return True
        return False


def verify_fragment_text(
    corpus: WorktreeCorpus,
    label: str,
    text: str,
    is_gerrit: bool = False,
) -> list[str]:
    """Verify file paths, line ranges, `- Line:` quotes, off-by-one lines, and symbols."""
    if corpus.worktree is None:
        return []
    errors: list[str] = []
    doc_paths: list[str] = []
    for m in PATH_RE.finditer(text):
        rel = m.group(1)
        if not _is_review_artifact(rel) and ".." not in PurePosixPath(rel).parts:
            if rel not in doc_paths:
                doc_paths.append(rel)
    local_basenames = {PurePosixPath(p).name: p for p in doc_paths}

    # 1. Verify all full path:line[-end] and basename file.ext:line[-end] citations
    for m in FULL_CITE_RE.finditer(text):
        rel, s_str, e_str = m.group(1), m.group(2), m.group(3)
        if _is_review_artifact(rel):
            continue
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append(
                f"{label} cites non-normalized path {rel}"
            )
            continue
        content = corpus.get_file(rel)
        if content is None:
            errors.append(
                f"{label} cites non-existent file in pinned worktree: {rel}"
            )
            continue
        lines = content.splitlines()
        s, e = int(s_str), int(e_str or s_str)
        if e < s or e > len(lines):
            rng = f"{s}-{e}" if e_str else f"{s}"
            errors.append(
                f"{label} citation {rel}:{rng} is out of bounds "
                f"(file has {len(lines)} lines)"
            )

    for m in BASENAME_CITE_RE.finditer(text):
        bname, s_str, e_str = m.group(1), m.group(2), m.group(3)
        if _is_review_artifact(bname):
            continue
        rel = local_basenames.get(bname) or corpus.basename_map.get(bname)
        if not rel:
            errors.append(
                f"{label} cites unknown file basename {bname}:{s_str}"
            )
            continue
        content = corpus.get_file(rel)
        if content is None:
            errors.append(
                f"{label} cites non-existent file in pinned worktree: {rel}"
            )
            continue
        lines = content.splitlines()
        s, e = int(s_str), int(e_str or s_str)
        if e < s or e > len(lines):
            rng = f"{s}-{e}" if e_str else f"{s}"
            errors.append(
                f"{label} citation {bname}:{rng} is out of bounds "
                f"(file {rel} has {len(lines)} lines)"
            )

    # 2. Verify `- Line: `...`` verbatim quote in Gerrit inline fragments/comments
    if is_gerrit:
        target_blocks = list(
            re.finditer(
                rf"(?m)^(?:###\s+)?([A-Za-z0-9_.+@{{}}\-]+(?:/[A-Za-z0-9_.+@{{}}\-]+)+\.(?:{SOURCE_EXTS})):([1-9]\d*)(?:-([1-9]\d*))?\s*$",
                text,
            )
        )
        for idx, tm in enumerate(target_blocks):
            rel, s_str, e_str = tm.group(1), tm.group(2), tm.group(3)
            block_end = (
                target_blocks[idx + 1].start()
                if idx + 1 < len(target_blocks)
                else len(text)
            )
            block = text[tm.end() : block_end]
            lm = re.search(r"(?m)^-\s*Line:\s*(`+)(.+?)\1\s*$", block)
            if lm is None:
                errors.append(
                    f"{label} Gerrit target {rel}:{s_str} lacks a "
                    "'- Line: `<verbatim line>`' field"
                )
                continue
            quoted = lm.group(2).strip()
            content = corpus.get_file(rel)
            if content is not None:
                lines = content.splitlines()
                s, e = int(s_str), int(e_str or s_str)
                if 1 <= s <= e <= len(lines):
                    window = [ln.strip() for ln in lines[s - 1 : e]]
                    joined = " ".join(window)
                    if quoted not in window and quoted not in joined:
                        actual_preview = window[0] if window else ""
                        rng = f"{s}-{e}" if e_str else f"{s}"
                        errors.append(
                            f"{label} Gerrit '- Line:' quote `{quoted}` does "
                            f"not match pinned file {rel}:{rng} verbatim "
                            f"(actual line {s}: `{actual_preview}`)"
                        )

    # 3. Verify line-level symbol accuracy (off-by-one) & symbol existence
    in_fence = False
    for raw_line in text.splitlines():
        if raw_line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or any(raw_line.startswith(p) for p in SKIP_LINE_PREFIXES):
            continue
        spans = list(CODE_SPAN_RE.finditer(raw_line))
        if not spans:
            continue
        cites: list[tuple[int, int, list[str], int, int]] = []
        for cm in FULL_CITE_RE.finditer(raw_line):
            if not _is_review_artifact(cm.group(1)):
                cites.append(
                    (
                        cm.start(),
                        cm.end(),
                        [cm.group(1)],
                        int(cm.group(2)),
                        int(cm.group(3) or cm.group(2)),
                    )
                )
        for bm in BASENAME_CITE_RE.finditer(raw_line):
            rel = local_basenames.get(bm.group(1)) or corpus.basename_map.get(
                bm.group(1)
            )
            if rel and not _is_review_artifact(rel):
                cites.append(
                    (
                        bm.start(),
                        bm.end(),
                        [rel],
                        int(bm.group(2)),
                        int(bm.group(3) or bm.group(2)),
                    )
                )
        cites.sort(key=lambda item: item[0])
        for sm in SHORT_CITE_RE.finditer(raw_line):
            prev = [c for c in cites if c[1] <= sm.start()]
            rels = list(
                dict.fromkeys(([prev[-1][2][0]] if prev else []) + doc_paths)
            )
            if rels:
                cites.append(
                    (
                        sm.start(),
                        sm.end(),
                        rels,
                        int(sm.group(1)),
                        int(sm.group(2) or sm.group(1)),
                    )
                )

        # (a) Citation-paired symbol & off-by-one checks
        for c_start, c_end, rels, s, e in cites:
            for sp in spans:
                if sp.start() <= c_start and sp.end() >= c_end:
                    continue
                if sp.end() > c_start:
                    continue
                between = raw_line[sp.end() : c_start]
                if not re.fullmatch(
                    r"\s*(?:at|in|on|from|line|\(|—|-|:)*\s*", between
                ):
                    continue
                snippet = sp.group(1).strip()
                clean = re.sub(r"\"[^\"]*\"|\x27[^\x27]*\x27", "", snippet)
                if "/" in clean or clean.startswith("--"):
                    continue
                if s == e:
                    primary_rel = rels[0]
                    content = corpus.get_file(primary_rel)
                    if content is not None:
                        lines = content.splitlines()
                        if 1 <= s <= len(lines):
                            ident_m = re.search(
                                r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\))?$", clean
                            )
                            if ident_m:
                                ident = ident_m.group(1)
                                if (
                                    len(ident) >= 3
                                    and ident not in KNOWN_IDENTIFIERS
                                    and not re.search(
                                        rf"\b{re.escape(ident)}\b", lines[s - 1]
                                    )
                                ):
                                    enclosing = snippet.endswith("()") and any(
                                        re.search(
                                            rf"\b{re.escape(ident)}\s*\(",
                                            lines[k - 1],
                                        )
                                        for k in range(max(1, s - 35), s)
                                    )
                                    if not enclosing:
                                        snippet_idents = [
                                            t
                                            for t in re.findall(
                                                r"\b[A-Za-z_][A-Za-z0-9_]*\b",
                                                clean,
                                            )
                                            if len(t) >= 3
                                        ]
                                        nearby = [
                                            ln
                                            for ln in range(
                                                max(1, s - 2),
                                                min(len(lines), s + 2) + 1,
                                            )
                                            if ln != s
                                            and all(
                                                re.search(
                                                    rf"\b{re.escape(i)}\b",
                                                    lines[ln - 1],
                                                )
                                                for i in snippet_idents
                                            )
                                        ]
                                        if nearby:
                                            errors.append(
                                                f"{label} cites {primary_rel}:{s} "
                                                f"for `{snippet}`, but it is on "
                                                f"line {nearby[0]}"
                                            )

                combined = "\n".join(
                    corpus.get_file(p) or ""
                    for r in rels
                    for p in _sibling_paths(r)
                )
                if combined.strip():
                    parts = [
                        p
                        for p in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", clean)
                        if len(p) >= 3 and p not in KNOWN_IDENTIFIERS
                    ]
                    code_parts = [
                        p
                        for p in parts
                        if "_" in p
                        or any(c.isupper() for c in p[1:])
                        or "::" in clean
                        or "(" in clean
                    ]
                    if "." in clean and "::" not in clean:
                        m_dot = re.search(
                            r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", clean
                        )
                        code_parts = (
                            [m_dot.group(1)]
                            if m_dot and m_dot.group(1) not in KNOWN_IDENTIFIERS
                            else []
                        )
                    for cp in code_parts:
                        if (
                            not re.search(rf"\b{re.escape(cp)}\b", combined)
                            and not corpus.symbol_in_corpus(cp)
                        ):
                            errors.append(
                                f"{label} cites unknown symbol `{cp}` "
                                f"(in `{snippet}`) at {rels[0]}"
                            )

        # (b) Corpus-wide check on qualified symbols, member vars, and functions
        for sp in spans:
            snippet = sp.group(1).strip()
            if (
                "/" in snippet
                or "specialist:" in snippet
                or "graph:" in snippet
                or FULL_CITE_RE.search(snippet)
                or BASENAME_CITE_RE.search(snippet)
            ):
                continue
            clean = re.sub(r"\"[^\"]*\"|\x27[^\x27]*\x27", "", snippet)
            candidates: set[str] = set()
            if "::" in clean:
                candidates.update(
                    re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", clean)
                )
            candidates.update(re.findall(r"\b[a-z][a-z0-9_]*_\b", clean))
            if "." not in clean or "::" in clean:
                candidates.update(
                    re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", clean)
                )
                candidates.update(
                    re.findall(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b", clean)
                )
                candidates.update(
                    re.findall(
                        r"\b([A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*)\b",
                        clean,
                    )
                )
                candidates.update(
                    re.findall(r"\b(k[A-Z][A-Za-z0-9]+)\b", clean)
                )
            else:
                m_dot = re.search(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", clean)
                if m_dot:
                    candidates.add(m_dot.group(1))
            for cand in sorted(candidates):
                if len(cand) < 4:
                    continue
                if not corpus.symbol_in_corpus(cand):
                    errors.append(
                        f"{label} references unknown symbol or variable "
                        f"`{cand}` (in `{snippet}`) not found in worktree corpus"
                    )

    return list(dict.fromkeys(errors))
