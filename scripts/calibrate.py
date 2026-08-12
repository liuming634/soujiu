"""
单应性矩阵标定工具
使用棋盘格图像进行相机到工作台的坐标映射标定
"""
import os
import sys
from logic.coordinate_mapper import PixelToPlaneMapper
from core.config import config


def calibrate_from_image(image_path, output_file="calibration_data/homography.npy",
                         pattern_size=None, square_size=None):
    """
    从单张棋盘格图像标定单应性矩阵

    Args:
        image_path: 棋盘格图像路径
        output_file: 输出文件路径
        pattern_size: 棋盘格角点数量 (列, 行)，默认使用 config.CHESSBOARD_PATTERN
        square_size: 棋盘格方格边长（米），默认使用 config.CHESSBOARD_SQUARE_SIZE
    """
    if pattern_size is None:
        pattern_size = config.CHESSBOARD_PATTERN
    if square_size is None:
        square_size = config.CHESSBOARD_SQUARE_SIZE

    # 将相对路径解析为基于项目根目录的绝对路径
    if output_file and not os.path.isabs(output_file):
        output_file = os.path.join(config.PROJECT_ROOT, output_file)
    if image_path and not os.path.isabs(image_path):
        image_path = os.path.join(config.PROJECT_ROOT, image_path)

    print("=" * 60)
    print("🎯 单应性矩阵标定工具")
    print("=" * 60)

    # 检查图像是否存在
    if not os.path.exists(image_path):
        print(f"[ERROR] 图像文件不存在: {image_path}")
        return False

    print("\n📷 标定参数:")
    print(f"   图像路径: {image_path}")
    print(f"   角点数量: {pattern_size[0]} x {pattern_size[1]}")
    print(f"   方格边长: {square_size} m")
    print(f"   输出文件: {output_file}\n")

    try:
        # 执行标定
        print("⏳ 正在标定...")
        mapper = PixelToPlaneMapper.calibrate(
            image_path=image_path,
            pattern_size=pattern_size,
            square_size=square_size
        )

        # 保存结果
        mapper.save(output_file)

        print("\n" + "=" * 60)
        print("✅ 标定完成！")
        print("=" * 60)
        print(f"单应性矩阵已保存到: {output_file}")
        print("\n💡 使用方法:")
        print("   from logic.coordinate_mapper import PixelToPlaneMapper")
        print(f"   mapper = PixelToPlaneMapper(homography_file='{output_file}')")
        print("   x, y = mapper.pixel_to_plane(pixel_x, pixel_y)")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n[ERROR] 标定失败: {e}")
        return False


if __name__ == '__main__':
    # 默认参数（基于项目根目录）
    image_path = os.path.join(config.PROJECT_ROOT, "chessboard_images", "img1.jpg")
    output_file = os.path.join(config.PROJECT_ROOT, "calibration_data", "homography.npy")
    pattern_size = None
    square_size = None

    # 允许命令行参数覆盖（传入绝对路径或相对于当前工作目录的路径）
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    if len(sys.argv) > 3:
        pattern_size = tuple(map(int, sys.argv[3].split('x')))
    if len(sys.argv) > 4:
        square_size = float(sys.argv[4])

    success = calibrate_from_image(
        image_path=image_path,
        output_file=output_file,
        pattern_size=pattern_size,
        square_size=square_size
    )

    if not success:
        sys.exit(1)
