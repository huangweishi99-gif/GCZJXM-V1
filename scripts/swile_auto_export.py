#!/usr/bin/env python3
"""自动化操作斯维尔清单计价软件导出定额数据"""
import os
import sys
import time
import json
import subprocess
import win32gui
import win32con
import win32api

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_window(title):
    """查找窗口句柄"""
    def callback(handle, extra):
        if title in win32gui.GetWindowText(handle):
            extra.append(handle)
        return True
    handles = []
    win32gui.EnumWindows(callback, handles)
    return handles


def send_key_to_window(hwnd, key):
    """向窗口发送按键"""
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, key, 0)
    time.sleep(0.1)
    win32api.SendMessage(hwnd, win32con.WM_KEYUP, key, 0)


def start_swile_and_export():
    """启动斯维尔软件并尝试导出定额数据"""
    exe_path = r"D:\THSware\斯维尔清单计价BQ6.0深圳版\bin\QDJJ2024.exe"
    
    if not os.path.exists(exe_path):
        print(f"斯维尔软件不存在: {exe_path}")
        return False
    
    print("启动斯维尔清单计价软件...")
    try:
        process = subprocess.Popen(exe_path)
        
        # 等待软件启动（需要用户输入密码）
        print("等待软件启动，请在弹出的登录窗口中输入账号密码并登录...")
        print("登录后按任意键继续...")
        input()
        
        # 查找斯维尔主窗口
        time.sleep(5)
        handles = find_window("斯维尔")
        if handles:
            hwnd = handles[0]
            print(f"找到斯维尔窗口: {hwnd}")
            win32gui.SetForegroundWindow(hwnd)
            
            # 尝试打开定额库管理
            print("\n尝试打开定额库管理...")
            time.sleep(2)
            
            # 模拟菜单操作：文件 -> 导出
            # 先按Alt激活菜单
            send_key_to_window(hwnd, win32con.VK_MENU)
            time.sleep(0.5)
            
            # 按F打开文件菜单
            send_key_to_window(hwnd, ord('F'))
            time.sleep(0.5)
            
            # 按E选择导出
            send_key_to_window(hwnd, ord('E'))
            time.sleep(1)
            
            # 等待导出对话框
            print("等待导出对话框...")
            time.sleep(5)
            
            # 查找导出对话框
            export_handles = find_window("导出")
            if export_handles:
                print(f"找到导出对话框: {export_handles[0]}")
                # 按Enter确认导出
                send_key_to_window(export_handles[0], win32con.VK_RETURN)
                time.sleep(2)
                
                # 查找保存对话框
                save_handles = find_window("另存为")
                if save_handles:
                    print(f"找到保存对话框: {save_handles[0]}")
                    # 输入文件名
                    send_key_to_window(save_handles[0], ord('S'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('W'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('I'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('L'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('E'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('_'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('Q'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('U'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('O'))
                    time.sleep(0.5)
                    send_key_to_window(save_handles[0], ord('T'))
                    time.sleep(0.5)
                    
                    # 按Enter保存
                    send_key_to_window(save_handles[0], win32con.VK_RETURN)
                    print("定额数据已导出")
                    return True
            
            print("未能自动完成导出，请手动操作")
        else:
            print("未找到斯维尔主窗口")
            
        return False
        
    except Exception as e:
        print(f"操作失败: {e}")
        return False


def main():
    print("=== 斯维尔定额数据自动导出工具 ===")
    print("注意：此工具需要手动配合操作")
    print("\n操作步骤：")
    print("1. 脚本将启动斯维尔软件")
    print("2. 请在弹出的登录窗口中输入账号密码并登录")
    print("3. 登录后按回车继续")
    print("4. 脚本将尝试自动打开导出功能")
    print("5. 如果自动导出失败，请手动操作：文件 -> 导出 -> 选择Excel格式 -> 保存到 data/exports/")
    
    print("\n按任意键开始...")
    input()
    
    success = start_swile_and_export()
    
    if success:
        print("\n=== 导出成功 ===")
        print("接下来运行：")
        print("  python app.py learn 'data/exports/swile_quota.xlsx'")
    else:
        print("\n=== 导出失败 ===")
        print("请手动导出定额数据：")
        print("1. 打开斯维尔清单计价BQ6.0深圳版")
        print("2. 进入定额库管理")
        print("3. 选择要导出的定额库（如深圳市装饰工程消耗(2003)）")
        print("4. 使用'导出'功能，选择Excel格式")
        print("5. 保存到 data/exports/ 目录")
        print("6. 运行 python app.py learn 'data/exports/xxx.xlsx'")


if __name__ == '__main__':
    main()
