# 个人 IP 包格式

## 数据根目录

默认：

```text
~/.agents/personal-ip-article-illustrations/
├── config.json
├── ips/
│   └── <ip-id>/
│       ├── manifest.json
│       ├── assets/
│       │   └── turnaround.png
│       └── references/
│           └── character-spec.md
└── outputs/
```

如设置 `PERSONAL_IP_HOME`，将其作为数据根目录。该变量只能指向专用目录，不能指向用户主目录、文件系统根目录或 Skill 仓库。

## `ip-id`

- 简短英文小写 kebab-case，只允许 `a-z`、`0-9` 和单连字符。
- 不允许空格、斜杠、反斜杠、绝对路径、`..` 或控制字符。
- 同名包存在且内容不同，不覆盖；依次使用 `-v2`、`-v3`。

## manifest

```json
{
  "schemaVersion": 1,
  "id": "alex-creator",
  "displayName": "Alex Creator",
  "style": "white-space-watercolor-editorial",
  "assets": {
    "turnaround": "assets/turnaround.png",
    "turnaroundSha256": "<sha256>"
  },
  "characterSpec": "references/character-spec.md",
  "license": "private"
}
```

路径必须相对于包目录，解析后仍在包内；拒绝绝对路径、`..` 与逃逸符号链接。

## config

```json
{
  "schemaVersion": 1,
  "activeIp": "alex-creator"
}
```

只有目标包完整通过验证后才能激活。配置损坏时报告错误，不静默覆盖。

## 脚本

创建包：

```bash
python3 "<skill-root>/scripts/ip_pack.py" create \
  --id alex-creator \
  --display-name "Alex Creator" \
  --turnaround "/path/to/approved-turnaround.png" \
  --character-spec "/path/to/approved-character-spec.md" \
  --activate
```

验证包：

```bash
python3 "<skill-root>/scripts/ip_pack.py" validate "/path/to/ip-pack"
```

列出和切换：

```bash
python3 "<skill-root>/scripts/ip_pack.py" list
python3 "<skill-root>/scripts/ip_pack.py" activate alex-creator
```
