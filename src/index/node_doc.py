"""Turn a `CodeNode` into the text document that actually gets embedded.

This is the highest-leverage module in the project. Get it right and the rest
works; get it wrong and no amount of model tuning rescues it.

The key decision: we do NOT embed raw source code. Raw Java is mostly syntax --
braces, modifiers, type names, boilerplate -- and a sentence embedding model
trained on English prose has no idea what to do with it. The signal that
actually connects "the system shall notify the user of nearby attractions" to
`sendAlert()` is *the words inside the identifiers*, and those words are welded
together in camelCase where no tokenizer will find them.

So we synthesise a pseudo-English document per node from:

    1. The node name, split on camelCase/snake_case ("dispatchEvent" ->
       "dispatch event")
    2. The signature (parameter names carry real domain vocabulary)
    3. Attached comments / Javadoc (already English -- the strongest signal
       available, when present)
    4. Identifiers from the body, also split
    5. The enclosing class name, split

Identifier splitting is the single highest-impact trick here. It is what turns
an embedding model that has never seen Java into a usable code retriever, and it
is why this project can use a general-purpose sentence model rather than
needing a code-specific one.
"""

from __future__ import annotations

from src.contracts import CodeNode


def split_identifier(identifier: str) -> list[str]:
    """Split a programming identifier into its English words, lowercased.

    Examples:
        ``dispatchEvent``      -> ``["dispatch", "event"]``
        ``send_alert``         -> ``["send", "alert"]``
        ``HTTPServerHandler``  -> ``["http", "server", "handler"]``
        ``getURLFor2ndUser``   -> ``["get", "url", "for", "2nd", "user"]``

    The acronym case (``HTTPServer`` -> ``http server``, not ``h t t p server``)
    is the one that catches people out: a naive split on every uppercase letter
    shreds acronyms into single letters and destroys the signal. Handle the
    upper-to-upper-followed-by-lower boundary explicitly.

    Write the tests for this function first. It is twenty lines of code that
    everything else depends on, and it is trivially unit-testable in isolation.
    """
    raise NotImplementedError


def build_node_document(node: CodeNode, enclosing_class: str = "") -> str:
    """Assemble the embeddable pseudo-English document for one node.

    Args:
        node: The parsed AST node.
        enclosing_class: Name of the containing class, for extra context.

    Returns:
        A space-joined bag of words. Not grammatical English, and that is fine --
        sentence embedders degrade gracefully on keyword soup, and we are after
        topical similarity, not syntax.

    Implementation notes:
        - Drop Java keywords and single-character identifiers (``i``, ``x``).
          They are pure noise and they dilute the vector.
        - Do NOT stem here. The baseline (TfidfVectorizer) applies its own
          preprocessing; if the two pipelines normalise differently, the B-vs-E
          comparison stops being apples-to-apples and the ablation loses its
          meaning.
        - Deduplicate body identifiers but keep name/signature tokens even if
          repeated -- repetition in the name is genuine emphasis.
        - Cap the document length. A 300-line method otherwise produces a vector
          dominated by whatever it happens to loop over. ~200 tokens is plenty,
          and MiniLM truncates at 256 anyway.
    """
    raise NotImplementedError
