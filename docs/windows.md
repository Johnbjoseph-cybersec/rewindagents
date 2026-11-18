# Windows CI: every failure, one by one

Source of the failure list: the windows-latest job of `tests` run 44262918115 on `main` at b63f2a2
(`gh run view --job 134660374813 --log -R Johnbjoseph-cybersec/rewindagents`): `Ran 849 tests in 164.542s`,
`FAILED (failures=44, errors=43, skipped=32)`, 87 failure identities (a `subTest` failure and its parent count
separately, as unittest prints them). That run already contained every fix of the two earlier squads (F1-F5,
SW1-SW10, summarised at the end); this document supersedes their 101-row map, several of whose "fixed" rows
were still red in this run.

Branch `win/green` addresses all 87: 84 fixed, 3 skipped with a stated reason (rows below; 1 of the 84 passes
by a Windows-specific expectation, also stated). **None of this has run on Windows.** `continue-on-error` stays on
the Windows matrix row and README.md keeps "Windows is not supported" until a green windows-latest run is seen.

## How each fix was checked here (macOS)

- **Simulated:** the Windows behaviour was reproduced on macOS, the old code failed the way CI did, the new code
  passes.
  - Text-mode writes: a throwaway `sitecustomize.py` on `PYTHONPATH` wraps `io.open`/`open` so a text-mode write
    with `newline=None` writes `\r\n`, as CPython does on Windows (subprocesses load it too). With the old
    `test_rewind.Agent` it reproduces 14 of the CI failures; with the fix the whole suite passes under it except
    `test_vsl_audio.test_regenerating_gives_the_pinned_bytes`, which is skipped on windows-latest (no audio
    toolchain) and is a brand build script, not a CI identity.
  - `git apply` of a CRLF patch on an LF file: fails with the CI's own message (`patch failed: app.py:1`).
  - `shutil.which` with `sys.platform == "win32"` semantics (CPython's own branch, PATHEXT `.COM;.EXE;.BAT;.CMD`):
    bare stand-in names are not found (the CI failure), `.cmd` names are.
  - `bundle.root_spellings` with `PureWindowsPath` and a realpath stand-in mapping `RUNNER~1` to `runneradmin`;
    `export.scrub` on JSON text. Committed as tests in `tests/test_windows_paths.py`; they fail on the old code.
  - `agents.uninstall` of a Windows-path Copilot hook under `bash`: OS-independent, committed in
    `tests/test_windows_hook.py`, fails on the old code.
  - msvcrt shared-lock refusal: against `test_filelock.FakeMsvcrt`.
  - rmtree of a read-only file with `unlink` made to refuse read-only files as Windows does.
- **Reasoning only:** W1 (Windows refuses to remove a directory that a live process has as its cwd), W7 (Git
  Bash location on the runner, and the Windows command form running under it), W9, and the cause named for W10
  (that git's read-only object files are what stayed behind is inferred; the CI log does not show it). Also the
  short-name expansion W3 relies on: that `os.path.realpath` on Windows turns `C:\Users\RUNNER~1` into the long
  name. The CI log is consistent with it (the bundle's `root_spellings` held only the long name while the
  records held the short one) but it was not run.

## Fixes

| # | Commit | Where | Root cause | Fix |
|---|---|---|---|---|
| W1 | 10f0613 | `tests/test_mcp.py` `ServerCase` | Cleanups run last-in first-out; the temp dir was removed before the `rewindagents mcp` process in it was killed. Windows refuses (WinError 32). | Register the directory cleanup first. |
| W2 | bdd7cb5 | `tests/test_rewind.py` `Agent.write` | The shared fixture simulated a Write tool with `write_text(text)`: CRLF and the locale codec on Windows. SW1 had added `newline=""` to 74 direct calls but not to this helper, which most modules drive the hook through. | `encoding="utf-8", newline=""`: the content on disk byte for byte, as a Write tool does. |
| W3 | 8e58b19 | `src/rewindagents/bundle.py` `root_spellings`, `src/rewindagents/export.py` `scrub`, `export` | (a) The tail match `s.endswith("/" + tail)` never matched a backslash path, so only the resolved root was a spelling and import left the short-name paths (`RUNNER~1`) pointing at the source. (b) `scrub` did not know a Windows root as JSON prints it (`\\`). (c) The page was written in text mode: CRLF on disk, LF byte count reported. | (a) Tail compared with either separator, case-insensitively for a Windows spelling; POSIX unchanged. (b) Also remove the JSON-escaped form. (c) `newline=""`. |
| W4 | 8cdb352 | `src/rewindagents/agents.py` `uninstall`; `tests/test_stale.py` | `uninstall` looked only under the key `install` would pick (`powershell` for a Windows command), so a stale Windows hook under Copilot's `bash` stayed. SW8c's `sys.executable = /usr/bin/python3` patch made the replacement itself stale on Windows (claude subtest). The status regex embedded an unescaped Windows path (`\U`). | Match every key `_command_keys` names; drop the patch; `re.escape`. |
| W5 | 37df761 | `tests/test_init.py`, `tests/test_usable.py` | Windows `shutil.which` only matches a name with a PATHEXT extension; the stand-ins were extension-less. `init.detect` is right (npm installs `claude.cmd`). | Stand-in is `<name>.cmd` on Windows; the CLI test also sets `USERPROFILE` (Windows `Path.home()` ignores `HOME`). |
| W6 | 8471c35 | `tests/test_diff.py`, `tests/test_project_root.py`, `tests/test_runs.py` | `subprocess.run(input=patch, text=True)` writes `\r\n` on Windows; Git for Windows also ships `core.autocrlf=true`, under which `git apply` writes CRLF files. | Patch passed as UTF-8 bytes; `git -c core.autocrlf=false apply`. |
| W7 | 6b82ee6 | `tests/test_agents_more.py` | `"bash"` resolves to `System32\bash.exe` (WSL launcher) before PATH; no distro on the runner, so it printed a UTF-16 notice and exited 1. | `bash()` helper: Git Bash next to `git.exe` or on PATH outside System32; skips the test, with a reason, if there is none. POSIX: `"bash"`. |
| W8 | b4586b0 | `tests/test_filelock.py` | `TestUnixPath` runs on the real backend; msvcrt has no shared lock (documented in `filelock.py`). | **Windows-specific expectation**: on Windows a second shared holder is refused while the first holds, granted after release. POSIX assertions unchanged. |
| W9 | 0503da9 | `tests/test_site.py` `repo_text_files` | `os.path.relpath` is `\`-joined on Windows; `HOST_ALLOWED` names `brand/site/config.json`. | `'/'`-joined relative path. |
| W10 | 11d0904 | `bench/takeback/takeback.py` `run_one` | `rmtree(ignore_errors=True)` cannot delete read-only files on Windows (git's objects), so a `takeback-*` dir stayed. | `remove_tree`: clear the read-only flag and retry. |

## Skips added (each with its reason string in the code)

| # | Commit | Test | Reason |
|---|---|---|---|
| S1 | 24ef82c | `test_bashscan.TestBashLimits.test_a_deleted_script_comes_back_executable`, `test_bashscan.TestBashLimits.test_a_file_the_write_tool_replaced_gets_its_mode_back` | No POSIX mode bits on NTFS: `os.chmod` only toggles read-only, so a chmod-only change or 0o700/0o750 cannot round-trip (CI read back 0o666). |
| S2 | 24ef82c | `test_runs_demo.TestRunsDemo` (whole class) | `ux-review/try-runs.sh` is a POSIX sh demo (mktemp, /tmp paths, python3) whose POSIX output the site quotes; on windows-latest the runner's sh exited 2 on it. |

| S3 | 6b82ee6 | `test_agents_more`: the four `test_the_installed_command_runs_and_records` and `TestCopilot.test_the_command_cannot_fail_closed` | Conditional, Windows only: skipped only when no Git Bash is found (only the WSL launcher, or no bash). Git for Windows is on windows-latest, so CI is expected to run them. |

Skips that were already there and stay: `test_revert...test_a_file_the_step_deleted_comes_back_with_its_mode`
(SW5, same NTFS reason), and the environment skips the CI log lists (no `REWINDAGENTS_BIN`/`REWINDAGENTS_DIST`,
no ffmpeg, no fontTools, POSIX-shell probes, no claude CLI).

## Every failure in run 44262918115

| Test | CI | Status | Note |
|---|---|---|---|
| `test_agents_more.TestCopilot.test_the_command_cannot_fail_closed` | FAIL | fixed (W7, 6b82ee6) | Git Bash instead of System32\bash.exe (WSL launcher) |
| `test_agents_more.TestCopilot.test_the_installed_command_runs_and_records` | FAIL | fixed (W7, 6b82ee6) | Git Bash instead of System32\bash.exe (WSL launcher) |
| `test_agents_more.TestDroid.test_the_installed_command_runs_and_records` | FAIL | fixed (W7, 6b82ee6) | Git Bash instead of System32\bash.exe (WSL launcher) |
| `test_agents_more.TestGemini.test_the_installed_command_runs_and_records` | FAIL | fixed (W7, 6b82ee6) | Git Bash instead of System32\bash.exe (WSL launcher) |
| `test_agents_more.TestQwen.test_the_installed_command_runs_and_records` | FAIL | fixed (W7, 6b82ee6) | Git Bash instead of System32\bash.exe (WSL launcher) |
| `test_bashscan.TestBashLimits.test_a_deleted_script_comes_back_executable` | FAIL | skipped (S1, 24ef82c) | NTFS has no POSIX mode bits |
| `test_bashscan.TestBashLimits.test_a_file_the_write_tool_replaced_gets_its_mode_back` | FAIL | skipped (S1, 24ef82c) | NTFS has no POSIX mode bits |
| `test_bundle.TestCli.test_bundle_then_import_through_the_cli` | FAIL | fixed (W3, 8e58b19) | root_spellings finds the 8.3 short spelling the hook saw |
| `test_bundle.TestRoundTrip.test_a_session_moved_to_another_project_replays_and_rewinds_there` | FAIL | fixed (W3, 8e58b19) | root_spellings finds the 8.3 short spelling the hook saw |
| `test_bundle.TestRoundTrip.test_root_spellings_cover_the_unresolved_temp_path` | FAIL | fixed (W3, 8e58b19) | root_spellings finds the 8.3 short spelling the hook saw |
| `test_bundle.TestRoundTrip.test_times_are_kept_so_sessions_shows_the_original_span` | FAIL | fixed (W3, 8e58b19) | root_spellings finds the 8.3 short spelling the hook saw |
| `test_diff.TestDiff.test_a_file_rewind_would_create_shows_as_new` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_diff.TestDiff.test_diff_goes_from_now_to_the_rewind_state` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_diff.TestDiff.test_git_apply_of_the_diff_does_what_rewind_does` | FAIL | fixed (W6, 8471c35; W2) | patch was piped in text mode (CRLF); fixture content was CRLF too |
| `test_drift.TestHandEdit.test_the_post_record_holds_the_hash_right_after_the_step` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_export.TestBuild.test_after_is_the_next_checkpoint_when_the_file_changed_again_later` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_export.TestBuild.test_bash_rename_shows_the_deleted_and_the_created_file` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_export.TestBuild.test_diff_is_before_the_step_against_after_it` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_export.TestCli.test_export_writes_the_default_file_and_reports_it` | FAIL | fixed (W3, 8e58b19; W2) | page written with newline="": file size equals the reported count |
| `test_export.TestPage.test_project_location_is_not_in_the_page` | FAIL | fixed (W3, 8e58b19) | scrub also removes the JSON-escaped Windows root |
| `test_filelock.TestUnixPath.test_shared_holders_coexist_and_keep_exclusive_out` | ERROR | fixed (W8, b4586b0) | Windows-specific expectation: a shared request takes the exclusive lock (documented) |
| `test_gc.TestGc.test_a_scan_no_record_names_is_listed_and_an_unreadable_old_one_can_be_dropped` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_gc.TestGc.test_deletes_only_unnamed_copies_measures_bytes_and_rewind_still_works` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_init.TestCli.test_cli_init_end_to_end_with_home_and_path` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestDetect.test_config_dir_in_project_user_dir_or_binary_on_path` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_global_writes_the_user_files` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_terminal_prompt_empty_answer_means_no` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_terminal_prompt_yes_installs_and_no_does_not` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_unreadable_config_is_an_error_and_the_others_still_install` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_without_yes_and_no_terminal_it_is_a_dry_run` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_init.TestInit.test_yes_installs_one_line_per_agent_and_a_second_run_changes_nothing` | FAIL | fixed (W5, 37df761) | stand-in binary is <name>.cmd on Windows; USERPROFILE set for the CLI test |
| `test_mcp.TestBadArguments.test_boolean_is_not_accepted_as_the_integer_it_technically_is_in_python` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestBadArguments.test_missing_required_argument_is_an_error` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestBadArguments.test_non_integer_step_is_an_error_not_a_crash` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestBadArguments.test_unknown_session_names_what_sessions_there_are` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_confirm_as_a_string_is_not_the_boolean_true_and_is_refused` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_confirm_as_the_integer_one_is_refused` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_confirm_false_is_refused` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_confirmed_rewind_actually_writes` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_no_tool_schema_exposes_a_force_argument` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_revert_step_without_confirm_is_refused` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDestructiveConfirmRefusal.test_rewind_to_step_without_confirm_is_refused` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDriftRefusal.test_a_second_identical_call_refuses_the_same_way_again` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestDriftRefusal.test_refuses_and_changes_nothing` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestHandshake.test_initialize_echoes_a_known_protocol_version_and_names_the_server` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestHandshake.test_initialize_falls_back_to_its_own_version_for_one_it_does_not_know` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestHandshake.test_notification_gets_no_reply_a_following_request_still_does` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestHandshake.test_ping` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestNoLogYet.test_every_tool_refuses_gracefully_with_no_log_in_the_project` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestProtocolRobustness.test_bad_json_gets_a_parse_error_and_the_server_keeps_going` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestProtocolRobustness.test_blank_lines_are_skipped_not_answered` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestProtocolRobustness.test_unknown_method_gets_method_not_found` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestProtocolRobustness.test_unknown_notification_gets_no_reply_either` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_diff` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_diff_out_of_range_step_is_an_error` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_preview_writes_nothing` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_replay` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_replay_seq_range` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_sessions` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestReadOnlyToolsAgainstAFixture.test_rewind_summary` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestRevertConflictRefusal.test_refuses_and_changes_nothing` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestRewindDiffRedaction.test_redacted_by_default` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestRewindDiffRedaction.test_reveal_secrets_anything_but_the_json_boolean_true_still_redacts` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestRewindDiffRedaction.test_reveal_secrets_true_returns_the_raw_text` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestStdoutPurity.test_every_line_on_stdout_is_exactly_one_json_object_in_order` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestToolsList.test_every_tool_has_a_schema_and_the_right_hint` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestToolsList.test_exactly_seven_tools` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestToolsList.test_required_arguments_match_the_frozen_contract` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_mcp.TestUnknownTool.test_unknown_tool_name_is_a_tool_error_not_a_protocol_error` | ERROR | fixed (W1, 10f0613) | cleanup error only: the directory was removed while the server still ran in it |
| `test_project_root.TestStepDiff.test_each_kind_with_its_own_diff` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_project_root.TestStepDiff.test_reverse_applying_a_step_diff_undoes_exactly_that_step` | FAIL | fixed (W6, 8471c35) | patch was piped in text mode (CRLF) |
| `test_redact.TestBundle.test_bundle_carries_no_secret_and_still_imports_and_rewinds` | ERROR | fixed (W3, 8e58b19) | import moves the paths, so rewind writes into the destination |
| `test_redact.TestBundle.test_no_redact_carries_the_session_exactly` | ERROR | fixed (W3, 8e58b19) | import moves the paths, so rewind writes into the destination |
| `test_runs.TestCompare.test_diff_between_two_runs_applies_with_git` | FAIL | fixed (W6, 8471c35; W2) | patch piped in text mode; autocrlf would rewrite the applied files |
| `test_runs.TestFork.test_fork_holds_the_files_as_they_were_right_after_the_step_and_leaves_the_project_alone` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_runs_demo.TestRunsDemo (setUpClass)` | ERROR | skipped (S2, 24ef82c) | POSIX sh demo; Windows has no POSIX sh |
| `test_site.TestSite.test_site_url_lives_in_config_only` | FAIL | fixed (W9, 0503da9) | repo paths '/'-joined before the HOST_ALLOWED lookup |
| `test_stale.StaleTest.test_init_yes_replaces_the_stale_hook_in_every_config_shape_and_keeps_the_users_hooks` | FAIL | fixed (W4, 8cdb352) | uninstall reads every command key; the /usr/bin/python3 patch (SW8c) removed |
| `test_stale.StaleTest.test_init_yes_replaces_the_stale_hook_in_every_config_shape_and_keeps_the_users_hooks` (agent='claude') | FAIL | fixed (W4, 8cdb352) | uninstall reads every command key; the /usr/bin/python3 patch (SW8c) removed |
| `test_stale.StaleTest.test_status_reports_each_file_writes_nothing_and_exits_1_on_stale` | ERROR | fixed (W4, 8cdb352) | regex escapes the Windows temp path |
| `test_takeback.RealRunTest.test_temp_dirs_are_removed` | FAIL | fixed (W10, 11d0904) | remove_tree clears git's read-only flag and retries |
| `test_ui.TestData.test_step_detail_has_the_diff_input_and_result_without_the_project_path` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_usable.TestInitWithoutHomeDirectoryCallsHookEphemeralSafely.test_dry_run_also_completes` | FAIL | fixed (W5, 37df761) | same stand-in fix |
| `test_usable.TestInitWithoutHomeDirectoryCallsHookEphemeralSafely.test_project_init_completes_and_installs_with_hook_ephemeral_called_for_real` | FAIL | fixed (W5, 37df761) | same stand-in fix |
| `test_usable.TestSummary.test_a_file_changed_and_changed_back_is_not_listed` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_usable.TestSummary.test_lists_net_file_changes_with_lines_steps_and_the_undo_commands` | FAIL | fixed (W2, bdd7cb5) | test Agent writes content byte for byte (no CRLF) |
| `test_windows_paths.TestBundleFromWindows.test_a_bundle_recorded_on_windows_imports_replays_and_rewinds_here` | FAIL | fixed (W3, 8e58b19) | root_spellings fix; windowsify() takes this OS's separator; destination-drive check made Windows-aware |

Count: 38 (W1) + 13 (W2) + 9 (W3) + 3 (W4) + 10 (W5) + 3 (W6) + 5 (W7) + 1 (W8) + 1 (W9) + 1 (W10) = 84 rows
marked fixed, and 3 skipped (S1: 2, S2: 1) = 87. Of the 84, `test_filelock` (W8) passes on Windows by a
Windows-specific expectation rather than the POSIX one.

## What a real Windows run still has to confirm

- That the whole list above is green: a fix that cures one failure can uncover the next assertion in the same
  test, which only a Windows run shows.
- W3's reliance on `realpath` expanding the 8.3 short name; W7's Git Bash path on the runner; W10's cause.
- Not covered by any test: the hook commands under PowerShell (Copilot's and Cursor's documented Windows shell);
  only Git Bash is exercised.

## Known Windows issue, not in the CI list and not fixed here

`rewindagents diff`, `replay --step N --diff` and `compare --diff` write the patch through `sys.stdout` in
text mode. On Windows that turns `\n` into `\r\n` (and a CRLF file's `\r\n` into `\r\r\n`), so a patch saved
with `>` will not `git apply` (the W6 failure, through the CLI instead of the tests). The fix is to write patch
text to `sys.stdout.buffer` on Windows, as the hook's reply already does (F2); it changes CLI output bytes, so it
is left for a separate, reviewed change.

## Earlier fixes still in the code (sprints 1 and 2)

F1 (`hook._OURS` accepts a single closing quote), F2 (hook reply written as bytes, no `\r\n`), F3
(`project.find_store_root` survives `Path.home()` raising), F4/F5 (Windows-hook tests use a POSIX stand-in
interpreter / build expectations with `Path`), SW1 (`newline=""` on 74 direct fixture writes), SW2
(`bundle.root_spellings` uses `ospaths.isabs`), SW3 (`rewind.relative()` and `init.py` display paths use
`.as_posix()`), SW4/SW4-fix/SW10 (`init.py`/`cli.py` survive `Path.home()` and `hook.ephemeral()` raising), SW5
(the test_revert mode skip), SW6 (`os.replace` in the export fixture), SW7 (UTF-8 in test_torn_write), SW8a/b
(hook-command assertions that hold for both command forms), SW9 (`bashscan.project_files` returns `/`-joined
paths). SW8c (patching `sys.executable` in test_stale) is removed by W4: it caused the claude subtest failure.
Their full write-up is in git history (`git show b63f2a2:docs/windows.md`).
