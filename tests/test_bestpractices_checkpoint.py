# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
"""Exercise ER-74's actual embedded Python against offline JSON fixtures."""

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

CHECKPOINTS = (
    Path(__file__).resolve().parent.parent
    / "skills/enterprise-readiness/checkpoints.yaml"
)


def checkpoint_program():
    """Read only the delimited Python source, without interpreting YAML."""
    source = CHECKPOINTS.read_text(encoding="utf-8")
    return textwrap.dedent(
        source.split("# BEGIN ER-74 Python\n", 1)[1].split(
            "      # END ER-74 Python", 1
        )[0]
    )


class BestPracticesCheckpointTests(unittest.TestCase):
    def check(self, content, expected):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".bestpractices.json").write_bytes(content)
            result = subprocess.run(
                [sys.executable, "-c", checkpoint_program()],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, expected, result.stderr)

    def valid(self, **changes):
        value = {
            "repo_public_status": "Met",
            "repo_public_justification": "Public source: https://github.com/org/project",
        }
        value.update(changes)
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    def test_supported_statuses_and_case(self):
        for status in ("Met", "Unmet", "N/A", " met ", "unmet", "n/a"):
            with self.subTest(status=status):
                self.check(self.valid(repo_public_status=status), 0)

    def test_missing_or_malformed_object(self):
        for content in (b"", b"{", b"{}", b"[]", b"null", b"true", b"42"):
            with self.subTest(content=content):
                self.check(content, 1)

    def test_duplicate_keys_are_not_last_value_wins(self):
        self.check(
            b'{"test_status":"Unmet","test_status":"Met",'
            b'"test_justification":"https://example.org/tests"}',
            1,
        )

    def test_missing_pairs_and_ignored_metadata(self):
        for value in (
            {"test_status": "Met"},
            {"test_justification": "https://example.org/tests"},
            {"_comment": "Ignored by upstream"},
        ):
            with self.subTest(value=value):
                self.check(json.dumps(value).encode(), 1)

    def test_non_string_and_ignored_statuses(self):
        for status in ("?", "unknown", "", "yes", 1, None, {}, []):
            with self.subTest(status=status):
                self.check(self.valid(repo_public_status=status), 1)

    def test_justification_limits_and_https_evidence(self):
        prefix = "https://example.org/evidence "
        self.check(self.valid(repo_public_justification=prefix.ljust(8192)), 0)
        self.check(self.valid(repo_public_justification=prefix.ljust(8193)), 1)
        for value in ("", " ", "http://example.org", "https://", "https://?q=x", 1):
            with self.subTest(value=value):
                self.check(self.valid(repo_public_justification=value), 1)

    def test_file_size_is_utf8_bytes(self):
        content = self.valid()
        self.check(content.ljust(100000), 0)
        self.check(content.ljust(100001), 1)
        multibyte = {}
        for number in range(7):
            multibyte[f"test_{number}_status"] = "Met"
            multibyte[f"test_{number}_justification"] = (
                "https://example.org/" + "ä" * 8000
            )
        self.check(json.dumps(multibyte, ensure_ascii=False).encode("utf-8"), 1)

    def test_invalid_unicode_and_nested_values(self):
        self.check(b'{"test_status":"\xff"}', 1)
        self.check(
            self.valid(repo_public_justification={"url": "https://example.org"}), 1
        )

    def test_escaped_surrogates_follow_badgeapp_utf8_rules(self):
        prefix = b'{"test_status":"Met","test_justification":"https://example.org/'
        for surrogate in (b"\\ud800", b"\\udfff"):
            with self.subTest(surrogate=surrogate):
                self.check(prefix + surrogate + b'"}', 1)
        self.check(prefix + b'\\ud83d\\ude00"}', 0)

    def test_format_does_not_claim_criterion_or_evidence_validation(self):
        self.check(
            json.dumps(
                {
                    "invented_criterion_status": "N/A",
                    "invented_criterion_justification": "https://example.org/other-project",
                }
            ).encode(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
