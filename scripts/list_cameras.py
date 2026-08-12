"""
摄像头枚举工具 - 列出系统中所有可用摄像头
在 Windows 上运行此脚本，找到你的 USB 相机索引

使用方法:
    python list_cameras.py
"""
import cv2

from hardware.camera import get_camera_backends


def list_cameras():
    """枚举所有可用摄像头"""
    print("=" * 60)
    print("📹 枚举系统摄像头")
    print("=" * 60)

    found = []

    for backend, backend_name in get_camera_backends():
        print(f"\n--- {backend_name} 后端 ---")
        for index in range(10):  # 扫描 0-9
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"  ✅ 索引 {index}: {w}x{h}")
                    found.append((backend_name, index, w, h))
                cap.release()
            else:
                cap.release()

    print("\n" + "=" * 60)
    if found:
        print(f"共找到 {len(found)} 个可用摄像头:")
        for i, (backend, index, w, h) in enumerate(found):
            marker = " <-- 最可能是 USB 相机" if i > 0 and i == len(found) - 1 else ""
            print(f"  [{i}] {backend} 索引={index}  {w}x{h}{marker}")
        print("\n💡 打开「系统设置」→「相机」→ 输入对应的索引号即可")
        print("   也可以在 camera_params.yaml 中设置 camera_id")
        print(f"   如果索引 {found[0][1]} 是你的 USB 相机，则无需修改")
    else:
        print("❌ 未找到任何可用摄像头，请检查 USB 连接和驱动")
    print("=" * 60)

    return found


if __name__ == "__main__":
    list_cameras()
