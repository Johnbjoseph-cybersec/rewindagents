class Rewindagents < Formula
  include Language::Python::Virtualenv

  desc "Undo for AI coding agents: record, diff, and rewind tool calls"
  homepage "https://github.com/Johnbjoseph-cybersec/rewindagents"
  url "https://files.pythonhosted.org/packages/4c/58/7666dd51ca8b071ed144f68dfb5789d4e1dddb1c3eae1198f4949bd244d1/rewindagents-1.1.0.tar.gz"
  sha256 "8bf584fac0f030902c72ada34264ea8f7b30017ecf587fb313c35a81884c3d55"
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
    # in src/rewindagents/cli.py (confirmed present in the 1.1.0 sdist).
    output = shell_output("#{bin}/rewindagents --help")
    assert_match "The flight recorder for coding agents", output
  end
end
