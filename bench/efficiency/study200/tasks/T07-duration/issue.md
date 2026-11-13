Issue #31: compound durations are cut short

`parse_duration("1h30m")` returns 3600.0 (the "30m" is ignored) and `parse_duration("1h30")` returns 3600.0
instead of raising. The docstring of `parse_duration` describes the accepted format; please implement it.
