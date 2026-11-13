"""Tiny Semantic Versioning helpers.

Precedence follows SemVer 2.0.0, item 11 (https://semver.org/#spec-item-11):

* major, minor and patch are compared numerically;
* a version with a pre-release has LOWER precedence than the same version without one;
* pre-release identifiers (split on ".") are compared one by one: identifiers made only of digits are
  compared numerically, others lexically in ASCII order, and a numeric identifier always has lower
  precedence than a non-numeric one; if all compared identifiers are equal, the longer list wins;
* build metadata (after "+") is ignored for precedence.
"""
import functools
import re

_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")


class Version:
    def __init__(self, major, minor, patch, prerelease="", build=""):
        self.major, self.minor, self.patch = major, minor, patch
        self.prerelease, self.build = prerelease, build

    def __str__(self):
        s = "%d.%d.%d" % (self.major, self.minor, self.patch)
        if self.prerelease:
            s += "-" + self.prerelease
        if self.build:
            s += "+" + self.build
        return s


def parse(text):
    """Parse "MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]"; raise ValueError on anything else."""
    m = _RE.match(text.strip())
    if not m:
        raise ValueError("not a semantic version: %r" % text)
    return Version(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "", m.group(5) or "")


def compare(a, b):
    """Return -1, 0 or 1 as version string a has lower, equal or higher precedence than b."""
    va, vb = parse(a), parse(b)
    ka = (va.major, va.minor, va.patch, va.prerelease)
    kb = (vb.major, vb.minor, vb.patch, vb.prerelease)
    return (ka > kb) - (ka < kb)


def sort_versions(versions):
    """Return the version strings sorted from lowest to highest precedence (stable for equal ones)."""
    return sorted(versions, key=functools.cmp_to_key(compare))
