# 清单与辅助工具

路径默认相对清单所在目录解析。工具没有任何上传功能。以下例子使用 `python`，在 Codex 中优先使用工作区依赖加载器返回的 Python；不要求固定安装路径。

## 逐页清单

JSON 编码为 UTF-8，`schema_version` 为 1。必需字段如下；额外规划字段允许保留。

```json
{
  "schema_version": 1,
  "presenter": "李江平",
  "expected_slide_count": 20,
  "max_seconds": 1200,
  "planned_seconds": 1170,
  "forbidden_text": ["［", "请替换", "[Paper title"],
  "slides": [
    {
      "number": 1,
      "title": "研究题目",
      "seconds": 30,
      "cue": "介绍题目与核心问题",
      "speech": "各位老师、同学好……",
      "source": "原文 p.1，题名与摘要",
      "asset_ids": []
    }
  ]
}
```

例子只展示一页结构，实际清单必须包含 `expected_slide_count` 页，编号连续，逐页秒数之和等于 `planned_seconds`。每页 `asset_ids` 列出该页使用的来源素材 ID；没有素材时使用空列表。核查会在指定页实际嵌入的图片中检查素材哈希。

## PDF 原图裁剪

```sh
python scripts/crop_pdf_asset.py --pdf paper.pdf --page 11 --bbox 360 257 541 295 --scale 6 --output assets/equation-7.png --manifest assets.json --id equation-7 --kind equation --label "Equation (7)" --printed-page 111
```

`--page` 从 1 开始。`--bbox` 是 PDF 页面的左上角坐标系，单位为点，顺序为左、上、右、下，包含旋转后的实际页面坐标。先渲染定位再给坐标，禁止照抄其他论文的坐标。倍率必须为有限正数，建议 4–6。输出文件必须不存在；修改裁剪时使用新文件名和 ID。

工具更新素材清单：记录 PDF 哈希、文件页码、印刷页码、坐标、倍率、类型、标签和 PNG 哈希。路径为相对路径，复制工作目录时一并复制 PDF 与素材，或更新路径。工具拒绝重复 ID、不合法页码、越界裁剪及覆盖已有 PNG。

## 最终交付核查

```sh
python scripts/audit_report.py --pptx output/report.pptx --script output/speaker.md --manifest report-plan.json --assets-manifest assets.json --output qa/report.json
python scripts/audit_report.py --verify-report qa/report.json
```

无来源图片的任务可省略 `--assets-manifest`；任何页声明的 `asset_ids` 都必须可解析。核查读取 PPTX 的实际逻辑顺序，检查可见页、标题、备注、讲稿内容、来源、时间、汇报人、占位残留、图片在对应页中的哈希和来源 PDF 哈希。

报告包含最终文件及所有输入与素材的 SHA-256、检查结果和核查边界。失败时返回非零退出码。`--verify-report` 对报告中的全部文件重新求哈希，拒绝失败报告及过期或缺失的输入。它不证明论文理解和视觉设计正确，也不重新判定来源截图的学术含义。
