"""Windowed entry point with visible startup errors instead of silent failures."""
import os
from pathlib import Path
import traceback

try:
    from app import main
    raise SystemExit(main())
except Exception:
    details = traceback.format_exc()
    error_file = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'DailyFocus' / 'startup_error.log'
    try:
        error_file.parent.mkdir(parents=True, exist_ok=True)
        error_file.write_text(details, encoding='utf-8')
    except OSError:
        pass
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,
        '启动未成功。\n\n错误详情：\n' + details[-1800:] + '\n\n日志：' + str(error_file),
        '今日新闻 · 启动失败', 0x10)
