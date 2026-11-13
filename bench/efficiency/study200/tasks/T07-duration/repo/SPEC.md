# durations: format_duration (planned)

`format_duration(seconds)` writes a number of seconds back in the form `parse_duration` reads, using the
largest units first and leaving out zero parts: `5400` -> `"1h30m"`, `90061` -> `"1d1h1m1s"`, `0.25` ->
`"250ms"`, `61.5` -> `"1m1s500ms"`, `0` -> `"0s"`, `-90` -> `"-1m30s"`. The input is first rounded to whole
milliseconds (`1.0004` -> `"1s"`, `1.0006` -> `"1s1ms"`). `parse_duration(format_duration(x))` equals `x`
rounded to whole milliseconds.
