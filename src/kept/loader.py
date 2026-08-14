"""Discover specifications on disk and drive the front end over them.

This is the only module in the front end that touches the filesystem. It also
owns the path boundary: every path leaving here is repository-relative with
forward slashes, so no absolute path can reach an artefact and a result produced
on one machine compares cleanly against one produced on another (REQ-6.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from kept.diagnostics import Diagnostic, sort_key
from kept.ears.parser import parse_criterion
from kept.ir import Criterion, Requirement, SpecDocument, build_requirement
from kept.markdown import extract

#: Where Kiro keeps specifications, relative to the repository root.
SPECS_DIRECTORY = PurePosixPath(".kiro/specs")

#: The file within each specification directory that holds acceptance criteria.
REQUIREMENTS_FILENAME = "requirements.md"


class SpecNotFoundError(FileNotFoundError):
    """Raised when a path that was expected to hold a specification does not."""


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Every specification found, with all diagnostics gathered along the way."""

    documents: tuple[SpecDocument, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        """Every criterion across every document, in deterministic order."""
        return tuple(
            criterion for document in self.documents for criterion in document.criteria
        )

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.is_error)


def relative_posix(path: Path, root: Path) -> str:
    """Express `path` relative to `root` using forward slashes.

    Falls back to the path's own name when it lies outside the root, which can
    happen when a caller points `kept` at a file elsewhere on disk. Emitting a
    bare name is preferable to leaking an absolute path into an artefact.
    """
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.name
    return relative.as_posix()


def discover_spec_files(root: Path) -> tuple[Path, ...]:
    """Find every `requirements.md` directly beneath a directory in `.kiro/specs`.

    Sorted by path so that discovery order is deterministic (REQ-4.1, REQ-6.2).
    Nested directories are not searched: a specification is one directory holding
    one requirements document, and recursing would pick up unrelated files that
    happen to share the name.
    """
    specs_root = root / SPECS_DIRECTORY
    if not specs_root.is_dir():
        return ()

    found = [
        candidate / REQUIREMENTS_FILENAME
        for candidate in sorted(specs_root.iterdir())
        if candidate.is_dir() and (candidate / REQUIREMENTS_FILENAME).is_file()
    ]
    return tuple(found)


def load_document(path: Path, *, root: Path, name: str | None = None) -> LoadResult:
    """Parse one requirements document into a `SpecDocument`.

    Args:
        path: The requirements document to read.
        root: The repository root, used to relativise paths.
        name: Override for the specification name. Defaults to the name of the
            containing directory (REQ-4.2).
    """
    if not path.is_file():
        msg = f"no requirements document at {path}"
        raise SpecNotFoundError(msg)

    source = relative_posix(path, root)
    text = path.read_text(encoding="utf-8")
    spec_name = name if name is not None else path.parent.name

    extraction = extract(text, source=source)
    diagnostics: list[Diagnostic] = list(extraction.diagnostics)
    requirements: list[Requirement] = []

    for raw_requirement in extraction.requirements:
        criteria: list[Criterion] = []
        for raw_criterion in raw_requirement.criteria:
            result = parse_criterion(
                raw_criterion.text,
                requirement_number=raw_criterion.requirement_number,
                position=raw_criterion.position,
                span=raw_criterion.span,
            )
            diagnostics.extend(result.diagnostics)
            if result.criterion is not None:
                criteria.append(result.criterion)

        requirements.append(
            build_requirement(
                number=raw_requirement.number,
                criteria=tuple(criteria),
                title=raw_requirement.title,
                user_story=raw_requirement.user_story,
            )
        )

    # Requirements are ordered by number so that output does not depend on the
    # order headings happened to appear in (REQ-6.2).
    requirements.sort(key=lambda requirement: requirement.number)

    document = SpecDocument(
        name=spec_name,
        path=source,
        requirements=tuple(requirements),
    )
    return LoadResult(
        documents=(document,),
        diagnostics=tuple(sorted(diagnostics, key=sort_key)),
    )


def load_all(root: Path) -> LoadResult:
    """Parse every specification found beneath `.kiro/specs`."""
    documents: list[SpecDocument] = []
    diagnostics: list[Diagnostic] = []

    for path in discover_spec_files(root):
        result = load_document(path, root=root)
        documents.extend(result.documents)
        diagnostics.extend(result.diagnostics)

    documents.sort(key=lambda document: document.path)
    return LoadResult(
        documents=tuple(documents),
        diagnostics=tuple(sorted(diagnostics, key=sort_key)),
    )
