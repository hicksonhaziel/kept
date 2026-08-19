"""Spec discovery and parse orchestration. The only front-end module doing I/O.

Owns the path boundary: every path leaving here is repository-relative with
forward slashes, so no absolute path reaches an artefact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from kept.diagnostics import Diagnostic, Severity, sort_key
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
    return load(root)


def load(root: Path, *, specs: Sequence[Path] | None = None) -> LoadResult:
    """Parse the given specifications, or discover them under `.kiro/specs`.

    Args:
        root: The project root, used to relativise paths.
        specs: Explicit requirements documents. Any markdown file with numbered
            criteria under an "Acceptance Criteria" heading works; it need not
            live in `.kiro/specs`. When omitted, kept discovers Kiro's specs.
    """
    paths = tuple(_resolve(path, root) for path in specs) if specs else discover_spec_files(root)

    documents: list[SpecDocument] = []
    diagnostics: list[Diagnostic] = []

    for path in paths:
        result = load_document(path, root=root)
        documents.extend(result.documents)
        diagnostics.extend(result.diagnostics)

    documents.sort(key=lambda document: document.path)
    diagnostics.extend(_duplicate_identifiers(documents))

    return LoadResult(
        documents=tuple(documents),
        diagnostics=tuple(sorted(diagnostics, key=sort_key)),
    )


def _resolve(path: Path, root: Path) -> Path:
    """Interpret a spec path against the project root, then the caller's directory.

    Root-relative is the useful reading, since `--root` names the project being
    verified. Falling back to the working directory keeps a path that the user can
    see on their own shell from being rejected.
    """
    if path.is_absolute() or path.is_file():
        return path
    candidate = root / path
    return candidate if candidate.is_file() else path


def _duplicate_identifiers(documents: Sequence[SpecDocument]) -> list[Diagnostic]:
    """Report identifiers claimed by more than one document.

    Identifiers are numbered per document, so two specifications that both open
    with "Requirement 1" would each produce REQ-1.1. A binding naming that
    identifier would then be ambiguous, and kept would silently attribute evidence
    to the wrong promise. Reported as an error rather than resolved by guessing
    which document was meant.
    """
    owners: dict[str, list[SpecDocument]] = {}
    for document in documents:
        for criterion in document.criteria:
            owners.setdefault(criterion.id, []).append(document)

    diagnostics: list[Diagnostic] = []
    for identifier, claimants in sorted(owners.items()):
        if len(claimants) < 2:
            continue
        names = ", ".join(sorted(document.path for document in claimants))
        first = claimants[0].criterion_by_id(identifier)
        diagnostics.append(
            Diagnostic(
                code="E003",
                severity=Severity.ERROR,
                message=(
                    f"{identifier} is defined in more than one specification: {names}. "
                    f"Renumber the requirement headings so each identifier is claimed "
                    f"once, or verify one specification at a time with --spec."
                ),
                span=first.span if first is not None else None,
            )
        )
    return diagnostics
