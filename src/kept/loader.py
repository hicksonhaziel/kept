"""Spec discovery and parse orchestration. The only front-end module doing I/O.

Owns the path boundary: every path leaving here is repository-relative with
forward slashes, so no absolute path reaches an artefact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from kept.diagnostics import Diagnostic, sort_key
from kept.ears.parser import parse_criterion
from kept.ir import Criterion, Requirement, SpecDocument, build_requirement
from kept.markdown import extract

SPECS_DIRECTORY = PurePosixPath(".kiro/specs")
REQUIREMENTS_FILENAME = "requirements.md"


class SpecNotFoundError(FileNotFoundError):
    """Raised when a path expected to hold a specification does not."""


@dataclass(frozen=True, slots=True)
class LoadResult:
    documents: tuple[SpecDocument, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        return tuple(criterion for document in self.documents for criterion in document.criteria)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.is_error)


def relative_posix(path: Path, root: Path) -> str:
    """Express `path` relative to `root` with forward slashes.

    Falls back to the bare filename when the path lies outside the root, which is
    preferable to leaking an absolute path into an artefact.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def discover_spec_files(root: Path) -> tuple[Path, ...]:
    """Find every `requirements.md` directly beneath a directory in `.kiro/specs`.

    Not recursive: a specification is one directory holding one requirements
    document, and recursing would pick up unrelated files of the same name.
    """
    specs_root = root / SPECS_DIRECTORY
    if not specs_root.is_dir():
        return ()

    return tuple(
        candidate / REQUIREMENTS_FILENAME
        for candidate in sorted(specs_root.iterdir())
        if candidate.is_dir() and (candidate / REQUIREMENTS_FILENAME).is_file()
    )


def load_document(path: Path, *, root: Path, name: str | None = None) -> LoadResult:
    """Parse one requirements document. `name` defaults to the directory name."""
    if not path.is_file():
        msg = f"no requirements document at {path}"
        raise SpecNotFoundError(msg)

    source = relative_posix(path, root)
    text = path.read_text(encoding="utf-8")
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

    requirements.sort(key=lambda requirement: requirement.number)
    document = SpecDocument(
        name=name if name is not None else path.parent.name,
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
