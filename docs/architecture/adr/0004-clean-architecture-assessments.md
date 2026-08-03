# ADR 0004 - Clean Architecture for structured assessments

- Status: accepted
- Date: 2026-07-31

## Context

AIA, RIPD, and the international-processing analysis share lifecycle, authorization,
versioning, and audit, but have different answers and applicability rules. Coupling
these rules directly to FastAPI, Pydantic, or SQLAlchemy would make testing, schema
evolution, and future queue-based or GRC-integration inputs harder.

## Decision

- represent each definition with immutable, versioned types in the pure domain;
- concentrate applicability, risk calculation, and transitions in I/O-free functions;
- implement create/update, list, and submit as cohesive use cases;
- declare store, audit, and transaction ports in the consuming module;
- implement the ports with SQLAlchemy adapters wired at the composition root;
- explicitly map Pydantic DTOs, domain values, and ORM entities;
- translate typed errors to HTTP only at the edge;
- require an expected version on mutations and type uniqueness per initiative in the
  database;
- keep audit events free of response content;
- document modules, classes, and public operations with docstrings.

This design applies single responsibility and dependency inversion. New adapters can
be added without changing the use cases; new definitions require an explicit contract
and version, avoiding generic schemas that would hide material changes.

## Twelve-Factor

The module introduces no process state or hardcoded configuration. Database session,
identity, clock, and ID generator enter through existing boundaries or by injection.
The API can scale horizontally, PostgreSQL remains an attached resource configured
externally, and audit continues emitting structured events.

## Consequences

- rules can be tested without an HTTP server or database;
- adapters and mappings add code, but make boundaries verifiable;
- a submitted assessment stays read-only until the review workflow is implemented;
- concurrent creation is protected by the `uq_assessment_initiative_type` constraint;
- adding a definition requires deliberately updating the typed union, schemas,
  adapter, and portal, including a new contract version.
