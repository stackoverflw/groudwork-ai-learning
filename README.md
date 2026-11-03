# 地基 Groundwork

**离线 AI 工程学习平台。12 周练习问题定义、评测设计和可靠交付。**

[English](README.en.md) · [课程架构](课程架构.md) · [使用说明](使用说明.md)

地基面向大一学生和初学者。每节先讲一个小例子，再给自测和动手练习。四节预备课覆盖 Python、数学、计算机基础与常用硬件单位。主线从 NumPy、矩阵、梯度和注意力逐步进入数据校验、检索、引用评测、重试、权限和持久化。

贯穿项目是**本地论文与技术文档证据助手**。选取 UTF-8 的 TXT 或 Markdown 文件，按关键词检索原文，查看文件名和行号。课程用这个词法检索基线学习怎样构建评测集、区分命中与引用支持，以及证据不足时如何转人工复核。

## 快速开始

需要 Windows 10/11 和 Python 3.11。首次安装需要下载 Python 依赖。

```powershell
git clone https://github.com/stackoverflw/groudwork-ai-learning.git
cd groudwork-ai-learning
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

如果 Python 不在 PATH 上，可以为安装脚本传入 `-Python C:\path\to\python.exe`。安装完成后双击桌面的 **Groundwork** 快捷方式或仓库里的 `启动.bat`，再打开本地页面。 [打开 Groundwork](http://127.0.0.1:9890)

首页点 **从基础预备课开始**，或跟随当前单元的 **先看讲解 → 动手 → 自测**。编辑器用 **Ctrl+S** 保存草稿，**Ctrl+Enter** 运行测试。提醒默认关闭，可在设置中开启。

## 课程与功能

| 阶段 | 产出 |
| --- | --- |
| 预备课 | Python 函数、比例与变化率、数据与编码、传输时间与能量估算 |
| 第 1–2 周 | 五道算子练习、五份详细讲义、两个本机 CPU NumPy 实验 |
| 第 3–6 周 | 输入输出契约、数据验证、混淆矩阵和资源估算 |
| 第 7–9 周 | 可复现检索、引用检查和故障重试 |
| 第 10–12 周 | 权限边界、幂等处理及带出处的证据助手 |

应用包含 12 周课程、4 节预备课、4 套里程碑题，以及错题复习、工时统计和实验记账。项目练习包含正确性和边界测试。闭卷计算题自动评分，解释与设计题按评分标准自评。

## 本地数据与运行

服务只监听 `127.0.0.1:9890`。运行时离线，学习记录存于 `data/groundwork.db`。可以在 **账** 中导出 JSON 和恢复记录。证据助手在浏览器中读取你选择的文件。练习代码在本机子进程中执行，拥有当前用户权限，请运行你信任的代码。

两个 NumPy 实验测量的是 CPU 耗时与内存。证据助手的当前版本采用词法检索，课程将它作为比较模型生成与检索增强方案的基线。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe run.py --selfcheck
.\.venv\Scripts\python.exe -m pytest -q
```

`app/` 包含 FastAPI、SQLite、练习运行器和网页。 `content/` 包含课程与实验。 `scripts/` 包含安装和维护工具。 `tests/` 包含课程推进、故障恢复和备份轮转测试。

欢迎提交可复现的错误报告、讲解改进或额外测试。许可证采用 MIT。 [查看 LICENSE](LICENSE)
