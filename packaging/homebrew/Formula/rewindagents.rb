class Rewindagents < Formula
  include Language::Python::Virtualenv

  desc "Undo for AI coding agents: record, diff, and rewind tool calls"
  homepage "https://github.com/Johnbjoseph-cybersec/rewindagents"
  url "https://files.pythonhosted.org/packages/1d/fc/322e7e3e35fd23e5bbc49581ccd81befaaa0262ccca59a380d3b0486a029/rewindagents-1.0.0.tar.gz"
  sha256 "94f843a8960675b0ee024da2761d796476305947277c0032f7b33f66b05a2901"
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
    # in src/rewindagents/cli.py (confirmed present in the 1.0.0 sdist).
    output = shell_output("#{bin}/rewindagents --help")
    assert_match "The flight recorder for coding agents", output
  end
end
