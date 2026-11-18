class Rewindagents < Formula
  include Language::Python::Virtualenv

  desc "Undo for AI coding agents: record, diff, and rewind tool calls"
  homepage "https://github.com/Johnbjoseph-cybersec/rewindagents"
  url "https://files.pythonhosted.org/packages/2c/4e/07bc7954fd7611cfd776d208b558b50c6802ba148250d49d3a44d4aefbba/rewindagents-1.1.1.tar.gz"
  sha256 "6b3ebf5c5ce4c61bac629f5cbb6ca11bd98efb2872170f6eb13162fb2d6fefce"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    # Zero runtime dependencies: a bare venv in libexec, pip install this
    # sdist into it, link its console script into bin. No resource blocks
    # needed because rewindagents has no third-party Python dependencies.
    virtualenv_install_with_resources
  end

  test do
    # "The flight recorder for coding agents" is the fixed --help description
    # in src/rewindagents/cli.py (confirmed present in the 1.1.1 sdist).
    output = shell_output("#{bin}/rewindagents --help")
    assert_match "The flight recorder for coding agents", output
  end
end
