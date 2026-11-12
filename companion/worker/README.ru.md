# Proxy Guard Cloudflare Worker

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

Необязательный ретранслятор управления Pro между OpenWrt и VPS Agent через Tunnel/VPC Service. Передаёт аутентификацию, политики и статус. Трафик прокси и независимый сигнал через SOCKS имеют отдельный путь.

- [Развёртывание и привязки](../../docs/CLOUDFLARE-WORKER.ru.md)
- [Архитектура и сбои](../../docs/PRO-COMPANION.ru.md)
- [Протокол и обновление](../../docs/EDITION-MATRIX.ru.md)
- [Установка VPS Agent](../../docs/LINUX-AGENT-INSTALL.ru.md)

Версия npm 0.2.0, протокол Agent v3. Используйте исходники одного выпуска, проверьте привязки, отдельные секреты и реальные ответы. Облачные и локальные проверки выполняются отдельно. Прямой HTTPS обходится без Worker.

[Участие](../../docs/CONTRIBUTING.ru.md) · [Политика безопасности](../../docs/SECURITY.ru.md) · [Сторонние уведомления](THIRD_PARTY_NOTICES.ru.md)
