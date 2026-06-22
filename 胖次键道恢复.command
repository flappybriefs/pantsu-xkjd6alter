#!/bin/zsh

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR" || exit 1

clear
echo "胖次键道维护日志恢复"
echo "可恢复最近 5 次合并前的状态。"
echo
/usr/bin/python3 "$SCRIPT_DIR/tools/pantsu_maintenance.py" restore-log
result=$?

echo
if (( result != 0 )); then
  echo "恢复工具运行失败，错误码：$result"
fi
read "?按回车键关闭窗口……"
exit $result
