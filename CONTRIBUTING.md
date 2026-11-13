# Contributing

[English](CONTRIBUTING.md) · [简体中文](docs/CONTRIBUTING.zh-CN.md) · [日本語](docs/CONTRIBUTING.ja.md) · [Русский](docs/CONTRIBUTING.ru.md) · [فارسی](docs/CONTRIBUTING.fa.md)

Proxy Guard welcomes reproducible bug reports, compatibility results, documentation fixes and focused pull requests.

- [Bug report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=bug_report.yml)
- [Compatibility report](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=compatibility.yml)
- [Feature request](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=feature_request.yml)
- [Documentation feedback](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=documentation.yml)

Report security issues privately according to the security policy. Share redacted evidence in public issues. [Security policy](docs/SECURITY.en.md)

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

These checks read repository files only. They validate translation files, navigation, the destination language of Markdown links, anchors, version tables, changelog headings, and package filenames. They do not replace semantic translation review or VM tests.

CI also compares the latest stable GitHub Release with the versions in the source and five READMEs. Pull requests run offline checks; publication and default-branch checks add the live Release comparison. A planned version bump can pass PR checks before publication, but the default-branch Release check will remain failing until the matching stable Release is published. Re-run the workflow after publication if needed.

## Pull requests and evidence

Explain the problem, changed behavior, validation and remaining limits. For compatibility additions, include exact versions, date and whether the test used mocks, isolated real kernels, or an actual deployment. Preserve the first failure when a later rerun passes.

Do not include generated packages, private lab logs or unrelated formatting churn in a documentation PR. Contributions use the repository's existing license; preserve third-party notices. See [licensing](docs/LICENSING.en.md).
