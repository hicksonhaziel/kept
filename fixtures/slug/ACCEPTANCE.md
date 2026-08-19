# Acceptance Criteria

A plain Python project. No Kiro, no `.kiro` directory, requirements written by hand
in whatever file the team already keeps them in.

### Requirement 1: Slug generation

#### Acceptance Criteria

1. WHEN a title is given THEN the system SHALL return it in lower case.
2. WHEN a title contains spaces THEN the system SHALL replace each run of spaces with a single hyphen.
3. WHEN a title contains punctuation THEN the system SHALL remove it.
4. THE system SHALL NOT return a slug with a leading or trailing hyphen.
5. WHEN a title is empty THEN the system SHALL return an empty string.
