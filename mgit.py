#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import shutil

# --- 颜色配置区域 ---
try:
    from colorama import init, Fore, Style
    init(autoreset=True, strip=False)
    COLOR_AVAILABLE = True
except ImportError:
    COLOR_AVAILABLE = False
    class Fore: RED = GREEN = YELLOW = CYAN = BLUE = WHITE = MAGENTA = RESET = ""
    class Style: BRIGHT = RESET_ALL = ""
    print("【警告】未检测到 'colorama' 库，输出将为黑白。", file=sys.stderr)
    print(f"请尝试在当前环境运行安装命令: {sys.executable} -m pip install colorama\n", file=sys.stderr)

CONFIG_FILE = Path.home() / ".mgit_config.json"
print_lock = threading.Lock()

class MGit:
    def __init__(self):
        self.repos = self._load_config()

    def _load_config(self):
        if not CONFIG_FILE.exists():
            return []
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"{Fore.RED}加载配置文件失败: {e}")
            return []

    def _save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.repos, f, indent=4)
        except Exception as e:
            print(f"{Fore.RED}保存配置文件失败: {e}")

    def add_repo(self, path):
        abs_path = os.path.abspath(path)
        if not os.path.isdir(os.path.join(abs_path, '.git')):
            print(f"{Fore.RED}错误: '{abs_path}' 不是一个有效的 git 仓库。")
            return
        
        if abs_path in self.repos:
            print(f"{Fore.YELLOW}仓库已存在: {abs_path}")
            return

        self.repos.append(abs_path)
        self._save_config()
        print(f"{Fore.GREEN}成功添加仓库: {abs_path}")

    def remove_repo(self, target):
        target_path = None
        try:
            idx = int(target)
            if 0 <= idx < len(self.repos):
                target_path = self.repos[idx]
        except ValueError:
            abs_path = os.path.abspath(target)
            if abs_path in self.repos:
                target_path = abs_path
        
        if target_path:
            self.repos.remove(target_path)
            self._save_config()
            print(f"{Fore.GREEN}已移除仓库: {target_path}")
        else:
            print(f"{Fore.RED}未找到仓库: {target}")

    def _fuzzy_match(self, query, text):
        """
        分词模糊匹配逻辑 (Subsequence Match)
        返回: (是否匹配, 匹配字符的索引集合)
        例如: query='re1', text='repo1' -> True, {0, 1, 4}
        """
        query = query.lower()
        text_lower = text.lower()
        indices = set()
        
        t_start = 0
        temp_indices = []
        
        # 顺序查找每一个字符
        for char in query:
            found_idx = text_lower.find(char, t_start)
            if found_idx == -1:
                return False, set()
            temp_indices.append(found_idx)
            # 下一次查找从当前找到的位置之后开始
            t_start = found_idx + 1
            
        return True, set(temp_indices)

    def _highlight_text(self, text, indices, base_color=""):
        """
        根据索引高亮文本
        base_color: 高亮结束后恢复的颜色
        """
        if not indices:
            return text
        
        res = []
        # 高亮样式：黄色+加粗
        hl_style = f"{Fore.YELLOW}{Style.BRIGHT}"
        # 恢复样式：重置所有 + 恢复基础颜色
        reset_style = f"{Style.RESET_ALL}{base_color}"
        
        for i, char in enumerate(text):
            if i in indices:
                res.append(f"{hl_style}{char}{reset_style}")
            else:
                res.append(char)
        return "".join(res)

    def get_target_repos(self, selector):
        """
        根据选择器筛选仓库，并返回高亮信息
        返回格式: { repo_path: matched_indices_set }
        """
        if not selector:
            # 如果没指定筛选，返回所有仓库，且无高亮
            return {repo: set() for repo in self.repos}
        
        selected_map = {} # path -> set(indices)
        keys = selector.split(',')
        
        for key in keys:
            key = key.strip()
            if not key: continue
            
            # 1. 尝试按索引匹配 (不进行高亮)
            try:
                idx = int(key)
                if 0 <= idx < len(self.repos):
                    repo = self.repos[idx]
                    if repo not in selected_map:
                        selected_map[repo] = set()
                    continue
            except ValueError:
                pass
            
            # 2. 尝试按名称智能分词匹配
            match_found = False
            for repo in self.repos:
                repo_name = os.path.basename(repo)
                is_match, indices = self._fuzzy_match(key, repo_name)
                
                if is_match:
                    match_found = True
                    if repo not in selected_map:
                        selected_map[repo] = set()
                    # 合并高亮索引 (处理同一个仓库匹配多个关键词的情况)
                    selected_map[repo].update(indices)
            
            if not match_found and not key.isdigit():
                 print(f"{Fore.YELLOW}警告: 未找到匹配 '{key}' 的仓库")

        return selected_map

    def list_repos(self, target_map=None):
        """
        target_map: {path: indices}
        """
        # 如果没有 map，默认显示所有
        if target_map is None:
            target_map = {repo: set() for repo in self.repos}
            
        print(f"{Style.BRIGHT}当前管理的仓库 ({len(target_map)}/{len(self.repos)}):")
        
        for idx, repo in enumerate(self.repos):
            if repo in target_map:
                repo_name = os.path.basename(repo)
                # 在列表中，基础颜色是默认终端色，所以 base_color 传空或 RESET
                highlighted_name = self._highlight_text(repo_name, target_map[repo], base_color="")
                print(f" [{idx}] {highlighted_name}  {Fore.CYAN}({repo})")

    def _run_single_repo(self, repo_path, command, is_shell=False, highlight_indices=None):
        repo_name = os.path.basename(repo_path)
        try:
            term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
            
            if is_shell:
                cmd = command
            else:
                cmd = ["git", "-c", "color.ui=always"] + command
            
            env = os.environ.copy()
            env["COLUMNS"] = str(term_width)

            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, shell=is_shell, env=env
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            with print_lock:
                # 构造高亮的 header
                # 注意：header 的基础颜色是 CYAN，所以高亮结束后要恢复为 CYAN
                display_name = self._highlight_text(repo_name, highlight_indices, base_color=Fore.CYAN)
                header_str = f"[{display_name}]"
                
                # 打印头部
                print(f"{Fore.CYAN}{Style.BRIGHT}┌── {header_str} {Style.RESET_ALL}{Fore.CYAN}in {repo_path}")
                
                if result.returncode == 0:
                    # 成功时，同时打印 stdout 和 stderr
                    # Git 的很多正常输出(如 push/fetch 的进度)都在 stderr 中
                    if output:
                        print(f"{output}")
                    if error:
                        print(f"{error}")
                        
                    if not output and not error:
                        print(f"{Fore.GREEN}√ 完成 (无输出)")
                else:
                    print(f"{Fore.RED}× 失败 (Code: {result.returncode})")
                    if output: print(output)
                    if error: print(f"{Fore.RED}{error}")
                
                print(f"{Fore.CYAN}└──────────────────────────────")

        except FileNotFoundError:
            with print_lock:
                print(f"{Fore.RED}错误: 路径不存在 {repo_path}")
        except Exception as e:
            with print_lock:
                print(f"{Fore.RED}执行出错 [{repo_name}]: {e}")

    def _get_repo_status_summary(self, repo_path, highlight_indices=None):
        repo_name = os.path.basename(repo_path)
        display_name = self._highlight_text(repo_name, highlight_indices, base_color="")
        
        try:
            res_status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True)
            is_dirty = bool(res_status.stdout.strip())
            
            res_branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path, capture_output=True, text=True)
            branch = res_branch.stdout.strip()

            res_ahead = subprocess.run(["git", "rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"], cwd=repo_path, capture_output=True, text=True)
            
            sync_state = ""
            if res_ahead.returncode == 0:
                ahead, behind = res_ahead.stdout.strip().split()
                if int(ahead) > 0: sync_state += f"{Fore.GREEN}↑{ahead} "
                if int(behind) > 0: sync_state += f"{Fore.RED}↓{behind} "
            
            status_symbol = f"{Fore.RED}CHANGES" if is_dirty else f"{Fore.GREEN}CLEAN"
            return (display_name, branch, status_symbol, sync_state)
        except Exception:
            return (display_name, "Unknown", f"{Fore.RED}ERROR", "")

    def run_concurrent(self, args, is_shell=False, targets_map=None):
        """
        targets_map: {path: indices}
        """
        if targets_map is None:
            targets_map = {repo: set() for repo in self.repos}
        
        if not targets_map:
            print(f"{Fore.YELLOW}没有指定或找到有效的仓库。")
            return

        print(f"{Style.BRIGHT}正在 {len(targets_map)} 个仓库中执行命令...\n")
        
        with ThreadPoolExecutor(max_workers=min(10, len(targets_map))) as executor:
            # 传递 repo 和对应的高亮索引
            futures = [
                executor.submit(self._run_single_repo, repo, args, is_shell, targets_map[repo]) 
                for repo in targets_map
            ]

    def show_summary(self, targets_map=None):
        if targets_map is None:
            targets_map = {repo: set() for repo in self.repos}
        
        if not targets_map:
            print(f"{Fore.YELLOW}没有指定或找到有效的仓库。")
            return
        
        print(f"{Style.BRIGHT}正在分析 {len(targets_map)} 个仓库状态...\n")
        # 调整 Name 列宽，因为 ANSI 转义字符不占用显示宽度但占用字符串长度，这里简单增加 buffer
        # 更好的做法是计算可见字符长度，这里为了简单给个宽一点的
        print(f"{'Repository':<35} | {'Branch':<15} | {'Status':<10} | {'Sync'}")
        print("-" * 75)

        results = []
        with ThreadPoolExecutor(max_workers=min(20, len(targets_map))) as executor:
            futures = [
                executor.submit(self._get_repo_status_summary, repo, targets_map[repo]) 
                for repo in targets_map
            ]
            for f in futures:
                results.append(f.result())
        
        for name_display, branch, status, sync in results:
            # 注意: name_display 包含隐藏的颜色代码，format 对齐可能会不准
            # 简单修复：使用更宽松的填充
            # 或者先计算长度差 (这里不再展开复杂的 ANSI 对齐逻辑)
            
            # 使用简单的手动补空格方式 (假设颜色代码固定长度很难，这里直接让列更宽)
            # 这里简单处理：让 name 占用 print 位置，但如果颜色代码多，可能会导致后面的列不对齐
            # 完美的对齐需要 stripping ansi codes 来计算长度，暂且忽略微小的不对齐
            print(f"{name_display:<35} | {branch:<15} | {status:<10} | {sync}")
        print("-" * 75)

def print_help():
    print(f"""
{Fore.CYAN}{Style.BRIGHT}MGit - Multi-Git Repository Manager
===================================
{Fore.WHITE}用法: mgit [-t targets] <command> [args...]

{Fore.YELLOW}选项:{Style.RESET_ALL}
  -t, --target <idx/name>  指定目标仓库(支持索引或分词模糊匹配)
                           例如: -t 0
                                 -t re1 (匹配 repo1)
                                 -t sfa (匹配 search-framework-android)

{Fore.YELLOW}管理命令:{Style.RESET_ALL}
  mgit repo-add <path>     添加仓库
  mgit repo-rm <path/id>   移除仓库
  mgit repo-list           列出仓库 (支持 -t 筛选查看)

{Fore.YELLOW}批量操作:{Style.RESET_ALL}
  mgit summary             显示仓库概览 (支持 -t)
  mgit exec "cmd"          执行 Shell 命令 (支持 -t)
  mgit <git_cmd> ...       执行 Git 命令 (支持 -t)

{Fore.YELLOW}示例:{Style.RESET_ALL}
  mgit status              # 所有仓库状态
  mgit -t re1 pull         # 匹配 repo1 并拉取
  mgit -t web exec ls      # 匹配 web 相关仓库并列出文件
    """)

def main():
    mgit = MGit()
    
    if len(sys.argv) < 2:
        print_help()
        return

    target_selector = None
    args_start_idx = 1
    
    if len(sys.argv) >= 3 and sys.argv[1] in ("-t", "--target"):
        target_selector = sys.argv[2]
        args_start_idx = 3
    
    if len(sys.argv) <= args_start_idx:
        print_help()
        return

    command = sys.argv[args_start_idx]
    args = sys.argv[args_start_idx+1:]

    # 获取目标仓库列表 map {repo: indices}
    target_map = None
    if target_selector:
        target_map = mgit.get_target_repos(target_selector)
        # 如果指定了筛选器但没结果，直接返回
        if not target_map:
            return
    else:
        # 没指定，默认全部，且无高亮
        target_map = {repo: set() for repo in mgit.repos}

    if command == "repo-add":
        if not args:
            print(f"{Fore.RED}用法: mgit repo-add <path/to/repo>")
        else:
            mgit.add_repo(args[0])
            
    elif command == "repo-rm":
        if not args:
            print(f"{Fore.RED}用法: mgit repo-rm <path_or_index>")
        else:
            mgit.remove_repo(args[0])
            
    elif command == "repo-list":
        mgit.list_repos(target_map)

    elif command == "summary":
        mgit.show_summary(target_map)
        
    elif command == "exec":
        if not args:
            print(f"{Fore.RED}用法: mgit exec \"<shell command>\"")
        else:
            shell_cmd = " ".join(args)
            mgit.run_concurrent(shell_cmd, is_shell=True, targets_map=target_map)

    else:
        git_args = [command] + args
        mgit.run_concurrent(git_args, is_shell=False, targets_map=target_map)

if __name__ == "__main__":
    main()