# deps: levels (planned)

`levels(deps)` groups the targets into build waves that can run in parallel: wave 0 holds every target with
no dependencies, wave k holds every target whose deepest dependency is in wave k-1. Returns a list of lists,
each wave sorted alphabetically. Same input rules as `toposort` (names that only appear as dependencies are
targets; a cycle raises CycleError). An empty mapping gives `[]`.

Example: `levels({"app": ["lib", "cfg"], "lib": ["cfg"]})` -> `[["cfg"], ["lib"], ["app"]]`.
