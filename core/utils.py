"""
工具函数模块 - 提供通用的工具函数
"""
import sys
import os


def log_error(e, context=""):
    """
    统一的错误日志记录
    
    Args:
        e: 异常对象
        context: 错误上下文描述
    """
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if exc_tb:
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        lineno = exc_tb.tb_lineno
        msg = f"[ERROR] File: {fname}, Line: {lineno} | {type(e).__name__}: {str(e)}"
        if context:
            msg = f"[ERROR] {context} | File: {fname}, Line: {lineno} | {type(e).__name__}: {str(e)}"
        print(msg)
    else:
        msg = f"[ERROR] {type(e).__name__}: {str(e)}"
        if context:
            msg = f"[ERROR] {context} | {type(e).__name__}: {str(e)}"
        print(msg)



