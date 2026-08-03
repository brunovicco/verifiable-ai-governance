# ADR 0001 - Monorepo and initial stack

- Status: accepted
- Date: 2026-07-31

## Context

The MVP needs to evolve contracts, rules, API, portal, templates, and documentation in
a coordinated way, with simple local execution.

## Decision

Use a monorepo with Next.js for the portal, FastAPI for the backend, independent Python
packages for schemas and policies, PostgreSQL as the transactional database, `uv` for
the Python workspace, and npm workspaces for the frontend.

## Consequences

- contract changes can be tested in the same pull request;
- CI and setup stay centralized;
- independent releases are not yet a priority;
- external integrations sit behind adapters to avoid coupling to the monorepo.
