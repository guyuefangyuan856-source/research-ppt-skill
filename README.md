# Research PPT · 科研汇报 Skill

从论文全文和参考模板制作可编辑的科研组会 PPT、原文公式截图及逐页讲稿。默认中文、共 20 页、汇报人李江平，计划讲解 19 分 30 秒，上限 20 分钟。论文、模板、页数、时间、姓名与语言均可修改。

## 使用

在 Codex 中打开本仓库目录，或从仓库内部启动 Codex，然后提供论文 PDF：

```text
使用 $artifact-template-research-ppt，深入阅读我提供的 paper.pdf，
沿用默认模板制作组会汇报 PPT 和逐页 Markdown 讲稿。
让没有读过论文的同学能够理解研究问题、方法、关键证据和局限。
```

覆盖默认参数：

```text
使用 $artifact-template-research-ppt，基于 paper.pdf 和 my-template.pptx，
制作共 12 页、10 分钟以内的中文汇报，汇报人王同学。
公式必须使用原文截图，解释符号并提供对应的逐页讲稿。
```

技能入口位于 `.agents/skills/artifact-template-research-ppt/SKILL.md`。Codex 会扫描仓库内的 `.agents/skills`；从本仓库的父目录工作时，需要显式提供该入口或将本仓库作为工作目录。若当前会话尚未显示新技能，重新打开仓库会话。无需修改全局配置。

## 内容与依赖

- `SKILL.md`：触发范围、默认参数和主流程。
- `references/`：论文证据、讲稿、视觉验收及清单格式。
- `assets/`：19 页蓝白占位模板和封面预览，已移除旧论文图文与原汇报人信息。
- `scripts/`：PDF 图像裁剪与交付一致性核查。
- `examples/`：无真实论文的示例请求与精简清单。

制作幻灯片依赖 Codex 的 Presentations 工作流及其提供的 JavaScript 运行库；本仓库不分发该私有运行库，也不是无需模型参与的“一键读论文生成 PPT”程序。Python 辅助工具要求 Python 3.11+。

在 Codex 中优先使用工作区依赖加载器提供的环境。单独运行辅助工具时，可在本仓库内创建虚拟环境：

```sh
python -m venv .venv
# 激活 .venv 后执行
python -m pip install -r requirements-dev.txt
python tools/check_repository.py
python -B -m unittest discover -s tests -v
```

脚本命令和 JSON 格式见技能中的 `references/manifest-and-tools.md`。默认制作过程先理解论文，再规划逐页内容，随后复用模板、截图公式、生成讲稿并检查最终渲染。

## 验收与限制

交付核查检查实际页序、标题、备注、讲稿、时间、素材在对应页的嵌入及文件哈希。报告绑定最终 PPTX、讲稿、清单、素材和来源文件，任何输入变化都需要重新核查。

```sh
python .agents/skills/artifact-template-research-ppt/scripts/audit_report.py --verify-report .work/case20/qa/report.json
```

结构检查不证明科研结论正确、裁剪语义完整或视觉效果良好，也不代表已经完成真人口头计时。每次仍需依据论文核对事实、查看全部最终幻灯片，并按需要排练。

GitHub Actions 在 Windows 与 Linux 上执行资源检查和辅助工具测试；完整 PPT 渲染在具备 Codex Presentations 依赖的本地环境执行。首版验证记录见 `VALIDATION.md`。

## Git 版本迭代

本仓库独立于父项目；临时文件、原论文、完整测试成品及依赖保留在 `.work/` 等忽略目录中。只提交技能、公开占位模板、精简示例和维护工具。

```sh
git clone https://github.com/guyuefangyuan856-source/research-ppt-skill.git
cd research-ppt-skill
git switch -c improve/formula-explanation
# 修改后先执行上面的检查与测试，并检查受影响的示例幻灯片
git add .agents tools tests examples README.md CHANGELOG.md
git commit -m "feat: improve formula explanation guidance"
git push -u origin improve/formula-explanation
```

合并到 `main` 后，根据改动更新版本记录：兼容修复升补丁号，兼容能力增加升次版本号，不兼容清单或调用变更升主版本号。首版为 `v0.1.0`。

```sh
git tag -a v0.1.1 -m "Release v0.1.1"
git push origin main
git push origin v0.1.1
python tools/package_skill.py --version v0.1.1
```

查看历史版本可用 `git switch --detach v0.1.0`，返回开发用 `git switch main`。共享分支需要撤销某次修改时使用 `git revert <commit>`，保留协作历史。工作区有未提交修改时先保存。

## 授权与来源

原创技能说明、脚本、测试及维护文档采用 MIT，见 `LICENSE`。参考模板中的校徽、校园背景和其他第三方素材不在 MIT 授权范围内，见 `THIRD_PARTY_NOTICES.md`。原论文及完整真实案例不在本公开仓库中。

结构依据 [OpenAI 的 Skills 文档](https://learn.chatgpt.com/docs/build-skills)，模板基础包使用宿主提供的 Template Creator 创建，后续按科研汇报需求补充工作流程和辅助工具。
