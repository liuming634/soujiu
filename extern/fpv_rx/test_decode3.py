import sys, os, time, av, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpv_rx

r = fpv_rx.Receiver()
r.start('0bda:8812', 161, 0, 'gs.key', 7669206)
time.sleep(6)

ctx = av.CodecContext.create('hevc', 'r')
saved = False

for i in range(200):
    fd = r.recv(200)
    if fd.valid:
        raw = bytes(fd.data)
        # Check NAL header
        if raw[:4] == b'\x00\x00\x00\x01':
            nal_hdr0 = raw[4]
            nal_hdr1 = raw[5] if len(raw) > 5 else -1
            nal_type = (nal_hdr0 >> 1) & 0x3F
            if not saved:
                print(f'NAL: type={nal_type} bytes={raw[4]:02x} {raw[5]:02x} size={len(raw)}', flush=True)
        try:
            for p in ctx.parse(raw):
                for f in ctx.decode(p):
                    arr = f.to_ndarray(format='bgr24')
                    if arr.size > 0:
                        cv2.imwrite('debug_frame.jpg', arr)
                        print(f'DECODED: shape={arr.shape}', flush=True)
                        saved = True
        except Exception as e:
            if not saved:
                print(f'Error: {e}', flush=True)
    time.sleep(0.1)
    if saved:
        break

if not saved:
    print('NO FRAME DECODED', flush=True)
r.stop()
