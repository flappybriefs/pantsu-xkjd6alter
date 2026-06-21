#!/bin/zsh

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR" || exit 1

clear
/usr/bin/python3 "$SCRIPT_DIR/tools/pantsu_maintenance.py" interactive
status=$?

if (( status != 0 )); then
  echo
  echo "维护工具运行失败，错误码：$status"
  read "?按回车键关闭窗口……"
fi

exit $status
