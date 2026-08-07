#!/bin/bash
# FPV Receiver Linux 构建脚本
# 用法: ./scripts/build_fpv_rx.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXT_DIR="$PROJECT_ROOT/extern/fpv_rx"
OUT_DIR="$EXT_DIR/bin/linux"

echo "=== 构建 FPV Receiver (Linux) ==="
echo "源码目录: $EXT_DIR"
echo "输出目录: $OUT_DIR"

# 检查系统依赖
echo ""
echo "--- 检查系统依赖 ---"
DEPS=(python3-dev pybind11-dev libusb-1.0-0-dev libsodium-dev
      libavcodec-dev libavformat-dev libswscale-dev libavutil-dev pkg-config)
MISSING=()
for dep in "${DEPS[@]}"; do
    if ! dpkg -s "$dep" &>/dev/null 2>&1; then
        MISSING+=("$dep")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "缺少依赖: ${MISSING[*]}"
    echo "运行: sudo apt install ${MISSING[*]}"
    exit 1
fi
echo "所有依赖已满足"

# 构建
echo ""
echo "--- 编译 C++ 扩展 ---"
cd "$EXT_DIR"
python3 setup.py build_ext --inplace 2>&1

# 查找编译产物
echo ""
echo "--- 拷贝扩展到输出目录 ---"
mkdir -p "$OUT_DIR"
SO_FILE=$(find "$EXT_DIR" -maxdepth 1 -name 'fpv_rx*.so' -type f 2>/dev/null | head -1)
if [ -z "$SO_FILE" ]; then
    # 可能构建在 build/ 目录下
    SO_FILE=$(find "$EXT_DIR/build" -name 'fpv_rx*.so' -type f 2>/dev/null | head -1)
fi
if [ -n "$SO_FILE" ]; then
    cp "$SO_FILE" "$OUT_DIR/"
    echo "✅ 已复制: $SO_FILE → $OUT_DIR/"
else
    echo "⚠️  未找到编译产物，检查 build/ 目录"
    find "$EXT_DIR/build" -name 'fpv_rx*' -type f 2>/dev/null
fi

# 清理构建中间文件（可选）
echo ""
echo "--- 清理临时文件 ---"
rm -rf "$EXT_DIR/build" "$EXT_DIR/fpv_rx.egg-info" 2>/dev/null || true

echo ""
echo "=== 完成 ==="
echo "扩展已安装至: $OUT_DIR/"
