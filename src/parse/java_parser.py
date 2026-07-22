"""Java source -> `CodeNode` objects, via tree-sitter.

Why tree-sitter rather than a Java-specific library: it is a pluggable parser
family with one API across ~40 grammars. Adding Python or C# later (the
generalisation claim) means installing another grammar wheel and writing a new
node-type query, not rewriting this module. `javalang` would work today but
would have to be thrown away the moment a second language appears.

Since tree-sitter 0.22 the grammars ship as their own prebuilt wheels
(`tree-sitter-java`), so there is no C toolchain and nothing to compile. Note
that grammar wheels encode an ABI version: a newer core can refuse a grammar
built against an older one, so if `Language(...)` raises on construction it is a
core/grammar version mismatch, not a bug in this file. If it does fight us on
Windows, `javalang` is listed in requirements.txt as a drop-in fallback -- it is
pure Python and cannot fail to build. Swapping to it means rewriting only this
file, because everything downstream depends on `CodeNode`, not on the parser.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts import CodeNode

#: tree-sitter node types we lift into `CodeNode`s, mapped to `NodeKind`.
#: Fields and enums are deliberately excluded: a bare field declaration carries
#: almost no behavioural signal and would flood the index with near-empty
#: documents, hurting both precision and the orphan count.
NODE_TYPES: dict[str, str] = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "class_declaration": "class",
    "interface_declaration": "interface",
}


def parse_file(path: str | Path, repo_root: str | Path) -> list[CodeNode]:
    """Parse one Java file into its constituent AST nodes.

    Args:
        path: Absolute path to a ``.java`` file.
        repo_root: Used to compute the repo-relative `CodeNode.file_path`.

    Returns:
        One `CodeNode` per declaration of interest, in source order. A file with
        no parseable declarations returns an empty list -- that is not an error.

    Implementation notes:
        - tree-sitter never raises on malformed input; it produces ERROR nodes
          and keeps going. Count them and log the total. Silent partial parses
          are the most likely cause of a mysteriously low recall number.
        - Build `node_id` as ``{file_path}::{name}#{start_line}`` -- Java allows
          overloads, so name alone is not unique within a file.
        - tree-sitter line numbers are 0-based; `CodeNode` is 1-based. Convert.
        - Capture the enclosing class name while descending; `node_doc` needs it
          and re-deriving it later means walking the tree twice.
    """
    raise NotImplementedError


def parse_repo(repo_root: str | Path) -> list[CodeNode]:
    """Parse an entire source tree. Thin loop over `parse_file`.

    Kept separate so the demo can parse a single file quickly during
    development without paying for the whole corpus.
    """
    raise NotImplementedError
