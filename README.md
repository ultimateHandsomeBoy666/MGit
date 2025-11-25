# MGit (Multi-Git) 使用手册

MGit 是一个轻量级的命令行工具，用于同时管理多个 Git 仓库。当你需要在多个微服务或模块中执行相同的操作（如 `pull`, `status`, `checkout`）时，它能为你节省大量时间。

## 安装指南

### 前置要求

- Python 3.6+
- `pip install colorama` 以获得彩色输出体验（Windows下推荐安装）。
  - 如果 `pip install colorama` 安装成功但是颜色不生效，可能是默认 pip 和 默认 python3 版本不一致，可以使用 `python3 -m pip install colorama` 来安装

### 安装步骤

1. 将 `mgit.py` 下载到你的电脑。

2. (Linux/Mac) 赋予执行权限并建立软链接：

   ```bash
   chmod +x mgit.py
   # 建议链接到 /usr/local/bin 或其他在 PATH 中的目录
   sudo ln -s /path/to/mgit.py /usr/local/bin/mgit
   ```

3. (Windows) 将 `mgit.py` 所在的文件夹添加到系统的环境变量 `PATH` 中，或者创建一个 `mgit.bat` 批处理文件指向它。

## 功能介绍

### 1. 仓库管理

MGit 使用一个本地 JSON 文件 (`~/.mgit_config.json`) 来记录你管理的仓库路径。

- **添加仓库**：

  ```bash
  mgit repo-add ./my-project-backend
  ```

- **列出仓库**：

  ```bash
  mgit repo-list
  ```

  *输出中会显示索引号（如 `[0]`, `[1]`），可以在删除或指定目标时使用。*

- **移除仓库**：

  ```bash
  mgit repo-rm 0              # 按列表索引移除
  ```

### 2. 指定目标仓库 (Target) 🔥

你可以使用 `-t` 或 `--target` 参数来指定只对某些仓库执行命令。支持**索引**和**智能分词模糊匹配**，支持逗号分隔。

- **按索引**：

  ```bash
  mgit -t 0 status           # 只查看第 0 个仓库
  mgit -t 0,2 pull           # 只拉取第 0 和 第 2 个仓库
  ```

- **按名称 (智能分词匹配)**： 支持非连续字符匹配，并**高亮**显示匹配字符，让你快速确认目标。

  ```bash
  mgit -t re1 pull           # 匹配 "repo1"
  mgit -t core,ui checkout master  # 操作所有包含 "core" 或 "ui" 的仓库
  ```

### 3. 执行 Git 命令

任何非 `repo-` 开头的命令都会被视为 Git 命令，并发地在所有(或指定)受管仓库中执行。

- **批量拉取代码**：

  ```bash
  mgit pull
  ```

- **查看状态**：

  ```bash
  mgit status
  ```

### 4. 高级功能 (特色)

- **智能概览 (`summary`)**： 以表格形式显示：仓库名、当前分支、是否有未提交修改、以及相对于远程分支的领先/落后情况。

  ```bash
  mgit summary
  mgit -t backend summary  # 只看后端仓库的概览
  ```

- **通用 Shell 命令 (`exec`)**： 在仓库目录下运行任意系统命令。

  ```bash
  mgit exec "npm install"
  mgit -t 0 exec "rm -rf build"  # 只在第0个仓库清理构建
  ```

## 设计思路

1. **并发执行**：使用了 Python 的 `ThreadPoolExecutor`，确保即使管理几十个仓库，网络请求（如 pull/push）也能并行处理，极大减少等待时间。
2. **线程安全输出**：使用了 `threading.Lock` 确保多个仓库的输出日志不会混乱地交织在一起。
3. **容错性**：如果某个仓库路径不存在或命令执行失败，不会中断其他仓库的操作，并在最后显示红色的错误信息。
