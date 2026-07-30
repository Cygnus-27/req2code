"""Java source -> `CodeNode` objects, via tree-sitter.

Why tree-sitter rather than a Java-specific library: it is a pluggable parser
family with one API across ~40 grammars. Adding Python or C# later (the
generalisation claim) means installing another grammar wheel and writing a new
node-type query, not rewriting this module.

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

from functools import lru_cache
from pathlib import Path

import tree_sitter
import tree_sitter_java

from src.contracts import CodeNode, NodeKind
from src.ingest.text_io import read_text

#: tree-sitter node types we lift into `CodeNode`s, mapped to `NodeKind`.
#: Fields and enums are deliberately excluded: a bare field declaration carries
#: almost no behavioural signal and would flood the index with near-empty
#: documents, hurting both precision and the orphan count.
NODE_TYPES: dict[str, NodeKind] = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "class_declaration": "class",
    "interface_declaration": "interface",
}

#: Container types we descend through looking for members.
_CONTAINERS = frozenset({"class_declaration", "interface_declaration"})

#: Comment node types across tree-sitter-java grammar versions. Older grammars
#: emit a single "comment" type; newer ones split line and block comments.
_COMMENT_TYPES = frozenset({"comment", "line_comment", "block_comment"})


@lru_cache(maxsize=1)
def _parser() -> tree_sitter.Parser:
    """Build the parser once and reuse it. Cached because Language construction
    is the expensive part and it is entirely stateless."""
    language = tree_sitter.Language(tree_sitter_java.language())
    return tree_sitter.Parser(language)


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _child_text(node: tree_sitter.Node, field: str, source: bytes) -> str:
    child = node.child_by_field_name(field)
    return _node_text(child, source) if child is not None else ""


def _signature(node: tree_sitter.Node, source: bytes) -> str:
    """Return type + name + parameter list, as source text.

    Parameter names are the point here -- they carry real domain vocabulary
    (``int idRefreshmentPoint``), which is exactly the signal node_doc mines.
    """
    return_type = _child_text(node, "type", source)
    name = _child_text(node, "name", source)
    params = _child_text(node, "parameters", source)
    return " ".join(part for part in (return_type, name + params) if part).strip()


def _leading_doc(node: tree_sitter.Node, source: bytes) -> str:
    """Return the comment block immediately preceding a declaration, if any.

    Javadoc is a *preceding sibling* of the declaration, not a child, so it does
    not appear in `CodeNode.text`. It is the single strongest signal available for
    matching -- eTour has 864 English Javadoc blocks, and they paraphrase the
    requirements almost directly ("Implements the method for the elimination of a
    cultural system").

    Modifiers and annotations can sit between the comment and the declaration
    keyword, so we walk back over them.
    """
    sibling = node.prev_sibling
    while sibling is not None and sibling.type in ("modifiers", "annotation"):
        sibling = sibling.prev_sibling
    if sibling is not None and sibling.type in _COMMENT_TYPES:
        return _node_text(sibling, source)
    return ""


def parse_file(
    path: str | Path, repo_root: str | Path
) -> tuple[list[CodeNode], dict[str, str]]:
    """Parse one Java file into its constituent AST nodes.

    Args:
        path: Path to a ``.java`` file.
        repo_root: Used to compute the repo-relative `CodeNode.file_path`. For
            eTour this yields a bare filename (``CulturalHeritage.java``), which
            is exactly the form the gold links use.

    Returns:
        ``(nodes, docs)`` -- one `CodeNode` per declaration of interest in source
        order, plus a ``node_id -> raw doc comment`` map. Docs are returned
        alongside rather than on the dataclass because `CodeNode` is a frozen
        contract shared with the other half of the project; adding a field to it
        would break that agreement for a detail only the indexer needs.
    """
    path = Path(path)
    source = read_text(path).encode("utf-8")
    tree = _parser().parse(source)

    try:
        file_path = str(path.resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        file_path = path.name
    file_path = file_path.replace("\\", "/")

    nodes: list[CodeNode] = []
    docs: dict[str, str] = {}

    def visit(node: tree_sitter.Node, enclosing: str) -> None:
        kind = NODE_TYPES.get(node.type)
        if kind is not None:
            name = _child_text(node, "name", source) or "<anonymous>"
            # tree-sitter rows are 0-based; CodeNode is 1-based.
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            node_id = f"{file_path}::{name}#{start_line}"
            nodes.append(
                CodeNode(
                    node_id=node_id,
                    file_path=file_path,
                    kind=kind,
                    name=name,
                    signature=_signature(node, source)
                    if kind in ("method", "constructor")
                    else name,
                    start_line=start_line,
                    end_line=end_line,
                    text=_node_text(node, source),
                )
            )
            doc = _leading_doc(node, source)
            if doc:
                docs[node_id] = doc
            if node.type in _CONTAINERS:
                enclosing = name

        for child in node.children:
            visit(child, enclosing)

    visit(tree.root_node, "")
    return nodes, docs


def parse_repo(
    repo_root: str | Path, suffix: str = ".java"
) -> tuple[list[CodeNode], dict[str, str]]:
    """Parse an entire source tree. Returns ``(nodes, docs)``.

    tree-sitter never raises on malformed input -- it produces ERROR nodes and
    keeps going -- so a file that fails to parse yields few or no nodes rather
    than an exception. Callers should sanity-check the returned count.
    """
    from src.ingest.repo_walker import walk_source_files

    nodes: list[CodeNode] = []
    docs: dict[str, str] = {}
    for path in walk_source_files(repo_root, suffix=suffix):
        file_nodes, file_docs = parse_file(path, repo_root)
        nodes.extend(file_nodes)
        docs.update(file_docs)
    return nodes, docs


def enclosing_class_map(nodes: list[CodeNode]) -> dict[str, str]:
    """Map each node_id to the name of its enclosing class.

    Derived by containment on line ranges rather than during the parse walk,
    because the walk emits nodes in a flat list and this keeps `parse_file`'s
    return type simple. Cheap: one pass per file, and files are small.
    """
    by_file: dict[str, list[CodeNode]] = {}
    for node in nodes:
        by_file.setdefault(node.file_path, []).append(node)

    result: dict[str, str] = {}
    for file_nodes in by_file.values():
        containers = [n for n in file_nodes if n.kind in ("class", "interface")]
        for node in file_nodes:
            best = ""
            best_span = None
            for container in containers:
                if container.node_id == node.node_id:
                    continue
                if (
                    container.start_line <= node.start_line
                    and container.end_line >= node.end_line
                ):
                    span = container.end_line - container.start_line
                    # Innermost enclosing container wins (smallest span).
                    if best_span is None or span < best_span:
                        best, best_span = container.name, span
            result[node.node_id] = best
    return result
