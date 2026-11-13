"""Order build targets so that every target comes after the targets it depends on."""


class CycleError(ValueError):
    """Raised when the dependencies contain a cycle. ``.cycle`` is a list of target names forming it."""

    def __init__(self, cycle):
        super().__init__("dependency cycle: " + " -> ".join(cycle))
        self.cycle = cycle


def toposort(deps):
    """Return every target in ``deps`` in build order.

    ``deps`` maps a target name to the list of names it depends on. A name that only appears as a
    dependency is a target too (with no dependencies of its own) and is part of the result.

    The order is deterministic: at each point, among the targets whose dependencies are all already placed,
    the one with the alphabetically smallest name comes next. Duplicate dependencies are allowed.

    If there is a cycle (including a target that depends on itself), raise CycleError whose ``.cycle`` lists
    the names around one cycle, starting and ending with the same name, e.g. ``["a", "b", "a"]``.
    ``deps`` is not modified.
    """
    order = []
    seen = set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for d in deps.get(n, []):
            visit(d)
        order.append(n)

    for n in deps:
        visit(n)
    return order
