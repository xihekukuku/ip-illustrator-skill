# Personal IP Article Illustrations

一个可公开安装的 Codex Skill：先从清晰照片或已有三视图创建、导入和切换每位用户自己的个人 IP，再用当前 IP 为完整文章生成统一的正文插图与长审片图。

公开仓库只保存流程、模板和辅助脚本，不包含任何真人照片、私人三视图、用户文章或生成成品。

## 视觉默认值

- 16:9 横版正文插图
- 纯白背景与大面积留白
- 低饱和水彩漫画、轻纸张颗粒、细手绘轮廓
- 每张图一个核心观点、一个异常关系、1—3 个主要物件
- 第一眼读懂关系，第二眼发现一个不合理却准确回应观点的细节
- 同一 IP 可在一张图中重复出现，用于阶段、对照、选择或重复动作

## 安装

在 Codex 中直接说：

```text
请使用 $skill-installer 从 xihekukuku/ip-illustrator-skill 安装 skills/personal-ip-article-illustrations
```

或运行系统 Skill Installer：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo xihekukuku/ip-illustrator-skill \
  --path skills/personal-ip-article-illustrations
```

也可以手动安装：

```bash
git clone https://github.com/xihekukuku/ip-illustrator-skill.git /tmp/ip-illustrator-skill
test ! -e ~/.codex/skills/personal-ip-article-illustrations && \
  cp -R /tmp/ip-illustrator-skill/skills/personal-ip-article-illustrations \
    ~/.codex/skills/personal-ip-article-illustrations
```

安装完成后，从下一次对话开始可用。

## 典型触发词

创建个人 IP：

```text
用这张照片创建我的个人 IP 三视图，长期用于文章配图。
```

导入已有角色：

```text
把这张三视图和角色规范导入为我的个人 IP，并设为当前角色。
```

文章配图和审片：

```text
用我的当前 IP 给这篇文章配图：16:9 白底留白、低饱和水彩隐喻风格，完成后生成长审片图。
```

也可以显式调用 `$personal-ip-article-illustrations`。

## 五种工作模式

1. `build`：照片 → 三视图 → 用户确认 → IP 包。
2. `import`：已有三视图 + 角色规范 → 校验 → IP 包。
3. `select`：列出与切换当前 IP。
4. `illustrate`：完整读取文章并生成独立插图。
5. `review`：把本次插图拼成不裁切的长审片图。

三视图确认是唯一固定审核门。确认前不会写入正式 IP 包，也不会开始批量文章配图。

## 用户数据位置

默认保存在：

```text
~/.agents/personal-ip-article-illustrations/
```

可以用专用环境变量 `PERSONAL_IP_HOME` 指定其他绝对目录。角色包位于 `ips/`，文章成品优先写入当前可写工作区的 `.ip-illustrations/`，否则回退到用户数据目录的 `outputs/`。

所有正式写入都采用非覆盖策略；同名内容自动使用 `-v2`、`-v3`。卸载 Skill 不会删除用户 IP 数据。

## 隐私与许可

- 真人照片只用于当次视觉参考，不复制进 IP 包，不写入路径，不提交到 Git。
- 不做人脸实名识别，不推断敏感属性。
- 自定义 IP 包默认 `license: private`。
- MIT License 仅覆盖本仓库代码和文档，不覆盖用户输入、三视图、角色规范或生成图片。
- 用户应确认自己有权使用第三方人物、角色和品牌素材。

详见 [PRIVACY.md](PRIVACY.md)。

## 依赖

- 具备参考图能力的图像生成工具，才能直接生成三视图与文章插图。
- Python 3.10+ 用于辅助脚本。
- Pillow 用于图片标准化与长审片图；没有 Pillow 时，IP 打包脚本仍可处理标准 PNG。
- 没有图像生成能力时，Skill 只输出完整提示词与保存计划，并明确标记“图片尚未生成”。

开发验证：

```bash
python3 -m pip install -r requirements-dev.txt
python3 skills/personal-ip-article-illustrations/scripts/validate_skill.py \
  skills/personal-ip-article-illustrations
python3 skills/personal-ip-article-illustrations/scripts/public_release_check.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## 不适用范围

本 Skill 不用于封面、商业海报、Logo、头像、换脸、角色训练数据集、无文章语境的普通生图，也不替代用户对三视图一致性的人工确认。

## License

[MIT](LICENSE) for repository code and documentation. User assets retain their own rights and licenses.
