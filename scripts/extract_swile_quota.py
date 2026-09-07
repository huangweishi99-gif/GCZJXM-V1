#!/usr/bin/env python3
"""从斯维尔清单计价软件提取定额数据"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def start_swile_software():
    """启动斯维尔清单计价软件"""
    exe_path = r"D:\THSware\斯维尔清单计价BQ6.0深圳版\bin\QDJJ2024.exe"
    if os.path.exists(exe_path):
        print(f"启动斯维尔软件: {exe_path}")
        try:
            process = subprocess.Popen(exe_path)
            return process
        except Exception as e:
            print(f"启动失败: {e}")
            return None
    else:
        print(f"文件不存在: {exe_path}")
        return None


def check_swile_running():
    """检查斯维尔软件是否运行"""
    try:
        import win32com.client
        try:
            swile = win32com.client.GetActiveObject("THS.QDJJ2024")
            return swile
        except Exception:
            return None
    except ImportError:
        return None


def extract_quota_data():
    """提取定额数据（通过分析数据库文件结构）"""
    print("=== 分析斯维尔定额库文件 ===")
    
    quota_dir = r"D:\THSware\斯维尔清单计价BQ6.0深圳版\深圳\定额库"
    
    # 列出所有定额库文件
    quota_files = []
    for root, dirs, files in os.walk(quota_dir):
        for f in files:
            if f.endswith('.Dek'):
                quota_files.append(os.path.join(root, f))
    
    print(f"发现 {len(quota_files)} 个定额库文件:")
    for f in quota_files:
        size = os.path.getsize(f) / 1024 / 1024
        print(f"  {os.path.basename(f)} ({size:.1f} MB)")
    
    # 尝试解析Dek文件（THSware Database V2.0格式）
    print("\n=== 尝试解析定额库文件 ===")
    
    for dek_file in quota_files[:3]:  # 只尝试前3个
        print(f"\n解析: {os.path.basename(dek_file)}")
        
        # 读取文件头
        with open(dek_file, 'rb') as f:
            header = f.read(100)
            print(f"文件头: {header[:30].hex()}")
            
            # 尝试查找文本内容
            f.seek(0)
            content = f.read(10000)
            try:
                text = content.decode('gbk', errors='ignore')
                # 提取看起来像定额的文本
                lines = text.split('\x00')
                quota_lines = []
                for line in lines:
                    if len(line) > 5 and len(line) < 100:
                        # 查找包含数字和中文的行（可能是定额子目）
                        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in line)
                        has_number = any(c.isdigit() for c in line)
                        if has_chinese and has_number:
                            quota_lines.append(line.strip())
                
                if quota_lines:
                    print(f"找到 {len(quota_lines)} 条疑似定额数据:")
                    for line in quota_lines[:10]:
                        print(f"  {line}")
            except Exception as e:
                print(f"解码失败: {e}")
    
    # 导出到JSON
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'swile_quota_extract.json'
    )
    
    # 创建一个示例结构
    quota_data = {
        "source": "斯维尔清单计价BQ6.0深圳版",
        "version": "2024",
        "extraction_method": "文件分析",
        "quota_files": [os.path.basename(f) for f in quota_files],
        "categories": {
            "装饰工程": ["深圳市装饰工程消耗(2003)"],
            "安装工程": ["深圳市安装工程消耗(2003)"],
            "建筑工程": ["深圳市建筑工程消耗(2003)"],
            "市政工程": ["深圳市市政工程消耗(2003)"],
            "园林工程": ["深圳园林绿化工程(2000)"],
            "房屋修缮": ["深圳市房屋修缮工程"],
            "装配式建筑": ["深圳市装配式建筑工程"],
            "轨道交通": ["深圳市城市轨道交通"],
            "高压工程": ["深圳市高(次高)压"],
            "环卫工程": ["深圳市环卫工程消耗"]
        },
        "note": "斯维尔定额库文件为专有格式(THSware Database V2.0)，无法直接解析。建议通过以下方式获取定额数据：1) 使用斯维尔软件导出Excel; 2) 使用斯维尔API; 3) 购买官方数据接口"
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(quota_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n定额库信息已保存: {output_path}")
    return quota_data


def main():
    print("=== 斯维尔定额数据提取工具 ===")
    
    # 检查斯维尔软件是否运行
    swile = check_swile_running()
    if swile:
        print("斯维尔软件已在运行")
    else:
        print("斯维尔软件未运行")
        # 可选：启动软件
        # process = start_swile_software()
        # if process:
        #     print("等待软件启动...")
        #     time.sleep(10)
    
    # 分析定额库文件
    extract_quota_data()
    
    print("\n=== 提取完成 ===")
    print("\n建议方案：")
    print("1. 手动打开斯维尔软件，使用'导出'功能将定额数据导出为Excel")
    print("2. 将导出的Excel文件放入'清单数据资料/AI学习清单/'目录")
    print("3. 运行 python app.py learn 命令学习定额数据")
    print("4. 或运行 python app.py import-quota 导入定额标准")


if __name__ == '__main__':
    main()
