Issue #41: pre-releases sort after the release

`compare("1.0.0-alpha", "1.0.0")` returns 1, so our release tool thinks the alpha is newer than the release.
And `sort_versions(["1.0.0-rc.10", "1.0.0", "1.0.0-rc.2"])` gives `["1.0.0", "1.0.0-rc.10", "1.0.0-rc.2"]`.
The module docstring says precedence follows SemVer 2.0.0; it should.
