# 长审片图

## JSON 格式

```json
{
  "title": "文章配图审片",
  "subtitle": "当前 IP：Alex Creator",
  "sections": [
    {
      "title": "第一组 · 核心判断",
      "items": [
        {
          "path": "01-core-idea.png",
          "caption": "01 · 核心判断 · 建议放在开头之后"
        }
      ]
    }
  ]
}
```

相对图片路径以 JSON 文件所在目录为基准。所有 section 和 item 都不能为空。

## 生成

```bash
python3 "<skill-root>/scripts/build_review_longshot.py" \
  --spec "/absolute/path/review-spec.json" \
  --output "/absolute/path/article-review-longshot.png"
```

默认长图宽 1400px，单图展示宽 1280px；每张图在白色 16:9 框内等比缩放并完整显示，不裁切。脚本需要 Pillow。找不到中文字体时用 `--font` 指定字体。

输出同名存在时自动创建 `-v2`、`-v3`。长图是审片索引，独立原图必须保留。
