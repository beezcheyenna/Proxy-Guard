# Contributing / 参与贡献

Proxy Guard welcomes reproducible bug reports, compatibility results, documentation fixes and focused pull requests.

- [Bug report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=bug_report.yml)
- [Compatibility report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=compatibility.yml)
- [Feature request](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=feature_request.yml)
- [Documentation feedback](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=documentation.yml)

**Security reports must be private.** Email [beezcheyenna268@gmail.com](mailto:beezcheyenna268@gmail.com) before publishing exploitable details, especially VPS access, authentication, SSH or protection bypasses. Read the [security policy](docs/SECURITY.en.md). Do not upload credentials, private keys, full production configurations, HAR files or real deployment addresses.

## Before changing behavior

1. Describe the trigger, expected behavior and actual result. Use documentation addresses and a minimal sanitized topology.
2. Record firmware/distribution, kernel, architecture, package format, Standard/Pro versions, actual proxy core and forwarding mode. Distinguish package metadata from the running binary.
3. Use an authorized isolated environment. Scripts that manage services, routes or firewall rules belong inside disposable VMs, not a workstation or production host.
4. Keep changes focused. Do not weaken ACLs, bypass certificate verification or change unrelated NAT/DNS/network configuration to make a test pass.

See [building](docs/BUILDING.md), [test matrix](docs/TEST-MATRIX.md) and [component compatibility](docs/EDITION-MATRIX.md). A passing mock test does not establish native installation or packet-path compatibility.

## Documentation and translations

The five user-facing languages are Simplified Chinese, English, Japanese, Russian and Persian. The repository homepage is English, with Simplified Chinese as the second language entry. Update matching README and user-guide passages when behavior changes. Changelogs are maintained in English; the former localized changelog URLs retain English content for link compatibility. Technical reference pages are shared and linked from the localized guides.

Run the lightweight documentation checks from the repository root:

```sh
python3 tools/check_docs.py
python3 -m unittest discover -s tools/tests -p 'test_check_docs.py'
```

These checks read repository files only. They validate local Markdown/HTML links and anchors, the five README version tables, changelog release headings and package filenames. They do not replace semantic translation review or VM tests.

CI also compares the latest stable GitHub Release with the versions in the source and five READMEs. Pull requests run offline checks; publication and default-branch checks add the live Release comparison. A planned version bump can pass PR checks before publication, but the default-branch Release check will remain failing until the matching stable Release is published. Re-run the workflow after publication if needed.

## Pull requests and evidence

Explain the problem, changed behavior, validation and remaining limits. For compatibility additions, include exact versions, date and whether the test used mocks, isolated real kernels, or an actual deployment. Preserve the first failure when a later rerun passes.

Do not include generated packages, private lab logs or unrelated formatting churn in a documentation PR. Contributions use the repository's existing license; preserve third-party notices. See [licensing](docs/LICENSING.md).
