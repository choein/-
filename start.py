# -*- coding: utf-8 -*-
import sys
import time
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

# --- 常量 ---
class Config:
    """存放所有设置和文件路径"""
	#保存运行程序所需要的文件
    DATA_DIR = "data"
	#保存导出的文件
    OUTPUT_DIR = "output"
	#保存需要转换成ciku.txt或danzi.txt的txt文件
    UPDATE_DIR = "update"
    
	#用于生成五笔编码
    DANZI_FILE = f"{DATA_DIR}/danzi.txt"
	#主词库
    CIKU_FILE = f"{DATA_DIR}/ciku.txt"
	#用于导出为RIME词库时，补充文件头部的内容
    HEAD_FILE = f"{DATA_DIR}/head.txt"
	#用于导出为RIME词库时，补充一级简码的全码
    STEM_FILE = f"{DATA_DIR}/stem.txt"
	#批量自动录入词条文件
    BATCH_FILE = "batch_add.txt"
	#默认导出文件名
    DEFAULT_OUTPUT_FILE = "wubi98_ci.dict.yaml"

# --- 辅助功能 ---
def log_info(message: str):
    """打印參考資訊"""
    print(f"[INFO] {message}")

def log_error(message: str):
    """打印錯誤訊息"""
    print(f"[ERROR] {message}", file=sys.stderr)

# --- 文件读取/写入 ---
def load_danzi_file(file_path: Path) -> Dict[str, str]:
    if not file_path.exists():
        log_error(f"文件 '{file_path}' 不存在，请确保文件已放入 '{Config.DATA_DIR}' 文件夹中。")
        return {}
    data = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                char, code = parts[0], parts[1]
                if char not in data: data[char] = code
    return data

def load_ciku_structured(file_path: Path) -> Dict[str, List[str]]:
    if not file_path.exists():
        log_error(f"文件 '{file_path}' 不存在，请确保文件已放入 '{Config.DATA_DIR}' 文件夹中。")
        return {}
    data = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                code, words = parts[0], parts[1:]
                data[code] = words
    return data

def load_stem_file(file_path: Path) -> Dict[str, str]:
    if not file_path.exists():
        log_error(f"文件 '{file_path}' 不存在，单字简码的词条将无法导出全码。")
        return {}
    data = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                char, full_code = parts[0][0], parts[1]
                if char not in data: data[char] = full_code
    return data

def write_ciku_structured(file_path: Path, data: Dict[str, List[str]]):
    log_info(f"正在更新文件： {file_path}...")
    try:
        file_path.parent.mkdir(exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            for code, words in sorted(data.items()):
                if words: f.write(f"{code} {' '.join(words)}\n")
        log_info("词库文件更新成功！")
    except Exception as e: log_error(f"更新词库文件时出错: {e}")

def append_to_danzi_file(file_path: Path, char: str, code: str):
    log_info(f"正在将新的单字 [{char}] 追加到 {file_path}...")
    try:
        file_path.parent.mkdir(exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f: f.write(f"{char} {code}\n")
        log_info("单字文件更新成功！")
    except Exception as e: log_error(f"更新单字文件时出错: {e}")

# --- 词库自动升级功能 ---
def analyze_dict_file(file_path: Path) -> Dict:
    """分析用户提供的词库文件特性，确保数据的可用性"""
    analysis = { "delimiter": "space", "format": "unknown", "structure": "single", "entries": [] }
    lines = None
    encodings_to_try = ['utf-8-sig', 'utf-16', 'utf-8', 'gb18030', 'gbk']
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                lines = [line.strip() for line in f if line.strip()]
            log_info(f"文件 '{file_path.name}' 使用 '{encoding}' 编码成功读取。")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if lines is None:
        log_error(f"读取文件 {file_path.name} 时出错：文件编码不兼容。")
        return None
    if not lines: return None

    if '\t' in lines[0]: analysis["delimiter"] = "tab"
    
    code_first_votes, word_first_votes = 0, 0
    def is_code(s): return s and s.isalpha() and s.islower()

    for line in lines[:100]:
        parts = line.split('\t' if analysis["delimiter"] == "tab" else ' ')
        if len(parts) < 2: continue
        if is_code(parts[0]) and not is_code(parts[1]): code_first_votes += 1
        elif not is_code(parts[0]) and is_code(parts[1]): word_first_votes += 1
    
    if code_first_votes > word_first_votes: analysis["format"] = "code_first"
    elif word_first_votes > code_first_votes: analysis["format"] = "word_first"
    else: return analysis

    # 將所有词条存入列表，避免覆盖
    all_entries = []
    for line in lines:
        parts = line.split('\t' if analysis["delimiter"] == "tab" else ' ')
        if len(parts) < 2: continue

        if analysis["format"] == "code_first":
            code, terms = parts[0], parts[1:]
            if len(terms) > 1: analysis["structure"] = "multi"
            if is_code(code):
                for term in terms:
                    all_entries.append((term, code))
        else:
            if len(parts) == 2 and is_code(parts[1]):
                code, term = parts[1], parts[0]
                all_entries.append((term, code))
    
    analysis["entries"] = all_entries
    return analysis

def perform_upgrade(analysis: Dict, file_path: Path):
    """执行具体的升级操作，使用完整的数据"""
    all_entries = analysis["entries"]
    danzi_entries = [(term, code) for term, code in all_entries if len(term) == 1]
    ciku_entries = [(term, code) for term, code in all_entries if len(term) > 1]
    
    # 报告分析结果
    log_info(f"分析报告:")
    log_info(f"  - 分隔符: {'Tab' if analysis['delimiter'] == 'tab' else '空格'}")
    log_info(f"  - 格式: {'编码在前' if analysis['format'] == 'code_first' else '词条在前'}")
    log_info(f"  - 结构: {'单行多义' if analysis['structure'] == 'multi' else '单行单义'}")
    log_info(f"  - 內容: 包含 {len(danzi_entries)} 个单字, {len(ciku_entries)} 个词组。（非精确统计）")

    # 升级替换 danzi.txt
    if danzi_entries:
        current_danzi_count = len(load_danzi_file(Path(Config.DANZI_FILE)))
        log_info(f"检测到新文件中有 {len(danzi_entries)} 个单字 (当前 danzi.txt 有 {current_danzi_count} 个)。")
        if input("是否用这些单字替换现有的 danzi.txt? (y/n): ").lower() == 'y':
            new_danzi_dict = {}
            for term, code in danzi_entries:
                if len(code) > 1:
                    new_danzi_dict[term] = code # 后面的会覆盖前面的，以保持每个字的编码的唯一性
            
            log_info(f"已过滤 {len(danzi_entries) - len(new_danzi_dict)} 个一级简码单字...")
            with open(Config.DANZI_FILE, 'w', encoding='utf-8') as f:
                for char, code in sorted(new_danzi_dict.items()):
                    f.write(f"{char} {code}\n")
            log_info(f"danzi.txt 已成功升级，写入 {len(new_danzi_dict)} 个单字。")

    # 升级替换 ciku.txt
    if all_entries:
        current_ciku = load_ciku_structured(Path(Config.CIKU_FILE))
        current_ciku_count = sum(len(v) for v in current_ciku.values())
        log_info(f"检测到新文件中有 {len(all_entries)} 个词条 (当前 ciku.txt 有 {current_ciku_count} 个)。")
        
        if not ciku_entries: log_info("提示：此文件似乎只包含单字。")
        
        if input("是否用新文件的所有內容替换现有的 ciku.txt? (y/n): ").lower() == 'y':
            new_ciku_structured = {}
            for term, code in all_entries:
                if code not in new_ciku_structured: new_ciku_structured[code] = []
                if term not in new_ciku_structured[code]: # 避免重复
                    new_ciku_structured[code].append(term)
            
            for code in new_ciku_structured:
                new_ciku_structured[code].sort()
            write_ciku_structured(Path(Config.CIKU_FILE), new_ciku_structured)

def check_for_updates():
    """启动时检查 update 文件夹是否存在词库并执行升级流程"""
    update_dir = Path(Config.UPDATE_DIR)
    if not update_dir.is_dir(): update_dir.mkdir(exist_ok=True)
    update_files = list(update_dir.glob("*.txt"))
    if not update_files: return False

    log_info(f"在 '{Config.UPDATE_DIR}' 文件夹中检测到 {len(update_files)} 个待处理文件，准备进入词库升级模式。")
    for file_path in update_files:
        print("\n" + "-"*20 + f" 正在处理文件: {file_path.name} " + "-"*20)
        analysis = analyze_dict_file(file_path)
        if not analysis or analysis["format"] == "unknown":
            log_error(f"文件 '{file_path.name}' 为空或格式无法被自动识别，已跳过。")
            continue
        
        perform_upgrade(analysis, file_path)

    log_info(f"所有升级操作已完成，正在清空 {Config.UPDATE_DIR} 文件夹...")
    for file_path in update_files:
        file_path.unlink()
    log_info(f"{Config.UPDATE_DIR} 文件夹已清空。")
    return True

# --- 核心功能 ---
def generate_word_code(word: str, danzi: Dict[str, str]) -> Tuple[str, List[str]]:
    char_codes, missing_chars = [], []
    for char in word:
        if char in danzi: char_codes.append(danzi[char])
        else: missing_chars.append(char)
    if missing_chars: return None, missing_chars
    word_len = len(char_codes)
    if word_len == 1: return char_codes[0], []
    if word_len == 2: return char_codes[0][:2] + char_codes[1][:2], []
    if word_len == 3: return char_codes[0][0] + char_codes[1][0] + char_codes[2][:2], []
    if word_len == 4: return char_codes[0][0] + char_codes[1][0] + char_codes[2][0] + char_codes[3][0], []
    if word_len > 4: return char_codes[0][0] + char_codes[1][0] + char_codes[2][0] + char_codes[-1][0], []
    return None, []

def export_rime_dict(ciku_structured: Dict[str, List[str]], stem_data: Dict[str, str]):
    log_info("已进入 RIME 词库导出模式。")
    output_dir = Path(Config.OUTPUT_DIR); output_dir.mkdir(exist_ok=True)
    default_filename = Config.DEFAULT_OUTPUT_FILE
    user_filename = input(f"请输入导出文件名 (默认为 '{default_filename}', 直接按 Enter 使用默认文件名): ")
    output_filename = user_filename if user_filename else default_filename
    output_path = output_dir / output_filename
    export_lines, head_path = [], Path(Config.HEAD_FILE)
    if head_path.exists():
        with open(head_path, 'r', encoding='utf-8') as f: export_lines.extend(f.readlines())
    else: log_error(f"文件 '{Config.HEAD_FILE}' 不存在。")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    export_lines.append(f"# 导出时间：{current_time}\n")
    log_info("正在处理词库数据...")
    for code, words in sorted(ciku_structured.items()):
        weight = 1100000
        for word in words:
            line_parts = [word, code, str(weight)]
            if len(code) == 1 and word in stem_data: line_parts.append(stem_data[word])
            export_lines.append("\t".join(line_parts) + "\n")
            weight -= 10
    log_info(f"正在导出到文件: {output_path} ...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f: f.writelines(export_lines)
        log_info(f"导出成功！文件已保存为 {output_path}")
    except Exception as e: log_error(f"导出文件时出错: {e}")

def edit_mode(ciku_structured: Dict[str, List[str]]):
    log_info("已进入编辑模式，输入 'q' 返回主菜单。")
    while True:
        code = input("\n请输入要编辑的词条编码 (输入'q'退出): ")
        if code.lower() == 'q': break
        if not code: continue
        if code not in ciku_structured or not ciku_structured[code]:
            log_error(f"编码 [{code}] 不存在。"); continue
        while True:
            word_list = ciku_structured[code]
            print(f"\n--- 正在编辑编码 [{code}] ---")
            if not word_list:
                log_info("此编码下所有的词条都已被删除。"); del ciku_structured[code]; break
            for i, word in enumerate(word_list): print(f"  {i+1}. {word}")
            action = input("请选择操作: [D] 删除, [M] 调整位置, [Q] 完成退出: ").lower()
            if action == 'q': log_info(f"完成编辑 [{code}]。"); break
            elif action == 'd':
                del_num_str = input(f"请输入要删除的词条编号 (1-{len(word_list)}): ")
                try:
                    del_idx = int(del_num_str) - 1
                    if 0 <= del_idx < len(word_list):
                        removed_word = word_list.pop(del_idx); log_info(f"词条 [{removed_word}] 已删除。")
                        write_ciku_structured(Path(Config.CIKU_FILE), ciku_structured)
                    else: log_error("无效编号！")
                except ValueError: log_error("请输入数字！")
            elif action == 'm':
                move_num_str = input(f"请输入要调整位置的词条编号 (1-{len(word_list)}): ")
                try:
                    old_idx = int(move_num_str) - 1
                    if not (0 <= old_idx < len(word_list)): log_error("无效编号！"); continue
                    new_pos_str = input(f"请输入新的位置 (1-{len(word_list)}): ")
                    new_idx = int(new_pos_str) - 1
                    if not (0 <= new_idx < len(word_list)): log_error("无效目标位置！"); continue
                    word_to_move = word_list.pop(old_idx); word_list.insert(new_idx, word_to_move)
                    log_info(f"词条 [{word_to_move}] 已调整位置。")
                    write_ciku_structured(Path(Config.CIKU_FILE), ciku_structured)
                except ValueError: log_error("请输入数字！")
            else: log_error("无效操作！")

def entry_mode(ciku_structured: Dict[str, List[str]], danzi: Dict[str, str]):
    log_info("已进入录入词条模式，输入 'q' 可返回主菜单。")
    while True:
        word = input("\n请输入要录入的词条 (输入q退出): ")
        if word.lower() == 'q': break
        if not word: continue
        generated_code, missing_chars = generate_word_code(word, danzi)
        while missing_chars:
            missing_char = missing_chars.pop(0)
            log_error(f"字库中缺少单字 '{missing_char}'，请补充添加。")
            new_char_code = input(f"请为 '{missing_char}' 输入五笔编码: ")
            if not new_char_code or not all('a' <= c <= 'z' for c in new_char_code):
                log_error("无效编码！"); break
            danzi[missing_char] = new_char_code
            append_to_danzi_file(Path(Config.DANZI_FILE), missing_char, new_char_code)
            generated_code, missing_chars = generate_word_code(word, danzi)
        if not generated_code: log_error("无法生成编码！"); continue
        log_info(f"为词条 [{word}] 自动生成编码: [{generated_code}]")
        code = generated_code
        if code not in ciku_structured: ciku_structured[code] = [word]; log_info(f"已为新编码 [{code}] 添加词条 [{word}]。")
        else:
            if word in ciku_structured[code]: log_info(f"编码 [{code}] 中已存在词条 [{word}]。")
            else: ciku_structured[code].append(word); log_info(f"新词条 [{word}] 已追加到末尾。")
        write_ciku_structured(Path(Config.CIKU_FILE), ciku_structured)

def batch_entry_mode(ciku_structured: Dict[str, List[str]], danzi: Dict[str, str]):
    batch_file_path = Path(Config.BATCH_FILE)
    log_info(f"正在处理文件: {batch_file_path} ，开始执行批量录入。")
    with open(batch_file_path, 'r', encoding='utf-8') as f: words_to_add = [line.strip() for line in f if line.strip()]
    if not words_to_add: log_info("批量处理文件为空。"); return
    ciku_flat = {word for words in ciku_structured.values() for word in words}
    new_word_count = 0
    for word in words_to_add:
        if word in ciku_flat: log_info(f"忽略: [{word}] 已存在。"); continue
        generated_code, missing_chars = generate_word_code(word, danzi)
        while missing_chars:
            missing_char = missing_chars.pop(0)
            log_error(f"批量处理中断：[{word}] 缺少单字 '{missing_char}'，请补充。")
            new_char_code = input(f"请为 '{missing_char}' 输入五笔编码: ")
            if not new_char_code or not all('a' <= c <= 'z' for c in new_char_code):
                log_error("无效编码，已跳过。"); generated_code = None; break
            danzi[missing_char] = new_char_code
            append_to_danzi_file(Path(Config.DANZI_FILE), missing_char, new_char_code)
            generated_code, missing_chars = generate_word_code(word, danzi)
        if not generated_code: log_error(f"跳过: [{word}]。"); continue
        if generated_code not in ciku_structured: ciku_structured[generated_code] = []
        ciku_structured[generated_code].append(word)
        log_info(f"添加: [{word}] -> 编码 [{generated_code}]"); new_word_count += 1
    if new_word_count > 0: write_ciku_structured(Path(Config.CIKU_FILE), ciku_structured)
    log_info("批量处理完毕，正在清空 batch_add.txt ..."); open(batch_file_path, 'w').close()
    log_info("所有操作完成。")

# --- 互動式主函式 (Interactive Main Function) ---
def print_menu():
    """打印主菜单"""
    print("\n" + "=" * 40)
    print("      五笔词库管理")
    print("-" * 40)
    print("--- 词库修改 ---")
    print(" 1. 【录入】词条")
    print(" 2. 【编辑】编码下的词条")
    print("--- 导出词库 ---")
    print(" 9. 【导出】RIME词库")
    print("-" * 40)
    print(" 0. 【 退出 】")
    print("=" * 40)

def main():
    """主程序"""
    if check_for_updates():
        input("\n--- 词库升级完成，按 Enter 键加载新词库并进入主菜单 ---")
        
    log_info("正在加载数据，请稍候...")
    danzi = load_danzi_file(Path(Config.DANZI_FILE))
    ciku_structured = load_ciku_structured(Path(Config.CIKU_FILE))
    stem_data = load_stem_file(Path(Config.STEM_FILE))
    log_info(f"数据加载完毕！(单字: {len(danzi)}, 词库: {len(ciku_structured)})")
    
    batch_file_path = Path(Config.BATCH_FILE)
    if batch_file_path.exists() and batch_file_path.stat().st_size > 0:
        user_choice = input(f"[提示] 检测到文件 '{Config.BATCH_FILE}' 中有待处理的词条，是否立即执行批量录入词条? (y/n): ")
        if user_choice.lower() == 'y':
            batch_entry_mode(ciku_structured, danzi)
            input("\n--- 批量录入词条处理完成，按 Enter 键进入主菜单 ---")
    
    while True:
        print_menu()
        choice_str = input("请输入功能序号 (数字): ")
        if not choice_str.isdigit(): log_error("无效输入。"); time.sleep(1); continue
        choice = int(choice_str)
        if choice == 0: log_info("感谢使用，正在退出..."); break
        elif choice == 1: entry_mode(ciku_structured, danzi)
        elif choice == 2: edit_mode(ciku_structured)
        elif choice == 9: export_rime_dict(ciku_structured, stem_data); input("\n--- 导出完成，按 Enter 键返回主菜单 ---")
        else: log_error("无效选择！"); time.sleep(1)

if __name__ == "__main__":
    main()