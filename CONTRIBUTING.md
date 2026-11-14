# Contributing

[English](CONTRIBUTING.md) · [简体中文](docs/CONTRIBUTING.zh-CN.md) · [日本語](docs/CONTRIBUTING.ja.md) · [Русский](docs/CONTRIBUTING.ru.md) · [فارسی](docs/CONTRIBUTING.fa.md)

Proxy Guard welcomes reproducible bug reports, compatibility results, documentation fixes and focused pull requests.

- [Bug report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=bug_report.yml)
- [Compatibility report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=compatibility.yml)
- [Feature request](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=feature_request.yml)
- [Documentation feedback](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=documentation.yml)

Use public issues for ordinary problems and share redacted evidence. Keep unpatched vulnerability details out of public issues. [Security policy](docs/SECURITY.en.md)

## Before changing behavior

1. Describe the trigger, expected behavior and actual result. Use documentation addresses and a minimal sanitized topology.
2. Record firmware, kernel, architecture, package format, installed Proxy Guard version, actual proxy core and forwarding mode. Distinguish package metadata from the running binary.
3. Use an authorized isolated environment. Scripts that manage services, routes or firewall rules belong inside disposable VMs, not a workstation or production host.
4. Keep changes focused. Do not weaken ACLs, bypass certificate verification or change unrelated NAT/DNS/network configuration to make a test pass.

See [building](docs/BUILDING.en.md) and the [test matrix](docs/TEST-MATRIX.en.md). A passing mock test does not establish native installation or packet-path compatibility.

## Documentation and translations

The five user-facing languages are Simplified Chinese, English, Japanese, Russian and Persian. The repository homepage is English, with Simplified Chinese as the second language entry. Update the affected pages in all five languages when behavior changes. Keep links in the reader's language and use the page's language menu for switching languages. Changelogs are English, across the documentation. Preserve the original license texts and distribution notices.

Run the lightweight documentation checks from the repository root:

```sh
python3 tools/check_docs.py
python3 -m unittest discover -s tools/tests -p 'test_check_docs.py'
```

These checks read repository files only. They validate translation files, navigation, link languages and anchors, package revisions and filenames, changelogs, and license-manifest checksums. Review translations and runtime behavior separately.

Pull requests run offline checks. Publication and default-branch checks also compare the latest stable GitHub Release with the versions in the source and five READMEs, and check links against the tag or commit they reference. After a version bump reaches the default branch, publish the matching stable Release to make the Release check pass.

## Pull requests and evidence

Explain the problem, changed behavior, validation and remaining limits. For compatibility additions, include exact versions, date and whether the test used mocks, isolated real kernels, or an actual deployment. Preserve the first failure when a later rerun passes.

Do not include generated packages, private lab logs or unrelated formatting churn in a documentation PR. Contributions use the repository's existing license; preserve third-party notices. See [licensing](docs/LICENSING.en.md).
