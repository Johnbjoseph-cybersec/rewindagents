"""Order build targets so that every target comes after the targets it depends on."""
import heapq


class CycleError(ValueError):
    def __init__(self, cycle):
        super().__init__("dependency cycle: " + " -> ".join(cycle))
        self.cycle = cycle


def _graph(deps):
    g = {}
    for n, ds in deps.items():
        g.setdefault(n, set()).update(ds)
        for d in ds:
            g.setdefault(d, set())
    return g


def _find_cycle(g, nodes):
    color = {}
    for start in sorted(nodes):
        if start in color:
            continue
        stack = [(start, iter(sorted(g[start])))]
        path = [start]
        color[start] = 1
        while stack:
            n, it = stack[-1]
            for d in it:
                if color.get(d) == 1:
                    return path[path.index(d):] + [d]
                if d not in color:
                    color[d] = 1
                    path.append(d)
                    stack.append((d, iter(sorted(g[d]))))
                    break
            else:
                color[n] = 2
                path.pop()
                stack.pop()
    raise AssertionError("no cycle")


def toposort(deps):
    g = _graph(deps)
    need = {n: len(ds) for n, ds in g.items()}
    users = {n: [] for n in g}
    for n, ds in g.items():
        for d in ds:
            users[d].append(n)
    ready = [n for n, k in need.items() if k == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for u in users[n]:
            need[u] -= 1
            if need[u] == 0:
                heapq.heappush(ready, u)
    if len(order) != len(g):
        raise CycleError(_find_cycle(g, [n for n in g if n not in set(order)]))
    return order


def levels(deps):
    g = _graph(deps)
    lvl = {}
    for n in toposort(deps):
        lvl[n] = 1 + max((lvl[d] for d in g[n]), default=-1)
    out = [[] for _ in range(max(lvl.values()) + 1)] if lvl else []
    for n in sorted(lvl):
        out[lvl[n]].append(n)
    return out
