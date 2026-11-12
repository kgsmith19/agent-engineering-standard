#!/usr/bin/env python3
"""conventions — name and describe work the standard way, automatically.

Branch names, PR bodies and Issue bodies follow simple conventions. This tool
makes them for you, and the PR Gate uses the same rules, so a PR fails only when
something cannot be worked out (#333).

The rules, in one place:

* A branch is ``issue/<n>-<slug>``. This is a recommendation, not a gate: agent
  harnesses often choose their own branch names. When it is followed, the
  branch name supplies the Issue number.
* A PR closes its Issue. The Issue comes from the body's ``Closes #N`` line,
  else from an ``issue/<n>-`` branch, else from a title ending in ``(#N)``.
  When it is derived, the Merge Policy workflow writes the ``Closes #N`` line
  into the body, so GitHub closes the Issue on merge.
* PR and Issue bodies use the repository's templates. ``pr-body`` and
  ``issue-body`` print a filled skeleton; ``repair-pr`` adds a missing
  ``Closes`` line and any missing template sections without touching what is
  already there.

Subcommands
===========

``branch --issue N --title T``            print ``issue/<n>-<slug>``
``pr-body --issue N [--summary S] [--template PATH]``
                                         print a PR body from the template
``issue-body [--outcome O] [--template PATH]``
                                         print an Issue body from the template
``check-pr --event PATH`` | ``--body-file F --head-ref R [--title T]``
                                         exit 1 only when no Issue can be found
``repair-pr`` (same inputs as check-pr)   print the repaired PR body

Standard library only (Python 3.9+). Exit codes: 0 ok, 1 refused, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PR_TEMPLATE = os.path.join(ROOT, ".github", "PULL_REQUEST_TEMPLATE.md")
ISSUE_TEMPLATE = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "work-item.md")

SLUG_LIMIT = 48
_CLOSES = re.compile(r"(?im)^\s*(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#([1-9][0-9]*)\b")
_BRANCH = re.compile(r"^issue/([1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
_TITLE_REF = re.compile(r"\(#([1-9][0-9]*)\)\s*$")
_HEADING = re.compile(r"^## .+$", re.M)
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def slugify(title):
    """Lower-case words joined by single hyphens, at most ``SLUG_LIMIT`` chars."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    slug = ""
    for word in words:
        candidate = word if not slug else slug + "-" + word
        if len(candidate) > SLUG_LIMIT:
            break
        slug = candidate
    return slug or "work"


def branch_name(issue, title):
    return "issue/%d-%s" % (int(issue), slugify(title))


def branch_follows_convention(head_ref):
    return bool(_BRANCH.match(head_ref or ""))


def closing_issue(body):
    """The first Issue the body closes with a ``Closes #N`` line, or None."""
    match = _CLOSES.search(body or "")
    return int(match.group(1)) if match else None


def derive_issue(body, head_ref="", title=""):
    """``(number, source)`` for the Issue this PR closes, or ``(None, None)``.

    Sources, in order: the body's ``Closes`` line, an ``issue/<n>-`` branch,
    a title ending in ``(#N)``.
    """
    number = closing_issue(body)
    if number:
        return number, "body"
    match = _BRANCH.match(head_ref or "")
    if match:
        return int(match.group(1)), "branch"
    match = _TITLE_REF.search(title or "")
    if match:
        return int(match.group(1)), "title"
    return None, None


def template_headings(template_text):
    return _HEADING.findall(_FRONT_MATTER.sub("", template_text or ""))


def missing_headings(body, template_text):
    present = set(line.strip() for line in (body or "").splitlines())
    return [h for h in template_headings(template_text) if h not in present]


def repair_pr_body(body, template_text, issue):
    """Add a ``Closes #issue`` line when none exists, and any missing template
    sections at the end. Existing text is never changed or reordered."""
    body = (body or "").rstrip()
    if issue and not closing_issue(body):
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if line.strip().lower().startswith("## related"):
                lines.insert(index + 1, "\nCloses #%d" % issue)
                break
        else:
            lines.append("\nCloses #%d" % issue)
        body = "\n".join(lines).strip()
    for heading in missing_headings(body, template_text):
        body += "\n\n%s\n\n_Not filled in._" % heading
    return body + "\n"


def fill_template(template_text, replacements):
    """The template without front matter, with ``Closes #`` and similar
    placeholders filled from ``replacements`` (exact line -> new line)."""
    text = _FRONT_MATTER.sub("", template_text or "").strip("\n")
    lines = [replacements.get(line, line) for line in text.splitlines()]
    return "\n".join(lines) + "\n"


def pr_body(template_text, issue, summary=""):
    replacements = {"Closes #": "Closes #%d" % int(issue)}
    if summary:
        replacements["State the behavioral outcome and smallest coherent implementation."] = summary
    return fill_template(template_text, replacements)


def issue_body(template_text, outcome=""):
    replacements = {}
    if outcome:
        replacements["State one observable result."] = outcome
    return fill_template(template_text, replacements)


def check_pr(body, head_ref="", title=""):
    """``(ok, messages)``: ok unless no Issue can be found. The branch name is
    advice only."""
    messages = []
    number, source = derive_issue(body, head_ref, title)
    if number is None:
        return False, ["PR closes no Issue: add a 'Closes #<issue>' line (or "
                       "name the branch issue/<n>-<slug>). "
                       "`python3 tools/conventions.py pr-body --issue N` prints a "
                       "complete body."]
    if source == "body":
        messages.append("ok: closes #%d" % number)
    else:
        messages.append("ok: closes #%d (from the %s; the Merge Policy workflow "
                        "adds the 'Closes #%d' line)" % (number, source, number))
    if not branch_follows_convention(head_ref):
        messages.append("note: branch %r is not issue/<n>-<slug>; that is fine. "
                        "The convention would be %s" % (head_ref, branch_name(number, title or "work")))
    return True, messages


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _pr_inputs(args):
    if args.event:
        try:
            pr = json.loads(_read(args.event))["pull_request"]
            return pr.get("body") or "", pr["head"]["ref"], pr.get("title") or ""
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("not a readable pull_request event: %s" % exc)
    return _read(args.body_file) if args.body_file else "", args.head_ref or "", args.title or ""


def build_parser():
    parser = argparse.ArgumentParser(prog="conventions", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    br = sub.add_parser("branch", help="print issue/<n>-<slug>")
    br.add_argument("--issue", type=int, required=True)
    br.add_argument("--title", required=True)
    pb = sub.add_parser("pr-body", help="print a PR body from the template")
    pb.add_argument("--issue", type=int, required=True)
    pb.add_argument("--summary", default="")
    pb.add_argument("--template", default=PR_TEMPLATE)
    ib = sub.add_parser("issue-body", help="print an Issue body from the template")
    ib.add_argument("--outcome", default="")
    ib.add_argument("--template", default=ISSUE_TEMPLATE)
    for name in ("check-pr", "repair-pr"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--event", help="pull_request event payload ($GITHUB_EVENT_PATH)")
        cmd.add_argument("--body-file")
        cmd.add_argument("--head-ref", default="")
        cmd.add_argument("--title", default="")
        cmd.add_argument("--template", default=PR_TEMPLATE)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "branch":
            print(branch_name(args.issue, args.title))
        elif args.command == "pr-body":
            sys.stdout.write(pr_body(_read(args.template), args.issue, args.summary))
        elif args.command == "issue-body":
            sys.stdout.write(issue_body(_read(args.template), args.outcome))
        else:
            body, head_ref, title = _pr_inputs(args)
            if args.command == "check-pr":
                ok, messages = check_pr(body, head_ref, title)
                for message in messages:
                    print(message, file=sys.stdout if ok else sys.stderr)
                return 0 if ok else 1
            number, _ = derive_issue(body, head_ref, title)
            template = _read(args.template) if os.path.exists(args.template) else ""
            sys.stdout.write(repair_pr_body(body, template, number))
    except (OSError, ValueError) as exc:
        print("conventions: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
