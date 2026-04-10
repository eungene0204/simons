# Skill: spec-writer

## Purpose

Convert a short or loosely phrased user request into an executable Simons task specification.

## When to use

Use this skill when the incoming request is missing one or more of the following:
- a clear boundary
- explicit file scope
- constraints
- validation commands
- delivery format

Do not use this skill when the request is already fully structured.

## Output format

Return the final result in exactly this structure:

Task:
<one-sentence task>

Boundary:
<one boundary only>

Files allowed:
- <path>
- <path>

Do not:
- <constraint>
- <constraint>

Requirements:
- <requirement>
- <requirement>

Run:
- <command>

Deliver:
- Small diff
- Summary of changed files
- Test results summary

## Boundary selection rules

Choose exactly one boundary.

Available boundaries:
- Strategy UI
- Backtest Transform
- Backtest Core
- AI / XAI Layer
- Dashboard / Read-only UI

If the request spans multiple boundaries, narrow the task to the smallest safe boundary.

## Forbidden paths

Never include these in Files allowed unless the user explicitly asks:
- prisma/**
- backend/engine/providers/**
- app/api/login/**
- app/api/register/**
- app/api/user/**
- scripts/**

## Quality rules

- Prefer the smallest actionable scope
- Preserve API contracts
- Require a validation command
- Prefer reviewable diffs
- If the request is too broad, rewrite it into a smaller first step
